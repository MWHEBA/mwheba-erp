"""
Phase -1.4: Admin Bypass Risk Assessment Command
يطلع:
- الموديلات الحساسة المعروضة في admin
- هل admin يسمح edit/delete؟
- أين لا يوجد audit trail؟
مخرجات: "Admin attack surface map"
"""

import os
import json
import ast
import inspect
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.contrib import admin
from django.apps import apps
from django.contrib.admin.sites import site
from django.db import models


class AdminBypassRiskAssessor:
    def __init__(self):
        self.sensitive_models = [
            # Financial Models (أخطر النماذج)
            'JournalEntry', 'JournalEntryLine', 'AccountingPeriod',
            
            # Payment Models
            'CustomerPayment', 'PurchasePayment', 'SalaryPayment',
            
            # Stock Models
            'ProductStock', 'StockMovement', 'InventoryMovement',
            
            # Core Business Models
            'Customer', 'Sale', 'Purchase',
            
            # User & Permission Models
            'User', 'Group', 'Permission'
        ]
        
        self.risk_assessment = {
            'registered_models': {},
            'unregistered_sensitive_models': [],
            'high_risk_admins': [],
            'medium_risk_admins': [],
            'low_risk_admins': [],
            'audit_trail_gaps': [],
            'permission_bypasses': []
        }
        
        self.admin_capabilities = {}
    
    def scan_admin_registrations(self):
        """مسح جميع النماذج المسجلة في admin"""
        print("🔍 Scanning admin registrations...")
        
        registered_models = {}
        
        # الحصول على جميع النماذج المسجلة
        for model, admin_class in site._registry.items():
            model_name = model.__name__
            app_label = model._meta.app_label
            
            # تحليل إعدادات admin
            admin_info = self._analyze_admin_class(model, admin_class)
            
            registered_models[f"{app_label}.{model_name}"] = {
                'model_name': model_name,
                'app_label': app_label,
                'admin_class': admin_class.__class__.__name__,
                'is_sensitive': model_name in self.sensitive_models,
                'capabilities': admin_info,
                'risk_score': self._calculate_admin_risk_score(model_name, admin_info)
            }
        
        self.risk_assessment['registered_models'] = registered_models
        
        # البحث عن النماذج الحساسة غير المسجلة
        self._find_unregistered_sensitive_models()
    
    def _analyze_admin_class(self, model, admin_class):
        """تحليل قدرات admin class"""
        capabilities = {
            'can_add': True,
            'can_change': True,
            'can_delete': True,
            'can_view': True,
            'has_custom_permissions': False,
            'has_readonly_fields': False,
            'has_custom_queryset': False,
            'has_custom_save': False,
            'has_custom_delete': False,
            'has_audit_logging': False,
            'list_display_fields': [],
            'readonly_fields': [],
            'exclude_fields': [],
            'custom_actions': [],
            'fieldsets': None
        }
        
        # فحص الصلاحيات الأساسية
        if hasattr(admin_class, 'has_add_permission'):
            try:
                capabilities['can_add'] = self._check_permission_method(admin_class.has_add_permission)
            except:
                capabilities['can_add'] = True
        
        if hasattr(admin_class, 'has_change_permission'):
            try:
                capabilities['can_change'] = self._check_permission_method(admin_class.has_change_permission)
            except:
                capabilities['can_change'] = True
        
        if hasattr(admin_class, 'has_delete_permission'):
            try:
                capabilities['can_delete'] = self._check_permission_method(admin_class.has_delete_permission)
            except:
                capabilities['can_delete'] = True
        
        if hasattr(admin_class, 'has_view_permission'):
            try:
                capabilities['can_view'] = self._check_permission_method(admin_class.has_view_permission)
            except:
                capabilities['can_view'] = True
        
        # فحص الحقول
        if hasattr(admin_class, 'list_display') and admin_class.list_display:
            capabilities['list_display_fields'] = list(admin_class.list_display)
        
        if hasattr(admin_class, 'readonly_fields') and admin_class.readonly_fields:
            capabilities['readonly_fields'] = list(admin_class.readonly_fields)
            capabilities['has_readonly_fields'] = len(admin_class.readonly_fields) > 0
        
        if hasattr(admin_class, 'exclude') and admin_class.exclude:
            capabilities['exclude_fields'] = list(admin_class.exclude)
        
        if hasattr(admin_class, 'fieldsets'):
            capabilities['fieldsets'] = admin_class.fieldsets is not None
        
        # فحص الإجراءات المخصصة
        if hasattr(admin_class, 'actions') and admin_class.actions:
            capabilities['custom_actions'] = [
                str(action) for action in admin_class.actions
                if str(action) not in ['delete_selected']
            ]
        
        # فحص التخصيصات المتقدمة
        capabilities['has_custom_queryset'] = hasattr(admin_class, 'get_queryset')
        capabilities['has_custom_save'] = hasattr(admin_class, 'save_model')
        capabilities['has_custom_delete'] = hasattr(admin_class, 'delete_model')
        
        # فحص audit logging (تخمين أساسي)
        capabilities['has_audit_logging'] = self._check_audit_logging(admin_class)
        
        return capabilities
    
    def _check_permission_method(self, method):
        """فحص ما إذا كانت دالة الصلاحية تسمح بالعملية"""
        try:
            # محاولة تحليل الكود للتحقق من القيود
            source = inspect.getsource(method)
            
            # إذا كانت الدالة ترجع False مباشرة
            if 'return False' in source:
                return False
            
            # إذا كانت تحتوي على شروط معقدة
            if 'if ' in source and ('request.user' in source or 'permission' in source):
                return 'conditional'
            
            # افتراضياً True
            return True
            
        except Exception:
            # إذا فشل التحليل، افترض True
            return True
    
    def _check_audit_logging(self, admin_class):
        """فحص وجود audit logging"""
        # فحص مبسط للبحث عن مؤشرات audit
        audit_indicators = [
            'log_addition', 'log_change', 'log_deletion',
            'LogEntry', 'audit', 'history', 'track'
        ]
        
        try:
            source = inspect.getsource(admin_class)
            return any(indicator in source for indicator in audit_indicators)
        except Exception:
            return False
    
    def _find_unregistered_sensitive_models(self):
        """البحث عن النماذج الحساسة غير المسجلة"""
        registered_model_names = set()
        for model_key in self.risk_assessment['registered_models']:
            model_name = model_key.split('.')[-1]
            registered_model_names.add(model_name)
        
        unregistered = []
        for sensitive_model in self.sensitive_models:
            if sensitive_model not in registered_model_names:
                # محاولة العثور على النموذج
                found_models = []
                for app_config in apps.get_app_configs():
                    try:
                        model = apps.get_model(app_config.label, sensitive_model)
                        found_models.append({
                            'model_name': sensitive_model,
                            'app_label': app_config.label,
                            'full_name': f"{app_config.label}.{sensitive_model}",
                            'status': 'exists_but_unregistered'
                        })
                    except LookupError:
                        continue
                
                if not found_models:
                    unregistered.append({
                        'model_name': sensitive_model,
                        'status': 'not_found'
                    })
                else:
                    unregistered.extend(found_models)
        
        self.risk_assessment['unregistered_sensitive_models'] = unregistered
    
    def _calculate_admin_risk_score(self, model_name, capabilities):
        """حساب درجة خطر admin"""
        risk_score = 0
        
        # خطر أساسي للنماذج الحساسة
        if model_name in self.sensitive_models:
            risk_score += 5
        
        # خطر الصلاحيات
        if capabilities['can_delete']:
            risk_score += 3
        if capabilities['can_change']:
            risk_score += 2
        if capabilities['can_add']:
            risk_score += 1
        
        # تقليل الخطر للممارسات الجيدة
        if capabilities['has_readonly_fields']:
            risk_score -= 1
        if capabilities['has_audit_logging']:
            risk_score -= 2
        if capabilities['can_delete'] == 'conditional':
            risk_score -= 1
        if capabilities['can_change'] == 'conditional':
            risk_score -= 1
        
        # خطر إضافي للإجراءات المخصصة
        if capabilities['custom_actions']:
            risk_score += len(capabilities['custom_actions'])
        
        return max(0, min(risk_score, 10))  # بين 0 و 10
    
    def categorize_risk_levels(self):
        """تصنيف النماذج حسب مستوى الخطر"""
        print("📊 Categorizing admin risk levels...")
        
        high_risk = []
        medium_risk = []
        low_risk = []
        
        for model_key, model_info in self.risk_assessment['registered_models'].items():
            risk_score = model_info['risk_score']
            
            risk_entry = {
                'model': model_key,
                'model_name': model_info['model_name'],
                'app_label': model_info['app_label'],
                'risk_score': risk_score,
                'is_sensitive': model_info['is_sensitive'],
                'capabilities': model_info['capabilities']
            }
            
            if risk_score >= 7:
                high_risk.append(risk_entry)
            elif risk_score >= 4:
                medium_risk.append(risk_entry)
            else:
                low_risk.append(risk_entry)
        
        # ترتيب حسب درجة الخطر
        high_risk.sort(key=lambda x: x['risk_score'], reverse=True)
        medium_risk.sort(key=lambda x: x['risk_score'], reverse=True)
        low_risk.sort(key=lambda x: x['risk_score'], reverse=True)
        
        self.risk_assessment['high_risk_admins'] = high_risk
        self.risk_assessment['medium_risk_admins'] = medium_risk
        self.risk_assessment['low_risk_admins'] = low_risk
    
    def identify_audit_trail_gaps(self):
        """تحديد الثغرات في audit trail"""
        print("🔍 Identifying audit trail gaps...")
        
        gaps = []
        
        for model_key, model_info in self.risk_assessment['registered_models'].items():
            if model_info['is_sensitive']:
                capabilities = model_info['capabilities']
                
                gap_info = {
                    'model': model_key,
                    'model_name': model_info['model_name'],
                    'risk_score': model_info['risk_score'],
                    'gaps': []
                }
                
                # فحص الثغرات
                if not capabilities['has_audit_logging']:
                    gap_info['gaps'].append('no_audit_logging')
                
                if capabilities['can_delete'] and capabilities['can_delete'] != 'conditional':
                    gap_info['gaps'].append('unrestricted_delete')
                
                if capabilities['can_change'] and not capabilities['has_readonly_fields']:
                    gap_info['gaps'].append('no_readonly_protection')
                
                if capabilities['custom_actions'] and not capabilities['has_audit_logging']:
                    gap_info['gaps'].append('unaudited_custom_actions')
                
                if gap_info['gaps']:
                    gaps.append(gap_info)
        
        self.risk_assessment['audit_trail_gaps'] = gaps
    
    def identify_permission_bypasses(self):
        """تحديد إمكانيات تجاوز الصلاحيات"""
        print("🔍 Identifying permission bypass opportunities...")
        
        bypasses = []
        
        for model_key, model_info in self.risk_assessment['registered_models'].items():
            if model_info['is_sensitive']:
                capabilities = model_info['capabilities']
                
                bypass_info = {
                    'model': model_key,
                    'model_name': model_info['model_name'],
                    'bypass_methods': []
                }
                
                # فحص طرق التجاوز المحتملة
                if capabilities['can_delete'] == True:  # غير مشروط
                    bypass_info['bypass_methods'].append('direct_delete_via_admin')
                
                if capabilities['can_change'] == True and not capabilities['readonly_fields']:
                    bypass_info['bypass_methods'].append('direct_edit_all_fields')
                
                if capabilities['custom_actions']:
                    bypass_info['bypass_methods'].append('custom_actions_without_validation')
                
                if not capabilities['has_custom_save']:
                    bypass_info['bypass_methods'].append('bypass_business_logic_on_save')
                
                if not capabilities['has_custom_delete']:
                    bypass_info['bypass_methods'].append('bypass_business_logic_on_delete')
                
                if bypass_info['bypass_methods']:
                    bypasses.append(bypass_info)
        
        self.risk_assessment['permission_bypasses'] = bypasses
    
    def generate_attack_surface_map(self):
        """توليد خريطة سطح الهجوم"""
        print("🗺️  Generating admin attack surface map...")
        
        # تجميع الإحصائيات
        total_registered = len(self.risk_assessment['registered_models'])
        sensitive_registered = sum(1 for m in self.risk_assessment['registered_models'].values() if m['is_sensitive'])
        high_risk_count = len(self.risk_assessment['high_risk_admins'])
        audit_gaps_count = len(self.risk_assessment['audit_trail_gaps'])
        bypass_opportunities = len(self.risk_assessment['permission_bypasses'])
        
        # حساب درجة الخطر الإجمالية
        total_risk_score = sum(m['risk_score'] for m in self.risk_assessment['registered_models'].values())
        avg_risk_score = total_risk_score / total_registered if total_registered > 0 else 0
        
        # تحديد مستوى الخطر الإجمالي
        if high_risk_count > 5 or avg_risk_score > 6:
            overall_risk_level = 'CRITICAL'
        elif high_risk_count > 2 or avg_risk_score > 4:
            overall_risk_level = 'HIGH'
        elif audit_gaps_count > 3 or avg_risk_score > 2:
            overall_risk_level = 'MEDIUM'
        else:
            overall_risk_level = 'LOW'
        
        attack_surface_map = {
            'overall_assessment': {
                'risk_level': overall_risk_level,
                'total_registered_models': total_registered,
                'sensitive_models_registered': sensitive_registered,
                'high_risk_admins': high_risk_count,
                'audit_trail_gaps': audit_gaps_count,
                'bypass_opportunities': bypass_opportunities,
                'average_risk_score': round(avg_risk_score, 2)
            },
            'top_threats': self._identify_top_threats(),
            'immediate_actions_required': self._generate_immediate_actions(),
            'detailed_findings': self.risk_assessment
        }
        
        return attack_surface_map
    
    def _identify_top_threats(self):
        """تحديد أكبر التهديدات"""
        threats = []
        
        # أخطر النماذج
        high_risk_models = self.risk_assessment['high_risk_admins'][:5]
        for model in high_risk_models:
            threats.append({
                'type': 'high_risk_admin',
                'model': model['model'],
                'risk_score': model['risk_score'],
                'threat': f"Admin can directly modify {model['model_name']} without proper controls"
            })
        
        # أكبر الثغرات في audit
        audit_gaps = sorted(
            self.risk_assessment['audit_trail_gaps'],
            key=lambda x: x['risk_score'],
            reverse=True
        )[:3]
        
        for gap in audit_gaps:
            threats.append({
                'type': 'audit_gap',
                'model': gap['model'],
                'gaps': gap['gaps'],
                'threat': f"No audit trail for {gap['model_name']} modifications"
            })
        
        return threats
    
    def _generate_immediate_actions(self):
        """توليد الإجراءات الفورية المطلوبة"""
        actions = []
        
        # إجراءات للنماذج عالية الخطر
        high_risk_count = len(self.risk_assessment['high_risk_admins'])
        if high_risk_count > 0:
            actions.append({
                'priority': 'CRITICAL',
                'action': f'Restrict admin access for {high_risk_count} high-risk models',
                'details': 'Implement readonly_fields, custom permissions, or remove from admin entirely'
            })
        
        # إجراءات للثغرات في audit
        audit_gaps_count = len(self.risk_assessment['audit_trail_gaps'])
        if audit_gaps_count > 0:
            actions.append({
                'priority': 'HIGH',
                'action': f'Implement audit logging for {audit_gaps_count} sensitive models',
                'details': 'Add LogEntry creation or django-simple-history integration'
            })
        
        # إجراءات لتجاوز الصلاحيات
        bypass_count = len(self.risk_assessment['permission_bypasses'])
        if bypass_count > 0:
            actions.append({
                'priority': 'HIGH',
                'action': f'Close {bypass_count} permission bypass opportunities',
                'details': 'Implement custom permission methods and business logic validation'
            })
        
        # النماذج الحساسة غير المسجلة
        unregistered_sensitive = [
            m for m in self.risk_assessment['unregistered_sensitive_models']
            if m['status'] == 'exists_but_unregistered'
        ]
        if unregistered_sensitive:
            actions.append({
                'priority': 'MEDIUM',
                'action': f'Review {len(unregistered_sensitive)} unregistered sensitive models',
                'details': 'Determine if they should be registered with proper restrictions'
            })
        
        return actions


