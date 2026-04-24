"""
خدمة إدارة الإجازات
"""
from django.db import transaction
from django.utils import timezone
from datetime import date
from ..models import Leave, LeaveBalance


class LeaveService:
    """خدمة إدارة الإجازات"""
    
    @staticmethod
    @transaction.atomic
    def request_leave(employee, leave_data):
        """
        طلب إجازة جديد
        
        Args:
            employee: الموظف
            leave_data: بيانات الإجازة
        
        Returns:
            Leave: طلب الإجازة
        """
        leave_type = leave_data['leave_type']
        start_date = leave_data['start_date']
        end_date = leave_data['end_date']
        
        # حساب عدد الأيام
        days_count = (end_date - start_date).days + 1
        
        # التحقق من الرصيد
        if not LeaveService._check_leave_balance(employee, leave_type, days_count, start_date):
            raise ValueError('رصيد الإجازات غير كافٍ')
        
        # إنشاء الطلب
        leave = Leave.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            reason=leave_data['reason'],
            status='pending'
        )
        
        return leave
    
    @staticmethod
    def _check_leave_balance(employee, leave_type, days_count, start_date):
        """التحقق من رصيد الإجازات المستحق"""

        # الإجازات الاستثنائية والمرضية وغير المدفوعة لا تحتاج رصيداً مسبقاً
        if not leave_type.requires_balance:
            return True

        leave_year = start_date.year
        
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=leave_year
            )
            # تحديث الاستحقاق قبل التحقق
            balance.update_accrued_days()
            
            # التحقق من الرصيد المتبقي (المستحق - المستخدم)
            return balance.remaining_days >= days_count
        except LeaveBalance.DoesNotExist:
            return False
    
    @staticmethod
    @transaction.atomic
    def approve_leave(leave, approver, review_notes=None):
        """
        اعتماد الإجازة
        
        Args:
            leave: الإجازة
            approver: المعتمد
            review_notes: ملاحظات المراجعة (اختياري)
        
        Returns:
            Leave: الإجازة المعتمدة
        """
        leave.status = 'approved'
        leave.approved_by = approver
        leave.approved_at = timezone.now()
        if review_notes:
            leave.review_notes = review_notes
        leave.save()
        
        # خصم من الرصيد
        LeaveService._deduct_from_balance(leave)
        
        # تحديث سجلات الحضور الموجودة من absent → on_leave
        LeaveService._mark_attendance_as_on_leave(leave)
        
        return leave
    
    @staticmethod
    def _deduct_from_balance(leave):
        """خصم الإجازة من الرصيد"""
        leave_year = leave.start_date.year
        
        try:
            balance = LeaveBalance.objects.get(
                employee=leave.employee,
                leave_type=leave.leave_type,
                year=leave_year
            )
            balance.used_days += leave.days_count
            balance.update_balance()
        except LeaveBalance.DoesNotExist:
            pass

    @staticmethod
    def _mark_attendance_as_on_leave(leave):
        """
        تحديث سجلات الحضور الموجودة من absent → on_leave
        يُستدعى عند اعتماد الإجازة
        """
        from ..models import Attendance, AttendanceSummary
        from hr.services.attendance_summary_service import AttendanceSummaryService
        from datetime import date

        updated = Attendance.objects.filter(
            employee=leave.employee,
            date__gte=leave.start_date,
            date__lte=leave.end_date,
            status='absent'
        ).update(status='on_leave', notes='تم التحديث تلقائياً عند اعتماد الإجازة')

        # إعادة حساب ملخصات الحضور المتأثرة (الأشهر التي تقع فيها الإجازة)
        if updated:
            today = date.today()
            affected_months = set()
            cur = leave.start_date.replace(day=1)
            end_month = leave.end_date.replace(day=1)
            while cur <= end_month:
                affected_months.add(cur)
                # الانتقال للشهر التالي
                if cur.month == 12:
                    cur = cur.replace(year=cur.year + 1, month=1)
                else:
                    cur = cur.replace(month=cur.month + 1)

            for month in affected_months:
                try:
                    summary = AttendanceSummary.objects.filter(
                        employee=leave.employee,
                        month=month
                    ).first()
                    if summary:
                        AttendanceSummaryService.recalculate_summary(summary)
                except ValueError:
                    # الراتب محسوب بالفعل - تجاهل
                    pass
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(
                        f'فشل إعادة حساب ملخص الحضور عند اعتماد الإجازة: {e}'
                    )

    @staticmethod
    def _restore_attendance_from_on_leave(leave):
        """
        إرجاع سجلات الحضور من on_leave → absent
        يُستدعى عند إلغاء الإجازة
        """
        from ..models import Attendance
        from datetime import date
        today = date.today()
        # فقط الأيام اللي لسه ما جاتش (المستقبل) - الماضي يفضل كما هو
        Attendance.objects.filter(
            employee=leave.employee,
            date__gte=today,
            date__lte=leave.end_date,
            status='on_leave'
        ).update(status='absent', notes='تم التحديث تلقائياً عند إلغاء الإجازة')
    
    @staticmethod
    @transaction.atomic
    def reject_leave(leave, reviewer, notes):
        """
        رفض الإجازة
        
        Args:
            leave: الإجازة
            reviewer: المراجع
            notes: ملاحظات الرفض
        
        Returns:
            Leave: الإجازة المرفوضة
        """
        leave.status = 'rejected'
        leave.reviewed_by = reviewer
        leave.reviewed_at = timezone.now()
        leave.review_notes = notes
        leave.save()
        
        return leave
    
    @staticmethod
    @transaction.atomic
    def cancel_leave(leave, cancelled_by, cancellation_reason=None):
        """
        إلغاء الإجازة مع استرداد الرصيد
        
        القواعد:
        - يمكن الإلغاء فقط قبل بداية الإجازة
        - يمكن الإلغاء للإجازات المعتمدة أو المعلقة
        - يتم استرداد الرصيد تلقائياً للإجازات المعتمدة
        
        Args:
            leave: الإجازة المراد إلغاؤها
            cancelled_by: المستخدم الذي ألغى الإجازة
            cancellation_reason: سبب الإلغاء (اختياري)
        
        Returns:
            Leave: الإجازة الملغاة
        
        Raises:
            ValueError: إذا لم يمكن الإلغاء
        """
        from django.utils import timezone
        
        # التحقق من الحالة
        if leave.status not in ['pending', 'approved']:
            raise ValueError(
                f'لا يمكن إلغاء إجازة في حالة "{leave.get_status_display()}"'
            )
        
        # التحقق من عدم استهلاك الإجازة (لم تبدأ بعد)
        today = date.today()
        if leave.start_date <= today:
            raise ValueError(
                'لا يمكن إلغاء إجازة بدأت بالفعل أو في الماضي. '
                f'تاريخ البداية: {leave.start_date}'
            )
        
        # استرداد الرصيد إذا كانت معتمدة
        if leave.status == 'approved':
            LeaveService._restore_balance(leave)
            # إرجاع سجلات الحضور المستقبلية من on_leave → absent
            LeaveService._restore_attendance_from_on_leave(leave)
        
        # تحديث حالة الإجازة
        leave.status = 'cancelled'
        leave.reviewed_by = cancelled_by
        leave.reviewed_at = timezone.now()
        if cancellation_reason:
            leave.review_notes = f"[ملغاة] {cancellation_reason}"
        leave.save()
        
        return leave
    
    @staticmethod
    def _restore_balance(leave):
        """استرداد الرصيد عند إلغاء إجازة معتمدة"""
        # فقط للإجازات التي تحتاج رصيد
        if not leave.leave_type.requires_balance:
            return
        
        leave_year = leave.start_date.year
        
        try:
            balance = LeaveBalance.objects.get(
                employee=leave.employee,
                leave_type=leave.leave_type,
                year=leave_year
            )
            balance.used_days -= leave.days_count
            balance.update_balance()
        except LeaveBalance.DoesNotExist:
            pass
    
    @staticmethod
    def calculate_leave_balance(employee, leave_type):
        """
        حساب رصيد الإجازات
        
        Args:
            employee: الموظف
            leave_type: نوع الإجازة
        
        Returns:
            dict: معلومات الرصيد
        """
        current_year = date.today().year
        
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=current_year
            )
            return {
                'total_days': balance.total_days,
                'used_days': balance.used_days,
                'remaining_days': balance.remaining_days,
            }
        except LeaveBalance.DoesNotExist:
            return {
                'total_days': 0,
                'used_days': 0,
                'remaining_days': 0,
            }
