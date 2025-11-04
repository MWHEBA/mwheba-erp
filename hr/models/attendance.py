"""
نماذج الحضور والانصراف
"""
from django.db import models
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta

User = get_user_model()


class Shift(models.Model):
    """نموذج الورديات"""
    
    SHIFT_TYPE_CHOICES = [
        ('morning', 'صباحية'),
        ('evening', 'مسائية'),
        ('night', 'ليلية'),
        ('rotating', 'متناوبة'),
    ]
    
    name = models.CharField(max_length=100, verbose_name='اسم الوردية')
    shift_type = models.CharField(
        max_length=20,
        choices=SHIFT_TYPE_CHOICES,
        verbose_name='نوع الوردية'
    )
    start_time = models.TimeField(verbose_name='وقت البداية')
    end_time = models.TimeField(verbose_name='وقت النهاية')
    
    # فترات السماح
    grace_period_in = models.IntegerField(
        default=15,
        verbose_name='فترة السماح للحضور (دقائق)'
    )
    grace_period_out = models.IntegerField(
        default=15,
        verbose_name='فترة السماح للانصراف (دقائق)'
    )
    
    # ساعات العمل
    work_hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        verbose_name='ساعات العمل',
        blank=True,
        null=True
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
        return 0
    
    def save(self, *args, **kwargs):
        """حساب ساعات العمل تلقائياً قبل الحفظ"""
        if not self.work_hours:
            self.work_hours = self.calculate_work_hours()
        super().save(*args, **kwargs)


class Attendance(models.Model):
    """نموذج سجل الحضور والانصراف"""
    
    STATUS_CHOICES = [
        ('present', 'حاضر'),
        ('absent', 'غائب'),
        ('late', 'متأخر'),
        ('half_day', 'نصف يوم'),
        ('on_leave', 'في إجازة'),
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
    check_in = models.DateTimeField(verbose_name='وقت الحضور')
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
        """حساب ساعات العمل الفعلية"""
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
            if self.work_hours > float(self.shift.work_hours):
                self.overtime_hours = self.work_hours - float(self.shift.work_hours)
            
            self.save()
