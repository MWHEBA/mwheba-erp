from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator, MinValueValidator
from django.conf import settings
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# استيراد نماذج الدفعات
try:
    from .models.payment import SupplierPayment
except ImportError:
    # في حالة عدم وجود الملف، إنشاء نموذج بسيط
    SupplierPayment = None

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

    name = models.CharField(_("اسم المورد"), max_length=255)
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
    is_active = models.BooleanField(_("نشط"), default=True)
    tax_number = models.CharField(
        _("الرقم الضريبي"), max_length=50, blank=True, null=True
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

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        """Generate automatic supplier code if not provided"""
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
                self.code = f"SUP{int(time.time()) % 100000:05d}"
        
        super().save(*args, **kwargs)

    @property
    def actual_balance(self):
        """
        حساب الاستحقاق الفعلي من فواتير المشتريات والمدفوعات
        """
        from django.db.models import Sum

        # إجمالي كل فواتير المشتريات
        total_purchases = self.purchases.aggregate(total=Sum("total"))["total"] or 0

        # إجمالي المدفوعات الفعلية على فواتير المشتريات
        from purchase.models import PurchasePayment

        total_purchase_payments = (
            PurchasePayment.objects.filter(purchase__supplier=self).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        # الاستحقاق = إجمالي فواتير المشتريات - إجمالي المدفوعات على الفواتير
        return total_purchases - total_purchase_payments





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
        return f"{self.service.name}: {self.min_quantity}+ → {self.price_per_unit}"




