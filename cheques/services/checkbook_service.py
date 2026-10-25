# -*- coding: utf-8 -*-
import logging
from typing import Optional
from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from financial.models import ChartOfAccounts
from cheques.models import (
    Checkbook,
    CheckbookLeaf,
    Cheque,
    ChequeActionLog,
    ChequeActionType,
)

logger = logging.getLogger(__name__)


class CheckbookService:
    """
    خدمة إدارة دفاتر الشيكات البنكية وأوراقها الذرية واستبدال الأوراق التالفة
    (Smart & Optional Checkbook Inventory Service)
    """

    @classmethod
    def create_checkbook(
        cls,
        bank_account,
        serial_from: int,
        serial_to: int,
        user,
        serial_prefix: str = "",
        name: Optional[str] = None,
    ) -> Checkbook:
        """
        إنشاء دفتر شيكات جديد وتوليد أوراقه الذرية تلقائياً مع قفل الحساب لمنع التداخل بالتزامن.
        """
        bank_account_id = bank_account.id if hasattr(bank_account, "id") else bank_account

        with transaction.atomic():
            # قفل سجل الحساب البنكي ذرياً
            ChartOfAccounts.objects.filter(pk=bank_account_id).select_for_update().exists()

            if serial_to < serial_from:
                raise ValidationError(_("نهاية الترقيم التسلسلي يجب أن تكون أكبر من أو تساوي البداية."))

            # التحقق من عدم التداخل
            overlapping = Checkbook.objects.filter(
                bank_account_id=bank_account_id,
                serial_prefix=serial_prefix
            ).filter(
                models.Q(serial_from__lte=serial_to) & models.Q(serial_to__gte=serial_from)
            )
            if overlapping.exists():
                raise ValidationError(_("نطاق أرقام هذا الدفتر يتداخل مع دفتر شيكات آخر مسجل لنفس الحساب البنكي."))

            if not name:
                acc = ChartOfAccounts.objects.get(pk=bank_account_id)
                prefix_str = f"({serial_prefix}) " if serial_prefix else ""
                name = f"دفتر {acc.name} {prefix_str}[{serial_from} -> {serial_to}]"

            checkbook = Checkbook(
                name=name,
                bank_account_id=bank_account_id,
                serial_prefix=serial_prefix,
                serial_from=serial_from,
                serial_to=serial_to,
                leaf_count=serial_to - serial_from + 1,
                current_serial=serial_from,
                created_by=user,
            )
            checkbook.save()
            return checkbook

    @classmethod
    def get_next_available_leaf(
        cls,
        bank_account_id: int,
        serial_prefix: Optional[str] = None
    ) -> Optional[CheckbookLeaf]:
        """
        الحصول على ورقة الشيك التالية المتاحة من الدفاتر النشطة لهذا الحساب البنكي مع قفل الصف.
        """
        qs = CheckbookLeaf.objects.select_for_update().filter(
            checkbook__bank_account_id=bank_account_id,
            checkbook__is_active=True,
            status=CheckbookLeaf.LeafStatus.AVAILABLE
        )
        if serial_prefix is not None:
            qs = qs.filter(checkbook__serial_prefix=serial_prefix)

        return qs.order_by("checkbook__id", "id").first()

    @classmethod
    def replace_ruined_leaf(
        cls,
        cheque: Cheque,
        new_leaf: CheckbookLeaf,
        voided_reason: str,
        ruined_leaf_image=None,
        user=None
    ) -> Cheque:
        """
        إجراء استبدال ورقة الشيك التالفة في الطابعة أو الممزقة:
        1. وسم الورقة القديمة كـ VOIDED مع توثيق السبب والصورة الإلزاميين.
        2. تخصيص الورقة الجديدة المتاحة وتحويلها إلى ISSUED.
        3. تحديث رقم الشيك الورقي مع تفعيل سياق التعديل المعتمد _authorized_mutation_context.
        4. تسجيل حركة تدقيق REPLACE_LEAF في ChequeActionLog.
        """
        if not voided_reason or not voided_reason.strip():
            raise ValidationError(_("يجب تدوين سبب إتلاف ورقة الشيك الورقية."))

        with transaction.atomic():
            cheque_locked = Cheque.objects.select_for_update().get(pk=cheque.pk)
            old_leaf = cheque_locked.checkbook_leaf

            # التأكد من صلاحية الورقة الجديدة
            new_leaf_locked = CheckbookLeaf.objects.select_for_update().get(pk=new_leaf.pk)
            if new_leaf_locked.status != CheckbookLeaf.LeafStatus.AVAILABLE:
                raise ValidationError(_("ورقة الشيك البديلة المختارة غير متاحة في الدفتر."))

            # 1. إتلاف الورقة القديمة
            old_serial = ""
            if old_leaf:
                old_leaf_locked = CheckbookLeaf.objects.select_for_update().get(pk=old_leaf.pk)
                old_leaf_locked.status = CheckbookLeaf.LeafStatus.VOIDED
                old_leaf_locked.voided_reason = voided_reason
                if ruined_leaf_image:
                    old_leaf_locked.voided_image = ruined_leaf_image
                old_leaf_locked.save()
                old_serial = old_leaf_locked.serial_number

            # 2. تخصيص الورقة الجديدة
            new_leaf_locked.status = CheckbookLeaf.LeafStatus.ISSUED
            new_leaf_locked.save()

            # 3. تحديث الشيك مع السياق المعتمد
            cheque_locked._authorized_mutation_context = "REPLACE_RUINED_LEAF"
            cheque_locked.checkbook_leaf = new_leaf_locked
            cheque_locked.cheque_number = new_leaf_locked.serial_number
            cheque_locked.save()

            # 4. تسجيل حركة التدقيق
            ChequeActionLog.objects.create(
                cheque=cheque_locked,
                action=ChequeActionType.REPLACE_LEAF,
                from_status=cheque_locked.status,
                to_status=cheque_locked.status,
                action_date=timezone.now().date(),
                idempotency_key=f"REPLACE_LEAF:{cheque_locked.pk}:{new_leaf_locked.pk}:{timezone.now().timestamp()}",
                reason=f"استبدال ورقة تالفة {old_serial} بالورقة {new_leaf_locked.serial_number}: {voided_reason}",
                created_by=user,
            )

            logger.info(f"Leaf replaced for Cheque #{cheque_locked.pk}: Old '{old_serial}' -> New '{new_leaf_locked.serial_number}'")
            return cheque_locked
