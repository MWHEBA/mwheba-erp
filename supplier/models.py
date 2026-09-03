from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator, MinValueValidator
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import logging

from financial.mixins import MonetaryTransactionMixin
from utils.validators import validate_national_id

logger = logging.getLogger(__name__)

# إضافة النموذج الجديد في نفس الملف لتجنب مشاكل الاستيراد


class SupplierType(models.Model):
    """أنواع الموردين - النموذج الأساسي (للتوافق مع النظام القديم)"""

    name = models.CharField(_("اسم النوع"), max_length=100)
    code = models.CharField(
        _("الرمز"), max_length=50, unique=True  # إزالة choices وزيادة max_length
    )
    slug = models.SlugField(_("الرابط"), max_length=100, unique=True, blank=True)
    description = models.TextField(_("وصف"), blank=True)
    icon = models.CharField(
        _("أيقونة"),
        max_length=50,
        blank=True,
        help_text=_("اسم الأيقونة من Font Awesome"),
    )
    color = models.CharField(
        _("لون"), max_length=7, default="#007bff", help_text=_("لون بصيغة HEX")
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    display_order = models.PositiveIntegerField(_("ترتيب العرض"), default=0)
    
    # ربط مع النموذج الجديد للإعدادات الديناميكية
    settings = models.OneToOneField(
        'SupplierTypeSettings',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='supplier_type',
        verbose_name=_("إعدادات النوع")
    )

    class Meta:
        verbose_name = _("نوع مورد")
        verbose_name_plural = _("أنواع الموردين")
        ordering = ["display_order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.code)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    
    @classmethod
    def sync_with_settings(cls):
        """مزامنة الأنواع الحالية مع إعدادات النظام الجديد"""
        # إنشاء الأنواع الافتراضية إذا لم تكن موجودة
        SupplierTypeSettings.create_default_types()
        
        # مزامنة الأنواع الموجودة
        for supplier_type in cls.objects.all():
            settings, created = SupplierTypeSettings.objects.get_or_create(
                code=supplier_type.code,
                defaults={
                    'name': supplier_type.name,
                    'description': supplier_type.description,
                    'icon': supplier_type.icon or 'fas fa-truck',
                    'color': supplier_type.color,
                    'display_order': supplier_type.display_order,
                    'is_active': supplier_type.is_active,
                }
            )
            
            # ربط الإعدادات بالنوع
            if not supplier_type.settings:
                supplier_type.settings = settings
                supplier_type.save()
    
    @property
    def dynamic_name(self):
        """الحصول على الاسم من الإعدادات الديناميكية أو الاسم الثابت"""
        if self.settings:
            return self.settings.name
        return self.name
    
    @property
    def dynamic_icon(self):
        """الحصول على الأيقونة من الإعدادات الديناميكية أو الأيقونة الثابتة"""
        if self.settings:
            return self.settings.icon
        return self.icon or 'fas fa-truck'
    
    @property
    def dynamic_color(self):
        """الحصول على اللون من الإعدادات الديناميكية أو اللون الثابت"""
        if self.settings:
            return self.settings.color
        return self.color


class Supplier(models.Model):
    """
    نموذج المورد
    """
    ENTITY_TYPES = (
        ("individual", _("فرد")),
        ("company", _("شركة / منشأة")),
        ("government", _("جهة حكومية")),
    )

    name = models.CharField(_("اسم المورد"), max_length=255)
    entity_type = models.CharField(
        _("الكيان القانوني والضريبي"),
        max_length=20,
        choices=ENTITY_TYPES,
        default="company",
        blank=True,
        help_text=_("الكيان القانوني والضريبي للمورد (فرد، شركة/منشأة، جهة حكومية)")
    )
    national_id = models.CharField(
        _("الرقم القومي (للأفراد)"),
        max_length=14,
        blank=True,
        null=True,
        validators=[validate_national_id],
        help_text=_("الرقم القومي المكون من 14 رقماً للأفراد والحرفيين وموردي الخدمات المستقلين")
    )
    commercial_registry = models.CharField(
        _("السجل التجاري"),
        max_length=50,
        blank=True,
        null=True,
        help_text=_("رقم السجل التجاري للشركات والمنشآت")
    )
    phone_regex = RegexValidator(
        regex=r"^\+?1?\d{9,15}$",
        message=_(
            "يجب أن يكون رقم الهاتف بالصيغة: '+999999999'. يسمح بـ 15 رقم كحد أقصى."
        ),
    )
    phone = models.CharField(
        _("رقم الهاتف"), validators=[phone_regex], max_length=17, blank=True
    )
    address = models.TextField(_("العنوان"), blank=True, null=True)
    email = models.EmailField(_("البريد الإلكتروني"), blank=True, null=True)
    code = models.CharField(_("كود المورد"), max_length=20, unique=True, blank=True)
    contact_person = models.CharField(
        _("الشخص المسؤول"), max_length=255, blank=True, null=True
    )
    balance = models.DecimalField(
        _("الرصيد الحالي"), max_digits=12, decimal_places=2, default=0
    )
    credit_limit = models.DecimalField(
        _("سقف التسهيلات الائتمانية"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        help_text=_("الحد الأقصى للتسهيلات الائتمانية الممنوحة من المورد لشركتنا")
    )
    default_payment_term = models.ForeignKey(
        "customer.PaymentTerm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("شروط السداد المعيارية"),
        related_name="suppliers",
        help_text=_("شروط ومهلة السداد المعيارية المتفق عليها مع المورد")
    )
    grace_period_days = models.IntegerField(
        _("فترة السماح (أيام)"),
        default=0,
        blank=True,
        help_text=_("أيام السماح الإضافية بعد تاريخ استحقاق الفاتورة")
    )
    default_currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("العملة الافتراضية"),
        related_name="suppliers_default_currency",
        help_text=_("العملة الافتراضية المعتمدة لفتح فواتير ومعاملات هذا المورد تلقائياً")
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    tax_number = models.CharField(
        _("الرقم الضريبي"), max_length=50, blank=True, null=True
    )

    # بيانات التحويلات والحسابات البنكية للمورد
    bank_name = models.CharField(
        _("اسم البنك"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("اسم البنك الخاص بحساب المورد للتحويلات البنكية")
    )
    bank_account_number = models.CharField(
        _("رقم الحساب / الآيبان (IBAN)"),
        max_length=50,
        blank=True,
        null=True,
        help_text=_("رقم الحساب البنكي أو الآيبان الدولي للمورد")
    )
    bank_beneficiary_name = models.CharField(
        _("اسم المستفيد للتحويل البنكي"),
        max_length=150,
        blank=True,
        null=True,
        help_text=_("اسم المستفيد المطابق لبيانات الحساب البنكي")
    )

    # ربط مع دليل الحسابات
    financial_account = models.OneToOneField(
        "financial.ChartOfAccounts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("الحساب المحاسبي"),
        related_name="supplier",
        help_text=_("الحساب المحاسبي المرتبط بهذا المورد في دليل الحسابات"),
    )

    # نوع المورد الموحد
    primary_type = models.ForeignKey(
        SupplierType,
        on_delete=models.PROTECT,
        related_name="suppliers",
        verbose_name=_("نوع المورد"),
        help_text=_("تصنيف المورد حسب نوع الخدمة المقدمة")
    )



    # معلومات التواصل المحسنة
    website = models.URLField(_("الموقع الإلكتروني"), blank=True)
    whatsapp = models.CharField(_("واتساب"), max_length=20, blank=True)
    secondary_phone = models.CharField(_("هاتف ثانوي"), max_length=17, blank=True)

    # معلومات الموقع
    city = models.CharField(_("المدينة"), max_length=100, blank=True)
    country = models.CharField(_("البلد"), max_length=100, blank=True, default="مصر")

    # معلومات التشغيل
    working_hours = models.CharField(
        _("ساعات العمل"),
        max_length=100,
        blank=True,
        help_text=_("مثال: من 9 صباحاً إلى 5 مساءً"),
    )
    is_preferred = models.BooleanField(
        _("مورد مفضل"), default=False, help_text=_("هل هذا مورد مفضل للشركة؟")
    )

    # معلومات تجارية إضافية
    delivery_time_days = models.PositiveIntegerField(
        _("مدة التسليم (أيام)"),
        null=True,
        blank=True,
        help_text=_("متوسط مدة التسليم بالأيام"),
    )
    min_order_amount = models.DecimalField(
        _("الحد الأدنى للطلب"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("الحد الأدنى لقيمة الطلب"),
    )
    payment_terms = models.CharField(
        _("شروط الدفع"),
        max_length=100,
        blank=True,
        help_text=_("مثال: 30 يوم، نقداً، آجل"),
    )
    supplier_rating = models.DecimalField(
        _("تقييم المورد"),
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        help_text=_("تقييم من 1 إلى 5"),
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True, null=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True, null=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="suppliers_created",
        null=True,
    )

    class Meta:
        verbose_name = _("مورد")
        verbose_name_plural = _("الموردين")
        ordering = ["name"]

    @property
    def available_prepaid_balance(self):
        """
        Legacy Compatibility Wrapper: حساب الرصيد المسبق المتاح للمورد بالعملة المحددة أو الأحادية
        """
        try:
            from financial.services.partner_advance_service import PartnerAdvanceService
            return PartnerAdvanceService.get_available_balance(self, currency=self.default_currency)
        except Exception:
            from supplier.services.supplier_allocation_service import SupplierAllocationService
            return SupplierAllocationService.get_available_supplier_prepaid_balance(self.id)

    def __str__(self):
        return str(self.name or f"Supplier {self.pk or ''}")
    
    def save(self, *args, **kwargs):
        """Generate automatic supplier code and set default primary_type and default_currency if not provided"""
        if not self.default_currency_id:
            try:
                from financial.services.exchange_rate_service import ExchangeRateService
                func_curr = ExchangeRateService.get_functional_currency()
                if func_curr:
                    self.default_currency = func_curr
            except Exception:
                pass

        if not hasattr(self, 'primary_type') or self.primary_type_id is None:
            default_type, _ = SupplierType.objects.get_or_create(
                code='GENERAL',
                defaults={
                    'name': 'عام',
                    'slug': 'general',
                    'description': 'مورد عام'
                }
            )
            self.primary_type = default_type

        if not self.code:
            # Get the last supplier code (without locking to avoid transaction issues)
            last_supplier = Supplier.objects.filter(
                code__startswith='SUP',
                code__regex=r'^SUP\d+$'  # Only codes matching SUP followed by digits
            ).order_by('-code').first()
            
            if last_supplier and last_supplier.code:
                try:
                    # Extract number from last code (remove SUP prefix)
                    code_number = last_supplier.code.replace('SUP', '')
                    last_number = int(code_number)
                    new_number = last_number + 1
                except (ValueError, AttributeError):
                    new_number = 1
            else:
                new_number = 1
            
            # Generate new code with SUP prefix and ensure uniqueness
            max_attempts = 100
            for attempt in range(max_attempts):
                potential_code = f"SUP{new_number:03d}"
                if not Supplier.objects.filter(code=potential_code).exists():
                    self.code = potential_code
                    break
                new_number += 1
            else:
                # Fallback: use timestamp-based code if all attempts fail
                import time
        if self.default_payment_term and hasattr(self.default_payment_term, 'name'):
            self.payment_terms = self.default_payment_term.name

        super().save(*args, **kwargs)

        # مزامنة اسم الحساب المحاسبي تلقائياً في شجرة الحسابات بالنمط القياسي
        if self.financial_account:
            expected_account_name = f"{self.name} - {self.code}"
            if self.financial_account.name != expected_account_name:
                self.financial_account.name = expected_account_name
                self.financial_account.save(update_fields=["name"])

    @property
    def actual_balance(self):
        """
        حساب الاستحقاق الفعلي من فواتير المشتريات والمدفوعات (يستخدم الحقل المخزن لمنع N+1 Queries)
        """
        return self.balance





    @property 
    def monthly_cost_per_unit(self):
        """
        التكلفة الشهرية للوحدة
        """
        return 0



    def get_primary_type_display(self):
        """عرض النوع الأساسي للمورد من الإعدادات الديناميكية"""
        if self.primary_type and hasattr(self.primary_type, 'settings') and self.primary_type.settings:
            return self.primary_type.settings.name
        elif self.primary_type:
            return self.primary_type.name
        else:
            return _("غير محدد")
    
    def get_primary_type_icon(self):
        """الحصول على أيقونة النوع الأساسي من الإعدادات الديناميكية"""
        if self.primary_type and hasattr(self.primary_type, 'settings') and self.primary_type.settings:
            return self.primary_type.settings.icon
        elif self.primary_type:
            return self.primary_type.icon
        else:
            return 'fas fa-industry'
    
    def get_primary_type_color(self):
        """الحصول على لون النوع الأساسي من الإعدادات الديناميكية"""
        if self.primary_type and hasattr(self.primary_type, 'settings') and self.primary_type.settings:
            return self.primary_type.settings.color
        elif self.primary_type:
            return self.primary_type.color
        else:
            return '#6c757d'
    
    def get_primary_type_code(self):
        """الحصول على كود النوع الأساسي"""
        return self.primary_type.code if self.primary_type else None

    def get_all_types_display(self):
        """عرض نوع المورد الأساسي"""
        if self.primary_type:
            if self.primary_type.settings:
                return self.primary_type.settings.name
            return self.primary_type.name
        return "غير محدد"

    def supplier_types_display(self):
        """عرض نوع المورد بتنسيق HTML جميل للجداول"""
        if not self.primary_type:
            return '<span class="text-muted">غير محدد</span>'
        
        # استخدام الاسم والأيقونة واللون من الإعدادات الديناميكية
        name = self.primary_type.settings.name if self.primary_type.settings else self.primary_type.name
        icon = self.primary_type.settings.icon if self.primary_type.settings else self.primary_type.icon or 'fas fa-industry'
        color = self.primary_type.settings.color if self.primary_type.settings else self.primary_type.color or '#6c757d'
        
        badge_html = f'<span class="badge" style="background-color: {color}; color: white; font-size: 0.75rem;"><i class="{icon} me-1"></i>{name}</span>'
        return badge_html

    def get_contact_methods(self):
        """الحصول على طرق التواصل المتاحة"""
        methods = []
        if self.phone:
            methods.append({"type": "phone", "value": self.phone, "label": _("هاتف")})
        if self.secondary_phone:
            methods.append(
                {
                    "type": "phone",
                    "value": self.secondary_phone,
                    "label": _("هاتف ثانوي"),
                }
            )
        if self.whatsapp:
            methods.append(
                {"type": "whatsapp", "value": self.whatsapp, "label": _("واتساب")}
            )
        if self.email:
            methods.append(
                {"type": "email", "value": self.email, "label": _("بريد إلكتروني")}
            )
        if self.website:
            methods.append(
                {"type": "website", "value": self.website, "label": _("موقع إلكتروني")}
            )
        return methods



    def is_available_for_order(self):
        """التحقق من إمكانية الطلب من المورد"""
        return self.is_active and self.primary_type and self.primary_type.is_active
    
    
    def is_educational_supplier(self):
        """التحقق من كون المورد مورد متخصص - ديناميكي من الإعدادات"""
        if self.primary_type and hasattr(self.primary_type, 'settings') and self.primary_type.settings:
            return self.primary_type.settings.is_educational
        # Fallback للطريقة القديمة
        return self.primary_type and self.primary_type.code == 'educational'
    
    def is_service_provider(self):
        """التحقق من كون المورد مقدم خدمات - ديناميكي من الإعدادات"""
        if self.primary_type and hasattr(self.primary_type, 'settings') and self.primary_type.settings:
            return self.primary_type.settings.is_service_provider
        # Fallback للطريقة القديمة
        return self.primary_type and self.primary_type.code == 'service_provider'
    
    
    def get_educational_info(self):
        """الحصول على معلومات المورد المتخصص"""
        if not self.is_educational_supplier():
            return None
        
        return {
            'products_count': self.get_educational_products_count()
        }
    
    def get_educational_products_count(self):
        """عدد المنتجات المتخصصة للمورد"""
        try:
            from product.models import Product
            return Product.objects.filter(
                supplier=self,
                category__name__icontains='مواد'
            ).count()
        except:
            return 0
    
    def get_service_info(self):
        """الحصول على معلومات مقدم الخدمة"""
        if not self.is_service_provider():
            return None
        
        return {
            'service_category': 'خدمات عامة',
            'total_purchases': self.get_total_purchases_amount()
        }
    
    def get_supplier_type_display_ar(self):
        """عرض تصنيف المورد بالعربية"""
        if self.primary_type and self.primary_type.settings:
            return self.primary_type.settings.name
        elif self.primary_type:
            return self.primary_type.name
        return "غير محدد"
    
    def get_supplier_type_icon(self):
        """الحصول على أيقونة تصنيف المورد"""
        if self.primary_type and self.primary_type.settings:
            return self.primary_type.settings.icon
        elif self.primary_type:
            return self.primary_type.icon
        return 'fas fa-industry'
    
    def get_supplier_type_color(self):
        """الحصول على لون تصنيف المورد"""
        if self.primary_type and self.primary_type.settings:
            return self.primary_type.settings.color
        elif self.primary_type:
            return self.primary_type.color
        return '#6c757d'
    
    def get_total_purchases_amount(self, date_from=None, date_to=None):
        """حساب إجمالي المشتريات لفترة معينة"""
        try:
            from purchase.models import Purchase
            queryset = Purchase.objects.filter(supplier=self)
            
            if date_from:
                queryset = queryset.filter(date__gte=date_from)
            if date_to:
                queryset = queryset.filter(date__lte=date_to)
            
            from django.db.models import Sum
            total = queryset.aggregate(Sum('total'))['total__sum']
            return total or Decimal('0.00')
        except:
            return Decimal('0.00')
    
    def get_total_payments_amount(self, date_from=None, date_to=None):
        """حساب إجمالي المدفوعات لفترة معينة"""
        try:
            from purchase.models import PurchasePayment
            queryset = PurchasePayment.objects.filter(purchase__supplier=self)
            
            if date_from:
                queryset = queryset.filter(payment_date__gte=date_from)
            if date_to:
                queryset = queryset.filter(payment_date__lte=date_to)
            
            from django.db.models import Sum
            total = queryset.aggregate(Sum('amount'))['amount__sum']
            return total or Decimal('0.00')
        except:
            return Decimal('0.00')
    
    def get_last_transaction_date(self):
        """الحصول على تاريخ آخر معاملة"""
        try:
            from purchase.models import Purchase
            last_purchase = Purchase.objects.filter(supplier=self).order_by('-date').first()
            return last_purchase.date if last_purchase else None
        except:
            return None




# ========================================
# نموذج إعدادات أنواع الموردين الديناميكية
# ========================================

















# ========================================
# نموذج إعدادات أنواع الموردين الديناميكية
# ========================================

import re
from django.conf import settings
from django.core.exceptions import ValidationError


class SupplierTypeSettings(models.Model):
    """
    إعدادات أنواع الموردين الديناميكية
    يسمح بإضافة وتعديل أنواع الموردين من الواجهة
    """
    
    # معلومات أساسية
    name = models.CharField(
        _("اسم النوع"), 
        max_length=100,
        help_text=_("اسم نوع المورد كما سيظهر في الواجهة")
    )
    code = models.CharField(
        _("الرمز"), 
        max_length=50, 
        unique=True,
        help_text=_("رمز فريد لنوع المورد (بالإنجليزية)")
    )
    description = models.TextField(
        _("الوصف"), 
        blank=True,
        help_text=_("وصف مختصر لنوع المورد")
    )
    
    # المظهر البصري
    icon = models.CharField(
        _("الأيقونة"), 
        max_length=50,
        default="fas fa-truck",
        help_text=_("اسم الأيقونة من Font Awesome (مثل: fas fa-truck)")
    )
    color = models.CharField(
        _("اللون"), 
        max_length=7, 
        default="#007bff",
        help_text=_("لون النوع بصيغة HEX (مثل: #007bff)")
    )
    
    # الترتيب والحالة
    display_order = models.PositiveIntegerField(
        _("ترتيب العرض"), 
        default=0,
        help_text=_("ترتيب ظهور النوع في القوائم")
    )
    is_active = models.BooleanField(
        _("نشط"), 
        default=True,
        help_text=_("هل النوع نشط ويظهر في الواجهة؟")
    )
    is_system = models.BooleanField(
        _("نوع نظام"), 
        default=False,
        help_text=_("الأنواع الأساسية التي لا يمكن حذفها")
    )
    
    # ✨ نوع المورد - منتجات أم خدمات
    is_service_provider = models.BooleanField(
        _("مقدم خدمات"),
        default=False,
        help_text=_("هل هذا المورد يقدم خدمات (بدون مخزون) أم منتجات (تحتاج مخزون)؟")
    )
    
    # تتبع التغييرات
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True, null=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="created_supplier_types"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name=_("حُدث بواسطة"),
        related_name="updated_supplier_types"
    )
    
    class Meta:
        verbose_name = _("إعدادات نوع المورد")
        verbose_name_plural = _("إعدادات أنواع الموردين")
        ordering = ['display_order', 'name']
        db_table = 'supplier_type_settings'
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """التحقق من صحة البيانات"""
        super().clean()
        
        # التحقق من عدم تكرار الرمز
        if SupplierTypeSettings.objects.filter(
            code=self.code
        ).exclude(pk=self.pk).exists():
            raise ValidationError({
                'code': _("هذا الرمز مستخدم بالفعل")
            })
        
        # التحقق من صحة اللون
        if not re.match(r'^#[0-9A-Fa-f]{6}$', self.color):
            raise ValidationError({
                'color': _("يجب أن يكون اللون بصيغة HEX صحيحة (مثل: #007bff)")
            })
        
        # التحقق من صحة الرمز (إنجليزي فقط)
        if not re.match(r'^[a-zA-Z0-9_]+$', self.code):
            raise ValidationError({
                'code': _("يجب أن يحتوي الرمز على أحرف إنجليزية وأرقام وشرطة سفلية فقط")
            })
    
    def save(self, *args, **kwargs):
        """حفظ النموذج مع التحقق من البيانات والتحديث التلقائي"""
        self.full_clean()
        super().save(*args, **kwargs)
        
        # تحديث SupplierType المرتبط تلقائياً
        self.sync_with_supplier_type()
    
    def sync_with_supplier_type(self):
        """مزامنة البيانات مع SupplierType المرتبط"""
        try:
            # البحث عن SupplierType المرتبط أو إنشاؤه
            supplier_type, created = SupplierType.objects.get_or_create(
                code=self.code,
                defaults={
                    'name': self.name,
                    'description': self.description,
                    'icon': self.icon,
                    'color': self.color,
                    'display_order': self.display_order,
                    'is_active': self.is_active,
                    'settings': self
                }
            )
            
            # إذا كان موجوداً، قم بتحديثه بدون استدعاء save() لمنع الـ sync loop
            if not created:
                SupplierType.objects.filter(pk=supplier_type.pk).update(
                    name=self.name,
                    description=self.description,
                    icon=self.icon,
                    color=self.color,
                    display_order=self.display_order,
                    is_active=self.is_active,
                    settings=self,
                )
            
            # ربط العلاقة العكسية إذا لم تكن موجودة
            if not hasattr(self, 'supplier_type'):
                self.supplier_type = supplier_type
                # تجنب استدعاء save() مرة أخرى لمنع التكرار اللانهائي
                SupplierTypeSettings.objects.filter(pk=self.pk).update(supplier_type=supplier_type)
                
        except Exception as e:
            # تسجيل الخطأ دون إيقاف العملية
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"فشل في مزامنة SupplierTypeSettings {self.code} مع SupplierType: {e}")
    
    @property
    def suppliers_count(self):
        """عدد الموردين المرتبطين بهذا النوع"""
        return self.supplier_type.suppliers.filter(is_active=True).count() if hasattr(self, 'supplier_type') else 0
    
    @property
    def can_delete(self):
        """هل يمكن حذف هذا النوع؟"""
        return not self.is_system and self.suppliers_count == 0


    @property
    def is_educational(self):
        """هل هذا النوع خاص بالموردين المتخصصين؟"""
        return self.code == 'educational'
    
    @classmethod
    def get_active_types(cls):
        """جلب الأنواع النشطة مرتبة"""
        return cls.objects.filter(is_active=True).order_by('display_order', 'name')

    @classmethod
    def create_default_types(cls):
        """إنشاء الأنواع الافتراضية للنظام"""
        return cls.create_company_supplier_types()


# ========================================
# نماذج خدمات الموردين — المرحلة الأولى
# ========================================

class ServiceType(models.Model):
    """
    أنواع الخدمات التي يقدمها الموردون.
    كل نوع يحمل attribute_schema يعرّف الحقول الديناميكية لخدماته.
    """

    CATEGORY_CHOICES = [
        ('printing',      _('طباعة')),
        ('logistics',     _('لوجستيات')),
        ('manufacturing', _('تصنيع')),
        ('general',       _('عام')),
    ]

    code             = models.CharField(_("الرمز"), max_length=50, unique=True, db_index=True)
    name             = models.CharField(_("الاسم"), max_length=100)
    category         = models.CharField(_("الفئة"), max_length=50, choices=CATEGORY_CHOICES, default='general')
    icon             = models.CharField(_("الأيقونة"), max_length=50, default='fas fa-cog')
    description      = models.TextField(_("الوصف"), blank=True)
    attribute_schema = models.JSONField(
        _("مخطط الخصائص"),
        default=dict,
        blank=True,
        help_text=_("تعريف الحقول الديناميكية لهذا النوع من الخدمات")
    )
    is_active        = models.BooleanField(_("نشط"), default=True)
    order            = models.PositiveIntegerField(_("الترتيب"), default=0)
    created_at       = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name        = _("نوع خدمة")
        verbose_name_plural = _("أنواع الخدمات")
        ordering            = ['order', 'name']
        db_table            = 'supplier_service_type'

    def __str__(self):
        return self.name


class SupplierService(models.Model):
    """
    خدمة محددة يقدمها مورد معين.
    الخصائص التفصيلية (السعر، المواصفات) تُخزَّن في حقل attributes كـ JSON
    وفق attribute_schema الخاص بـ ServiceType.
    """

    supplier     = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='services',
        verbose_name=_("المورد")
    )
    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.PROTECT,
        related_name='supplier_services',
        verbose_name=_("نوع الخدمة")
    )
    currency     = models.ForeignKey(
        'financial.Currency',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_services',
        verbose_name=_("العملة"),
        help_text=_("عملة التسعير (اتركه فارغاً للعملة الافتراضية)")
    )
    pricing_formula = models.CharField(
        _("طريقة / معادلة التسعير"),
        max_length=30,
        choices=[
            ('PER_PIECE', _('بالقطعة / بالنسخة')),
            ('PER_SHEET', _('بالفرخ')),
            ('PER_SQM', _('بالمتر المربع')),
            ('PER_THOUSAND', _('بالألف (سحب / تراج)')),
            ('PER_SIGNATURE', _('بالملزمة')),
            ('FIXED_TOOLING', _('قالب / فورمة مقطوعية')),
            ('PER_REAM', _('بالرزمة (250/500 فرخ)')),
            ('PER_TON', _('بالطن (مع التحويل للفرخ)')),
        ],
        default='PER_PIECE',
        help_text=_("وحدة وطريقة احتساب تكلفة الخدمة أو الخامة")
    )
    minimum_charge = models.DecimalField(
        _("الحد الأدنى للتشغيل"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_("الحد الأدنى لقيمة أمر الشغل لهذه الخدمة بغض النظر عن صغر الكمية")
    )
    sheets_per_pack = models.PositiveIntegerField(
        _("عدد الأفرخ في الرزمة/الباكيت"),
        null=True,
        blank=True,
        default=500,
        help_text=_("يستخدم عند التسعير بالرزمة لحساب سعر الفرخ المفرد")
    )
    price_per_ton = models.DecimalField(
        _("سعر الطن"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("يستخدم عند التسعير بالطن لحساب سعر الفرخ بناءً على الجراماج والمقاس")
    )
    name         = models.CharField(_("اسم الخدمة"), max_length=255)
    base_price   = models.DecimalField(
        _("السعر الأساسي"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    setup_cost   = models.DecimalField(
        _("تكلفة الإعداد"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    attributes   = models.JSONField(
        _("الخصائص"),
        default=dict,
        blank=True,
        help_text=_("القيم الفعلية حسب attribute_schema الخاص بنوع الخدمة")
    )
    is_active    = models.BooleanField(_("نشط"), default=True)
    notes        = models.TextField(_("ملاحظات"), blank=True)
    created_at   = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at   = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name        = _("خدمة مورد")
        verbose_name_plural = _("خدمات الموردين")
        ordering            = ['supplier__name', 'service_type__name']
        db_table            = 'supplier_supplier_service'
        indexes             = [
            models.Index(fields=['supplier', 'service_type']),
            models.Index(fields=['service_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.supplier.name} — {self.name}"

    def get_price_for_quantity(self, quantity=1):
        """
        إرجاع السعر المناسب للكمية المطلوبة.
        يبحث أولاً في الشرائح السعرية، ثم يرجع base_price كـ fallback.
        """
        tier = self.price_tiers.filter(
            is_active=True,
            min_quantity__lte=quantity
        ).filter(
            models.Q(max_quantity__isnull=True) | models.Q(max_quantity__gte=quantity)
        ).order_by('-min_quantity').first()

        return tier.price_per_unit if tier else self.base_price

    def calculate_cost(self, quantity=1, setup=None):
        """
        احتساب التكلفة الإجمالية للخدمة بالمعادلة الصناعية مع احترام الحد الأدنى للتشغيل:
        Cost = max(minimum_charge, (quantity * unit_price) + setup_cost)
        """
        unit_price = self.get_price_for_quantity(quantity)
        setup_fee = self.setup_cost if setup is None else Decimal(str(setup))
        calculated = (Decimal(str(quantity)) * unit_price) + setup_fee
        min_floor = self.minimum_charge or Decimal('0.00')
        return max(min_floor, calculated)

    def get_effective_sheet_price(self, width_cm=None, height_cm=None, gsm=None):
        """
        حساب سعر الفرخ المفرد الفعلي بناءً على نوع التسعير (فرخ / رزمة / طن)
        """
        if self.pricing_formula == 'PER_TON' and self.price_per_ton and width_cm and height_cm and gsm:
            sheet_weight_kg = (Decimal(str(width_cm)) * Decimal(str(height_cm)) * Decimal(str(gsm))) / Decimal('10000000')
            return (sheet_weight_kg * (self.price_per_ton / Decimal('1000'))).quantize(Decimal('0.0001'))
        elif self.pricing_formula == 'PER_REAM' and self.base_price and self.sheets_per_pack:
            return (self.base_price / Decimal(str(self.sheets_per_pack))).quantize(Decimal('0.0001'))
        return self.base_price


class ServicePriceTier(models.Model):
    """
    شرائح سعرية للخدمة — سعر مختلف حسب الكمية.
    مثال: 1-999 نسخة بسعر X، 1000+ نسخة بسعر Y.
    """

    service        = models.ForeignKey(
        SupplierService,
        on_delete=models.CASCADE,
        related_name='price_tiers',
        verbose_name=_("الخدمة")
    )
    min_quantity   = models.PositiveIntegerField(_("الحد الأدنى للكمية"))
    max_quantity   = models.PositiveIntegerField(
        _("الحد الأقصى للكمية"),
        null=True,
        blank=True,
        help_text=_("اتركه فارغاً للدلالة على بلا حد أعلى")
    )
    price_per_unit = models.DecimalField(
        _("السعر لكل وحدة"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    is_active      = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name        = _("شريحة سعرية")
        verbose_name_plural = _("الشرائح السعرية")
        ordering            = ['service', 'min_quantity']
        db_table            = 'supplier_service_price_tier'
        constraints         = [
            models.CheckConstraint(
                check=models.Q(max_quantity__isnull=True) | models.Q(max_quantity__gte=models.F('min_quantity')),
                name='price_tier_max_gte_min'
            )
        ]

    def __str__(self):
        if self.max_quantity:
            return f"{self.service.name}: {self.min_quantity}–{self.max_quantity} → {self.price_per_unit}"

class SupplierTransaction(models.Model):
    """
    معاملات الموردين المفتوحة للتسوية (FIN-SUB-001 & FIN-SUB-007 DB CheckConstraint)
    """
    supplier = models.ForeignKey(
        'Supplier',
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name=_("المورد")
    )
    transaction_type = models.CharField(_("نوع المعاملة"), max_length=50) # BILL, PAYMENT, CREDIT_NOTE
    transaction_number = models.CharField(_("رقم المعاملة"), max_length=100)
    issue_date = models.DateField(_("تاريخ الإصدار"))
    due_date = models.DateField(_("تاريخ الاستحقاق"))
    currency = models.CharField(_("العملة"), max_length=10, default="EGP")
    foreign_amount = models.DecimalField(_("المبلغ بالعملة الأجنبية"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal('1.000000'))
    functional_amount = models.DecimalField(_("المبلغ الوظيفي بالعملة المحلية"), max_digits=15, decimal_places=2)
    open_amount_foreign = models.DecimalField(_("المبلغ المفتوح بالعملة الأجنبية"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    open_amount_functional = models.DecimalField(_("المبلغ المفتوح الوظيفي"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    open_amount = models.DecimalField(_("المبلغ المفتوح المتبقي للتسوية"), max_digits=15, decimal_places=2)
    status = models.CharField(_("الحالة"), max_length=20, default="OPEN") # OPEN, PARTIAL, CLOSED

    class Meta:
        verbose_name = _("معاملة مالية للمورد")
        verbose_name_plural = _("معاملات الموردين المالية")
        indexes = [
            models.Index(fields=["supplier", "status"]),
            models.Index(fields=["due_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(open_amount__gte=Decimal('0.00')),
                name="check_supplier_txn_open_amount_positive"
            )
        ]

    def __str__(self):
        return f"SupplierTxn {self.transaction_number} ({self.open_amount} {self.currency})"


import uuid
import hashlib


class SupplierAdvancePayment(MonetaryTransactionMixin, models.Model):
    """
    نموذج الدفعات المقدمة للموردين (عربون/سداد تحت الحساب قبل صدور الفواتير)
    """
    PAYMENT_METHODS = (
        ("cash", _("نقدي")),
        ("bank_transfer", _("تحويل بنكي")),
        ("check", _("شيك")),
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        verbose_name=_("المورد"),
        related_name="advance_payments",
    )
    amount = models.DecimalField(_("المبلغ الأصلي"), max_digits=12, decimal_places=2)
    allocated_amount = models.DecimalField(_("المبلغ المخصص على الفواتير"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_date = models.DateField(_("تاريخ الصرف"), default=timezone.now)
    payment_method = models.CharField(
        _("طريقة الصرف"), max_length=20, choices=PAYMENT_METHODS, default="cash"
    )
    reference_number = models.CharField(
        _("رقم المرجع / الشيك"), max_length=50, blank=True, null=True
    )
    financial_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("الخزينة / البنك المصدر"),
    )
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("القيد المحاسبي المرتبط"),
    )
    notes = models.TextField(_("ملاحظات / السبب"), blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
    )

    class Meta:
        verbose_name = _("دفعة مقدمة للمورد")
        verbose_name_plural = _("الدفعات المقدمة للموردين")
        ordering = ["-payment_date", "-created_at"]

    def save(self, *args, **kwargs):
        self.populate_monetary_fields()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Supplier Advance #{self.id} - {self.supplier.name} ({self.amount} EGP)"

    @property
    def remaining_amount(self) -> Decimal:
        """المبلغ المتبقي المتاح للتخصيص من هذه الدفعة"""
        return max(Decimal("0.00"), self.amount - self.allocated_amount)


SupplierPayment = SupplierAdvancePayment


class ImmutableSupplierAllocationAuditManager(models.Manager):
    def update(self, **kwargs):
        raise ValueError("FIN-AP-004 Immutability Guard: Bulk UPDATE operations on SupplierAllocationAudit are strictly prohibited.")

    def delete(self):
        raise ValueError("FIN-AP-004 Immutability Guard: Bulk DELETE operations on SupplierAllocationAudit are strictly prohibited.")


class SupplierAllocationAudit(models.Model):
    """
    FIN-AP-004: Supplier Allocation Audit Evidence Model
    سجل تدقيق وإثبات توزيعات سداد مستحقات الموردين غير القابل للتعديل
    """
    objects = ImmutableSupplierAllocationAuditManager()

    TYPE_CHOICES = (
        ("PAYMENT_TO_BILL", _("سداد فاتورة مشتريات")),
        ("ADVANCE_TO_BILL", _("تسوية دفعة مقدمة")),
        ("DEBIT_NOTE_TO_BILL", _("تسوية إشعار خصم/مردودات")),
        ("REVERSAL", _("عكس توزيع سداد")),
    )

    STATUS_CHOICES = (
        ("APPLIED", _("مطبق")),
        ("REVERSED", _("معكوس")),
    )

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="allocation_audits", verbose_name=_("المورد"))
    allocation_reference = models.CharField(_("مرجع التوزيع الفريد"), max_length=100, unique=True, default=uuid.uuid4)
    payment_transaction = models.ForeignKey(SupplierTransaction, on_delete=models.PROTECT, related_name="payment_allocations", verbose_name=_("معاملة التحصيل/الإشعار"))
    invoice_transaction = models.ForeignKey(SupplierTransaction, on_delete=models.PROTECT, related_name="bill_allocations", verbose_name=_("معاملة الفاتورة المستهدفة"))

    source_document_type = models.CharField(_("نوع المستند المصدر"), max_length=50, blank=True, null=True)
    source_document_number = models.CharField(_("رقم المستند المصدر"), max_length=100, blank=True, null=True)
    target_document_type = models.CharField(_("نوع المستند المستهدف"), max_length=50, blank=True, null=True)
    target_document_number = models.CharField(_("رقم المستند المستهدف"), max_length=100, blank=True, null=True)

    allocation_type = models.CharField(_("نوع التوزيع"), max_length=30, choices=TYPE_CHOICES, default="ADVANCE_TO_BILL")
    allocated_amount = models.DecimalField(_("المبلغ المخصص بالعملة الأصلي"), max_digits=15, decimal_places=2)
    allocation_currency = models.CharField(_("عملة التوزيع"), max_length=3, default="EGP")
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))
    functional_amount = models.DecimalField(_("المبلغ الوظيفي المخصص (EGP)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    realized_fx_difference = models.DecimalField(_("فروق عملة محققة (EGP)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    allocation_status = models.CharField(_("حالة التوزيع"), max_length=20, choices=STATUS_CHOICES, default="APPLIED")
    reversed_audit = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reversals", verbose_name=_("سجل التدقيق المعكوس"))
    allocation_date = models.DateField(_("تاريخ التوزيع"), default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("أنشئ بواسطة"))
    evidence_hash = models.CharField(_("توقيع إثبات التوزيع SHA256"), max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("تدقيق توزيعات سداد الموردين")
        verbose_name_plural = _("سجلات تدقيق توزيعات سداد الموردين")
        ordering = ["-allocation_date", "-created_at"]
        indexes = [
            models.Index(fields=["supplier", "allocation_date"]),
            models.Index(fields=["allocation_reference", "created_at"], name="idx_supp_alloc_corr_time"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-AP-004 Immutability Guard: SupplierAllocationAudit records are strictly INSERT-ONLY and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FIN-AP-004 Immutability Guard: SupplierAllocationAudit records cannot be deleted.")

    def __str__(self):
        return f"Supplier Allocation Audit [{self.allocation_type}]: {self.source_document_number} -> {self.target_document_number} ({self.allocated_amount} {self.allocation_currency})"





