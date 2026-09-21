"""
خدمة الرقابة المالية والأمان للخزن والحسابات البنكية للمستخدمين
Granular Zero-Trust Treasury Security & Governance Service
"""

import logging
from decimal import Decimal
from typing import List, Optional, Tuple, Union

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.treasury_access import TreasuryAccessAuditLog, UserTreasuryAccess
from financial.models.validation_audit_log import ValidationAuditLog

logger = logging.getLogger(__name__)


class TreasurySecurityService:
    """
    الخدمة المركزية لإدارة وتطبيق الحوكمة والسرية التامة على الخزن والبنوك للمستخدمين
    """

    CACHE_KEY_PREFIX = "payment_accounts_user_"
    CACHE_TIMEOUT = 600  # 10 دقائق مع إبطال فوري بالـ Signals

    @classmethod
    def get_cache_key(cls, user_id: int) -> str:
        return f"{cls.CACHE_KEY_PREFIX}{user_id}"

    @classmethod
    def invalidate_user_cache(cls, user_id: int) -> None:
        """إبطال الكاش المخصص للمستخدم فور أي تغيير في الصلاحيات"""
        if user_id:
            cache.delete(cls.get_cache_key(user_id))
            logger.debug(f"Invalidated treasury cache for user {user_id}")

    @classmethod
    def invalidate_all_users_cache(cls) -> None:
        """إبطال كاش حسابات الخزن لجميع المستخدمين عند تحديث أسعار الصرف أو التغييرات العامة"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user_ids = list(User.objects.values_list("id", flat=True))
            for uid in user_ids:
                cache.delete(cls.get_cache_key(uid))
            logger.info(f"Invalidated treasury cache for {len(user_ids)} users.")
        except Exception as e:
            logger.warning(f"Error invalidating all users treasury cache: {e}")

    @classmethod
    def get_user_accessible_treasuries(
        cls,
        user,
        action: str = "any",
        currency: Optional[Union[str, object]] = None,
        target_date=None,
    ) -> models.QuerySet:
        """
        الحصول على الحسابات النقدية والبنكية وأوراق القبض المصرح بها للمستخدم
        action: 'deposit' (إيداع/تحصيل), 'disburse' (صرف/سداد), 'any' (أي صلاحية)
        """
        if not user or not user.is_authenticated:
            return ChartOfAccounts.objects.none()

        today = target_date or timezone.now().date()

        # حسابات النقدية والبنوك النشطة والنهائية فقط
        base_qs = (
            ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
            .filter(
                Q(is_cash_account=True)
                | Q(is_bank_account=True)
                | Q(account_type__code__iexact="cash")
                | Q(account_type__code__iexact="bank")
                | Q(account_type__name__icontains="نقدي")
                | Q(account_type__name__icontains="صندوق")
                | Q(account_type__name__icontains="خزينة")
                | Q(account_type__name__icontains="بنك")
                | Q(account_type__name__icontains="مصرف")
                | Q(account_type__name__icontains="عهدة")
                | Q(code__startswith="1145")
                | Q(code__startswith="1051")
            )
            .select_related("currency", "account_type")
            .order_by("code")
        )

        if currency:
            if isinstance(currency, str):
                base_qs = base_qs.filter(Q(currency__code__iexact=currency) | Q(currency__symbol=currency))
            elif hasattr(currency, "id"):
                base_qs = base_qs.filter(currency=currency)

        # السوبر أدمن والمدير المالي ليهم وصول كامل لجميع الخزن
        if user.is_superuser:
            return base_qs

        # جلب الصلاحيات السارية للمستخدم
        access_filter = Q(user=user)
        validity_q = (
            (Q(valid_from__isnull=True) | Q(valid_from__lte=today))
            & (Q(valid_until__isnull=True) | Q(valid_until__gte=today))
        )
        access_filter &= validity_q

        if action == "deposit":
            access_filter &= Q(can_deposit=True)
        elif action == "disburse":
            access_filter &= Q(can_disburse=True)
        else:  # 'any'
            access_filter &= (Q(can_deposit=True) | Q(can_disburse=True))

        allowed_treasury_ids = UserTreasuryAccess.objects.filter(access_filter).values_list(
            "treasury_id", flat=True
        )

        return base_qs.filter(id__in=allowed_treasury_ids)

    @classmethod
    def get_user_deposit_treasuries(cls, user, currency=None, target_date=None) -> models.QuerySet:
        return cls.get_user_accessible_treasuries(user, action="deposit", currency=currency, target_date=target_date)

    @classmethod
    def get_user_disbursement_treasuries(cls, user, currency=None, target_date=None) -> models.QuerySet:
        return cls.get_user_accessible_treasuries(user, action="disburse", currency=currency, target_date=target_date)

    @classmethod
    def get_user_default_treasury(
        cls,
        user,
        currency=None,
        action: str = "deposit",
        target_date=None,
    ) -> Optional[ChartOfAccounts]:
        """الحصول على الخزينة الافتراضية للمستخدم للعملة المحددة"""
        if not user or not user.is_authenticated:
            return None

        today = target_date or timezone.now().date()
        validity_q = (
            (Q(valid_from__isnull=True) | Q(valid_from__lte=today))
            & (Q(valid_until__isnull=True) | Q(valid_until__gte=today))
        )

        perm_q = Q(can_deposit=True) if action == "deposit" else Q(can_disburse=True)

        # 1. البحث عن خزينة محددة كافتراضية
        access = (
            UserTreasuryAccess.objects.filter(
                user=user,
                is_default=True,
            )
            .filter(perm_q & validity_q)
            .select_related("treasury")
            .first()
        )

        if access and access.treasury:
            return access.treasury

        # 2. السقوط لأول خزينة مسموحة
        accessible = cls.get_user_accessible_treasuries(user, action=action, currency=currency, target_date=target_date)
        return accessible.first()

    @classmethod
    def can_user_deposit(cls, user, treasury_id: int, target_date=None) -> bool:
        """هل يملك المستخدم صلاحية الإيداع على الخزينة"""
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        today = target_date or timezone.now().date()
        return UserTreasuryAccess.objects.filter(
            user=user,
            treasury_id=treasury_id,
            can_deposit=True,
        ).filter(
            (Q(valid_from__isnull=True) | Q(valid_from__lte=today))
            & (Q(valid_until__isnull=True) | Q(valid_until__gte=today))
        ).exists()

    @classmethod
    def can_user_disburse(
        cls,
        user,
        treasury_id: int,
        amount: Optional[Decimal] = None,
        target_date=None,
    ) -> Tuple[bool, str]:
        """
        التحقق من صلاحية الصرف وسقف المبالغ (للحركة واليومي)
        يرجع (True, "") أو (False, "رسالة الخطأ")
        """
        if not user or not user.is_authenticated:
            return False, _("المستخدم غير مسجل أو غير مصرح له.")
        if user.is_superuser:
            return True, ""

        today = target_date or timezone.now().date()
        access = (
            UserTreasuryAccess.objects.filter(
                user=user,
                treasury_id=treasury_id,
                can_disburse=True,
            )
            .filter(
                (Q(valid_from__isnull=True) | Q(valid_from__lte=today))
                & (Q(valid_until__isnull=True) | Q(valid_until__gte=today))
            )
            .first()
        )

        if not access:
            return False, _("ليس لديك صلاحية صرف أو سداد من هذه الخزينة.")

        if amount is not None and amount > Decimal("0.00"):
            # 1. فحص الحد الأقصى للحركة الواحدة
            if (
                access.max_single_disbursement_limit
                and amount > access.max_single_disbursement_limit
            ):
                return False, _(
                    f"المبلغ المطلوب صرفه ({amount}) يتجاوز الحد الأقصى المسموح به للحركة الواحدة ({access.max_single_disbursement_limit})."
                )

            # 2. فحص الحد الأقصى اليومي التراكمي
            if access.daily_disbursement_limit:
                # حساب إجمالي الصرف اليومي الفعلي المسجل في القيود المرحلة
                from financial.models.journal_entry import JournalEntryLine

                today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

                today_spent = (
                    JournalEntryLine.objects.filter(
                        journal_entry__created_by=user,
                        journal_entry__status="posted",
                        journal_entry__date=today,
                        account_id=treasury_id,
                        credit__gt=Decimal("0.00"),
                    ).aggregate(total=Sum("credit"))["total"]
                    or Decimal("0.00")
                )

                if (today_spent + amount) > access.daily_disbursement_limit:
                    return False, _(
                        f"إجمالي المنصرف اليومي التراكمي سيصبح ({today_spent + amount}) مما يتجاوز السقف اليومي المصرح به ({access.daily_disbursement_limit})."
                    )

        return True, ""

    @classmethod
    def enforce_deposit(cls, user, treasury_id: int, request=None) -> None:
        """فرض التحقق الإلزامي من صلاحية الإيداع وإطلاق ValidationError وتسجيل التدقيق عند الفشل"""
        if not cls.can_user_deposit(user, treasury_id):
            ip = request.META.get("REMOTE_ADDR") if request else None
            try:
                if user and user.is_authenticated:
                    trsy_obj = ChartOfAccounts.objects.filter(id=treasury_id).first()
                    if trsy_obj:
                        TreasuryAccessAuditLog.objects.create(
                            user=user,
                            treasury=trsy_obj,
                            action="TAMPER_ATTEMPT",
                            notes="محاولة إيداع أو تحصيل في خزينة غير مصرح بها",
                            ip_address=ip,
                            performed_by=user,
                        )
            except Exception as ex:
                logger.warning(f"Could not log treasury audit attempt: {ex}")

            raise ValidationError(
                _("غير مصرح لك بإيداع أو تحصيل النقدية في هذا الحساب.")
            )

    @classmethod
    def enforce_disbursement(cls, user, treasury_id: int, amount: Optional[Decimal] = None, request=None) -> None:
        """فرض التحقق الإلزامي من صلاحية الصرف وحدود المبالغ"""
        can_disb, err_msg = cls.can_user_disburse(user, treasury_id, amount=amount)
        if not can_disb:
            ip = request.META.get("REMOTE_ADDR") if request else None
            try:
                if user and user.is_authenticated:
                    trsy_obj = ChartOfAccounts.objects.filter(id=treasury_id).first()
                    if trsy_obj:
                        TreasuryAccessAuditLog.objects.create(
                            user=user,
                            treasury=trsy_obj,
                            action="LIMIT_BREACH_ATTEMPT",
                            notes=f"محاولة صرف غير مصرح بها: {err_msg} (المبلغ: {amount})",
                            ip_address=ip,
                            performed_by=user,
                        )
            except Exception as ex:
                logger.warning(f"Could not log treasury audit attempt: {ex}")

            raise ValidationError(err_msg)

    @classmethod
    def get_user_visible_treasury_balances(cls, user) -> dict:
        """
        حساب إجمالي النقدية والسيولة الظاهرة للمستخدم فقط لاستخدامها في الداشبورد والإحصائيات
        """
        treasuries = cls.get_user_accessible_treasuries(user, action="any")
        if not treasuries.exists():
            return {
                "total_cash": Decimal("0.00"),
                "total_bank": Decimal("0.00"),
                "total_liquidity": Decimal("0.00"),
                "count": 0,
            }

        from financial.models.enhanced_balance import AccountBalanceCache

        account_ids = treasuries.values_list("id", flat=True)
        caches = AccountBalanceCache.objects.filter(account_id__in=account_ids)

        balance_map = {c.account_id: c.current_balance for c in caches}

        total_cash = Decimal("0.00")
        total_bank = Decimal("0.00")

        for trsy in treasuries:
            bal = balance_map.get(trsy.id, Decimal("0.00"))
            if getattr(trsy, "is_bank_account", False) or "بنك" in trsy.name:
                total_bank += bal
            else:
                total_cash += bal

        return {
            "total_cash": total_cash,
            "total_bank": total_bank,
            "total_liquidity": total_cash + total_bank,
            "count": treasuries.count(),
        }


# ربط الـ Signals لتفريغ الكاش المخصص للمستخدم تلقائياً عند أي تعديل
@receiver([post_save, post_delete], sender=UserTreasuryAccess)
def handle_user_treasury_access_change(sender, instance, **kwargs):
    if instance and instance.user_id:
        TreasurySecurityService.invalidate_user_cache(instance.user_id)
