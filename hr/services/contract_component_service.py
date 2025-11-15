"""
خدمة إدارة بنود العقود الذكية
"""
from django.db import transaction
from django.utils import timezone
from datetime import date
from typing import Dict, List, Tuple, Optional
from ..models import Contract, SalaryComponent, Employee
from .component_classification_service import ComponentClassificationService


class ContractComponentService:
    """خدمة ذكية لإدارة بنود العقود والموظفين"""
    
    @staticmethod
    def analyze_employee_components(employee: Employee) -> Dict:
        """
        تحليل بنود الموظف الحالية قبل إنشاء عقد جديد
        
        Args:
            employee: الموظف
            
        Returns:
            dict: تحليل شامل للبنود
        """
        # جلب جميع البنود النشطة
        active_components = SalaryComponent.objects.filter(
            employee=employee,
            is_active=True
        ).select_related('template', 'contract')
        
        # تصنيف البنود حسب المصدر
        components_by_source = ComponentClassificationService.get_components_by_source(employee)
        
        # البنود المؤقتة والشخصية (قابلة للنقل)
        transferable_components = []
        transferable_components.extend(components_by_source['personal'])
        transferable_components.extend(components_by_source['temporary'])
        transferable_components.extend(components_by_source['exceptional'])
        
        # البنود التي ستتأثر بالعقد الجديد
        contract_components = components_by_source['contract']
        
        # البنود المنتهية قريباً
        expiring_components = ComponentClassificationService.get_expiring_components().filter(
            employee=employee
        )
        
        # حساب التأثير المالي
        current_earnings = sum(
            c.amount for c in active_components.filter(component_type='earning')
        )
        current_deductions = sum(
            c.amount for c in active_components.filter(component_type='deduction')
        )
        current_net = current_earnings - current_deductions
        
        return {
            'total_active_components': active_components.count(),
            'contract_components': contract_components,
            'transferable_components': transferable_components,
            'expiring_components': expiring_components,
            'components_by_source': components_by_source,
            'financial_impact': {
                'current_earnings': current_earnings,
                'current_deductions': current_deductions,
                'current_net_salary': current_net,
            },
            'recommendations': ContractComponentService._generate_recommendations(
                transferable_components, expiring_components, contract_components
            )
        }
    
    @staticmethod
    def _generate_recommendations(transferable, expiring, contract_components) -> List[Dict]:
        """توليد توصيات ذكية للتعامل مع البنود"""
        recommendations = []
        
        # توصيات للبنود القابلة للنقل
        if transferable:
            recommendations.append({
                'type': 'transfer',
                'priority': 'high',
                'title': f'نقل {len(transferable)} بند شخصي/مؤقت',
                'description': 'يُنصح بنقل البنود الشخصية والمؤقتة للعقد الجديد',
                'components': transferable,
                'action': 'suggest_transfer'
            })
        
        # تنبيه للبنود المنتهية
        if expiring:
            recommendations.append({
                'type': 'warning',
                'priority': 'medium',
                'title': f'{len(expiring)} بند سينتهي قريباً',
                'description': 'هناك بنود ستنتهي خلال 30 يوم، يُنصح بمراجعتها',
                'components': expiring,
                'action': 'review_expiring'
            })
        
        # تنبيه لاستبدال بنود العقد
        if contract_components:
            recommendations.append({
                'type': 'info',
                'priority': 'medium',
                'title': f'استبدال {len(contract_components)} بند من العقد القديم',
                'description': 'سيتم تعطيل بنود العقد القديم وتفعيل بنود العقد الجديد',
                'components': contract_components,
                'action': 'replace_contract_components'
            })
        
        return recommendations
    
    @staticmethod
    @transaction.atomic
    def transfer_components_to_contract(
        employee: Employee, 
        component_ids: List[int], 
        new_contract: Contract,
        transfer_options: Dict = None
    ) -> Tuple[bool, str, Dict]:
        """
        نقل البنود المختارة للعقد الجديد
        
        Args:
            employee: الموظف
            component_ids: قائمة معرفات البنود المراد نقلها
            new_contract: العقد الجديد
            transfer_options: خيارات النقل
            
        Returns:
            tuple: (نجح, رسالة, تفاصيل)
        """
        transfer_options = transfer_options or {}
        
        # جلب البنود المراد نقلها
        components_to_transfer = SalaryComponent.objects.filter(
            id__in=component_ids,
            employee=employee,
            is_active=True
        )
        
        if not components_to_transfer.exists():
            return False, 'لا توجد بنود صالحة للنقل', {}
        
        transferred_count = 0
        updated_count = 0
        errors = []
        
        for component in components_to_transfer:
            try:
                # تحديد نوع النقل حسب مصدر البند
                if component.source in ['personal', 'temporary', 'exceptional']:
                    # نقل البنود الشخصية/المؤقتة: تحديث المرجع للعقد الجديد
                    component.contract = new_contract
                    component.source = 'contract'  # تحويل لبند عقد
                    component.is_from_contract = True
                    component.save()
                    updated_count += 1
                    
                elif component.source == 'adjustment':
                    # التعديلات: إنشاء نسخة جديدة في العقد
                    new_component = SalaryComponent.objects.create(
                        employee=employee,
                        contract=new_contract,
                        component_type=component.component_type,
                        name=component.name,
                        calculation_method=component.calculation_method,
                        amount=component.amount,
                        percentage=component.percentage,
                        source='contract',
                        is_from_contract=True,
                        is_active=True,
                        effective_from=new_contract.start_date,
                        notes=f'منقول من تعديل: {component.notes or ""}'
                    )
                    
                    # تعطيل البند القديم
                    component.is_active = False
                    component.effective_to = date.today()
                    component.save()
                    
                    transferred_count += 1
                    
            except Exception as e:
                errors.append(f'خطأ في نقل البند "{component.name}": {str(e)}')
        
        # إعداد الرسالة
        success_parts = []
        if transferred_count > 0:
            success_parts.append(f'تم نقل {transferred_count} بند')
        if updated_count > 0:
            success_parts.append(f'تم تحديث {updated_count} بند')
        
        if success_parts:
            message = ' و '.join(success_parts) + ' بنجاح'
            if errors:
                message += f' مع {len(errors)} خطأ'
        else:
            message = 'لم يتم نقل أي بنود'
        
        return len(success_parts) > 0, message, {
            'transferred_count': transferred_count,
            'updated_count': updated_count,
            'errors': errors,
            'total_processed': transferred_count + updated_count
        }
    
    @staticmethod
    def get_component_transfer_preview(
        employee: Employee, 
        component_ids: List[int]
    ) -> Dict:
        """
        معاينة نتائج نقل البنود قبل التنفيذ
        
        Args:
            employee: الموظف
            component_ids: قائمة معرفات البنود
            
        Returns:
            dict: معاينة التأثير
        """
        components = SalaryComponent.objects.filter(
            id__in=component_ids,
            employee=employee,
            is_active=True
        )
        
        preview = {
            'components': [],
            'financial_impact': {
                'earnings_change': 0,
                'deductions_change': 0,
                'net_change': 0
            },
            'warnings': [],
            'recommendations': []
        }
        
        for component in components:
            amount = component.amount
            
            component_info = {
                'id': component.id,
                'name': component.name,
                'type': component.get_component_type_display(),
                'source': component.get_source_display(),
                'amount': amount,
                'action': 'transfer' if component.source != 'adjustment' else 'copy_and_deactivate'
            }
            
            preview['components'].append(component_info)
            
            # حساب التأثير المالي
            if component.component_type == 'earning':
                preview['financial_impact']['earnings_change'] += amount
            else:
                preview['financial_impact']['deductions_change'] += amount
        
        # حساب التغيير الصافي
        preview['financial_impact']['net_change'] = (
            preview['financial_impact']['earnings_change'] - 
            preview['financial_impact']['deductions_change']
        )
        
        # إضافة تحذيرات
        temporary_components = [c for c in components if c.is_temporary()]
        if temporary_components:
            preview['warnings'].append(
                f'يحتوي على {len(temporary_components)} بند مؤقت سيصبح دائماً في العقد الجديد'
            )
        
        return preview
    
    @staticmethod
    def cleanup_inactive_components(employee: Employee, days_old: int = 90) -> Dict:
        """
        تنظيف البنود غير النشطة القديمة
        
        Args:
            employee: الموظف (أو None لجميع الموظفين)
            days_old: عمر البنود بالأيام
            
        Returns:
            dict: نتائج التنظيف
        """
        cutoff_date = date.today() - timezone.timedelta(days=days_old)
        
        query = SalaryComponent.objects.filter(
            is_active=False,
            effective_to__lt=cutoff_date
        )
        
        if employee:
            query = query.filter(employee=employee)
        
        # عد البنود قبل الحذف
        count_before = query.count()
        
        # الحذف
        deleted_count = query.delete()[0]
        
        return {
            'deleted_count': deleted_count,
            'cutoff_date': cutoff_date,
            'employee': employee.get_full_name_ar() if employee else 'جميع الموظفين'
        }
    
    @staticmethod
    def copy_selected_components_to_contract(employee: Employee, component_ids: List[int], contract) -> Tuple[bool, str, Dict]:
        """
        نسخ بنود محددة من الموظف إلى العقد الجديد
        
        Args:
            employee: الموظف
            component_ids: قائمة معرفات البنود المراد نسخها
            contract: العقد الجديد
            
        Returns:
            tuple: (نجح, رسالة, تفاصيل)
        """
        from ..models import ContractSalaryComponent
        
        # جلب البنود المراد نسخها
        components_to_copy = SalaryComponent.objects.filter(
            id__in=component_ids,
            employee=employee,
            is_active=True
        )
        
        if not components_to_copy.exists():
            return False, 'لا توجد بنود صالحة للنسخ', {}
        
        copied_components = []
        
        for component in components_to_copy:
            try:
                # إنشاء ContractSalaryComponent جديد
                contract_component = ContractSalaryComponent.objects.create(
                    contract=contract,
                    code=component.code,
                    name=component.name,
                    component_type=component.component_type,
                    calculation_method=component.calculation_method,
                    amount=component.amount,
                    percentage=component.percentage,
                    formula=component.formula,
                    is_taxable=getattr(component, 'is_taxable', False),
                    is_social_security=getattr(component, 'is_social_security', False),
                    notes=f'منسوخ من بند الموظف (ID: {component.id})',
                    order=getattr(component, 'order', 0)
                )
                
                copied_components.append({
                    'original': component,
                    'copied': contract_component
                })
                
            except Exception as e:
                # في حالة الخطأ، نسجل الخطأ ونكمل
                print(f"خطأ في نسخ البند {component.name}: {str(e)}")
                continue
        
        return True, f'تم نسخ {len(copied_components)} بند بنجاح', {
            'copied_count': len(copied_components),
            'copied_components': copied_components
        }
