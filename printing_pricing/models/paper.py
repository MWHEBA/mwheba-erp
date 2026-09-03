"""
نماذج إعدادات وخامات الورق ومقاسات القطع
printing_pricing/models/paper.py
"""
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from .base import BaseLookupModel


class PaperType(BaseLookupModel):
    """نموذج أنواع الورق (كوشيه، طبع، بريستول، دوبلكس...)"""

    override_sheets_per_pack = models.PositiveIntegerField(
        _("سعة رزمة خاصة بالخامة (فرخ)"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=_("سعة خاصة تتجاوز الجراماج (مثل: 100 فرخ للدوبلكس، 100 للستيكر). اتركه فارغاً للاعتماد على سعة الجراماج.")
    )

    class Meta:
        db_table = "printing_pricing_papertype"
        verbose_name = _("نوع الورق")
        verbose_name_plural = _("أنواع الورق")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class PaperSize(BaseLookupModel):
    """نموذج مقاسات الفروخ الخام (70×100، 66×88...)"""

    width = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)

    class Meta:
        db_table = "printing_pricing_papersize"
        verbose_name = _("مقاس الورق")
        verbose_name_plural = _("مقاسات الورق")
        ordering = ["sort_order", "name"]

    def __str__(self):
        from core.templatetags.pricing_filters import remove_trailing_zeros
        width_clean = remove_trailing_zeros(self.width)
        height_clean = remove_trailing_zeros(self.height)
        return f"{self.name} ({width_clean}×{height_clean})"


class PaperWeight(BaseLookupModel):
    """نموذج أوزان الورق والجراماجات (150 جم، 200 جم...)"""

    gsm = models.PositiveIntegerField(
        _("الوزن (جرام)"),
        unique=True,
        validators=[MinValueValidator(50)]
    )
    sheets_per_pack = models.PositiveIntegerField(
        _("سعة الرزمة القياسية (فرخ)"),
        default=250,
        validators=[MinValueValidator(1)],
        help_text=_("عدد الأفرخ القياسي في الرزمة لهذا الجراماج (مثال: 500 للأوزان الخفيفة، 250 للمتوسطة)")
    )

    class Meta:
        db_table = "printing_pricing_paperweight"
        verbose_name = _("وزن الورق")
        verbose_name_plural = _("أوزان الورق")
        ordering = ["gsm"]

    def __str__(self):
        return f"{self.name} ({self.gsm} جم)"


class PaperOrigin(BaseLookupModel):
    """نموذج منشأ الورق (كوري، صيني، إندونيسي...)"""

    code = models.CharField(_("رمز البلد"), max_length=10, unique=True, blank=True, null=True)

    class Meta:
        db_table = "printing_pricing_paperorigin"
        verbose_name = _("منشأ الورق")
        verbose_name_plural = _("مناشئ الورق")
        ordering = ["sort_order", "name"]

    def __str__(self):
        if self.code:
            return f"{self.name} ({self.code})"
        return self.name


class PieceSize(BaseLookupModel):
    """نموذج مقاسات القطع المقصوصة من الفرخ مع حسابات الاستغلال والمساحة"""

    paper_type = models.ForeignKey(
        PaperSize,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="piece_sizes",
        verbose_name=_("مقاس الورق الأساسي"),
        help_text=_("مقاس الورق الأساسي المناسب لهذا المقاس من القطع")
    )
    width = models.DecimalField(_("العرض (سم)"), max_digits=8, decimal_places=2)
    height = models.DecimalField(_("الطول (سم)"), max_digits=8, decimal_places=2)
    pieces_per_sheet = models.PositiveIntegerField(
        _("عدد القطع في الفرخ"),
        blank=True,
        null=True,
        help_text=_("اتركه فارغاً للحساب التلقائي")
    )

    class Meta:
        db_table = "printing_pricing_piecesize"
        verbose_name = _("مقاس القطع")
        verbose_name_plural = _("مقاسات القطع")
        ordering = ["sort_order", "name"]

    def __str__(self):
        from core.templatetags.pricing_filters import remove_trailing_zeros
        width_clean = remove_trailing_zeros(self.width)
        height_clean = remove_trailing_zeros(self.height)
        return f"{self.name} ({width_clean}×{height_clean} سم)"

    def get_area(self):
        """حساب المساحة بالسنتيمتر المربع"""
        if self.width and self.height:
            return float(self.width * self.height)
        return 0.0

    def get_area_display(self):
        """عرض المساحة بشكل مقروء"""
        return f"{self.get_area():.2f} سم²"

    def get_paper_type_display(self):
        """عرض نوع الورق الأساسي"""
        if self.paper_type:
            return self.paper_type.name
        return "عام"

    def calculate_pieces_per_sheet(self):
        """حساب عدد القطع في الفرخ تلقائياً"""
        if not self.paper_type or not self.paper_type.width or not self.paper_type.height:
            return self.pieces_per_sheet
        
        # حساب عدد القطع بناءً على الأبعاد
        pieces_width = int(self.paper_type.width // self.width)
        pieces_height = int(self.paper_type.height // self.height)
        
        # جرب الاتجاه المعكوس أيضاً
        pieces_width_rotated = int(self.paper_type.width // self.height)
        pieces_height_rotated = int(self.paper_type.height // self.width)
        
        normal_pieces = pieces_width * pieces_height
        rotated_pieces = pieces_width_rotated * pieces_height_rotated
        
        return max(normal_pieces, rotated_pieces)

    def get_pieces_per_sheet_display(self):
        """عرض عدد القطع في الفرخ"""
        if self.pieces_per_sheet:
            return f"{self.pieces_per_sheet} قطعة"
        calculated = self.calculate_pieces_per_sheet()
        if calculated:
            return f"{calculated} قطعة (محسوب)"
        return "غير محدد"


__all__ = [
    'PaperType',
    'PaperSize',
    'PaperWeight',
    'PaperOrigin',
    'PieceSize'
]
