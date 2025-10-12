from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from django.urls import reverse


class PurchaseOrder(models.Model):
    """
    نموذج أمر الشراء
    """
    STATUS_CHOICES = (
        ('draft', _('مسودة')),
        ('confirmed', _('مؤكد')),
        ('received', _('مستلم')),
        ('cancelled', _('ملغي')),
    )
    
    number = models.CharField(_('رقم أمر الشراء'), max_length=20, unique=True)
    date = models.DateField(_('تاريخ الأمر'))
    supplier = models.ForeignKey('supplier.Supplier', on_delete=models.PROTECT, 
                               verbose_name=_('المورد'), related_name='purchase_orders')
    warehouse = models.ForeignKey('product.Warehouse', on_delete=models.PROTECT,
                                verbose_name=_('المستودع'), related_name='purchase_orders')
    expected_date = models.DateField(_('التاريخ المتوقع للاستلام'), blank=True, null=True)
    status = models.CharField(_('الحالة'), max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(_('ملاحظات'), blank=True, null=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 verbose_name=_('أنشئ بواسطة'), related_name='purchase_orders_created')
    
    class Meta:
        verbose_name = _('أمر شراء')
        verbose_name_plural = _('أوامر الشراء')
        ordering = ['-date', '-number']
    
    def __str__(self):
        return f"{self.number} - {self.supplier} - {self.date}"
        
    def get_absolute_url(self):
        """
        ترجع URL لعرض تفاصيل أمر الشراء
        """
        return reverse('purchase:purchase_order_detail', kwargs={'pk': self.pk})


class PurchaseOrderItem(models.Model):
    """
    نموذج بنود أمر الشراء
    """
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, 
                                      verbose_name=_('أمر الشراء'), related_name='items')
    product = models.ForeignKey('product.Product', on_delete=models.PROTECT, verbose_name=_('المنتج'))
    quantity = models.IntegerField(_('الكمية'), validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(_('سعر الوحدة'), max_digits=12, decimal_places=2)
    received_quantity = models.IntegerField(_('الكمية المستلمة'), default=0)
    notes = models.TextField(_('ملاحظات'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('بند أمر الشراء')
        verbose_name_plural = _('بنود أمر الشراء')
    
    def __str__(self):
        return f"{self.product} x {self.quantity}"
    
    @property
    def total(self):
        return self.quantity * self.unit_price
    
    @property
    def pending_quantity(self):
        return self.quantity - self.received_quantity 