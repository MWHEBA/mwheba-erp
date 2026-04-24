from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

User = get_user_model()


class SystemSetting(models.Model):
    """
    نموذج إعدادات النظام
    """

    DATA_TYPES = (
        ("string", _("نص")),
        ("integer", _("عدد صحيح")),
        ("decimal", _("عدد عشري")),
        ("boolean", _("منطقي")),
        ("json", _("JSON")),
        ("date", _("تاريخ")),
        ("datetime", _("تاريخ ووقت")),
    )

    GROUPS = (
        ("general", _("عام")),
        ("finance", _("مالي")),
        ("inventory", _("مخزون")),
        ("sales", _("مبيعات")),
        ("purchases", _("مشتريات")),
        ("hr", _("موارد بشرية")),
        ("system", _("نظام")),
        ("whatsapp", _("واتساب")),
    )

    key = models.CharField(_("المفتاح"), max_length=100, unique=True)
    value = models.TextField(_("القيمة"))
    data_type = models.CharField(
        _("نوع البيانات"), max_length=20, choices=DATA_TYPES, default="string"
    )
    description = models.TextField(_("الوصف"), blank=True, null=True)
    group = models.CharField(
        _("المجموعة"), max_length=20, choices=GROUPS, default="general"
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("إعداد النظام")
        verbose_name_plural = _("إعدادات النظام")
        ordering = ["group", "key"]

    def __str__(self):
        return f"{self.key} ({self.group})"

    @classmethod
    def get_setting(cls, key, default=None):
        """
        الحصول على قيمة إعداد معين
        """
        try:
            setting = cls.objects.get(key=key, is_active=True)
            if setting.data_type == "integer":
                return int(setting.value)
            elif setting.data_type == "decimal":
                return float(setting.value)
            elif setting.data_type == "boolean":
                return setting.value.lower() in ("true", "1", "yes")
            elif setting.data_type == "json":
                import json

                return json.loads(setting.value)
            else:
                return setting.value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def get_currency_symbol(cls):
        """
        الحصول على رمز العملة من الإعدادات
        """
        return cls.get_setting('default_currency', 'ج.م')
    
    @classmethod
    def get_site_name(cls):
        """
        الحصول على اسم الموقع من الإعدادات
        """
        return cls.get_setting('site_name', 'موهبة ERP')
    
    @classmethod
    def get_light_logo(cls):
        """
        الحصول على مسار اللوجو الفاتح من الإعدادات
        """
        return cls.get_setting('light_logo', 'img/logo-mini.png')
    
    @classmethod
    def get_timezone(cls):
        """
        الحصول على المنطقة الزمنية من الإعدادات
        """
        return cls.get_setting('timezone', 'Africa/Cairo')


class DashboardStat(models.Model):
    """
    نموذج إحصائيات لوحة التحكم
    """

    PERIODS = (
        ("daily", _("يومي")),
        ("weekly", _("أسبوعي")),
        ("monthly", _("شهري")),
        ("yearly", _("سنوي")),
        ("current", _("حالي")),
    )

    TYPES = (
        ("sales", _("مبيعات")),
        ("purchases", _("مشتريات")),
        ("inventory", _("مخزون")),
        ("finance", _("مالي")),
        ("customers", _("عملاء")),
        ("suppliers", _("موردين")),
        ("users", _("مستخدمين")),
        ("invoices", _("فواتير")),
    )

    CHANGE_TYPES = (
        ("increase", _("زيادة")),
        ("decrease", _("نقصان")),
        ("no_change", _("لا تغيير")),
    )

    title = models.CharField(_("العنوان"), max_length=100)
    value = models.CharField(_("القيمة"), max_length=100)
    icon = models.CharField(_("الأيقونة"), max_length=50, blank=True, null=True)
    color = models.CharField(_("اللون"), max_length=20, blank=True, null=True)
    order = models.PositiveIntegerField(_("الترتيب"), default=0)
    is_active = models.BooleanField(_("نشط"), default=True)
    period = models.CharField(
        _("الفترة"), max_length=20, choices=PERIODS, default="monthly"
    )
    type = models.CharField(_("النوع"), max_length=20, choices=TYPES, default="sales")
    change_value = models.CharField(
        _("قيمة التغيير"), max_length=20, blank=True, null=True
    )
    change_type = models.CharField(
        _("نوع التغيير"), max_length=20, choices=CHANGE_TYPES, default="no_change"
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("إحصائية لوحة التحكم")
        verbose_name_plural = _("إحصائيات لوحة التحكم")
        ordering = ["order", "title"]

    def __str__(self):
        return f"{self.title} ({self.period})"


class Notification(models.Model):
    """
    نموذج الإشعارات
    """

    TYPE_CHOICES = (
        # أنواع عامة
        ("info", _("معلومات")),
        ("success", _("نجاح")),
        ("warning", _("تحذير")),
        ("danger", _("خطر")),
        
        # المخزون والمنتجات
        ("inventory_alert", _("تنبيه مخزون")),
        ("product_expiry", _("انتهاء صلاحية منتج")),
        ("stock_transfer", _("نقل مخزون")),
        
        # المبيعات
        ("new_sale", _("مبيعات جديدة")),
        ("sale_payment", _("دفعة مبيعات")),
        ("sale_return", _("إرجاع مبيعات")),
        
        # المشتريات
        ("new_purchase", _("مشتريات جديدة")),
        ("purchase_payment", _("دفعة مشتريات")),
        ("purchase_return", _("إرجاع مشتريات")),
        
        # المالية
        ("payment_received", _("دفعة مستلمة")),
        ("payment_made", _("دفعة مسددة")),
        ("new_invoice", _("فاتورة جديدة")),
        
        # الموارد البشرية
        ("hr_leave_request", _("طلب إجازة")),
        ("hr_attendance", _("حضور وانصراف")),
        ("hr_payroll", _("رواتب")),
        ("hr_contract", _("عقد موظف")),
        
        # أخرى
        ("return_request", _("طلب إرجاع")),
        ("system_alert", _("تنبيه نظام")),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("المستخدم"),
        related_name="notifications",
    )
    title = models.CharField(_("العنوان"), max_length=100)
    message = models.TextField(_("الرسالة"))
    type = models.CharField(
        _("النوع"), max_length=20, choices=TYPE_CHOICES, default="info"
    )
    is_read = models.BooleanField(_("مقروءة"), default=False)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    
    # حقول الربط بالكائنات
    link_url = models.CharField(_("رابط"), max_length=255, blank=True, null=True, help_text="الرابط المباشر للصفحة المتعلقة بالإشعار")
    related_model = models.CharField(_("النموذج المرتبط"), max_length=50, blank=True, null=True, help_text="مثل: Sale, Purchase, Product")
    related_id = models.PositiveIntegerField(_("معرف الكائن المرتبط"), blank=True, null=True)

    class Meta:
        verbose_name = _("إشعار")
        verbose_name_plural = _("الإشعارات")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user.username})"
    
    def get_link_url(self):
        """
        الحصول على رابط الإشعار
        """
        if self.link_url:
            return self.link_url
        
        # إنشاء رابط تلقائي بناءً على النموذج المرتبط
        if self.related_model and self.related_id:
            from django.urls import reverse
            try:
                if self.related_model == 'Sale':
                    # return reverse('sale:sale_detail', kwargs={'pk': self.related_id})
                    return "#"  # تم تعطيل المبيعات مؤقتاً
                elif self.related_model == 'Purchase':
                    return reverse('purchase:purchase_detail', kwargs={'pk': self.related_id})
                elif self.related_model == 'Product':
                    return reverse('product:product_detail', kwargs={'pk': self.related_id})
            except:
                pass
        
        return None
    
    def get_icon(self):
        """
        الحصول على أيقونة الإشعار من المصدر الموحد
        """
        from .notification_icons import get_notification_icon
        return get_notification_icon(self.type)