class Command(BaseCommand):
    help = 'Phase -1.4: Assess admin bypass risk and generate attack surface map'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output-format',
            choices=['markdown', 'json', 'both'],
            default='both',
            help='Output format for the report'
        )
        parser.add_argument(
            '--output-dir',
            default='reports',
            help='Directory to save reports'
        )
        parser.add_argument(
            '--include-low-risk',
            action='store_true',
            help='Include low-risk models in detailed output'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting Admin Bypass Risk Assessment (Phase -1.4)')
        )
        
        # إنشاء مجلد التقارير
        output_dir = options['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        
        # تشغيل التقييم
        assessor = AdminBypassRiskAssessor()
        assessor.scan_admin_registrations()
        assessor.categorize_risk_levels()
        assessor.identify_audit_trail_gaps()
        assessor.identify_permission_bypasses()
        
        # توليد خريطة سطح الهجوم
        attack_surface_map = assessor.generate_attack_surface_map()
        
        # حفظ التقارير
        if options['output_format'] in ['json', 'both']:
            json_path = os.path.join(output_dir, 'admin_bypass_risk_assessment.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(attack_surface_map, f, indent=2, ensure_ascii=False)
            self.stdout.write(f"📄 JSON report saved: {json_path}")
        
        if options['output_format'] in ['markdown', 'both']:
            md_path = os.path.join(output_dir, 'admin_bypass_risk_assessment.md')
            self._generate_markdown_report(attack_surface_map, md_path, options['include_low_risk'])
            self.stdout.write(f"📄 Markdown report saved: {md_path}")
        
        # عرض ملخص في الكونسول
        self._display_summary(attack_surface_map)
        
        # تحديد حالة الخروج حسب مستوى الخطر
        risk_level = attack_surface_map['overall_assessment']['risk_level']
        if risk_level == 'CRITICAL':
            self.stdout.write(
                self.style.ERROR(f'❌ Assessment completed - Risk Level: {risk_level}')
            )
            exit(1)
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Admin Bypass Risk Assessment completed - Risk Level: {risk_level}')
            )
    
    def _generate_markdown_report(self, attack_surface_map, file_path, include_low_risk):
        """توليد تقرير Markdown"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# Admin Bypass Risk Assessment Report\n\n")
            f.write(f"**Generated:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # التقييم الإجمالي
            overall = attack_surface_map['overall_assessment']
            f.write("## Overall Risk Assessment\n\n")
            f.write(f"**🎯 Risk Level: {overall['risk_level']}**\n\n")
            f.write(f"- **Total Registered Models:** {overall['total_registered_models']}\n")
            f.write(f"- **Sensitive Models Registered:** {overall['sensitive_models_registered']}\n")
            f.write(f"- **High Risk Admins:** {overall['high_risk_admins']}\n")
            f.write(f"- **Audit Trail Gaps:** {overall['audit_trail_gaps']}\n")
            f.write(f"- **Bypass Opportunities:** {overall['bypass_opportunities']}\n")
            f.write(f"- **Average Risk Score:** {overall['average_risk_score']}/10\n\n")
            
            # أكبر التهديدات
            if attack_surface_map.get('top_threats'):
                f.write("## 🚨 Top Threats\n\n")
                for i, threat in enumerate(attack_surface_map['top_threats'], 1):
                    f.write(f"### {i}. {threat['model']}\n")
                    f.write(f"**Type:** {threat['type']}\n")
                    f.write(f"**Threat:** {threat['threat']}\n")
                    if 'risk_score' in threat:
                        f.write(f"**Risk Score:** {threat['risk_score']}/10\n")
                    f.write("\n")
            
            # الإجراءات الفورية
            if attack_surface_map.get('immediate_actions_required'):
                f.write("## ⚡ Immediate Actions Required\n\n")
                for action in attack_surface_map['immediate_actions_required']:
                    f.write(f"### {action['priority']}: {action['action']}\n")
                    f.write(f"{action['details']}\n\n")
            
            # النماذج عالية الخطر
            detailed = attack_surface_map['detailed_findings']
            if detailed.get('high_risk_admins'):
                f.write("## 🔴 High Risk Admin Models\n\n")
                f.write("| Model | App | Risk Score | Can Delete | Can Change | Audit Logging |\n")
                f.write("|-------|-----|------------|------------|------------|---------------|\n")
                
                for model in detailed['high_risk_admins']:
                    caps = model['capabilities']
                    f.write(f"| {model['model_name']} | {model['app_label']} | {model['risk_score']}/10 | ")
                    f.write(f"{'✅' if caps['can_delete'] else '❌'} | ")
                    f.write(f"{'✅' if caps['can_change'] else '❌'} | ")
                    f.write(f"{'✅' if caps['has_audit_logging'] else '❌'} |\n")
                f.write("\n")
            
            # الثغرات في audit trail
            if detailed.get('audit_trail_gaps'):
                f.write("## 🕳️ Audit Trail Gaps\n\n")
                for gap in detailed['audit_trail_gaps']:
                    f.write(f"### {gap['model_name']}\n")
                    f.write(f"**Risk Score:** {gap['risk_score']}/10\n")
                    f.write(f"**Gaps:** {', '.join(gap['gaps'])}\n\n")
            
            # فرص تجاوز الصلاحيات
            if detailed.get('permission_bypasses'):
                f.write("## 🚪 Permission Bypass Opportunities\n\n")
                for bypass in detailed['permission_bypasses']:
                    f.write(f"### {bypass['model_name']}\n")
                    f.write("**Bypass Methods:**\n")
                    for method in bypass['bypass_methods']:
                        f.write(f"- {method.replace('_', ' ').title()}\n")
                    f.write("\n")
            
            # النماذج الحساسة غير المسجلة
            if detailed.get('unregistered_sensitive_models'):
                f.write("## 📋 Unregistered Sensitive Models\n\n")
                f.write("| Model | Status | App |\n")
                f.write("|-------|--------|---------|\n")
                for model in detailed['unregistered_sensitive_models']:
                    app = model.get('app_label', 'N/A')
                    f.write(f"| {model['model_name']} | {model['status']} | {app} |\n")
                f.write("\n")
            
            # النماذج متوسطة الخطر (اختياري)
            if include_low_risk and detailed.get('medium_risk_admins'):
                f.write("## 🟡 Medium Risk Admin Models\n\n")
                f.write("| Model | App | Risk Score | Key Issues |\n")
                f.write("|-------|-----|------------|------------|\n")
                for model in detailed['medium_risk_admins']:
                    caps = model['capabilities']
                    issues = []
                    if caps['can_delete']:
                        issues.append('Can Delete')
                    if not caps['has_audit_logging']:
                        issues.append('No Audit')
                    if not caps['has_readonly_fields']:
                        issues.append('No Readonly')
                    
                    f.write(f"| {model['model_name']} | {model['app_label']} | {model['risk_score']}/10 | {', '.join(issues)} |\n")
    
    def _display_summary(self, attack_surface_map):
        """عرض ملخص في الكونسول"""
        overall = attack_surface_map['overall_assessment']
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.WARNING("📊 ADMIN BYPASS RISK ASSESSMENT SUMMARY"))
        self.stdout.write("="*60)
        
        # عرض مستوى الخطر بألوان
        risk_level = overall['risk_level']
        if risk_level == 'CRITICAL':
            self.stdout.write(self.style.ERROR(f"🎯 Overall Risk Level: {risk_level}"))
        elif risk_level == 'HIGH':
            self.stdout.write(self.style.WARNING(f"🎯 Overall Risk Level: {risk_level}"))
        else:
            self.stdout.write(f"🎯 Overall Risk Level: {risk_level}")
        
        self.stdout.write(f"Total Registered Models: {overall['total_registered_models']}")
        self.stdout.write(f"Sensitive Models: {overall['sensitive_models_registered']}")
        self.stdout.write(f"High Risk Admins: {overall['high_risk_admins']}")
        self.stdout.write(f"Audit Trail Gaps: {overall['audit_trail_gaps']}")
        self.stdout.write(f"Bypass Opportunities: {overall['bypass_opportunities']}")
        self.stdout.write(f"Average Risk Score: {overall['average_risk_score']}/10")
        
        # عرض أكبر التهديدات
        if attack_surface_map.get('top_threats'):
            self.stdout.write(f"\n🚨 TOP THREATS:")
            for threat in attack_surface_map['top_threats'][:3]:
                self.stdout.write(f"   {threat['model']} - {threat['threat']}")
        
        # عرض الإجراءات الفورية
        if attack_surface_map.get('immediate_actions_required'):
            self.stdout.write(f"\n⚡ IMMEDIATE ACTIONS:")
            for action in attack_surface_map['immediate_actions_required']:
                priority_color = self.style.ERROR if action['priority'] == 'CRITICAL' else self.style.WARNING
                self.stdout.write(f"   {priority_color(action['priority'])}: {action['action']}")
        
        self.stdout.write("="*60 + "\n")