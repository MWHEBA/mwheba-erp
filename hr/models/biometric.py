"""
نماذج ماكينة البصمة وسجلات الحركات الخام
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class BiometricDevice(models.Model):
    """نموذج ماكينة البصمة"""
    
    DEVICE_TYPE_CHOICES = [
        ('fingerprint', 'بصمة الإصبع'),
        ('face', 'التعرف على الوجه'),
        ('card', 'كارت'),
        ('mixed', 'مختلط'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'نشط'),
        ('inactive', 'غير نشط'),
        ('maintenance', 'تحت الصيانة'),
        ('error', 'خطأ'),
    ]
    
    # معلومات الجهاز
    device_name = models.CharField(max_length=100, verbose_name='اسم الجهاز')
    device_code = models.CharField(max_length=50, unique=True, verbose_name='كود الجهاز')
    device_type = models.CharField(
        max_length=20,
        choices=DEVICE_TYPE_CHOICES,
        verbose_name='نوع الجهاز'
    )
    serial_number = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='الرقم التسلسلي'
    )
    
    # معلومات الاتصال
    ip_address = models.GenericIPAddressField(verbose_name='عنوان IP')
    port = models.IntegerField(default=4370, verbose_name='المنفذ')
    
    # الموقع
    location = models.CharField(max_length=200, verbose_name='الموقع')
    department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_devices',
        verbose_name='القسم'
    )
    
    # الإعدادات وفارق التوقيت (DST / Timezone Offset)
    timezone = models.CharField(
        max_length=50,
        default='Africa/Cairo',
        verbose_name='المنطقة الزمنية'
    )
    timezone_offset_hours = models.IntegerField(
        default=0,
        verbose_name='تعويض فارق التوقيت (ساعات)',
        help_text='إضافة أو خصم ساعات لتعويض فروق التوقيت الصيفي أو خطأ ساعة الماكينة الداخلية'
    )
    auto_sync = models.BooleanField(
        default=True,
        verbose_name='مزامنة تلقائية'
    )
    sync_interval = models.IntegerField(
        default=30,
        verbose_name='فترة المزامنة (دقائق)'
    )
    
    # معلومات الاتصال
    username = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='اسم المستخدم'
    )
    password = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='كلمة المرور'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='الحالة'
    )
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    # آخر اتصال
    last_sync = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='آخر مزامنة'
    )
    last_connection = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='آخر اتصال'
    )
    
    # الإحصائيات
    total_users = models.IntegerField(default=0, verbose_name='عدد المستخدمين')
    total_records = models.IntegerField(default=0, verbose_name='عدد السجلات')
    
    # ملاحظات
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإضافة')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_devices',
        verbose_name='أضيف بواسطة'
    )
    
    class Meta:
        verbose_name = 'ماكينة بصمة'
        verbose_name_plural = 'ماكينات البصمة'
        ordering = ['device_name']
    
    def __str__(self):
        return f"{self.device_name} ({self.ip_address})"
    
    @property
    def connection_string(self):
        """نص الاتصال"""
        return f"{self.ip_address}:{self.port}"
    
    @property
    def is_online(self):
        """هل الجهاز متصل"""
        from datetime import timedelta
        from django.utils import timezone
        if self.last_connection:
            now = timezone.now()
            last_conn = self.last_connection
            if timezone.is_naive(last_conn):
                last_conn = timezone.make_aware(last_conn)
            return now - last_conn < timedelta(minutes=5)
        return False


class BiometricLog(models.Model):
    """سجل البصمات والحركات الخام من الماكينات والموبايل والزيارات الميدانية"""
    
    LOG_TYPE_CHOICES = [
        ('check_in', 'حضور'),
        ('check_out', 'انصراف'),
        ('break_start', 'بداية استراحة'),
        ('break_end', 'نهاية استراحة'),
    ]

    SOURCE_CHOICES = [
        ('device', 'ماكينة'),
        ('mobile', 'موبايل'),
        ('field_visit', 'زيارة ميدانية'),
        ('supervisor', 'مشرف'),
        ('manual', 'يدوي'),
        ('excel', 'استيراد إكسيل'),
    ]
    
    device = models.ForeignKey(
        BiometricDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs',
        verbose_name='الجهاز'
    )
    
    # معلومات السجل
    user_id = models.CharField(max_length=50, verbose_name='معرف المستخدم')
    timestamp = models.DateTimeField(verbose_name='وقت البصمة')
    log_type = models.CharField(
        max_length=20,
        choices=LOG_TYPE_CHOICES,
        default='check_in',
        verbose_name='نوع السجل'
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='device',
        verbose_name='المصدر'
    )
    
    # ربط بالموظف
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_logs',
        verbose_name='الموظف'
    )
    
    # ربط بسجل الحضور
    attendance = models.ForeignKey(
        'Attendance',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_logs',
        verbose_name='سجل الحضور'
    )

    # بيانات الجيوفينسنج والموبايل ومكافحة التحايل
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True, verbose_name='خط العرض')
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True, verbose_name='خط الطول')
    location_accuracy = models.FloatField(null=True, blank=True, verbose_name='دقة الموقع (متر)')
    matched_location = models.ForeignKey(
        'hr.WorkLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_logs',
        verbose_name='المقر المطابق'
    )
    selfie_image = models.ImageField(
        upload_to='attendance_selfies/%Y/%m/',
        null=True,
        blank=True,
        verbose_name='صورة السيلفي'
    )
    device_uuid = models.CharField(max_length=255, blank=True, null=True, verbose_name='معرف عتاد الجهاز')
    is_device_unverified = models.BooleanField(default=False, verbose_name='جهاز غير موثق (طوارئ)')
    device_info = models.JSONField(null=True, blank=True, verbose_name='معلومات المتصفح/الجهاز')
    is_offline_synced = models.BooleanField(default=False, verbose_name='تمت المزامنة أوفلاين')
    sync_received_at = models.DateTimeField(null=True, blank=True, verbose_name='توقيت وصول المزامنة')

    # الربط الاختياري بالعملاء وأوامر الشغل للزيارات الميدانية
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_logs',
        verbose_name='العميل المرتبط'
    )
    work_order = models.ForeignKey(
        'work_order.WorkOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_logs',
        verbose_name='أمر الشغل المرتبط'
    )
    
    # حالة المعالجة
    is_processed = models.BooleanField(default=False, verbose_name='تمت المعالجة')
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='وقت المعالجة'
    )
    
    # البيانات الخام
    raw_data = models.JSONField(
        null=True,
        blank=True,
        verbose_name='البيانات الخام'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'سجل بصمة'
        verbose_name_plural = 'سجلات البصمات'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['device', 'timestamp']),
            models.Index(fields=['employee', 'timestamp']),
            models.Index(fields=['device', 'is_processed']),
            models.Index(fields=['is_processed']),
            models.Index(fields=['source']),
        ]
    
    def __str__(self):
        return f"{self.user_id} - {self.timestamp} ({self.source})"


class BiometricSyncLog(models.Model):
    """سجل عمليات المزامنة"""
    
    STATUS_CHOICES = [
        ('success', 'نجحت'),
        ('failed', 'فشلت'),
        ('partial', 'جزئية'),
    ]
    
    device = models.ForeignKey(
        BiometricDevice,
        on_delete=models.CASCADE,
        related_name='sync_logs',
        verbose_name='الجهاز'
    )
    
    started_at = models.DateTimeField(verbose_name='وقت البداية')
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='وقت الانتهاء'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        verbose_name='الحالة'
    )
    
    records_fetched = models.IntegerField(default=0, verbose_name='السجلات المجلوبة')
    records_processed = models.IntegerField(default=0, verbose_name='السجلات المعالجة')
    records_failed = models.IntegerField(default=0, verbose_name='السجلات الفاشلة')
    
    error_message = models.TextField(blank=True, verbose_name='رسالة الخطأ')
    
    class Meta:
        verbose_name = 'سجل مزامنة'
        verbose_name_plural = 'سجلات المزامنة'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['device', '-started_at']),
            models.Index(fields=['started_at']),
        ]
    
    def __str__(self):
        return f"{self.device.device_name} - {self.started_at}"
    
    @classmethod
    def cleanup_old_logs(cls, days=30):
        """حذف سجلات المزامنة القديمة"""
        from django.utils import timezone
        from datetime import timedelta
        cutoff_date = timezone.now() - timedelta(days=days)
        deleted_count = cls.objects.filter(started_at__lt=cutoff_date).delete()[0]
        return deleted_count
    
    @property
    def duration(self):
        """مدة المزامنة"""
        if self.completed_at and self.started_at:
            from django.utils import timezone
            started = self.started_at
            completed = self.completed_at
            if timezone.is_naive(started):
                started = timezone.make_aware(started)
            if timezone.is_naive(completed):
                completed = timezone.make_aware(completed)
            delta = completed - started
            return round(delta.total_seconds(), 2)
        return None
