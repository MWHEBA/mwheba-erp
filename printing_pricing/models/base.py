from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal


class BaseModel(models.Model):
    """
    النموذج الأساسي لجميع نماذج وحدة التسعير
    """
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ الإنشاء")
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("تاريخ آخر تحديث")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='%(class)s_created',
        verbose_name=_('أنشأ بواسطة'),
        null=True,
        blank=True
    )
    
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='%(class)s_updated',
        verbose_name=_('حُدث بواسطة'),
        null=True,
        blank=True
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("نشط")
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات")
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        """
        حفظ محسن مع إضافة منطق إضافي
        """
        super().save(*args, **kwargs)


class PricingStatus(models.TextChoices):
    """
    حالات طلبات التسعير
    """
    DRAFT = 'draft', _('مسودة')
    PENDING = 'pending', _('قيد المراجعة')
    APPROVED = 'approved', _('معتمد')
    REJECTED = 'rejected', _('مرفوض')
    COMPLETED = 'completed', _('مكتمل')
    CANCELLED = 'cancelled', _('ملغي')


class OrderType(models.TextChoices):
    """
    أنواع طلبات التسعير
    """
    BOOK = 'book', _('كتاب')
    MAGAZINE = 'magazine', _('مجلة')
    BROCHURE = 'brochure', _('بروشور')
    FLYER = 'flyer', _('فلاير')
    POSTER = 'poster', _('بوستر')
    BUSINESS_CARD = 'business_card', _('كارت شخصي')
    ENVELOPE = 'envelope', _('مظروف')
    LETTERHEAD = 'letterhead', _('ورق رسمي')
    INVOICE = 'invoice', _('فاتورة')
    CATALOG = 'catalog', _('كتالوج')
    CALENDAR = 'calendar', _('تقويم')
    NOTEBOOK = 'notebook', _('دفتر')
    FOLDER = 'folder', _('ملف')
    BOX = 'box', _('علبة')
    LABEL = 'label', _('لصقة')
    STICKER = 'sticker', _('ستيكر')
    BANNER = 'banner', _('بانر')
    OTHER = 'other', _('أخرى')


class CalculationType(models.TextChoices):
    """
    أنواع الحسابات
    """
    MATERIAL = 'material', _('تكلفة المواد')
    PRINTING = 'printing', _('تكلفة الطباعة')
    FINISHING = 'finishing', _('تكلفة التشطيبات')
    DESIGN = 'design', _('تكلفة التصميم')
    TOTAL = 'total', _('التكلفة الإجمالية')


class PriceUnit(models.TextChoices):
    """
    وحدات التسعير
    """
    PIECE = 'piece', _('بالقطعة')
    THOUSAND = 'thousand', _('بالألف')


__all__ = [
    'BaseModel',
    'PricingStatus',
    'OrderType', 
    'CalculationType',
    'PriceUnit'
]
