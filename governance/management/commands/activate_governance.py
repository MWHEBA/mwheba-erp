"""
Django Management Command لتفعيل Governance تلقائياً
Auto-Activate Governance Django Management Command

يتم استدعاؤه تلقائياً بعد migrate أو يدوياً عند الحاجة
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'تفعيل موديول Governance تلقائياً - Auto-activate Governance module'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='فرض التفعيل حتى لو كان مفعلاً بالفعل',
        )
        parser.add_argument(
            '--silent',
            action='store_true',
            help='تشغيل صامت بدون رسائل تفصيلية',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='فحص الحالة فقط بدون تفعيل',
        )
    
    def handle(self, *args, **options):
        """تنفيذ الأمر"""
        
        force = options.get('force', False)
        silent = options.get('silent', False)
        check_only = options.get('check_only', False)
        
        if not silent:
            self.stdout.write(
                self.style.SUCCESS('🚀 بدء تفعيل موديول Governance التلقائي')
            )
        
        try:
            # استيراد الخدمات
            from governance.services import governance_switchboard
            from governance.services.audit_service import AuditService
            
            # فحص الحالة الحالية
            stats = governance_switchboard.get_governance_statistics()
            
            if check_only:
                self._display_status(stats, silent)
                return
            
            # الحصول على مستخدم النظام
            system_user = self._get_system_user()
            
            # تفعيل المكونات الحرجة
            activated_components = self._activate_critical_components(
                governance_switchboard, system_user, force, silent
            )
            
            # تفعيل سير العمل الحرج
            activated_workflows = self._activate_critical_workflows(
                governance_switchboard, system_user, force, silent
            )
            
            # التحقق من النجاح
            final_stats = governance_switchboard.get_governance_statistics()
            success = self._verify_activation(final_stats, silent)
            
            if success:
                if not silent:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ تم تفعيل Governance بنجاح! '
                            f'المكونات: {len(activated_components)}, '
                            f'سير العمل: {len(activated_workflows)}'
                        )
                    )
                
                # تسجيل في التدقيق
                if system_user:
                    AuditService.log_operation(
                        model_name='GovernanceSwitchboard',
                        object_id=0,
                        operation='AUTO_ACTIVATION_SUCCESS',
                        source_service='ManagementCommand',
                        user=system_user,
                        after_data={
                            'activated_components': activated_components,
                            'activated_workflows': activated_workflows,
                            'timestamp': datetime.now().isoformat()
                        }
                    )
            else:
                raise CommandError('فشل في تفعيل Governance - راجع الأخطاء أعلاه')
                
        except Exception as e:
            error_msg = f'خطأ في تفعيل Governance: {str(e)}'
            logger.error(error_msg)
            raise CommandError(error_msg)
    
    def _get_system_user(self):
        """الحصول على مستخدم النظام للتدقيق"""
        try:
            User = get_user_model()
            # البحث عن مستخدم admin أو superuser
            system_user = User.objects.filter(
                is_superuser=True, is_active=True
            ).first()
            
            if not system_user:
                # إنشاء مستخدم نظام مؤقت إذا لم يوجد
                system_user = User.objects.create_superuser(
                    username='governance_system',
                    email='system@governance.local',
                    password='temp_governance_password'
                )
            
            return system_user
        except Exception as e:
            logger.warning(f'لا يمكن الحصول على مستخدم النظام: {e}')
            return None
    
    def _activate_critical_components(self, switchboard, user, force, silent):
        """تفعيل المكونات الحرجة"""
        
        critical_components = [
            'accounting_gateway_enforcement',
            'movement_service_enforcement',
            'admin_lockdown_enforcement',
            'authority_boundary_enforcement',
            'audit_trail_enforcement',
            'idempotency_enforcement'
        ]
        
        activated = []
        
        for component in critical_components:
            try:
                if force or not switchboard.is_component_enabled(component):
                    success = switchboard.enable_component(
                        component,
                        reason="تفعيل تلقائي عبر Management Command",
                        user=user
                    )
                    
                    if success:
                        activated.append(component)
                        if not silent:
                            self.stdout.write(f'  ✅ تم تفعيل المكون: {component}')
                    else:
                        if not silent:
                            self.stdout.write(
                                self.style.WARNING(f'  ⚠️ فشل تفعيل المكون: {component}')
                            )
                else:
                    if not silent:
                        self.stdout.write(f'  ℹ️ المكون مفعل بالفعل: {component}')
                        
            except Exception as e:
                if not silent:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ خطأ في تفعيل {component}: {e}')
                    )
        
        return activated
    
    def _activate_critical_workflows(self, switchboard, user, force, silent):
        """تفعيل سير العمل الحرج"""
        
        critical_workflows = [
            'customer_payment_to_journal_entry',
            'stock_movement_to_journal_entry',
            'purchase_payment_to_journal_entry',
            'admin_direct_edit_prevention',
            'cross_service_validation',
            'audit_logging',
            'duplicate_operation_prevention'
        ]
        
        activated = []
        
        for workflow in critical_workflows:
            try:
                if force or not switchboard.is_workflow_enabled(workflow):
                    success = switchboard.enable_workflow(
                        workflow,
                        reason="تفعيل تلقائي عبر Management Command",
                        user=user
                    )
                    
                    if success:
                        activated.append(workflow)
                        if not silent:
                            self.stdout.write(f'  ✅ تم تفعيل سير العمل: {workflow}')
                    else:
                        if not silent:
                            self.stdout.write(
                                self.style.WARNING(f'  ⚠️ فشل تفعيل سير العمل: {workflow}')
                            )
                else:
                    if not silent:
                        self.stdout.write(f'  ℹ️ سير العمل مفعل بالفعل: {workflow}')
                        
            except Exception as e:
                if not silent:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ خطأ في تفعيل {workflow}: {e}')
                    )
        
        return activated
    
    def _verify_activation(self, stats, silent):
        """التحقق من نجاح التفعيل"""
        
        critical_components = [
            'accounting_gateway_enforcement',
            'movement_service_enforcement',
            'admin_lockdown_enforcement',
            'authority_boundary_enforcement',
            'audit_trail_enforcement',
            'idempotency_enforcement'
        ]
        
        critical_workflows = [
            'customer_payment_to_journal_entry',
            'stock_movement_to_journal_entry',
            'purchase_payment_to_journal_entry',
            'admin_direct_edit_prevention',
            'cross_service_validation',
            'audit_logging',
            'duplicate_operation_prevention'
        ]
        
        # فحص المكونات
        enabled_components = stats['components']['enabled_list']
        missing_components = [
            comp for comp in critical_components 
            if comp not in enabled_components
        ]
        
        # فحص سير العمل
        enabled_workflows = stats['workflows']['enabled_list']
        missing_workflows = [
            workflow for workflow in critical_workflows 
            if workflow not in enabled_workflows
        ]
        
        if missing_components or missing_workflows:
            if not silent:
                if missing_components:
                    self.stdout.write(
                        self.style.ERROR(f'❌ مكونات غير مفعلة: {missing_components}')
                    )
                if missing_workflows:
                    self.stdout.write(
                        self.style.ERROR(f'❌ سير عمل غير مفعل: {missing_workflows}')
                    )
            return False
        
        return True
    
    def _display_status(self, stats, silent):
        """عرض حالة Governance"""
        
        if silent:
            return
        
        self.stdout.write('📊 حالة موديول Governance:')
        self.stdout.write(f'  المكونات المفعلة: {stats["components"]["enabled"]}/{stats["components"]["total"]}')
        self.stdout.write(f'  سير العمل المفعل: {stats["workflows"]["enabled"]}/{stats["workflows"]["total"]}')
        self.stdout.write(f'  حالات الطوارئ النشطة: {stats["emergency"]["active"]}')
        
        if stats['components']['disabled_list']:
            self.stdout.write(
                self.style.WARNING(f'  المكونات المعطلة: {stats["components"]["disabled_list"]}')
            )
        
        if stats['workflows']['disabled_list']:
            self.stdout.write(
                self.style.WARNING(f'  سير العمل المعطل: {stats["workflows"]["disabled_list"]}')
            )
        
        if stats['emergency']['active'] > 0:
            self.stdout.write(
                self.style.ERROR(f'  حالات الطوارئ النشطة: {stats["emergency"]["active_list"]}')
            )