class NotificationPreference(models.Model):
    """
    نموذج تفضيلات الإشعارات للمستخدم
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("المستخدم"),
        related_name="notification_preferences"
    )
    
    # ==================== أنواع الإشعارات ====================
    enable_inventory_alerts = models.BooleanField(
        _("تنبيهات المخزون"),
        default=True,
        help_text=_("تنبيهات المخزون المنخفض ونفاذ المنتجات")
    )
    enable_invoice_notifications = models.BooleanField(
        _("إشعارات الفواتير"),
        default=True,
        help_text=_("فواتير المبيعات والمشتريات الجديدة")
    )
    enable_payment_notifications = models.BooleanField(
        _("إشعارات الدفعات"),
        default=True,
        help_text=_("الدفعات المستلمة والمسددة")
    )
    enable_return_notifications = models.BooleanField(
        _("إشعارات الإرجاع"),
        default=True,
        help_text=_("طلبات إرجاع المبيعات والمشتريات")
    )
    enable_customer_notifications = models.BooleanField(
        _("إشعارات العملاء"),
        default=False,
        help_text=_("عملاء جدد وتحديثات العملاء")
    )
    enable_product_notifications = models.BooleanField(
        _("إشعارات المنتجات"),
        default=False,
        help_text=_("منتجات جديدة وتحديثات المنتجات")
    )
    enable_user_notifications = models.BooleanField(
        _("إشعارات المستخدمين"),
        default=False,
        help_text=_("مستخدمين جدد وتحديثات المستخدمين")
    )
    enable_system_notifications = models.BooleanField(
        _("إشعارات النظام"),
        default=True,
        help_text=_("إشعارات النظام والتحديثات المهمة")
    )
    
    # ==================== طرق الإشعار ====================
    notify_in_app = models.BooleanField(
        _("داخل النظام"),
        default=True,
        help_text=_("عرض الإشعارات داخل النظام")
    )
    notify_email = models.BooleanField(
        _("البريد الإلكتروني"),
        default=False,
        help_text=_("إرسال إشعارات عبر البريد الإلكتروني")
    )
    email_for_notifications = models.EmailField(
        _("البريد الإلكتروني للإشعارات"),
        blank=True,
        null=True,
        help_text=_("البريد الإلكتروني المستخدم لإرسال الإشعارات")
    )
    notify_sms = models.BooleanField(
        _("رسائل SMS"),
        default=False,
        help_text=_("إرسال إشعارات عبر رسائل SMS")
    )
    phone_for_notifications = models.CharField(
        _("رقم الهاتف للإشعارات"),
        max_length=20,
        blank=True,
        null=True,
        help_text=_("رقم الهاتف المستخدم لإرسال الإشعارات")
    )
    notify_whatsapp = models.BooleanField(
        _("واتساب"),
        default=False,
        help_text=_("إرسال إشعارات للعملاء عبر واتساب")
    )
    
    # ==================== جدولة التنبيهات ====================
    inventory_check_frequency = models.CharField(
        _("تكرار فحص المخزون"),
        max_length=20,
        choices=[
            ('hourly', _('كل ساعة')),
            ('3hours', _('كل 3 ساعات')),
            ('6hours', _('كل 6 ساعات')),
            ('daily', _('يومياً')),
        ],
        default='6hours'
    )
    invoice_check_frequency = models.CharField(
        _("تكرار فحص الفواتير"),
        max_length=20,
        choices=[
            ('daily', _('يومياً')),
            ('3days', _('كل 3 أيام')),
            ('weekly', _('أسبوعياً')),
        ],
        default='daily'
    )
    send_daily_summary = models.BooleanField(
        _("إرسال ملخص يومي"),
        default=False,
        help_text=_("إرسال ملخص يومي بجميع الإشعارات")
    )
    daily_summary_time = models.TimeField(
        _("وقت الملخص اليومي"),
        default='09:00',
        help_text=_("الوقت المفضل لإرسال الملخص اليومي")
    )
    
    # ==================== حدود التنبيهات ====================
    alert_on_minimum_stock = models.BooleanField(
        _("تنبيه عند الحد الأدنى"),
        default=True,
        help_text=_("تنبيه عند وصول المخزون للحد الأدنى")
    )
    alert_on_half_minimum = models.BooleanField(
        _("تنبيه عند 50% من الحد الأدنى"),
        default=True,
        help_text=_("تنبيه عند وصول المخزون لـ 50% من الحد الأدنى")
    )
    alert_on_out_of_stock = models.BooleanField(
        _("تنبيه عند نفاذ المخزون"),
        default=True,
        help_text=_("تنبيه عند نفاذ المخزون تماماً")
    )
    invoice_due_days_before = models.IntegerField(
        _("التنبيه قبل الاستحقاق بـ (أيام)"),
        default=3,
        help_text=_("عدد الأيام قبل استحقاق الفاتورة للتنبيه")
    )
    alert_on_invoice_due = models.BooleanField(
        _("تنبيه عند الاستحقاق"),
        default=True,
        help_text=_("تنبيه عند استحقاق الفاتورة")
    )
    alert_on_invoice_overdue = models.BooleanField(
        _("تنبيه بعد التأخير"),
        default=True,
        help_text=_("تنبيه بعد تأخر سداد الفاتورة")
    )
    invoice_overdue_days_after = models.IntegerField(
        _("التنبيه بعد التأخير بـ (أيام)"),
        default=1,
        help_text=_("عدد الأيام بعد التأخير للتنبيه")
    )
    
    # ==================== عدم الإزعاج ====================
    enable_do_not_disturb = models.BooleanField(
        _("تفعيل عدم الإزعاج"),
        default=False,
        help_text=_("عدم إرسال إشعارات في أوقات محددة")
    )
    do_not_disturb_start = models.TimeField(
        _("بداية عدم الإزعاج"),
        null=True,
        blank=True,
        default='22:00',
        help_text=_("وقت بداية فترة عدم الإزعاج")
    )
    do_not_disturb_end = models.TimeField(
        _("نهاية عدم الإزعاج"),
        null=True,
        blank=True,
        default='08:00',
        help_text=_("وقت نهاية فترة عدم الإزعاج")
    )
    
    # ==================== إدارة الإشعارات القديمة ====================
    auto_delete_read_notifications = models.BooleanField(
        _("حذف الإشعارات المقروءة تلقائياً"),
        default=False,
        help_text=_("حذف الإشعارات المقروءة بعد فترة محددة")
    )
    auto_delete_after_days = models.IntegerField(
        _("الحذف بعد (أيام)"),
        default=30,
        help_text=_("عدد الأيام قبل حذف الإشعارات المقروءة")
    )
    auto_archive_old_notifications = models.BooleanField(
        _("أرشفة الإشعارات القديمة تلقائياً"),
        default=False,
        help_text=_("أرشفة الإشعارات القديمة بعد فترة محددة")
    )
    auto_archive_after_months = models.IntegerField(
        _("الأرشفة بعد (أشهر)"),
        default=6,
        help_text=_("عدد الأشهر قبل أرشفة الإشعارات")
    )
    
    # ==================== الحقول الإضافية ====================
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    
    class Meta:
        verbose_name = _("تفضيلات الإشعارات")
        verbose_name_plural = _("تفضيلات الإشعارات")
        db_table = "core_notification_preference"
    
    def __str__(self):
        return f"تفضيلات إشعارات {self.user.get_full_name() or self.user.username}"
    
    @classmethod
    def get_or_create_for_user(cls, user):
        """
        الحصول على تفضيلات المستخدم أو إنشاؤها إذا لم تكن موجودة
        """
        preference, created = cls.objects.get_or_create(user=user)
        return preference
    
    def is_notification_enabled(self, notification_type):
        """
        التحقق من تفعيل نوع إشعار معين
        """
        type_mapping = {
            'inventory_alert': self.enable_inventory_alerts,
            'new_invoice': self.enable_invoice_notifications,
            'payment_received': self.enable_payment_notifications,
            'return_request': self.enable_return_notifications,
            'info': self.enable_system_notifications,
            'success': self.enable_system_notifications,
            'warning': self.enable_system_notifications,
            'danger': self.enable_system_notifications,
        }
        return type_mapping.get(notification_type, True)
    
    def is_in_do_not_disturb_period(self):
        """
        التحقق من وجود المستخدم في فترة عدم الإزعاج
        """
        if not self.enable_do_not_disturb or not self.do_not_disturb_start or not self.do_not_disturb_end:
            return False
        
        from datetime import datetime
        now = datetime.now().time()
        
        # إذا كانت فترة عدم الإزعاج تمتد لليوم التالي
        if self.do_not_disturb_start > self.do_not_disturb_end:
            return now >= self.do_not_disturb_start or now <= self.do_not_disturb_end
        else:
            return self.do_not_disturb_start <= now <= self.do_not_disturb_end


# ============================================================
# PHASE 5: DATA PROTECTION MODELS
# ============================================================

class BackupRecord(models.Model):
    """
    Track backup operations and their status
    """
    BACKUP_TYPES = [
        ('full', 'Full Backup'),
        ('database', 'Database Only'),
        ('media', 'Media Files Only'),
        ('config', 'Configuration Only'),
        ('incremental', 'Incremental Backup'),
    ]
    
    BACKUP_STATUS = [
        ('started', 'Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('verified', 'Verified'),
        ('corrupted', 'Corrupted'),
    ]
    
    STORAGE_TYPES = [
        ('local', 'Local Storage'),
        ('s3', 'Amazon S3'),
        ('ftp', 'FTP Server'),
        ('sftp', 'SFTP Server'),
    ]
    
    backup_id = models.CharField(max_length=100, unique=True, db_index=True)
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPES)
    status = models.CharField(max_length=20, choices=BACKUP_STATUS, default='started')
    storage_type = models.CharField(max_length=20, choices=STORAGE_TYPES)
    
    # Backup details
    total_size_bytes = models.BigIntegerField(default=0)
    file_count = models.IntegerField(default=0)
    compression_ratio = models.FloatField(null=True, blank=True)
    
    # Timing information
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Verification information
    verification_status = models.CharField(max_length=20, null=True, blank=True)
    verified_files = models.IntegerField(default=0)
    failed_files = models.IntegerField(default=0)
    verification_errors = models.TextField(blank=True)
    
    # Remote storage information
    remote_path = models.CharField(max_length=500, blank=True)
    remote_upload_status = models.CharField(max_length=20, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'core_backup_record'
        ordering = ['-started_at']
        verbose_name = _("سجل النسخة الاحتياطية")
        verbose_name_plural = _("سجلات النسخ الاحتياطية")
    
    def __str__(self):
        return f"Backup {self.backup_id} ({self.backup_type}) - {self.status}"
    
    @property
    def size_mb(self):
        """Return size in megabytes"""
        return self.total_size_bytes / (1024 * 1024) if self.total_size_bytes else 0
    
    @property
    def is_successful(self):
        """Check if backup was successful"""
        return self.status in ['completed', 'verified']


class BackupFile(models.Model):
    """
    Track individual files within a backup
    """
    FILE_TYPES = [
        ('database', 'Database Dump'),
        ('media', 'Media Archive'),
        ('config', 'Configuration Files'),
        ('logs', 'Log Files'),
        ('other', 'Other Files'),
    ]
    
    backup_record = models.ForeignKey(BackupRecord, on_delete=models.CASCADE, related_name='files')
    file_type = models.CharField(max_length=20, choices=FILE_TYPES)
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    
    # File information
    size_bytes = models.BigIntegerField()
    checksum = models.CharField(max_length=64)  # SHA-256 hash
    is_encrypted = models.BooleanField(default=False)
    is_compressed = models.BooleanField(default=False)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'core_backup_file'
        ordering = ['file_type', 'filename']
        verbose_name = _("ملف النسخة الاحتياطية")
        verbose_name_plural = _("ملفات النسخ الاحتياطية")
    
    def __str__(self):
        return f"{self.filename} ({self.file_type})"
    
    @property
    def size_mb(self):
        """Return size in megabytes"""
        return self.size_bytes / (1024 * 1024)


class DataRetentionPolicy(models.Model):
    """
    Define data retention policies for different data types
    """
    POLICY_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('draft', 'Draft'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    model_name = models.CharField(max_length=100)  # e.g., 'client.Customer'
    
    # Retention settings
    retention_days = models.IntegerField()
    archive_before_delete = models.BooleanField(default=True)
    anonymize_before_delete = models.BooleanField(default=False)
    cascade_delete = models.BooleanField(default=False)
    
    # Notification settings
    notification_days = models.IntegerField(default=30)
    
    # Policy conditions (stored as JSON)
    conditions = models.JSONField(default=dict, blank=True)
    exclude_conditions = models.JSONField(default=dict, blank=True)
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=POLICY_STATUS, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        db_table = 'core_data_retention_policy'
        verbose_name = _("سياسة الاحتفاظ بالبيانات")
        verbose_name_plural = _("سياسات الاحتفاظ بالبيانات")
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.retention_days} days)"
    
    @property
    def is_active(self):
        """Check if policy is active"""
        return self.status == 'active'


class DataRetentionExecution(models.Model):
    """
    Track data retention cleanup executions
    """
    EXECUTION_STATUS = [
        ('started', 'Started'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Completed'),
    ]
    
    execution_id = models.CharField(max_length=100, unique=True, db_index=True)
    policy = models.ForeignKey(DataRetentionPolicy, on_delete=models.CASCADE, related_name='executions')
    
    # Execution details
    status = models.CharField(max_length=20, choices=EXECUTION_STATUS, default='started')
    dry_run = models.BooleanField(default=False)
    
    # Results
    records_found = models.IntegerField(default=0)
    records_deleted = models.IntegerField(default=0)
    records_archived = models.IntegerField(default=0)
    records_anonymized = models.IntegerField(default=0)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Error tracking
    errors = models.TextField(blank=True)
    
    class Meta:
        db_table = 'core_data_retention_execution'
        ordering = ['-started_at']
        verbose_name = _("تنفيذ سياسة الاحتفاظ")
        verbose_name_plural = _("تنفيذات سياسات الاحتفاظ")
    
    def __str__(self):
        return f"Retention execution {self.execution_id} - {self.policy.name}"


class EncryptionKey(models.Model):
    """
    Track encryption keys and their rotation
    """
    KEY_STATUS = [
        ('active', 'Active'),
        ('rotated', 'Rotated'),
        ('revoked', 'Revoked'),
    ]
    
    key_id = models.CharField(max_length=100, unique=True, db_index=True)
    key_hash = models.CharField(max_length=64)  # SHA-256 hash of the key
    algorithm = models.CharField(max_length=50, default='fernet')
    
    # Key lifecycle
    status = models.CharField(max_length=20, choices=KEY_STATUS, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    
    # Usage tracking
    encryption_count = models.IntegerField(default=0)
    decryption_count = models.IntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    rotation_reason = models.CharField(max_length=200, blank=True)
    
    class Meta:
        db_table = 'core_encryption_key'
        ordering = ['-created_at']
        verbose_name = _("مفتاح التشفير")
        verbose_name_plural = _("مفاتيح التشفير")
    
    def __str__(self):
        return f"Encryption Key {self.key_id} ({self.status})"
    
    @property
    def is_active(self):
        """Check if key is active"""
        return self.status == 'active'


class DataProtectionAudit(models.Model):
    """
    Audit trail for data protection operations
    """
    OPERATION_TYPES = [
        ('backup_created', 'Backup Created'),
        ('backup_verified', 'Backup Verified'),
        ('backup_restored', 'Backup Restored'),
        ('data_encrypted', 'Data Encrypted'),
        ('data_decrypted', 'Data Decrypted'),
        ('data_anonymized', 'Data Anonymized'),
        ('data_deleted', 'Data Deleted'),
        ('key_rotated', 'Key Rotated'),
        ('policy_applied', 'Policy Applied'),
    ]
    
    operation_type = models.CharField(max_length=30, choices=OPERATION_TYPES)
    object_type = models.CharField(max_length=100)  # Model name or object type
    object_id = models.CharField(max_length=100, blank=True)
    
    # Operation details
    description = models.TextField()
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    # Context information
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'core_data_protection_audit'
        ordering = ['-timestamp']
        verbose_name = _("سجل تدقيق حماية البيانات")
        verbose_name_plural = _("سجلات تدقيق حماية البيانات")
    
    def __str__(self):
        return f"{self.operation_type} - {self.object_type} ({self.timestamp})"


class DataClassification(models.Model):
    """
    Classify data sensitivity levels
    """
    CLASSIFICATION_LEVELS = [
        ('public', 'Public'),
        ('internal', 'Internal'),
        ('confidential', 'Confidential'),
        ('restricted', 'Restricted'),
    ]
    
    model_name = models.CharField(max_length=100)
    field_name = models.CharField(max_length=100)
    classification_level = models.CharField(max_length=20, choices=CLASSIFICATION_LEVELS)
    
    # Classification rules
    requires_encryption = models.BooleanField(default=False)
    requires_anonymization = models.BooleanField(default=False)
    retention_days = models.IntegerField(null=True, blank=True)
    
    # Metadata
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_data_classification'
        unique_together = ['model_name', 'field_name']
        ordering = ['model_name', 'field_name']
        verbose_name = _("تصنيف البيانات")
        verbose_name_plural = _("تصنيفات البيانات")
    
    def __str__(self):
        return f"{self.model_name}.{self.field_name} ({self.classification_level})"
    
    @property
    def is_sensitive(self):
        """Check if data is sensitive (confidential or restricted)"""
        return self.classification_level in ['confidential', 'restricted']

# ✅ PHASE 7: Simplified Monitoring Models (Consolidated from 7 to 3 models)

class UnifiedLog(models.Model):
    """
    ✅ SIMPLIFIED MONITORING: Unified logging model
    Consolidates SystemLog, SecurityLog, PerformanceLog, AuditLog, and SystemMetric into one model
    """
    LOG_TYPES = [
        ('system', 'System Log'),
        ('security', 'Security Log'),
        ('performance', 'Performance Log'),
        ('audit', 'Audit Log'),
        ('metric', 'System Metric'),
    ]
    
    LEVEL_CHOICES = [
        ('DEBUG', 'تصحيح'),
        ('INFO', 'معلومات'),
        ('WARNING', 'تحذير'),
        ('ERROR', 'خطأ'),
        ('CRITICAL', 'حرج'),
    ]
    
    CATEGORY_CHOICES = [
        ('general', 'عام'),
        ('authentication', 'مصادقة'),
        ('authorization', 'صلاحيات'),
        ('performance', 'أداء'),
        ('security', 'أمان'),
        ('audit', 'مراجعة'),
        ('financial', 'مالي'),
        ('database', 'قاعدة بيانات'),
        ('integration', 'تكامل'),
        ('system_metric', 'مقاييس النظام'),
    ]
    
    # Core fields (common to all log types)
    log_type = models.CharField(_("نوع السجل"), max_length=15, choices=LOG_TYPES, db_index=True)
    level = models.CharField(_("المستوى"), max_length=10, choices=LEVEL_CHOICES, default='INFO')
    category = models.CharField(_("الفئة"), max_length=20, choices=CATEGORY_CHOICES, default='general')
    message = models.TextField(_("الرسالة"))
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                            verbose_name=_("المستخدم"), related_name='unified_logs')
    
    # Request/Session tracking
    request_id = models.CharField(_("معرف الطلب"), max_length=100, blank=True, null=True)
    ip_address = models.GenericIPAddressField(_("عنوان IP"), blank=True, null=True)
    user_agent = models.TextField(_("وكيل المستخدم"), blank=True)
    
    # Flexible data storage for all log types
    data = models.JSONField(_("البيانات"), default=dict, blank=True, help_text="Stores all type-specific data")
    
    # Timestamp
    timestamp = models.DateTimeField(_("الوقت"), auto_now_add=True, db_index=True)
    
    class Meta:
        verbose_name = _("السجل الموحد")
        verbose_name_plural = _("السجلات الموحدة")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['log_type', 'timestamp']),
            models.Index(fields=['level', 'timestamp']),
            models.Index(fields=['category', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
        ]
    
    def __str__(self):
        return f"[{self.log_type.upper()}] [{self.level}] {self.message[:50]}..."
    
    @classmethod
    def log_system(cls, level, message, user=None, category='general', **extra_data):
        """Create a system log entry"""
        return cls.objects.create(
            log_type='system',
            level=level,
            category=category,
            message=message,
            user=user,
            data=extra_data
        )
    
    @classmethod
    def log_security(cls, event_type, user=None, success=False, severity='medium', **extra_data):
        """Create a security log entry"""
        return cls.objects.create(
            log_type='security',
            level='WARNING' if not success else 'INFO',
            category='security',
            message=f"Security event: {event_type}",
            user=user,
            data={
                'event_type': event_type,
                'success': success,
                'severity': severity,
                **extra_data
            }
        )
    
    @classmethod
    def log_performance(cls, metric_name, metric_value, unit='ms', threshold=None, **extra_data):
        """Create a performance log entry"""
        level = 'WARNING' if threshold and metric_value > threshold else 'INFO'
        return cls.objects.create(
            log_type='performance',
            level=level,
            category='performance',
            message=f"Performance metric: {metric_name} = {metric_value}{unit}",
            data={
                'metric_name': metric_name,
                'metric_value': metric_value,
                'unit': unit,
                'threshold': threshold,
                **extra_data
            }
        )
    
    @classmethod
    def log_audit(cls, user, action, resource_type, resource_id, **extra_data):
        """Create an audit log entry"""
        return cls.objects.create(
            log_type='audit',
            level='INFO',
            category='audit',
            message=f"User {user.username} performed {action} on {resource_type}:{resource_id}",
            user=user,
            data={
                'action': action,
                'resource_type': resource_type,
                'resource_id': resource_id,
                **extra_data
            }
        )
    
    @classmethod
    def log_metric(cls, metric_category, metric_name, value, unit='count', **extra_data):
        """Create a system metric entry"""
        return cls.objects.create(
            log_type='metric',
            level='INFO',
            category='system_metric',
            message=f"Metric: {metric_category}.{metric_name} = {value}{unit}",
            data={
                'metric_category': metric_category,
                'metric_name': metric_name,
                'value': value,
                'unit': unit,
                **extra_data
            }
        )


class AlertRule(models.Model):
    """
    ✅ SIMPLIFIED ALERTING: Alert rules configuration model
    Defines conditions and thresholds for automated alerts
    """
    METRIC_TYPES = [
        ('error_rate', 'Error Rate'),
        ('response_time', 'Response Time'),
        ('memory_usage', 'Memory Usage'),
        ('cpu_usage', 'CPU Usage'),
        ('disk_usage', 'Disk Usage'),
        ('failed_logins', 'Failed Logins'),
        ('concurrent_users', 'Concurrent Users'),
        ('database_connections', 'Database Connections'),
    ]
    
    OPERATORS = [
        ('gt', 'Greater Than'),
        ('gte', 'Greater Than or Equal'),
        ('lt', 'Less Than'),
        ('lte', 'Less Than or Equal'),
        ('eq', 'Equal'),
        ('ne', 'Not Equal'),
    ]
    
    SEVERITY_LEVELS = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]
    
    name = models.CharField(_("اسم القاعدة"), max_length=100, unique=True)
    description = models.TextField(_("الوصف"), blank=True)
    metric_type = models.CharField(_("نوع المقياس"), max_length=30, choices=METRIC_TYPES)
    operator = models.CharField(_("المشغل"), max_length=5, choices=OPERATORS)
    threshold_value = models.FloatField(_("قيمة العتبة"))
    severity = models.CharField(_("مستوى الخطورة"), max_length=10, choices=SEVERITY_LEVELS)
    time_window_minutes = models.PositiveIntegerField(_("نافذة الوقت (دقائق)"), default=5)
    is_active = models.BooleanField(_("نشط"), default=True)
    email_recipients = models.TextField(_("مستقبلو البريد الإلكتروني"), help_text="Comma-separated email addresses", blank=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    
    class Meta:
        verbose_name = _("قاعدة التنبيه")
        verbose_name_plural = _("قواعد التنبيهات")
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.metric_type} {self.operator} {self.threshold_value})"


class Alert(models.Model):
    """
    ✅ SIMPLIFIED ALERTING: Alert instances model
    Stores triggered alerts and their status
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('suppressed', 'Suppressed'),
    ]
    
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, verbose_name=_("القاعدة"))
    status = models.CharField(_("الحالة"), max_length=15, choices=STATUS_CHOICES, default='active')
    message = models.TextField(_("الرسالة"))
    metric_value = models.FloatField(_("قيمة المقياس"))
    threshold_value = models.FloatField(_("قيمة العتبة"))
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='acknowledged_alerts', verbose_name=_("تم الإقرار بواسطة")
    )
    acknowledged_at = models.DateTimeField(_("وقت الإقرار"), null=True, blank=True)
    resolved_at = models.DateTimeField(_("وقت الحل"), null=True, blank=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    
    class Meta:
        verbose_name = _("تنبيه")
        verbose_name_plural = _("التنبيهات")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['rule', 'created_at']),
        ]
    
    def acknowledge(self, user: User):
        """Acknowledge the alert"""
        self.status = 'acknowledged'
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save()
    
    def resolve(self):
        """Mark alert as resolved"""
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.save()
    
    def __str__(self):
        return f"[{self.rule.severity.upper()}] {self.rule.name} - {self.status}"


