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


class BaseLookupModel(BaseModel):
    """
    النموذج الأساسي المجرد لجميع جداول التكويد والإعدادات في وحدة التسعير
    يوفر الحقول القياسية (الاسم، الوصف، الترتيب، النشاط، الافتراضي) مع تطبيق مبدأ DRY
    """
    name = models.CharField(
        _("الاسم"),
        max_length=100,
        help_text=_("اسم العنصر أو الإعداد")
    )
    description = models.TextField(
        _("الوصف"),
        blank=True,
        null=True,
        help_text=_("وصف توضيحي اختياري")
    )
    sort_order = models.PositiveIntegerField(
        _("الترتيب"),
        default=0,
        help_text=_("ترتيب الظهور في القوائم المنسدلة")
    )
    is_default = models.BooleanField(
        _("افتراضي"),
        default=False,
        help_text=_("هل هذا هو العنصر الافتراضي؟")
    )

    class Meta:
        abstract = True
        ordering = ['sort_order', 'name', 'id']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """
        حفظ مع إدارة حصرية العنصر الافتراضي
        """
        super().save(*args, **kwargs)
        if self.is_default and self.pk:
            self.__class__.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)


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
    أنواع طلبات التسعير الورقية
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
    NOTEBOOK = 'notebook', _('دفتر / بلوك نوت')
    FOLDER = 'folder', _('فولدر / ملف')
    BOX = 'box', _('علبة كرتون خفيفة')
    LABEL = 'label', _('لصقة')
    STICKER = 'sticker', _('شيت ستيكر')


class CalculationType(models.TextChoices):
    """
    أنواع الحسابات الورقية
    """
    MATERIAL = 'material', _('تكلفة المواد والورق')
    PRINTING = 'printing', _('تكلفة الطباعة')
    FINISHING = 'finishing', _('تكلفة خدمات الطباعة والتشطيب')
    DESIGN = 'design', _('تكلفة التصميم')
    TOTAL = 'total', _('التكلفة الإجمالية')


class PriceUnit(models.TextChoices):
    """
    وحدات التسعير الورقية
    """
    PIECE = 'piece', _('بالقطعة')
    THOUSAND = 'thousand', _('بالألف')
    SHEET = 'sheet', _('بالفرخ / شيت')
    PACKAGE = 'package', _('بالباكدج')


__all__ = [
    'BaseModel',
    'BaseLookupModel',
    'PricingStatus',
    'OrderType', 
    'CalculationType',
    'PriceUnit'
]

