from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.conf import settings

from users.models import User
from client.models import Customer as Client
from supplier.models import Supplier
from product.models import Product

# ==================== النماذج الأساسية للتسعير ====================


class PaperType(models.Model):
    """نموذج أنواع الورق"""

    name = models.CharField(_("اسم نوع الورق"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("نوع الورق")
        verbose_name_plural = _("أنواع الورق")
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaperSize(models.Model):
    """نموذج أحجام الورق"""

    name = models.CharField(_("اسم المقاس"), max_length=100)
    width = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("مقاس الورق")
        verbose_name_plural = _("مقاسات الورق")
        ordering = ["name"]

    def __str__(self):
        from .templatetags.pricing_filters import remove_trailing_zeros

        width_clean = remove_trailing_zeros(self.width)
        height_clean = remove_trailing_zeros(self.height)
        return f"{self.name} ({width_clean}×{height_clean})"


class PaperWeight(models.Model):
    """نموذج أوزان الورق"""

    name = models.CharField(_("اسم الوزن"), max_length=100)
    gsm = models.PositiveIntegerField(
        _("الوزن (جرام)"), validators=[MinValueValidator(50)]
    )
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("وزن الورق")
        verbose_name_plural = _("أوزان الورق")
        ordering = ["gsm"]
        unique_together = ["gsm"]

    def __str__(self):
        return f"{self.name} ({self.gsm} جم)"


# تم حذف التعريفات المكررة - النماذج معرفة في الأسفل


class PrintDirection(models.Model):
    """نموذج اتجاهات الطباعة"""

    name = models.CharField(_("اسم الاتجاه"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("اتجاه الطباعة")
        verbose_name_plural = _("اتجاهات الطباعة")
        ordering = ["name"]

    def __str__(self):
        return self.name


class PrintSide(models.Model):
    """نموذج جوانب الطباعة"""

    name = models.CharField(_("اسم الجانب"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("جانب الطباعة")
        verbose_name_plural = _("جوانب الطباعة")
        ordering = ["id"]

    def __str__(self):
        return self.name


class CoatingType(models.Model):
    """نموذج أنواع التغطية"""

    name = models.CharField(_("اسم نوع التغطية"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("نوع التغطية")
        verbose_name_plural = _("أنواع التغطية")
        ordering = ["name"]

    def __str__(self):
        return self.name


class FinishingType(models.Model):
    """نموذج أنواع خدمات ما بعد الطباعة"""

    name = models.CharField(_("اسم نوع التشطيب"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("نوع التشطيب")
        verbose_name_plural = _("أنواع التشطيب")
        ordering = ["name"]

    def __str__(self):
        return self.name


class PlateSize(models.Model):
    """نموذج أحجام الزنكات"""

    name = models.CharField(_("اسم مقاس الزنك"), max_length=100)
    width = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("مقاس الزنك")
        verbose_name_plural = _("مقاسات الزنكات")
        ordering = ["name"]

    def __str__(self):
        from .templatetags.pricing_filters import remove_trailing_zeros

        width_clean = remove_trailing_zeros(self.width)
        height_clean = remove_trailing_zeros(self.height)
        return f"{self.name} ({width_clean}×{height_clean})"


# تم نقل SupplierService إلى supplier/models.py لتجنب التكرار

# ==================== النماذج المتقدمة ====================
# تم نقل النماذج التالية إلى supplier/models.py لتجنب التكرار:
# - PaperServiceDetails
# - PlateServiceDetails
# - DigitalPrintingDetails
# يجب استخدام النماذج من supplier.models بدلاً من هذه


class VATSetting(models.Model):
    """نموذج إعدادات ضريبة القيمة المضافة"""

    is_enabled = models.BooleanField(_("مفعل"), default=False)
    percentage = models.DecimalField(
        _("النسبة المئوية"), max_digits=5, decimal_places=2, default=Decimal("15.00")
    )
    description = models.TextField(_("الوصف"), blank=True)
    effective_date = models.DateField(_("تاريخ السريان"), auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="vat_settings",
        verbose_name=_("تم الإنشاء بواسطة"),
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("إعداد ضريبة القيمة المضافة")
        verbose_name_plural = _("إعدادات ضريبة القيمة المضافة")
        ordering = ["-created_at"]

    def __str__(self):
        status = _("مفعل") if self.is_enabled else _("معطل")
        return f"ضريبة القيمة المضافة {self.percentage}% - {status}"

    @classmethod
    def get_current_vat(cls):
        """الحصول على إعدادات الضريبة الحالية"""
        return cls.objects.filter(is_enabled=True).first()

    def save(self, *args, **kwargs):
        # إذا كان هذا الإعداد مفعل، قم بتعطيل جميع الإعدادات الأخرى
        if self.is_enabled:
            VATSetting.objects.filter(is_enabled=True).update(is_enabled=False)
        super().save(*args, **kwargs)


class PricingOrder(models.Model):
    """نموذج طلب التسعير الرئيسي"""

    ORDER_TYPES = (
        ("offset", _("أوفست")),
        ("digital", _("ديجيتال")),
    )

    STATUS_CHOICES = (
        ("draft", _("مسودة")),
        ("pending", _("قيد الانتظار")),
        ("approved", _("معتمد")),
        ("rejected", _("مرفوض")),
        ("executed", _("منفذ")),
        ("cancelled", _("ملغي")),
    )

    CLIENT_TYPES = (
        ("regular", _("عميل عادي")),
        ("vip", _("عميل مميز")),
        ("corporate", _("شركة")),
        ("government", _("جهة حكومية")),
    )

    order_number = models.CharField(
        _("رقم الطلب"), max_length=20, unique=True, editable=False
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name=_("العميل"),
    )
    order_type = models.CharField(_("نوع الطلب"), max_length=10, choices=ORDER_TYPES)
    title = models.CharField(_("عنوان الطلب"), max_length=255)
    description = models.TextField(_("وصف الطلب"), blank=True)
    quantity = models.PositiveIntegerField(
        _("الكمية"), validators=[MinValueValidator(1)]
    )

    # تحسينات ربط العملاء
    client_contact_person = models.CharField(
        _("الشخص المسؤول"), max_length=100, blank=True
    )
    client_phone = models.CharField(_("هاتف العميل"), max_length=20, blank=True)
    client_email = models.EmailField(_("بريد العميل"), blank=True)
    client_type = models.CharField(
        _("نوع العميل"), max_length=20, choices=CLIENT_TYPES, default="regular"
    )
    client_notes = models.TextField(_("ملاحظات العميل"), blank=True)

    # ربط بالمنتج (اختياري)
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        related_name="pricing_orders",
        verbose_name=_("المنتج"),
        null=True,
        blank=True,
    )

    # الحقول المشتركة
    has_internal_content = models.BooleanField(
        _("يحتوي على محتوى داخلي"), default=False
    )

    # معلومات المنتج والورق والطباعة
    product_type = models.ForeignKey(
        "ProductType",
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("نوع المنتج"),
        null=True,
        blank=True,
    )
    paper_type = models.ForeignKey(
        PaperType,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("نوع الورق"),
        null=True,
        blank=True,
    )
    product_size = models.ForeignKey(
        "ProductSize",
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("مقاس المنتج"),
        null=True,
        blank=True,
    )
    print_direction = models.ForeignKey(
        PrintDirection,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("اتجاه الطباعة"),
    )
    print_sides = models.ForeignKey(
        PrintSide,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("جوانب الطباعة"),
    )
    colors_front = models.PositiveIntegerField(_("عدد ألوان الوجه الأمامي"), default=4)
    colors_back = models.PositiveIntegerField(_("عدد ألوان الوجه الخلفي"), default=0)

    # تفاصيل إضافية من النظام المرجعي
    paper_weight = models.PositiveIntegerField(_("وزن الورق (جرام)"), default=80)
    custom_width = models.DecimalField(
        _("العرض المخصص (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    custom_height = models.DecimalField(
        _("الطول المخصص (سم)"), max_digits=8, decimal_places=2, null=True, blank=True
    )

    # معلومات المونتاج
    montage_info = models.TextField(_("معلومات المونتاج"), blank=True)

    # معلومات التصميم
    design_price = models.DecimalField(
        _("سعر التصميم"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    internal_design_price = models.DecimalField(
        _("سعر التصميم الداخلي"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # خدمات مابعد الطباعة والتغطية
    coating_type = models.ForeignKey(
        CoatingType,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("نوع التغطية"),
        null=True,
        blank=True,
    )
    coating_service = models.ForeignKey(
        "supplier.SpecializedService",
        on_delete=models.PROTECT,
        related_name="coating_orders",
        verbose_name=_("خدمة التغطية"),
        null=True,
        blank=True,
    )

    # تحسينات ربط الموردين
    primary_supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="primary_orders",
        verbose_name=_("المورد الأساسي"),
        null=True,
        blank=True,
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("المورد"),
        null=True,
        blank=True,
    )
    press = models.CharField(_("نوع الماكينة"), max_length=255, blank=True)
    supplier_notes = models.TextField(_("ملاحظات الموردين"), blank=True)

    # التكاليف والأسعار
    material_cost = models.DecimalField(
        _("تكلفة الخامات"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    printing_cost = models.DecimalField(
        _("تكلفة الطباعة"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    finishing_cost = models.DecimalField(
        _("تكلفة خدمات الطباعة"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    plates_cost = models.DecimalField(
        _("تكلفة الزنكات"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    extra_cost = models.DecimalField(
        _("تكاليف إضافية"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total_cost = models.DecimalField(
        _("إجمالي التكلفة"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    profit_margin = models.DecimalField(
        _("هامش الربح (%)"), max_digits=5, decimal_places=2, default=Decimal("20.00")
    )
    sale_price = models.DecimalField(
        _("سعر البيع"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # حالة الطلب
    is_approved = models.BooleanField(_("معتمد"), default=False)
    is_executed = models.BooleanField(_("منفذ"), default=False)
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="draft"
    )

    # معلومات المستخدم
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_orders",
        verbose_name=_("تم الإنشاء بواسطة"),
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="approved_orders",
        verbose_name=_("تم الاعتماد بواسطة"),
        null=True,
        blank=True,
    )

    # الطوابع الزمنية
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    approved_at = models.DateTimeField(_("تاريخ الاعتماد"), null=True, blank=True)
    executed_at = models.DateTimeField(_("تاريخ التنفيذ"), null=True, blank=True)

    class Meta:
        verbose_name = _("طلب تسعير")
        verbose_name_plural = _("طلبات التسعير")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_number} - {self.client.name} - {self.title}"

    def save(self, *args, **kwargs):
        # إنشاء رقم الطلب إذا كان جديدًا
        if not self.order_number:
            last_order = PricingOrder.objects.order_by("-id").first()
            if last_order:
                last_id = last_order.id
            else:
                last_id = 0
            self.order_number = f"ORD-{last_id + 1:06d}"

        # حساب إجمالي التكلفة
        self.total_cost = (
            self.material_cost
            + self.printing_cost
            + self.finishing_cost
            + self.plates_cost
            + self.extra_cost
        )

        # حساب سعر البيع إذا تم تحديد هامش الربح
        if self.profit_margin > 0:
            self.sale_price = self.total_cost * (1 + (self.profit_margin / 100))

        # تطبيق ضريبة القيمة المضافة إذا كانت مفعلة
        if getattr(settings, "VAT_ENABLED", False):
            vat_rate = getattr(settings, "VAT_PERCENTAGE", 0) / 100
            self.sale_price = self.sale_price * (1 + Decimal(str(vat_rate)))

        super().save(*args, **kwargs)

    def calculate_material_cost(self):
        """حساب تكلفة الخامات"""
        if not self.paper_type or not self.product_size:
            return Decimal("0.00")

        try:
            # البحث عن خدمة الورق من المورد
            from supplier.models import PaperServiceDetails

            paper_service = PaperServiceDetails.objects.filter(
                supplier=self.supplier,
                paper_type=self.paper_type,
                paper_size=self.product_size,
                gsm=80,  # وزن افتراضي
                is_active=True,
            ).first()

            if paper_service:
                # حساب التكلفة حسب الكمية
                sheets_needed = self.quantity
                if self.has_internal_content and hasattr(self, "internal_content"):
                    sheets_needed += self.quantity * self.internal_content.page_count

                cost = sheets_needed * paper_service.price_per_sheet
                self.material_cost = cost
                return cost
        except Exception as e:
            print(f"خطأ في حساب تكلفة المواد: {e}")

        return Decimal("0.00")

    def calculate_printing_cost(self):
        """حساب تكلفة الطباعة"""
        if not self.supplier or self.order_type not in ["offset", "digital"]:
            return Decimal("0.00")

        try:
            if self.order_type == "digital":
                # البحث عن خدمة الطباعة الرقمية
                from supplier.models import DigitalPrintingDetails

                digital_service = DigitalPrintingDetails.objects.filter(
                    supplier=self.supplier,
                    paper_size=self.product_size,
                    color_type="color"
                    if (self.colors_front + self.colors_back) > 1
                    else "bw",
                ).first()

                if digital_service:
                    copies_needed = self.quantity
                    if self.print_sides.name in ["وجهين", "double"]:
                        copies_needed *= 2

                    cost = copies_needed * digital_service.price_per_copy
                    self.printing_cost = cost
                    return cost

            # للطباعة الأوفست - حساب مبسط
            base_cost = Decimal("100.00")  # تكلفة أساسية
            color_multiplier = (self.colors_front + self.colors_back) * Decimal("0.5")
            quantity_discount = Decimal("1.0") - (self.quantity / Decimal("10000.0"))

            cost = (
                base_cost
                * (Decimal("1.0") + color_multiplier)
                * quantity_discount
                * self.quantity
            )
            self.printing_cost = cost
            return cost

        except Exception as e:
            print(f"خطأ في حساب تكلفة الطباعة: {e}")

        return Decimal("0.00")

    def calculate_finishing_cost(self):
        """حساب تكلفة خدمات الطباعة"""
        total_finishing_cost = Decimal("0.00")

        try:
            # جمع تكاليف جميع خدمات التشطيب
            finishing_services = self.finishing_services.all()
            for service in finishing_services:
                total_finishing_cost += service.total_price

            # إضافة تكلفة التغطية إذا كان موجود
            if self.coating_service:
                coating_cost = self.coating_service.unit_price * self.quantity
                total_finishing_cost += coating_cost

            self.finishing_cost = total_finishing_cost
            return total_finishing_cost

        except Exception as e:
            print(f"خطأ في حساب تكلفة التشطيب: {e}")

        return Decimal("0.00")

    def calculate_plates_cost(self):
        """حساب تكلفة الزنكات"""
        if self.order_type != "offset":
            return Decimal("0.00")

        total_plates_cost = Decimal("0.00")

        try:
            # جمع تكاليف جميع الزنكات
            ctp_plates = self.ctp_plates.all()
            for plate in ctp_plates:
                total_plates_cost += plate.total_cost

            self.plates_cost = total_plates_cost
            return total_plates_cost

        except Exception as e:
            print(f"خطأ في حساب تكلفة الزنكات: {e}")

        return Decimal("0.00")

    def calculate_all_costs(self):
        """حساب جميع التكاليف"""
        self.calculate_material_cost()
        self.calculate_printing_cost()
        self.calculate_finishing_cost()
        self.calculate_plates_cost()

        # حساب إجمالي التكلفة
        self.total_cost = (
            self.material_cost
            + self.printing_cost
            + self.finishing_cost
            + self.plates_cost
            + self.extra_cost
        )

        # حساب سعر البيع
        if self.profit_margin > 0:
            self.sale_price = self.total_cost * (1 + (self.profit_margin / 100))

        return self.total_cost

    def get_vat_amount(self):
        """حساب مبلغ ضريبة القيمة المضافة"""
        if getattr(settings, "VAT_ENABLED", False):
            vat_rate = getattr(settings, "VAT_PERCENTAGE", 0) / 100
            return self.sale_price - (self.sale_price / (1 + Decimal(str(vat_rate))))
        return Decimal("0.00")


class InternalContent(models.Model):
    """نموذج المحتوى الداخلي للطلب"""

    order = models.OneToOneField(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="internal_content",
        verbose_name=_("الطلب"),
    )
    paper_type = models.ForeignKey(
        PaperType,
        on_delete=models.PROTECT,
        related_name="internal_contents",
        verbose_name=_("نوع الورق"),
    )
    product_size = models.ForeignKey(
        PaperSize,
        on_delete=models.PROTECT,
        related_name="internal_contents",
        verbose_name=_("مقاس المنتج"),
        null=True,
        blank=True,
    )
    page_count = models.PositiveIntegerField(
        _("عدد الصفحات"), validators=[MinValueValidator(1)]
    )
    print_sides = models.ForeignKey(
        PrintSide,
        on_delete=models.PROTECT,
        related_name="internal_contents",
        verbose_name=_("جوانب الطباعة"),
    )
    colors_front = models.PositiveIntegerField(_("عدد ألوان الوجه الأمامي"), default=4)
    colors_back = models.PositiveIntegerField(_("عدد ألوان الوجه الخلفي"), default=0)
    material_cost = models.DecimalField(
        _("تكلفة الخامات"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    printing_cost = models.DecimalField(
        _("تكلفة الطباعة"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        verbose_name = _("محتوى داخلي")
        verbose_name_plural = _("محتويات داخلية")

    def __str__(self):
        return f"{_('محتوى داخلي')} - {self.order.order_number}"


class OrderFinishing(models.Model):
    """نموذج خدمات الطباعة للطلب"""

    order = models.ForeignKey(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="finishing_services",
        verbose_name=_("الطلب"),
    )
    finishing_type = models.ForeignKey(
        FinishingType,
        on_delete=models.PROTECT,
        related_name="order_services",
        verbose_name=_("نوع خدمات مابعد الطباعة"),
        null=True,
        blank=True,
    )
    supplier_service = models.ForeignKey(
        "supplier.SpecializedService",
        on_delete=models.PROTECT,
        related_name="order_services",
        verbose_name=_("خدمة المورد"),
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(
        _("الكمية"), validators=[MinValueValidator(1)]
    )
    unit_price = models.DecimalField(_("سعر الوحدة"), max_digits=10, decimal_places=2)
    total_price = models.DecimalField(
        _("السعر الإجمالي"), max_digits=12, decimal_places=2
    )
    notes = models.TextField(_("ملاحظات"), blank=True)

    class Meta:
        verbose_name = _("تشطيب الطلب")
        verbose_name_plural = _("تشطيبات الطلب")

    def __str__(self):
        return f"{self.finishing_type.name} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class ExtraExpense(models.Model):
    """نموذج المصاريف الإضافية للطلب"""

    order = models.ForeignKey(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="extra_expenses",
        verbose_name=_("الطلب"),
    )
    name = models.CharField(_("اسم المصروف"), max_length=255)
    description = models.TextField(_("الوصف"), blank=True)
    amount = models.DecimalField(_("المبلغ"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("مصروف إضافي")
        verbose_name_plural = _("مصاريف إضافية")

    def __str__(self):
        return f"{self.name} - {self.order.order_number}"


class CtpPlates(models.Model):
    """نموذج الزنكات (CTP) للطلب"""

    order = models.ForeignKey(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="ctp_plates",
        verbose_name=_("الطلب"),
    )
    is_internal = models.BooleanField(_("للمحتوى الداخلي"), default=False)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="order_plates",
        verbose_name=_("المورد"),
    )
    plate_size = models.ForeignKey(
        PlateSize,
        on_delete=models.PROTECT,
        related_name="order_plates",
        verbose_name=_("مقاس الزنك"),
    )
    plates_count = models.PositiveIntegerField(
        _("عدد الزنكات"), validators=[MinValueValidator(1)]
    )
    plate_price = models.DecimalField(_("سعر الزنك"), max_digits=10, decimal_places=2)
    transportation_cost = models.DecimalField(
        _("تكلفة الانتقالات"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    total_cost = models.DecimalField(
        _("التكلفة الإجمالية"), max_digits=12, decimal_places=2
    )
    notes = models.TextField(_("ملاحظات"), blank=True)

    class Meta:
        verbose_name = _("زنك CTP")
        verbose_name_plural = _("زنكات CTP")

    def __str__(self):
        return (
            f"{_('زنكات')} - {self.order.order_number} - {self.plates_count} {_('زنك')}"
        )

    def save(self, *args, **kwargs):
        # حساب إجمالي التكلفة
        self.total_cost = (
            self.plates_count * self.plate_price
        ) + self.transportation_cost
        super().save(*args, **kwargs)


class OrderComment(models.Model):
    """نموذج تعليقات الطلب"""

    order = models.ForeignKey(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("الطلب"),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="order_comments",
        verbose_name=_("المستخدم"),
    )
    comment = models.TextField(_("التعليق"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("تعليق الطلب")
        verbose_name_plural = _("تعليقات الطلب")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{_('تعليق')} - {self.order.order_number} - {self.user.get_full_name()}"


# ==================== النماذج الجديدة للنظام المستقل ====================


class OrderSupplier(models.Model):
    """نموذج ربط الموردين المتعددين بطلب التسعير"""

    SUPPLIER_ROLES = (
        ("primary", _("أساسي")),
        ("secondary", _("ثانوي")),
        ("backup", _("احتياطي")),
        ("specialist", _("متخصص")),
    )

    SERVICE_TYPES = (
        ("printing", _("طباعة")),
        ("paper", _("ورق")),
        ("finishing", _("تشطيب")),
        ("coating", _("تغطية")),
        ("binding", _("تجليد")),
        ("cutting", _("قص")),
        ("other", _("أخرى")),
    )

    order = models.ForeignKey(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="order_suppliers",
        verbose_name=_("الطلب"),
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="supplier_orders",
        verbose_name=_("المورد"),
    )
    role = models.CharField(
        _("دور المورد"), max_length=20, choices=SUPPLIER_ROLES, default="secondary"
    )
    service_type = models.CharField(
        _("نوع الخدمة"), max_length=20, choices=SERVICE_TYPES
    )

    # تفاصيل الخدمة
    description = models.TextField(_("وصف الخدمة"), blank=True)
    estimated_cost = models.DecimalField(
        _("التكلفة المقدرة"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    quoted_price = models.DecimalField(
        _("السعر المعروض"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # معلومات إضافية
    contact_person = models.CharField(_("الشخص المسؤول"), max_length=100, blank=True)
    phone = models.CharField(_("الهاتف"), max_length=20, blank=True)
    email = models.EmailField(_("البريد الإلكتروني"), blank=True)

    # حالة التعامل
    is_confirmed = models.BooleanField(_("مؤكد"), default=False)
    is_active = models.BooleanField(_("نشط"), default=True)
    notes = models.TextField(_("ملاحظات"), blank=True)

    # تواريخ
    created_at = models.DateTimeField(_("تاريخ الإضافة"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("مورد الطلب")
        verbose_name_plural = _("موردي الطلب")
        unique_together = ["order", "supplier", "service_type"]
        ordering = ["role", "service_type", "supplier__name"]

    def __str__(self):
        return f"{self.order.order_number} - {self.supplier.name} ({self.get_service_type_display()})"


class PricingQuotation(models.Model):
    """نموذج عروض الأسعار المستقلة"""

    STATUS_CHOICES = (
        ("draft", _("مسودة")),
        ("sent", _("مرسل")),
        ("under_review", _("قيد المراجعة")),
        ("accepted", _("مقبول")),
        ("rejected", _("مرفوض")),
        ("expired", _("منتهي الصلاحية")),
        ("cancelled", _("ملغي")),
    )

    SENT_VIA_CHOICES = (
        ("email", _("بريد إلكتروني")),
        ("whatsapp", _("واتساب")),
        ("hand_delivery", _("تسليم يد")),
        ("fax", _("فاكس")),
        ("postal", _("بريد عادي")),
        ("phone", _("هاتف")),
    )

    pricing_order = models.OneToOneField(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="quotation",
        verbose_name=_("طلب التسعير"),
    )
    quotation_number = models.CharField(
        _("رقم العرض"), max_length=20, unique=True, editable=False
    )

    # معلومات العرض
    sent_date = models.DateField(_("تاريخ الإرسال"), null=True, blank=True)
    valid_until = models.DateField(_("صالح حتى"))
    follow_up_date = models.DateField(_("تاريخ المتابعة"), null=True, blank=True)

    # حالة العرض
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="draft"
    )

    # شروط العرض (مستقلة عن الأنظمة الأخرى)
    payment_terms = models.TextField(
        _("شروط الدفع"), default="50% مقدم، 50% عند التسليم"
    )
    delivery_terms = models.TextField(
        _("شروط التسليم"), default="التسليم خلال 7-10 أيام عمل"
    )
    warranty_terms = models.TextField(_("شروط الضمان"), blank=True)
    special_conditions = models.TextField(_("شروط خاصة"), blank=True)

    # معلومات المتابعة
    client_feedback = models.TextField(_("ملاحظات العميل"), blank=True)
    internal_notes = models.TextField(_("ملاحظات داخلية"), blank=True)

    # معلومات الاتصال
    sent_to_person = models.CharField(_("تم الإرسال إلى"), max_length=100, blank=True)
    sent_via = models.CharField(
        _("طريقة الإرسال"), max_length=20, choices=SENT_VIA_CHOICES, default="email"
    )

    # معلومات إضافية
    discount_percentage = models.DecimalField(
        _("نسبة الخصم %"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        _("مبلغ الخصم"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    final_price = models.DecimalField(
        _("السعر النهائي"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # تواريخ مهمة
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    accepted_at = models.DateTimeField(_("تاريخ القبول"), null=True, blank=True)
    rejected_at = models.DateTimeField(_("تاريخ الرفض"), null=True, blank=True)

    # معلومات المستخدم
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_quotations",
        verbose_name=_("تم الإنشاء بواسطة"),
    )

    class Meta:
        verbose_name = _("عرض سعر")
        verbose_name_plural = _("عروض الأسعار")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.quotation_number} - {self.pricing_order.client.name}"

    def save(self, *args, **kwargs):
        # إنشاء رقم العرض إذا كان جديدًا
        if not self.quotation_number:
            last_quotation = PricingQuotation.objects.order_by("-id").first()
            if last_quotation:
                last_id = last_quotation.id
            else:
                last_id = 0
            self.quotation_number = f"QUO-{last_id + 1:06d}"

        # حساب السعر النهائي
        if self.discount_percentage > 0:
            self.discount_amount = self.pricing_order.sale_price * (
                self.discount_percentage / 100
            )

        self.final_price = self.pricing_order.sale_price - self.discount_amount

        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        """التحقق من انتهاء صلاحية العرض"""
        from django.utils import timezone

        return self.valid_until < timezone.now().date() if self.valid_until else False

    @property
    def days_until_expiry(self):
        """عدد الأيام المتبقية حتى انتهاء الصلاحية"""
        from django.utils import timezone

        if self.valid_until:
            delta = self.valid_until - timezone.now().date()
            return delta.days
        return None


class PricingApprovalWorkflow(models.Model):
    """تدفق موافقات التسعير المبسط"""

    name = models.CharField(_("اسم التدفق"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)

    # حدود الموافقة
    min_amount = models.DecimalField(
        _("الحد الأدنى للمبلغ"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    max_amount = models.DecimalField(
        _("الحد الأقصى للمبلغ"), max_digits=12, decimal_places=2, null=True, blank=True
    )

    # المعتمدين
    primary_approver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="primary_approval_workflows",
        verbose_name=_("المعتمد الأساسي"),
    )
    secondary_approver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="secondary_approval_workflows",
        verbose_name=_("المعتمد الثانوي"),
        null=True,
        blank=True,
    )

    # إعدادات الإشعارات
    email_notifications = models.BooleanField(_("إشعارات بريد إلكتروني"), default=True)
    whatsapp_notifications = models.BooleanField(_("إشعارات واتساب"), default=False)

    # إعدادات إضافية
    auto_approve_below_limit = models.BooleanField(
        _("موافقة تلقائية تحت الحد الأدنى"), default=False
    )
    require_both_approvers = models.BooleanField(
        _("يتطلب موافقة المعتمدين"), default=False
    )

    # تواريخ
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_workflows",
        verbose_name=_("تم الإنشاء بواسطة"),
    )

    class Meta:
        verbose_name = _("تدفق الموافقات")
        verbose_name_plural = _("تدفقات الموافقات")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.min_amount} - {self.max_amount or 'لا محدود'})"

    def is_applicable_for_amount(self, amount):
        """التحقق من إمكانية تطبيق التدفق على مبلغ معين"""
        if amount < self.min_amount:
            return False
        if self.max_amount and amount > self.max_amount:
            return False
        return True


class PricingApproval(models.Model):
    """موافقات طلبات التسعير"""

    APPROVAL_LEVELS = (
        ("primary", _("أساسي")),
        ("secondary", _("ثانوي")),
        ("final", _("نهائي")),
    )

    STATUS_CHOICES = (
        ("pending", _("في الانتظار")),
        ("approved", _("معتمد")),
        ("rejected", _("مرفوض")),
        ("cancelled", _("ملغي")),
    )

    NOTIFICATION_METHODS = (
        ("email", _("بريد إلكتروني")),
        ("whatsapp", _("واتساب")),
        ("both", _("كلاهما")),
        ("none", _("بدون إشعار")),
    )

    pricing_order = models.ForeignKey(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="approvals",
        verbose_name=_("طلب التسعير"),
    )
    workflow = models.ForeignKey(
        PricingApprovalWorkflow,
        on_delete=models.CASCADE,
        verbose_name=_("تدفق الموافقة"),
    )

    # معلومات الموافقة
    approver = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name=_("المعتمد")
    )
    approval_level = models.CharField(
        _("مستوى الموافقة"), max_length=20, choices=APPROVAL_LEVELS
    )

    # حالة الموافقة
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="pending"
    )

    # تواريخ ومعلومات
    requested_at = models.DateTimeField(_("تاريخ الطلب"), auto_now_add=True)
    responded_at = models.DateTimeField(_("تاريخ الرد"), null=True, blank=True)
    comments = models.TextField(_("تعليقات"), blank=True)

    # معلومات الإشعار
    notification_sent = models.BooleanField(_("تم إرسال الإشعار"), default=False)
    notification_method = models.CharField(
        _("طريقة الإشعار"), max_length=20, choices=NOTIFICATION_METHODS, default="email"
    )
    notification_sent_at = models.DateTimeField(
        _("تاريخ إرسال الإشعار"), null=True, blank=True
    )

    # معلومات إضافية
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="requested_approvals",
        verbose_name=_("طلب الموافقة"),
    )
    priority = models.CharField(
        _("الأولوية"),
        max_length=10,
        choices=(
            ("low", _("منخفضة")),
            ("normal", _("عادية")),
            ("high", _("عالية")),
            ("urgent", _("عاجلة")),
        ),
        default="normal",
    )

    class Meta:
        verbose_name = _("موافقة التسعير")
        verbose_name_plural = _("موافقات التسعير")
        ordering = ["-requested_at"]
        unique_together = ["pricing_order", "approver", "approval_level"]

    def __str__(self):
        return f"{self.pricing_order.order_number} - {self.approver.get_full_name()} ({self.get_status_display()})"

    def approve(self, comments=""):
        """اعتماد الطلب"""
        from django.utils import timezone

        self.status = "approved"
        self.responded_at = timezone.now()
        self.comments = comments
        self.save()

    def reject(self, comments=""):
        """رفض الطلب"""
        from django.utils import timezone

        self.status = "rejected"
        self.responded_at = timezone.now()
        self.comments = comments
        self.save()

    @property
    def is_overdue(self):
        """التحقق من تأخر الموافقة"""
        from django.utils import timezone
        from datetime import timedelta

        if self.status != "pending":
            return False

        # اعتبار الموافقة متأخرة بعد 3 أيام للعادية، يوم واحد للعاجلة
        if self.priority == "urgent":
            deadline = self.requested_at + timedelta(days=1)
        elif self.priority == "high":
            deadline = self.requested_at + timedelta(days=2)
        else:
            deadline = self.requested_at + timedelta(days=3)

        return timezone.now() > deadline


class PricingReport(models.Model):
    """تقارير التسعير المستقلة"""

    REPORT_TYPES = (
        ("client_analysis", _("تحليل العملاء")),
        ("supplier_comparison", _("مقارنة الموردين")),
        ("pricing_trends", _("اتجاهات التسعير")),
        ("quotation_success", _("معدل نجاح العروض")),
        ("profit_analysis", _("تحليل الربحية")),
        ("monthly_summary", _("ملخص شهري")),
        ("quarterly_summary", _("ملخص ربع سنوي")),
    )

    report_type = models.CharField(
        _("نوع التقرير"), max_length=20, choices=REPORT_TYPES
    )
    title = models.CharField(_("عنوان التقرير"), max_length=200)
    generated_by = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name=_("تم الإنشاء بواسطة")
    )
    generated_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    # فترة التقرير
    date_from = models.DateField(_("من تاريخ"))
    date_to = models.DateField(_("إلى تاريخ"))

    # فلاتر التقرير
    client_filter = models.ForeignKey(
        "client.Customer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("فلتر العميل"),
    )
    supplier_filter = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("فلتر المورد"),
    )
    order_type_filter = models.CharField(
        _("فلتر نوع الطلب"), max_length=10, choices=PricingOrder.ORDER_TYPES, blank=True
    )

    # نتائج التقرير (JSON)
    report_data = models.JSONField(_("بيانات التقرير"), default=dict)
    summary = models.TextField(_("ملخص التقرير"), blank=True)

    # إعدادات التقرير
    is_scheduled = models.BooleanField(_("تقرير مجدول"), default=False)
    schedule_frequency = models.CharField(
        _("تكرار الجدولة"),
        max_length=10,
        choices=(
            ("daily", _("يومي")),
            ("weekly", _("أسبوعي")),
            ("monthly", _("شهري")),
            ("quarterly", _("ربع سنوي")),
        ),
        blank=True,
    )

    class Meta:
        verbose_name = _("تقرير التسعير")
        verbose_name_plural = _("تقارير التسعير")
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.title} - {self.generated_at.strftime('%Y-%m-%d')}"


class PricingKPI(models.Model):
    """مؤشرات الأداء الرئيسية للتسعير"""

    date = models.DateField(_("التاريخ"), unique=True)

    # مؤشرات العروض
    total_quotations = models.PositiveIntegerField(_("إجمالي العروض"), default=0)
    accepted_quotations = models.PositiveIntegerField(_("العروض المقبولة"), default=0)
    rejected_quotations = models.PositiveIntegerField(_("العروض المرفوضة"), default=0)
    pending_quotations = models.PositiveIntegerField(_("العروض المعلقة"), default=0)
    expired_quotations = models.PositiveIntegerField(
        _("العروض المنتهية الصلاحية"), default=0
    )

    # مؤشرات مالية (مستقلة)
    total_quoted_value = models.DecimalField(
        _("إجمالي قيمة العروض"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    accepted_value = models.DecimalField(
        _("قيمة العروض المقبولة"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    rejected_value = models.DecimalField(
        _("قيمة العروض المرفوضة"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    average_order_value = models.DecimalField(
        _("متوسط قيمة الطلب"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # مؤشرات الأداء
    success_rate = models.DecimalField(
        _("معدل النجاح %"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    average_response_time = models.PositiveIntegerField(
        _("متوسط وقت الرد (أيام)"), default=0
    )
    average_profit_margin = models.DecimalField(
        _("متوسط هامش الربح %"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )

    # مؤشرات العملاء والموردين
    new_clients = models.PositiveIntegerField(_("عملاء جدد"), default=0)
    active_clients = models.PositiveIntegerField(_("عملاء نشطين"), default=0)
    active_suppliers = models.PositiveIntegerField(_("موردين نشطين"), default=0)

    # تواريخ
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("مؤشر أداء التسعير")
        verbose_name_plural = _("مؤشرات أداء التسعير")
        ordering = ["-date"]

    def __str__(self):
        return f"مؤشرات {self.date.strftime('%Y-%m-%d')}"

    @classmethod
    def calculate_daily_kpi(cls, date):
        """حساب مؤشرات الأداء ليوم معين"""
        from django.db.models import Count, Sum, Avg

        # الحصول على البيانات لليوم المحدد
        quotations = PricingQuotation.objects.filter(created_at__date=date)
        orders = PricingOrder.objects.filter(created_at__date=date)

        # حساب المؤشرات
        total_quotations = quotations.count()
        accepted_quotations = quotations.filter(status="accepted").count()
        rejected_quotations = quotations.filter(status="rejected").count()
        pending_quotations = quotations.filter(
            status__in=["draft", "sent", "under_review"]
        ).count()
        expired_quotations = quotations.filter(status="expired").count()

        # المؤشرات المالية
        total_quoted_value = quotations.aggregate(total=Sum("final_price"))[
            "total"
        ] or Decimal("0.00")
        accepted_value = quotations.filter(status="accepted").aggregate(
            total=Sum("final_price")
        )["total"] or Decimal("0.00")
        rejected_value = quotations.filter(status="rejected").aggregate(
            total=Sum("final_price")
        )["total"] or Decimal("0.00")
        average_order_value = orders.aggregate(avg=Avg("sale_price"))["avg"] or Decimal(
            "0.00"
        )

        # حساب معدل النجاح
        success_rate = (
            (accepted_quotations / total_quotations * 100)
            if total_quotations > 0
            else Decimal("0.00")
        )

        # متوسط هامش الربح
        average_profit_margin = orders.aggregate(avg=Avg("profit_margin"))[
            "avg"
        ] or Decimal("0.00")

        # العملاء والموردين
        new_clients = orders.values("client").distinct().count()
        active_suppliers = (
            OrderSupplier.objects.filter(created_at__date=date)
            .values("supplier")
            .distinct()
            .count()
        )

        # إنشاء أو تحديث المؤشر
        kpi, created = cls.objects.get_or_create(
            date=date,
            defaults={
                "total_quotations": total_quotations,
                "accepted_quotations": accepted_quotations,
                "rejected_quotations": rejected_quotations,
                "pending_quotations": pending_quotations,
                "expired_quotations": expired_quotations,
                "total_quoted_value": total_quoted_value,
                "accepted_value": accepted_value,
                "rejected_value": rejected_value,
                "average_order_value": average_order_value,
                "success_rate": success_rate,
                "average_profit_margin": average_profit_margin,
                "new_clients": new_clients,
                "active_suppliers": active_suppliers,
            },
        )

        if not created:
            # تحديث البيانات إذا كان المؤشر موجود
            kpi.total_quotations = total_quotations
            kpi.accepted_quotations = accepted_quotations
            kpi.rejected_quotations = rejected_quotations
            kpi.pending_quotations = pending_quotations
            kpi.expired_quotations = expired_quotations
            kpi.total_quoted_value = total_quoted_value
            kpi.accepted_value = accepted_value
            kpi.rejected_value = rejected_value
            kpi.average_order_value = average_order_value
            kpi.success_rate = success_rate
            kpi.average_profit_margin = average_profit_margin
            kpi.new_clients = new_clients
            kpi.active_suppliers = active_suppliers
            kpi.save()

        return kpi


class PricingSupplierSelection(models.Model):
    """نموذج اختيار الموردين للطلب - مستوحى من النظام المرجعي"""

    SELECTION_STATUS_CHOICES = (
        ("pending", _("قيد الانتظار")),
        ("quoted", _("تم تقديم عرض")),
        ("selected", _("مختار")),
        ("rejected", _("مرفوض")),
        ("cancelled", _("ملغي")),
    )

    PRIORITY_CHOICES = (
        ("low", _("منخفضة")),
        ("medium", _("متوسطة")),
        ("high", _("عالية")),
        ("urgent", _("عاجل")),
    )

    # العلاقات الأساسية
    order = models.ForeignKey(
        PricingOrder,
        on_delete=models.CASCADE,
        related_name="supplier_selections",
        verbose_name=_("طلب التسعير"),
    )
    supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.CASCADE,
        related_name="pricing_selections",
        verbose_name=_("المورد"),
    )
    service_tag = models.ForeignKey(
        "supplier.SupplierServiceTag",
        on_delete=models.CASCADE,
        related_name="pricing_selections",
        verbose_name=_("نوع الخدمة"),
        help_text=_("نوع الخدمة المطلوبة من المورد"),
    )

    # معلومات التسعير
    quoted_price = models.DecimalField(
        _("السعر المعروض"),
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text=_("السعر المعروض من المورد"),
    )
    estimated_cost = models.DecimalField(
        _("التكلفة المقدرة"),
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text=_("التكلفة المقدرة للخدمة"),
    )
    final_price = models.DecimalField(
        _("السعر النهائي"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("السعر النهائي المتفق عليه"),
    )

    # حالة الاختيار
    status = models.CharField(
        _("حالة الاختيار"),
        max_length=20,
        choices=SELECTION_STATUS_CHOICES,
        default="pending",
    )
    is_selected = models.BooleanField(
        _("مختار"), default=False, help_text=_("هل تم اختيار هذا المورد للخدمة")
    )
    priority = models.CharField(
        _("الأولوية"), max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )

    # معلومات إضافية
    selection_reason = models.TextField(
        _("سبب الاختيار"), blank=True, help_text=_("سبب اختيار أو رفض هذا المورد")
    )
    notes = models.TextField(
        _("ملاحظات"), blank=True, help_text=_("ملاحظات إضافية حول التعامل مع المورد")
    )

    # معلومات التواصل
    contact_person = models.CharField(
        _("الشخص المسؤول"),
        max_length=255,
        blank=True,
        help_text=_("الشخص المسؤول في المورد لهذا الطلب"),
    )
    contact_phone = models.CharField(_("هاتف التواصل"), max_length=20, blank=True)
    contact_email = models.EmailField(_("بريد التواصل"), blank=True)

    # التواريخ المهمة
    quote_requested_at = models.DateTimeField(
        _("تاريخ طلب العرض"), null=True, blank=True
    )
    quote_received_at = models.DateTimeField(
        _("تاريخ استلام العرض"), null=True, blank=True
    )
    selected_at = models.DateTimeField(_("تاريخ الاختيار"), null=True, blank=True)
    expected_delivery = models.DateField(
        _("تاريخ التسليم المتوقع"), null=True, blank=True
    )

    # معلومات المستخدم
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_supplier_selections",
        verbose_name=_("تم الإنشاء بواسطة"),
    )
    selected_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="selected_supplier_selections",
        verbose_name=_("تم الاختيار بواسطة"),
        null=True,
        blank=True,
    )

    # الطوابع الزمنية
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("اختيار مورد للتسعير")
        verbose_name_plural = _("اختيارات الموردين للتسعير")
        unique_together = ["order", "supplier", "service_tag"]
        ordering = ["-created_at", "priority"]
        indexes = [
            models.Index(fields=["order", "status"]),
            models.Index(fields=["supplier", "is_selected"]),
            models.Index(fields=["service_tag", "status"]),
        ]

    def __str__(self):
        return f"{self.order.order_number} - {self.supplier.name} - {self.service_tag.name}"

    def save(self, *args, **kwargs):
        """حفظ مع تحديث التواريخ"""
        from django.utils import timezone

        # تحديث تاريخ الاختيار عند التحديد
        if self.is_selected and not self.selected_at:
            self.selected_at = timezone.now()
            self.status = "selected"

        # تحديث تاريخ استلام العرض عند تقديم سعر
        if self.quoted_price > 0 and not self.quote_received_at:
            self.quote_received_at = timezone.now()
            if self.status == "pending":
                self.status = "quoted"

        super().save(*args, **kwargs)

    def get_price_difference(self):
        """حساب الفرق بين السعر المعروض والتكلفة المقدرة"""
        if self.quoted_price and self.estimated_cost:
            return self.quoted_price - self.estimated_cost
        return 0

    def get_price_difference_percentage(self):
        """حساب نسبة الفرق في السعر"""
        if self.estimated_cost and self.estimated_cost > 0:
            difference = self.get_price_difference()
            return (difference / self.estimated_cost) * 100
        return 0

    def is_overdue(self):
        """فحص إذا كان الطلب متأخر"""
        from django.utils import timezone

        if self.expected_delivery:
            return timezone.now().date() > self.expected_delivery
        return False


# ==================== نماذج إعدادات ماكينات الأوفست ====================


class OffsetMachineType(models.Model):
    """أنواع ماكينات الأوفست"""

    name = models.CharField(_("اسم نوع الماكينة"), max_length=100, unique=True)
    code = models.CharField(_("كود النوع"), max_length=30, unique=True)
    description = models.TextField(_("الوصف"), blank=True)
    manufacturer = models.CharField(_("الشركة المصنعة"), max_length=100, blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("نوع ماكينة أوفست")
        verbose_name_plural = _("أنواع ماكينات الأوفست")
        ordering = ["manufacturer", "name"]

    def __str__(self):
        return f"{self.manufacturer} - {self.name}" if self.manufacturer else self.name

    def save(self, *args, **kwargs):
        # التأكد من وجود نوع افتراضي واحد فقط
        if self.is_default:
            OffsetMachineType.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class OffsetSheetSize(models.Model):
    """مقاسات ماكينات الأوفست"""

    name = models.CharField(_("اسم المقاس"), max_length=100, unique=True)
    code = models.CharField(_("كود المقاس"), max_length=30, unique=True)
    width_cm = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height_cm = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    is_custom_size = models.BooleanField(_("مقاس مخصص"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("مقاس ماكينة أوفست")
        verbose_name_plural = _("مقاسات ماكينات الأوفست")
        ordering = ["width_cm", "height_cm"]

    def __str__(self):
        from .templatetags.pricing_filters import remove_trailing_zeros
        
        width_clean = remove_trailing_zeros(self.width_cm)
        height_clean = remove_trailing_zeros(self.height_cm)
        return f"{self.name} ({width_clean}×{height_clean} سم)"

    @property
    def area_cm2(self):
        """حساب المساحة بالسنتيمتر المربع"""
        return self.width_cm * self.height_cm

    @property
    def area_m2(self):
        """حساب المساحة بالمتر المربع"""
        return self.area_cm2 / 10000

    def save(self, *args, **kwargs):
        # التأكد من وجود مقاس افتراضي واحد فقط
        if self.is_default:
            OffsetSheetSize.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


# ==================== نماذج إعدادات ماكينات الديجيتال ====================


class DigitalMachineType(models.Model):
    """أنواع ماكينات الطباعة الديجيتال"""

    name = models.CharField(_("اسم نوع الماكينة"), max_length=100, unique=True)
    code = models.CharField(_("كود النوع"), max_length=30, unique=True)
    description = models.TextField(_("الوصف"), blank=True)
    manufacturer = models.CharField(_("الشركة المصنعة"), max_length=100, blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("نوع ماكينة ديجيتال")
        verbose_name_plural = _("أنواع ماكينات الديجيتال")
        ordering = ["manufacturer", "name"]

    def __str__(self):
        return f"{self.manufacturer} - {self.name}" if self.manufacturer else self.name

    def save(self, *args, **kwargs):
        # التأكد من وجود نوع افتراضي واحد فقط
        if self.is_default:
            DigitalMachineType.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class DigitalSheetSize(models.Model):
    """مقاسات ماكينات الطباعة الديجيتال"""

    name = models.CharField(_("اسم المقاس"), max_length=100, unique=True)
    code = models.CharField(_("كود المقاس"), max_length=30, unique=True)
    width_cm = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height_cm = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    is_custom_size = models.BooleanField(_("مقاس مخصص"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "pricing"
        verbose_name = _("مقاس ماكينة ديجيتال")
        verbose_name_plural = _("مقاسات ماكينات الديجيتال")
        ordering = ["width_cm", "height_cm"]

    def __str__(self):
        from .templatetags.pricing_filters import remove_trailing_zeros
        
        width_clean = remove_trailing_zeros(self.width_cm)
        height_clean = remove_trailing_zeros(self.height_cm)
        return f"{self.name} ({width_clean}×{height_clean} سم)"

    @property
    def area_cm2(self):
        """حساب المساحة بالسنتيمتر المربع"""
        return self.width_cm * self.height_cm

    @property
    def area_m2(self):
        """حساب المساحة بالمتر المربع"""
        return self.area_cm2 / 10000

    def save(self, *args, **kwargs):
        # التأكد من وجود مقاس افتراضي واحد فقط
        if self.is_default:
            DigitalSheetSize.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class PaperOrigin(models.Model):
    """نموذج منشأ الورق"""

    name = models.CharField(
        max_length=100,
        verbose_name=_("اسم المنشأ"),
        help_text=_("مثال: مصر، الصين، ألمانيا"),
    )

    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name=_("رمز المنشأ"),
        help_text=_("رمز مختصر للمنشأ مثل EG, CN, DE"),
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("الوصف"),
        help_text=_("وصف اختياري لمنشأ الورق"),
    )

    is_active = models.BooleanField(
        default=True, verbose_name=_("نشط"), help_text=_("هل هذا المنشأ نشط؟")
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name=_("افتراضي"),
        help_text=_("هل هذا هو المنشأ الافتراضي؟"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("تاريخ الإنشاء")
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("تاريخ التحديث"))

    class Meta:
        verbose_name = _("منشأ الورق")
        verbose_name_plural = _("منشأ الورق")
        ordering = ["name"]
        db_table = "pricing_paper_origin"

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        # التأكد من وجود منشأ افتراضي واحد فقط
        if self.is_default:
            PaperOrigin.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


# ==================== نماذج أنواع ومقاسات المنتجات ====================


class ProductType(models.Model):
    """نموذج أنواع المنتجات"""

    name = models.CharField(
        max_length=100,
        verbose_name=_("اسم نوع المنتج"),
        help_text=_("مثال: كتالوج، بروشور، فلاير"),
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("الوصف"),
        help_text=_("وصف اختياري لنوع المنتج"),
    )

    is_active = models.BooleanField(
        default=True, verbose_name=_("نشط"), help_text=_("هل هذا النوع نشط؟")
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name=_("افتراضي"),
        help_text=_("هل هذا هو النوع الافتراضي؟"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("تاريخ الإنشاء")
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("تاريخ التحديث"))

    class Meta:
        verbose_name = _("نوع المنتج")
        verbose_name_plural = _("أنواع المنتجات")
        ordering = ["name"]
        db_table = "pricing_product_type"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # التأكد من وجود نوع افتراضي واحد فقط
        if self.is_default:
            ProductType.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class ProductSize(models.Model):
    """نموذج مقاسات المنتجات"""

    name = models.CharField(
        max_length=100,
        verbose_name=_("اسم المقاس"),
        help_text=_("مثال: A4، A3، فرخ كامل"),
    )

    width = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("العرض (سم)"),
        help_text=_("عرض المقاس بالسنتيمتر"),
    )

    height = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("الطول (سم)"),
        help_text=_("طول المقاس بالسنتيمتر"),
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("الوصف"),
        help_text=_("وصف اختياري للمقاس"),
    )

    is_active = models.BooleanField(
        default=True, verbose_name=_("نشط"), help_text=_("هل هذا المقاس نشط؟")
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name=_("افتراضي"),
        help_text=_("هل هذا هو المقاس الافتراضي؟"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("تاريخ الإنشاء")
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("تاريخ التحديث"))

    class Meta:
        verbose_name = _("مقاس المنتج")
        verbose_name_plural = _("مقاسات المنتجات")
        ordering = ["name"]
        db_table = "pricing_product_size"

    def __str__(self):
        from .templatetags.pricing_filters import remove_trailing_zeros

        width_clean = remove_trailing_zeros(self.width)
        height_clean = remove_trailing_zeros(self.height)
        return f"{self.name} ({width_clean}×{height_clean})"

    def save(self, *args, **kwargs):
        # التأكد من وجود مقاس افتراضي واحد فقط
        if self.is_default:
            ProductSize.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
