from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from hr.models import SalaryComponent, Employee, Contract
from hr.services.component_classification_service import ComponentClassificationService
from decimal import Decimal


class SmartContractAnalyzer:
    """محلل ذكي متقدم للعقود وبنود الراتب"""
    
    def __init__(self):
        self.classification_service = ComponentClassificationService()
    
    def analyze_employee_for_contract(self, employee, new_contract=None):
        """تحليل شامل لبنود الموظف مع العقد الجديد"""
        
        # جلب بنود الموظف الحالية
        current_components = self.get_active_components(employee)
        
        # تصنيف البنود
        classified_components = self.classify_components(current_components)
        
        # تحديد البنود القابلة للنقل
        transferable_components = self.identify_transferable_components(classified_components)
        
        # اكتشاف التضارب
        conflicts = self.detect_conflicts(current_components, new_contract) if new_contract else []
        
        # توليد التوصيات
        recommendations = self.generate_recommendations(classified_components, new_contract)
        
        # تخطيط الإجراءات التلقائية
        auto_actions = self.plan_automatic_actions(classified_components)
        
        # حساب التأثير المالي
        financial_impact = self.calculate_financial_impact(current_components, new_contract)
        
        return {
            'employee': employee,
            'total_components': len(current_components),
            'classified_components': classified_components,
            'transferable_components': transferable_components,
            'conflicts': conflicts,
            'recommendations': recommendations,
            'auto_actions': auto_actions,
            'financial_impact': financial_impact,
            'analysis_date': timezone.now()
        }
    
    def get_active_components(self, employee):
        """جلب بنود الموظف النشطة (باستثناء الراتب الأساسي)"""
        return SalaryComponent.objects.filter(
            employee=employee,
            is_active=True,
            is_basic=False  # استبعاد الراتب الأساسي
        ).order_by('component_type', 'name')
    
    def classify_components(self, components):
        """تصنيف البنود حسب المصدر والنوع"""
        classified = {
            'contract': [],      # بنود العقد
            'temporary': [],     # بنود مؤقتة
            'personal': [],      # بنود شخصية (قروض)
            'exceptional': [],   # بنود استثنائية
            'adjustment': []     # تعديلات
        }
        
        for component in components:
            source = component.source or 'contract'
            classified[source].append(component)
        
        return classified
    
    def identify_transferable_components(self, classified_components):
        """تحديد البنود القابلة للنقل للعقد الجديد"""
        transferable = []
        
        # البنود الشخصية (قروض، مقدمات) - قابلة للنقل
        for component in classified_components.get('personal', []):
            transferable.append({
                'component': component,
                'transfer_type': 'copy',  # نسخ
                'reason': 'بند شخصي يجب أن يستمر مع الموظف',
                'priority': 'high'
            })
        
        # البنود المؤقتة النشطة - قابلة للنقل
        for component in classified_components.get('temporary', []):
            if self.is_component_still_valid(component):
                transferable.append({
                    'component': component,
                    'transfer_type': 'move',  # نقل
                    'reason': 'بند مؤقت لا يزال ساري المفعول',
                    'priority': 'medium'
                })
        
        # البنود الاستثنائية الحديثة - قابلة للنقل
        for component in classified_components.get('exceptional', []):
            if self.is_recent_component(component):
                transferable.append({
                    'component': component,
                    'transfer_type': 'copy',
                    'reason': 'بند استثنائي حديث',
                    'priority': 'low'
                })
        
        # بنود التعديل النشطة - قابلة للنقل
        for component in classified_components.get('adjustment', []):
            transferable.append({
                'component': component,
                'transfer_type': 'copy',  # نسخ
                'reason': 'بند تعديل يجب الاحتفاظ به',
                'priority': 'medium'
            })
        
        return transferable
    
    def detect_conflicts(self, current_components, new_contract):
        """اكتشاف التضارب بين البنود الحالية والعقد الجديد"""
        conflicts = []
        
        if not new_contract:
            return conflicts
        
        # التحقق من تضارب الراتب الأساسي
        basic_salary_components = [
            comp for comp in current_components 
            if 'راتب' in comp.name and comp.component_type == 'earning'
        ]
        
        if basic_salary_components and new_contract.basic_salary:
            for component in basic_salary_components:
                if abs(component.amount - new_contract.basic_salary) > Decimal('0.01'):
                    conflicts.append({
                        'type': 'salary_mismatch',
                        'component': component,
                        'message': f'تضارب في الراتب الأساسي: {component.amount} مقابل {new_contract.basic_salary}',
                        'severity': 'high'
                    })
        
        # التحقق من البنود المكررة (فقط للعقود المحفوظة)
        contract_components = []
        if new_contract and new_contract.id:
            contract_components_manager = getattr(new_contract, 'salary_components', None)
            if contract_components_manager is not None:
                contract_components = contract_components_manager.all()
        # للعقود المؤقتة (بدون id)، لا توجد بنود مكررة للفحص
            
        for current_comp in current_components:
            for contract_comp in contract_components:
                if (current_comp.name == contract_comp.name and 
                    current_comp.component_type == contract_comp.component_type):
                    conflicts.append({
                        'type': 'duplicate_component',
                        'component': current_comp,
                        'message': f'بند مكرر: {current_comp.name}',
                        'severity': 'medium'
                    })
        
        return conflicts
    
    def generate_recommendations(self, classified_components, new_contract):
        """توليد التوصيات الذكية"""
        recommendations = []
        
        # توصيات للبنود المنتهية
        expired_components = []
        for source_components in classified_components.values():
            for component in source_components:
                if not self.is_component_still_valid(component):
                    expired_components.append(component)
        
        if expired_components:
            recommendations.append({
                'type': 'cleanup',
                'title': 'تنظيف البنود المنتهية',
                'message': f'يوجد {len(expired_components)} بند منتهي الصلاحية يمكن إلغاء تفعيله',
                'action': 'deactivate_expired',
                'components': expired_components,
                'priority': 'medium'
            })
        
        # توصيات للبنود الشخصية
        personal_components = classified_components.get('personal', [])
        if personal_components:
            recommendations.append({
                'type': 'transfer',
                'title': 'نقل البنود الشخصية',
                'message': f'يُنصح بنقل {len(personal_components)} بند شخصي للعقد الجديد',
                'action': 'transfer_personal',
                'components': personal_components,
                'priority': 'high'
            })
        
        # توصيات لبنود التعديل
        adjustment_components = classified_components.get('adjustment', [])
        if adjustment_components:
            recommendations.append({
                'type': 'transfer',
                'title': 'الاحتفاظ ببنود التعديل',
                'message': f'يُنصح بالاحتفاظ بـ {len(adjustment_components)} بند تعديل في العقد الجديد',
                'action': 'transfer_adjustments',
                'components': adjustment_components,
                'priority': 'high'
            })
        
        # توصيات للتحسين
        unclassified_components = [
            comp for comp in classified_components.get('contract', [])
            if not comp.is_from_contract
        ]
        
        if unclassified_components:
            recommendations.append({
                'type': 'classification',
                'title': 'تصنيف البنود',
                'message': f'يوجد {len(unclassified_components)} بند يحتاج تصنيف أفضل',
                'action': 'reclassify',
                'components': unclassified_components,
                'priority': 'low'
            })
        
        return recommendations
    
    def plan_automatic_actions(self, classified_components):
        """تخطيط الإجراءات التلقائية"""
        actions = {
            'transfer': [],      # البنود التي ستُنقل تلقائياً
            'archive': [],       # البنود التي ستُؤرشف
            'update': [],        # البنود التي ستُحدث
            'create': []         # البنود الجديدة التي ستُنشأ
        }
        
        # نقل البنود الشخصية تلقائياً
        for component in classified_components.get('personal', []):
            actions['transfer'].append({
                'component': component,
                'reason': 'بند شخصي',
                'auto': True
            })
        
        # نقل البنود المؤقتة الصالحة
        for component in classified_components.get('temporary', []):
            if self.is_component_still_valid(component):
                actions['transfer'].append({
                    'component': component,
                    'reason': 'بند مؤقت صالح',
                    'auto': True
                })
        
        # أرشفة البنود المنتهية
        for source_components in classified_components.values():
            for component in source_components:
                if not self.is_component_still_valid(component):
                    actions['archive'].append({
                        'component': component,
                        'reason': 'منتهي الصلاحية',
                        'auto': True
                    })
        
        return actions
    
    def calculate_financial_impact(self, current_components, new_contract):
        """حساب التأثير المالي للتغييرات"""
        
        # حساب إجمالي الاستحقاقات والخصومات الحالية
        current_earnings = sum(
            comp.amount for comp in current_components 
            if comp.component_type == 'earning' and comp.is_active
        )
        current_deductions = sum(
            comp.amount for comp in current_components 
            if comp.component_type == 'deduction' and comp.is_active
        )
        current_net = current_earnings - current_deductions
        
        # حساب التأثير المتوقع مع العقد الجديد
        new_earnings = new_contract.basic_salary if new_contract else current_earnings
        new_deductions = current_deductions  # الخصومات ستبقى كما هي
        new_net = new_earnings - new_deductions
        
        # حساب التغيير
        earnings_change = new_earnings - current_earnings
        net_change = new_net - current_net
        change_percentage = (net_change / current_net * Decimal('100')) if current_net > 0 else Decimal('0')
        
        return {
            'current': {
                'earnings': current_earnings,
                'deductions': current_deductions,
                'net': current_net
            },
            'projected': {
                'earnings': new_earnings,
                'deductions': new_deductions,
                'net': new_net
            },
            'changes': {
                'earnings': earnings_change,
                'deductions': Decimal('0'),  # لا تغيير في الخصومات
                'net': net_change,
                'percentage': round(change_percentage, 2)
            }
        }
    
    def is_component_still_valid(self, component):
        """التحقق من صلاحية البند"""
        if not component.effective_to:
            return True  # بند دائم
        
        return component.effective_to >= timezone.now().date()
    
    def is_recent_component(self, component, days=30):
        """التحقق من كون البند حديث"""
        cutoff_date = timezone.now().date() - timedelta(days=days)
        return component.created_at.date() >= cutoff_date
    
    def smart_activate_contract(self, contract):
        """تفعيل ذكي للعقد مع معالجة تلقائية للبنود"""
        
        # تحليل بنود الموظف
        analysis = self.analyze_employee_for_contract(contract.employee, contract)
        
        # تطبيق الإجراءات التلقائية
        results = self.apply_automatic_actions(analysis['auto_actions'], contract)
        
        # تفعيل العقد
        contract.status = 'active'
        contract.activation_date = timezone.now().date()
        contract.save()
        
        return {
            'success': True,
            'contract': contract,
            'analysis': analysis,
            'results': results,
            'summary': self.generate_activation_summary(results)
        }
    
    def apply_automatic_actions(self, auto_actions, new_contract):
        """تطبيق الإجراءات التلقائية"""
        results = {
            'transferred': [],
            'archived': [],
            'updated': [],
            'created': [],
            'errors': []
        }
        
        try:
            # نقل البنود
            for action in auto_actions.get('transfer', []):
                component = action['component']
                
                # إنشاء نسخة جديدة مرتبطة بالعقد الجديد
                new_component = SalaryComponent.objects.create(
                    employee=new_contract.employee,
                    contract=new_contract,
                    name=component.name,
                    amount=component.amount,
                    component_type=component.component_type,
                    source=component.source,
                    is_recurring=component.is_recurring,
                    auto_renew=component.auto_renew,
                    renewal_period_months=component.renewal_period_months,
                    effective_from=new_contract.start_date,
                    effective_to=component.effective_to,
                    is_from_contract=False,
                    notes=f'منقول من العقد السابق - {component.notes or ""}'
                )
                
                results['transferred'].append({
                    'original': component,
                    'new': new_component,
                    'reason': action['reason']
                })
                
                # إلغاء تفعيل البند القديم
                component.is_active = False
                component.save()
            
            # أرشفة البنود المنتهية
            for action in auto_actions.get('archive', []):
                component = action['component']
                component.is_active = False
                component.save()
                
                results['archived'].append({
                    'component': component,
                    'reason': action['reason']
                })
        
        except Exception as e:
            results['errors'].append(str(e))
        
        return results
    
    def generate_activation_summary(self, results):
        """توليد ملخص عملية التفعيل"""
        transferred_count = len(results['transferred'])
        archived_count = len(results['archived'])
        errors_count = len(results['errors'])
        
        summary = f"تم تفعيل العقد بنجاح. "
        
        if transferred_count > 0:
            summary += f"تم نقل {transferred_count} بند. "
        
        if archived_count > 0:
            summary += f"تم أرشفة {archived_count} بند منتهي. "
        
        if errors_count > 0:
            summary += f"حدث {errors_count} خطأ أثناء المعالجة."
        
        return summary
