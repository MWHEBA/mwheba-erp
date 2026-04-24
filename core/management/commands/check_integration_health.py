"""
أمر إدارة لفحص صحة التكامل مع الأنظمة الخارجية
Management command to check integration health with external systems
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from financial.services.integration_security_service import FinancialIntegrationSecurityService
from core.services.api_integration_security import APIIntegrationSecurityService
import json


class Command(BaseCommand):
    help = 'فحص صحة التكامل مع الأنظمة الخارجية'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--service',
            type=str,
            choices=['financial', 'api', 'all'],
            default='all',
            help='نوع الخدمة المراد فحصها'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='عرض تفاصيل مفصلة'
        )
        
        parser.add_argument(
            '--json',
            action='store_true',
            help='عرض النتائج بتنسيق JSON'
        )
    
    def handle(self, *args, **options):
        """تنفيذ فحص صحة التكامل"""
        
        service_type = options['service']
        verbose = options['verbose']
        json_output = options['json']
        
        health_results = {
            'timestamp': timezone.now().isoformat(),
            'overall_status': 'healthy',
            'services': {}
        }
        
        try:
            # فحص التكامل المالي
            if service_type in ['financial', 'all']:
                if not json_output:
                    self.stdout.write('🔍 فحص صحة التكامل المالي...')
                
                financial_health = FinancialIntegrationSecurityService.get_integration_health_status()
                health_results['services']['financial'] = financial_health
                
                if not json_output:
                    self._display_service_health('التكامل المالي', financial_health, verbose)
            
            # فحص تكامل APIs
            if service_type in ['api', 'all']:
                if not json_output:
                    self.stdout.write('🔍 فحص صحة تكامل APIs...')
                
                api_health = APIIntegrationSecurityService.get_api_integration_health()
                health_results['services']['api'] = api_health
                
                if not json_output:
                    self._display_service_health('تكامل APIs', api_health, verbose)
            
            # تحديد الحالة العامة
            service_statuses = [service['status'] for service in health_results['services'].values()]
            
            if 'critical' in service_statuses:
                health_results['overall_status'] = 'critical'
            elif 'warning' in service_statuses:
                health_results['overall_status'] = 'warning'
            else:
                health_results['overall_status'] = 'healthy'
            
            # عرض النتائج
            if json_output:
                self.stdout.write(json.dumps(health_results, indent=2, ensure_ascii=False))
            else:
                self._display_overall_summary(health_results)
            
            # تحديد رمز الخروج
            if health_results['overall_status'] == 'critical':
                raise CommandError('حالة التكامل حرجة')
            elif health_results['overall_status'] == 'warning':
                self.stdout.write(
                    self.style.WARNING('⚠️ توجد تحذيرات في حالة التكامل')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('✅ جميع خدمات التكامل تعمل بشكل طبيعي')
                )
                
        except Exception as e:
            if json_output:
                error_result = {
                    'timestamp': timezone.now().isoformat(),
                    'overall_status': 'error',
                    'error': str(e)
                }
                self.stdout.write(json.dumps(error_result, indent=2, ensure_ascii=False))
            else:
                self.stdout.write(
                    self.style.ERROR(f'💥 خطأ في فحص صحة التكامل: {str(e)}')
                )
            
            raise CommandError(f'خطأ في فحص صحة التكامل: {str(e)}')
    
    def _display_service_health(self, service_name, health_data, verbose=False):
        """عرض صحة خدمة معينة"""
        
        status = health_data['status']
        status_icon = {
            'healthy': '✅',
            'warning': '⚠️',
            'critical': '🔴',
            'error': '💥'
        }.get(status, '❓')
        
        self.stdout.write(f'\n{status_icon} {service_name}: {status}')
        
        # عرض التوصيات
        if health_data.get('recommendations'):
            self.stdout.write('   التوصيات:')
            for recommendation in health_data['recommendations']:
                self.stdout.write(f'   • {recommendation}')
        
        # عرض تفاصيل Circuit Breaker
        if health_data.get('circuit_breaker'):
            cb_data = health_data['circuit_breaker']
            cb_status = cb_data.get('state', 'unknown')
            cb_icon = {
                'closed': '🟢',
                'open': '🔴',
                'half_open': '🟡'
            }.get(cb_status, '❓')
            
            self.stdout.write(f'   Circuit Breaker: {cb_icon} {cb_status}')
            
            if verbose and cb_data.get('failure_count', 0) > 0:
                self.stdout.write(f'   عدد الأخطاء: {cb_data["failure_count"]}')
        
        # عرض الإحصائيات
        if verbose and health_data.get('statistics'):
            stats = health_data['statistics']
            self.stdout.write('   الإحصائيات:')
            
            for key, value in stats.items():
                if isinstance(value, float):
                    if 'rate' in key or 'percentage' in key:
                        self.stdout.write(f'   • {key}: {value:.1%}')
                    elif 'time' in key:
                        self.stdout.write(f'   • {key}: {value:.2f}s')
                    else:
                        self.stdout.write(f'   • {key}: {value:.2f}')
                else:
                    self.stdout.write(f'   • {key}: {value}')
        
        # عرض العمليات الحديثة
        if verbose and health_data.get('recent_operations'):
            ops = health_data['recent_operations']
            self.stdout.write('   العمليات الحديثة:')
            
            for key, value in ops.items():
                self.stdout.write(f'   • {key}: {value}')
    
    def _display_overall_summary(self, health_results):
        """عرض الملخص العام"""
        
        overall_status = health_results['overall_status']
        status_icon = {
            'healthy': '✅',
            'warning': '⚠️',
            'critical': '🔴',
            'error': '💥'
        }.get(overall_status, '❓')
        
        self.stdout.write(f'\n📊 الحالة العامة: {status_icon} {overall_status}')
        
        # عدد الخدمات حسب الحالة
        service_counts = {}
        for service_data in health_results['services'].values():
            status = service_data['status']
            service_counts[status] = service_counts.get(status, 0) + 1
        
        self.stdout.write('\n📈 ملخص الخدمات:')
        for status, count in service_counts.items():
            status_icon = {
                'healthy': '✅',
                'warning': '⚠️',
                'critical': '🔴',
                'error': '💥'
            }.get(status, '❓')
            
            self.stdout.write(f'   {status_icon} {status}: {count} خدمة')
        
        # التوصيات العامة
        all_recommendations = []
        for service_data in health_results['services'].values():
            if service_data.get('recommendations'):
                all_recommendations.extend(service_data['recommendations'])
        
        if all_recommendations:
            self.stdout.write('\n💡 التوصيات العامة:')
            for i, recommendation in enumerate(set(all_recommendations), 1):
                self.stdout.write(f'   {i}. {recommendation}')
        
        self.stdout.write(f'\n🕒 وقت الفحص: {health_results["timestamp"]}')