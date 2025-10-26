from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator

# استيراد نماذج الدفعات
try:
    from .models.payment import CustomerPayment
except ImportError:
    # في حالة عدم وجود الملف، إنشاء نموذج بسيط
    CustomerPayment = None


class Customer(models.Model):
    """
    نموذج العميل المحسن مع التكامل مع النظام المرجعي
    """

    CLIENT_TYPES = (
        ("individual", _("فرد")),
        ("company", _("شركة")),
        ("government", _("جهة حكومية")),
        ("vip", _("عميل مميز")),
    )

    CONTACT_FREQUENCY_CHOICES = (
        ("weekly", _("أسبوعي")),
        ("monthly", _("شهري")),
        ("quarterly", _("ربع سنوي")),
        ("yearly", _("سنوي")),
    )

    # المعلومات الأساسية
    name = models.CharField(_("اسم العميل"), max_length=255)
    company_name = models.CharField(
        _("اسم الشركة"),
        max_length=255,
        blank=True,
        help_text=_("اسم الشركة إذا كان العميل شركة"),
    )

    # معلومات الاتصال المحسنة (من النظام المرجعي)
    phone = models.CharField(
        _("رقم الهاتف"), max_length=50, blank=True
    )
    phone_primary = models.CharField(
        _("رقم الهاتف الأساسي"),
        max_length=20,
        blank=True,
        help_text=_("رقم الهاتف الأساسي للتواصل"),
    )
    phone_secondary = models.CharField(
        _("رقم الهاتف الثانوي"),
        max_length=20,
        blank=True,
        help_text=_("رقم هاتف إضافي للتواصل"),
    )
    email = models.EmailField(_("البريد الإلكتروني"), blank=True, null=True)

    # معلومات العنوان المحسنة
    address = models.TextField(_("العنوان"), blank=True, null=True)
    city = models.CharField(
        _("المدينة"),
        max_length=100,
        blank=True,
        help_text=_("المدينة التي يقع فيها العميل"),
    )

    # المعلومات المالية والإدارية
    code = models.CharField(_("كود العميل"), max_length=20, unique=True)
    credit_limit = models.DecimalField(
        _("الحد الائتماني"), max_digits=12, decimal_places=2, default=0
    )
    balance = models.DecimalField(
        _("الرصيد الحالي"), max_digits=12, decimal_places=2, default=0
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    tax_number = models.CharField(
        _("الرقم الضريبي"), max_length=50, blank=True, null=True
    )

    # تصنيف العميل (من النظام المرجعي)
    client_type = models.CharField(
        _("نوع العميل"),
        max_length=20,
        choices=CLIENT_TYPES,
        default="individual",
        help_text=_("تصنيف العميل حسب النوع"),
    )

    # معلومات إدارة العلاقات (CRM)
    last_contact_date = models.DateTimeField(
        _("تاريخ آخر اتصال"),
        null=True,
        blank=True,
        help_text=_("تاريخ آخر تواصل مع العميل"),
    )
    contact_frequency = models.CharField(
        _("تكرار الاتصال"),
        max_length=20,
        choices=CONTACT_FREQUENCY_CHOICES,
        blank=True,
        help_text=_("معدل التواصل المطلوب مع العميل"),
    )

    # الملاحظات
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # ربط مع دليل الحسابات
    financial_account = models.OneToOneField(
        "financial.ChartOfAccounts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("الحساب المحاسبي"),
        related_name="customer",
        help_text=_("الحساب المحاسبي المرتبط بهذا العميل في دليل الحسابات"),
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="customers_created",
        null=True,
    )

    class Meta:
        verbose_name = _("عميل")
        verbose_name_plural = _("العملاء")
        ordering = ["name"]

    def __str__(self):
        # تجنب التكرار في العرض
        if self.company_name and self.company_name != self.name:
            return f"{self.name} ({self.company_name})"
        return self.name

    @property
    def available_credit(self):
        """
        حساب الرصيد المتاح
        """
        return self.credit_limit - self.balance

    @property
    def actual_balance(self):
        """
        حساب المديونية الفعلية من الفواتير والمدفوعات
        """
        from django.db.models import Sum

        # إجمالي كل الفواتير (نقدية وآجلة)
        total_sales = self.sales.aggregate(total=Sum("total"))["total"] or 0

        # إجمالي المدفوعات الفعلية على الفواتير
        from sale.models import SalePayment

        total_sale_payments = (
            SalePayment.objects.filter(sale__customer=self).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        # المديونية = إجمالي الفواتير - إجمالي المدفوعات على الفواتير
        return total_sales - total_sale_payments


class CustomerPayment(models.Model):
    """
    نموذج لتسجيل المدفوعات المستلمة من العملاء
    """

    PAYMENT_METHODS = (
        ("cash", _("نقدي")),
        ("bank_transfer", _("تحويل بنكي")),
        ("check", _("شيك")),
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        verbose_name=_("العميل"),
        related_name="payments",
    )
    amount = models.DecimalField(_("المبلغ"), max_digits=12, decimal_places=2)
    payment_date = models.DateField(_("تاريخ الدفع"))
    payment_method = models.CharField(
        _("طريقة الدفع"), max_length=20, choices=PAYMENT_METHODS
    )
    reference_number = models.CharField(
        _("رقم المرجع"), max_length=50, blank=True, null=True
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="customer_payments_created",
        null=True,
    )

    class Meta:
        verbose_name = _("مدفوعات العميل")
        verbose_name_plural = _("مدفوعات العملاء")
        ordering = ["-payment_date"]

    def __str__(self):
        return f"{self.customer} - {self.amount} - {self.payment_date}"
