from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone


class WorkOrder(models.Model):
    """
    نموذج أمر الشغل (مركز التكلفة / المشروع المصغر)
    """
    STATUS_CHOICES = (
        ("draft", _("مسودة")),
        ("pending", _("قيد الانتظار")),
        ("in_progress", _("قيد التنفيذ")),
        ("completed", _("مكتمل")),
        ("cancelled", _("ملغي")),
    )

    number = models.CharField(_("رقم أمر الشغل"), max_length=50, unique=True, blank=True)
    customer = models.ForeignKey(
        "client.Customer",
        on_delete=models.PROTECT,
        related_name="work_orders",
        verbose_name=_("العميل"),
    )
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    start_date = models.DateField(_("تاريخ البدء"), null=True, blank=True)
    delivery_date = models.DateField(_("تاريخ التسليم المتوقع"), null=True, blank=True)
    estimated_cost = models.DecimalField(
        _("التكلفة التقديرية"), max_digits=12, decimal_places=2, default=0
    )
    notes = models.TextField(_("ملاحظات وشروط العمل"), blank=True, null=True)
    
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="work_orders_created",
        verbose_name=_("أنشئ بواسطة"),
    )

    class Meta:
        verbose_name = _("أمر شغل")
        verbose_name_plural = _("أوامر الشغل")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.number:
            year = timezone.now().strftime('%Y')
            prefix = f"WO-{year}-"
            last_order = WorkOrder.objects.filter(number__startswith=prefix).order_by('-number').first()
            if last_order:
                try:
                    last_num = int(last_order.number.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexErr):
                    new_num = 1
            else:
                new_num = 1
            self.number = f"{prefix}{new_num:04d}"
        super().save(*args, **kwargs)
