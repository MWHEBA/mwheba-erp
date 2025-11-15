"""
خدمة موحدة لإدارة بنود الراتب - تجمع جميع العمليات في مكان واحد
"""
from django.db import transaction, models
from django.utils import timezone
from decimal import Decimal
import logging
import json

logger = logging.getLogger(__name__)


class UnifiedSalaryComponentService:
    """خدمة موحدة لإدارة بنود الراتب"""
    
    def __init__(self):
        """تهيئة الخدمة"""
        from ..models import SalaryComponent, SalaryComponentTemplate, Contract, Employee
        self.SalaryComponent = SalaryComponent
        self.SalaryComponentTemplate = SalaryComponentTemplate
        self.Contract = Contract
        self.Employee = Employee
    
    # ==================== إدارة البنود ====================
    
    @transaction.atomic
    def create_component(self, employee, data, contract=None, template=None):
        """
        إنشاء بند راتب جديد
        
        Args:
            employee: الموظف
            data: بيانات البند (dict)
            contract: العقد (اختياري)
            template: القالب (اختياري)
        
        Returns:
            SalaryComponent: البند المُنشأ
        """
        # توليد كود فريد إذا لم يتم تحديده
        if not data.get('code'):
            data['code'] = self._generate_unique_code(employee, data.get('name', 'COMPONENT'))
        
        # إنشاء البند
        component = self.SalaryComponent.objects.create(
            employee=employee,
            contract=contract,
            template=template,
            **data
        )
        
        logger.info(f"تم إنشاء بند راتب جديد: {component.name} للموظف {employee.get_full_name_ar()}")
        return component
    
    @transaction.atomic
    def update_component(self, component_id, data):
        """
        تحديث بند راتب
        
        Args:
            component_id: معرف البند
            data: البيانات الجديدة
        
        Returns:
            SalaryComponent: البند المُحدث
        """
        component = self.SalaryComponent.objects.get(id=component_id)
        
        # تحديث الحقول
        for key, value in data.items():
            if hasattr(component, key):
                setattr(component, key, value)
        
        component.save()
        
        logger.info(f"تم تحديث بند راتب: {component.name}")
        return component
    
    @transaction.atomic
    def delete_component(self, component_id, soft_delete=True):
        """
        حذف بند راتب
        
        Args:
            component_id: معرف البند
            soft_delete: حذف ناعم (تعطيل) أم حذف نهائي
        
        Returns:
            bool: نجح الحذف أم لا
        """
        try:
            component = self.SalaryComponent.objects.get(id=component_id)
            
            if soft_delete:
                component.is_active = False
                component.effective_to = timezone.now().date()
                component.save()
                logger.info(f"تم تعطيل بند راتب: {component.name}")
            else:
                component_name = component.name
                component.delete()
                logger.info(f"تم حذف بند راتب نهائياً: {component_name}")
            
            return True
        except Exception as e:
            logger.error(f"خطأ في حذف بند الراتب: {str(e)}")
            return False
    
    # ==================== إدارة القوالب ====================
    
    @transaction.atomic
    def apply_template(self, employee, template_code, custom_data=None, contract=None):
        """
        تطبيق قالب على موظف
        
        Args:
            employee: الموظف
            template_code: كود القالب
            custom_data: بيانات مخصصة لتجاوز القالب
            contract: العقد (اختياري)
        
        Returns:
            SalaryComponent: البند المُنشأ
        """
        try:
            template = self.SalaryComponentTemplate.objects.get(
                code=template_code,
                is_active=True
            )
            
            # إعداد البيانات من القالب
            component_data = {
                'code': template.code,
                'name': template.name,
                'component_type': template.component_type,
                'calculation_method': 'formula' if template.formula else 'fixed',
                'amount': template.default_amount,
                'formula': template.formula,
                'account_code': template.default_account_code,
                'is_active': True,
                'effective_from': timezone.now().date(),
                'source': 'template',
                'notes': f'تم الإنشاء من القالب: {template.name}'
            }
            
            # تطبيق البيانات المخصصة
            if custom_data:
                component_data.update(custom_data)
            
            # إنشاء البند
            component = self.create_component(
                employee=employee,
                data=component_data,
                contract=contract,
                template=template
            )
            
            return component
            
        except self.SalaryComponentTemplate.DoesNotExist:
            logger.error(f"القالب {template_code} غير موجود")
            return None
        except Exception as e:
            logger.error(f"خطأ في تطبيق القالب: {str(e)}")
            return None
    
    def create_from_template(self, employee, template, effective_from=None, contract=None, custom_amount=None):
        """
        إنشاء بند من قالب (للتوافق مع الكود القديم)
        """
        custom_data = {}
        if custom_amount is not None:
            custom_data['amount'] = custom_amount
        if effective_from:
            custom_data['effective_from'] = effective_from
            
        return self.apply_template(
            employee=employee,
            template_code=template.code,
            custom_data=custom_data,
            contract=contract
        )
    
    # ==================== إدارة العقود ====================
    
    @transaction.atomic
    def copy_from_contract(self, contract, employee=None, selected_components=None):
        """
        نسخ بنود من العقد إلى الموظف
        
        Args:
            contract: العقد
            employee: الموظف (افتراضياً موظف العقد)
            selected_components: قائمة معرفات البنود المحددة
        
        Returns:
            list: قائمة البنود المنسوخة
        """
        if not employee:
            employee = contract.employee
        
        # جلب بنود العقد
        contract_components = contract.salary_components.all()
        
        # تطبيق الفلتر إذا تم تحديد بنود معينة
        if selected_components:
            contract_components = contract_components.filter(
                id__in=selected_components
            )
        
        copied_components = []
        
        for contract_component in contract_components:
            # توليد كود فريد لتجنب التضارب
            unique_code = self._generate_unique_code(
                employee=employee, 
                name=contract_component.name,
                original_code=contract_component.code
            )
            
            # إعداد بيانات البند
            component_data = {
                'code': unique_code,  # استخدام الكود الفريد
                'name': contract_component.name,
                'component_type': contract_component.component_type,
                'calculation_method': contract_component.calculation_method,
                'amount': contract_component.amount,
                'percentage': getattr(contract_component, 'percentage', None),
                'formula': contract_component.formula,
                'is_basic': getattr(contract_component, 'is_basic', False),
                'is_taxable': getattr(contract_component, 'is_taxable', True),
                'is_fixed': getattr(contract_component, 'is_fixed', True),
                'affects_overtime': getattr(contract_component, 'affects_overtime', False),
                'show_in_payslip': getattr(contract_component, 'show_in_payslip', True),
                'order': contract_component.order,
                'account_code': getattr(contract_component, 'account_code', ''),
                'notes': f"منسوخ من العقد: {contract_component.notes}" if contract_component.notes else f"منسوخ من العقد {contract.id}",
                'is_from_contract': True,
                'source': 'contract',
                'effective_from': contract.start_date,
                'is_active': True
            }
            
            # إنشاء البند
            component = self.create_component(
                employee=employee,
                data=component_data,
                contract=contract,
                template=getattr(contract_component, 'template', None)
            )
            
            # ربط بالبند الأصلي في العقد
            component.source_contract_component = contract_component
            component.save()
            
            copied_components.append(component)
        
        logger.info(f"تم نسخ {len(copied_components)} بند من العقد {contract.id} للموظف {employee.get_full_name_ar()}")
        return copied_components
    
    @transaction.atomic
    def sync_with_contract(self, contract):
        """
        مزامنة بنود الموظف مع العقد
        
        Args:
            contract: العقد
        
        Returns:
            dict: نتائج المزامنة
        """
        employee = contract.employee
        
        # جلب البنود المنسوخة من العقد
        existing_components = employee.salary_components.filter(
            is_from_contract=True,
            contract=contract,
            is_active=True
        )
        
        # جلب بنود العقد الحالية
        contract_components = contract.salary_components.all()
        
        results = {
            'updated': 0,
            'added': 0,
            'removed': 0,
            'unchanged': 0
        }
        
        # تحديث البنود الموجودة
        for existing in existing_components:
            contract_component = contract_components.filter(
                code=existing.code
            ).first()
            
            if contract_component:
                # تحديث البيانات
                updated = False
                if existing.amount != contract_component.amount:
                    existing.amount = contract_component.amount
                    updated = True
                if existing.name != contract_component.name:
                    existing.name = contract_component.name
                    updated = True
                
                if updated:
                    existing.save()
                    results['updated'] += 1
                else:
                    results['unchanged'] += 1
            else:
                # البند لم يعد موجود في العقد
                existing.is_active = False
                existing.effective_to = timezone.now().date()
                existing.save()
                results['removed'] += 1
        
        # إضافة البنود الجديدة
        existing_codes = set(existing_components.values_list('code', flat=True))
        for contract_component in contract_components:
            if contract_component.code not in existing_codes:
                self.copy_from_contract(
                    contract=contract,
                    selected_components=[contract_component.id]
                )
                results['added'] += 1
        
        logger.info(f"مزامنة العقد {contract.id}: {results}")
        return results
    
    # ==================== الحسابات ====================
    
    def calculate_salary(self, employee, month=None, include_inactive=False):
        """
        حساب إجمالي الراتب للموظف
        
        Args:
            employee: الموظف
            month: الشهر (افتراضياً الشهر الحالي)
            include_inactive: تضمين البنود غير النشطة
        
        Returns:
            dict: تفاصيل الراتب
        """
        if not month:
            month = timezone.now().date()
        
        # جلب البنود النشطة
        components = self.get_active_components(employee, month, include_inactive)
        
        # الحصول على الراتب الأساسي
        basic_salary = self._get_basic_salary(employee)
        
        # إعداد السياق للحساب
        context = {
            'basic_salary': basic_salary,
            'month': month,
            'worked_days': 30  # يمكن تحسينه لاحقاً
        }
        
        # حساب المستحقات
        earnings = components.filter(component_type='earning')
        total_earnings = basic_salary + sum(
            self._calculate_component_amount(comp, context) 
            for comp in earnings
        )
        
        # حساب الاستقطاعات
        deductions = components.filter(component_type='deduction')
        total_deductions = sum(
            self._calculate_component_amount(comp, context) 
            for comp in deductions
        )
        
        return {
            'basic_salary': basic_salary,
            'total_earnings': total_earnings,
            'total_deductions': total_deductions,
            'net_salary': total_earnings - total_deductions,
            'components_count': components.count(),
            'earnings_count': earnings.count(),
            'deductions_count': deductions.count()
        }
    
    def get_active_components(self, employee, month=None, include_inactive=False):
        """
        جلب البنود النشطة للموظف
        
        Args:
            employee: الموظف
            month: الشهر
            include_inactive: تضمين البنود غير النشطة
        
        Returns:
            QuerySet: البنود النشطة
        """
        if not month:
            month = timezone.now().date()
        
        components = employee.salary_components.all()
        
        if not include_inactive:
            components = components.filter(is_active=True)
        
        # فلترة حسب التاريخ
        components = components.filter(
            models.Q(effective_from__isnull=True) | models.Q(effective_from__lte=month)
        ).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=month)
        )
        
        return components.order_by('component_type', 'order', 'name')
    
    # ==================== المعاينة الجديدة ====================
    
    def preview_contract_components(self, contract, employee=None):
        """
        معاينة بنود العقد للنسخ (النهج الجديد)
        
        Args:
            contract: العقد
            employee: الموظف (افتراضياً موظف العقد)
        
        Returns:
            dict: بيانات المعاينة
        """
        if not employee:
            employee = contract.employee
        
        # جلب بنود العقد
        contract_components = contract.salary_components.all()
        
        # جلب البنود الحالية للموظف
        existing_components = employee.salary_components.filter(is_active=True)
        
        preview_data = []
        
        for contract_comp in contract_components:
            # البحث عن بند مشابه للموظف
            existing = existing_components.filter(code=contract_comp.code).first()
            
            component_preview = {
                'id': contract_comp.id,
                'code': contract_comp.code,
                'name': contract_comp.name,
                'component_type': contract_comp.component_type,
                'amount': contract_comp.amount,
                'calculation_method': contract_comp.calculation_method,
                'is_new': existing is None,
                'existing_amount': existing.amount if existing else None,
                'will_replace': existing is not None,
                'recommended': True,  # يمكن تحسينه بمنطق أذكى
                'source': 'contract'
            }
            
            preview_data.append(component_preview)
        
        return {
            'contract_id': contract.id,
            'employee_id': employee.id,
            'components': preview_data,
            'total_components': len(preview_data),
            'new_components': len([c for c in preview_data if c['is_new']]),
            'replacement_components': len([c for c in preview_data if c['will_replace']]),
            'estimated_impact': self._estimate_financial_impact(preview_data, employee)
        }
    
    def apply_preview_selection(self, contract, selected_component_ids, employee=None):
        """
        تطبيق الاختيار من المعاينة (النهج الجديد)
        
        Args:
            contract: العقد
            selected_component_ids: قائمة معرفات البنود المحددة
            employee: الموظف
        
        Returns:
            list: البنود المنسوخة
        """
        return self.copy_from_contract(
            contract=contract,
            employee=employee,
            selected_components=selected_component_ids
        )
    
    # ==================== دوال مساعدة ====================
    
    def _generate_unique_code(self, employee, name, original_code=None):
        """توليد كود فريد للبند"""
        import re
        
        # استخدام الكود الأصلي إذا كان متوفراً
        if original_code:
            base_code = original_code
        else:
            base_code = re.sub(r'[^a-zA-Z0-9]', '_', name.upper())[:45]
        
        counter = 1
        code = base_code
        while self.SalaryComponent.objects.filter(
            employee=employee, 
            code=code
        ).exists():
            if counter == 1:
                # أول محاولة: إضافة _CONTRACT
                code = f"{base_code}_CONTRACT"
            else:
                # محاولات أخرى: إضافة رقم
                code = f"{base_code}_CONTRACT_{counter}"
            counter += 1
            if counter > 999:
                import uuid
                code = f"{base_code}_{str(uuid.uuid4())[:8]}"
                break
        
        return code
    
    def _get_basic_salary(self, employee):
        """الحصول على الراتب الأساسي للموظف"""
        # محاولة الحصول من العقد النشط أولاً
        active_contract = employee.contracts.filter(status='active').first()
        if active_contract and active_contract.basic_salary:
            return Decimal(str(active_contract.basic_salary))
        
        # البحث في البنود
        basic_component = employee.salary_components.filter(
            is_basic=True,
            is_active=True
        ).first()
        
        return basic_component.amount if basic_component else Decimal('0')
    
    def _calculate_component_amount(self, component, context):
        """حساب مبلغ البند"""
        if component.calculation_method == 'fixed':
            return component.amount
        elif component.calculation_method == 'percentage':
            if component.percentage:
                return context['basic_salary'] * (component.percentage / Decimal('100'))
        elif component.calculation_method == 'formula':
            return self._evaluate_formula(component.formula, context)
        
        return component.amount
    
    def _evaluate_formula(self, formula, context):
        """تقييم الصيغة الحسابية"""
        if not formula:
            return Decimal('0')
        
        try:
            # استبدال المتغيرات
            formula_eval = formula.upper()
            formula_eval = formula_eval.replace('BASIC', str(context['basic_salary']))
            formula_eval = formula_eval.replace('DAYS', str(context.get('worked_days', 30)))
            
            # تقييم آمن
            allowed_chars = set('0123456789.+-*/() ')
            if all(c in allowed_chars for c in formula_eval):
                result = eval(formula_eval, {"__builtins__": {}}, {})
                return Decimal(str(result))
        except:
            pass
        
        return Decimal('0')
    
    def _estimate_financial_impact(self, preview_data, employee):
        """تقدير التأثير المالي للمعاينة"""
        current_salary = self.calculate_salary(employee)
        
        # حساب التأثير المتوقع
        estimated_earnings_change = Decimal('0')
        estimated_deductions_change = Decimal('0')
        
        for comp in preview_data:
            amount = Decimal(str(comp['amount']))
            if comp['component_type'] == 'earning':
                estimated_earnings_change += amount
            else:
                estimated_deductions_change += amount
        
        return {
            'current_net': current_salary['net_salary'],
            'estimated_earnings_change': estimated_earnings_change,
            'estimated_deductions_change': estimated_deductions_change,
            'estimated_net_change': estimated_earnings_change - estimated_deductions_change,
            'risk_level': 'low'  # يمكن تحسينه
        }
