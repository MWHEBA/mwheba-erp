from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from django.urls import reverse

class PurchaseReturn(models.Model):
    """
    نموذج مرتجع المشتريات
    """
    RETURN_STATUSES = (
        ('draft', _('مسودة')),
        ('confirmed', _('مؤكد')),
        ('cancelled', _('ملغي')),
    )
    
    number = models.CharField(_('رقم المرتجع'), max_length=20, unique=True)
    date = models.DateField(_('تاريخ المرتجع'))
    purchase = models.ForeignKey('purchase.Purchase', on_delete=models.PROTECT,
                             verbose_name=_('فاتورة المشتريات'), related_name='returns')
    warehouse = models.ForeignKey('product.Warehouse', on_delete=models.PROTECT,
                              verbose_name=_('المستودع'), related_name='purchase_returns')
    subtotal = models.DecimalField(_('المجموع الفرعي'), max_digits=12, decimal_places=2)
    discount = models.DecimalField(_('الخصم'), max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(_('الضريبة'), max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(_('الإجمالي'), max_digits=12, decimal_places=2)
    status = models.CharField(_('الحالة'), max_length=20, choices=RETURN_STATUSES, default='draft')
    notes = models.TextField(_('ملاحظات'), blank=True, null=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 verbose_name=_('أنشئ بواسطة'), related_name='purchase_returns_created')
    
    class Meta:
        verbose_name = _('مرتجع مشتريات')
        verbose_name_plural = _('مرتجعات المشتريات')
        ordering = ['-date', '-number']
    
    def __str__(self):
        return f"{self.number} - {self.purchase.number} - {self.date}"
    
    def get_absolute_url(self):
        """
        ترجع URL لعرض تفاصيل مرتجع المشتريات
        """
        return reverse('purchase:purchase_return_detail', kwargs={'pk': self.pk})
    
    def save(self, *args, **kwargs):
        if not self.number:
            # الحصول على الرقم التسلسلي
            from product.models import SerialNumber
            
            # البحث عن آخر رقم مستخدم
            last_return = PurchaseReturn.objects.order_by('-number').first()
            if last_return:
                try:
                    last_number = int(last_return.number.replace('PRET', ''))
                except ValueError:
                    last_number = 0
            else:
                last_number = 0
            
            # إنشاء أو تحديث الرقم التسلسلي
            serial = SerialNumber.objects.get_or_create(
                document_type='purchase_return',
                year=timezone.now().year,
                defaults={
                    'prefix': 'PRET',
                    'last_number': last_number
                }
            )[0]
            
            # توليد الرقم الجديد
            self.number = serial.get_next_number()
        
        super().save(*args, **kwargs)


class PurchaseReturnItem(models.Model):
    """
    نموذج بند مرتجع المشتريات
    """
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE,
                                   verbose_name=_('مرتجع المشتريات'), related_name='items')
    purchase_item = models.ForeignKey('purchase.PurchaseItem', on_delete=models.PROTECT,
                                 verbose_name=_('بند المشتريات'), related_name='return_items')
    product = models.ForeignKey('product.Product', on_delete=models.PROTECT,
                              verbose_name=_('المنتج'), related_name='purchase_return_items')
    quantity = models.PositiveIntegerField(_('الكمية'))
    unit_price = models.DecimalField(_('سعر الوحدة'), max_digits=12, decimal_places=2)
    discount = models.DecimalField(_('الخصم'), max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(_('الإجمالي'), max_digits=12, decimal_places=2)
    reason = models.CharField(_('سبب الإرجاع'), max_length=255)
    
    class Meta:
        verbose_name = _('بند مرتجع مشتريات')
        verbose_name_plural = _('بنود مرتجعات المشتريات')
    
    def __str__(self):
        return f"{self.purchase_return.number} - {self.product.name}"
    
    def save(self, *args, **kwargs):
        if not self.total:
            self.total = (self.quantity * self.unit_price) - self.discount
        super().save(*args, **kwargs)