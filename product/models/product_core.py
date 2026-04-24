# -*- coding: utf-8 -*-
"""
النماذج الأساسية للمنتجات
يحتوي على: Category, Unit, Product, ProductImage, ProductVariant
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class Category(models.Model):
    """
    نموذج تصنيفات المنتجات
    """

    name = models.CharField(_("اسم التصنيف"), max_length=255)
    code = models.CharField(
        _("رمز التصنيف"), 
        max_length=10, 
        unique=True,
        blank=True,
        null=True,
        help_text=_("رمز مختصر للتصنيف (مثل: SUP للمواد والمستلزمات)")
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="children",
        verbose_name=_("التصنيف الأم"),
    )
    description = models.TextField(_("الوصف"), blank=True, null=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("فئة")
        verbose_name_plural = _("التصنيفات")
        ordering = ["name"]

    def __str__(self):
        if self.parent:
            return f"{self.parent} > {self.name}"
        return self.name
    
    @classmethod
    def create_default_categories(cls):
        """إنشاء تصنيفات المنتجات الافتراضية للشركة"""
        from django.db import transaction
        
        default_categories = [
            # التصنيفات الرئيسية
            {'name': 'المواد والمستلزمات', 'parent': None, 'code': 'SUP'},
            {'name': 'الزي الرسمي', 'parent': None, 'code': 'UNI'},
            {'name': 'القرطاسية والمكتبية', 'parent': None, 'code': 'STA'},
            {'name': 'الأنشطة والفعاليات', 'parent': None, 'code': 'ACT'},
            {'name': 'مستلزمات المطبخ', 'parent': None, 'code': 'KIT'},
            {'name': 'مستلزمات النظافة', 'parent': None, 'code': 'CLN'},
            {'name': 'المستلزمات الطبية', 'parent': None, 'code': 'MED'},
            
            # تصنيفات فرعية للمواد والمستلزمات
            {'name': 'مواد الإنتاج', 'parent': 'المواد والمستلزمات', 'code': 'SUP-PRD'},
            {'name': 'أدوات العمل', 'parent': 'المواد والمستلزمات', 'code': 'SUP-TLS'},
            {'name': 'معدات التشغيل', 'parent': 'المواد والمستلزمات', 'code': 'SUP-EQP'},
            {'name': 'مواد التغليف', 'parent': 'المواد والمستلزمات', 'code': 'SUP-PKG'},
            
            # تصنيفات فرعية للزي الرسمي
            {'name': 'الزي الصيفي', 'parent': 'الزي الرسمي', 'code': 'UNI-SUM'},
            {'name': 'الزي الشتوي', 'parent': 'الزي الرسمي', 'code': 'UNI-WIN'},
            {'name': 'الأحذية', 'parent': 'الزي الرسمي', 'code': 'UNI-SHO'},
            {'name': 'الحقائب', 'parent': 'الزي الرسمي', 'code': 'UNI-BAG'},
            
            # تصنيفات فرعية للقرطاسية
            {'name': 'أدوات الكتابة', 'parent': 'القرطاسية والمكتبية', 'code': 'STA-PEN'},
            {'name': 'أدوات الرسم', 'parent': 'القرطاسية والمكتبية', 'code': 'STA-DRA'},
            {'name': 'المستلزمات المكتبية', 'parent': 'القرطاسية والمكتبية', 'code': 'STA-OFF'},
        ]
        
        try:
            with transaction.atomic():
                created_categories = {}
                
                # إنشاء التصنيفات الرئيسية أولاً
                for cat_data in default_categories:
                    if cat_data['parent'] is None:
                        category, created = cls.objects.get_or_create(
                            name=cat_data['name'],
                            defaults={
                                'description': f'تصنيف {cat_data["name"]}',
                                'is_active': True
                            }
                        )
                        created_categories[cat_data['name']] = category
                
                # ثم إنشاء التصنيفات الفرعية
                for cat_data in default_categories:
                    if cat_data['parent'] is not None:
                        parent_category = created_categories.get(cat_data['parent'])
                        if parent_category:
                            category, created = cls.objects.get_or_create(
                                name=cat_data['name'],
                                defaults={
                                    'parent': parent_category,
                                    'description': f'تصنيف فرعي: {cat_data["name"]}',
                                    'is_active': True
                                }
                            )
                            created_categories[cat_data['name']] = category
                
                return True
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"فشل في إنشاء تصنيفات الشركة: {e}")
            return False


class Unit(models.Model):
    """
    نموذج وحدات القياس
    """

    name = models.CharField(_("اسم الوحدة"), max_length=50)
    symbol = models.CharField(_("الرمز"), max_length=10)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("وحدة قياس")
        verbose_name_plural = _("وحدات القياس")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class Product(models.Model):
    """
    نموذج المنتجات
    """

    name = models.CharField(_("اسم المنتج"), max_length=255)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("التصنيف"),
    )

    description = models.TextField(_("الوصف"), blank=True, null=True)
    sku = models.CharField(_("كود المنتج"), max_length=50, unique=True, blank=True)
    barcode = models.CharField(_("الباركود"), max_length=50, blank=True, null=True)
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("وحدة القياس"),
    )
    cost_price = models.DecimalField(
        _("سعر التكلفة"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    selling_price = models.DecimalField(
        _("سعر البيع"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    min_stock = models.PositiveIntegerField(_("الحد الأدنى للمخزون"), default=0)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_featured = models.BooleanField(_("مميز"), default=False)
    tax_rate = models.DecimalField(
        _("نسبة الضريبة"),
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    discount_rate = models.DecimalField(
        _("نسبة الخصم"),
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="products_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("عُدل بواسطة"),
        related_name="products_updated",
    )

    # المورد الافتراضي
    default_supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("المورد الافتراضي"),
        related_name="default_products",
        help_text=_("المورد الافتراضي لهذا المنتج"),
    )
    
    # أنواع المنتجات حسب الاستخدام
    ITEM_TYPES = [
        ('educational', _('مادة متخصصة')),
        ('uniform', _('زي رسمي')),
        ('stationery', _('قرطاسية')),
        ('activity', _('نشاط')),
        ('kitchen', _('مطبخ')),
        ('cleaning', _('نظافة')),
        ('medical', _('طبي')),
        ('general', _('عام')),
    ]
    
    item_type = models.CharField(
        _("نوع المنتج"),
        max_length=20,
        choices=ITEM_TYPES,
        default='general',
        help_text=_("تصنيف المنتج حسب الاستخدام"),
    )
    
    # الفئة المستهدفة
    suitable_for_grades = models.CharField(
        _("الفئة المستهدفة"),
        max_length=200,
        blank=True,
        help_text=_("الفئة أو القسم المستهدف بهذا المنتج")
    )
    
    # معلومات إضافية للزي الرسمي
    uniform_size = models.CharField(
        _("مقاس الزي"),
        max_length=20,
        blank=True,
        help_text=_("مقاس الزي الرسمي (S, M, L, XL, إلخ)")
    )
    uniform_gender = models.CharField(
        _("جنس الزي"),
        max_length=10,
        choices=[('boys', _('رجالي')), ('girls', _('نسائي')), ('unisex', _('مشترك'))],
        blank=True,
        help_text=_("الجنس المخصص له الزي")
    )
    
    # معلومات إضافية للمواد المتخصصة
    educational_subject = models.CharField(
        _("التخصص"),
        max_length=100,
        blank=True,
        help_text=_("التخصص أو القسم المرتبط بهذا المنتج")
    )
    
    # معلومات السلامة والجودة
    is_child_safe = models.BooleanField(
        _("آمن للاستخدام"),
        default=True,
        help_text=_("هل المنتج آمن للاستخدام العام؟")
    )
    quality_certificate = models.CharField(
        _("شهادة الجودة"),
        max_length=100,
        blank=True,
        help_text=_("شهادة الجودة أو المطابقة للمنتج")
    )
    
    # حقل المنتجات المجمعة
    is_bundle = models.BooleanField(
        _("منتج مجمع"),
        default=False,
        help_text=_("هل هذا المنتج عبارة عن مجموعة من المنتجات الأخرى؟")
    )
    
    # ✨ حقل الخدمات
    is_service = models.BooleanField(
        _("خدمة"),
        default=False,
        db_index=True,
        help_text=_("هل هذا منتج أم خدمة؟ (الخدمات لا تحتاج مخزون)")
    )

    class Meta:
        verbose_name = _("منتج")
        verbose_name_plural = _("المنتجات")
        ordering = ["name"]
        indexes = [
            models.Index(fields=['is_bundle'], name='product_is_bundle_idx'),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"
    
    def get_type_display_ar(self):
        """عرض نوع المنتج بالعربي"""
        if self.is_service:
            return "خدمة"
        elif self.is_bundle:
            return "منتج مجمع"
        else:
            return "منتج"
    
    def get_type_icon(self):
        """أيقونة نوع المنتج"""
        if self.is_service:
            return "fa-concierge-bell"
        elif self.is_bundle:
            return "fa-boxes"
        else:
            return "fa-box"

    @property
    def user(self):
        """
        Backward compatibility property for code that accesses product.user
        Returns created_by for compatibility
        """
        return self.created_by
    
    @property
    def current_stock(self):
        """
        حساب المخزون الحالي في جميع المخازن
        """
        from django.db.models import Sum

        # معالجة حالة عدم وجود مخزون
        stock = self.stocks.aggregate(Sum("quantity"))
        return stock["quantity__sum"] or 0

    @property
    def calculated_stock(self):
        """
        المخزون المحسوب - للمنتجات العادية يُرجع المخزون الفعلي، للمنتجات المجمعة يُرجع المخزون المحسوب
        Requirements: 2.2, 2.3, 2.4
        """
        if self.is_bundle:
            return self.get_bundle_stock()
        return self.current_stock

    def get_bundle_stock(self):
        """
        حساب المخزون المتاح للمنتج المجمع بناءً على توفر المكونات
        Requirements: 2.2, 2.3, 2.4
        """
        if not self.is_bundle:
            return 0
        
        from ..services.stock_calculation_engine import StockCalculationEngine
        return StockCalculationEngine.calculate_bundle_stock(self)

    def get_bundle_stock_breakdown(self):
        """
        الحصول على تفصيل مخزون المنتج المجمع ومكوناته
        """
        if not self.is_bundle:
            return None
        
        from ..services.stock_calculation_engine import StockCalculationEngine
        return StockCalculationEngine.get_bundle_stock_breakdown(self)

    def validate_bundle_availability(self, requested_quantity):
        """
        التحقق من توفر كمية معينة من المنتج المجمع
        Requirements: 3.2, 3.3
        """
        if not self.is_bundle:
            return self.current_stock >= requested_quantity, "منتج عادي"
        
        from ..services.stock_calculation_engine import StockCalculationEngine
        return StockCalculationEngine.validate_bundle_availability(self, requested_quantity)

    @property
    def profit_margin(self):
        """
        حساب هامش الربح
        """
        if self.cost_price > 0:
            return (self.selling_price - self.cost_price) / self.cost_price * 100
        return 0

    def get_supplier_price(self, supplier):
        """
        الحصول على سعر المنتج من مورد معين
        """
        try:
            from .supplier_pricing import SupplierProductPrice
            supplier_price = SupplierProductPrice.objects.get(
                product=self, supplier=supplier, is_active=True
            )
            return supplier_price.cost_price
        except SupplierProductPrice.DoesNotExist:
            return None

    def get_all_supplier_prices(self):
        """الحصول على جميع أسعار الموردين للمنتج"""
        from .supplier_pricing import SupplierProductPrice
        return SupplierProductPrice.objects.filter(product=self, is_active=True)
    
    # دوال خاصة بأنواع المنتجات
    def is_educational_item(self):
        """التحقق من كون المنتج مادة متخصصة (للتوافق مع الكود القديم)"""
        return self.item_type == 'educational'
    
    def is_uniform_item(self):
        """التحقق من كون المنتج زي رسمي (للتوافق مع الكود القديم)"""
        return self.item_type == 'uniform'
    
    def is_suitable_for_grade(self, grade_level):
        """التحقق من مناسبة المنتج لفئة معينة (للتوافق مع الكود القديم)"""
        if not self.suitable_for_grades:
            return True
        return grade_level.lower() in self.suitable_for_grades.lower()
    
    def get_item_type_display_ar(self):
        """عرض نوع المنتج بالعربية"""
        return dict(self.ITEM_TYPES).get(self.item_type, self.item_type)
    
    def get_uniform_info(self):
        """الحصول على معلومات الزي الرسمي"""
        if not self.is_uniform_item():
            return None
        
        return {
            'size': self.uniform_size,
            'gender': self.get_uniform_gender_display() if self.uniform_gender else None,
            'suitable_for': self.suitable_for_grades,
            'quality_certificate': self.quality_certificate
        }
    
    def get_educational_info(self):
        """الحصول على معلومات المادة المتخصصة"""
        if not self.is_educational_item():
            return None
        
        return {
            'subject': self.educational_subject,
            'suitable_for': self.suitable_for_grades,
            'quality_certificate': self.quality_certificate,
            'is_safe': self.is_child_safe
        }
    
    @classmethod
    def get_products_by_type(cls, item_type):
        """الحصول على المنتجات حسب النوع"""
        return cls.objects.filter(
            item_type=item_type,
            is_active=True
        )
    
    @classmethod
    def get_products_for_grade(cls, grade_level):
        """الحصول على المنتجات المناسبة لفئة معينة"""
        return cls.objects.filter(
            models.Q(suitable_for_grades__icontains=grade_level) | 
            models.Q(suitable_for_grades='') | 
            models.Q(suitable_for_grades__isnull=True),
            is_active=True
        )
    
    @classmethod
    def generate_sku(cls, category):
        """
        توليد كود المنتج تلقائياً بناءً على كود التصنيف
        Format: [CATEGORY_CODE]-[SEQUENTIAL_NUMBER]
        مثال: EDU-001, UNI-002, STA-003
        """
        from django.utils.text import slugify
        
        # استخدام كود التصنيف إذا كان موجوداً، وإلا استخدم كود افتراضي
        if hasattr(category, 'code') and category.code:
            category_code = category.code.upper()
        else:
            # إنشاء كود إنجليزي من اسم التصنيف
            category_name = category.name.strip()
            
            # mapping للتصنيفات الموجودة
            arabic_to_english = {
                'كتب ومواد متخصصة': 'EDU',
                'مستلزمات مكتبية': 'STA',
                'الزي الرسمي': 'UNI',
                'ألعاب وترفيه': 'TOY',
                'خدمات': 'SRV',
                'أخرى': 'OTH',
                'سبلايز': 'SUP',
                # إضافات للكلمات الشائعة
                'كتب': 'BOO',
                'مواد': 'MAT',
                'متخصصة': 'EDU',
                'مكتبية': 'OFF',
                'الزي': 'UNI',
                'ألعاب': 'TOY',
                'خدمات': 'SRV',
            }
            
            # البحث عن تطابق كامل أولاً
            category_code = arabic_to_english.get(category_name)
            
            # إذا لم يوجد تطابق كامل، ابحث عن تطابق جزئي
            if not category_code:
                for arabic, english in arabic_to_english.items():
                    if arabic in category_name:
                        category_code = english
                        break
            
            # إذا لم يوجد أي تطابق، استخدم GEN
            if not category_code:
                category_code = 'GEN'
        
        # البحث عن آخر رقم تسلسلي للتصنيف
        prefix = f"{category_code}-"
        
        # البحث عن المنتجات التي تبدأ بنفس البادئة
        existing_products = cls.objects.filter(
            sku__startswith=prefix
        ).order_by('-sku')
        
        if existing_products.exists():
            # استخراج الرقم التسلسلي من آخر منتج
            last_sku = existing_products.first().sku
            try:
                # استخراج الرقم التسلسلي (بعد الشرطة)
                last_number = int(last_sku.split('-')[-1])
                next_number = last_number + 1
            except (ValueError, IndexError):
                next_number = 1
        else:
            next_number = 1
        
        # تكوين الكود الجديد
        new_sku = f"{prefix}{next_number:03d}"
        
        # التأكد من عدم وجود الكود (احتياط إضافي)
        while cls.objects.filter(sku=new_sku).exists():
            next_number += 1
            new_sku = f"{prefix}{next_number:03d}"
        
        return new_sku
    
    def save(self, *args, **kwargs):
        """
        حفظ المنتج مع توليد الكود تلقائياً إذا لم يكن موجوداً
        """
        if not self.sku and self.category:
            self.sku = self.generate_sku(self.category)
        
        super().save(*args, **kwargs)

    def get_primary_image(self):
        """
        الحصول على الصورة الرئيسية للمنتج
        """
        primary_image = self.images.filter(is_primary=True).first()
        if primary_image:
            return primary_image
        # إذا لم توجد صورة رئيسية، إرجاع أول صورة
        return self.images.first()

    def get_all_images(self):
        """
        الحصول على جميع صور المنتج مرتبة (الرئيسية أولاً)
        """
        return self.images.all().order_by("-is_primary", "created_at")

    def get_secondary_images(self):
        """
        الحصول على الصور الثانوية (غير الرئيسية)
        """
        return self.images.filter(is_primary=False).order_by("created_at")

    def has_images(self):
        """
        التحقق من وجود صور للمنتج
        """
        return self.images.exists()

    def images_count(self):
        """
        عدد صور المنتج
        """
        return self.images.count()

    def update_cost_price_from_supplier(
        self, supplier, new_price, user, reason="manual_update", purchase_reference=None
    ):
        """
        تحديث سعر التكلفة من مورد معين
        """
        try:
            from decimal import Decimal
            from .supplier_pricing import SupplierProductPrice, PriceHistory

            # الحصول على أو إنشاء سعر المورد
            supplier_price, created = SupplierProductPrice.objects.get_or_create(
                product=self,
                supplier=supplier,
                defaults={
                    "cost_price": new_price,
                    "created_by": user,
                    "is_default": not SupplierProductPrice.objects.filter(
                        product=self
                    ).exists(),
                },
            )

            # إذا كان السعر موجود، سجل التغيير في التاريخ
            if not created and supplier_price.cost_price != new_price:
                PriceHistory.objects.create(
                    supplier_product_price=supplier_price,
                    old_price=supplier_price.cost_price,
                    new_price=new_price,
                    change_reason=reason,
                    purchase_reference=purchase_reference,
                    changed_by=user,
                )

                # تحديث السعر
                supplier_price.cost_price = new_price
                supplier_price.save()

            return supplier_price

        except Exception as e:
            print(f"خطأ في تحديث سعر المورد: {e}")
            return None


class ProductImage(models.Model):
    """
    نموذج صور المنتجات
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("المنتج"),
    )
    image = models.ImageField(_("الصورة"), upload_to="products/%Y/%m/")
    is_primary = models.BooleanField(_("صورة رئيسية"), default=False)
    alt_text = models.CharField(_("نص بديل"), max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("صورة منتج")
        verbose_name_plural = _("صور المنتجات")
        ordering = ["-is_primary", "created_at"]
        # Note: UniqueConstraint with condition not supported in MariaDB
        # Uniqueness is enforced in save() method instead

    def save(self, *args, **kwargs):
        # إذا كانت هذه الصورة رئيسية، تأكد من عدم وجود صورة رئيسية أخرى
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)

        # إذا كانت هذه أول صورة للمنتج، اجعلها رئيسية
        elif not self.product.images.exists():
            self.is_primary = True

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # إذا تم حذف الصورة الرئيسية، اجعل أول صورة أخرى رئيسية
        if self.is_primary:
            next_image = self.product.images.exclude(pk=self.pk).first()
            if next_image:
                next_image.is_primary = True
                next_image.save()

        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.product} - {self.alt_text or 'صورة'}"


