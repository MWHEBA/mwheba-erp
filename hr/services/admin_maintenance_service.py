"""
خدمة أدوات الصيانة الإدارية لنظام الموارد البشرية
"""
from django.db import transaction, models
from django.utils import timezone
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional
from ..models import SalaryComponent, Employee, Contract
from .component_classification_service import ComponentClassificationService


class AdminMaintenanceService:
    """خدمة شاملة لأدوات الصيانة الإدارية"""
    
    @staticmethod
    def get_system_overview() -> Dict:
        """
        الحصول على نظرة عامة شاملة على النظام
        
        Returns:
            dict: إحصائيات شاملة للنظام
        """
        # إحصائيات الموظفين
        total_employees = Employee.objects.count()
        active_employees = Employee.objects.filter(status='active').count()
        
        # إحصائيات العقود
        total_contracts = Contract.objects.count()
        active_contracts = Contract.objects.filter(status='active').count()
        draft_contracts = Contract.objects.filter(status='draft').count()
        expiring_contracts = Contract.objects.filter(
            status='active',
            end_date__isnull=False,
            end_date__lte=date.today() + timedelta(days=30)
        ).count()
        
        # إحصائيات البنود
        total_components = SalaryComponent.objects.count()
        active_components = SalaryComponent.objects.filter(is_active=True).count()
        inactive_components = SalaryComponent.objects.filter(is_active=False).count()
        
        # البنود حسب المصدر
        components_by_source = {}
        for source, _ in SalaryComponent.COMPONENT_SOURCE_CHOICES:
            count = SalaryComponent.objects.filter(source=source, is_active=True).count()
            components_by_source[source] = count
        
        # البنود المنتهية والقابلة للتجديد
        expiring_components = ComponentClassificationService.get_expiring_components().count()
        renewable_components = SalaryComponent.objects.filter(
            is_active=True,
            auto_renew=True,
            effective_to__lte=date.today() + timedelta(days=7)
        ).count()
        
        # البنود اليتيمة (بدون موظف نشط أو عقد)
        orphaned_components = SalaryComponent.objects.filter(
            models.Q(employee__isnull=True) |
            ~models.Q(employee__status='active') |
            models.Q(contract__isnull=True)
        ).count()
        
        # البيانات المتضاربة
        duplicate_components = AdminMaintenanceService._find_duplicate_components()
        inconsistent_data = AdminMaintenanceService._find_data_inconsistencies()
        
        return {
            'employees': {
                'total': total_employees,
                'active': active_employees,
                'inactive': total_employees - active_employees
            },
            'contracts': {
                'total': total_contracts,
                'active': active_contracts,
                'draft': draft_contracts,
                'expiring_soon': expiring_contracts
            },
            'components': {
                'total': total_components,
                'active': active_components,
                'inactive': inactive_components,
                'by_source': components_by_source,
                'expiring': expiring_components,
                'renewable': renewable_components,
                'orphaned': orphaned_components
            },
            'data_quality': {
                'duplicate_components': len(duplicate_components),
                'inconsistent_records': len(inconsistent_data),
                'last_cleanup': AdminMaintenanceService._get_last_cleanup_date()
            }
        }
    
    @staticmethod
    def cleanup_expired_components(days_old: int = 90, dry_run: bool = True) -> Dict:
        """
        تنظيف البنود المنتهية القديمة
        
        Args:
            days_old: عمر البنود بالأيام
            dry_run: تشغيل تجريبي بدون حذف فعلي
            
        Returns:
            dict: نتائج التنظيف
        """
        cutoff_date = date.today() - timedelta(days=days_old)
        
        # البنود المرشحة للحذف
        candidates = SalaryComponent.objects.filter(
            is_active=False,
            effective_to__lt=cutoff_date
        ).select_related('employee', 'contract')
        
        # تصنيف البنود
        by_source = {}
        by_employee = {}
        total_amount = 0
        
        for component in candidates:
            # حسب المصدر
            source = component.source or 'unknown'
            if source not in by_source:
                by_source[source] = {'count': 0, 'components': []}
            by_source[source]['count'] += 1
            by_source[source]['components'].append({
                'id': component.id,
                'name': component.name,
                'amount': component.amount,
                'employee': component.employee.get_full_name_ar() if component.employee else 'غير محدد',
                'effective_to': component.effective_to
            })
            
            # حسب الموظف
            employee_name = component.employee.get_full_name_ar() if component.employee else 'غير محدد'
            if employee_name not in by_employee:
                by_employee[employee_name] = 0
            by_employee[employee_name] += 1
            
            # المبلغ الإجمالي
            total_amount += component.amount
        
        result = {
            'total_candidates': candidates.count(),
            'cutoff_date': cutoff_date,
            'by_source': by_source,
            'by_employee': by_employee,
            'total_amount': total_amount,
            'dry_run': dry_run
        }
        
        # الحذف الفعلي
        if not dry_run and candidates.exists():
            deleted_count = 0
            protected_count = 0
            
            for component in candidates:
                try:
                    component.delete()
                    deleted_count += 1
                except models.ProtectedError:
                    # البند محمي بسبب ارتباطه بقسائم راتب
                    protected_count += 1
                    continue
            
            result['deleted_count'] = deleted_count
            result['protected_count'] = protected_count
            result['cleanup_date'] = timezone.now()
            
            # تسجيل عملية التنظيف
            AdminMaintenanceService._log_cleanup_operation('expired_components', {
                'deleted_count': deleted_count,
                'protected_count': protected_count,
                'cutoff_date': cutoff_date.isoformat(),
                'total_amount': total_amount
            })
        
        return result
    
    @staticmethod
    def cleanup_orphaned_components(dry_run: bool = True) -> Dict:
        """
        تنظيف البنود اليتيمة (بدون موظف أو عقد صحيح)
        
        Args:
            dry_run: تشغيل تجريبي بدون حذف فعلي
            
        Returns:
            dict: نتائج التنظيف
        """
        # البنود اليتيمة
        orphaned = SalaryComponent.objects.filter(
            models.Q(employee__isnull=True) |
            ~models.Q(employee__status='active') |
            models.Q(contract__isnull=True)
        ).select_related('employee', 'contract')
        
        orphaned_list = []
        for component in orphaned:
            orphaned_list.append({
                'id': component.id,
                'name': component.name,
                'amount': component.amount,
                'employee': component.employee.get_full_name_ar() if component.employee else 'غير محدد',
                'contract': f'عقد {component.contract.contract_number}' if component.contract else 'غير محدد',
                'is_active': component.is_active,
                'reason': AdminMaintenanceService._get_orphan_reason(component)
            })
        
        result = {
            'total_orphaned': orphaned.count(),
            'orphaned_components': orphaned_list,
            'dry_run': dry_run
        }
        
        # الحذف الفعلي
        if not dry_run and orphaned.exists():
            deleted_count = 0
            protected_count = 0
            
            for component in orphaned:
                try:
                    component.delete()
                    deleted_count += 1
                except models.ProtectedError:
                    # البند محمي بسبب ارتباطه بقسائم راتب
                    protected_count += 1
                    continue
            
            result['deleted_count'] = deleted_count
            result['protected_count'] = protected_count
            result['cleanup_date'] = timezone.now()
            
            # تسجيل عملية التنظيف
            AdminMaintenanceService._log_cleanup_operation('orphaned_components', {
                'deleted_count': deleted_count,
                'protected_count': protected_count,
                'orphaned_list': orphaned_list
            })
        
        return result
    
    @staticmethod
    def fix_data_inconsistencies(dry_run: bool = True) -> Dict:
        """
        إصلاح التضارب في البيانات
        
        Args:
            dry_run: تشغيل تجريبي بدون تطبيق فعلي
            
        Returns:
            dict: نتائج الإصلاح
        """
        fixes_applied = []
        
        # 1. إصلاح البنود بدون تصنيف مصدر
        unclassified = SalaryComponent.objects.filter(
            models.Q(source__isnull=True) | models.Q(source='')
        )
        
        for component in unclassified:
            old_source = component.source
            new_source = component.auto_classify_source()
            
            if not dry_run:
                component.source = new_source
                component.save()
            
            fixes_applied.append({
                'type': 'source_classification',
                'component_id': component.id,
                'component_name': component.name,
                'old_value': old_source,
                'new_value': new_source
            })
        
        # 2. إصلاح التواريخ المتضاربة
        invalid_dates = SalaryComponent.objects.filter(
            effective_from__gt=models.F('effective_to')
        )
        
        for component in invalid_dates:
            old_to = component.effective_to
            new_to = component.effective_from + timedelta(days=365) if component.effective_from else None
            
            if not dry_run and new_to:
                component.effective_to = new_to
                component.save()
            
            fixes_applied.append({
                'type': 'date_correction',
                'component_id': component.id,
                'component_name': component.name,
                'old_value': old_to,
                'new_value': new_to
            })
        
        # 3. إصلاح البنود المكررة
        duplicates = AdminMaintenanceService._find_duplicate_components()
        
        for duplicate_group in duplicates:
            # الاحتفاظ بالأحدث وحذف الباقي
            components = duplicate_group['components']
            if len(components) > 1:
                latest = max(components, key=lambda x: x.created_at)
                to_remove = [c for c in components if c.id != latest.id]
                
                for component in to_remove:
                    if not dry_run:
                        component.delete()
                    
                    fixes_applied.append({
                        'type': 'duplicate_removal',
                        'component_id': component.id,
                        'component_name': component.name,
                        'kept_component': latest.id,
                        'reason': 'duplicate'
                    })
        
        result = {
            'total_fixes': len(fixes_applied),
            'fixes_by_type': {},
            'fixes_applied': fixes_applied,
            'dry_run': dry_run
        }
        
        # تجميع الإصلاحات حسب النوع
        for fix in fixes_applied:
            fix_type = fix['type']
            if fix_type not in result['fixes_by_type']:
                result['fixes_by_type'][fix_type] = 0
            result['fixes_by_type'][fix_type] += 1
        
        if not dry_run and fixes_applied:
            # تسجيل عملية الإصلاح
            AdminMaintenanceService._log_cleanup_operation('data_fixes', result)
        
        return result
    
    @staticmethod
    def generate_maintenance_report() -> Dict:
        """
        توليد تقرير صيانة شامل
        
        Returns:
            dict: تقرير الصيانة
        """
        overview = AdminMaintenanceService.get_system_overview()
        
        # تحليل البنود المنتهية
        expired_analysis = AdminMaintenanceService.cleanup_expired_components(dry_run=True)
        
        # تحليل البنود اليتيمة
        orphaned_analysis = AdminMaintenanceService.cleanup_orphaned_components(dry_run=True)
        
        # تحليل التضارب
        inconsistencies_analysis = AdminMaintenanceService.fix_data_inconsistencies(dry_run=True)
        
        # توصيات الصيانة
        recommendations = AdminMaintenanceService._generate_maintenance_recommendations(
            overview, expired_analysis, orphaned_analysis, inconsistencies_analysis
        )
        
        return {
            'generated_at': timezone.now(),
            'system_overview': overview,
            'maintenance_analysis': {
                'expired_components': expired_analysis,
                'orphaned_components': orphaned_analysis,
                'data_inconsistencies': inconsistencies_analysis
            },
            'recommendations': recommendations,
            'next_maintenance_date': date.today() + timedelta(days=30)
        }
    
    @staticmethod
    def _find_duplicate_components() -> List[Dict]:
        """البحث عن البنود المكررة"""
        # البحث عن البنود المكررة بناءً على الموظف والاسم والنوع
        duplicates = []
        
        components = SalaryComponent.objects.filter(is_active=True).values(
            'employee', 'name', 'component_type'
        ).annotate(
            count=models.Count('id')
        ).filter(count__gt=1)
        
        for duplicate in components:
            duplicate_components = SalaryComponent.objects.filter(
                employee=duplicate['employee'],
                name=duplicate['name'],
                component_type=duplicate['component_type'],
                is_active=True
            )
            
            duplicates.append({
                'criteria': duplicate,
                'components': list(duplicate_components)
            })
        
        return duplicates
    
    @staticmethod
    def _find_data_inconsistencies() -> List[Dict]:
        """البحث عن التضارب في البيانات"""
        inconsistencies = []
        
        # البنود بدون تصنيف
        unclassified = SalaryComponent.objects.filter(
            models.Q(source__isnull=True) | models.Q(source='')
        ).count()
        
        if unclassified > 0:
            inconsistencies.append({
                'type': 'unclassified_components',
                'count': unclassified,
                'description': 'بنود بدون تصنيف مصدر'
            })
        
        # تواريخ متضاربة
        invalid_dates = SalaryComponent.objects.filter(
            effective_from__gt=models.F('effective_to')
        ).count()
        
        if invalid_dates > 0:
            inconsistencies.append({
                'type': 'invalid_dates',
                'count': invalid_dates,
                'description': 'تواريخ بداية أكبر من تواريخ النهاية'
            })
        
        return inconsistencies
    
    @staticmethod
    def _get_orphan_reason(component: SalaryComponent) -> str:
        """تحديد سبب كون البند يتيماً"""
        if not component.employee:
            return 'لا يوجد موظف مرتبط'
        elif component.employee.status != 'active':
            return 'الموظف غير نشط'
        elif not component.contract:
            return 'لا يوجد عقد مرتبط'
        else:
            return 'سبب غير محدد'
    
    @staticmethod
    def _generate_maintenance_recommendations(overview, expired, orphaned, inconsistencies) -> List[Dict]:
        """توليد توصيات الصيانة"""
        recommendations = []
        
        # توصيات البنود المنتهية
        if expired['total_candidates'] > 0:
            priority = 'high' if expired['total_candidates'] > 100 else 'medium'
            recommendations.append({
                'type': 'cleanup_expired',
                'priority': priority,
                'title': f'تنظيف {expired["total_candidates"]} بند منتهي',
                'description': f'يوجد {expired["total_candidates"]} بند منتهي منذ أكثر من 90 يوم',
                'action': 'cleanup_expired_components',
                'estimated_time': '5-10 دقائق'
            })
        
        # توصيات البنود اليتيمة
        if orphaned['total_orphaned'] > 0:
            recommendations.append({
                'type': 'cleanup_orphaned',
                'priority': 'medium',
                'title': f'تنظيف {orphaned["total_orphaned"]} بند يتيم',
                'description': 'بنود غير مرتبطة بموظفين أو عقود صحيحة',
                'action': 'cleanup_orphaned_components',
                'estimated_time': '2-5 دقائق'
            })
        
        # توصيات إصلاح التضارب
        if inconsistencies['total_fixes'] > 0:
            recommendations.append({
                'type': 'fix_inconsistencies',
                'priority': 'high',
                'title': f'إصلاح {inconsistencies["total_fixes"]} تضارب في البيانات',
                'description': 'بيانات متضاربة تحتاج إصلاح',
                'action': 'fix_data_inconsistencies',
                'estimated_time': '10-15 دقيقة'
            })
        
        # توصية التجديد التلقائي
        renewable_count = overview['components']['renewable']
        if renewable_count > 0:
            recommendations.append({
                'type': 'auto_renewal',
                'priority': 'medium',
                'title': f'تجديد {renewable_count} بند تلقائياً',
                'description': 'بنود قابلة للتجديد التلقائي',
                'action': 'process_auto_renewals',
                'estimated_time': '1-2 دقيقة'
            })
        
        return recommendations
    
    @staticmethod
    def _get_last_cleanup_date() -> Optional[str]:
        """الحصول على تاريخ آخر عملية تنظيف"""
        # يمكن تطوير هذا لاحقاً لحفظ تواريخ التنظيف في قاعدة البيانات
        return None
    
    @staticmethod
    def _log_cleanup_operation(operation_type: str, details: Dict):
        """تسجيل عملية التنظيف"""
        # يمكن تطوير هذا لاحقاً لحفظ سجل العمليات
        pass
