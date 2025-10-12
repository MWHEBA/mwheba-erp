"""
نظام Audit Trail لتسجيل جميع التغييرات على الدفعات والقيود المحاسبية
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
import json


class AuditTrail(models.Model):
    """
    نموذج تسجيل التغييرات (Audit Trail)
    يسجل جميع العمليات المهمة على الدفعات والقيود المحاسبية
    """

    ACTION_CHOICES = (
        ("create", _("إنشاء")),
        ("update", _("تحديث")),
        ("delete", _("حذف")),
        ("post", _("ترحيل")),
        ("unpost", _("إلغاء ترحيل")),
        ("sync", _("ربط مالي")),
        ("unsync", _("إلغاء ربط مالي")),
        ("approve", _("اعتماد")),
        ("reject", _("رفض")),
        ("cancel", _("إلغاء")),
    )

    ENTITY_TYPES = (
        ("sale_payment", _("دفعة مبيعات")),
        ("purchase_payment", _("دفعة مشتريات")),
        ("journal_entry", _("قيد محاسبي")),
        ("cash_movement", _("حركة خزن")),
        ("sale", _("فاتورة مبيعات")),
        ("purchase", _("فاتورة مشتريات")),
    )

    # معلومات العملية
    action = models.CharField(_("العملية"), max_length=20, choices=ACTION_CHOICES)
    entity_type = models.CharField(_("نوع الكيان"), max_length=30, choices=ENTITY_TYPES)
    entity_id = models.PositiveIntegerField(_("معرف الكيان"))
    entity_name = models.CharField(_("اسم الكيان"), max_length=200, blank=True)

    # ربط عام بأي نموذج
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # معلومات المستخدم والوقت
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("المستخدم"),
    )
    timestamp = models.DateTimeField(_("وقت العملية"), default=timezone.now)
    ip_address = models.GenericIPAddressField(_("عنوان IP"), null=True, blank=True)
    user_agent = models.TextField(_("متصفح المستخدم"), blank=True)

    # تفاصيل التغيير
    description = models.TextField(_("وصف العملية"))
    reason = models.TextField(_("سبب العملية"), blank=True)

    # البيانات القديمة والجديدة (JSON)
    old_values = models.JSONField(_("القيم القديمة"), null=True, blank=True)
    new_values = models.JSONField(_("القيم الجديدة"), null=True, blank=True)
    changes = models.JSONField(_("التغييرات"), null=True, blank=True)

    # معلومات إضافية
    metadata = models.JSONField(_("معلومات إضافية"), null=True, blank=True)

    # حالة العملية
    STATUS_CHOICES = (
        ("success", _("نجحت")),
        ("failed", _("فشلت")),
        ("pending", _("معلقة")),
        ("cancelled", _("ملغية")),
    )
    status = models.CharField(
        _("حالة العملية"), max_length=20, choices=STATUS_CHOICES, default="success"
    )
    error_message = models.TextField(_("رسالة الخطأ"), blank=True)

    class Meta:
        verbose_name = _("سجل التدقيق")
        verbose_name_plural = _("سجلات التدقيق")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["action", "timestamp"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.get_entity_type_display()} #{self.entity_id} - {self.user} - {self.timestamp}"

    @property
    def has_changes(self):
        """هل توجد تغييرات مسجلة"""
        return bool(self.changes)

    @property
    def changes_count(self):
        """عدد الحقول المتغيرة"""
        return len(self.changes) if self.changes else 0

    def get_change_summary(self):
        """ملخص التغييرات"""
        if not self.changes:
            return "لا توجد تغييرات"

        summary = []
        for field, change in self.changes.items():
            old_val = change.get("old", "غير محدد")
            new_val = change.get("new", "غير محدد")
            summary.append(f"{field}: {old_val} ← {new_val}")

        return " | ".join(summary)

    @classmethod
    def log_action(
        cls,
        action: str,
        entity_type: str,
        entity_id: int,
        user,
        description: str,
        entity_name: str = "",
        old_values: dict = None,
        new_values: dict = None,
        reason: str = "",
        metadata: dict = None,
        request=None,
        content_object=None,
    ):
        """
        تسجيل عملية جديدة في سجل التدقيق

        Args:
            action: نوع العملية
            entity_type: نوع الكيان
            entity_id: معرف الكيان
            user: المستخدم
            description: وصف العملية
            entity_name: اسم الكيان (اختياري)
            old_values: القيم القديمة
            new_values: القيم الجديدة
            reason: سبب العملية
            metadata: معلومات إضافية
            request: طلب HTTP (لاستخراج IP والمتصفح)
            content_object: الكائن المرتبط
        """

        # حساب التغييرات
        changes = {}
        if old_values and new_values:
            for key, new_value in new_values.items():
                old_value = old_values.get(key)
                if old_value != new_value:
                    changes[key] = {"old": old_value, "new": new_value}

        # استخراج معلومات الطلب
        ip_address = None
        user_agent = ""
        if request:
            ip_address = cls._get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]  # تحديد الطول

        # إنشاء السجل
        audit_entry = cls.objects.create(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            user=user,
            description=description,
            reason=reason,
            old_values=old_values,
            new_values=new_values,
            changes=changes,
            metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
            content_object=content_object,
        )

        return audit_entry

    @staticmethod
    def _get_client_ip(request):
        """استخراج عنوان IP الحقيقي للعميل"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    @classmethod
    def get_entity_history(cls, entity_type: str, entity_id: int):
        """الحصول على تاريخ كيان معين"""
        return cls.objects.filter(
            entity_type=entity_type, entity_id=entity_id
        ).order_by("-timestamp")

    @classmethod
    def get_user_activity(cls, user, days: int = 30):
        """الحصول على نشاط مستخدم معين"""
        from datetime import timedelta

        since = timezone.now() - timedelta(days=days)

        return cls.objects.filter(user=user, timestamp__gte=since).order_by(
            "-timestamp"
        )

    @classmethod
    def get_recent_activity(cls, hours: int = 24):
        """الحصول على النشاط الأخير"""
        from datetime import timedelta

        since = timezone.now() - timedelta(hours=hours)

        return cls.objects.filter(timestamp__gte=since).order_by("-timestamp")


class PaymentAuditMixin:
    """
    Mixin لإضافة وظائف التدقيق للدفعات
    """

    def log_payment_action(
        self,
        action: str,
        user,
        description: str,
        reason: str = "",
        request=None,
        **kwargs,
    ):
        """تسجيل عملية على الدفعة"""

        # تحديد نوع الكيان
        if hasattr(self, "sale"):
            entity_type = "sale_payment"
            entity_name = f"دفعة مبيعات - فاتورة {self.sale.number}"
        elif hasattr(self, "purchase"):
            entity_type = "purchase_payment"
            entity_name = f"دفعة مشتريات - فاتورة {self.purchase.number}"
        else:
            entity_type = "payment"
            entity_name = f"دفعة #{self.id}"

        # معلومات إضافية
        metadata = {
            "payment_id": self.id,
            "amount": float(self.amount),
            "payment_method": self.payment_method,
            "financial_status": self.financial_status,
            "status": self.status,
            **kwargs,
        }

        return AuditTrail.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=self.id,
            entity_name=entity_name,
            user=user,
            description=description,
            reason=reason,
            metadata=metadata,
            request=request,
            content_object=self,
        )

    def get_audit_history(self):
        """الحصول على تاريخ التدقيق للدفعة"""
        entity_type = "sale_payment" if hasattr(self, "sale") else "purchase_payment"
        return AuditTrail.get_entity_history(entity_type, self.id)
