"""
خدمة إدارة الجزاءات والمكافآت
"""
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class PenaltyRewardService:
    """خدمة إدارة الجزاءات والمكافآت"""

    @staticmethod
    @transaction.atomic
    def create(employee, data, created_by):
        """
        إنشاء جزاء/مكافأة جديد

        Args:
            employee: الموظف
            data: dict يحتوي على category, date, month, calculation_method, value, reason
            created_by: المستخدم المنشئ

        Returns:
            PenaltyReward
        """
        from hr.models import PenaltyReward

        pr = PenaltyReward(
            employee=employee,
            category=data['category'],
            date=data['date'],
            month=data['month'],
            calculation_method=data['calculation_method'],
            value=Decimal(str(data['value'])),
            reason=data['reason'],
            created_by=created_by,
            status='pending',
        )
        pr.calculate_amount()
        pr.save()

        logger.info(
            f"تم إنشاء {'جزاء' if pr.category == 'penalty' else 'مكافأة'} "
            f"للموظف {employee.get_full_name_ar()} بمبلغ {pr.calculated_amount} ج.م"
        )
        return pr

    @staticmethod
    @transaction.atomic
    def approve(penalty_reward, approver, notes=''):
        """اعتماد الجزاء/المكافأة"""
        if penalty_reward.status != 'pending':
            raise ValidationError('يمكن اعتماد الطلبات المعلقة فقط')

        penalty_reward.status = 'approved'
        penalty_reward.approved_by = approver
        penalty_reward.approved_at = timezone.now()
        penalty_reward.review_notes = notes
        penalty_reward.save()

        return penalty_reward

    @staticmethod
    @transaction.atomic
    def reject(penalty_reward, approver, notes):
        """رفض الجزاء/المكافأة"""
        if penalty_reward.status != 'pending':
            raise ValidationError('يمكن رفض الطلبات المعلقة فقط')

        if not notes or not notes.strip():
            raise ValidationError('يجب إدخال سبب الرفض')

        penalty_reward.status = 'rejected'
        penalty_reward.approved_by = approver
        penalty_reward.approved_at = timezone.now()
        penalty_reward.review_notes = notes
        penalty_reward.save()

        return penalty_reward

    @staticmethod
    @transaction.atomic
    def apply_to_payroll(penalty_reward, payroll):
        """
        تطبيق الجزاء/المكافأة على قسيمة الراتب كـ PayrollLine
        يُستدعى تلقائياً أثناء معالجة الرواتب
        """
        from hr.models import PayrollLine

        if penalty_reward.status != 'approved':
            raise ValidationError('يمكن تطبيق الجزاءات/المكافآت المعتمدة فقط')

        if penalty_reward.payroll_id:
            raise ValidationError('تم تطبيق هذا الجزاء/المكافأة مسبقاً')

        is_penalty = penalty_reward.category == 'penalty'
        component_type = 'deduction' if is_penalty else 'earning'
        label = 'جزاء' if is_penalty else 'مكافأة'
        source = 'deduction' if is_penalty else 'bonus'

        # اقتطاع السبب لـ 60 حرف للعرض في البند
        short_reason = penalty_reward.reason[:60]

        PayrollLine.objects.create(
            payroll=payroll,
            code=f"{'PENALTY' if is_penalty else 'REWARD'}_{penalty_reward.id}",
            name=f"{label}: {short_reason}",
            component_type=component_type,
            source=source,
            quantity=1,
            rate=penalty_reward.calculated_amount,
            amount=penalty_reward.calculated_amount,
            description=penalty_reward.reason,
            calculation_details={
                'penalty_reward_id': penalty_reward.id,
                'category': penalty_reward.category,
                'calculation_method': penalty_reward.calculation_method,
                'value': str(penalty_reward.value),
                'date': str(penalty_reward.date),
            },
            order=400,
        )

        penalty_reward.payroll = payroll
        penalty_reward.status = 'applied'
        penalty_reward.applied_at = timezone.now()
        penalty_reward.save()

        # إعادة حساب إجماليات الراتب
        payroll.calculate_totals_from_lines()
        payroll.save()

        return penalty_reward

    @staticmethod
    def get_approved_for_month(employee, month):
        """
        الحصول على الجزاءات/المكافآت المعتمدة لشهر معين
        تُستخدم في معالجة الرواتب
        """
        from hr.models import PenaltyReward

        return PenaltyReward.objects.filter(
            employee=employee,
            month=month,
            status='approved',
        ).select_related('employee')

    @staticmethod
    def check_pending_for_month(employee, month):
        """
        التحقق من وجود جزاءات/مكافآت معلقة قبل اعتماد الراتب

        Returns:
            tuple: (has_pending: bool, count: int)
        """
        from hr.models import PenaltyReward

        count = PenaltyReward.objects.filter(
            employee=employee,
            month=month,
            status='pending',
        ).count()

        return count > 0, count
