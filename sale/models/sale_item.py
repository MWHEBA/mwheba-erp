from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

class SaleItem(models.Model):
    """
    نموذج بنود فاتورة المبيعات
    """
    sale = models.ForeignKey('sale.Sale', on_delete=models.CASCADE, verbose_name=_('الفاتورة'), related_name='items')
    product = models.ForeignKey('product.Product', on_delete=models.PROTECT, verbose_name=_('المنتج'))
    quantity = models.DecimalField(_('الكمية'), max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    unit_price = models.DecimalField(_('سعر الوحدة'), max_digits=12, decimal_places=2)
    discount = models.DecimalField(_('الخصم'), max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(_('الإجمالي'), max_digits=12, decimal_places=2)
    
    class Meta:
        verbose_name = _('بند الفاتورة')
        verbose_name_plural = _('بنود الفاتورة')
    
    def __str__(self):
        return f"{self.product} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        self.total = (self.quantity * self.unit_price) - self.discount
        super().save(*args, **kwargs) 