from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from hr.models import Contract, SalaryComponent, Employee, ContractSalaryComponent
from hr.services.smart_contract_analyzer import SmartContractAnalyzer
from hr.services.auto_transfer_engine import AutoTransferEngine
from hr.services.component_intelligence import ComponentIntelligence
import logging

logger = logging.getLogger(__name__)


class UnifiedContractService:
    """خدمة موحدة لإدارة العقود وبنود الراتب"""
    
    def __init__(self):
        self.analyzer = SmartContractAnalyzer()
        self.transfer_engine = AutoTransferEngine()
        self.intelligence = ComponentIntelligence()
    
    def create_contract_with_analysis(self, employee, contract_data, user=None):
        """إنشاء عقد جديد مع التحليل الذكي"""
        
        logger.info(f"إنشاء عقد جديد للموظف {employee.id}")
        
        # تحليل بنود الموظف الحالية
        analysis = self.analyzer.analyze_employee_for_contract(employee)
        
        # إنشاء العقد
        contract = Contract.objects.create(
            employee=employee,
            created_by=user,
            **contract_data
        )
        
        # إرفاق التحليل بالعقد للمراجعة اللاحقة
        contract._analysis_data = analysis
        
        return {
            'contract': contract,
            'analysis': analysis,
            'recommendations': analysis['recommendations'],
            'requires_review': len(analysis['transferable_components']) > 0 or len(analysis['conflicts']) > 0
        }
    
    @transaction.atomic
    def smart_activate_contract(self, contract, user_selections=None, user=None):
        """تفعيل ذكي للعقد مع معالجة البنود"""
        
        logger.info(f"تفعيل ذكي للعقد {contract.id}")
        
        try:
            # التحقق من حالة العقد
            if contract.status != 'draft':
                raise ValidationError("يمكن تفعيل العقود المسودة فقط")
            
            # إلغاء تفعيل العقد السابق
            old_contract = self._deactivate_previous_contract(contract.employee, contract)
            
            # تحليل البنود والتحضير للنقل
            analysis = self.analyzer.analyze_employee_for_contract(contract.employee, contract)
            
            # تنفيذ النقل الذكي للبنود
            transfer_results = self.transfer_engine.execute_smart_transfer(
                old_contract, contract, user_selections
            )
            
            # تفعيل العقد
            contract.status = 'active'
            contract.activation_date = timezone.now().date()
            contract.activated_by = user
            contract.save()
            
            # تعطيل البنود القديمة التي لم تعد موجودة في العقد الجديد
            from .contract_activation_service import ContractActivationService
            deactivated_count = self._deactivate_obsolete_components(contract)
            
            # إضافة تفاصيل التعطيل للنتائج
            transfer_results['deactivated_components'] = deactivated_count
            
            # تسجيل العملية
            self._log_activation(contract, analysis, transfer_results, user)
            
            return {
                'success': True,
                'contract': contract,
                'analysis': analysis,
                'transfer_results': transfer_results,
                'summary': self._create_activation_summary(analysis, transfer_results)
            }
            
        except Exception as e:
            logger.error(f"خطأ في تفعيل العقد {contract.id}: {str(e)}")
            raise ValidationError(f"فشل في تفعيل العقد: {str(e)}")
    
    def preview_contract_activation(self, contract, user_selections=None):
        """معاينة تفعيل العقد بدون تنفيذ"""
        
        # تحليل البنود
        analysis = self.analyzer.analyze_employee_for_contract(contract.employee, contract)
        
        # معاينة النقل
        transfer_preview = self.transfer_engine.preview_transfer(
            contract.employee, contract, user_selections
        )
        
        return {
            'contract': contract,
            'analysis': analysis,
            'transfer_preview': transfer_preview,
            'estimated_impact': self._estimate_activation_impact(analysis, transfer_preview)
        }
    
    def get_employee_component_analysis(self, employee):
        """تحليل شامل لبنود الموظف"""
        
        # التحليل الأساسي
        basic_analysis = self.analyzer.analyze_employee_for_contract(employee)
        
        # تحليل الأنماط
        pattern_analysis = self.intelligence.analyze_component_patterns(employee)
        
        # تحليل التجديد
        renewal_analysis = self._analyze_renewal_needs(employee)
        
        return {
            'basic_analysis': basic_analysis,
            'pattern_analysis': pattern_analysis,
            'renewal_analysis': renewal_analysis,
            'overall_health': self._assess_component_health(basic_analysis, pattern_analysis)
        }
    
    def optimize_employee_components(self, employee, optimization_options=None):
        """تحسين بنود الموظف"""
        
        # تحليل البنود الحالية
        analysis = self.get_employee_component_analysis(employee)
        
        # توليد خطة التحسين
        optimization_plan = self._create_optimization_plan(analysis, optimization_options)
        
        # تنفيذ التحسينات (إذا طُلب)
        if optimization_options and optimization_options.get('execute', False):
            results = self._execute_optimization_plan(employee, optimization_plan)
            return {
                'analysis': analysis,
                'plan': optimization_plan,
                'results': results
            }
        
        return {
            'analysis': analysis,
            'plan': optimization_plan
        }
    
    def _deactivate_previous_contract(self, employee, new_contract):
        """إلغاء تفعيل العقد السابق"""
        
        previous_contracts = Contract.objects.filter(
            employee=employee,
            status='active'
        ).exclude(id=new_contract.id)
        
        old_contract = None
        for contract in previous_contracts:
            contract.status = 'inactive'
            contract.end_date = new_contract.start_date
            contract.save()
            old_contract = contract
            
            logger.info(f"تم إلغاء تفعيل العقد السابق {contract.id}")
        
        return old_contract
    
    def _analyze_renewal_needs(self, employee):
        """تحليل احتياجات التجديد للموظف"""
        
        components = SalaryComponent.objects.filter(
            employee=employee,
            is_active=True
        )
        
        renewal_analysis = {
            'needs_renewal': [],
            'auto_renewable': [],
            'expired': [],
            'recommendations': []
        }
        
        for component in components:
            renewal_prediction = self.intelligence.predict_component_renewal(component)
            
            if renewal_prediction['needs_renewal']:
                if component.auto_renew:
                    renewal_analysis['auto_renewable'].append({
                        'component': component,
                        'prediction': renewal_prediction
                    })
                else:
                    renewal_analysis['needs_renewal'].append({
                        'component': component,
                        'prediction': renewal_prediction
                    })
            
            # فحص البنود المنتهية
            if (component.effective_to and 
                component.effective_to < timezone.now().date()):
                renewal_analysis['expired'].append(component)
        
        # توليد توصيات التجديد
        renewal_analysis['recommendations'] = self._generate_renewal_recommendations(
            renewal_analysis
        )
        
        return renewal_analysis
    
    def _assess_component_health(self, basic_analysis, pattern_analysis):
        """تقييم صحة بنود الموظف"""
        
        health_score = 100
        issues = []
        
        # فحص التضارب
        if basic_analysis['conflicts']:
            health_score -= len(basic_analysis['conflicts']) * 10
            issues.append(f"{len(basic_analysis['conflicts'])} تضارب في البنود")
        
        # فحص الشذوذ
        anomalies = pattern_analysis.get('anomalies', [])
        if anomalies:
            health_score -= len(anomalies) * 5
            issues.append(f"{len(anomalies)} شذوذ في البنود")
        
        # فحص نسبة الخصومات
        deduction_ratio = pattern_analysis['financial_summary'].get('deduction_ratio', 0)
        if deduction_ratio > 30:
            health_score -= 15
            issues.append(f"نسبة خصومات عالية ({deduction_ratio:.1f}%)")
        
        # فحص البنود المنتهية
        expired_count = len([
            comp for comp in basic_analysis['classified_components'].get('temporary', [])
            if not self.analyzer.is_component_still_valid(comp)
        ])
        
        if expired_count > 0:
            health_score -= expired_count * 5
            issues.append(f"{expired_count} بند منتهي الصلاحية")
        
        # تحديد مستوى الصحة
        if health_score >= 90:
            health_level = 'excellent'
            health_text = 'ممتاز'
        elif health_score >= 75:
            health_level = 'good'
            health_text = 'جيد'
        elif health_score >= 60:
            health_level = 'fair'
            health_text = 'مقبول'
        else:
            health_level = 'poor'
            health_text = 'يحتاج تحسين'
        
        return {
            'score': max(health_score, 0),
            'level': health_level,
            'text': health_text,
            'issues': issues,
            'recommendations': self._generate_health_recommendations(health_score, issues)
        }
    
    def _create_optimization_plan(self, analysis, options=None):
        """إنشاء خطة تحسين البنود"""
        
        plan = {
            'cleanup': [],      # البنود للتنظيف
            'reclassify': [],   # البنود لإعادة التصنيف
            'renew': [],        # البنود للتجديد
            'consolidate': [],  # البنود للدمج
            'priority': 'medium'
        }
        
        # تنظيف البنود المنتهية
        for source_components in analysis['basic_analysis']['classified_components'].values():
            for component in source_components:
                if not self.analyzer.is_component_still_valid(component):
                    plan['cleanup'].append({
                        'component': component,
                        'action': 'deactivate',
                        'reason': 'منتهي الصلاحية'
                    })
        
        # إعادة تصنيف البنود غير المصنفة
        unclassified = [
            comp for comp in analysis['basic_analysis']['classified_components'].get('contract', [])
            if not comp.is_from_contract
        ]
        
        for component in unclassified:
            suggested_source = self.intelligence.suggest_component_source(component)
            if suggested_source != component.source:
                plan['reclassify'].append({
                    'component': component,
                    'current_source': component.source,
                    'suggested_source': suggested_source,
                    'reason': 'تحسين التصنيف'
                })
        
        # تجديد البنود المطلوبة
        for item in analysis['renewal_analysis']['needs_renewal']:
            plan['renew'].append({
                'component': item['component'],
                'prediction': item['prediction'],
                'suggested_duration': item['prediction']['suggested_duration']
            })
        
        return plan
    
    def _execute_optimization_plan(self, employee, plan):
        """تنفيذ خطة التحسين"""
        
        results = {
            'cleaned': [],
            'reclassified': [],
            'renewed': [],
            'errors': []
        }
        
        try:
            with transaction.atomic():
                # تنظيف البنود
                for item in plan['cleanup']:
                    try:
                        component = item['component']
                        component.is_active = False
                        component.notes = f"{component.notes or ''} - {item['reason']}"
                        component.save()
                        results['cleaned'].append(component)
                    except Exception as e:
                        results['errors'].append(f"خطأ في تنظيف {component.name}: {str(e)}")
                
                # إعادة التصنيف
                for item in plan['reclassify']:
                    try:
                        component = item['component']
                        component.source = item['suggested_source']
                        component.save()
                        results['reclassified'].append({
                            'component': component,
                            'old_source': item['current_source'],
                            'new_source': item['suggested_source']
                        })
                    except Exception as e:
                        results['errors'].append(f"خطأ في إعادة تصنيف {component.name}: {str(e)}")
        
        except Exception as e:
            logger.error(f"خطأ في تنفيذ خطة التحسين: {str(e)}")
            results['errors'].append(str(e))
        
        return results
    
    def _estimate_activation_impact(self, analysis, transfer_preview):
        """تقدير تأثير تفعيل العقد"""
        
        impact = {
            'financial_change': analysis['financial_impact']['changes'],
            'components_affected': transfer_preview['total_components'],
            'automatic_transfers': transfer_preview['auto_transfer_count'],
            'manual_reviews_needed': transfer_preview['manual_review_count'],
            'potential_issues': len(analysis['conflicts']),
            'risk_level': 'low'
        }
        
        # تحديد مستوى المخاطر
        if impact['potential_issues'] > 2 or impact['manual_reviews_needed'] > 5:
            impact['risk_level'] = 'high'
        elif impact['potential_issues'] > 0 or impact['manual_reviews_needed'] > 2:
            impact['risk_level'] = 'medium'
        
        return impact
    
    def _create_activation_summary(self, analysis, transfer_results):
        """إنشاء ملخص التفعيل"""
        
        summary = {
            'success': True,
            'components_analyzed': analysis['total_components'],
            'components_transferred': len(transfer_results['transferred']),
            'components_archived': len(transfer_results['archived']),
            'errors': len(transfer_results['errors']),
            'financial_impact': analysis['financial_impact']['changes'],
            'message': ''
        }
        
        # إنشاء رسالة الملخص
        messages = []
        messages.append("تم تفعيل العقد بنجاح")
        
        if summary['components_transferred'] > 0:
            messages.append(f"تم نقل {summary['components_transferred']} بند")
        
        if summary['components_archived'] > 0:
            messages.append(f"تم أرشفة {summary['components_archived']} بند")
        
        if summary['errors'] > 0:
            messages.append(f"حدث {summary['errors']} خطأ")
        
        summary['message'] = ". ".join(messages)
        
        return summary
    
    def _generate_renewal_recommendations(self, renewal_analysis):
        """توليد توصيات التجديد"""
        
        recommendations = []
        
        if renewal_analysis['needs_renewal']:
            recommendations.append({
                'type': 'manual_renewal',
                'message': f"يوجد {len(renewal_analysis['needs_renewal'])} بند يحتاج تجديد يدوي",
                'priority': 'high'
            })
        
        if renewal_analysis['expired']:
            recommendations.append({
                'type': 'cleanup_expired',
                'message': f"يوجد {len(renewal_analysis['expired'])} بند منتهي يحتاج تنظيف",
                'priority': 'medium'
            })
        
        return recommendations
    
    def _generate_health_recommendations(self, health_score, issues):
        """توليد توصيات تحسين الصحة"""
        
        recommendations = []
        
        if health_score < 60:
            recommendations.append({
                'type': 'urgent_review',
                'message': 'يُنصح بمراجعة شاملة لبنود الراتب',
                'priority': 'critical'
            })
        
        if 'تضارب في البنود' in str(issues):
            recommendations.append({
                'type': 'resolve_conflicts',
                'message': 'حل التضارب في البنود أولوية عالية',
                'priority': 'high'
            })
        
        if 'نسبة خصومات عالية' in str(issues):
            recommendations.append({
                'type': 'review_deductions',
                'message': 'مراجعة الخصومات وتبريرها',
                'priority': 'medium'
            })
        
        return recommendations
    
    def _log_activation(self, contract, analysis, transfer_results, user):
        """تسجيل عملية التفعيل"""
        
        logger.info(
            f"تم تفعيل العقد {contract.id} للموظف {contract.employee.name} "
            f"بواسطة {user.username if user else 'النظام'}"
        )
        
        logger.info(f"تحليل البنود: {analysis['total_components']} بند تم تحليله")
        logger.info(f"نتائج النقل: {transfer_results['summary']['message']}")
    
    def _deactivate_obsolete_components(self, contract):
        """تعطيل البنود القديمة التي لم تعد موجودة في العقد الجديد"""
        from .contract_activation_service import ContractActivationService
        
        employee = contract.employee
        
        # جلب بنود العقد الجديد
        contract_components = ContractSalaryComponent.objects.filter(contract=contract)
        
        # جلب بنود الموظف النشطة
        employee_components = SalaryComponent.objects.filter(
            employee=employee,
            is_active=True
        )
        
        deactivated_count = 0
        for emp_comp in employee_components:
            # استبعاد البنود التي يجب الحفاظ عليها
            should_preserve = ContractActivationService._should_preserve_component(emp_comp)
            if should_preserve:
                continue
                
            # تعطيل البند إذا لم يعد موجود في العقد الجديد
            if not ContractActivationService._has_match_in_contract(emp_comp, contract_components):
                emp_comp.is_active = False
                emp_comp.effective_to = timezone.now().date()
                emp_comp.save()
                deactivated_count += 1
                
        logger.info(f"تم تعطيل {deactivated_count} بند قديم للموظف {employee.name}")
        return deactivated_count
