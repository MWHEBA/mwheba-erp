from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

User = settings.AUTH_USER_MODEL


class PartnerSettings(models.Model):
    """
    إعدادات نظام الشراكة المبسطة
    """
    
    # إعدادات التقارير فقط
    monthly_report_enabled = models.BooleanField(
        _("تقرير شهري مفعل"),
        default=True
    )
    
    # معلومات التحديث
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("حُدث بواسطة")
    )
    
    updated_at = models.DateTimeField(
        _("تاريخ التحديث"),
        auto_now=True
    )
    
    class Meta:
        verbose_name = _("إعدادات الشراكة")
        verbose_name_plural = _("إعدادات الشراكة")
    
    def __str__(self):
        return "إعدادات نظام الشراكة"
    
    @classmethod
    def get_settings(cls):
        """الحصول على الإعدادات الحالية أو إنشاء إعدادات افتراضية"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
    
    def save(self, *args, **kwargs):
        """التأكد من وجود إعداد واحد فقط"""
        self.pk = 1
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """منع حذف الإعدادات"""
        pass


class PartnerPermission(models.Model):
    """
    صلاحيات الشركاء
    """
    
    PERMISSION_TYPES = (
        ('view_dashboard', _('عرض لوحة التحكم')),
        ('create_contribution', _('إنشاء مساهمة')),
        ('create_withdrawal', _('إنشاء سحب')),
        ('view_transactions', _('عرض المعاملات')),
        ('view_balance', _('عرض الرصيد')),
        ('approve_transactions', _('الموافقة على المعاملات')),
        ('cancel_transactions', _('إلغاء المعاملات')),
        ('view_reports', _('عرض التقارير')),
        ('manage_settings', _('إدارة الإعدادات')),
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='partner_permissions',
        verbose_name=_("المستخدم")
    )
    
    permission_type = models.CharField(
        _("نوع الصلاحية"),
        max_length=50,
        choices=PERMISSION_TYPES
    )
    
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='granted_partner_permissions',
        verbose_name=_("منح بواسطة")
    )
    
    granted_at = models.DateTimeField(
        _("تاريخ المنح"),
        auto_now_add=True
    )
    
    is_active = models.BooleanField(
        _("نشط"),
        default=True
    )
    
    class Meta:
        verbose_name = _("صلاحية الشريك")
        verbose_name_plural = _("صلاحيات الشركاء")
        unique_together = ('user', 'permission_type')
        indexes = [
            models.Index(fields=['user', 'permission_type', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_permission_type_display()}"
    
    @classmethod
    def user_has_permission(cls, user, permission_type):
        """التحقق من وجود صلاحية للمستخدم"""
        return cls.objects.filter(
            user=user,
            permission_type=permission_type,
            is_active=True
        ).exists()
    
    @classmethod
    def grant_permission(cls, user, permission_type, granted_by=None):
        """منح صلاحية للمستخدم"""
        permission, created = cls.objects.get_or_create(
            user=user,
            permission_type=permission_type,
            defaults={'granted_by': granted_by}
        )
        if not created and not permission.is_active:
            permission.is_active = True
            permission.granted_by = granted_by
            permission.save()
        return permission
    
    @classmethod
    def revoke_permission(cls, user, permission_type):
        """إلغاء صلاحية من المستخدم"""
        cls.objects.filter(
            user=user,
            permission_type=permission_type
        ).update(is_active=False)


class PartnerAuditLog(models.Model):
    """
    سجل تدقيق معاملات الشريك
    """
    
    ACTION_TYPES = (
        ('create_contribution', _('إنشاء مساهمة')),
        ('create_withdrawal', _('إنشاء سحب')),
        ('approve_transaction', _('الموافقة على معاملة')),
        ('cancel_transaction', _('إلغاء معاملة')),
        ('update_settings', _('تحديث الإعدادات')),
        ('grant_permission', _('منح صلاحية')),
        ('revoke_permission', _('إلغاء صلاحية')),
        ('view_dashboard', _('عرض لوحة التحكم')),
        ('view_reports', _('عرض التقارير')),
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='partner_audit_logs',
        verbose_name=_("المستخدم")
    )
    
    action = models.CharField(
        _("الإجراء"),
        max_length=50,
        choices=ACTION_TYPES
    )
    
    description = models.TextField(
        _("الوصف"),
        help_text=_("وصف تفصيلي للإجراء المنفذ")
    )
    
    ip_address = models.GenericIPAddressField(
        _("عنوان IP"),
        null=True,
        blank=True
    )
    
    user_agent = models.TextField(
        _("معلومات المتصفح"),
        null=True,
        blank=True
    )
    
    # معلومات إضافية (JSON)
    extra_data = models.JSONField(
        _("بيانات إضافية"),
        null=True,
        blank=True,
        help_text=_("بيانات إضافية متعلقة بالإجراء")
    )
    
    timestamp = models.DateTimeField(
        _("الوقت"),
        auto_now_add=True
    )
    
    class Meta:
        verbose_name = _("سجل تدقيق الشريك")
        verbose_name_plural = _("سجلات تدقيق الشريك")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'action', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_action_display()} - {self.timestamp}"
    
    @classmethod
    def log_action(cls, user, action, description, request=None, extra_data=None):
        """تسجيل إجراء في سجل التدقيق"""
        log_data = {
            'user': user,
            'action': action,
            'description': description,
            'extra_data': extra_data
        }
        
        if request:
            log_data.update({
                'ip_address': cls._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500]
            })
        
        return cls.objects.create(**log_data)
    
    @staticmethod
    def _get_client_ip(request):
        """الحصول على عنوان IP الحقيقي للعميل"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
