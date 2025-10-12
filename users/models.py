from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator


class User(AbstractUser):
    """
    نموذج المستخدم المخصص يوسع نموذج Django الأساسي
    """
    USER_TYPES = (
        ('admin', _('مدير')),
        ('accountant', _('محاسب')),
        ('inventory_manager', _('أمين مخزن')),
        ('sales_rep', _('مندوب مبيعات')),
    )
    
    USER_STATUS = (
        ('active', _('نشط')),
        ('inactive', _('غير نشط')),
    )
    
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message=_("يجب أن يكون رقم الهاتف بالصيغة: '+999999999'. يسمح بـ 15 رقم كحد أقصى.")
    )
    
    email = models.EmailField(_('البريد الإلكتروني'), unique=True)
    phone = models.CharField(_('رقم الهاتف'), validators=[phone_regex], max_length=17, blank=True)
    profile_image = models.ImageField(_('الصورة الشخصية'), upload_to='profile_images', blank=True, null=True)
    user_type = models.CharField(_('نوع المستخدم'), max_length=20, choices=USER_TYPES, default='sales_rep')
    status = models.CharField(_('الحالة'), max_length=10, choices=USER_STATUS, default='active')
    address = models.TextField(_('العنوان'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('مستخدم')
        verbose_name_plural = _('المستخدمين')
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}" if self.first_name and self.last_name else self.username
    
    @property
    def is_admin(self):
        return self.user_type == 'admin'
    
    @property
    def is_accountant(self):
        return self.user_type == 'accountant'
    
    @property
    def is_inventory_manager(self):
        return self.user_type == 'inventory_manager'
    
    @property
    def is_sales_rep(self):
        return self.user_type == 'sales_rep'


class ActivityLog(models.Model):
    """
    سجل نشاطات المستخدمين في النظام
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_('المستخدم'))
    action = models.CharField(_('الإجراء'), max_length=255)
    model_name = models.CharField(_('اسم النموذج'), max_length=100, blank=True, null=True)
    object_id = models.PositiveIntegerField(_('معرف الكائن'), blank=True, null=True)
    timestamp = models.DateTimeField(_('التوقيت'), auto_now_add=True)
    ip_address = models.GenericIPAddressField(_('عنوان IP'), blank=True, null=True)
    user_agent = models.TextField(_('متصفح المستخدم'), blank=True, null=True)
    extra_data = models.JSONField(_('بيانات إضافية'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('سجل النشاطات')
        verbose_name_plural = _('سجلات النشاطات')
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"
