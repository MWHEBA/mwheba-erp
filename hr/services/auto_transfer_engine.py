from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from hr.models import SalaryComponent, Contract
from hr.services.component_intelligence import ComponentIntelligence
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class AutoTransferEngine:
    """محرك النقل التلقائي للبنود بين العقود"""
    
    def __init__(self):
        self.intelligence = ComponentIntelligence()
        self.transfer_rules = self._load_transfer_rules()
    
    def _load_transfer_rules(self):
        """تحميل قواعد النقل التلقائي"""
        return {
            'personal': {
                'auto_transfer': True,
                'transfer_type': 'copy',  # نسخ البند
                'preserve_dates': True,   # الحفاظ على التواريخ
                'priority': 1            # أولوية عالية
            },
            'temporary': {
                'auto_transfer': True,
                'transfer_type': 'move',  # نقل البند
                'check_validity': True,   # فحص الصلاحية
                'priority': 2
            },
            'exceptional': {
                'auto_transfer': False,   # يحتاج موافقة يدوية
                'transfer_type': 'copy',
                'age_limit_days': 90,     # فقط البنود الحديثة
                'priority': 3
            },
            'adjustment': {
                'auto_transfer': False,   # لا ينقل تلقائياً
                'transfer_type': 'archive', # أرشفة
                'priority': 4
            },
            'contract': {
                'auto_transfer': False,   # بنود العقد لا تنقل
                'transfer_type': 'replace', # استبدال بالعقد الجديد
                'priority': 5
            }
        }
    
    @transaction.atomic
    def execute_smart_transfer(self, old_contract, new_contract, user_selections=None):
        """تنفيذ النقل الذكي للبنود"""
        
        old_contract_id = old_contract.id if old_contract else "لا يوجد"
        logger.info(f"بدء النقل الذكي من العقد {old_contract_id} إلى {new_contract.id}")
        
        # جلب بنود الموظف النشطة
        active_components = SalaryComponent.objects.filter(
            employee=new_contract.employee,
            is_active=True
        )
        
        # تحليل البنود وتصنيفها
        transfer_plan = self._create_transfer_plan(active_components, new_contract, user_selections)
        
        # تنفيذ خطة النقل
        results = self._execute_transfer_plan(transfer_plan, new_contract)
        
        # تسجيل النتائج
        self._log_transfer_results(results, old_contract, new_contract)
        
        return results
    
    def _create_transfer_plan(self, components, new_contract, user_selections=None):
        """إنشاء خطة النقل للبنود"""
        
        plan = {
            'auto_transfer': [],     # البنود التي ستنقل تلقائياً
            'manual_review': [],     # البنود التي تحتاج مراجعة يدوية
            'archive': [],           # البنود التي ستؤرشف
            'conflicts': [],         # البنود المتضاربة
            'skip': []              # البنود التي ستتجاهل
        }
        
        for component in components:
            # تحديد قاعدة النقل للبند
            transfer_rule = self.transfer_rules.get(component.source, self.transfer_rules['contract'])
            
            # فحص اختيارات المستخدم أولاً
            if user_selections and component.id in user_selections:
                user_choice = user_selections[component.id]
                plan[user_choice['action']].append({
                    'component': component,
                    'rule': transfer_rule,
                    'reason': 'اختيار المستخدم',
                    'user_choice': user_choice
                })
                continue
            
            # تطبيق القواعد التلقائية
            if transfer_rule['auto_transfer']:
                # فحص الشروط الإضافية
                if self._check_transfer_conditions(component, transfer_rule, new_contract):
                    plan['auto_transfer'].append({
                        'component': component,
                        'rule': transfer_rule,
                        'reason': 'قاعدة تلقائية'
                    })
                else:
                    plan['manual_review'].append({
                        'component': component,
                        'rule': transfer_rule,
                        'reason': 'لا يستوفي الشروط التلقائية'
                    })
            else:
                # البنود التي تحتاج مراجعة يدوية
                if transfer_rule['transfer_type'] == 'archive':
                    plan['archive'].append({
                        'component': component,
                        'rule': transfer_rule,
                        'reason': 'بند للأرشفة'
                    })
                else:
                    plan['manual_review'].append({
                        'component': component,
                        'rule': transfer_rule,
                        'reason': 'يحتاج موافقة يدوية'
                    })
        
        # ترتيب البنود حسب الأولوية
        for category in plan.values():
            if isinstance(category, list):
                category.sort(key=lambda x: x['rule']['priority'])
        
        return plan
    
    def _check_transfer_conditions(self, component, rule, new_contract):
        """فحص شروط النقل للبند"""
        
        # فحص صلاحية البند
        if rule.get('check_validity'):
            if not self._is_component_valid(component):
                return False
        
        # فحص عمر البند
        if 'age_limit_days' in rule:
            age_days = (timezone.now().date() - component.created_at.date()).days
            if age_days > rule['age_limit_days']:
                return False
        
        # فحص التضارب مع العقد الجديد
        if self._has_conflict_with_contract(component, new_contract):
            return False
        
        # فحص الحد الأقصى للمبلغ
        if hasattr(new_contract, 'max_component_amount'):
            if component.amount > new_contract.max_component_amount:
                return False
        
        return True
    
    def _is_component_valid(self, component):
        """فحص صلاحية البند"""
        if not component.is_active:
            return False
        
        if component.effective_to and component.effective_to < timezone.now().date():
            return False
        
        return True
    
    def _has_conflict_with_contract(self, component, new_contract):
        """فحص التضارب مع العقد الجديد"""
        
        # فحص تضارب الراتب الأساسي
        if ('راتب' in component.name.lower() and 
            component.component_type == 'earning' and
            new_contract.basic_salary):
            
            # إذا كان هناك فرق كبير في المبلغ
            if abs(component.amount - new_contract.basic_salary) > Decimal('100'):
                return True
        
        # فحص البنود المكررة في العقد الجديد
        # (يمكن إضافة منطق إضافي هنا حسب بنية العقد)
        
        return False
    
    @transaction.atomic
    def _execute_transfer_plan(self, plan, new_contract):
        """تنفيذ خطة النقل"""
        
        results = {
            'transferred': [],
            'archived': [],
            'conflicts_resolved': [],
            'errors': [],
            'summary': {}
        }
        
        try:
            # تنفيذ النقل التلقائي
            for item in plan['auto_transfer']:
                result = self._transfer_component(item, new_contract)
                if result['success']:
                    results['transferred'].append(result)
                else:
                    results['errors'].append(result)
            
            # أرشفة البنود
            for item in plan['archive']:
                result = self._archive_component(item)
                if result['success']:
                    results['archived'].append(result)
                else:
                    results['errors'].append(result)
            
            # إنشاء ملخص النتائج
            results['summary'] = self._create_results_summary(results, plan)
            
        except Exception as e:
            logger.error(f"خطأ في تنفيذ خطة النقل: {str(e)}")
            results['errors'].append({
                'type': 'execution_error',
                'message': str(e),
                'success': False
            })
        
        return results
    
    def _transfer_component(self, item, new_contract):
        """نقل بند واحد"""
        
        component = item['component']
        rule = item['rule']
        
        try:
            if rule['transfer_type'] == 'copy':
                # نسخ البند
                new_component = self._copy_component(component, new_contract, rule)
                
                return {
                    'success': True,
                    'type': 'copy',
                    'original_component': component,
                    'new_component': new_component,
                    'reason': item['reason']
                }
                
            elif rule['transfer_type'] == 'move':
                # نقل البند
                moved_component = self._move_component(component, new_contract, rule)
                
                return {
                    'success': True,
                    'type': 'move',
                    'original_component': component,
                    'moved_component': moved_component,
                    'reason': item['reason']
                }
            
        except Exception as e:
            logger.error(f"خطأ في نقل البند {component.id}: {str(e)}")
            return {
                'success': False,
                'component': component,
                'error': str(e),
                'reason': item['reason']
            }
    
    def _copy_component(self, original, new_contract, rule):
        """نسخ بند إلى العقد الجديد"""
        
        # تحديد التواريخ
        if rule.get('preserve_dates'):
            effective_from = original.effective_from
            effective_to = original.effective_to
        else:
            effective_from = new_contract.start_date
            effective_to = original.effective_to
        
        # إنشاء البند الجديد
        new_component = SalaryComponent.objects.create(
            employee=new_contract.employee,
            contract=new_contract,
            name=original.name,
            amount=original.amount,
            component_type=original.component_type,
            source=original.source,
            is_recurring=original.is_recurring,
            auto_renew=original.auto_renew,
            renewal_period_months=original.renewal_period_months,
            effective_from=effective_from,
            effective_to=effective_to,
            is_from_contract=False,
            notes=f"منسوخ من العقد السابق - {original.notes or ''}"
        )
        
        # إلغاء تفعيل البند الأصلي
        original.is_active = False
        original.notes = f"{original.notes or ''} - تم نسخه للعقد الجديد"
        original.save()
        
        return new_component
    
    def _move_component(self, component, new_contract, rule):
        """نقل بند إلى العقد الجديد"""
        
        # تحديث البند الحالي
        component.contract = new_contract
        
        # تحديث التواريخ إذا لزم الأمر
        if not rule.get('preserve_dates'):
            component.effective_from = new_contract.start_date
        
        # إضافة ملاحظة
        component.notes = f"{component.notes or ''} - منقول للعقد الجديد"
        component.save()
        
        return component
    
    def _archive_component(self, item):
        """أرشفة بند"""
        
        component = item['component']
        
        try:
            component.is_active = False
            component.notes = f"{component.notes or ''} - مؤرشف تلقائياً: {item['reason']}"
            component.save()
            
            return {
                'success': True,
                'component': component,
                'reason': item['reason']
            }
            
        except Exception as e:
            logger.error(f"خطأ في أرشفة البند {component.id}: {str(e)}")
            return {
                'success': False,
                'component': component,
                'error': str(e)
            }
    
    def _create_results_summary(self, results, plan):
        """إنشاء ملخص النتائج"""
        
        summary = {
            'total_processed': len(plan['auto_transfer']) + len(plan['archive']),
            'successful_transfers': len(results['transferred']),
            'successful_archives': len(results['archived']),
            'errors': len(results['errors']),
            'pending_manual_review': len(plan['manual_review']),
            'conflicts': len(plan['conflicts'])
        }
        
        # حساب النسب المئوية
        total = summary['total_processed']
        if total > 0:
            summary['success_rate'] = (
                (summary['successful_transfers'] + summary['successful_archives']) / total * Decimal('100')
            )
        else:
            summary['success_rate'] = Decimal('100')
        
        # إنشاء رسالة الملخص
        messages = []
        
        if summary['successful_transfers'] > 0:
            messages.append(f"تم نقل {summary['successful_transfers']} بند بنجاح")
        
        if summary['successful_archives'] > 0:
            messages.append(f"تم أرشفة {summary['successful_archives']} بند")
        
        if summary['errors'] > 0:
            messages.append(f"حدث {summary['errors']} خطأ")
        
        if summary['pending_manual_review'] > 0:
            messages.append(f"{summary['pending_manual_review']} بند يحتاج مراجعة يدوية")
        
        summary['message'] = ". ".join(messages) if messages else "لا توجد بنود للمعالجة"
        
        return summary
    
    def _log_transfer_results(self, results, old_contract, new_contract):
        """تسجيل نتائج النقل في السجلات"""
        
        old_contract_id = old_contract.id if old_contract else "لا يوجد"
        logger.info(
            f"نتائج النقل من العقد {old_contract_id} إلى {new_contract.id}: "
            f"{results['summary']['message']}"
        )
        
        # تسجيل تفاصيل الأخطاء
        for error in results['errors']:
            logger.error(f"خطأ في النقل: {error}")
    
    def preview_transfer(self, employee, new_contract, user_selections=None):
        """معاينة النقل بدون تنفيذ"""
        
        # جلب بنود الموظف النشطة
        active_components = SalaryComponent.objects.filter(
            employee=employee,
            is_active=True
        )
        
        # إنشاء خطة النقل
        transfer_plan = self._create_transfer_plan(active_components, new_contract, user_selections)
        
        # إنشاء معاينة النتائج
        preview = {
            'total_components': len(active_components),
            'auto_transfer_count': len(transfer_plan['auto_transfer']),
            'manual_review_count': len(transfer_plan['manual_review']),
            'archive_count': len(transfer_plan['archive']),
            'conflicts_count': len(transfer_plan['conflicts']),
            'plan': transfer_plan,
            'recommendations': self._generate_transfer_recommendations(transfer_plan)
        }
        
        return preview
    
    def _generate_transfer_recommendations(self, plan):
        """توليد توصيات للنقل"""
        
        recommendations = []
        
        # توصيات للبنود التي تحتاج مراجعة
        if plan['manual_review']:
            recommendations.append({
                'type': 'manual_review_needed',
                'message': f"يوجد {len(plan['manual_review'])} بند يحتاج مراجعة يدوية",
                'priority': 'high',
                'components': [item['component'] for item in plan['manual_review']]
            })
        
        # توصيات للتضارب
        if plan['conflicts']:
            recommendations.append({
                'type': 'conflicts_detected',
                'message': f"تم اكتشاف {len(plan['conflicts'])} تضارب يحتاج حل",
                'priority': 'critical',
                'components': [item['component'] for item in plan['conflicts']]
            })
        
        # توصيات للتحسين
        personal_components = [
            item for item in plan['auto_transfer'] 
            if item['component'].source == 'personal'
        ]
        
        if len(personal_components) > 3:
            recommendations.append({
                'type': 'review_personal_components',
                'message': f"يوجد {len(personal_components)} بند شخصي، يُنصح بمراجعة الحاجة إليها",
                'priority': 'medium',
                'components': [item['component'] for item in personal_components]
            })
        
        return recommendations
