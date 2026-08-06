from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


class Currency(models.Model):
    """
    FIN-CORE-016: Currency Master
    جدول العملات المحوكم وفق المعيار الدولي IAS 21
    """
    code = models.CharField(_("رمز العملة"), max_length=3, unique=True)  # EGP, USD, EUR, etc.
    name = models.CharField(_("اسم العملة"), max_length=50)
    symbol = models.CharField(_("رمز الرمزية"), max_length=10, blank=True, null=True)
    decimal_places = models.PositiveSmallIntegerField(_("الكسور العشريّة"), default=2)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_functional = models.BooleanField(_("العملة المحلية الأساسية؟"), default=False)

    @property
    def is_base(self):

        return self.is_functional

    class Meta:
        verbose_name = _("عملة")
        verbose_name_plural = _("العملات")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.pk:
            original = Currency.objects.get(pk=self.pk)
            if original.is_functional != self.is_functional:
                from financial.models.journal_entry import JournalEntry
                if JournalEntry.objects.filter(status="posted").exists():
                    from django.core.exceptions import ValidationError
                    raise ValidationError(_("محظور حوكمياً: لا يمكن تغيير العملة الأساسية للمؤسسة بعد ترحيل قيود محاسبية. استخدم سكريبت historical_currency_migration للمناقلة."))
        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.is_functional:
            # Ensure only one base currency exists
            Currency.objects.filter(is_functional=True).exclude(pk=self.pk).update(is_functional=False)
        super().save(*args, **kwargs)


class ExchangeRate(models.Model):
    """
    FIN-CORE-016: Exchange Rate Master & Historical Snapshots
    سجل أسعار الصرف التاريخية وفق المعيار الدولي IAS 21
    """
    from_currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name="from_rates", verbose_name=_("من عملة"))
    to_currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name="to_rates", verbose_name=_("إلى عملة"))
    rate = models.DecimalField(_("سعر الصرف"), max_digits=18, decimal_places=6)
    effective_date = models.DateField(_("تاريخ السريان"), default=timezone.now)
    source = models.CharField(_("المصدر"), max_length=50, default="MANUAL")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("سعر صرف")
        verbose_name_plural = _("أسعار الصرف")
        ordering = ["-effective_date", "-created_at"]
        indexes = [
            models.Index(fields=["from_currency", "to_currency", "effective_date"]),
        ]

    def __str__(self):
        return f"1 {self.from_currency.code} = {self.rate} {self.to_currency.code} ({self.effective_date})"
