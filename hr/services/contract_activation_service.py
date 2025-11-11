"""
خدمة تفعيل العقود ونسخ البنود
"""
from django.db import transaction
from django.utils import timezone
from hr.models import Contract, ContractSalaryComponent, SalaryComponent


class ContractActivationService:
    """خدمة تفعيل العقد ونسخ البنود تلقائياً"""
    
    @staticmethod
    @transaction.atomic
    def activate_contract(contract, activated_by=None):
        """
        تفعيل العقد ونسخ البنود إلى الموظف
        
        Args:
            contract: العقد المراد تفعيله
            activated_by: المستخدم الذي فعّل العقد (اختياري)
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if contract.status == 'active':
            return False, 'العقد مفعّل بالفعل'
        
        employee = contract.employee
        
        # 1. تعطيل العقد القديم (إن وجد)
        old_contracts = Contract.objects.filter(
            employee=employee,
            status='active'
        ).exclude(pk=contract.pk)
        
        for old_contract in old_contracts:
            old_contract.status = 'expired'
            old_contract.save()
            
            # تعطيل البنود المنسوخة من العقد القديم
            SalaryComponent.objects.filter(
                employee=employee,
                contract=old_contract,
                is_from_contract=True
            ).update(
                is_active=False,
                effective_to=timezone.now().date()
            )
        
        # 2. تفعيل العقد الجديد
        contract.status = 'active'
        contract.save()
        
        # 2.5. التأكد من وجود بند الراتب الأساسي
        if contract.basic_salary and contract.basic_salary > 0:
            basic_exists = ContractSalaryComponent.objects.filter(
                contract=contract,
                is_basic=True
            ).exists()
            
            if not basic_exists:
                # إضافة بند الراتب الأساسي تلقائياً
                ContractSalaryComponent.objects.create(
                    contract=contract,
                    component_type='earning',
                    code='BASIC_SALARY',
                    name='الراتب الأساسي',
                    calculation_method='fixed',
                    amount=contract.basic_salary,
                    is_basic=True,
                    is_taxable=True,
                    is_fixed=True,
                    affects_overtime=True,
                    order=0,
                    show_in_payslip=True,
                    notes='تم إضافته تلقائياً عند التفعيل'
                )
        
        # 3. نسخ البنود من ContractSalaryComponent إلى SalaryComponent
        contract_components = ContractSalaryComponent.objects.filter(
            contract=contract
        ).order_by('order')
        
        copied_count = 0
        for component in contract_components:
            component.copy_to_employee_component(employee)
            copied_count += 1
        
        # 4. تحديث بيانات الموظف (إن كانت مختلفة)
        if contract.job_title and employee.job_title != contract.job_title:
            employee.job_title = contract.job_title
        
        if contract.department and employee.department != contract.department:
            employee.department = contract.department
        
        employee.save()
        
        # 5. ربط البصمة (إن وجدت)
        if contract.biometric_user_id:
            try:
                from hr.models import BiometricUserMapping
                # استخدام update_or_create لتجنب التضارب
                BiometricUserMapping.objects.update_or_create(
                    employee=employee,
                    defaults={
                        'biometric_user_id': contract.biometric_user_id,
                        'is_active': True
                    }
                )
            except Exception as e:
                # لا نوقف العملية إذا فشل ربط البصمة
                pass
        
        return True, f'تم تفعيل العقد ونسخ {copied_count} بند بنجاح'
    
    @staticmethod
    @transaction.atomic
    def deactivate_contract(contract):
        """
        إيقاف العقد وتعطيل البنود المنسوخة
        
        يقوم بـ:
        - تغيير حالة العقد إلى suspended
        - تعطيل جميع البنود المنسوخة من العقد
        - إيقاف البصمة (يتم تلقائياً عبر signals)
        - إرسال إشعارات (يتم تلقائياً عبر signals)
        
        Args:
            contract: العقد المراد إيقافه
            
        Returns:
            dict: نتيجة العملية
        """
        if contract.status != 'active':
            return {
                'success': False,
                'message': 'العقد غير مفعّل'
            }
        
        # إيقاف العقد
        contract.status = 'suspended'
        contract.save()
        
        # تعطيل البنود المنسوخة
        deactivated_count = SalaryComponent.objects.filter(
            employee=contract.employee,
            contract=contract,
            is_from_contract=True
        ).update(
            is_active=False,
            effective_to=timezone.now().date()
        )
        
        # ملاحظة: إيقاف البصمة وإرسال الإشعارات يتم تلقائياً عبر signals.py
        # - sync_contract_with_attendance: يوقف البصمة عند status='suspended'
        # - send_contract_notifications: يرسل إشعارات للموظف وقسم HR
        
        return {
            'success': True,
            'message': f'تم إيقاف العقد وتعطيل {deactivated_count} بند',
            'deactivated_count': deactivated_count
        }
    
    @staticmethod
    def get_contract_summary(contract):
        """
        الحصول على ملخص بنود العقد
        
        Args:
            contract: العقد
            
        Returns:
            dict: ملخص البنود
        """
        components = ContractSalaryComponent.objects.filter(contract=contract)
        
        earnings = components.filter(component_type='earning')
        deductions = components.filter(component_type='deduction')
        
        total_fixed_earnings = sum(
            c.amount for c in earnings.filter(calculation_method='fixed')
        )
        
        total_fixed_deductions = sum(
            c.amount for c in deductions.filter(calculation_method='fixed')
        )
        
        return {
            'total_components': components.count(),
            'earnings_count': earnings.count(),
            'deductions_count': deductions.count(),
            'total_fixed_earnings': total_fixed_earnings,
            'total_fixed_deductions': total_fixed_deductions,
            'estimated_net': total_fixed_earnings - total_fixed_deductions,
        }
