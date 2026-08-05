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
    def _get_all_settings_dict(cls):
        from django.core.cache import cache
        cache_key = 'global_settings_dict_v2'
        settings_dict = cache.get(cache_key)
        if settings_dict is None:
            settings_dict = {}
            for s in cls.objects.filter(is_active=True).values('key', 'value', 'data_type'):
                val = s['value']
                dt = s['data_type']
                if dt == "boolean":
                    val = str(val).lower() in ("true", "1", "yes", "نعم")
                elif dt == "integer":
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        val = 0
                elif dt in ("decimal", "float"):
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        val = 0.0
                elif dt == "json":
                    import json
                    try:
                        val = json.loads(val)
                    except Exception:
                        val = {}
                settings_dict[s['key']] = val
            cache.set(cache_key, settings_dict, 300)
        return settings_dict

    @classmethod
    def invalidate_cache(cls):
        from django.core.cache import cache
        cache.delete('global_settings_dict_v2')

    @classmethod
    def get_setting(cls, key, default=None):
        """
        الحصول على قيمة إعداد معين باستخدام الكاش الموحد
        """
        try:
            settings_dict = cls._get_all_settings_dict()
            if key in settings_dict:
                return settings_dict[key]
            return default
        except Exception:
            try:
                setting = cls.objects.get(key=key, is_active=True)
                if setting.data_type == "integer":
                    return int(setting.value)
                elif setting.data_type == "decimal":
                    return float(setting.value)
                elif setting.data_type == "boolean":
                    return setting.value.lower() in ("true", "1", "yes", "نعم")
                elif setting.data_type == "json":
                    import json
                    return json.loads(setting.value)
                else:
                    return setting.value
            except cls.DoesNotExist:
                return default

    @classmethod
    def set_setting(cls, key, value, group="general", data_type="string", description=""):
        """
        تحديث أو إنشاء إعداد مع مسح الكاش صراحة
        """
        obj, created = cls.objects.update_or_create(
            key=key,
            defaults={
                "value": str(value),
                "group": group,
                "data_type": data_type,
                "description": description,
                "is_active": True,
            }
        )
        cls.invalidate_cache()
        return obj

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.invalidate_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.invalidate_cache()
    
    @classmethod
    def get_currency_symbol(cls):
        """
        الحصول على رمز العملة من الإعدادات
        """
        return cls.get_setting('default_currency', 'ج.م')

    @classmethod
    def get_currency_symbol_en(cls):
        """
        الحصول على رمز العملة بالإنجليزية من الإعدادات
        """
        return cls.get_setting('currency_symbol_en', 'EGP')

    @classmethod
    def get_default_print_language(cls):
        """
        الحصول على لغة الطباعة الافتراضية
        """
        return cls.get_setting('default_print_language', 'ar')

    @classmethod
    def get_company_address_en(cls):
        """
        الحصول على عنوان الشركة بالإنجليزية
        """
        return cls.get_setting('company_address_en', '')

    @classmethod
    def get_sale_invoice_notes_en(cls):
        """
        الحصول على الشروط والأحكام الإنجليزية لفواتير المبيعات
        """
        return cls.get_setting('default_sale_invoice_notes_en', '')

    @classmethod
    def get_quotation_notes_en(cls):
        """
        الحصول على الشروط والأحكام الإنجليزية لعروض الأسعار
        """
        return cls.get_setting('default_quotation_notes_en', '')

    @classmethod
    def get_invoice_title_sale_en(cls):
        """
        الحصول على عنوان فاتورة المبيعات بالإنجليزية
        """
        return cls.get_setting('invoice_title_sale_en', 'TAX INVOICE')

    @classmethod
    def get_invoice_title_quotation_en(cls):
        """
        الحصول على عنوان عرض السعر بالإنجليزية
        """
        return cls.get_setting('invoice_title_quotation_en', 'QUOTATION')
    
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


# ============================================================
# ENTERPRISE DOCUMENT MANAGEMENT SYSTEM (DMS) MODELS
# ============================================================
import uuid
from django.db.models import Q, UniqueConstraint
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


