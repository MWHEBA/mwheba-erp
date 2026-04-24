"""
خدمة تدقيق قسائم الرواتب - تسجيل كل تعديل ومن قام به ومتى
"""
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class PayrollAuditService:
    """تسجيل جميع العمليات على قسائم الرواتب"""

    # الحقول اللي بنحفظها في الـ snapshot
    SNAPSHOT_FIELDS = [
        'status', 'basic_salary', 'gross_salary', 'net_salary',
        'total_additions', 'total_deductions', 'advance_deduction',
        'absence_days', 'absence_deduction', 'late_deduction',
        'overtime_amount', 'bonus', 'social_insurance', 'tax',
    ]

    @classmethod
    def _build_snapshot(cls, payroll):
        """بناء snapshot مختصر للحالة الحالية للقسيمة"""
        snapshot = {}
        for field in cls.SNAPSHOT_FIELDS:
            val = getattr(payroll, field, None)
            snapshot[field] = str(val) if val is not None else None
        return snapshot

    @classmethod
    def log(cls, payroll, action, performed_by, notes='', include_snapshot=True):
        """
        تسجيل عملية على قسيمة الراتب.

        Args:
            payroll: كائن Payroll
            action: نوع العملية (من ACTION_CHOICES)
            performed_by: المستخدم الذي نفذ العملية
            notes: ملاحظات إضافية (اختياري)
            include_snapshot: هل نحفظ snapshot للبيانات
        """
        try:
            from hr.models import PayrollAuditLog
            snapshot = cls._build_snapshot(payroll) if include_snapshot else None
            PayrollAuditLog.objects.create(
                payroll=payroll,
                action=action,
                performed_by=performed_by,
                notes=notes,
                snapshot=snapshot,
            )
        except Exception as e:
            # لا نوقف العملية الأصلية لو فشل التسجيل
            logger.error(f"فشل تسجيل audit للقسيمة {payroll.pk}: {e}")

    @classmethod
    def log_calculated(cls, payroll, performed_by):
        cls.log(payroll, 'calculated', performed_by,
                notes=f'تم حساب الراتب - صافي: {payroll.net_salary} ج.م')

    @classmethod
    def log_recalculated(cls, payroll, performed_by):
        cls.log(payroll, 'recalculated', performed_by,
                notes=f'تمت إعادة الحساب - صافي جديد: {payroll.net_salary} ج.م')

    @classmethod
    def log_lines_edited(cls, payroll, performed_by, changes_summary=''):
        notes = f'تم تعديل البنود'
        if changes_summary:
            notes += f' - {changes_summary}'
        cls.log(payroll, 'lines_edited', performed_by, notes=notes)

    @classmethod
    def log_approved(cls, payroll, performed_by):
        cls.log(payroll, 'approved', performed_by,
                notes=f'تم الاعتماد - صافي: {payroll.net_salary} ج.م')

    @classmethod
    def log_unapproved(cls, payroll, performed_by):
        cls.log(payroll, 'unapproved', performed_by,
                notes='تم إلغاء الاعتماد بواسطة المدير العام')

    @classmethod
    def log_paid(cls, payroll, performed_by):
        account_name = ''
        if payroll.payment_account:
            account_name = f' - الحساب: {payroll.payment_account.name}'
        cls.log(payroll, 'paid', performed_by,
                notes=f'تم الدفع - المبلغ: {payroll.net_salary} ج.م{account_name}')
