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
    
    # حقول الإغلاق المحاسبي المتقدمة
    retained_earnings_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='fiscal_years_retained',
        verbose_name=_("حساب الأرباح والخسائر المرحلة")
    )
    closing_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fiscal_years_closed',
        verbose_name=_("قيد تصفية السنة المالية")
    )
    closed_at = models.DateTimeField(_("تاريخ الإغلاق النهائي"), null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fiscal_years_closed_by',
        verbose_name=_("أغلق بواسطة")
    )
    net_profit_loss = models.DecimalField(
        _("صافي الربح/الخسارة المحسوب"),
        max_digits=18,
        decimal_places=2,
        default=0
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    @property
    def is_closed(self):
        return self.status == 'closed'

    def get_effective_retained_earnings_account(self):
        """
        الحصول على حساب الأرباح المرحلة المعتمد:
        1. التخصيص الخاص بالسنة المالية إن وجد
        2. سجل الأدوار المالية AccountRoleRegistry / إعدادات الشركة
        3. الحساب الافتراضي النظامي 30200
        """
        if self.retained_earnings_account_id:
            return self.retained_earnings_account

        from financial.models.chart_of_accounts import ChartOfAccounts
        # المحاولة عبر كود الحساب الافتراضي النظامي 30200
        account = ChartOfAccounts.objects.filter(code='30200', is_active=True).first()
        if account:
            return account

        # البحث عن حساب من فئة حقوق الملكية باسم أرباح مرحلة
        account = ChartOfAccounts.objects.filter(
            account_type__category='equity',
            is_active=True
        ).first()
        return account

    class Meta:
        verbose_name = _("سنة مالية")
        verbose_name_plural = _("السنوات المالية")
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.year_code})"
