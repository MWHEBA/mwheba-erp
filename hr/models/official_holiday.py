"""
نموذج الإجازات الرسمية
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from datetime import timedelta

User = get_user_model()


class OfficialHoliday(models.Model):
    """إجازة رسمية (عيد، عطلة رسمية، إجازة رسمية)"""

    name = models.CharField(max_length=200, verbose_name='اسم الإجازة')
    start_date = models.DateField(verbose_name='تاريخ البداية')
    end_date = models.DateField(verbose_name='تاريخ النهاية')
    description = models.TextField(blank=True, verbose_name='الوصف')
    is_active = models.BooleanField(default=True, verbose_name='نشطة')

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_official_holidays',
        verbose_name='أنشأها'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')

    class Meta:
        verbose_name = 'إجازة رسمية'
        verbose_name_plural = 'الإجازات الرسمية'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError('تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية')

    @property
    def duration_days(self):
        """عدد أيام الإجازة"""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    def get_date_range(self):
        """يرجع قائمة بجميع تواريخ الإجازة"""
        dates = []
        current = self.start_date
        while current <= self.end_date:
            dates.append(current)
            current += timedelta(days=1)
        return dates
