"""
نماذج تزامن المدفوعات وتتبع حالة العمليات المالية
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import uuid
import json

# استخدام settings.AUTH_USER_MODEL مباشرة في ForeignKey


class PaymentSyncOperation(models.Model):
    """
    تتبع عمليات تزامن المدفوعات
    """

    STATUS_CHOICES = (
        ("pending", _("قيد الانتظار")),
        ("processing", _("قيد المعالجة")),
        ("completed", _("مكتملة")),
        ("failed", _("فاشلة")),
        ("rolled_back", _("تم التراجع")),
        ("retry", _("إعادة المحاولة")),
    )

    OPERATION_TYPES = (
        ("create_payment", _("إنشاء دفعة")),
        ("update_payment", _("تحديث دفعة")),
        ("delete_payment", _("حذف دفعة")),
        ("sync_payment", _("مزامنة دفعة")),
        ("rollback_payment", _("التراجع عن دفعة")),
    )

    # معرف فريد للعملية
    operation_id = models.UUIDField(_("معرف العملية"), default=uuid.uuid4, unique=True)

    # نوع العملية وحالتها
    operation_type = models.CharField(
        _("نوع العملية"), max_length=20, choices=OPERATION_TYPES
    )
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="pending"
    )

    # الكائن المرتبط (SalePayment أو PurchasePayment)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, verbose_name=_("نوع الكائن")
    )
    object_id = models.PositiveIntegerField(_("معرف الكائن"))
    content_object = GenericForeignKey("content_type", "object_id")

    # بيانات العملية
    payment_data = models.JSONField(_("بيانات الدفعة"), default=dict)
    sync_targets = models.JSONField(
        _("أهداف المزامنة"), default=list
    )  # قائمة بالجداول المطلوب المزامنة معها

    # معلومات التنفيذ
    started_at = models.DateTimeField(_("بدء التنفيذ"), null=True, blank=True)
    completed_at = models.DateTimeField(_("انتهاء التنفيذ"), null=True, blank=True)
    retry_count = models.PositiveIntegerField(_("عدد المحاولات"), default=0)
    max_retries = models.PositiveIntegerField(_("الحد الأقصى للمحاولات"), default=3)

    # معلومات الخطأ
    error_message = models.TextField(_("رسالة الخطأ"), blank=True, null=True)
    error_details = models.JSONField(_("تفاصيل الخطأ"), default=dict)

    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="payment_sync_operations",
    )

    class Meta:
        verbose_name = _("عملية تزامن دفعة")
        verbose_name_plural = _("عمليات تزامن المدفوعات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["operation_id"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.operation_type} - {self.operation_id} - {self.status}"

    def start_processing(self):
        """بدء معالجة العملية"""
        self.status = "processing"
        self.started_at = timezone.now()
        self.save()

    def mark_completed(self):
        """تحديد العملية كمكتملة"""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.save()

    def mark_failed(self, error_message: str, error_details: dict = None):
        """تحديد العملية كفاشلة"""
        self.status = "failed"
        self.error_message = error_message
        self.error_details = error_details or {}
        self.completed_at = timezone.now()
        self.save()

    def increment_retry(self):
        """زيادة عدد المحاولات"""
        self.retry_count += 1
        if self.retry_count >= self.max_retries:
            self.status = "failed"
        else:
            self.status = "retry"
        self.save()

    def can_retry(self) -> bool:
        """التحقق من إمكانية إعادة المحاولة"""
        return self.retry_count < self.max_retries and self.status in [
            "failed",
            "retry",
        ]


class PaymentSyncLog(models.Model):
    """
    سجل تفصيلي لعمليات تزامن المدفوعات
    """

    ACTION_CHOICES = (
        ("create_customer_payment", _("إنشاء دفعة عميل")),
        ("create_supplier_payment", _("إنشاء دفعة مورد")),
        ("update_customer_payment", _("تحديث دفعة عميل")),
        ("update_supplier_payment", _("تحديث دفعة مورد")),
        ("delete_customer_payment", _("حذف دفعة عميل")),
        ("delete_supplier_payment", _("حذف دفعة مورد")),
        ("create_journal_entry", _("إنشاء قيد محاسبي")),
        ("update_balance_cache", _("تحديث كاش الرصيد")),
        ("rollback_operation", _("التراجع عن العملية")),
    )

    sync_operation = models.ForeignKey(
        PaymentSyncOperation,
        on_delete=models.CASCADE,
        verbose_name=_("عملية التزامن"),
        related_name="logs",
    )

    action = models.CharField(_("الإجراء"), max_length=30, choices=ACTION_CHOICES)
    target_model = models.CharField(_("النموذج المستهدف"), max_length=50)
    target_id = models.PositiveIntegerField(_("معرف الهدف"), null=True, blank=True)

    # بيانات الإجراء
    action_data = models.JSONField(_("بيانات الإجراء"), default=dict)
    result_data = models.JSONField(_("نتيجة الإجراء"), default=dict)

    # حالة الإجراء
    success = models.BooleanField(_("نجح"), default=True)
    error_message = models.TextField(_("رسالة الخطأ"), blank=True, null=True)

    # معلومات التوقيت
    executed_at = models.DateTimeField(_("وقت التنفيذ"), auto_now_add=True)
    execution_time = models.FloatField(_("وقت التنفيذ (ثانية)"), null=True, blank=True)

    class Meta:
        verbose_name = _("سجل تزامن دفعة")
        verbose_name_plural = _("سجلات تزامن المدفوعات")
        ordering = ["-executed_at"]
        indexes = [
            models.Index(fields=["sync_operation", "executed_at"]),
            models.Index(fields=["action", "success"]),
        ]

    def __str__(self):
        return (
            f"{self.action} - {self.target_model} - {'نجح' if self.success else 'فشل'}"
        )


class PaymentSyncRule(models.Model):
    """
    قواعد تزامن المدفوعات
    """

    TRIGGER_CHOICES = (
        ("on_create", _("عند الإنشاء")),
        ("on_update", _("عند التحديث")),
        ("on_delete", _("عند الحذف")),
        ("on_status_change", _("عند تغيير الحالة")),
    )

    SOURCE_CHOICES = (
        ("sale_payment", _("دفعة مبيعات")),
        ("purchase_payment", _("دفعة مشتريات")),
        ("customer_payment", _("دفعة عميل")),
        ("supplier_payment", _("دفعة مورد")),
    )

    name = models.CharField(_("اسم القاعدة"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True, null=True)

    # مصدر التزامن
    source_model = models.CharField(
        _("النموذج المصدر"), max_length=20, choices=SOURCE_CHOICES
    )
    trigger_event = models.CharField(
        _("حدث التشغيل"), max_length=20, choices=TRIGGER_CHOICES
    )

    # أهداف التزامن
    sync_to_customer_payment = models.BooleanField(
        _("مزامنة مع دفعات العملاء"), default=False
    )
    sync_to_supplier_payment = models.BooleanField(
        _("مزامنة مع دفعات الموردين"), default=False
    )
    sync_to_journal_entry = models.BooleanField(
        _("مزامنة مع القيود المحاسبية"), default=False
    )
    sync_to_balance_cache = models.BooleanField(
        _("مزامنة مع كاش الأرصدة"), default=False
    )

    # شروط التزامن
    conditions = models.JSONField(_("شروط التزامن"), default=dict)
    mapping_rules = models.JSONField(_("قواعد الربط"), default=dict)

    # حالة القاعدة
    is_active = models.BooleanField(_("نشطة"), default=True)
    priority = models.PositiveIntegerField(_("الأولوية"), default=1)

    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="payment_sync_rules",
    )

    class Meta:
        verbose_name = _("قاعدة تزامن دفعة")
        verbose_name_plural = _("قواعد تزامن المدفوعات")
        ordering = ["priority", "name"]
        indexes = [
            models.Index(fields=["source_model", "trigger_event"]),
            models.Index(fields=["is_active", "priority"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.source_model} - {self.trigger_event}"

    def matches_conditions(self, payment_obj, event_data: dict = None) -> bool:
        """التحقق من تطابق الشروط"""
        if not self.conditions:
            return True

        # تطبيق الشروط المخصصة
        for condition_key, condition_value in self.conditions.items():
            if hasattr(payment_obj, condition_key):
                obj_value = getattr(payment_obj, condition_key)
                if obj_value != condition_value:
                    return False

        return True

    def get_sync_targets(self) -> list:
        """الحصول على قائمة أهداف التزامن"""
        targets = []

        if self.sync_to_customer_payment:
            targets.append("customer_payment")
        if self.sync_to_supplier_payment:
            targets.append("supplier_payment")
        if self.sync_to_journal_entry:
            targets.append("journal_entry")
        if self.sync_to_balance_cache:
            targets.append("balance_cache")

        return targets


class PaymentSyncError(models.Model):
    """
    أخطاء تزامن المدفوعات
    """

    ERROR_TYPES = (
        ("validation_error", _("خطأ في التحقق")),
        ("database_error", _("خطأ في قاعدة البيانات")),
        ("network_error", _("خطأ في الشبكة")),
        ("permission_error", _("خطأ في الصلاحيات")),
        ("business_logic_error", _("خطأ في منطق العمل")),
        ("system_error", _("خطأ في النظام")),
    )

    sync_operation = models.ForeignKey(
        PaymentSyncOperation,
        on_delete=models.CASCADE,
        verbose_name=_("عملية التزامن"),
        related_name="errors",
    )

    error_type = models.CharField(_("نوع الخطأ"), max_length=20, choices=ERROR_TYPES)
    error_code = models.CharField(_("كود الخطأ"), max_length=20, blank=True, null=True)
    error_message = models.TextField(_("رسالة الخطأ"))

    # تفاصيل الخطأ
    stack_trace = models.TextField(_("تتبع المكدس"), blank=True, null=True)
    context_data = models.JSONField(_("بيانات السياق"), default=dict)

    # معلومات الإصلاح
    is_resolved = models.BooleanField(_("تم الحل"), default=False)
    resolution_notes = models.TextField(_("ملاحظات الحل"), blank=True, null=True)
    resolved_at = models.DateTimeField(_("تاريخ الحل"), null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("حل بواسطة"),
        related_name="resolved_sync_errors",
    )

    # معلومات التتبع
    occurred_at = models.DateTimeField(_("وقت الحدوث"), auto_now_add=True)

    class Meta:
        verbose_name = _("خطأ تزامن دفعة")
        verbose_name_plural = _("أخطاء تزامن المدفوعات")
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["sync_operation", "occurred_at"]),
            models.Index(fields=["error_type", "is_resolved"]),
        ]

    def __str__(self):
        return f"{self.error_type} - {self.error_message[:50]}"

    def mark_resolved(self, user=None, notes: str = None):
        """تحديد الخطأ كمحلول"""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.resolution_notes = notes
        self.save()
