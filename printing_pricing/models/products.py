"""
نماذج أنواع ومقاسات المنتجات التجارية
printing_pricing/models/products.py
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from .base import BaseLookupModel


class ProductType(BaseLookupModel):
    """نموذج أنواع المنتجات والتصنيف التشغيلي للمحرك"""

    ARCHETYPE_CHOICES = [
        ('flyer', _('مطبوع مفرود (كروت / فلاير)')),
        ('catalog', _('مطبوع مع داخلي (كتالوج / بلوك نوت / كتاب)')),
        ('folder', _('مطبوع مع فورمة تكسير (فولدر / علب)')),
        ('invoice', _('دفاتر مكربن (فواتير / إيصالات)')),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("اسم نوع المطبوع"),
        help_text=_("مثال: مطبوع مفرود، كتالوج، فولدر، دفاتر فواتير"),
    )
    base_archetype = models.CharField(
        max_length=20,
        choices=ARCHETYPE_CHOICES,
        default='flyer',
        verbose_name=_("التصنيف التشغيلي للمحرك"),
        help_text=_("يحدد مسار التشغيل وتفكيك التكاليف والخطوات في شاشة التسعير"),
    )

    class Meta:
        db_table = "printing_pricing_producttype"
        verbose_name = _("نوع المطبوع")
        verbose_name_plural = _("أنواع المطبوعات")
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class ProductSize(BaseLookupModel):
    """نموذج مقاسات المطبوعات التجارية (A4, A5, كارت شخصي...)"""

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("اسم المقاس"),
        help_text=_("مثال: A4، A5، كارت شخصي"),
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
        verbose_name=_("الارتفاع (سم)"),
        help_text=_("ارتفاع المنتج بالسنتيمتر"),
    )

    class Meta:
        db_table = "printing_pricing_productsize"
        verbose_name = _("مقاس المطبوع")
        verbose_name_plural = _("مقاسات المطبوعات")
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name} ({self.width}×{self.height} سم)"

    def get_area(self):
        """حساب المساحة بالسنتيمتر المربع"""
        if self.width and self.height:
            return float(self.width * self.height)
        return 0.0

    def get_area_display(self):
        """عرض المساحة بشكل مقروء"""
        area = self.get_area()
        return f"{area:.2f} سم²"


__all__ = [
    'ProductType',
    'ProductSize'
]
