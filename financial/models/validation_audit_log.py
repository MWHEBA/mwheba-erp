"""
نموذج ValidationAuditLog لتسجيل محاولات التحقق من المعاملات المالية المرفوضة
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone


class ValidationAuditLog(models.Model):
    """
    سجل تدقيق محاولات التحقق من المعاملات المالية
    
    يسجل جميع محاولات المعاملات المالية التي فشلت في التحقق من الشروط المحاسبية
    (الحساب المحاسبي، الفترة المحاسبية، إلخ)
    """
    
    VALIDATION_TYPE_CHOICES = (
        ('chart_of_accounts', _('حساب محاسبي')),
        ('accounting_period', _('فترة محاسبية')),
        ('both', _('كلاهما')),
    )
    
    ENTITY_TYPE_CHOICES = (
        ('customer', _('عميل')),
        ('supplier', _('مورد')),
        ('employee', _('موظف')),
        ('product', _('منتج')),
        ('sale', _('مبيعات')),
        ('purchase', _('مشتريات')),
        ('other', _('أخرى')),
    )

    MODULE_CHOICES = (
        ('financial', _('المالية')),
        ('client', _('العملاء')),
        ('product', _('المنتجات')),
        ('sale', _('المبيعات')),
        ('purchase', _('المشتريات')),
        ('supplier', _('الموردين')),
        ('hr', _('الموارد البشرية')),
        ('other', _('أخرى')),
    )
    
    # معلومات المحاولة
    timestamp = models.DateTimeField(
        _('وقت المحاولة'),
        default=timezone.now,
        db_index=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('المستخدم'),
        related_name='validation_attempts'
    )
    
    # معلومات الكيان
    entity_type = models.CharField(
        _('نوع الكيان'),
        max_length=50,
        choices=ENTITY_TYPE_CHOICES,
        db_index=True
    )
    entity_id = models.PositiveIntegerField(_('معرف الكيان'))
    entity_name = models.CharField(_('اسم الكيان'), max_length=200)
    
    # معلومات المعاملة
    transaction_type = models.CharField(
        _('نوع المعاملة'),
        max_length=50,
        null=True,
        blank=True,
        help_text=_('مثل: payment, journal_entry, opening, adjustment')
    )
    transaction_date = models.DateField(
        _('تاريخ المعاملة'),
        null=True,
        blank=True
    )
    transaction_amount = models.DecimalField(
        _('مبلغ المعاملة'),
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # معلومات الفشل
    validation_type = models.CharField(
        _('نوع التحقق'),
        max_length=50,
        choices=VALIDATION_TYPE_CHOICES,
        db_index=True,
        help_text=_('نوع التحقق الذي فشل')
    )
    failure_reason = models.TextField(
        _('سبب الفشل'),
        help_text=_('السبب التقني للفشل (مثل: missing_account, inactive_account)')
    )
    error_message = models.TextField(
        _('رسالة الخطأ'),
        help_text=_('رسالة الخطأ المعروضة للمستخدم بالعربية')
    )
    
    # معلومات إضافية
    module = models.CharField(
        _('الوحدة'),
        max_length=50,
        choices=MODULE_CHOICES,
        db_index=True,
        help_text=_('الوحدة التي حدثت فيها المحاولة')
    )
    view_name = models.CharField(
        _('اسم الـ View'),
        max_length=100,
        null=True,
        blank=True,
        help_text=_('اسم الـ view أو الدالة التي حدثت فيها المحاولة')
    )
    request_path = models.CharField(
        _('مسار الطلب'),
        max_length=500,
        null=True,
        blank=True,
        help_text=_('مسار URL للطلب')
    )
    
    # حالة المحاولة
    is_bypass_attempt = models.BooleanField(
        _('محاولة تجاوز'),
        default=False,
        help_text=_('هل كانت محاولة لتجاوز التحقق')
    )
    bypass_reason = models.TextField(
        _('سبب التجاوز'),
        null=True,
        blank=True,
        help_text=_('سبب محاولة التجاوز إذا كانت موجودة')
    )
    
    # معلومات الطلب
    ip_address = models.GenericIPAddressField(
        _('عنوان IP'),
        null=True,
        blank=True
    )
    user_agent = models.TextField(
        _('متصفح المستخدم'),
        blank=True,
        help_text=_('معلومات المتصفح والجهاز')
    )
    
    class Meta:
        verbose_name = _('سجل تدقيق التحقق')
        verbose_name_plural = _('سجلات تدقيق التحقق')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['entity_type', 'entity_id'], name='val_audit_entity_idx'),
            models.Index(fields=['user', 'timestamp'], name='val_audit_user_idx'),
            models.Index(fields=['validation_type', 'timestamp'], name='val_audit_type_idx'),
            models.Index(fields=['module', 'timestamp'], name='val_audit_module_idx'),
            models.Index(fields=['timestamp'], name='val_audit_time_idx'),
        ]
    
    def __str__(self):
        return f"{self.get_validation_type_display()} - {self.entity_name} - {self.timestamp}"
    
    @classmethod
    def log_validation_failure(
        cls,
        user,
        entity_type: str,
        entity_id: int,
        entity_name: str,
        validation_type: str,
        failure_reason: str,
        error_message: str,
        module: str,
        transaction_type: str = None,
        transaction_date=None,
        transaction_amount=None,
        view_name: str = None,
        request_path: str = None,
        is_bypass_attempt: bool = False,
        bypass_reason: str = None,
        request=None,
    ):
        """
        تسجيل محاولة تحقق فاشلة
        
        Args:
            user: المستخدم الذي حاول المعاملة
            entity_type: نوع الكيان (customer, supplier, etc.)
            entity_id: معرف الكيان
            entity_name: اسم الكيان
            validation_type: نوع التحقق (chart_of_accounts, accounting_period, both)
            failure_reason: السبب التقني للفشل
            error_message: رسالة الخطأ بالعربية
            module: الوحدة (client, financial, etc.)
            transaction_type: نوع المعاملة (اختياري)
            transaction_date: تاريخ المعاملة (اختياري)
            transaction_amount: مبلغ المعاملة (اختياري)
            view_name: اسم الـ view (اختياري)
            request_path: مسار الطلب (اختياري)
            is_bypass_attempt: هل هي محاولة تجاوز (اختياري)
            bypass_reason: سبب التجاوز (اختياري)
            request: كائن الطلب HTTP (اختياري)
            
        Returns:
            ValidationAuditLog: السجل المُنشأ
        """
        # استخراج معلومات الطلب
        ip_address = None
        user_agent = ''
        if request:
            ip_address = cls._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            
            # استخراج مسار الطلب إذا لم يتم توفيره
            if not request_path:
                request_path = request.path
        
        # إنشاء السجل
        log_entry = cls.objects.create(
            user=user,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            validation_type=validation_type,
            failure_reason=failure_reason,
            error_message=error_message,
            module=module,
            transaction_type=transaction_type,
            transaction_date=transaction_date,
            transaction_amount=transaction_amount,
            view_name=view_name,
            request_path=request_path,
            is_bypass_attempt=is_bypass_attempt,
            bypass_reason=bypass_reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        return log_entry
    
    @staticmethod
    def _get_client_ip(request):
        """استخراج عنوان IP الحقيقي للعميل"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @classmethod
    def get_entity_failures(cls, entity_type: str, entity_id: int, days: int = 30):
        """
        الحصول على محاولات الفشل لكيان معين
        
        Args:
            entity_type: نوع الكيان
            entity_id: معرف الكيان
            days: عدد الأيام للبحث (افتراضي 30)
            
        Returns:
            QuerySet: محاولات الفشل
        """
        from datetime import timedelta
        since = timezone.now() - timedelta(days=days)
        
        return cls.objects.filter(
            entity_type=entity_type,
            entity_id=entity_id,
            timestamp__gte=since
        ).order_by('-timestamp')
    
    @classmethod
    def get_user_failures(cls, user, hours: int = 1):
        """
        الحصول على محاولات الفشل لمستخدم معين
        
        Args:
            user: المستخدم
            hours: عدد الساعات للبحث (افتراضي 1)
            
        Returns:
            QuerySet: محاولات الفشل
        """
        from datetime import timedelta
        since = timezone.now() - timedelta(hours=hours)
        
        return cls.objects.filter(
            user=user,
            timestamp__gte=since
        ).order_by('-timestamp')
    
    @classmethod
    def get_recent_failures(cls, hours: int = 24):
        """
        الحصول على محاولات الفشل الأخيرة
        
        Args:
            hours: عدد الساعات للبحث (افتراضي 24)
            
        Returns:
            QuerySet: محاولات الفشل
        """
        from datetime import timedelta
        since = timezone.now() - timedelta(hours=hours)
        
        return cls.objects.filter(
            timestamp__gte=since
        ).order_by('-timestamp')
    
    @classmethod
    def check_repeated_attempts(cls, user, hours: int = 1, threshold: int = 3):
        """
        التحقق من المحاولات المتكررة لمستخدم معين
        
        Args:
            user: المستخدم
            hours: عدد الساعات للبحث (افتراضي 1)
            threshold: عتبة المحاولات (افتراضي 3)
            
        Returns:
            tuple: (has_repeated_attempts: bool, count: int)
        """
        count = cls.get_user_failures(user, hours).count()
        return (count > threshold, count)
    
    @classmethod
    def get_failure_statistics(cls, days: int = 30):
        """
        الحصول على إحصائيات الفشل
        
        Args:
            days: عدد الأيام للبحث (افتراضي 30)
            
        Returns:
            dict: إحصائيات الفشل
        """
        from datetime import timedelta
        from django.db.models import Count
        
        since = timezone.now() - timedelta(days=days)
        failures = cls.objects.filter(timestamp__gte=since)
        
        return {
            'total_failures': failures.count(),
            'by_validation_type': dict(
                failures.values('validation_type')
                .annotate(count=Count('id'))
                .values_list('validation_type', 'count')
            ),
            'by_entity_type': dict(
                failures.values('entity_type')
                .annotate(count=Count('id'))
                .values_list('entity_type', 'count')
            ),
            'by_module': dict(
                failures.values('module')
                .annotate(count=Count('id'))
                .values_list('module', 'count')
            ),
            'by_user': list(
                failures.values('user__username')
                .annotate(count=Count('id'))
                .order_by('-count')[:10]
            ),
        }
