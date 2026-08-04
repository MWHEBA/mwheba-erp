from django.db import models
from django.utils.translation import gettext_lazy as _


class FiscalYear(models.Model):
    """
    السنة المالية (Fiscal Year Model)
    """
    STATUS_CHOICES = [
        ('draft', _('مسودة')),
        ('open', _('مفتوحة')),
        ('closed', _('مغلقة')),
    ]

    year_code = models.CharField(max_length=20, unique=True, verbose_name=_("رمز السنة المالية"))
    name = models.CharField(max_length=100, verbose_name=_("اسم السنة المالية"))
    start_date = models.DateField(verbose_name=_("تاريخ البداية"))
    end_date = models.DateField(verbose_name=_("تاريخ النهاية"))
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name=_("الحالة")
    )
    is_closed = models.BooleanField(default=False, verbose_name=_("مغلقة؟"))

    class Meta:
        verbose_name = _("سنة مالية")
        verbose_name_plural = _("السنوات المالية")
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.year_code})"
