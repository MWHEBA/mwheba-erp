"""
خدمة إدارة السلف والأقساط

هذه الخدمة مسؤولة عن:
- حساب خصم الأقساط الشهرية
- تسجيل دفعات الأقساط
- تحديث حالة السلف
- إنشاء سجلات الأقساط
"""

from decimal import Decimal
from datetime import date
from django.db import transaction
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class AdvanceService:
    """خدمة إدارة السلف"""
    
    @staticmethod
    def calculate_advance_deduction(employee, payroll_month):
        """
        حساب خصم السلف للموظف في شهر معين
        
        Args:
            employee: كائن الموظف
            payroll_month: تاريخ شهر الراتب
            
        Returns:
            tuple: (total_deduction, advances_list)
                - total_deduction: إجمالي المبلغ المخصوم
                - advances_list: قائمة السلف التي تم الخصم منها
        """
        from ..models import Advance
        
        # الحصول على السلف المعتمدة أو قيد الخصم للموظف
        advances = Advance.objects.filter(
            employee=employee,
            status__in=['approved', 'in_progress'],
            deduction_start_month__lte=payroll_month,
            remaining_amount__gt=0
        ).order_by('deduction_start_month')
        
        total_deduction = Decimal('0.00')
        processed_advances = []
        
        for advance in advances:
            # حساب مبلغ القسط لهذا الشهر
            installment_amount = advance.get_next_installment_amount()
            
            if installment_amount > 0:
                total_deduction += installment_amount
                processed_advances.append({
                    'advance': advance,
                    'amount': installment_amount
                })
        
        return total_deduction, processed_advances
    
    @staticmethod
    @transaction.atomic
    def record_advance_deduction(payroll, advance, amount):
        """
        تسجيل خصم قسط من السلفة
        
        Args:
            payroll: كائن الراتب
            advance: كائن السلفة
            amount: مبلغ القسط المخصوم
            
        Returns:
            AdvanceInstallment: سجل القسط المُنشأ
        """
        from ..models import AdvanceInstallment
        
        # تحديث حالة السلفة إلى "قيد الخصم" إذا كانت معتمدة
        if advance.status == 'approved':
            advance.status = 'in_progress'
            advance.save(update_fields=['status'])
        
        # تسجيل دفعة القسط مع تمرير شهر مسيرة الراتب
        installment = advance.record_installment_payment(
            month=payroll.month,
            amount=amount
        )

        # ربط سجل القسط بقسيمة الراتب الحالية إن لم يكن مرتبطاً
        if installment.payroll_id != payroll.id:
            installment.payroll = payroll
            installment.save(update_fields=['payroll'])
        
        # التحقق من اكتمال السلفة
        if advance.is_completed:
            advance.status = 'completed'
            advance.save(update_fields=['status'])
            logger.info(f"تم إكمال السلفة {advance.id} للموظف {advance.employee.get_full_name_ar()}")
        
        return installment
    
    @staticmethod
    @transaction.atomic
    def process_payroll_advances(payroll):
        """
        معالجة جميع خصومات السلف لراتب معين
        
        Args:
            payroll: كائن الراتب
            
        Returns:
            Decimal: إجمالي المبلغ المخصوم
        """
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            employee=payroll.employee,
            payroll_month=payroll.month
        )
        
        # تسجيل كل قسط
        for advance_data in advances_list:
            AdvanceService.record_advance_deduction(
                payroll=payroll,
                advance=advance_data['advance'],
                amount=advance_data['amount']
            )
        
        return total_deduction
    
    @staticmethod
    def get_employee_pending_advances(employee):
        """
        الحصول على السلف المعلقة للموظف
        
        Args:
            employee: كائن الموظف
            
        Returns:
            QuerySet: السلف المعلقة
        """
        from ..models import Advance
        
        return Advance.objects.filter(
            employee=employee,
            status__in=['approved', 'in_progress'],
            remaining_amount__gt=0
        )
    
    @staticmethod
    def get_employee_total_pending_amount(employee):
        """
        حساب إجمالي المبالغ المعلقة للموظف
        
        Args:
            employee: كائن الموظف
            
        Returns:
            Decimal: إجمالي المبالغ المعلقة
        """
        from django.db.models import Sum
        
        pending_advances = AdvanceService.get_employee_pending_advances(employee)
        total = pending_advances.aggregate(
            total=Sum('remaining_amount')
        )['total'] or Decimal('0.00')
        
        return total
    
    @staticmethod
    def validate_advance_request(employee, amount, installments_count):
        """
        التحقق من صحة طلب السلفة
        
        Args:
            employee: كائن الموظف
            amount: مبلغ السلفة المطلوب
            installments_count: عدد الأقساط
            
        Returns:
            tuple: (is_valid, error_message)
        """
        # التحقق من وجود عقد نشط
        if not hasattr(employee, 'active_contract') or not employee.active_contract:
            return False, "الموظف ليس لديه عقد نشط"
        
        # تحويل amount إلى Decimal
        amount = Decimal(str(amount))
        
        # التحقق من الحد الأقصى للمبلغ
        if amount > Decimal('50000'):
            return False, "المبلغ يتجاوز الحد الأقصى المسموح (50,000 جنيه)"
        
        # التحقق من عدد الأقساط
        if installments_count < 1 or installments_count > 24:
            return False, "عدد الأقساط يجب أن يكون بين 1 و 24 شهر"
        
        # التحقق من قيمة القسط مقارنة بالراتب
        installment_amount = amount / Decimal(str(installments_count))
        monthly_salary = employee.active_contract.total_salary
        
        if installment_amount > (monthly_salary * Decimal('0.5')):
            return False, "قيمة القسط الشهري تتجاوز 50% من الراتب"
        
        # التحقق من السلف المعلقة
        pending_total = AdvanceService.get_employee_total_pending_amount(employee)
        if pending_total + amount > monthly_salary * 2:
            return False, f"إجمالي السلف المعلقة ({pending_total + amount:,.0f} جنيه) يتجاوز ضعف الراتب الشهري"
        
        return True, None
    
    @staticmethod
    @transaction.atomic
    def create_advance(employee, amount, installments_count, deduction_start_month, reason, requested_by=None):
        """
        إنشاء سلفة جديدة
        
        Args:
            employee: كائن الموظف
            amount: مبلغ السلفة
            installments_count: عدد الأقساط
            deduction_start_month: شهر بدء الخصم
            reason: سبب السلفة
            requested_by: المستخدم الذي طلب السلفة (اختياري)
            
        Returns:
            Advance: كائن السلفة المُنشأ
        """
        from ..models import Advance
        
        # التحقق من صحة الطلب
        is_valid, error_message = AdvanceService.validate_advance_request(
            employee, amount, installments_count
        )
        
        if not is_valid:
            raise ValueError(error_message)
        
        # إنشاء السلفة
        advance = Advance.objects.create(
            employee=employee,
            amount=amount,
            installments_count=installments_count,
            deduction_start_month=deduction_start_month,
            reason=reason,
            status='pending'
        )
        
        logger.info(
            f"تم إنشاء سلفة جديدة #{advance.id} للموظف {employee.get_full_name_ar()} "
            f"- المبلغ: {amount:,.0f} جنيه على {installments_count} قسط"
        )
        
        return advance

