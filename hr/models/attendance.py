"""
نماذج الحضور والانصراف
"""
from django.db import models
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError

User = get_user_model()


class Shift(models.Model):
    """نموذج الورديات"""
    
    SHIFT_TYPE_CHOICES = [
        ('annual', 'سنة مالية'),
        ('summer', 'نشاط صيفي'),
    ]
    
    name = models.CharField(max_length=100, verbose_name='اسم الوردية')
    shift_type = models.CharField(
        max_length=20,
        choices=SHIFT_TYPE_CHOICES,
        verbose_name='نوع الوردية'
    )
    start_time = models.TimeField(verbose_name='وقت البداية')
    end_time = models.TimeField(verbose_name='وقت النهاية')

    # أوقات رمضان (اختيارية)
    ramadan_start_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name='وقت بداية رمضان'
    )
    ramadan_end_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name='وقت نهاية رمضان'
    )
    
    # فترات السماح
    grace_period_in = models.IntegerField(
        default=15,
        verbose_name='فترة السماح للحضور (دقائق)'
    )
    grace_period_out = models.IntegerField(
        default=15,
        verbose_name='فترة السماح للانصراف (دقائق)'
    )
    
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    class Meta:
        verbose_name = 'وردية'
        verbose_name_plural = 'الورديات'
    
    def __str__(self):
        return f"{self.name} ({self.start_time} - {self.end_time})"
    
    def calculate_work_hours(self):
        """حساب ساعات العمل من وقت البداية والنهاية"""
        if self.start_time and self.end_time:
            # تحويل الأوقات إلى datetime للحساب
            start = datetime.combine(datetime.today(), self.start_time)
            end = datetime.combine(datetime.today(), self.end_time)
            
            # إذا كان وقت النهاية أقل من البداية، معناها الوردية تمتد لليوم التالي
            if end < start:
                end += timedelta(days=1)
            
            # حساب الفرق بالساعات
            delta = end - start
            hours = delta.total_seconds() / 3600
            
            return round(hours, 2)
        return 8

    def calculate_ramadan_work_hours(self):
        """حساب ساعات العمل في رمضان من وقت البداية والنهاية الرمضانيين"""
        if self.ramadan_start_time and self.ramadan_end_time:
            start = datetime.combine(datetime.today(), self.ramadan_start_time)
            end = datetime.combine(datetime.today(), self.ramadan_end_time)

            if end < start:
                end += timedelta(days=1)

            delta = end - start
            hours = delta.total_seconds() / 3600
            return round(hours, 2)
        return 6
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class Attendance(models.Model):
    """نموذج سجل الحضور والانصراف"""
    
    STATUS_CHOICES = [
        ('present', 'حاضر'),
        ('absent', 'غائب'),
        ('late', 'متأخر'),
        ('half_day', 'نصف يوم'),
        ('on_leave', 'في إجازة'),
        ('permission', 'في إذن'),
    ]
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='attendances',
        verbose_name='الموظف'
    )
    date = models.DateField(verbose_name='التاريخ')
    shift = models.ForeignKey(
        Shift,
        on_delete=models.PROTECT,
        verbose_name='الوردية'
    )
    
    # أوقات الحضور والانصراف
    check_in = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='وقت الحضور'
    )
    check_out = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='وقت الانصراف'
    )
    
    # الحسابات
    work_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='ساعات العمل'
    )
    late_minutes = models.IntegerField(
        default=0,
        verbose_name='دقائق التأخير'
    )
    early_leave_minutes = models.IntegerField(
        default=0,
        verbose_name='دقائق الانصراف المبكر'
    )
    overtime_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='ساعات العمل الإضافي'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='present',
        verbose_name='الحالة'
    )
    
    # معامل الغياب (1 = عادي، 2 = مضاعف، 3 = ثلاثي)
    absence_multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=1.0,
        verbose_name='معامل الغياب',
        help_text='يؤثر على حساب خصم هذا اليوم فقط'
    )
    
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    # الموافقات
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_attendances',
        verbose_name='اعتمد بواسطة'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'حضور'
        verbose_name_plural = 'سجل الحضور'
        unique_together = ['employee', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.date}"
    
    def calculate_work_hours(self):
        """حساب ساعات العمل الفعلية - بدون save، الـ caller هو المسؤول عن الحفظ"""
        if self.check_in and self.check_out:
            from django.utils import timezone
            
            check_in = self.check_in
            check_out = self.check_out
            
            # التأكد من أن التواريخ timezone-aware
            if timezone.is_naive(check_in):
                check_in = timezone.make_aware(check_in)
            if timezone.is_naive(check_out):
                check_out = timezone.make_aware(check_out)
            
            delta = check_out - check_in
            hours = delta.total_seconds() / 3600
            self.work_hours = round(hours, 2)
            
            # حساب العمل الإضافي
            shift_hours = self.shift.calculate_work_hours()
            if self.work_hours > shift_hours:
                self.overtime_hours = self.work_hours - shift_hours

    def get_adjusted_late_minutes(self):
        """
        حساب دقائق التأخير مع مراعاة رمضان
        يستخدم AttendanceService للحساب لضمان consistency
        """
        if not self.check_in:
            return 0
        
        from hr.services.attendance_service import AttendanceService
        return AttendanceService._calculate_late_minutes(self.check_in, self.shift, self.date)

    def get_adjusted_early_leave_minutes(self):
        """
        حساب دقائق الانصراف المبكر مع مراعاة رمضان
        يستخدم AttendanceService للحساب لضمان consistency
        """
        if not self.check_out:
            return 0
        
        from hr.services.attendance_service import AttendanceService
        return AttendanceService._calculate_early_leave(self.check_out, self.shift, self.date)


