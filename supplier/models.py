from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator

# استيراد نماذج الدفعات
try:
    from .models.payment import SupplierPayment
except ImportError:
    # في حالة عدم وجود الملف، إنشاء نموذج بسيط
    SupplierPayment = None


class SupplierType(models.Model):
    """أنواع الموردين"""

    TYPE_CHOICES = (
        ("paper", _("مخزن ورق")),
        ("offset_printing", _("مطبعة أوفست")),
        ("digital_printing", _("مطبعة ديجيتال")),
        ("finishing", _("خدمات الطباعة")),
        ("plates", _("مكتب فصل")),
        ("packaging", _("تقفيل")),
        ("coating", _("تغطية")),
        ("outdoor", _("أوت دور")),
        ("laser", _("ليزر")),
        ("vip_gifts", _("هدايا VIP")),
        ("other", _("أخرى")),
    )

    name = models.CharField(_("اسم النوع"), max_length=100)
    code = models.CharField(
        _("الرمز"), max_length=20, choices=TYPE_CHOICES, unique=True
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


class SupplierServiceTag(models.Model):
    """نموذج خدمات الموردين للتصفية - مستوحى من النظام المرجعي"""

    SERVICE_CATEGORIES = (
        ("printing", _("طباعة")),
        ("paper", _("ورق")),
        ("finishing", _("تشطيب")),
        ("packaging", _("تقفيل")),
        ("binding", _("تجليد")),
        ("cutting", _("قص")),
        ("coating", _("تغطية")),
        ("digital", _("خدمات رقمية")),
        ("logistics", _("لوجستيات")),
        ("other", _("أخرى")),
    )

    name = models.CharField(
        _("اسم الخدمة"),
        max_length=100,
        unique=True,
        help_text=_("اسم الخدمة المقدمة من المورد"),
    )
    category = models.CharField(
        _("فئة الخدمة"),
        max_length=20,
        choices=SERVICE_CATEGORIES,
        help_text=_("تصنيف الخدمة حسب النوع"),
    )
    description = models.TextField(
        _("وصف الخدمة"), blank=True, help_text=_("وصف تفصيلي للخدمة")
    )
    color_code = models.CharField(
        _("رمز اللون"),
        max_length=7,
        blank=True,
        default="#6c757d",
        help_text=_("لون الخدمة بصيغة HEX مثل #FF5733"),
    )
    icon = models.CharField(
        _("أيقونة"),
        max_length=50,
        blank=True,
        help_text=_("اسم الأيقونة من Font Awesome"),
    )
    display_order = models.PositiveSmallIntegerField(
        _("ترتيب العرض"), default=0, help_text=_("ترتيب عرض الخدمة في القوائم")
    )
    is_active = models.BooleanField(
        _("نشط"), default=True, help_text=_("هل الخدمة متاحة للاستخدام")
    )

    # ربط مع أنواع الموردين
    supplier_types = models.ManyToManyField(
        SupplierType,
        blank=True,
        related_name="service_tags",
        verbose_name=_("أنواع الموردين"),
        help_text=_("أنواع الموردين التي تقدم هذه الخدمة"),
    )

    # معلومات إضافية
    requires_approval = models.BooleanField(
        _("يتطلب موافقة"),
        default=False,
        help_text=_("هل تحتاج هذه الخدمة لموافقة خاصة"),
    )
    estimated_duration = models.PositiveIntegerField(
        _("المدة المقدرة (أيام)"),
        default=1,
        help_text=_("المدة المقدرة لتنفيذ الخدمة بالأيام"),
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("خدمة مورد")
        verbose_name_plural = _("خدمات الموردين")
        ordering = ["category", "display_order", "name"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["display_order"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def get_supplier_types_display(self):
        """الحصول على عرض أنواع الموردين"""
        return ", ".join(
            [supplier_type.name for supplier_type in self.supplier_types.all()]
        )

    def get_suppliers_count(self):
        """عدد الموردين الذين يقدمون هذه الخدمة"""
        return self.suppliers.filter(is_active=True).count()


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
    code = models.CharField(_("كود المورد"), max_length=20, unique=True)
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

    # ربط مع أنواع الموردين الجديدة
    supplier_types = models.ManyToManyField(
        SupplierType,
        blank=True,
        related_name="suppliers",
        verbose_name=_("أنواع المورد"),
    )
    primary_type = models.ForeignKey(
        SupplierType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_suppliers",
        verbose_name=_("النوع الأساسي"),
    )

    # ربط مع خدمات الموردين (من النظام المرجعي)
    service_tags = models.ManyToManyField(
        SupplierServiceTag,
        blank=True,
        related_name="suppliers",
        verbose_name=_("خدمات الموردين"),
        help_text=_("الخدمات التي يقدمها هذا المورد"),
    )

    # حقول نظام التسعير المحسنة
    delivery_time = models.IntegerField(
        _("مدة التسليم"), default=7, help_text=_("مدة التسليم الافتراضية بالأيام")
    )
    min_order_amount = models.DecimalField(
        _("الحد الأدنى للطلب"),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_("الحد الأدنى لمبلغ الطلب"),
    )

    # معلومات إضافية للتسعير
    pricing_notes = models.TextField(
        _("ملاحظات التسعير"), blank=True, help_text=_("ملاحظات خاصة بالتسعير والخدمات")
    )
    payment_terms = models.CharField(
        _("شروط الدفع"), max_length=100, blank=True, help_text=_("شروط الدفع المفضلة")
    )
    discount_policy = models.TextField(
        _("سياسة الخصومات"), blank=True, help_text=_("تفاصيل سياسة الخصومات للمورد")
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

    # تقييم المورد
    supplier_rating = models.DecimalField(
        _("تقييم المورد"),
        max_digits=3,
        decimal_places=1,
        default=0,
        help_text=_("تقييم من 0 إلى 5"),
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
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

    def get_specialized_services_count(self):
        """عدد الخدمات المتخصصة"""
        try:
            return self.specialized_services.filter(is_active=True).count()
        except:
            return 0

    def get_services_by_category(self, category_code):
        """الحصول على خدمات من فئة معينة"""
        try:
            return self.specialized_services.filter(
                category__code=category_code, is_active=True
            )
        except:
            return []

    def has_service_category(self, category_code):
        """التحقق من وجود خدمات من فئة معينة"""
        return self.get_services_by_category(category_code).exists()

    def get_primary_type_display(self):
        """عرض النوع الأساسي للمورد"""
        return self.primary_type.name if self.primary_type else _("غير محدد")

    def get_all_types_display(self):
        """عرض جميع أنواع المورد"""
        return ", ".join([t.name for t in self.supplier_types.all()])

    def supplier_types_display(self):
        """عرض أنواع المورد بتنسيق HTML جميل للجداول"""
        types = self.supplier_types.all()
        if not types:
            return '<span class="text-muted">غير محدد</span>'

        badges = []
        for supplier_type in types:
            badge_html = f'<span class="badge me-1 mb-1" style="background-color: {supplier_type.color}; color: white; font-size: 0.75rem;"><i class="{supplier_type.icon} me-1"></i>{supplier_type.name}</span>'
            badges.append(badge_html)

        return "".join(badges)

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

    def get_best_price_service(self, category_code):
        """الحصول على أفضل سعر في فئة معينة"""
        services = self.get_services_by_category(category_code)
        if not services.exists():
            return None

        return services.order_by("setup_cost").first()

    def get_services_with_price_tiers(self):
        """الحصول على الخدمات التي تستخدم شرائح سعرية"""
        try:
            return self.specialized_services.filter(
                is_active=True, price_tiers__isnull=False
            ).distinct()
        except:
            return []

    def calculate_delivery_cost(self, order_amount):
        """حساب تكلفة التوصيل حسب مبلغ الطلب"""
        # يمكن تخصيص هذه الدالة حسب سياسة كل مورد
        if order_amount >= self.min_order_amount:
            return 0  # توصيل مجاني
        else:
            # تكلفة توصيل افتراضية
            return 50

    def is_available_for_order(self):
        """التحقق من إمكانية الطلب من المورد"""
        return (
            self.is_active
            and self.get_specialized_services_count() > 0
            and self.supplier_types.filter(is_active=True).exists()
        )

    def get_service_categories(self):
        """الحصول على فئات الخدمات المتاحة"""
        try:
            from django.apps import apps

            SupplierServiceCategory = apps.get_model(
                "supplier", "SupplierServiceCategory"
            )
            return SupplierServiceCategory.objects.filter(
                specializedservice__supplier=self,
                specializedservice__is_active=True,
                is_active=True,
            ).distinct()
        except:
            return []


# ========================================
# نماذج الخدمات المتخصصة
# ========================================

# تم حذف SupplierServiceCategory لتجنب التكرار مع SupplierType


class SpecializedService(models.Model):
    """الخدمات المتخصصة للموردين"""

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="specialized_services"
    )
    category = models.ForeignKey(
        SupplierType, on_delete=models.PROTECT, verbose_name=_("فئة الخدمة")
    )
    name = models.CharField(_("اسم الخدمة"), max_length=255)
    description = models.TextField(_("وصف الخدمة"), blank=True)

    # معلومات السعر الأساسية
    setup_cost = models.DecimalField(
        _("تكلفة التجهيز"), max_digits=10, decimal_places=2, default=0
    )

    # معلومات إضافية
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("خدمة متخصصة")
        verbose_name_plural = _("خدمات متخصصة")
        ordering = ["supplier", "category", "name"]

    def __str__(self):
        return f"{self.supplier.name} - {self.name}"

    def get_price_for_quantity(self, quantity):
        """حساب السعر حسب الكمية مع الشرائح السعرية"""
        if not self.price_tiers.filter(is_active=True).exists():
            return 0

        # البحث عن الشريحة المناسبة
        for tier in self.price_tiers.filter(is_active=True).order_by("min_quantity"):
            if quantity >= tier.min_quantity:
                if tier.max_quantity is None or quantity <= tier.max_quantity:
                    return tier.price_per_unit

        # إذا لم توجد شريحة مناسبة، استخدم أول شريحة متاحة
        first_tier = (
            self.price_tiers.filter(is_active=True).order_by("min_quantity").first()
        )
        return first_tier.price_per_unit if first_tier else 0

    def get_total_cost(self, quantity):
        """حساب التكلفة الإجمالية شاملة تكلفة الإعداد"""
        unit_price = self.get_price_for_quantity(quantity)
        return (unit_price * quantity) + self.setup_cost

    def get_applicable_tier(self, quantity):
        """الحصول على الشريحة السعرية المناسبة للكمية"""
        for tier in self.price_tiers.filter(is_active=True).order_by("min_quantity"):
            if quantity >= tier.min_quantity:
                if tier.max_quantity is None or quantity <= tier.max_quantity:
                    return tier
        return None

    def get_discount_percentage(self, quantity):
        """حساب نسبة الخصم للكمية المحددة"""
        tier = self.get_applicable_tier(quantity)
        return tier.discount_percentage if tier else 0

    def has_price_tiers(self):
        """التحقق من وجود شرائح سعرية"""
        return self.price_tiers.filter(is_active=True).exists()

    def get_price_breakdown(self, quantity):
        """تفصيل كامل للسعر والتكاليف"""
        unit_price = self.get_price_for_quantity(quantity)
        subtotal = unit_price * quantity
        setup_cost = self.setup_cost
        total = subtotal + setup_cost
        tier = self.get_applicable_tier(quantity)

        return {
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "setup_cost": setup_cost,
            "total": total,
            "tier": tier,
            "discount_percentage": tier.discount_percentage if tier else 0,
            "savings": 0,  # سيتم حسابها من الشرائح السعرية
        }

    # Properties للأوفست - للتوافق مع Templates
    @property
    def sheet_size(self):
        """مقاس الماكينة للأوفست"""
        if hasattr(self, 'offset_details'):
            return self.offset_details.get_sheet_size_display()
        return ""

    @property
    def machine_type(self):
        """نوع الماكينة للأوفست"""
        if hasattr(self, 'offset_details'):
            return self.offset_details.get_machine_type_display()
        return ""

    @property
    def colors_capacity(self):
        """عدد الألوان للأوفست"""
        if hasattr(self, 'offset_details'):
            return self.offset_details.max_colors
        return 0

    @property
    def impression_cost(self):
        """سعر التراج للأوفست"""
        if hasattr(self, 'offset_details'):
            return self.offset_details.impression_cost_per_1000
        return 0

    @property
    def has_tiers(self):
        """وجود شرائح سعرية"""
        return self.has_price_tiers()


class PaperServiceDetails(models.Model):
    """تفاصيل خدمات الورق"""

    PAPER_TYPE_CHOICES = (
        ("coated", _("كوشيه")),
        ("offset", _("أوفست")),
        ("cardboard", _("كرتون")),
        ("art_paper", _("ورق فني")),
        ("newsprint", _("ورق جرائد")),
    )

    SHEET_SIZE_CHOICES = (
        ("full_70x100", _("فرخ كامل 70×100")),
        ("half_50x70", _("نصف فرخ 50×70")),
        ("quarter_35x50", _("ربع فرخ 35×50")),
        ("a3", _("A3")),
        ("a4", _("A4")),
        ("custom", _("مقاس مخصص")),
    )

    service = models.OneToOneField(
        SpecializedService, on_delete=models.CASCADE, related_name="paper_details"
    )
    paper_type = models.CharField(
        _("نوع الورق"), max_length=100  # إزالة choices للمرونة
    )
    gsm = models.PositiveIntegerField(_("وزن الورق (جرام)"))
    sheet_size = models.CharField(
        _("مقاس الفرخ"), max_length=50  # إزالة choices وزيادة الطول للمرونة
    )

    # أبعاد مخصصة
    custom_width = models.DecimalField(
        _("العرض المخصص (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    custom_height = models.DecimalField(
        _("الارتفاع المخصص (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )

    # معلومات إضافية
    country_of_origin = models.CharField(_("بلد المنشأ"), max_length=100, blank=True)
    brand = models.CharField(_("الماركة"), max_length=100, blank=True)
    price_per_sheet = models.DecimalField(
        _("سعر الفرخ"), max_digits=10, decimal_places=2
    )

    def __str__(self):
        parts = []
        if self.paper_type:
            parts.append(self.paper_type)
        if self.country_of_origin:
            parts.append(self.country_of_origin)
        if self.gsm:
            parts.append(f"{self.gsm}جم")
        if self.sheet_size:
            # استخدام get_sheet_size_display للحصول على العرض المناسب
            size_display = self.get_sheet_size_display()
            parts.append(size_display)
        
        if parts:
            return " - ".join(parts)
        return f"خدمة ورق #{self.id}"

    def get_sheet_size_display(self):
        """عرض مقاس الفرخ مع التنسيق المناسب"""
        if self.sheet_size == "custom" and self.custom_width and self.custom_height:
            from pricing.templatetags.pricing_filters import remove_trailing_zeros
            width_clean = remove_trailing_zeros(self.custom_width)
            height_clean = remove_trailing_zeros(self.custom_height)
            return f"مخصص ({width_clean}×{height_clean} سم)"
        else:
            # التحقق من الأكواد المحددة مسبقاً
            size_display = dict(self.SHEET_SIZE_CHOICES).get(self.sheet_size)
            if size_display:
                return size_display
            
            # إذا كان المقاس مخزون كأرقام، حاول تحويله لاسم مفهوم
            if self.sheet_size:
                # تنظيف الأرقام وإزالة الأصفار
                from pricing.templatetags.pricing_filters import remove_trailing_zeros
                
                # التحقق من المقاسات الشائعة
                if "70" in self.sheet_size and "100" in self.sheet_size:
                    return "فرخ كامل (70×100 سم)"
                elif "50" in self.sheet_size and "70" in self.sheet_size:
                    return "نصف فرخ (50×70 سم)"
                elif "35" in self.sheet_size and "50" in self.sheet_size:
                    return "ربع فرخ (35×50 سم)"
                else:
                    # للمقاسات الأخرى، نظف الأرقام فقط
                    import re
                    # استخراج الأرقام من النص
                    numbers = re.findall(r'\d+\.?\d*', self.sheet_size)
                    if len(numbers) >= 2:
                        width = remove_trailing_zeros(float(numbers[0]))
                        height = remove_trailing_zeros(float(numbers[1]))
                        return f"مقاس ({width}×{height} سم)"
            
            return self.sheet_size

    class Meta:
        verbose_name = _("تفاصيل خدمة ورق")
        verbose_name_plural = _("تفاصيل خدمات الورق")


class DigitalPrintingDetails(models.Model):
    """تفاصيل خدمات الطباعة الديجيتال"""

    MACHINE_TYPE_CHOICES = (
        ("laser_mono", _("ليزر أبيض وأسود")),
        ("laser_color", _("ليزر ملون")),
        ("inkjet_large", _("نفث حبر كبير")),
        ("inkjet_small", _("نفث حبر صغير")),
        ("offset_digital", _("أوفست ديجيتال")),
        ("production_printer", _("طابعة إنتاج")),
    )

    PAPER_HANDLING_CHOICES = (
        ("sheet_fed", _("تغذية أوراق")),
        ("roll_fed", _("تغذية لفائف")),
        ("both", _("كلاهما")),
    )

    PAPER_SIZE_CHOICES = (
        ("a4", _("A4")),
        ("a3", _("A3")),
        ("a3_plus", _("A3+")),
        ("sra3", _("SRA3")),
        ("custom", _("مقاس مخصص")),
    )

    service = models.OneToOneField(
        SpecializedService, on_delete=models.CASCADE, related_name="digital_details"
    )
    machine_type = models.CharField(
        _("نوع الماكينة"), max_length=30, choices=MACHINE_TYPE_CHOICES
    )
    machine_model = models.CharField(_("موديل الماكينة"), max_length=100, blank=True)
    paper_handling = models.CharField(
        _("نوع التغذية"), max_length=20, choices=PAPER_HANDLING_CHOICES
    )
    paper_size = models.CharField(
        _("مقاس الورق"), max_length=20, choices=PAPER_SIZE_CHOICES
    )

    # أسعار الطباعة الأساسية (يمكن تجاوزها بالشرائح السعرية)
    price_per_page_bw = models.DecimalField(
        _("سعر الصفحة أبيض/أسود"), max_digits=10, decimal_places=2
    )
    price_per_page_color = models.DecimalField(
        _("سعر الصفحة ملونة"), max_digits=10, decimal_places=2
    )

    # استخدام الشرائح السعرية
    has_price_tiers = models.BooleanField(
        _("استخدام شرائح سعرية"),
        default=True,
        help_text=_(
            "إذا كان نشطاً، سيتم استخدام الشرائح السعرية بدلاً من الأسعار الثابتة"
        ),
    )

    # إمكانيات الماكينة
    duplex_printing = models.BooleanField(_("طباعة على الوجهين"), default=True)
    variable_data_printing = models.BooleanField(
        _("طباعة بيانات متغيرة"), default=False
    )
    supports_heavy_paper = models.BooleanField(_("يدعم الورق السميك"), default=False)
    max_paper_weight_gsm = models.PositiveIntegerField(
        _("أقصى وزن ورق (جرام)"), default=300
    )

    # معلومات الإنتاج
    pages_per_minute_bw = models.PositiveIntegerField(
        _("صفحة/دقيقة أبيض وأسود"), null=True, blank=True
    )
    pages_per_minute_color = models.PositiveIntegerField(
        _("صفحة/دقيقة ملون"), null=True, blank=True
    )
    setup_time_minutes = models.PositiveIntegerField(
        _("وقت الإعداد (دقائق)"), default=5
    )

    class Meta:
        verbose_name = _("تفاصيل طباعة ديجيتال")
        verbose_name_plural = _("تفاصيل طباعة ديجيتال")


class FinishingServiceDetails(models.Model):
    """تفاصيل خدمات الطباعة"""

    FINISHING_TYPE_CHOICES = (
        ("cutting", _("قص")),
        ("folding", _("طي")),
        ("binding_spiral", _("تجليد حلزوني")),
        ("binding_perfect", _("تجليد كعب")),
        ("lamination", _("تقفيل")),
        ("uv_coating", _("طلاء UV")),
        ("embossing", _("نقش بارز")),
        ("die_cutting", _("تكسير")),
        ("perforation", _("تثقيب")),
        ("stapling", _("تدبيس")),
    )

    CALCULATION_METHOD_CHOICES = (
        ("per_piece", _("بالقطعة")),
        ("per_thousand", _("بالألف")),
        ("per_hour", _("بالساعة")),
        ("per_meter", _("بالمتر")),
    )

    service = models.OneToOneField(
        SpecializedService, on_delete=models.CASCADE, related_name="finishing_details"
    )
    finishing_type = models.CharField(
        _("نوع الخدمة"), max_length=20, choices=FINISHING_TYPE_CHOICES
    )
    calculation_method = models.CharField(
        _("طريقة الحساب"), max_length=20, choices=CALCULATION_METHOD_CHOICES
    )

    # قيود المقاسات
    min_size_cm = models.DecimalField(
        _("أصغر مقاس (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    max_size_cm = models.DecimalField(
        _("أكبر مقاس (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )

    # الأسعار
    price_per_unit = models.DecimalField(
        _("سعر الوحدة"), max_digits=10, decimal_places=2
    )
    setup_time_minutes = models.PositiveIntegerField(
        _("وقت التجهيز (دقائق)"), default=0
    )

    # معلومات التسليم
    turnaround_time_hours = models.PositiveIntegerField(
        _("وقت التسليم (ساعات)"), default=24
    )

    class Meta:
        verbose_name = _("تفاصيل خدمات الطباعة")
        verbose_name_plural = _("تفاصيل خدمات الطباعة")


# ========================================
# نماذج الشرائح السعرية الديناميكية
# ========================================


class ServicePriceTier(models.Model):
    """شرائح سعرية ديناميكية لكل خدمة"""

    service = models.ForeignKey(
        SpecializedService, on_delete=models.CASCADE, related_name="price_tiers"
    )
    tier_name = models.CharField(
        _("اسم الشريحة"), max_length=50, help_text=_("مثال: 1-20، 21-50")
    )
    min_quantity = models.PositiveIntegerField(_("الحد الأدنى للكمية"))
    max_quantity = models.PositiveIntegerField(
        _("الحد الأقصى للكمية"),
        null=True,
        blank=True,
        help_text=_("اتركه فارغاً للكمية المفتوحة"),
    )
    price_per_unit = models.DecimalField(
        _("سعر الوحدة"), max_digits=10, decimal_places=2
    )
    floor_price = models.DecimalField(
        _("السعر للأرضيات"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("السعر الخاص للأرضيات (اختياري)"),
    )
    discount_percentage = models.DecimalField(
        _("نسبة الخصم %"), max_digits=5, decimal_places=2, default=0
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    display_order = models.PositiveIntegerField(_("ترتيب العرض"), default=0)

    class Meta:
        verbose_name = _("شريحة سعرية")
        verbose_name_plural = _("شرائح سعرية")
        ordering = ["service", "display_order", "min_quantity"]
        unique_together = ["service", "min_quantity"]

    def __str__(self):
        from pricing.templatetags.pricing_filters import remove_trailing_zeros
        
        max_qty = self.max_quantity if self.max_quantity else "∞"
        price_clean = remove_trailing_zeros(self.price_per_unit)
        return f"{self.service.name} - {self.min_quantity}-{max_qty}: {price_clean} ج.م"

    def get_quantity_range_display(self):
        """عرض نطاق الكمية"""
        if self.max_quantity:
            return f"{self.min_quantity} - {self.max_quantity}"
        else:
            return f"{self.min_quantity}+"


# ========================================
# نماذج الخدمات المتخصصة الجديدة
# ========================================


class OffsetPrintingDetails(models.Model):
    """تفاصيل خدمات الطباعة الأوفست"""

    # تم إزالة الخيارات الثابتة - يتم جلب البيانات من pricing app فقط

    service = models.OneToOneField(
        SpecializedService, on_delete=models.CASCADE, related_name="offset_details"
    )
    machine_type = models.CharField(
        _("نوع الماكينة"), max_length=30
    )
    sheet_size = models.CharField(
        _("مقاس الفرخ"), max_length=20
    )

    # أبعاد مخصصة
    custom_width_cm = models.DecimalField(
        _("العرض المخصص (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    custom_height_cm = models.DecimalField(
        _("الارتفاع المخصص (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )

    # تكاليف الإعداد
    color_calibration_cost = models.DecimalField(
        _("تكلفة معايرة الألوان"), max_digits=10, decimal_places=2, default=0
    )

    # التسعير بالتراج
    impression_cost_per_1000 = models.DecimalField(
        _("تكلفة الفرخ لكل 1000"), max_digits=10, decimal_places=2
    )
    special_impression_cost = models.DecimalField(
        _("سعر التراج مخصوص"), max_digits=10, decimal_places=2, default=0, blank=True
    )
    break_impression_cost = models.DecimalField(
        _("سعر كسر التراج"), max_digits=10, decimal_places=2, default=0, blank=True
    )

    # إمكانيات الماكينة
    max_colors = models.PositiveIntegerField(_("أقصى عدد ألوان"), default=4)
    has_uv_coating = models.BooleanField(_("طلاء UV"), default=False)
    has_aqueous_coating = models.BooleanField(_("طلاء مائي"), default=False)

    class Meta:
        verbose_name = _("تفاصيل طباعة أوفست")
        verbose_name_plural = _("تفاصيل طباعة أوفست")

    def get_machine_type_display(self):
        """عرض نوع الماكينة من المرجعية"""
        try:
            from printing_pricing.models.settings_models import OffsetMachineType
            machine = OffsetMachineType.objects.filter(code=self.machine_type, is_active=True).first()
            if machine:
                return str(machine)
        except ImportError:
            pass
        return self.machine_type

    def get_sheet_size_display(self):
        """عرض مقاس الماكينة من المرجعية"""
        try:
            from printing_pricing.models.settings_models import OffsetSheetSize
            size = OffsetSheetSize.objects.filter(code=self.sheet_size, is_active=True).first()
            if size:
                return str(size)
        except ImportError:
            pass
        return self.sheet_size

    def get_main_price_display(self):
        """عرض السعر الأساسي"""
        if self.impression_cost_per_1000:
            return f"{self.impression_cost_per_1000} ج.م/1000 تراج"
        return "غير محدد"

    def get_capabilities_display(self):
        """عرض إمكانيات الماكينة"""
        capabilities = []
        capabilities.append(f"{self.max_colors} ألوان")
        if self.has_uv_coating:
            capabilities.append("طلاء UV")
        if self.has_aqueous_coating:
            capabilities.append("طلاء مائي")
        return " - ".join(capabilities)

    def __str__(self):
        return f"{self.get_machine_type_display()} - {self.get_sheet_size_display()}"


class PlateServiceDetails(models.Model):
    """تفاصيل خدمات مكتب الفصل (الزنكات)"""

    # تم إزالة PLATE_SIZE_CHOICES - يتم جلب البيانات من pricing app
    PLATE_TYPE_CHOICES = (
        ("positive", _("زنك موجب")),
        ("negative", _("زنك سالب")),
        ("thermal", _("زنك حراري")),
        ("uv", _("زنك UV")),
    )

    service = models.OneToOneField(
        SpecializedService, on_delete=models.CASCADE, related_name="plate_details"
    )
    plate_size = models.CharField(
        _("مقاس الزنك"), max_length=50  # زيادة الطول لاستيعاب القيم الجديدة
    )

    # أبعاد مخصصة
    custom_width_cm = models.DecimalField(
        _("العرض المخصص (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    custom_height_cm = models.DecimalField(
        _("الارتفاع المخصص (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )

    # التسعير
    price_per_plate = models.DecimalField(
        _("سعر الزنك الواحد"), max_digits=10, decimal_places=2
    )
    set_price = models.DecimalField(
        _("سعر الطقم (4 زنكات)"), max_digits=10, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = _("تفاصيل خدمة زنكات")
        verbose_name_plural = _("تفاصيل خدمات الزنكات")


class OutdoorPrintingDetails(models.Model):
    """تفاصيل خدمات الأوت دور"""

    MATERIAL_TYPE_CHOICES = (
        ("vinyl", _("فينيل")),
        ("banner", _("بنر")),
        ("mesh", _("شبك")),
        ("canvas", _("كانفاس")),
        ("backlit", _("باك لايت")),
        ("one_way_vision", _("ون واي فيجن")),
        ("adhesive_vinyl", _("فينيل لاصق")),
    )

    PRINTING_TYPE_CHOICES = (
        ("digital_large_format", _("طباعة رقمية كبيرة")),
        ("eco_solvent", _("إيكو سولفنت")),
        ("latex", _("لاتكس")),
        ("uv", _("UV")),
    )

    service = models.OneToOneField(
        SpecializedService, on_delete=models.CASCADE, related_name="outdoor_details"
    )
    material_type = models.CharField(
        _("نوع المادة"), max_length=30, choices=MATERIAL_TYPE_CHOICES
    )
    printing_type = models.CharField(
        _("نوع الطباعة"), max_length=30, choices=PRINTING_TYPE_CHOICES
    )

    # أقصى مقاسات
    max_width_cm = models.DecimalField(
        _("أقصى عرض (سم)"), max_digits=8, decimal_places=2
    )
    max_height_cm = models.DecimalField(
        _("أقصى ارتفاع (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )

    # التسعير
    price_per_sqm = models.DecimalField(
        _("سعر المتر المربع"), max_digits=10, decimal_places=2
    )
    min_order_sqm = models.DecimalField(
        _("الحد الأدنى (متر مربع)"), max_digits=8, decimal_places=2, default=1
    )

    # خدمات إضافية
    includes_hemming = models.BooleanField(_("يشمل الحياكة"), default=False)
    hemming_cost_per_meter = models.DecimalField(
        _("تكلفة الحياكة للمتر"), max_digits=10, decimal_places=2, default=0
    )
    includes_grommets = models.BooleanField(_("يشمل الحلقات"), default=False)
    grommet_cost_each = models.DecimalField(
        _("تكلفة الحلقة الواحدة"), max_digits=10, decimal_places=2, default=0
    )

    # معلومات التسليم
    production_time_days = models.PositiveIntegerField(
        _("وقت الإنتاج (أيام)"), default=3
    )
    includes_installation = models.BooleanField(_("يشمل التركيب"), default=False)
    installation_cost_per_sqm = models.DecimalField(
        _("تكلفة التركيب للمتر المربع"), max_digits=10, decimal_places=2, default=0
    )

    class Meta:
        verbose_name = _("تفاصيل أوت دور")
        verbose_name_plural = _("تفاصيل أوت دور")


class LaserServiceDetails(models.Model):
    """تفاصيل خدمات الليزر"""

    LASER_TYPE_CHOICES = (
        ("co2", _("CO2 ليزر")),
        ("fiber", _("فايبر ليزر")),
        ("diode", _("دايود ليزر")),
    )

    MATERIAL_TYPE_CHOICES = (
        ("wood", _("خشب")),
        ("acrylic", _("أكريليك")),
        ("mdf", _("MDF")),
        ("cardboard", _("كرتون")),
        ("leather", _("جلد")),
        ("fabric", _("قماش")),
        ("metal", _("معدن")),
        ("glass", _("زجاج")),
        ("plastic", _("بلاستيك")),
    )

    SERVICE_TYPE_CHOICES = (
        ("cutting", _("قص")),
        ("engraving", _("حفر")),
        ("marking", _("تعليم")),
        ("cutting_engraving", _("قص وحفر")),
    )

    service = models.OneToOneField(
        SpecializedService, on_delete=models.CASCADE, related_name="laser_details"
    )
    laser_type = models.CharField(
        _("نوع الليزر"), max_length=20, choices=LASER_TYPE_CHOICES
    )
    service_type = models.CharField(
        _("نوع الخدمة"), max_length=30, choices=SERVICE_TYPE_CHOICES
    )
    material_type = models.CharField(
        _("نوع المادة"), max_length=20, choices=MATERIAL_TYPE_CHOICES
    )

    # قيود المقاسات
    max_width_cm = models.DecimalField(
        _("أقصى عرض (سم)"), max_digits=8, decimal_places=2
    )
    max_height_cm = models.DecimalField(
        _("أقصى ارتفاع (سم)"), max_digits=8, decimal_places=2
    )
    max_thickness_mm = models.DecimalField(
        _("أقصى سمك (مم)"), max_digits=6, decimal_places=2
    )

    # التسعير
    price_per_minute = models.DecimalField(
        _("سعر الدقيقة"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    price_per_cm = models.DecimalField(
        _("سعر السنتيمتر"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    price_per_piece = models.DecimalField(
        _("سعر القطعة"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    setup_cost = models.DecimalField(
        _("تكلفة الإعداد"), max_digits=10, decimal_places=2, default=0
    )

    # معلومات إضافية
    min_order_value = models.DecimalField(
        _("الحد الأدنى للطلب"), max_digits=10, decimal_places=2, default=0
    )
    turnaround_time_hours = models.PositiveIntegerField(
        _("وقت التسليم (ساعات)"), default=24
    )

    class Meta:
        verbose_name = _("تفاصيل خدمة ليزر")
        verbose_name_plural = _("تفاصيل خدمات الليزر")


class VIPGiftDetails(models.Model):
    """تفاصيل خدمات الهدايا المميزة"""

    GIFT_CATEGORY_CHOICES = (
        ("corporate", _("هدايا شركات")),
        ("promotional", _("هدايا دعائية")),
        ("awards", _("جوائز وتكريمات")),
        ("luxury", _("هدايا فاخرة")),
        ("personalized", _("هدايا مخصصة")),
        ("tech", _("هدايا تقنية")),
        ("accessories", _("إكسسوارات")),
    )

    CUSTOMIZATION_TYPE_CHOICES = (
        ("engraving", _("حفر")),
        ("printing", _("طباعة")),
        ("embossing", _("نقش بارز")),
        ("embroidery", _("تطريز")),
        ("laser_cutting", _("قص ليزر")),
        ("packaging", _("تقفيل")),
    )

    service = models.OneToOneField(
        SpecializedService, on_delete=models.CASCADE, related_name="vip_gift_details"
    )
    gift_category = models.CharField(
        _("فئة الهدية"), max_length=30, choices=GIFT_CATEGORY_CHOICES
    )
    customization_type = models.CharField(
        _("نوع التخصيص"), max_length=30, choices=CUSTOMIZATION_TYPE_CHOICES
    )

    # معلومات المنتج
    product_name = models.CharField(_("اسم المنتج"), max_length=200)
    product_description = models.TextField(_("وصف المنتج"), blank=True)
    brand = models.CharField(_("الماركة"), max_length=100, blank=True)
    country_of_origin = models.CharField(_("بلد المنشأ"), max_length=100, blank=True)

    # التسعير
    base_price = models.DecimalField(
        _("السعر الأساسي"), max_digits=10, decimal_places=2
    )
    customization_cost = models.DecimalField(
        _("تكلفة التخصيص"), max_digits=10, decimal_places=2, default=0
    )
    packaging_cost = models.DecimalField(
        _("تكلفة التغطية"), max_digits=10, decimal_places=2, default=0
    )

    # قيود الطلب
    min_order_quantity = models.PositiveIntegerField(_("الحد الأدنى للكمية"), default=1)
    max_customization_chars = models.PositiveIntegerField(
        _("أقصى عدد أحرف للتخصيص"), null=True, blank=True
    )

    # معلومات التسليم
    production_time_days = models.PositiveIntegerField(
        _("وقت الإنتاج (أيام)"), default=7
    )
    includes_gift_box = models.BooleanField(_("يشمل علبة هدايا"), default=True)
    includes_certificate = models.BooleanField(_("يشمل شهادة"), default=False)

    # خدمات إضافية
    includes_delivery = models.BooleanField(_("يشمل التوصيل"), default=False)
    delivery_cost = models.DecimalField(
        _("تكلفة التوصيل"), max_digits=10, decimal_places=2, default=0
    )
    includes_setup_service = models.BooleanField(_("يشمل خدمة الإعداد"), default=False)
    setup_service_cost = models.DecimalField(
        _("تكلفة خدمة الإعداد"), max_digits=10, decimal_places=2, default=0
    )

    class Meta:
        verbose_name = _("تفاصيل هدايا VIP")
        verbose_name_plural = _("تفاصيل هدايا VIP")
