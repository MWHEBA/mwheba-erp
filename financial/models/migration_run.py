from django.db import models
from django.utils.translation import gettext_lazy as _


class DataMigrationRun(models.Model):
    """
    جدول موحد لتتبع وتدقيق عمليات هجرة البيانات السابقة عبر مديولات النظام المختلفة
    """
    migration_name = models.CharField(_("اسم عملية الهجرة"), max_length=100)
    module_name = models.CharField(_("المديول"), max_length=50)
    status = models.CharField(_("الحالة"), max_length=20, default="COMPLETED")
    total_records_processed = models.PositiveIntegerField(_("إجمالي السجلات المعالجة"), default=0)
    unmatched_records_count = models.PositiveIntegerField(_("السجلات غير المتطابقة"), default=0)
    notes = models.TextField(_("ملاحظات / تقرير التدقيق"), blank=True, null=True)
    executed_at = models.DateTimeField(_("تاريخ التنفيذ"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل هجرة البيانات")
        verbose_name_plural = _("سجلات هجرة البيانات")
        ordering = ["-executed_at"]

    def __str__(self):
        return f"MigrationRun [{self.module_name} - {self.migration_name}] ({self.status}) - {self.executed_at}"
