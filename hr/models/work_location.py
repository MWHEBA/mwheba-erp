"""
نموذج مقرات العمل الجغرافية للشركات والفروع
"""
from django.db import models


class WorkLocation(models.Model):
    """نموذج مقر العمل الجغرافي (Geofencing Work Location)"""

    name_ar = models.CharField(max_length=150, verbose_name='اسم المقر بالعربية')
    name_en = models.CharField(max_length=150, blank=True, default='', verbose_name='اسم المقر بالإنجليزية')
    address = models.CharField(max_length=255, blank=True, default='', verbose_name='العنوان التفصيلي')

    # الإحداثيات الجغرافية
    latitude = models.DecimalField(max_digits=10, decimal_places=7, verbose_name='خط العرض (Latitude)')
    longitude = models.DecimalField(max_digits=10, decimal_places=7, verbose_name='خط الطول (Longitude)')

    # نصف القطر المسموح به للبصمة بالمتر
    radius_meters = models.PositiveIntegerField(
        default=100,
        verbose_name='نطاق البصمة المسموح (متر)',
        help_text='أقصى مسافة مسموح بها للموظف عن مركز المقر للبصم'
    )

    is_active = models.BooleanField(default=True, verbose_name='نشط')
    is_default = models.BooleanField(default=False, verbose_name='المقر الرئيسي الافتراضي')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')

    class Meta:
        verbose_name = 'مقر عمل'
        verbose_name_plural = 'مقرات العمل'
        ordering = ['-is_default', 'name_ar']

    def __str__(self):
        return f"{self.name_ar} ({self.radius_meters}م)"

    @property
    def name(self):
        return self.name_ar

    def save(self, *args, **kwargs):
        # إذا تم تعيين هذا المقر كافتراضي، يتم إلغاء الافتراضي عن باقي المقرات
        if self.is_default:
            WorkLocation.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
        from ..services.geofencing_service import GeofencingService
        GeofencingService.invalidate_cache()

    def delete(self, *args, **kwargs):
        res = super().delete(*args, **kwargs)
        from ..services.geofencing_service import GeofencingService
        GeofencingService.invalidate_cache()
        return res
