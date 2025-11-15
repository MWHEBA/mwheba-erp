"""
خدمة تفعيل العقود ونسخ البنود
"""
from django.db import transaction
from django.utils import timezone
from hr.models import Contract, ContractSalaryComponent, SalaryComponent
from .contract_component_service import ContractComponentService
from .component_classification_service import ComponentClassificationService


class ContractActivationService:
    """خدمة تفعيل العقد ونسخ البنود تلقائياً"""
    
    @staticmethod
    @transaction.atomic
    def activate_contract(contract, activated_by=None, transfer_components=None):
        """
        تفعيل العقد ونسخ البنود إلى الموظف مع المعالجة الذكية
        
        Args:
            contract: العقد المراد تفعيله
            activated_by: المستخدم الذي فعّل العقد (اختياري)
            transfer_components: قائمة معرفات البنود المراد نقلها (اختياري)
            
        Returns:
            tuple: (success: bool, message: str, details: dict)
        """
        if contract.status == 'active':
            return False, 'العقد مفعّل بالفعل', {}
        
        employee = contract.employee
        activation_details = {
            'old_contracts_deactivated': 0,
            'old_components_deactivated': 0,
            'new_components_copied': 0,
            'components_transferred': 0,
            'warnings': []
        }
        
        # 1. تحليل البنود الحالية للموظف
        component_analysis = ContractComponentService.analyze_employee_components(employee)
        
        # 2. تعطيل العقود القديمة مع المعالجة الذكية
        old_contracts = Contract.objects.filter(
            employee=employee,
            status='active'
        ).exclude(pk=contract.pk)
        
        for old_contract in old_contracts:
            old_contract.status = 'expired'
            old_contract.save()
            activation_details['old_contracts_deactivated'] += 1
            
            # تعطيل البنود المنسوخة من العقد القديم فقط
            deactivated_count = SalaryComponent.objects.filter(
                employee=employee,
                contract=old_contract,
                is_from_contract=True,
                source='contract'  # فقط بنود العقد، ليس الشخصية
            ).update(
                is_active=False,
                effective_to=timezone.now().date()
            )
            activation_details['old_components_deactivated'] += deactivated_count
        
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
        
        # 3. نقل البنود المختارة (إن وجدت)
        if transfer_components:
            transfer_success, transfer_message, transfer_details = (
                ContractComponentService.transfer_components_to_contract(
                    employee, transfer_components, contract
                )
            )
            activation_details['components_transferred'] = transfer_details.get('total_processed', 0)
            if not transfer_success:
                activation_details['warnings'].append(f'تحذير في نقل البنود: {transfer_message}')
        
        # 4. نسخ البنود مع المقارنة الدقيقة
        contract_components = ContractSalaryComponent.objects.filter(
            contract=contract
        ).order_by('order')
        
        employee_components = SalaryComponent.objects.filter(
            employee=employee,
            is_active=True
        )
        
        copied_count = 0
        updated_count = 0
        
        for contract_comp in contract_components:
            # البحث عن تطابق تام
            matching_employee_comp = ContractActivationService._find_exact_match(
                contract_comp, employee_components
            )
            
            if matching_employee_comp:
                # متطابق تماماً - لا نفعل شيء
                continue
            else:
                # بند جديد أو معدل - ننسخه للموظف
                new_component = contract_comp.copy_to_employee_component(employee)
                if new_component:
                    new_component.source = 'contract'
                    new_component.save()
                    copied_count += 1
        
        # تعطيل البنود القديمة التي لم تعد موجودة في العقد الجديد
        deactivated_count = 0
        for emp_comp in employee_components:
            # استبعاد البنود التي لا يجب تعطيلها
            should_preserve = ContractActivationService._should_preserve_component(emp_comp)
            if should_preserve:
                continue
                
            # تعطيل البند إذا لم يعد موجود في العقد الجديد
            if not ContractActivationService._has_match_in_contract(emp_comp, contract_components):
                emp_comp.is_active = False
                emp_comp.effective_to = timezone.now().date()
                emp_comp.save()
                deactivated_count += 1
        
        activation_details['new_components_copied'] = copied_count
        activation_details['old_components_deactivated'] += deactivated_count
        
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
        
        # إعداد الرسالة النهائية
        message_parts = [f'تم تفعيل العقد ونسخ {copied_count} بند']
        
        if activation_details['components_transferred'] > 0:
            message_parts.append(f'ونقل {activation_details["components_transferred"]} بند شخصي')
        
        if activation_details['old_components_deactivated'] > 0:
            message_parts.append(f'وتعطيل {activation_details["old_components_deactivated"]} بند قديم')
        
        final_message = ' '.join(message_parts) + ' بنجاح'
        
        return True, final_message, activation_details
    
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
    
    @staticmethod
    def get_activation_preview(contract):
        """
        معاينة تأثير تفعيل العقد على بنود الموظف
        
        Args:
            contract: العقد المراد تفعيله
            
        Returns:
            dict: معاينة شاملة للتأثير
        """
        employee = contract.employee
        
        # تحليل البنود الحالية
        current_analysis = ContractComponentService.analyze_employee_components(employee)
        
        # تحليل بنود العقد الجديد
        contract_summary = ContractActivationService.get_contract_summary(contract)
        
        # حساب التأثير المالي المتوقع
        current_net = current_analysis['financial_impact']['current_net_salary']
        new_net = contract_summary['estimated_net']
        net_change = new_net - current_net
        
        return {
            'employee': {
                'name': employee.get_full_name_ar(),
                'current_contract': employee.get_active_contract(),
                'current_components_count': current_analysis['total_active_components']
            },
            'current_financial': current_analysis['financial_impact'],
            'new_financial': {
                'estimated_earnings': contract_summary['total_fixed_earnings'],
                'estimated_deductions': contract_summary['total_fixed_deductions'],
                'estimated_net': contract_summary['estimated_net']
            },
            'financial_change': {
                'net_change': net_change,
                'change_percentage': (net_change / current_net * 100) if current_net > 0 else 0,
                'is_increase': net_change > 0
            },
            'components_impact': {
                'will_be_deactivated': len(current_analysis['components_by_source']['contract']),
                'will_be_added': contract_summary['total_components'],
                'transferable': len(current_analysis['transferable_components']),
                'expiring_soon': len(current_analysis['expiring_components'])
            },
            'recommendations': current_analysis['recommendations'],
            'warnings': ContractActivationService._generate_activation_warnings(
                current_analysis, contract
            )
        }
    
    @staticmethod
    def _generate_activation_warnings(current_analysis, contract):
        """توليد تحذيرات تفعيل العقد"""
        warnings = []
        
        # تحذير من فقدان البنود الشخصية
        transferable_count = len(current_analysis['transferable_components'])
        if transferable_count > 0:
            warnings.append({
                'type': 'component_loss',
                'level': 'warning',
                'message': f'سيتم فقدان {transferable_count} بند شخصي/مؤقت إذا لم يتم نقلهم',
                'action_required': True
            })
        
        # تحذير من تغيير كبير في الراتب
        return warnings
    
    @staticmethod
    def _find_exact_match(contract_comp, employee_components):
        """البحث عن تطابق تام بين بند العقد وبنود الموظف"""
        return employee_components.filter(
            code=contract_comp.code,
            name=contract_comp.name,
            component_type=contract_comp.component_type,
            calculation_method=contract_comp.calculation_method,
            amount=contract_comp.amount,
            percentage=contract_comp.percentage,
            formula=contract_comp.formula or ''
        ).first()
    
    @staticmethod
    def _has_match_in_contract(emp_comp, contract_components):
        """التحقق من وجود بند الموظف في بنود العقد الجديد"""
        for contract_comp in contract_components:
            if (contract_comp.code == emp_comp.code and
                contract_comp.name == emp_comp.name and
                contract_comp.component_type == emp_comp.component_type and
                contract_comp.calculation_method == emp_comp.calculation_method and
                contract_comp.amount == emp_comp.amount and
                contract_comp.percentage == emp_comp.percentage and
                (contract_comp.formula or '') == (emp_comp.formula or '')):
                return True
        return False
    
    @staticmethod
    def _should_preserve_component(component):
        """تحديد ما إذا كان يجب الحفاظ على البند أم لا"""
        
        # الحفاظ على القروض والسلف النشطة
        if component.source == 'personal':
            # إذا كان قرض أو سلفة لها تاريخ انتهاء مستقبلي
            if component.effective_to and component.effective_to > timezone.now().date():
                return True
        
        # الحفاظ على البنود المؤقتة النشطة
        if component.source == 'temporary':
            # إذا كان بند مؤقت لم ينته بعد
            if component.effective_to and component.effective_to > timezone.now().date():
                return True
        
        # الحفاظ على البنود الاستثنائية (مكافآت، حوافز) لفترة محدودة
        if component.source == 'exceptional':
            # إذا كان بند استثنائي حديث (أقل من شهر)
            if component.created_at and (timezone.now().date() - component.created_at.date()).days < 30:
                return True
        
        # عدم الحفاظ على باقي البنود (بنود العقد القديم، التعديلات، إلخ)
        return False
