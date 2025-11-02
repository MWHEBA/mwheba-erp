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
        ("system", _("نظام")),
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
        ("info", _("معلومات")),
        ("success", _("نجاح")),
        ("warning", _("تحذير")),
        ("danger", _("خطر")),
        ("inventory_alert", _("تنبيه مخزون")),
        ("payment_received", _("دفعة مستلمة")),
        ("new_invoice", _("فاتورة جديدة")),
        ("return_request", _("طلب إرجاع")),
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
                    return reverse('sale:sale_detail', kwargs={'pk': self.related_id})
                elif self.related_model == 'Purchase':
                    return reverse('purchase:purchase_detail', kwargs={'pk': self.related_id})
                elif self.related_model == 'Product':
                    return reverse('product:product_detail', kwargs={'pk': self.related_id})
            except:
                pass
        
        return None


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
