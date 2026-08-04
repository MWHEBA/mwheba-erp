from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

User = get_user_model()


class EnterpriseApprovalRule(models.Model):
    """
    FIN-CORE-017: Enterprise Approval Rule Model
    قواعد الاعتمادات الموحدة عبر أوامر الشراء والبيع والائتمان
    """
    MODULE_CHOICES = (
        ("PURCHASE", _("المشتريات")),
        ("SALES", _("المبيعات")),
        ("CREDIT", _("حدود الائتمان")),
        ("PAYMENT", _("المدفوعات")),
        ("EXPENSE", _("المصروفات")),
    )

    module = models.CharField(_("الموديول"), max_length=20, choices=MODULE_CHOICES, default="SALES")
    rule_name = models.CharField(_("اسم القاعدة"), max_length=100)
    min_amount = models.DecimalField(_("الحد الأدنى للقيمة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    max_amount = models.DecimalField(_("الحد الأقصى للقيمة"), max_digits=15, decimal_places=2, default=Decimal("999999999.00"))
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    approver_role = models.CharField(_("دور المعتمد (مثال: MANAGER, CTO)"), max_length=50)
    approval_level = models.IntegerField(_("مستوى الاعتماد"), default=1)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("قاعدة اعتماد مؤسسية")
        verbose_name_plural = _("قواعد الاعتماد المؤسسية")

    def __str__(self):
        return f"[{self.module}] {self.rule_name} (Level {self.approval_level} - Role: {self.approver_role})"


class EnterpriseApprovalRequest(models.Model):
    """
    FIN-CORE-017: Enterprise Approval Request Log
    سجل طلبات الاعتمادات للمستندات المعلقة
    """
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("PENDING", _("معلق")),
        ("APPROVED", _("معتمد")),
        ("REJECTED", _("مرفوض")),
        ("CANCELLED", _("ملغى")),
    )

    module = models.CharField(_("الموديول"), max_length=20, choices=EnterpriseApprovalRule.MODULE_CHOICES)
    reference_id = models.CharField(_("رقم مرجع المستند (SO/PO/Cust ID)"), max_length=100)
    rule = models.ForeignKey(EnterpriseApprovalRule, on_delete=models.PROTECT, related_name="requests")
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approval_requests_submitted", verbose_name=_("طالب الاعتماد"))
    status = models.CharField(_("حالة الطلب"), max_length=20, choices=STATUS_CHOICES, default="PENDING")
    comments = models.TextField(_("ملاحظات / سبب القرار"), blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approval_requests_approved", verbose_name=_("المعتمد النهائي"))
    approved_at = models.DateTimeField(_("تاريخ القرار النهائي"), null=True, blank=True)
    created_at = models.DateTimeField(_("تاريخ تقديم الطلب"), auto_now_add=True)

    class Meta:
        verbose_name = _("طلب اعتماد مؤسسي")
        verbose_name_plural = _("طلبات الاعتماد المؤسسية")
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.module}] Ref: {self.reference_id} - {self.status}"


class EnterpriseApprovalStep(models.Model):
    """
    FIN-CORE-017: Enterprise Multi-Level Approval Step Model
    خطوات الاعتماد متعددة المستويات لكل طلب
    """
    STATUS_CHOICES = (
        ("PENDING", _("معلق")),
        ("APPROVED", _("معتمد")),
        ("REJECTED", _("مرفوض")),
    )

    approval_request = models.ForeignKey(EnterpriseApprovalRequest, on_delete=models.CASCADE, related_name="steps", verbose_name=_("طلب الاعتماد"))
    sequence = models.IntegerField(_("ترتيب الخطوة"), default=1)
    approver_role = models.CharField(_("دور المعتمد"), max_length=50)
    status = models.CharField(_("حالة الخطوة"), max_length=20, choices=STATUS_CHOICES, default="PENDING")
    action_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("منفذ الإجراء"))
    action_at = models.DateTimeField(_("تاريخ الإجراء"), null=True, blank=True)
    comments = models.TextField(_("ملاحظات"), blank=True)

    class Meta:
        verbose_name = _("خطوة اعتماد مؤسسية")
        verbose_name_plural = _("خطوات الاعتماد المؤسسية")
        ordering = ["sequence"]

    def __str__(self):
        return f"Step {self.sequence} [{self.approver_role}] for Req #{self.approval_request.id} - {self.status}"


class EnterpriseApprovalAuditLog(models.Model):
    """
    FIN-CORE-017: Enterprise Approval Audit Trail Log
    سجل تدقيق محدد لكل إجراء تغيير في حالات طلبات وخطوات الاعتماد
    """
    approval_request = models.ForeignKey(EnterpriseApprovalRequest, on_delete=models.CASCADE, related_name="audit_logs", verbose_name=_("طلب الاعتماد"))
    old_status = models.CharField(_("الحالة السابقة"), max_length=20)
    new_status = models.CharField(_("الحالة الجديدة"), max_length=20)
    action_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قام بالإجراء"))
    comments = models.TextField(_("ملاحظات / السبب"), blank=True)
    timestamp = models.DateTimeField(_("الوقت والتاريخ"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تدقيق الاعتماد")
        verbose_name_plural = _("سجلات تدقيق الاعتمادات")
        ordering = ["-timestamp"]

    def __str__(self):
        return f"Audit: Req #{self.approval_request.id} ({self.old_status} -> {self.new_status})"
