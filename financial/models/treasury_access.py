"""
نموذج إسناد الخزن والحسابات البنكية للمستخدمين مع الرقابة والسرية التامة
Granular Zero-Trust Treasury & Bank Account User Access & Governance
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserTreasuryAccess(models.Model):
    """
    نموذج إسناد الخزينة / الحساب البنكي / أوراق القبض لمستخدم محدد
    يدعم الفصل التام بين صلاحية الإيداع (القبض) وصلاحية الصرف (السداد)
    مع الصلاحيات المؤقتة والأسقف المالية
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="treasury_accesses",
        verbose_name=_("المستخدم"),
    )
    treasury = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.CASCADE,
        related_name="user_accesses",
        verbose_name=_("الخزينة / الحساب البنكي"),
    )
    can_deposit = models.BooleanField(
        default=True,
        verbose_name=_("صلاحية الإيداع / التحصيل"),
        help_text=_("تتيح للمستخدم تحصيل وقبض النقدية وإيداعها في هذا الحساب"),
    )
    can_disburse = models.BooleanField(
        default=False,
        verbose_name=_("صلاحية الصرف / السداد"),
        help_text=_("تتيح للمستخدم سداد الفواتير والمصروفات وصرف النقدية من هذا الحساب"),
    )
    valid_from = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("ساري من تاريخ"),
        help_text=_("تاريخ بدء تفعيل الصلاحية للمستخدم (اختياري للورديات والإجازات)"),
    )
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("ساري حتى تاريخ"),
        help_text=_("تاريخ انتهاء الصلاحية تلقائياً (اختياري)"),
    )
    max_single_disbursement_limit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("الحد الأقصى للصرف للحركة الواحدة"),
        help_text=_("أقصى مبلغ مالي يمكن صرفه في عملية أو قيد واحد (اتركه فارغاً لبلا سقف)"),
    )
    daily_disbursement_limit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("الحد الأقصى للصرف اليومي التراكمي"),
        help_text=_("أقصى إجمالي مبالغ يمكن صرفها تراكمياً خلال اليوم الواحد"),
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("الخزينة الافتراضية للعملة"),
        help_text=_("تحديد هذا الحساب كخيار افتراضي عند قيام المستخدم بمعاملات بنفس عملة الحساب"),
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_treasury_accesses",
        verbose_name=_("تم الإسناد بواسطة"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("ملاحظات / سبب الإسناد"),
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("تاريخ الإنشاء"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("تاريخ آخر تحديث"),
    )

    class Meta:
        verbose_name = _("إسناد خزينة لمستخدم")
        verbose_name_plural = _("إسنادات الخزن للمستخدمين")
        unique_together = ("user", "treasury")
        indexes = [
            models.Index(fields=["user", "treasury"], name="idx_usr_trsy_acc"),
            models.Index(fields=["user", "can_deposit"], name="idx_usr_trsy_dep"),
            models.Index(fields=["user", "can_disburse"], name="idx_usr_trsy_disb"),
            models.Index(fields=["treasury", "is_default"], name="idx_trsy_is_def"),
            models.Index(fields=["valid_from", "valid_until"], name="idx_trsy_validity"),
        ]

    def clean(self):
        super().clean()
        if not self.can_deposit and not self.can_disburse:
            raise ValidationError(
                _("يجب منح المستخدم صلاحية واحدة على الأقل (إيداع أو صرف) للخزينة المحددة.")
            )

        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError(
                _("تاريخ بدء الصلاحية لا يمكن أن يكون لاحقاً لتاريخ الانتهاء.")
            )

        if (
            self.max_single_disbursement_limit
            and self.daily_disbursement_limit
            and self.max_single_disbursement_limit > self.daily_disbursement_limit
        ):
            raise ValidationError(
                _("حد الصرف للحركة الواحدة لا يمكن أن يتجاوز الحد اليومي التراكمي.")
            )

    def is_currently_valid(self, target_date=None) -> bool:
        """التحقق من سريان الصلاحية الزمنية للمستخدم"""
        check_date = target_date or timezone.now().date()
        if self.valid_from and check_date < self.valid_from:
            return False
        if self.valid_until and check_date > self.valid_until:
            return False
        return True

    def has_deposit_permission(self, target_date=None) -> bool:
        """هل يملك المستخدم صلاحية الإيداع السارية حالياً"""
        return self.can_deposit and self.is_currently_valid(target_date)

    def has_disburse_permission(self, target_date=None) -> bool:
        """هل يملك المستخدم صلاحية الصرف السارية حالياً"""
        return self.can_disburse and self.is_currently_valid(target_date)

    def __str__(self):
        permissions = []
        if self.can_deposit:
            permissions.append(_("إيداع"))
        if self.can_disburse:
            permissions.append(_("صرف"))
        perm_str = " + ".join(str(p) for p in permissions)
        return f"{self.user} -> {self.treasury.name} ({perm_str})"


class TreasuryAccessAuditLog(models.Model):
    """
    سجل تدقيق ورقابة العمليات والتعديلات على صلاحيات وإسناد الخزن
    وتوثيق محاضر التسليم والتسلم ورصد أي انتهاكات أمنية
    """

    ACTION_CHOICES = [
        ("ASSIGNED", _("إسناد جديد")),
        ("UPDATED", _("تعديل صلاحيات")),
        ("REVOKED", _("إلغاء إسناد")),
        ("LIMIT_BREACH_ATTEMPT", _("محاولة تجاوز سقف مالي")),
        ("TAMPER_ATTEMPT", _("محاولة وصول غير مصرح")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="treasury_audit_logs",
        verbose_name=_("المستخدم المعني"),
    )
    treasury = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.CASCADE,
        related_name="treasury_access_audit_logs",
        verbose_name=_("الخزينة"),
    )
    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        verbose_name=_("نوع الإجراء"),
    )
    old_permissions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("الصلاحيات السابقة"),
    )
    new_permissions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("الصلاحيات الجديدة"),
    )
    book_balance_at_change = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("الرصيد الدفتري لحظة التغيير"),
        help_text=_("توثيق الرصيد الدفتري لإخلاء الطرف ومحاضر التسليم والتسلم"),
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_treasury_audits",
        verbose_name=_("القائم بالإجراء"),
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("عنوان IP"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("ملاحظات"),
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("تاريخ ووقت التدقيق"),
    )

    class Meta:
        verbose_name = _("سجل تدقيق إسناد الخزن")
        verbose_name_plural = _("سجلات تدقيق إسناد الخزن")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "treasury"], name="idx_aud_usr_trsy"),
            models.Index(fields=["action", "created_at"], name="idx_aud_act_date"),
        ]

    def __str__(self):
        return f"[{self.get_action_display()}] {self.user} - {self.treasury} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
