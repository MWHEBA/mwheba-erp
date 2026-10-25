# -*- coding: utf-8 -*-
import logging
from decimal import Decimal
from typing import Optional
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from financial.models.treasury_access import UserTreasuryAccess
from financial.models.journal_entry import JournalEntryLine
from cheques.models import Cheque, ChequeType, ChequeStatus

logger = logging.getLogger(__name__)


class ChequeDisbursementSecurityService:
    """
    خدمة إنفاذ حدود الصرف وحجز السقف اليومي لأوراق الدفع
    (Atomic Disbursement Limit Reservation & Cross-User Attribution Guard)
    """

    @classmethod
    def enforce_and_reserve(
        cls,
        user,
        bank_account_id: int,
        amount: Decimal,
        as_of_date=None,
        request=None,
        exclude_cheque_id: Optional[int] = None,
    ) -> bool:
        """
        إنفاذ سقف الصرف وحجزه ذرياً قبل إصدار شيك الدفع:
        1. قفل سجل صلاحيات المستخدم والخزينة بـ select_for_update لمنع السباق التزامني.
        2. فحص سقف العملية الواحدة max_single_disbursement_limit.
        3. احتساب إجمالي المنصرف والالتزام المحجوز اليومي:
           - المنصرفات البنكية المباشرة الصادرة اليوم بنفس المستخدم (مع استبعاد قيود صرف الشيكات تماماً).
           - الشيكات الصادرة والمعتمدة اليوم بنفس المستخدم وما زالت معلقة.
           - الشيكات الصادرة والمعتمدة اليوم بنفس المستخدم وتم صرفها بنكياً اليوم (حتى لو نفذ الصرف مستخدم آخر).
        4. فحص تجاوز السقف اليومي daily_disbursement_limit وإثارة ValidationError فورياً عند التجاوز.
        """
        if not user or not user.is_authenticated:
            raise ValidationError(_("يجب تسجيل الدخول لتنفيذ عمليات الصرف."))

        actual_today = timezone.now().date()
        today = as_of_date or actual_today
        amt = Decimal(str(amount or "0.00"))

        access = UserTreasuryAccess.objects.select_for_update().filter(
            user=user,
            treasury_id=bank_account_id
        ).first()

        if not access:
            # إذا كان مدير نظام أو مستخدم بدون تقييد خزن محددة
            if getattr(user, "is_superuser", False):
                return True
            # فحص ما إذا كان المستخدم مقيداً بنظام الخزن
            if UserTreasuryAccess.objects.filter(user=user).exists():
                raise ValidationError(_("ليس لديك صلاحية صرف من هذا الحساب البنكي."))
            return True

        if not access.can_disburse:
            raise ValidationError(_("ليس لديك صلاحية صرف أو سداد من هذا الحساب البنكي."))

        # التحقق من سريان الصلاحية بتاريخ التنفيذ الفعلي لمنع تجاوز الصلاحية بتواريخ قديمة
        if not access.is_currently_valid(actual_today):
            raise ValidationError(_("صلاحية الصرف من هذا الحساب البنكي منتهية أو غير سارية بتاريخ اليوم."))
        if as_of_date and as_of_date != actual_today and not access.is_currently_valid(as_of_date):
            raise ValidationError(_("صلاحية الصرف من هذا الحساب البنكي غير سارية بتاريخ الحركة المطلوبة."))

        # 1. فحص سقف العملية الواحدة
        if access.max_single_disbursement_limit and amt > access.max_single_disbursement_limit:
            raise ValidationError(
                _("قيمة الشيك ({amount}) تتجاوز الحد الأقصى المصرح به للصرف للحركة الواحدة ({limit}).").format(
                    amount=amt,
                    limit=access.max_single_disbursement_limit
                )
            )

        # 2. فحص السقف اليومي التراكمي المحجوز بتاريخ التنفيذ الفعلي
        if access.daily_disbursement_limit:
            # أ. المنصرفات البنكية المباشرة للمستخدم اليوم (مع استبعاد قيود صرف الشيكات لمنع الازدواج)
            direct_bank_disbursements = JournalEntryLine.objects.filter(
                account_id=bank_account_id,
                journal_entry__created_by=user,
                journal_entry__status="posted",
                credit__gt=Decimal("0.00")
            ).filter(
                models.Q(journal_entry__date=actual_today) | models.Q(journal_entry__created_at__date=actual_today)
            ).exclude(
                models.Q(journal_entry__source_module="cheques") | models.Q(journal_entry__entry_type__startswith="cheque_")
            ).aggregate(total=models.Sum("credit"))["total"] or Decimal("0.00")

            # ب. الشيكات الصادرة والمعتمدة اليوم من نفس المستخدم والمعلقة (تُنسب للمُصدر الفعلي فقط)
            active_qs = Cheque.objects.filter(
                deposit_bank_account_id=bank_account_id,
                cheque_type=ChequeType.PAYABLE,
                issued_by=user,
            ).filter(
                models.Q(issued_at__date=actual_today) | (models.Q(issued_at__isnull=True) & models.Q(created_at__date=actual_today))
            ).exclude(
                status__in=[ChequeStatus.DRAFT, ChequeStatus.CANCELLED, ChequeStatus.CLEARED]
            )
            if exclude_cheque_id:
                active_qs = active_qs.exclude(id=exclude_cheque_id)
            active_issued_today = active_qs.aggregate(total=models.Sum("functional_amount"))["total"] or Decimal("0.00")

            # ج. الشيكات الصادرة والمعتمدة اليوم من نفس المستخدم وصُرفت بنكياً اليوم
            cleared_qs = Cheque.objects.filter(
                deposit_bank_account_id=bank_account_id,
                status=ChequeStatus.CLEARED,
                issued_by=user,
            ).filter(
                models.Q(issued_at__date=actual_today) | (models.Q(issued_at__isnull=True) & models.Q(created_at__date=actual_today))
            )
            if exclude_cheque_id:
                cleared_qs = cleared_qs.exclude(id=exclude_cheque_id)
            cleared_from_user_today = cleared_qs.aggregate(total=models.Sum("functional_amount"))["total"] or Decimal("0.00")

            total_committed_today = direct_bank_disbursements + active_issued_today + cleared_from_user_today

            if (total_committed_today + amt) > access.daily_disbursement_limit:
                raise ValidationError(
                    _("إجمالي المنصرف والالتزامات المحجوزة اليوم سيصبح ({total}) مما يتجاوز السقف اليومي المصرح به للمستخدم ({limit}).").format(
                        total=(total_committed_today + amt),
                        limit=access.daily_disbursement_limit
                    )
                )

        return True