class RamadanSettings(models.Model):
    """إعدادات شهر رمضان - تواريخ البداية والنهاية لكل سنة هجرية"""

    hijri_year = models.IntegerField(
        unique=True,
        verbose_name='السنة الهجرية'
    )
    start_date = models.DateField(verbose_name='تاريخ بداية رمضان')
    end_date = models.DateField(verbose_name='تاريخ نهاية رمضان')
    
    permission_max_count = models.PositiveIntegerField(
        default=2,
        verbose_name='الحد الأقصى لعدد الأذونات في رمضان'
    )
    permission_max_hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        verbose_name='الحد الأقصى لساعات الأذونات في رمضان'
    )

    class Meta:
        verbose_name = 'إعدادات رمضان'
        verbose_name_plural = 'إعدادات رمضان'
        ordering = ['-hijri_year']

    def __str__(self):
        return f"رمضان {self.hijri_year} هـ ({self.start_date} - {self.end_date})"

    @property
    def duration_days(self):
        """عدد أيام رمضان"""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError('تاريخ النهاية يجب أن يكون بعد تاريخ البداية')


class AttendancePenalty(models.Model):
    """جدول الجزاءات الديناميكي - نطاقات دقائق التأخير وقيمة الجزاء بالأيام"""

    name = models.CharField(max_length=100, verbose_name='اسم الجزاء')
    max_minutes = models.IntegerField(
        verbose_name='الحد الأقصى للدقائق',
        help_text='0 يعني نطاق مفتوح يطبق على ما يتجاوز كل النطاقات'
    )
    penalty_days = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        verbose_name='قيمة الجزاء (أيام)'
    )
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    order = models.IntegerField(default=0, verbose_name='الترتيب')

    class Meta:
        verbose_name = 'جزاء حضور'
        verbose_name_plural = 'جدول الجزاءات'
        ordering = ['order', 'max_minutes']

    def __str__(self):
        if self.max_minutes == 0:
            return f"{self.name} (نطاق مفتوح) → {self.penalty_days} يوم"
        return f"{self.name} (حتى {self.max_minutes} دقيقة) → {self.penalty_days} يوم"
