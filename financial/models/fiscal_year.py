from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class FiscalYear(models.Model):
    """
    نموذج السنة المالية - ينظم الفترات المالية والإقفالات السنوية
    """
    STATUS_CHOICES = [
        ('draft', _('مسودة')),
        ('open', _('مفتوحة')),
        ('closed', _('مغلقة')),
    ]

    year_code = models.CharField(max_length=20, unique=True, db_index=True, verbose_name=_("كود السنة المالية"))
    name = models.CharField(max_length=100, verbose_name=_("اسم السنة المالية"))
    start_date = models.DateField(verbose_name=_("تاريخ البداية"))
    end_date = models.DateField(verbose_name=_("تاريخ النهاية"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name=_("الحالة"))
    is_closed = models.BooleanField(default=False, verbose_name=_("مغلقة؟"))

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("سنة مالية")
        verbose_name_plural = _("السنوات المالية")
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.year_code})"