def attachment_upload_path(instance, filename):
    """
    توليد مسار تخزين فيزيائي مخصص ومفهرس حسب الشركة والفئة لمنع ثغرات Directory Traversal
    """
    company_id = getattr(instance, 'company_id', 1) or 1
    sha_prefix = getattr(instance, 'sha256_hash', 'blob')[:16]
    random_suffix = uuid.uuid4().hex[:8]
    return f"companies/{company_id}/attachments/%Y/%m/{sha_prefix}_{random_suffix}.dat"


class AttachmentCategory(models.Model):
    """
    نموذج فئات المستندات والمرفقات بحوكمة الاستبقاء والأمان (AttachmentCategory Model)
    """
    code = models.CharField(_("كود الفئة"), max_length=50, unique=True, db_index=True)
    name = models.CharField(_("اسم الفئة"), max_length=150)
    description = models.TextField(_("الوصف"), blank=True, null=True)

    max_size_mb = models.PositiveIntegerField(_("الحد الأقصى لحجم الملف (ميجابايت)"), default=10)
    allowed_extensions = models.CharField(_("الامتدادات المسموح بها"), max_length=255, default="pdf,png,jpg,jpeg,docx,xlsx")
    retention_days = models.PositiveIntegerField(_("مدة الاستبقاء القانونية (أيام)"), default=365)
    requires_integrity_check = models.BooleanField(_("يتطلب فحص السلامة (SHA-256)"), default=True)
    permission_required = models.CharField(_("الصلاحية المطلوبة للوصول"), max_length=150, blank=True, null=True)

    class Meta:
        verbose_name = _("فئة مستندات")
        verbose_name_plural = _("فئات المستندات")
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def get_allowed_extensions_list(self):
        if not self.allowed_extensions:
            return []
        return [ext.strip().lower().lstrip('.') for ext in self.allowed_extensions.split(',') if ext.strip()]


class FileBlob(models.Model):
    """
    نموذج كتلة التخزين الفيزيائية والمعزولة للملفات (FileBlob Model)
    """
    SECURITY_STATUS_CHOICES = (
        ('PENDING', _('قيد الفحص')),
        ('CLEAN', _('سليم')),
        ('BLOCKED', _('محظور')),
        ('QUARANTINED', _('في الحجر الصحي')),
    )

    sha256_hash = models.CharField(_("بصمة الملف (SHA-256)"), max_length=64, unique=True, db_index=True)
    file = models.FileField(_("الملف الفيزيائي"), upload_to=attachment_upload_path)
    file_size = models.PositiveBigIntegerField(_("حجم الملف (بايت)"))
    content_type = models.CharField(_("نوع MIME"), max_length=100)
    company_id = models.PositiveIntegerField(_("معرف الشركة"), default=1, db_index=True)
    reference_count = models.PositiveIntegerField(_("عداد الإشارات المرجعية الذري"), default=0)
    security_status = models.CharField(_("حالة الأمان"), max_length=20, choices=SECURITY_STATUS_CHOICES, default='CLEAN')
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("كتلة تخزين فيزيائية")
        verbose_name_plural = _("كتل التخزين الفيزيائية")
        indexes = [
            models.Index(fields=['sha256_hash']),
            models.Index(fields=['company_id', 'security_status']),
        ]

    def __str__(self):
        return f"Blob [{self.sha256_hash[:8]}] - {self.file_size} Bytes (Refs: {self.reference_count})"


