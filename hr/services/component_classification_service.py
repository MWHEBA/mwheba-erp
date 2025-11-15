"""
خدمة التصنيف الذكي لبنود الراتب
"""
from django.db import transaction
from django.utils import timezone
from hr.models import SalaryComponent
import logging

logger = logging.getLogger(__name__)


class ComponentClassificationService:
    """خدمة التصنيف الذكي لبنود الراتب"""
    
    @staticmethod
    def analyze_employee_components(employee):
        """تحليل بنود موظف معين - للتوافق مع الاستدعاءات القديمة"""
        from .unified_contract_service import UnifiedContractService
        
        # استخدام الخدمة الموحدة للتحليل
        unified_service = UnifiedContractService()
        return unified_service.get_employee_component_analysis(employee)
    
    @staticmethod
    def classify_all_existing_components():
        """تصنيف جميع البنود الموجودة تلقائياً"""
        
        with transaction.atomic():
            updated_count = 0
            
            # البنود المنسوخة من العقد
            contract_components = SalaryComponent.objects.filter(
                is_from_contract=True
            ).exclude(source='contract')
            
            for component in contract_components:
                component.source = 'contract'
                component.save(update_fields=['source'])
                updated_count += 1
            
            logger.info(f"تم تصنيف {contract_components.count()} بند كـ 'من العقد'")
            
            # البنود المؤقتة (لها تاريخ انتهاء)
            temporary_components = SalaryComponent.objects.filter(
                is_from_contract=False,
                effective_to__isnull=False
            ).exclude(source__in=['temporary', 'personal', 'exceptional'])
            
            for component in temporary_components:
                # تصنيف ذكي بناءً على الاسم
                auto_source = component.auto_classify_source()
                component.source = auto_source
                component.save(update_fields=['source'])
                updated_count += 1
            
            logger.info(f"تم تصنيف {temporary_components.count()} بند مؤقت")
            
            # البنود الدائمة (بدون تاريخ انتهاء وليست من العقد)
            permanent_components = SalaryComponent.objects.filter(
                is_from_contract=False,
                effective_to__isnull=True
            ).exclude(source='adjustment')
            
            for component in permanent_components:
                component.source = 'adjustment'
                component.save(update_fields=['source'])
                updated_count += 1
            
            logger.info(f"تم تصنيف {permanent_components.count()} بند كـ 'تعديل'")
            
            return updated_count
    
    @staticmethod
    def get_components_by_source(employee=None):
        """الحصول على البنود مصنفة حسب المصدر"""
        
        queryset = SalaryComponent.objects.all()
        if employee:
            queryset = queryset.filter(employee=employee)
        
        return {
            'contract': queryset.filter(source='contract', is_active=True),
            'temporary': queryset.filter(source='temporary', is_active=True),
            'personal': queryset.filter(source='personal', is_active=True),
            'exceptional': queryset.filter(source='exceptional', is_active=True),
            'adjustment': queryset.filter(source='adjustment', is_active=True),
            'inactive': queryset.filter(is_active=False),
        }
    
    @staticmethod
    def get_expiring_components(days_ahead=30):
        """الحصول على البنود التي ستنتهي قريباً"""
        
        from datetime import timedelta
        
        cutoff_date = timezone.now().date() + timedelta(days=days_ahead)
        
        return SalaryComponent.objects.filter(
            is_active=True,
            effective_to__isnull=False,
            effective_to__lte=cutoff_date,
            effective_to__gt=timezone.now().date()
        ).select_related('employee')
    
    @staticmethod
    def get_renewable_components():
        """الحصول على البنود القابلة للتجديد التلقائي"""
        
        components = []
        for component in SalaryComponent.objects.filter(
            is_active=True,
            auto_renew=True,
            effective_to__isnull=False
        ).select_related('employee'):
            if component.needs_renewal():
                components.append(component)
        
        return components
    
    @staticmethod
    def renew_component(component, new_end_date=None, renewed_by=None):
        """تجديد بند راتب"""
        
        if not component.auto_renew or not component.renewal_period_months:
            return False, "البند غير قابل للتجديد التلقائي"
        
        if new_end_date is None:
            new_end_date = component.get_renewal_date()
        
        if not new_end_date:
            return False, "لا يمكن حساب تاريخ التجديد"
        
        with transaction.atomic():
            # تحديث تاريخ الانتهاء
            old_end_date = component.effective_to
            component.effective_to = new_end_date
            component.save(update_fields=['effective_to'])
            
            logger.info(
                f"تم تجديد البند {component.name} للموظف {component.employee} "
                f"من {old_end_date} إلى {new_end_date}"
            )
            
            return True, f"تم تجديد البند حتى {new_end_date}"
    
    @staticmethod
    def bulk_renew_components():
        """تجديد جميع البنود القابلة للتجديد"""
        
        renewable_components = ComponentClassificationService.get_renewable_components()
        success_count = 0
        errors = []
        
        for component in renewable_components:
            success, message = ComponentClassificationService.renew_component(component)
            if success:
                success_count += 1
            else:
                errors.append(f"{component.name}: {message}")
        
        return success_count, errors