"""
نماذج إعدادات التسعير - printing_pricing/models/settings_models.py
تحتوي على جميع النماذج الأساسية لإعدادات نظام التسعير
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.conf import settings
from users.models import User


# ==================== نماذج إعدادات الورق ====================

class PaperType(models.Model):
    """نموذج أنواع الورق"""

    name = models.CharField(_("اسم نوع الورق"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "printing_pricing"
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
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("مقاس الورق")
        verbose_name_plural = _("مقاسات الورق")
        ordering = ["name"]

    def __str__(self):
        from core.templatetags.pricing_filters import remove_trailing_zeros

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
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("وزن الورق")
        verbose_name_plural = _("أوزان الورق")
        ordering = ["gsm"]
        unique_together = ["gsm"]

    def __str__(self):
        return f"{self.name} ({self.gsm} جم)"


class PaperOrigin(models.Model):
    """نموذج منشأ الورق"""

    name = models.CharField(_("اسم المنشأ"), max_length=100)
    code = models.CharField(_("رمز البلد"), max_length=5, unique=True)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("منشأ الورق")
        verbose_name_plural = _("مناشئ الورق")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


# ==================== نماذج إعدادات الطباعة ====================

class PrintDirection(models.Model):
    """نموذج اتجاهات الطباعة"""

    name = models.CharField(_("اسم الاتجاه"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
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
        app_label = "printing_pricing"
        verbose_name = _("جانب الطباعة")
        verbose_name_plural = _("جوانب الطباعة")
        ordering = ["id"]

    def __str__(self):
        return self.name


# ==================== نماذج إعدادات التشطيب ====================

class CoatingType(models.Model):
    """نموذج أنواع التغطية"""

    name = models.CharField(_("اسم نوع التغطية"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
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
        app_label = "printing_pricing"
        verbose_name = _("نوع التشطيب")
        verbose_name_plural = _("أنواع التشطيب")
        ordering = ["name"]

    def __str__(self):
        return self.name


# ==================== نماذج مقاسات القطع والزنكات ====================

class PieceSize(models.Model):
    """نموذج مقاسات القطع"""

    name = models.CharField(_("اسم المقاس"), max_length=100)
    width = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    paper_type = models.ForeignKey(
        'PaperSize',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("مقاس الورق الأساسي"),
        help_text=_("مقاس الورق الأساسي المناسب لهذا المقاس من القطع"),
        related_name="piece_sizes"
    )
    pieces_per_sheet = models.PositiveIntegerField(
        _("عدد القطع في الفرخ"),
        null=True,
        blank=True,
        help_text=_("عدد القطع التي يمكن قطعها من فرخ واحد من مقاس الورق الأساسي")
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("مقاس القطع")
        verbose_name_plural = _("مقاسات القطع")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.width}×{self.height} سم)"

    def get_area(self):
        """حساب المساحة بالسنتيمتر المربع"""
        return float(self.width * self.height)
    
    def get_area_display(self):
        """عرض المساحة بشكل مقروء"""
        area = self.get_area()
        return f"{area} سم²"
    
    def get_paper_type_display(self):
        """عرض نوع الورق الأساسي"""
        if self.paper_type:
            return self.paper_type.name
        return "عام"
    
    def calculate_pieces_per_sheet(self):
        """حساب عدد القطع في الفرخ تلقائياً"""
        if not self.paper_type:
            return None
        
        # حساب عدد القطع بناءً على الأبعاد
        pieces_width = int(self.paper_type.width // self.width)
        pieces_height = int(self.paper_type.height // self.height)
        
        # جرب الاتجاه المعكوس أيضاً
        pieces_width_rotated = int(self.paper_type.width // self.height)
        pieces_height_rotated = int(self.paper_type.height // self.width)
        
        # اختر الطريقة التي تعطي أكبر عدد قطع
        normal_pieces = pieces_width * pieces_height
        rotated_pieces = pieces_width_rotated * pieces_height_rotated
        
        return max(normal_pieces, rotated_pieces)
    
    def get_pieces_per_sheet_display(self):
        """عرض عدد القطع في الفرخ"""
        if self.pieces_per_sheet:
            return f"{self.pieces_per_sheet} قطعة"
        elif self.paper_type:
            calculated = self.calculate_pieces_per_sheet()
            if calculated:
                return f"{calculated} قطعة (محسوب)"
        return "غير محدد"


class PlateSize(models.Model):
    """نموذج أحجام الزنكات"""

    name = models.CharField(_("اسم مقاس الزنك"), max_length=100)
    width = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("مقاس الزنك")
        verbose_name_plural = _("مقاسات الزنكات")
        ordering = ["name"]

    def __str__(self):
        from core.templatetags.pricing_filters import remove_trailing_zeros

        width_clean = remove_trailing_zeros(self.width)
        height_clean = remove_trailing_zeros(self.height)
        return f"{self.name} ({width_clean}×{height_clean})"


# ==================== نماذج أنواع ومقاسات المنتجات ====================

class ProductType(models.Model):
    """نموذج أنواع المنتجات"""

    name = models.CharField(
        max_length=100,
        verbose_name=_("اسم نوع المنتج"),
        help_text=_("مثال: كتاب، مجلة، بروشور، كتالوج"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("الوصف"),
        help_text=_("وصف تفصيلي لنوع المنتج"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("نشط"),
        help_text=_("هل نوع المنتج هذا نشط ومتاح للاستخدام؟"),
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("افتراضي"),
        help_text=_("هل هذا هو نوع المنتج الافتراضي؟"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("تاريخ الإنشاء")
    )

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("نوع المنتج")
        verbose_name_plural = _("أنواع المنتجات")
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductSize(models.Model):
    """نموذج مقاسات المنتجات"""

    name = models.CharField(
        max_length=100,
        verbose_name=_("اسم المقاس"),
        help_text=_("مثال: A4، A5، مقاس مخصص"),
    )
    width = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("العرض (سم)"),
        help_text=_("عرض المنتج بالسنتيمتر"),
    )
    height = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("الطول (سم)"),
        help_text=_("طول المنتج بالسنتيمتر"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("الوصف"),
        help_text=_("وصف إضافي للمقاس"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("نشط"),
        help_text=_("هل هذا المقاس نشط ومتاح للاستخدام؟"),
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("افتراضي"),
        help_text=_("هل هذا هو المقاس الافتراضي؟"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("تاريخ الإنشاء")
    )

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("مقاس المنتج")
        verbose_name_plural = _("مقاسات المنتجات")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.width}×{self.height} سم)"

    def get_area(self):
        """حساب المساحة بالسنتيمتر المربع"""
        return float(self.width * self.height)

    def get_area_display(self):
        """عرض المساحة بشكل مقروء"""
        area = self.get_area()
        return f"{area:.2f} سم²"


# ==================== نماذج إعدادات ضريبة القيمة المضافة ====================

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
        related_name="printing_pricing_vat_settings",
        verbose_name=_("تم الإنشاء بواسطة"),
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
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


# ==================== نماذج إعدادات الماكينات ====================

class OffsetMachineType(models.Model):
    """نموذج أنواع ماكينات الأوفست"""

    name = models.CharField(_("اسم نوع الماكينة"), max_length=100)
    code = models.CharField(_("رمز الماكينة"), max_length=20, unique=True, blank=True, null=True)
    manufacturer = models.CharField(_("الشركة المصنعة"), max_length=100, blank=True)
    description = models.TextField(_("الوصف"), blank=True)
    max_sheet_size = models.CharField(_("أقصى مقاس فرخ"), max_length=50, blank=True)
    colors_capacity = models.PositiveIntegerField(_("عدد الألوان"), default=4)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("نوع ماكينة أوفست")
        verbose_name_plural = _("أنواع ماكينات الأوفست")
        ordering = ["name"]

    def __str__(self):
        return self.name


class OffsetSheetSize(models.Model):
    """نموذج مقاسات ماكينات الأوفست"""

    name = models.CharField(_("اسم المقاس"), max_length=100)
    code = models.CharField(_("رمز المقاس"), max_length=20, unique=True, blank=True, null=True)
    width_cm = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height_cm = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    description = models.TextField(_("الوصف"), blank=True)
    machine_type = models.ForeignKey(
        OffsetMachineType,
        on_delete=models.CASCADE,
        related_name="sheet_sizes",
        verbose_name=_("نوع الماكينة"),
        null=True,
        blank=True
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    is_custom_size = models.BooleanField(_("مقاس مخصص"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("مقاس ماكينة أوفست")
        verbose_name_plural = _("مقاسات ماكينات الأوفست")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.width_cm}×{self.height_cm})"


class DigitalMachineType(models.Model):
    """نموذج أنواع ماكينات الديجيتال"""

    name = models.CharField(_("اسم نوع الماكينة"), max_length=100)
    code = models.CharField(_("رمز الماكينة"), max_length=20, unique=True, blank=True, null=True)
    manufacturer = models.CharField(_("الشركة المصنعة"), max_length=100, blank=True)
    description = models.TextField(_("الوصف"), blank=True)
    max_sheet_size = models.CharField(_("أقصى مقاس فرخ"), max_length=50, blank=True)
    print_quality = models.CharField(_("جودة الطباعة"), max_length=50, blank=True)
    is_color = models.BooleanField(_("طباعة ملونة"), default=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("نوع ماكينة ديجيتال")
        verbose_name_plural = _("أنواع ماكينات الديجيتال")
        ordering = ["name"]

    def __str__(self):
        return self.name


class DigitalSheetSize(models.Model):
    """نموذج مقاسات ماكينات الديجيتال"""

    name = models.CharField(_("اسم المقاس"), max_length=100)
    code = models.CharField(_("رمز المقاس"), max_length=20, unique=True, blank=True, null=True)
    width_cm = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height_cm = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    description = models.TextField(_("الوصف"), blank=True)
    machine_type = models.ForeignKey(
        DigitalMachineType,
        on_delete=models.CASCADE,
        related_name="sheet_sizes",
        verbose_name=_("نوع الماكينة"),
        null=True,
        blank=True
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(_("افتراضي"), default=False)
    is_custom_size = models.BooleanField(_("مقاس مخصص"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("مقاس ماكينة ديجيتال")
        verbose_name_plural = _("مقاسات ماكينات الديجيتال")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.width_cm}×{self.height_cm})"


class SystemSetting(models.Model):
    """نموذج إعدادات النظام العامة"""

    key = models.CharField(_("مفتاح الإعداد"), max_length=100, unique=True)
    value = models.TextField(_("القيمة"))
    description = models.TextField(_("الوصف"), blank=True)
    category = models.CharField(_("الفئة"), max_length=50, default="general")
    is_active = models.BooleanField(_("نشط"), default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("تم الإنشاء بواسطة"),
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        app_label = "printing_pricing"
        verbose_name = _("إعداد النظام")
        verbose_name_plural = _("إعدادات النظام")
        ordering = ["category", "key"]

    def __str__(self):
        return f"{self.key}: {self.value[:50]}"

    @classmethod
    def get_setting(cls, key, default=None):
        """الحصول على قيمة إعداد معين"""
        try:
            setting = cls.objects.get(key=key, is_active=True)
            return setting.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_setting(cls, key, value, description="", category="general", user=None):
        """تعيين قيمة إعداد معين"""
        setting, created = cls.objects.update_or_create(
            key=key,
            defaults={
                'value': value,
                'description': description,
                'category': category,
                'created_by': user,
                'is_active': True
            }
        )
        return setting