class ProductVariant(models.Model):
    """
    نموذج متغيرات المنتج
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("المنتج"),
    )
    name = models.CharField(_("اسم المتغير"), max_length=255)
    sku = models.CharField(_("رمز المتغير"), max_length=50, unique=True)
    barcode = models.CharField(_("الباركود"), max_length=50, blank=True, null=True)
    cost_price = models.DecimalField(
        _("سعر التكلفة"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    selling_price = models.DecimalField(
        _("سعر البيع"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    stock = models.PositiveIntegerField(_("المخزون"), default=0)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("متغير منتج")
        verbose_name_plural = _("متغيرات المنتجات")
        ordering = ["product", "name"]

    def __str__(self):
        return f"{self.product} - {self.name} ({self.sku})"


class BundleComponent(models.Model):
    """
    نموذج مكونات المنتجات المجمعة
    يربط المنتج المجمع بالمنتجات المكونة له مع الكمية المطلوبة
    """
    
    bundle_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='components',
        verbose_name=_("المنتج المجمع"),
        help_text=_("المنتج المجمع الذي يحتوي على هذا المكون")
    )
    component_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='used_in_bundles',
        verbose_name=_("المنتج المكون"),
        help_text=_("المنتج المكون الذي يدخل في تكوين المنتج المجمع")
    )
    required_quantity = models.PositiveIntegerField(
        _("الكمية المطلوبة"),
        validators=[MinValueValidator(1)],
        help_text=_("الكمية المطلوبة من هذا المكون لتكوين وحدة واحدة من المنتج المجمع")
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    
    class Meta:
        verbose_name = _("مكون منتج مجمع")
        verbose_name_plural = _("مكونات المنتجات المجمعة")
        unique_together = ('bundle_product', 'component_product')
        ordering = ['bundle_product', 'component_product']
        indexes = [
            models.Index(fields=['bundle_product'], name='bundlecomponent_bundle_idx'),
            models.Index(fields=['component_product'], name='bundlecomponent_component_idx'),
            models.Index(fields=['bundle_product', 'component_product'], name='bundlecomponent_unique_idx'),
        ]
    
    def __str__(self):
        return f"{self.bundle_product.name} - {self.component_product.name} ({self.required_quantity})"
    
    def clean(self):
        """
        التحقق من صحة البيانات قبل الحفظ
        """
        from django.core.exceptions import ValidationError
        
        # التحقق من أن المنتج المجمع مختلف عن المنتج المكون (منع التكرار الذاتي)
        if self.bundle_product_id == self.component_product_id:
            raise ValidationError(_("لا يمكن أن يكون المنتج مكوناً لنفسه"))
        
        # التحقق من أن المنتج المجمع هو فعلاً منتج مجمع
        # ملاحظة: نتخطى هذا التحقق إذا كان المنتج المجمع جديد (لم يحفظ بعد)
        if self.bundle_product and self.bundle_product.pk and not self.bundle_product.is_bundle:
            raise ValidationError(_("المنتج المحدد ليس منتجاً مجمعاً"))
        
        # التحقق من أن المنتج المكون ليس منتجاً مجمعاً (منع التداخل المعقد)
        if self.component_product and self.component_product.is_bundle:
            raise ValidationError(_("لا يمكن أن يكون المنتج المكون منتجاً مجمعاً آخر"))
        
        # التحقق من أن المنتج المكون نشط
        if self.component_product and not self.component_product.is_active:
            raise ValidationError(_("المنتج المكون غير نشط"))
    
    def save(self, *args, **kwargs):
        """
        حفظ مكون المنتج المجمع مع التحقق من صحة البيانات
        """
        self.full_clean()
        super().save(*args, **kwargs)


class BundleComponentAlternative(models.Model):
    """
    نموذج البدائل المتاحة لمكونات المنتجات المجمعة
    يسمح بتحديد منتجات بديلة لكل مكون مع فرق السعر
    """
    
    bundle_component = models.ForeignKey(
        BundleComponent,
        on_delete=models.CASCADE,
        related_name='alternatives',
        verbose_name=_("مكون المنتج المجمع"),
        help_text=_("المكون الذي يتم توفير بدائل له")
    )
    alternative_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='alternative_in_bundles',
        verbose_name=_("المنتج البديل"),
        help_text=_("المنتج البديل الذي يمكن اختياره بدلاً من المكون الأساسي")
    )
    is_default = models.BooleanField(
        _("افتراضي"),
        default=False,
        help_text=_("هل هذا البديل هو الاختيار الافتراضي؟")
    )
    price_adjustment = models.DecimalField(
        _("تعديل السعر"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_("فرق السعر عن المكون الأساسي (موجب للزيادة، سالب للتخفيض)")
    )
    display_order = models.PositiveIntegerField(
        _("ترتيب العرض"),
        default=0,
        help_text=_("ترتيب ظهور البديل في القائمة")
    )
    is_active = models.BooleanField(
        _("نشط"),
        default=True,
        help_text=_("هل البديل متاح للاختيار؟")
    )
    notes = models.TextField(
        _("ملاحظات"),
        blank=True,
        help_text=_("ملاحظات إضافية عن البديل")
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    
    class Meta:
        verbose_name = _("بديل مكون منتج مجمع")
        verbose_name_plural = _("بدائل مكونات المنتجات المجمعة")
        unique_together = ('bundle_component', 'alternative_product')
        ordering = ['bundle_component', 'display_order', 'alternative_product']
        indexes = [
            models.Index(fields=['bundle_component', 'is_active'], name='bundlealt_component_active_idx'),
            models.Index(fields=['alternative_product'], name='bundlealt_product_idx'),
        ]
    
    def __str__(self):
        adjustment_str = ""
        if self.price_adjustment > 0:
            adjustment_str = f" (+{self.price_adjustment} ج.م)"
        elif self.price_adjustment < 0:
            adjustment_str = f" ({self.price_adjustment} ج.م)"
        
        default_str = " [افتراضي]" if self.is_default else ""
        return f"{self.bundle_component.bundle_product.name} - {self.alternative_product.name}{adjustment_str}{default_str}"
    
    def clean(self):
        """
        التحقق من صحة البيانات قبل الحفظ
        """
        from django.core.exceptions import ValidationError
        
        # التحقق من أن المنتج البديل نشط
        if self.alternative_product and not self.alternative_product.is_active:
            raise ValidationError(_("المنتج البديل غير نشط"))
        
        # التحقق من أن المنتج البديل ليس منتجاً مجمعاً
        if self.alternative_product and self.alternative_product.is_bundle:
            raise ValidationError(_("لا يمكن أن يكون المنتج البديل منتجاً مجمعاً"))
        
        # التحقق من أن المنتج البديل مختلف عن المكون الأساسي
        if self.alternative_product_id == self.bundle_component.component_product_id:
            raise ValidationError(_("المنتج البديل يجب أن يكون مختلفاً عن المكون الأساسي"))
        
        # التحقق من وجود بديل افتراضي واحد فقط
        if self.is_default:
            existing_default = BundleComponentAlternative.objects.filter(
                bundle_component=self.bundle_component,
                is_default=True
            ).exclude(pk=self.pk)
            
            if existing_default.exists():
                raise ValidationError(_("يوجد بالفعل بديل افتراضي لهذا المكون"))
    
    def save(self, *args, **kwargs):
        """
        حفظ البديل مع التحقق من صحة البيانات
        """
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def final_price(self):
        """
        حساب السعر النهائي للبديل
        """
        base_price = self.bundle_component.component_product.selling_price
        return base_price + self.price_adjustment
    
    @property
    def is_available(self):
        """
        التحقق من توفر البديل (نشط ولديه مخزون)
        """
        return self.is_active and self.alternative_product.current_stock > 0