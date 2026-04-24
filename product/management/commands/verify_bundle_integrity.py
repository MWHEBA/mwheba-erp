# -*- coding: utf-8 -*-
"""
أمر إدارة للتحقق من تكامل بيانات المنتجات المجمعة
Bundle Integrity Verification Management Command

Requirements: 10.5
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from typing import Dict, List, Any
import logging

from product.models import Product, BundleComponent
from product.services.stock_calculation_engine import StockCalculationEngine
from product.exceptions import BundleIntegrityError

logger = logging.getLogger('bundle_system')


class Command(BaseCommand):
    help = 'التحقق من تكامل بيانات المنتجات المجمعة وإصلاح المشاكل'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='إصلاح المشاكل المكتشفة تلقائياً'
        )
        
        parser.add_argument(
            '--bundle-id',
            type=int,
            help='فحص منتج مجمع محدد فقط'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='عرض تفاصيل إضافية'
        )
        
        parser.add_argument(
            '--report-file',
            type=str,
            help='حفظ التقرير في ملف'
        )
    
    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        self.verbose = options.get('verbose', False)
        self.fix_issues = options.get('fix', False)
        self.bundle_id = options.get('bundle_id')
        self.report_file = options.get('report_file')
        
        self.stdout.write(
            self.style.SUCCESS('بدء التحقق من تكامل بيانات المنتجات المجمعة...')
        )
        
        try:
            # تشغيل فحص التكامل
            integrity_report = self.run_integrity_check()
            
            # عرض النتائج
            self.display_results(integrity_report)
            
            # حفظ التقرير إذا طُلب ذلك
            if self.report_file:
                self.save_report(integrity_report)
            
            # تحديد حالة الخروج
            if integrity_report['critical_issues']:
                raise CommandError('تم اكتشاف مشاكل حرجة في تكامل البيانات')
            elif integrity_report['warning_issues']:
                self.stdout.write(
                    self.style.WARNING('تم اكتشاف مشاكل تحتاج لمراجعة')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('جميع فحوصات التكامل نجحت ✓')
                )
                
        except Exception as e:
            logger.error(f"خطأ في فحص تكامل المنتجات المجمعة: {str(e)}")
            raise CommandError(f'خطأ في تشغيل الفحص: {str(e)}')
    
    def run_integrity_check(self) -> Dict[str, Any]:
        """تشغيل فحص شامل لتكامل البيانات"""
        report = {
            'timestamp': timezone.now(),
            'bundles_checked': 0,
            'critical_issues': [],
            'warning_issues': [],
            'info_issues': [],
            'fixed_issues': [],
            'statistics': {}
        }
        
        # تحديد المنتجات المجمعة للفحص
        if self.bundle_id:
            bundles = Product.objects.filter(id=self.bundle_id, is_bundle=True)
            if not bundles.exists():
                raise CommandError(f'المنتج المجمع {self.bundle_id} غير موجود')
        else:
            bundles = Product.objects.filter(is_bundle=True)
        
        report['bundles_checked'] = bundles.count()
        
        if self.verbose:
            self.stdout.write(f'فحص {report["bundles_checked"]} منتج مجمع...')
        
        # فحص كل منتج مجمع
        for bundle in bundles:
            bundle_issues = self.check_bundle_integrity(bundle)
            
            # تصنيف المشاكل
            for issue in bundle_issues:
                if issue['severity'] == 'critical':
                    report['critical_issues'].append(issue)
                elif issue['severity'] == 'warning':
                    report['warning_issues'].append(issue)
                else:
                    report['info_issues'].append(issue)
                
                # محاولة الإصلاح إذا طُلب ذلك
                if self.fix_issues and issue.get('fixable', False):
                    fix_result = self.fix_issue(issue)
                    if fix_result['success']:
                        report['fixed_issues'].append(fix_result)
        
        # إضافة إحصائيات عامة
        report['statistics'] = self.generate_statistics(bundles)
        
        return report
    
    def check_bundle_integrity(self, bundle: Product) -> List[Dict[str, Any]]:
        """فحص تكامل منتج مجمع واحد"""
        issues = []
        
        try:
            # فحص 1: وجود مكونات
            components = bundle.components.all()
            if not components.exists():
                issues.append({
                    'type': 'no_components',
                    'severity': 'critical',
                    'message': f'المنتج المجمع "{bundle.name}" لا يحتوي على مكونات',
                    'bundle_id': bundle.id,
                    'bundle_name': bundle.name,
                    'fixable': False
                })
            
            # فحص 2: صحة المكونات
            for component in components:
                component_issues = self.check_component_integrity(bundle, component)
                issues.extend(component_issues)
            
            # فحص 3: الاعتماد الدائري
            circular_dependency = self.check_circular_dependency(bundle)
            if circular_dependency:
                issues.append({
                    'type': 'circular_dependency',
                    'severity': 'critical',
                    'message': f'اعتماد دائري في المنتج المجمع "{bundle.name}"',
                    'bundle_id': bundle.id,
                    'bundle_name': bundle.name,
                    'dependency_chain': circular_dependency,
                    'fixable': False
                })
            
            # فحص 4: حساب المخزون
            try:
                calculated_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
                if calculated_stock < 0:
                    issues.append({
                        'type': 'negative_stock',
                        'severity': 'warning',
                        'message': f'المنتج المجمع "{bundle.name}" له مخزون سالب: {calculated_stock}',
                        'bundle_id': bundle.id,
                        'bundle_name': bundle.name,
                        'calculated_stock': calculated_stock,
                        'fixable': True
                    })
            except Exception as e:
                issues.append({
                    'type': 'stock_calculation_error',
                    'severity': 'critical',
                    'message': f'خطأ في حساب مخزون المنتج المجمع "{bundle.name}": {str(e)}',
                    'bundle_id': bundle.id,
                    'bundle_name': bundle.name,
                    'error': str(e),
                    'fixable': False
                })
            
            # فحص 5: تطابق الأسعار
            price_issues = self.check_price_consistency(bundle)
            issues.extend(price_issues)
            
        except Exception as e:
            issues.append({
                'type': 'bundle_check_error',
                'severity': 'critical',
                'message': f'خطأ في فحص المنتج المجمع "{bundle.name}": {str(e)}',
                'bundle_id': bundle.id,
                'bundle_name': bundle.name,
                'error': str(e),
                'fixable': False
            })
        
        return issues
    
    def check_component_integrity(self, bundle: Product, component: BundleComponent) -> List[Dict[str, Any]]:
        """فحص تكامل مكون واحد"""
        issues = []
        
        # فحص وجود المنتج المكون
        if not component.component_product:
            issues.append({
                'type': 'missing_component_product',
                'severity': 'critical',
                'message': f'مكون مفقود في المنتج المجمع "{bundle.name}"',
                'bundle_id': bundle.id,
                'component_id': component.id,
                'fixable': True
            })
            return issues
        
        # فحص حالة المكون
        if not component.component_product.is_active:
            issues.append({
                'type': 'inactive_component',
                'severity': 'warning',
                'message': f'المكون "{component.component_product.name}" غير نشط في المنتج المجمع "{bundle.name}"',
                'bundle_id': bundle.id,
                'component_id': component.component_product.id,
                'component_name': component.component_product.name,
                'fixable': False
            })
        
        # فحص الكمية المطلوبة
        if component.required_quantity <= 0:
            issues.append({
                'type': 'invalid_quantity',
                'severity': 'critical',
                'message': f'كمية غير صحيحة للمكون "{component.component_product.name}" في المنتج المجمع "{bundle.name}": {component.required_quantity}',
                'bundle_id': bundle.id,
                'component_id': component.component_product.id,
                'required_quantity': component.required_quantity,
                'fixable': True
            })
        
        # فحص المخزون المتاح
        if hasattr(component.component_product, 'current_stock'):
            if component.component_product.current_stock < component.required_quantity:
                issues.append({
                    'type': 'insufficient_component_stock',
                    'severity': 'info',
                    'message': f'مخزون المكون "{component.component_product.name}" أقل من المطلوب في المنتج المجمع "{bundle.name}"',
                    'bundle_id': bundle.id,
                    'component_id': component.component_product.id,
                    'available_stock': component.component_product.current_stock,
                    'required_quantity': component.required_quantity,
                    'fixable': False
                })
        
        return issues
    
    def check_circular_dependency(self, bundle: Product, visited: List[int] = None) -> List[int]:
        """فحص الاعتماد الدائري"""
        if visited is None:
            visited = []
        
        if bundle.id in visited:
            return visited + [bundle.id]
        
        visited = visited + [bundle.id]
        
        # فحص مكونات المنتج المجمع
        for component in bundle.components.all():
            if component.component_product and component.component_product.is_bundle:
                circular_path = self.check_circular_dependency(
                    component.component_product, visited
                )
                if circular_path:
                    return circular_path
        
        return None
    
    def check_price_consistency(self, bundle: Product) -> List[Dict[str, Any]]:
        """فحص تطابق الأسعار"""
        issues = []
        
        try:
            # حساب مجموع أسعار تكلفة المكونات
            components_total = sum(
                component.component_product.cost_price * component.required_quantity
                for component in bundle.components.select_related('component_product').all()
                if component.component_product
            )
            
            # مقارنة مع سعر المنتج المجمع
            bundle_price = bundle.selling_price or 0
            
            if bundle_price > 0 and components_total > 0:
                price_difference = abs(bundle_price - components_total)
                percentage_difference = (price_difference / bundle_price) * 100
                
                if percentage_difference > 10:  # أكثر من 10% اختلاف
                    issues.append({
                        'type': 'price_inconsistency',
                        'severity': 'warning',
                        'message': f'اختلاف كبير في السعر للمنتج المجمع "{bundle.name}": سعر المنتج {bundle_price}, مجموع تكلفة المكونات {components_total}',
                        'bundle_id': bundle.id,
                        'bundle_price': bundle_price,
                        'components_total': components_total,
                        'difference_percentage': percentage_difference,
                        'fixable': False
                    })
        
        except Exception as e:
            issues.append({
                'type': 'price_check_error',
                'severity': 'warning',
                'message': f'خطأ في فحص أسعار المنتج المجمع "{bundle.name}": {str(e)}',
                'bundle_id': bundle.id,
                'error': str(e),
                'fixable': False
            })
        
        return issues
    
    def fix_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """محاولة إصلاح مشكلة"""
        fix_result = {
            'issue_type': issue['type'],
            'success': False,
            'message': '',
            'bundle_id': issue.get('bundle_id')
        }
        
        try:
            with transaction.atomic():
                if issue['type'] == 'missing_component_product':
                    # حذف المكون المفقود
                    BundleComponent.objects.filter(id=issue['component_id']).delete()
                    fix_result['success'] = True
                    fix_result['message'] = 'تم حذف المكون المفقود'
                
                elif issue['type'] == 'invalid_quantity':
                    # تصحيح الكمية إلى 1
                    component = BundleComponent.objects.get(
                        bundle_product_id=issue['bundle_id'],
                        component_product_id=issue['component_id']
                    )
                    component.required_quantity = 1
                    component.save()
                    fix_result['success'] = True
                    fix_result['message'] = 'تم تصحيح الكمية إلى 1'
                
                elif issue['type'] == 'negative_stock':
                    # إعادة حساب المخزون
                    bundle = Product.objects.get(id=issue['bundle_id'])
                    new_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
                    fix_result['success'] = True
                    fix_result['message'] = f'تم إعادة حساب المخزون: {new_stock}'
                
        except Exception as e:
            fix_result['message'] = f'فشل في الإصلاح: {str(e)}'
        
        return fix_result
    
    def generate_statistics(self, bundles) -> Dict[str, Any]:
        """إنشاء إحصائيات عامة"""
        try:
            total_components = BundleComponent.objects.filter(
                bundle_product__in=bundles
            ).count()
            
            active_bundles = bundles.filter(is_active=True).count()
            
            return {
                'total_bundles': bundles.count(),
                'active_bundles': active_bundles,
                'inactive_bundles': bundles.count() - active_bundles,
                'total_components': total_components,
                'avg_components_per_bundle': total_components / bundles.count() if bundles.count() > 0 else 0
            }
        except Exception:
            return {}
    
    def display_results(self, report: Dict[str, Any]) -> None:
        """عرض نتائج الفحص"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('تقرير فحص تكامل المنتجات المجمعة'))
        self.stdout.write('='*60)
        
        # الإحصائيات
        stats = report['statistics']
        self.stdout.write(f'\nالإحصائيات:')
        self.stdout.write(f'  - إجمالي المنتجات المجمعة: {stats.get("total_bundles", 0)}')
        self.stdout.write(f'  - المنتجات النشطة: {stats.get("active_bundles", 0)}')
        self.stdout.write(f'  - إجمالي المكونات: {stats.get("total_components", 0)}')
        
        # المشاكل الحرجة
        if report['critical_issues']:
            self.stdout.write(f'\n{self.style.ERROR("مشاكل حرجة:")} ({len(report["critical_issues"])})')
            for issue in report['critical_issues']:
                self.stdout.write(f'  ❌ {issue["message"]}')
        
        # التحذيرات
        if report['warning_issues']:
            self.stdout.write(f'\n{self.style.WARNING("تحذيرات:")} ({len(report["warning_issues"])})')
            for issue in report['warning_issues']:
                self.stdout.write(f'  ⚠️  {issue["message"]}')
        
        # المعلومات
        if report['info_issues']:
            self.stdout.write(f'\nمعلومات: ({len(report["info_issues"])})')
            for issue in report['info_issues']:
                self.stdout.write(f'  ℹ️  {issue["message"]}')
        
        # الإصلاحات
        if report['fixed_issues']:
            self.stdout.write(f'\n{self.style.SUCCESS("تم إصلاحها:")} ({len(report["fixed_issues"])})')
            for fix in report['fixed_issues']:
                self.stdout.write(f'  ✅ {fix["message"]}')
        
        self.stdout.write('\n' + '='*60)
    
    def save_report(self, report: Dict[str, Any]) -> None:
        """حفظ التقرير في ملف"""
        try:
            import json
            
            # تحويل datetime إلى string للتسلسل
            report_copy = report.copy()
            report_copy['timestamp'] = report_copy['timestamp'].isoformat()
            
            with open(self.report_file, 'w', encoding='utf-8') as f:
                json.dump(report_copy, f, ensure_ascii=False, indent=2)
            
            self.stdout.write(
                self.style.SUCCESS(f'تم حفظ التقرير في: {self.report_file}')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'خطأ في حفظ التقرير: {str(e)}')
            )