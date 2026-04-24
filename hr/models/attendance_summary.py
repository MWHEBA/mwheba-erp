"""
نموذج ملخص الحضور الشهري
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import logging
import json

User = get_user_model()
logger = logging.getLogger(__name__)


class AttendanceSummary(models.Model):
    """ملخص الحضور الشهري للموظف"""
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='attendance_summaries',
        verbose_name='الموظف'
    )
    month = models.DateField(verbose_name='الشهر')
    
    # إحصائيات الحضور
    total_working_days = models.IntegerField(
        default=0,
        verbose_name='إجمالي أيام العمل',
        help_text='عدد أيام العمل في الشهر (بدون الجمع والعطلات)'
    )
    present_days = models.IntegerField(
        default=0,
        verbose_name='أيام الحضور'
    )
    absent_days = models.IntegerField(
        default=0,
        verbose_name='أيام الغياب'
    )
    late_days = models.IntegerField(
        default=0,
        verbose_name='أيام التأخير'
    )
    half_days = models.IntegerField(
        default=0,
        verbose_name='أيام نصف يوم'
    )
    
    # الإجازات
    paid_leave_days = models.IntegerField(
        default=0,
        verbose_name='أيام الإجازات المدفوعة'
    )
    unpaid_leave_days = models.IntegerField(
        default=0,
        verbose_name='أيام الإجازات غير المدفوعة'
    )
    
    # الساعات
    total_work_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='إجمالي ساعات العمل'
    )
    total_late_minutes = models.IntegerField(
        default=0,
        verbose_name='إجمالي دقائق التأخير'
    )
    total_early_leave_minutes = models.IntegerField(
        default=0,
        verbose_name='إجمالي دقائق الانصراف المبكر'
    )
    total_overtime_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='إجمالي ساعات العمل الإضافي'
    )
    
    # الدقائق الصافية القابلة للجزاء (بعد خصم السماح)
    net_penalizable_minutes = models.IntegerField(
        default=0,
        verbose_name='الدقائق الصافية القابلة للجزاء'
    )

    # الأذونات الإضافية
    extra_permissions_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='ساعات الأذونات الإضافية'
    )
    extra_permissions_deduction_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='مبلغ خصم الأذونات الإضافية'
    )

    # الحسابات المالية
    absence_deduction_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='مبلغ خصم الغياب'
    )
    
    # معامل الغياب (1 = عادي، 2 = مضاعف، 3 = ثلاثي)
    absence_multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal('1.0'),
        verbose_name='معامل الغياب',
        help_text='1 = عادي، 2 = مضاعف، 3 = ثلاثي'
    )
    
    late_deduction_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='مبلغ خصم التأخير'
    )
    overtime_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='مبلغ العمل الإضافي'
    )
    
    # الحالة
    is_calculated = models.BooleanField(
        default=False,
        verbose_name='تم الحساب'
    )
    is_approved = models.BooleanField(
        default=False,
        verbose_name='معتمد'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_attendance_summaries',
        verbose_name='اعتمد بواسطة'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    # ملاحظات
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    calculation_details = models.JSONField(
        null=True,
        blank=True,
        verbose_name='تفاصيل الحساب'
    )
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    class Meta:
        verbose_name = 'ملخص حضور شهري'
        verbose_name_plural = 'ملخصات الحضور الشهرية'
        unique_together = ['employee', 'month']
        ordering = ['-month', 'employee']
        indexes = [
            models.Index(fields=['employee', 'month']),
            models.Index(fields=['month', 'is_calculated']),
            models.Index(fields=['is_approved']),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.month.strftime('%Y-%m')}"
    
    def calculate(self):
        """
        حساب ملخص الحضور للشهر
        
        FIX #20: Make attendance calculation atomic
        """
        from .attendance import Attendance
        from .leave import Leave
        from django.db import transaction
        
        # Guard: prevent recalculation if payroll already calculated for this month
        payroll_exists = self.employee.payrolls.filter(
            month=self.month,
            status__in=['calculated', 'approved', 'paid']
        ).exists()
        if payroll_exists and self.is_approved:
            raise ValueError(
                f'لا يمكن إعادة حساب ملخص الحضور للموظف {self.employee.get_full_name_ar()} '
                f'لشهر {self.month.strftime("%Y-%m")} — تم حساب الراتب بالفعل'
            )
        
        
        try:
            with transaction.atomic():
                # تحديد بداية ونهاية الدورة (تدعم الدورة المرنة)
                from hr.utils.payroll_helpers import get_payroll_period
                start_date, end_date, _ = get_payroll_period(self.month)
                
                # إنشاء السجلات الناقصة كغياب قبل الحساب (للموظفين غير المعفيين فقط)
                from hr.services.attendance_service import AttendanceService
                try:
                    if not self.employee.attendance_exempt:
                        # ننشئ غيابات حتى نهاية الشهر أو الأمس (أيهما أقرب)
                        from django.utils import timezone
                        today = timezone.now().date()
                        max_date = min(end_date, today - timedelta(days=1))
                        if start_date <= max_date:
                            AttendanceService.generate_missing_attendances(start_date, max_date)
                except Exception as e:
                    logger.error(f"Error generating missing attendances before summary calc: {e}")
                
                # جلب أيام الإجازة الأسبوعية والرسمية لاستثنائها من الحساب
                from hr.services.attendance_service import AttendanceService as _AS
                from core.models import SystemSetting

                _off_days = SystemSetting.get_setting('hr_weekly_off_days', [4])
                if isinstance(_off_days, str):
                    _off_days = json.loads(_off_days)
                _official_holidays = _AS.get_official_holiday_dates(start_date, end_date)

                # بناء قائمة التواريخ المستثناة (إجازة أسبوعية + رسمية)
                _excluded_dates = set()
                _cur = start_date
                while _cur <= end_date:
                    if _cur.weekday() in _off_days or _cur in _official_holidays:
                        _excluded_dates.add(_cur)
                    _cur += timedelta(days=1)

                # جلب سجلات الحضور مع الوردية (select_related لتجنب N+1 queries)
                # استثناء أيام الإجازة الأسبوعية والرسمية من الحساب
                attendance_records = Attendance.objects.filter(
                    employee=self.employee,
                    date__gte=start_date,
                    date__lte=end_date
                ).exclude(
                    date__in=_excluded_dates
                ).select_related('shift')

                if self.employee.attendance_exempt:
                    # المعفيون: نستثني سجلات الغياب من الحساب
                    attendance_records = attendance_records.exclude(status='absent')
                
                # حساب الإحصائيات
                self.present_days = attendance_records.filter(
                    status__in=['present', 'late', 'half_day']
                ).count()

                # استثناء أيام الإجازات المعتمدة من الغياب
                approved_leave_dates = set()
                approved_leaves = Leave.objects.filter(
                    employee=self.employee,
                    status='approved',
                    start_date__lte=end_date,
                    end_date__gte=start_date
                )
                for lv in approved_leaves:
                    cur = max(lv.start_date, start_date)
                    while cur <= min(lv.end_date, end_date):
                        approved_leave_dates.add(cur)
                        cur += timedelta(days=1)

                self.absent_days = attendance_records.filter(
                    status='absent'
                ).exclude(
                    date__in=approved_leave_dates
                ).count()

                self.late_days = attendance_records.filter(status='late').count()
                self.half_days = attendance_records.filter(status='half_day').count()
                
                # حساب الساعات
                totals = attendance_records.aggregate(
                    total_hours=Sum('work_hours'),
                    total_late=Sum('late_minutes'),
                    total_early=Sum('early_leave_minutes'),
                    total_overtime=Sum('overtime_hours')
                )
                
                self.total_work_hours = totals['total_hours'] or Decimal('0')
                self.total_late_minutes = totals['total_late'] or 0
                self.total_early_leave_minutes = totals['total_early'] or 0
                self.total_overtime_hours = totals['total_overtime'] or Decimal('0')

                # حساب الدقائق الصافية القابلة للجزاء مع مراعاة الأذونات المعتمدة
                from core.models import SystemSetting
                from .permission import PermissionRequest
                from hr.services.attendance_service import AttendanceService

                # جلب الأذونات المعتمدة للشهر مجمعة بالتاريخ
                month_permissions = PermissionRequest.objects.filter(
                    employee=self.employee,
                    date__gte=start_date,
                    date__lte=end_date,
                    status='approved'
                ).select_related('permission_type')

                perms_by_date = {}
                for perm in month_permissions:
                    perms_by_date.setdefault(perm.date, []).append(perm)

                net_minutes = 0
                for att in attendance_records:
                    grace_in = att.shift.grace_period_in if att.shift else 0
                    grace_out = att.shift.grace_period_out if att.shift else 0

                    # حساب دقائق التأخير الخام من check_in مباشرة (بدون الاعتماد على القيمة المحفوظة)
                    if att.check_in and att.shift:
                        raw_late = AttendanceService._calculate_late_minutes(att.check_in, att.shift, att.date)
                    else:
                        raw_late = att.late_minutes or 0

                    # حساب الانصراف المبكر الخام من check_out مباشرة
                    if att.check_out and att.shift:
                        raw_early = AttendanceService._calculate_early_leave(att.check_out, att.shift, att.date)
                    else:
                        raw_early = att.early_leave_minutes or 0

                    # جلب أذونات هذا اليوم
                    day_perms = perms_by_date.get(att.date, [])

                    # حساب دقائق إذن الحضور المتأخر (LATE_ARRIVAL)
                    late_permission_minutes = 0
                    has_early_leave_permission = False
                    for perm in day_perms:
                        code = perm.permission_type.code
                        if code == 'LATE_ARRIVAL':
                            late_permission_minutes += int(float(perm.duration_hours) * 60)
                        elif code == 'EARLY_LEAVE':
                            has_early_leave_permission = True
                        # أذونات الخروج من الدوام (LEAVE_WORK وما شابهها) تُتجاهل

                    # التأخير بعد خصم إذن الحضور المتأخر
                    # لو التأخير ≤ مدة الإذن → 0، لو أكتر → (التأخير - مدة الإذن)
                    effective_late = max(0, raw_late - late_permission_minutes)

                    # الانصراف المبكر: يُتجاهل لو في إذن انصراف مبكر
                    effective_early = 0 if has_early_leave_permission else raw_early

                    # خصم السماح اليومي للوردية
                    net_minutes += max(0, effective_late - grace_in)
                    net_minutes += max(0, effective_early - grace_out)

                # خصم السماح الشهري المؤسسي
                monthly_grace = int(SystemSetting.get_setting('hr_monthly_grace_minutes', 0))
                self.net_penalizable_minutes = max(0, net_minutes - monthly_grace)
                
                # حساب الإجازات
                leaves = Leave.objects.filter(
                    employee=self.employee,
                    status='approved',
                    start_date__lte=end_date,
                    end_date__gte=start_date
                )
                
                # ❌ تم إزالة حساب الإجازات - يتم الاعتماد على LeaveSummary
                # الإجازات المدفوعة وغير المدفوعة تُحسب في LeaveSummary فقط
                self.paid_leave_days = 0
                self.unpaid_leave_days = 0
                
                # حساب أيام العمل الفعلية (بدون الجمع)
                self.total_working_days = self._calculate_working_days(start_date, end_date)
                
                # حساب خصم الأذونات الإضافية
                from .permission import PermissionRequest
                extra_permissions = PermissionRequest.objects.filter(
                    employee=self.employee,
                    status='approved',
                    is_extra=True,
                    date__gte=start_date,
                    date__lte=end_date
                )
                
                # حساب الساعات: فقط الأذونات غير المعفاة من الخصم
                self.extra_permissions_hours = Decimal(str(sum(
                    float(p.deduction_hours or p.duration_hours) 
                    for p in extra_permissions
                    if not p.is_deduction_exempt  # استثناء المعفيين من الخصم
                )))
                
                # حساب المبالغ المالية
                self._calculate_financial_amounts()
                
                self.is_calculated = True
                self.save()
                
                
        except Exception as e:
            logger.error(f"❌ فشل حساب ملخص الحضور: {e}")
            raise  # Rollback transaction
    
    def _calculate_working_days(self, start_date, end_date):
        """حساب أيام العمل بناءً على hr_weekly_off_days والإجازات الرسمية"""
        from core.models import SystemSetting
        from hr.services.attendance_service import AttendanceService

        working_days = 0
        current_date = start_date

        off_days = SystemSetting.get_setting('hr_weekly_off_days', [4])
        if isinstance(off_days, str):
            off_days = json.loads(off_days)

        official_holidays = AttendanceService.get_official_holiday_dates(start_date, end_date)

        while current_date <= end_date:
            if current_date.weekday() not in off_days and current_date not in official_holidays:
                working_days += 1
            current_date += timedelta(days=1)

        return working_days
    
    def _calculate_financial_amounts(self):
        """حساب المبالغ المالية باستخدام نظام الجزاءات الديناميكي"""
        from core.models import SystemSetting
        from .attendance import AttendancePenalty

        # الحصول على العقد النشط الذي بدأ قبل أو خلال شهر الملخص
        from hr.utils.payroll_helpers import get_payroll_period as _get_period
        _start, _end, _ = _get_period(self.month)
        contract = self.employee.contracts.filter(
            status='active',
            start_date__lte=_end
        ).order_by('-start_date').first()
        if not contract:
            logger.debug(f"لا يوجد عقد نشط للموظف {self.employee.get_full_name_ar()} - تم تخطي حساب المبالغ المالية")
            return

        # حساب الراتب اليومي
        daily_salary = (Decimal(str(contract.basic_salary)) / Decimal('30')).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )

        # حساب خصم الغياب مع معامل كل يوم على حدة
        absence_deduction = Decimal('0')
        if self.absent_days > 0:
            # جلب أيام الغياب الفعلية (تدعم الدورة المرنة)
            from hr.utils.payroll_helpers import get_payroll_period
            from hr.models import Attendance
            start_date, end_date, _ = get_payroll_period(self.month)
            
            absent_records = Attendance.objects.filter(
                employee=self.employee,
                date__gte=start_date,
                date__lte=end_date,
                status='absent'
            )
            
            # استثناء أيام الإجازة الأسبوعية والرسمية
            from hr.services.attendance_service import AttendanceService as _AS
            _off_days_fin = SystemSetting.get_setting('hr_weekly_off_days', [4])
            if isinstance(_off_days_fin, str):
                import json as _json
                _off_days_fin = _json.loads(_off_days_fin)
            _holidays_fin = _AS.get_official_holiday_dates(start_date, end_date)
            _excl_fin = set()
            _c = start_date
            while _c <= end_date:
                if _c.weekday() in _off_days_fin or _c in _holidays_fin:
                    _excl_fin.add(_c)
                _c += timedelta(days=1)
            absent_records = absent_records.exclude(date__in=_excl_fin)

            # استثناء أيام الإجازات المعتمدة من خصم الغياب
            from .leave import Leave as _Leave
            _approved_leave_dates = set()
            for lv in _Leave.objects.filter(
                employee=self.employee,
                status='approved',
                start_date__lte=end_date,
                end_date__gte=start_date
            ):
                _cur = max(lv.start_date, start_date)
                while _cur <= min(lv.end_date, end_date):
                    _approved_leave_dates.add(_cur)
                    _cur += timedelta(days=1)
            if _approved_leave_dates:
                absent_records = absent_records.exclude(date__in=_approved_leave_dates)
            # حساب خصم كل يوم بمعامله الخاص + حفظ snapshot
            absence_details = []
            for record in absent_records:
                day_deduction = daily_salary * record.absence_multiplier
                absence_deduction += day_deduction
                absence_details.append({
                    'date': record.date.isoformat(),
                    'multiplier': str(record.absence_multiplier),
                    'deduction': str(day_deduction.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                })
            
            self.absence_deduction_amount = absence_deduction.quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP
            )
            
            # حفظ snapshot في calculation_details
            if not self.calculation_details:
                self.calculation_details = {}
            self.calculation_details['absence_snapshot'] = {
                'absent_days': len(absence_details),
                'daily_salary': str(daily_salary),
                'total_deduction': str(self.absence_deduction_amount),
                'details': absence_details
            }
        else:
            self.absence_deduction_amount = Decimal('0')

        # ❌ تم إزالة خصم الإجازات غير المدفوعة من هنا
        # الخصم يتم من LeaveSummary.deduction_amount مع دعم deduction_multiplier

        # حساب خصم التأخير من جدول AttendancePenalty
        if self.net_penalizable_minutes > 0:
            # أصغر نطاق max_minutes >= net_penalizable_minutes
            penalty = AttendancePenalty.objects.filter(
                is_active=True,
                max_minutes__gte=self.net_penalizable_minutes
            ).order_by('max_minutes').first()

            # fallback: النطاق المفتوح (max_minutes=0) لو تجاوز كل النطاقات
            if not penalty:
                penalty = AttendancePenalty.objects.filter(
                    is_active=True,
                    max_minutes=0
                ).first()

            if penalty:
                self.late_deduction_amount = (
                    penalty.penalty_days * daily_salary
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                
                # حفظ snapshot لخصم التأخير
                if not self.calculation_details:
                    self.calculation_details = {}
                self.calculation_details['late_deduction_snapshot'] = {
                    'net_penalizable_minutes': self.net_penalizable_minutes,
                    'penalty_id': penalty.id,
                    'penalty_name': penalty.name,
                    'penalty_days': str(penalty.penalty_days),
                    'penalty_max_minutes': penalty.max_minutes,
                    'daily_salary': str(daily_salary),
                    'total_deduction': str(self.late_deduction_amount)
                }
            else:
                self.late_deduction_amount = Decimal('0')
        else:
            self.late_deduction_amount = Decimal('0')

        # حساب خصم الأذونات الإضافية
        if self.extra_permissions_hours and self.extra_permissions_hours > 0:
            # استخدام ساعات العمل الفعلية من الوردية
            shift = getattr(self.employee, 'shift', None)
            
            if shift:
                # محاولة استخدام الساعات المحسوبة ديناميكياً
                shift_hours = Decimal(str(shift.calculate_work_hours()))
                if shift_hours <= Decimal('0'):
                    shift_hours = Decimal('8')
            else:
                shift_hours = Decimal('8')

            hourly_salary = daily_salary / shift_hours
            self.extra_permissions_deduction_amount = (
                Decimal(str(self.extra_permissions_hours)) * hourly_salary
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            self.extra_permissions_deduction_amount = Decimal('0')

        # حساب العمل الإضافي (مشروط بـ hr_overtime_enabled)
        overtime_enabled = SystemSetting.get_setting('hr_overtime_enabled', False)
        if overtime_enabled and self.total_overtime_hours > 0:
            # استخدام ساعات العمل الفعلية من الوردية
            shift = getattr(self.employee, 'shift', None)
            
            if shift:
                # محاولة استخدام الساعات المحسوبة ديناميكياً
                shift_hours = Decimal(str(shift.calculate_work_hours()))
                if shift_hours <= Decimal('0'):
                    shift_hours = Decimal('8')
            else:
                shift_hours = Decimal('8')

            hourly_salary = daily_salary / shift_hours
            overtime_rate = hourly_salary * Decimal('1.5')
            self.overtime_amount = (
                Decimal(str(self.total_overtime_hours)) * overtime_rate
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            self.overtime_amount = Decimal('0')
    
    def approve(self, approved_by):
        """اعتماد ملخص الحضور"""
        from django.utils import timezone

        if not self.is_calculated:
            raise ValueError(
                f'لا يمكن اعتماد ملخص الحضور للموظف {self.employee.get_full_name_ar()} '
                f'لشهر {self.month.strftime("%Y-%m")} — يجب حساب الملخص أولاً'
            )

        # Guard: prevent re-approval only if already approved AND payroll already calculated
        if self.is_approved:
            payroll_exists = self.employee.payrolls.filter(
                month=self.month,
                status__in=['calculated', 'approved', 'paid']
            ).exists()
            if payroll_exists:
                raise ValueError(
                    f'لا يمكن تعديل اعتماد ملخص الحضور للموظف {self.employee.get_full_name_ar()} '
                    f'لشهر {self.month.strftime("%Y-%m")} — تم حساب الراتب بالفعل'
                )

        self.is_approved = True
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save()
        
    
    @property
    def attendance_rate(self):
        """نسبة الحضور"""
        if self.total_working_days > 0:
            return (self.present_days / self.total_working_days) * 100
        return 0
    
    @property
    def total_deductions(self):
        """إجمالي الخصومات"""
        return self.absence_deduction_amount + self.late_deduction_amount + self.extra_permissions_deduction_amount

