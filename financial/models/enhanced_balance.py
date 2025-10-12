"""
نظام الأرصدة المحسن - حل مشكلة تضارب الأرصدة
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from django.utils import timezone
from decimal import Decimal
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BalanceSnapshot(models.Model):
    """
    لقطات الأرصدة لتحسين الأداء
    """

    account = models.ForeignKey(
        "ChartOfAccounts",
        on_delete=models.CASCADE,
        verbose_name=_("الحساب"),
        related_name="balance_snapshots",
    )

    snapshot_date = models.DateField(_("تاريخ اللقطة"))
    balance = models.DecimalField(_("الرصيد"), max_digits=15, decimal_places=2)

    # معلومات اللقطة
    transactions_count = models.PositiveIntegerField(_("عدد المعاملات"), default=0)
    last_transaction_id = models.PositiveIntegerField(
        _("آخر معاملة"), null=True, blank=True
    )

    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by_system = models.BooleanField(_("أنشئ بواسطة النظام"), default=True)

    class Meta:
        verbose_name = _("لقطة رصيد")
        verbose_name_plural = _("لقطات الأرصدة")
        unique_together = ["account", "snapshot_date"]
        ordering = ["-snapshot_date"]
        indexes = [
            models.Index(fields=["account", "snapshot_date"]),
            models.Index(fields=["snapshot_date"]),
        ]

    def __str__(self):
        return f"{self.account.code} - {self.snapshot_date} - {self.balance}"


class AccountBalanceCache(models.Model):
    """
    كاش الأرصدة للوصول السريع
    """

    account = models.OneToOneField(
        "ChartOfAccounts",
        on_delete=models.CASCADE,
        verbose_name=_("الحساب"),
        related_name="balance_cache",
    )

    # الأرصدة المختلفة
    current_balance = models.DecimalField(
        _("الرصيد الحالي"), max_digits=15, decimal_places=2, default=0
    )
    available_balance = models.DecimalField(
        _("الرصيد المتاح"), max_digits=15, decimal_places=2, default=0
    )
    pending_balance = models.DecimalField(
        _("الرصيد المعلق"), max_digits=15, decimal_places=2, default=0
    )

    # معلومات آخر تحديث
    last_updated = models.DateTimeField(_("آخر تحديث"), auto_now=True)
    last_transaction_id = models.PositiveIntegerField(
        _("آخر معاملة"), null=True, blank=True
    )

    # إحصائيات
    total_debits = models.DecimalField(
        _("إجمالي المدين"), max_digits=15, decimal_places=2, default=0
    )
    total_credits = models.DecimalField(
        _("إجمالي الدائن"), max_digits=15, decimal_places=2, default=0
    )
    transactions_count = models.PositiveIntegerField(_("عدد المعاملات"), default=0)

    # حالة الكاش
    is_valid = models.BooleanField(_("صالح"), default=True)
    needs_refresh = models.BooleanField(_("يحتاج تحديث"), default=False)

    class Meta:
        verbose_name = _("كاش رصيد الحساب")
        verbose_name_plural = _("كاش أرصدة الحسابات")
        indexes = [
            models.Index(fields=["last_updated"]),
            models.Index(fields=["is_valid", "needs_refresh"]),
        ]

    def __str__(self):
        return f"{self.account.code} - {self.current_balance}"

    def refresh_balance(self, force: bool = False) -> bool:
        """
        تحديث الرصيد من القيود المحاسبية
        """
        if not force and self.is_valid and not self.needs_refresh:
            return True

        try:
            from ..services.enhanced_balance_service import EnhancedBalanceService

            # حساب الرصيد الجديد
            balance_info = EnhancedBalanceService.calculate_account_balance_detailed(
                self.account
            )

            # تحديث البيانات
            self.current_balance = balance_info["balance"]
            self.total_debits = balance_info["total_debits"]
            self.total_credits = balance_info["total_credits"]
            self.transactions_count = balance_info["transactions_count"]
            self.last_transaction_id = balance_info["last_transaction_id"]

            # تحديث الحالة
            self.is_valid = True
            self.needs_refresh = False

            self.save()

            logger.info(f"تم تحديث كاش الرصيد للحساب {self.account.code}")
            return True

        except Exception as e:
            logger.error(
                f"خطأ في تحديث كاش الرصيد للحساب {self.account.code}: {str(e)}"
            )
            self.is_valid = False
            self.save()
            return False

    def invalidate(self):
        """
        إبطال الكاش
        """
        self.is_valid = False
        self.needs_refresh = True
        self.save()

    @classmethod
    def invalidate_account(cls, account):
        """
        إبطال كاش حساب معين
        """
        try:
            cache_obj = cls.objects.get(account=account)
            cache_obj.invalidate()
        except cls.DoesNotExist:
            # إنشاء كاش جديد
            cls.objects.create(account=account, needs_refresh=True)


class BalanceAuditLog(models.Model):
    """
    سجل مراجعة الأرصدة
    """

    ACTION_CHOICES = (
        ("calculate", _("حساب")),
        ("update", _("تحديث")),
        ("invalidate", _("إبطال")),
        ("refresh", _("تحديث")),
        ("snapshot", _("لقطة")),
    )

    account = models.ForeignKey(
        "ChartOfAccounts",
        on_delete=models.CASCADE,
        verbose_name=_("الحساب"),
        related_name="balance_audit_logs",
    )

    action = models.CharField(_("الإجراء"), max_length=20, choices=ACTION_CHOICES)
    old_balance = models.DecimalField(
        _("الرصيد القديم"), max_digits=15, decimal_places=2, null=True, blank=True
    )
    new_balance = models.DecimalField(
        _("الرصيد الجديد"), max_digits=15, decimal_places=2
    )

    # معلومات السياق
    transaction_id = models.PositiveIntegerField(
        _("معرف المعاملة"), null=True, blank=True
    )
    journal_entry_id = models.PositiveIntegerField(
        _("معرف القيد"), null=True, blank=True
    )

    # معلومات التتبع
    timestamp = models.DateTimeField(_("الوقت"), auto_now_add=True)
    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("المستخدم"),
    )

    # معلومات إضافية
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    system_generated = models.BooleanField(_("مولد بواسطة النظام"), default=True)

    class Meta:
        verbose_name = _("سجل مراجعة الرصيد")
        verbose_name_plural = _("سجلات مراجعة الأرصدة")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["account", "timestamp"]),
            models.Index(fields=["action", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.account.code} - {self.action} - {self.new_balance}"

    @classmethod
    def log_balance_change(
        cls,
        account,
        action: str,
        old_balance: Optional[Decimal] = None,
        new_balance: Decimal = Decimal("0"),
        **kwargs,
    ):
        """
        تسجيل تغيير في الرصيد
        """
        try:
            cls.objects.create(
                account=account,
                action=action,
                old_balance=old_balance,
                new_balance=new_balance,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"خطأ في تسجيل تغيير الرصيد: {str(e)}")


class BalanceReconciliation(models.Model):
    """
    تسوية الأرصدة
    """

    STATUS_CHOICES = (
        ("pending", _("قيد المراجعة")),
        ("reconciled", _("مسوى")),
        ("discrepancy", _("يوجد فرق")),
    )

    account = models.ForeignKey(
        "ChartOfAccounts",
        on_delete=models.CASCADE,
        verbose_name=_("الحساب"),
        related_name="reconciliations",
    )

    reconciliation_date = models.DateField(_("تاريخ التسوية"))

    # الأرصدة المختلفة
    system_balance = models.DecimalField(
        _("رصيد النظام"), max_digits=15, decimal_places=2
    )
    calculated_balance = models.DecimalField(
        _("الرصيد المحسوب"), max_digits=15, decimal_places=2
    )
    external_balance = models.DecimalField(
        _("الرصيد الخارجي"), max_digits=15, decimal_places=2, null=True, blank=True
    )

    # الفروقات
    system_difference = models.DecimalField(
        _("فرق النظام"), max_digits=15, decimal_places=2, default=0
    )
    external_difference = models.DecimalField(
        _("فرق خارجي"), max_digits=15, decimal_places=2, null=True, blank=True
    )

    # الحالة
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="pending"
    )

    # معلومات إضافية
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    reconciled_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("سوى بواسطة"),
    )

    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("تسوية رصيد")
        verbose_name_plural = _("تسويات الأرصدة")
        unique_together = ["account", "reconciliation_date"]
        ordering = ["-reconciliation_date"]
        indexes = [
            models.Index(fields=["account", "reconciliation_date"]),
            models.Index(fields=["status", "reconciliation_date"]),
        ]

    def __str__(self):
        return f"{self.account.code} - {self.reconciliation_date} - {self.status}"

    def calculate_differences(self):
        """
        حساب الفروقات
        """
        self.system_difference = self.calculated_balance - self.system_balance

        if self.external_balance is not None:
            self.external_difference = self.external_balance - self.calculated_balance

        # تحديد الحالة
        if abs(self.system_difference) < Decimal("0.01"):
            if self.external_balance is None or abs(self.external_difference) < Decimal(
                "0.01"
            ):
                self.status = "reconciled"
            else:
                self.status = "discrepancy"
        else:
            self.status = "discrepancy"

        self.save()

    def resolve_discrepancy(self, user, notes: str = None):
        """
        حل الفروقات
        """
        if self.status != "discrepancy":
            return False

        # يمكن إضافة منطق حل الفروقات هنا
        # مثل إنشاء قيود تسوية

        self.status = "reconciled"
        self.reconciled_by = user
        if notes:
            self.notes = (self.notes or "") + f"\nتم الحل: {notes}"

        self.save()
        return True