class Attachment(models.Model):
    """
    نموذج المرفقات المربوطة بمصادر الأعمال وقواعد الإصدارات (Attachment Model)
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    category = models.ForeignKey(AttachmentCategory, on_delete=models.PROTECT, related_name='attachments', verbose_name=_("فئة المستند"))
    file_blob = models.ForeignKey(FileBlob, on_delete=models.PROTECT, related_name='attachments', verbose_name=_("كتلة التخزين الفيزيائية"))
    original_name = models.CharField(_("اسم الملف الأصلي"), max_length=255)
    version = models.PositiveIntegerField(_("رقم الإصدار"), default=1)
    is_latest = models.BooleanField(_("النسخة الأحدث"), default=True, db_index=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("القائم بالرفع"))
    deleted_at = models.DateTimeField(_("تاريخ الحذف الناعم"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(_("تاريخ الرفع"), auto_now_add=True)

    class Meta:
        verbose_name = _("مرفق مستند")
        verbose_name_plural = _("مرفقات المستندات")
        indexes = [
            models.Index(fields=['content_type', 'object_id', 'is_latest']),
            models.Index(fields=['deleted_at']),
        ]
        constraints = [
            UniqueConstraint(
                fields=['content_type', 'object_id', 'category'],
                condition=Q(is_latest=True, deleted_at__isnull=True),
                name='one_latest_attachment_per_category'
            )
        ]

    def __str__(self):
        return f"{self.original_name} (V{self.version}) -> {self.category.name}"


class DraftAttachment(models.Model):
    """
    نموذج المسودات المؤقتة للمرفقات قبل حفظ الكائن الرئيسي (DraftAttachment Model)
    """
    draft_token = models.UUIDField(_("رمز المسودة الموقت"), default=uuid.uuid4, db_index=True, unique=True)
    session_key = models.CharField(_("مفتاح الجلسة"), max_length=100, db_index=True)
    file_blob = models.ForeignKey(FileBlob, on_delete=models.CASCADE, related_name='draft_attachments', verbose_name=_("كتلة التخزين"))
    category = models.ForeignKey(AttachmentCategory, on_delete=models.CASCADE, verbose_name=_("فئة المستند"))
    original_name = models.CharField(_("اسم الملف الأصلي"), max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("القائم بالرفع"))
    expires_at = models.DateTimeField(_("تاريخ الانتهاء"), db_index=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("مسودة مرفق مؤقتة")
        verbose_name_plural = _("مسودات المرفقات المؤقتة")

    def __str__(self):
        return f"Draft [{self.draft_token}] - {self.original_name}"


class AttachmentAuditLog(models.Model):
    """
    سجل التدقيق التاريخي للمرفقات (AttachmentAuditLog Model)
    """
    ACTION_CHOICES = (
        ('UPLOADED', _('رفع')),
        ('VIEWED', _('عرض')),
        ('DOWNLOADED', _('تنزيل')),
        ('REPLACED', _('استبدال / تحديث إصدار')),
        ('DELETED', _('حذف ناعم')),
        ('RESTORED', _('استعادة')),
    )

    attachment = models.ForeignKey(Attachment, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs', verbose_name=_("المرفق"))
    action = models.CharField(_("نوع الإجراء"), max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("القائم بالإجراء"))
    user_name_snapshot = models.CharField(_("لقطة اسم المستخدم"), max_length=150, blank=True, null=True)
    user_email_snapshot = models.CharField(_("لقطة بريد المستخدم"), max_length=150, blank=True, null=True)
    ip_address = models.GenericIPAddressField(_("عنوان IP"), blank=True, null=True)
    timestamp = models.DateTimeField(_("التوقيت"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تدقيق مرفق")
        verbose_name_plural = _("سجلات تدقيق المرفقات")
        ordering = ['-timestamp']


class AttachmentOrphanReview(models.Model):
    """
    نموذج مراجعة وإدارة كتل التخزين الأيتام (AttachmentOrphanReview Model)
    """
    STATUS_CHOICES = (
        ('FOUND', _('مكتشف كأيتام')),
        ('REVIEWED', _('تمت المراجعة')),
        ('MARKED_FOR_DELETE', _('مُعلم للحذف')),
        ('DELETED', _('تم الحذف النهائي')),
    )

    file_blob = models.ForeignKey(FileBlob, on_delete=models.CASCADE, related_name='orphan_reviews')
    status = models.CharField(_("حالة المراجعة"), max_length=30, choices=STATUS_CHOICES, default='FOUND')
    detected_at = models.DateTimeField(_("توقيت الاكتشاف"), auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المراجع"))
    deleted_at = models.DateTimeField(_("تاريخ الحذف النهائي"), null=True, blank=True)

    class Meta:
        verbose_name = _("مراجعة مستند يتيتم")
        verbose_name_plural = _("مراجعات المستندات الأيتام")


class DocumentSequenceRule(models.Model):
    """
    نموذج قواعد ترقيم المستندات (DocumentSequenceRule Model)
    """
    company_code = models.CharField(_("كود الشركة"), max_length=50, default="DEFAULT", db_index=True)
    warehouse = models.ForeignKey('product.Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='sequence_rules', verbose_name=_("المخزن / الفرع"))
    document_type = models.CharField(_("نوع المستند"), max_length=50, db_index=True)
    prefix = models.CharField(_("البادئة"), max_length=20)
    padding = models.PositiveIntegerField(_("طول الخانة التسلسلية"), default=5)
    numbering_basis = models.CharField(_("أساس السنة التسلسلية"), max_length=20, default="POSTING_DATE")
    version = models.PositiveIntegerField(_("إصدار القاعدة"), default=1)
    is_locked = models.BooleanField(_("مقفلة لإنشاء مستندات حقيقية"), default=False, help_text=_("تقفل القاعدة تلقائياً بعد إنتاج أول رقم لحماية تاريخ السجلات"))
    status = models.CharField(_("الحالة"), max_length=20, default="ACTIVE")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("قاعدة ترقيم مستند")
        verbose_name_plural = _("قواعد ترقيم المستندات")
        constraints = [
            models.UniqueConstraint(
                fields=["company_code", "warehouse", "document_type", "version"],
                name="unique_sequence_rule_version",
            ),
        ]

    def __str__(self):
        return f"{self.document_type} - {self.prefix} (v{self.version})"


class DocumentSequenceCounter(models.Model):
    """
    نموذج عداد ترقيم المستندات (DocumentSequenceCounter Model)
    """
    company_code = models.CharField(_("كود الشركة"), max_length=50, default="DEFAULT", db_index=True)
    warehouse = models.ForeignKey('product.Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='sequence_counters', verbose_name=_("المخزن / الفرع"))
    document_type = models.CharField(_("نوع المستند"), max_length=50, db_index=True)
    year = models.PositiveIntegerField(_("السنة التسلسلية"), db_index=True)
    last_number = models.PositiveIntegerField(_("آخر رقم تسلسلي"), default=0)
    last_reserved_at = models.DateTimeField(_("تاريخ آخر حجز/توليد"), auto_now=True)
    rule = models.ForeignKey(DocumentSequenceRule, on_delete=models.PROTECT, related_name='counters', verbose_name=_("قاعدة الترقيم المرتبطة"))

    class Meta:
        verbose_name = _("عداد ترقيم مستند")
        verbose_name_plural = _("عدادات ترقيم المستندات")
        constraints = [
            models.UniqueConstraint(
                fields=["company_code", "warehouse", "document_type", "year"],
                name="unique_sequence_counter_scope",
            ),
        ]

    def __str__(self):
        return f"{self.document_type} - {self.year}: {self.last_number}"


class DocumentSequenceAudit(models.Model):
    """
    سجل تدقيق الترقيم (DocumentSequenceAudit Model)
    """
    event_type = models.CharField(_("نوع الحدث"), max_length=30, db_index=True)
    document_type = models.CharField(_("نوع المستند"), max_length=50, db_index=True)
    document_number = models.CharField(_("رقم المستند الناتج"), max_length=100, blank=True, null=True, db_index=True)
    company_code = models.CharField(_("كود الشركة"), max_length=50, default="DEFAULT")
    warehouse = models.ForeignKey('product.Warehouse', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المخزن / الفرع"))
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المستخدم (إن وجد)"))
    source_type = models.CharField(_("مصدر الطلب"), max_length=20, default="USER")
    timestamp = models.DateTimeField(_("تاريخ وتوقيت الحدث"), auto_now_add=True, db_index=True)
    reason = models.TextField(_("السبب / الملاحظات"), blank=True, null=True)
    old_value = models.CharField(_("القيمة القديمة"), max_length=100, blank=True, null=True)
    new_value = models.CharField(_("القيمة الجديدة"), max_length=100, blank=True, null=True)
    prefix_snapshot = models.CharField(_("لقطة البادئة"), max_length=20, blank=True, null=True)
    padding_snapshot = models.PositiveIntegerField(_("لقطة الطول"), blank=True, null=True)
    year_snapshot = models.PositiveIntegerField(_("لقطة السنة"), blank=True, null=True)
    sequence_number = models.PositiveIntegerField(_("الرقم التسلسلي المجرد"), blank=True, null=True)

    class Meta:
        verbose_name = _("سجل تدقيق الترقيم")
        verbose_name_plural = _("سجلات تدقيق الترقيم")
        ordering = ["-timestamp"]