# ============================================================
# SYSTEM MODULES MANAGEMENT
# ============================================================

class SystemModule(models.Model):
    """
    نموذج لإدارة تطبيقات النظام القابلة للتفعيل/التعطيل
    """
    MODULE_TYPES = [
        ('core', 'تطبيق أساسي'),
        ('optional', 'تطبيق اختياري'),
    ]
    
    code = models.CharField(max_length=50, unique=True, verbose_name='كود التطبيق')
    name_ar = models.CharField(max_length=100, verbose_name='الاسم بالعربية')
    name_en = models.CharField(max_length=100, verbose_name='الاسم بالإنجليزية')
    description = models.TextField(blank=True, verbose_name='الوصف')
    icon = models.CharField(max_length=50, default='fas fa-cube', verbose_name='الأيقونة')
    
    module_type = models.CharField(max_length=20, choices=MODULE_TYPES, default='optional', verbose_name='نوع التطبيق')
    is_enabled = models.BooleanField(default=True, verbose_name='مفعّل')
    
    # التطبيقات المطلوبة (dependencies)
    required_modules = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        blank=True, 
        related_name='dependent_modules',
        verbose_name='التطبيقات المطلوبة'
    )
    
    # معلومات إضافية
    url_namespace = models.CharField(max_length=50, blank=True, verbose_name='URL Namespace')
    menu_id = models.CharField(max_length=50, blank=True, verbose_name='معرف القائمة')
    
    order = models.IntegerField(default=0, verbose_name='الترتيب')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    class Meta:
        verbose_name = 'تطبيق النظام'
        verbose_name_plural = 'تطبيقات النظام'
        ordering = ['order', 'name_ar']
    
    def __str__(self):
        return f"{self.name_ar} ({self.code})"
    
    def can_disable(self):
        """التحقق من إمكانية تعطيل التطبيق"""
        if self.module_type == 'core':
            return False
        # التحقق من عدم وجود تطبيقات أخرى مفعلة تعتمد عليه
        return not self.dependent_modules.filter(is_enabled=True).exists()
    
    def get_dependencies_status(self):
        """الحصول على حالة التطبيقات المطلوبة"""
        deps = self.required_modules.all()
        return {
            'all_enabled': all(dep.is_enabled for dep in deps),
            'missing': [dep for dep in deps if not dep.is_enabled]
        }
