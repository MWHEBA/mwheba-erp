from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

User = get_user_model()

class SystemSetting(models.Model):
    """
    نموذج إعدادات النظام
    """
    DATA_TYPES = (
        ('string', _('نص')),
        ('integer', _('عدد صحيح')),
        ('decimal', _('عدد عشري')),
        ('boolean', _('منطقي')),
        ('json', _('JSON')),
        ('date', _('تاريخ')),
        ('datetime', _('تاريخ ووقت')),
    )
    
    GROUPS = (
        ('general', _('عام')),
        ('finance', _('مالي')),
        ('inventory', _('مخزون')),
        ('sales', _('مبيعات')),
        ('purchases', _('مشتريات')),
        ('system', _('نظام')),
    )
    
    key = models.CharField(_('المفتاح'), max_length=100, unique=True)
    value = models.TextField(_('القيمة'))
    data_type = models.CharField(_('نوع البيانات'), max_length=20, choices=DATA_TYPES, default='string')
    description = models.TextField(_('الوصف'), blank=True, null=True)
    group = models.CharField(_('المجموعة'), max_length=20, choices=GROUPS, default='general')
    is_active = models.BooleanField(_('نشط'), default=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    
    class Meta:
        verbose_name = _('إعداد النظام')
        verbose_name_plural = _('إعدادات النظام')
        ordering = ['group', 'key']
    
    def __str__(self):
        return f"{self.key} ({self.group})"
    
    @classmethod
    def get_setting(cls, key, default=None):
        """
        الحصول على قيمة إعداد معين
        """
        try:
            setting = cls.objects.get(key=key, is_active=True)
            if setting.data_type == 'integer':
                return int(setting.value)
            elif setting.data_type == 'decimal':
                return float(setting.value)
            elif setting.data_type == 'boolean':
                return setting.value.lower() in ('true', '1', 'yes')
            elif setting.data_type == 'json':
                import json
                return json.loads(setting.value)
            else:
                return setting.value
        except cls.DoesNotExist:
            return default


class DashboardStat(models.Model):
    """
    نموذج إحصائيات لوحة التحكم
    """
    PERIODS = (
        ('daily', _('يومي')),
        ('weekly', _('أسبوعي')),
        ('monthly', _('شهري')),
        ('yearly', _('سنوي')),
        ('current', _('حالي')),
    )
    
    TYPES = (
        ('sales', _('مبيعات')),
        ('purchases', _('مشتريات')),
        ('inventory', _('مخزون')),
        ('finance', _('مالي')),
        ('customers', _('عملاء')),
        ('suppliers', _('موردين')),
        ('users', _('مستخدمين')),
        ('invoices', _('فواتير')),
    )
    
    CHANGE_TYPES = (
        ('increase', _('زيادة')),
        ('decrease', _('نقصان')),
        ('no_change', _('لا تغيير')),
    )
    
    title = models.CharField(_('العنوان'), max_length=100)
    value = models.CharField(_('القيمة'), max_length=100)
    icon = models.CharField(_('الأيقونة'), max_length=50, blank=True, null=True)
    color = models.CharField(_('اللون'), max_length=20, blank=True, null=True)
    order = models.PositiveIntegerField(_('الترتيب'), default=0)
    is_active = models.BooleanField(_('نشط'), default=True)
    period = models.CharField(_('الفترة'), max_length=20, choices=PERIODS, default='monthly')
    type = models.CharField(_('النوع'), max_length=20, choices=TYPES, default='sales')
    change_value = models.CharField(_('قيمة التغيير'), max_length=20, blank=True, null=True)
    change_type = models.CharField(_('نوع التغيير'), max_length=20, choices=CHANGE_TYPES, default='no_change')
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    
    class Meta:
        verbose_name = _('إحصائية لوحة التحكم')
        verbose_name_plural = _('إحصائيات لوحة التحكم')
        ordering = ['order', 'title']
    
    def __str__(self):
        return f"{self.title} ({self.period})"


class Notification(models.Model):
    """
    نموذج الإشعارات
    """
    TYPE_CHOICES = (
        ('info', _('معلومات')),
        ('success', _('نجاح')),
        ('warning', _('تحذير')),
        ('danger', _('خطر')),
        ('inventory_alert', _('تنبيه مخزون')),
        ('payment_received', _('دفعة مستلمة')),
        ('new_invoice', _('فاتورة جديدة')),
        ('return_request', _('طلب إرجاع')),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_('المستخدم'), related_name='notifications')
    title = models.CharField(_('العنوان'), max_length=100)
    message = models.TextField(_('الرسالة'))
    type = models.CharField(_('النوع'), max_length=20, choices=TYPE_CHOICES, default='info')
    is_read = models.BooleanField(_('مقروءة'), default=False)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('إشعار')
        verbose_name_plural = _('الإشعارات')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.user.username})" 