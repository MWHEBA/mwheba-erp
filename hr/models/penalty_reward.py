"""
نموذج الجزاءات والمكافآت
"""
from django.db import models
from django.contrib.auth import get_user_model
from decimal import Decimal, ROUND_HALF_UP

User = get_user_model()


class PenaltyReward(models.Model):
    """سجل الجزاءات والمكافآت"""

    CATEGORY_CHOICES = [
        ('penalty', 'جزاء'),
        ('reward', 'مكافأة'),
    ]

    CALCULATION_METHOD_CHOICES = [
        ('fixed', 'قيمة ثابتة'),
        ('days', 'بالأيام'),
        ('hours', 'بالساعات'),
    ]

    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('approved', 'معتمد'),
        ('rejected', 'مرفوض'),
        ('applied', 'مطبق'),
    ]

    # الأساسيات
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='penalties_rewards',
        verbose_name='الموظف'
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        verbose_name='النوع'
    )

    # التاريخ
    date = models.DateField(verbose_name='التاريخ')
    month = models.DateField(
        verbose_name='شهر التطبيق',
        help_text='الشهر الذي سيتم فيه تطبيق الجزاء/المكافأة على الراتب'
    )

    # الحساب
    calculation_method = models.CharField(
        max_length=20,
        choices=CALCULATION_METHOD_CHOICES,
        verbose_name='طريقة الحساب'
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='القيمة/العدد',
        help_text='المبلغ الثابت، أو عدد الأيام، أو عدد الساعات'
    )
    calculated_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='المبلغ المحسوب'
    )

    # التفاصيل
    reason = models.TextField(verbose_name='السبب/التفاصيل')

    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )

    # سير العمل
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_penalties_rewards',
        verbose_name='أنشئ بواسطة'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')

    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_penalties_rewards',
        verbose_name='اعتمد/رفض بواسطة'
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الاعتماد/الرفض')
    review_notes = models.TextField(blank=True, verbose_name='ملاحظات المراجعة')

    # الربط مع الراتب
    payroll = models.ForeignKey(
        'Payroll',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='penalties_rewards',
        verbose_name='قسيمة الراتب'
    )
    applied_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ التطبيق')

    class Meta:
        verbose_name = 'جزاء/مكافأة'
        verbose_name_plural = 'الجزاءات والمكافآت'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['month', 'status']),
            models.Index(fields=['category']),
        ]
        permissions = [
            ("can_approve_penalty_reward", "اعتماد الجزاءات والمكافآت"),
        ]

    def __str__(self):
        return (
            f"{'جزاء' if self.category == 'penalty' else 'مكافأة'} - "
            f"{self.employee.get_full_name_ar()} - "
            f"{self.date} - {self.calculated_amount} ج.م"
        )

    def clean(self):
        """التحقق من صحة التاريخ"""
        from django.core.exceptions import ValidationError
        if self.date and not self.pk:
            from hr.utils import validate_entry_date
            errors = validate_entry_date(self.date, 'date')
            if errors:
                raise ValidationError(errors)

    def calculate_amount(self):
        """
        حساب المبلغ بنفس منطق الأذونات:
        - يراعي الشيفت الخاص بالموظف
        - يراعي رمضان (أوقات الشيفت في رمضان)
        - يحسب بناءً على تاريخ الجزاء/المكافأة
        """
        if self.calculation_method == 'fixed':
            self.calculated_amount = self.value
            return self.calculated_amount

        # الحصول على العقد النشط للشهر المحدد (مع دعم الدورة المرنة)
        from django.db.models import Q
        from hr.utils.payroll_helpers import get_payroll_period
        _, period_end, _ = get_payroll_period(self.month)
        contract = self.employee.contracts.filter(
            status='active',
            start_date__lte=period_end
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=self.month)
        ).order_by('-start_date').first()
        if not contract:
            self.calculated_amount = self.value
            return self.calculated_amount

        basic_salary = Decimal(str(contract.basic_salary))

        if self.calculation_method == 'days':
            daily_rate = (basic_salary / Decimal('30')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            self.calculated_amount = (self.value * daily_rate).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        elif self.calculation_method == 'hours':
            # نفس منطق AttendanceSummary._calculate_financial_amounts
            shift = getattr(self.employee, 'shift', None)
            if shift:
                try:
                    shift_hours = Decimal(str(shift.calculate_work_hours()))
                    if shift_hours <= Decimal('0'):
                        shift_hours = Decimal('8')
                except Exception:
                    shift_hours = Decimal('8')

                # مراعاة رمضان: لو التاريخ في رمضان نستخدم ساعات الشيفت الرمضانية
                if shift.ramadan_start_time and shift.ramadan_end_time and self.date:
                    from hr.models.attendance import RamadanSettings
                    is_ramadan = RamadanSettings.objects.filter(
                        start_date__lte=self.date,
                        end_date__gte=self.date
                    ).exists()
                    if is_ramadan:
                        from datetime import datetime, date
                        ramadan_start = datetime.combine(date.today(), shift.ramadan_start_time)
                        ramadan_end = datetime.combine(date.today(), shift.ramadan_end_time)
                        ramadan_hours = (ramadan_end - ramadan_start).total_seconds() / 3600
                        if ramadan_hours > 0:
                            shift_hours = Decimal(str(ramadan_hours))
            else:
                shift_hours = Decimal('8')

            daily_rate = (basic_salary / Decimal('30')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            hourly_rate = (daily_rate / shift_hours).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            self.calculated_amount = (self.value * hourly_rate).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        return self.calculated_amount

    def save(self, *args, **kwargs):
        """حساب المبلغ تلقائياً عند الحفظ لو لم يُحسب"""
        if not self.calculated_amount or self.calculated_amount == Decimal('0'):
            self.calculate_amount()
        super().save(*args, **kwargs)
