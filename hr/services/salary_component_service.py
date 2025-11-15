"""
خدمة إدارة بنود الراتب
"""
from django.db import transaction
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class SalaryComponentService:
    """خدمة إدارة بنود الراتب"""
    
    @staticmethod
    def _generate_unique_code(employee, template):
        """توليد كود فريد للبند"""
        from ..models import SalaryComponent
        from django.db import IntegrityError
        
        base_code = template.name.upper().replace(' ', '_')[:45]  # ترك مساحة للرقم
        
        # محاولة استخدام الكود الأساسي أولاً
        if not SalaryComponent.objects.filter(employee=employee, code=base_code).exists():
            return base_code
        
        # إذا كان الكود موجود، أضف رقم تسلسلي
        counter = 1
        while counter <= 999:
            new_code = f"{base_code}_{counter}"
            if not SalaryComponent.objects.filter(employee=employee, code=new_code).exists():
                return new_code
            counter += 1
        
        # إذا فشل كل شيء، استخدم UUID
        import uuid
        return f"{base_code}_{str(uuid.uuid4())[:8]}"
    
    @staticmethod
    def _handle_duplicate_code_error(employee, template, original_error):
        """معالجة خطأ تضارب الكود وإعادة المحاولة"""
        try:
            # توليد كود جديد مع timestamp
            import time
            timestamp = str(int(time.time()))[-6:]  # آخر 6 أرقام من timestamp
            base_code = template.name.upper().replace(' ', '_')[:40]
            new_code = f"{base_code}_{timestamp}"
            
            return new_code
        except Exception:
            # إذا فشل كل شيء، استخدم UUID
            import uuid
            return f"COMP_{str(uuid.uuid4())[:12]}"
    
    @staticmethod
    @transaction.atomic
    def create_from_template(employee, template, effective_from=None, contract=None, custom_amount=None):
        """
        إنشاء بند راتب من قالب
        
        Args:
            employee: الموظف
            template: SalaryComponentTemplate
            effective_from: تاريخ السريان (اختياري)
            contract: العقد (اختياري)
            custom_amount: مبلغ مخصص (اختياري - يتجاوز المبلغ الافتراضي)
        
        Returns:
            SalaryComponent: البند المُنشأ
        """
        from ..models import SalaryComponent
        
        # تحديد طريقة الحساب بناءً على القالب
        if template.formula:
            calculation_method = 'formula'
            amount = Decimal('0')
            percentage = None
            formula = template.formula
        else:
            calculation_method = 'fixed'
            # استخدام المبلغ المخصص إذا تم توفيره، وإلا استخدم المبلغ الافتراضي
            amount = custom_amount if custom_amount is not None else template.default_amount
            percentage = None
            formula = ''
        
        # توليد كود فريد للبند مع معالجة التضارب
        unique_code = SalaryComponentService._generate_unique_code(employee, template)
        
        try:
            component = SalaryComponent.objects.create(
                employee=employee,
                template=template,
                contract=contract,
                code=unique_code,
                name=template.name,
                component_type=template.component_type,
                calculation_method=calculation_method,
                amount=amount,
                percentage=percentage,
                formula=formula,
                is_basic=False,
                is_taxable=True,
                is_fixed=True,
                is_from_contract=False,  # البند ليس من العقد، بل مضاف يدوياً
                source='adjustment',  # تصنيف كتعديل وليس من العقد
                order=template.order,
                effective_from=effective_from,
                notes=f'تم الإنشاء من القالب: {template.name}'
            )
        except Exception as e:
            # إذا حدث تضارب رغم التحقق، جرب كود بديل
            if 'UNIQUE constraint failed' in str(e):
                backup_code = SalaryComponentService._handle_duplicate_code_error(employee, template, e)
                component = SalaryComponent.objects.create(
                    employee=employee,
                    template=template,
                    contract=contract,
                    code=backup_code,
                    name=template.name,
                    component_type=template.component_type,
                    calculation_method=calculation_method,
                    amount=amount,
                    percentage=percentage,
                    formula=formula,
                    is_basic=False,
                    is_taxable=True,
                    is_fixed=True,
                    is_from_contract=False,  # البند ليس من العقد، بل مضاف يدوياً
                    source='adjustment',  # تصنيف كتعديل وليس من العقد
                    order=template.order,
                    effective_from=effective_from,
                    notes=f'تم الإنشاء من القالب: {template.name}'
                )
            else:
                raise e
        
        logger.info(
            f"تم إنشاء بند راتب من القالب - الموظف: {employee.get_full_name_ar()}, "
            f"البند: {component.name}, المبلغ: {amount}"
        )
        
        return component
    
    @staticmethod
    @transaction.atomic
    def create_from_structure(employee, structure, effective_from=None, contract=None):
        """
        نسخ بنود من SalaryComponentTemplate (هيكل راتب) إلى موظف
        
        Args:
            employee: الموظف
            structure: يمكن أن يكون:
                - قائمة من SalaryComponentTemplate
                - QuerySet من SalaryComponentTemplate
            effective_from: تاريخ السريان
            contract: العقد
        
        Returns:
            list: قائمة بالبنود المُنشأة
        """
        components = []
        
        for template in structure:
            component = SalaryComponentService.create_from_template(
                employee=employee,
                template=template,
                effective_from=effective_from,
                contract=contract
            )
            components.append(component)
        
        logger.info(
            f"تم نسخ {len(components)} بند راتب للموظف {employee.get_full_name_ar()}"
        )
        
        return components
    
    @staticmethod
    @transaction.atomic
    def add_component(employee, code, name, component_type, calculation_method='fixed',
                     amount=None, percentage=None, formula=None, **kwargs):
        """
        إضافة بند راتب جديد لموظف
        
        Args:
            employee: الموظف
            code: كود البند (مثل: BASIC, HOUSING)
            name: اسم البند
            component_type: نوع البند (earning/deduction)
            calculation_method: طريقة الحساب (fixed/percentage/formula)
            amount: المبلغ الثابت
            percentage: النسبة المئوية
            formula: الصيغة الحسابية
            **kwargs: حقول إضافية
        
        Returns:
            SalaryComponent: البند المُنشأ
        """
        from ..models import SalaryComponent
        
        # التحقق من القيم
        if calculation_method == 'fixed' and not amount:
            raise ValueError('المبلغ مطلوب للطريقة الثابتة')
        
        if calculation_method == 'percentage' and not percentage:
            raise ValueError('النسبة مطلوبة للطريقة النسبية')
        
        if calculation_method == 'formula' and not formula:
            raise ValueError('الصيغة مطلوبة للطريقة الحسابية')
        
        component = SalaryComponent.objects.create(
            employee=employee,
            code=code,
            name=name,
            component_type=component_type,
            calculation_method=calculation_method,
            amount=amount or Decimal('0'),
            percentage=percentage,
            formula=formula or '',
            **kwargs
        )
        
        logger.info(
            f"تم إضافة بند راتب - الموظف: {employee.get_full_name_ar()}, "
            f"البند: {component.name}, المبلغ: {component.amount}"
        )
        
        return component
    
    @staticmethod
    @transaction.atomic
    def update_component(component_id, **updates):
        """
        تحديث بند راتب
        
        Args:
            component_id: معرف البند
            **updates: الحقول المراد تحديثها
        
        Returns:
            SalaryComponent: البند المُحدث
        """
        from ..models import SalaryComponent
        
        component = SalaryComponent.objects.get(id=component_id)
        
        for key, value in updates.items():
            if hasattr(component, key):
                setattr(component, key, value)
        
        component.save()
        
        logger.info(
            f"تم تحديث بند راتب - الموظف: {component.employee.get_full_name_ar()}, "
            f"البند: {component.name}"
        )
        
        return component
    
    @staticmethod
    @transaction.atomic
    def deactivate_component(component_id, effective_to=None):
        """
        إلغاء تفعيل بند راتب
        
        Args:
            component_id: معرف البند
            effective_to: تاريخ انتهاء السريان (اختياري)
        
        Returns:
            SalaryComponent: البند المُلغى
        """
        from ..models import SalaryComponent
        from django.utils import timezone
        
        component = SalaryComponent.objects.get(id=component_id)
        component.is_active = False
        
        if effective_to:
            component.effective_to = effective_to
        else:
            component.effective_to = timezone.now().date()
        
        component.save()
        
        logger.info(
            f"تم إلغاء تفعيل بند راتب - الموظف: {component.employee.get_full_name_ar()}, "
            f"البند: {component.name}"
        )
        
        return component
    
    @staticmethod
    def get_active_components(employee, month=None, include_contract_components=True):
        """
        الحصول على بنود الراتب النشطة لموظف
        
        Args:
            employee: الموظف
            month: الشهر (اختياري - افتراضياً الشهر الحالي)
            include_contract_components: تضمين بنود العقد (افتراضياً True)
        
        Returns:
            QuerySet: بنود الراتب النشطة (من الموظف + من العقد إن وجد)
        """
        from django.db.models import Q
        from django.utils import timezone
        
        if not month:
            month = timezone.now().date()
        
        # جلب بنود الموظف النشطة
        components = employee.salary_components.filter(
            is_active=True
        )
        
        # فصل بنود العقد عن بنود التعديلات
        contract_components = components.filter(
            Q(is_from_contract=True) | Q(source='contract')
        )
        
        adjustment_components = components.exclude(
            Q(is_from_contract=True) | Q(source='contract')
        )
        
        # بنود العقد: نأخذها كلها إذا كانت نشطة (بغض النظر عن effective_from)
        # لأن العقد النشط يعني أن بنوده سارية
        valid_contract_components = contract_components.filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=month)
        )
        
        # بنود التعديلات: نطبق عليها فلتر التواريخ العادي
        valid_adjustment_components = adjustment_components.filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=month)
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=month)
        )
        
        # دمج البنود
        from django.db.models import Q
        component_ids = list(valid_contract_components.values_list('id', flat=True)) + \
                       list(valid_adjustment_components.values_list('id', flat=True))
        
        components = employee.salary_components.filter(id__in=component_ids)
        
        # إذا كان مطلوب تضمين بنود العقد، نتأكد أنها موجودة
        if include_contract_components:
            # التحقق من وجود بنود منسوخة من العقد
            # إذا لم توجد، نحاول جلبها من العقد النشط مباشرة
            contract_components_exist = components.filter(is_from_contract=True).exists()
            
            if not contract_components_exist:
                # محاولة جلب العقد النشط
                active_contract = employee.contracts.filter(status='active').first()
        
        return components.order_by('component_type', 'order')
    
    @staticmethod
    def calculate_total_salary(employee, month=None):
        """
        حساب إجمالي الراتب لموظف
        
        Args:
            employee: الموظف
            month: الشهر (اختياري)
        
        Returns:
            dict: {
                'basic_salary': الراتب الأساسي,
                'total_earnings': إجمالي المستحقات,
                'total_deductions': إجمالي الاستقطاعات,
                'net_salary': صافي الراتب
            }
        """
        components = SalaryComponentService.get_active_components(employee, month)
        
        # حساب الراتب الأساسي من العقد النشط أولاً
        active_contract = employee.contracts.filter(status='active').first()
        if active_contract and active_contract.basic_salary:
            basic_salary = Decimal(str(active_contract.basic_salary))
        else:
            # إذا لم يوجد عقد نشط، ابحث في البنود
            basic_component = components.filter(is_basic=True).first()
            basic_salary = basic_component.amount if basic_component else Decimal('0')
        
        # إعداد السياق للحساب
        context = {
            'basic_salary': basic_salary,
            'gross_salary': basic_salary,  # إضافة gross_salary للـ formulas
            'worked_days': 30,
            'month': month
        }
        
        # حساب المستحقات (بدون الراتب الأساسي لتجنب التكرار)
        earnings = components.filter(component_type='earning', is_basic=False)
        earnings_sum = sum((c.calculate_amount(context) for c in earnings), Decimal('0'))
        
        # إضافة الراتب الأساسي لإجمالي المستحقات
        total_earnings = basic_salary + earnings_sum
        
        # حساب الاستقطاعات
        deductions = components.filter(component_type='deduction')
        total_deductions = sum((c.calculate_amount(context) for c in deductions), Decimal('0'))
        
        return {
            'basic_salary': basic_salary,
            'total_earnings': total_earnings,
            'total_deductions': total_deductions,
            'net_salary': total_earnings - total_deductions
        }
