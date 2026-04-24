"""
Management command to register all signals in the system
أمر لتسجيل جميع الإشارات في النظام
"""
from django.core.management.base import BaseCommand
from django.apps import apps
from django.db.models import signals as django_signals
import inspect
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'تسجيل جميع الإشارات الموجودة في النظام'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            help='تحديث الإشارات الموجودة',
        )
    
    def handle(self, *args, **options):
        from governance.models import SignalRegistry
        
        self.stdout.write(self.style.SUCCESS('🔍 البحث عن الإشارات في النظام...'))
        
        registered_count = 0
        updated_count = 0
        
        # List of known signal modules
        signal_modules = [
            'client.signals',
            'supplier.signals',
            'purchase.signals',
            'sale.signals',
            'product.signals',
            'product.signals_bundle_stock',
            'hr.signals',
            'hr.signals_permissions',
            'financial.signals.payment_signals',
            'financial.signals.validation_signals',
            'governance.signals.auto_activation',
            'governance.signals.payroll_signals',
            'governance.signals.security_signals',
        ]
        
        for module_path in signal_modules:
            try:
                # Import the module
                module = __import__(module_path, fromlist=[''])
                
                # Get module name
                app_name = module_path.split('.')[0]
                
                # Find all receiver functions
                for name, obj in inspect.getmembers(module):
                    if inspect.isfunction(obj) and hasattr(obj, '__wrapped__'):
                        # This is likely a signal receiver
                        signal_name = obj.__name__
                        
                        # Try to determine signal type and model
                        signal_type = 'custom'
                        model_name = 'Unknown'
                        priority = 'MEDIUM'
                        is_critical = False
                        description = ''
                        
                        # Check if it has governed_signal_handler decorator
                        if hasattr(obj, '_signal_name'):
                            signal_name = obj._signal_name
                        if hasattr(obj, '_is_critical'):
                            is_critical = obj._is_critical
                        if hasattr(obj, '_description'):
                            description = obj._description
                        
                        # Try to extract from docstring
                        if obj.__doc__:
                            description = obj.__doc__.strip().split('\n')[0]
                        
                        # Determine signal type from name
                        if 'post_save' in signal_name or '_saved' in signal_name or '_creation' in signal_name:
                            signal_type = 'post_save'
                        elif 'pre_save' in signal_name or '_before' in signal_name:
                            signal_type = 'pre_save'
                        elif 'post_delete' in signal_name or '_deleted' in signal_name or '_deletion' in signal_name:
                            signal_type = 'post_delete'
                        elif 'pre_delete' in signal_name:
                            signal_type = 'pre_delete'
                        
                        # Determine priority from name
                        if 'critical' in signal_name.lower() or 'payment' in signal_name.lower() or 'account' in signal_name.lower():
                            priority = 'CRITICAL'
                            is_critical = True
                        elif 'important' in signal_name.lower() or 'balance' in signal_name.lower():
                            priority = 'HIGH'
                        
                        # Register or update signal
                        signal_registry, created = SignalRegistry.objects.get_or_create(
                            signal_name=signal_name,
                            defaults={
                                'signal_type': signal_type,
                                'module_name': app_name,
                                'model_name': model_name,
                                'priority': priority,
                                'is_critical': is_critical,
                                'description': description[:500] if description else '',
                                'handler_function': f"{module_path}.{obj.__name__}",
                                'status': 'ACTIVE',
                            }
                        )
                        
                        if created:
                            registered_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(f'  ✅ تم تسجيل: {signal_name} ({app_name})')
                            )
                        elif options['update']:
                            # Update existing
                            signal_registry.signal_type = signal_type
                            signal_registry.module_name = app_name
                            signal_registry.priority = priority
                            signal_registry.is_critical = is_critical
                            if description:
                                signal_registry.description = description[:500]
                            signal_registry.handler_function = f"{module_path}.{obj.__name__}"
                            signal_registry.save()
                            updated_count += 1
                            self.stdout.write(
                                self.style.WARNING(f'  🔄 تم تحديث: {signal_name} ({app_name})')
                            )
                
            except ImportError as e:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  تخطي {module_path}: {e}')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ❌ خطأ في {module_path}: {e}')
                )
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'✅ تم تسجيل {registered_count} إشارة جديدة'))
        if options['update']:
            self.stdout.write(self.style.SUCCESS(f'🔄 تم تحديث {updated_count} إشارة موجودة'))
        
        total_signals = SignalRegistry.objects.count()
        active_signals = SignalRegistry.objects.filter(status='ACTIVE').count()
        critical_signals = SignalRegistry.objects.filter(is_critical=True).count()
        
        self.stdout.write(self.style.SUCCESS(f'📊 إجمالي الإشارات في النظام: {total_signals}'))
        self.stdout.write(self.style.SUCCESS(f'   - نشطة: {active_signals}'))
        self.stdout.write(self.style.SUCCESS(f'   - حرجة: {critical_signals}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
