"""
مهام Celery للمطابقة المالية التلقائية
Celery tasks for automated financial reconciliation
"""

import logging
from datetime import datetime, timedelta, date
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from financial.services.data_reconciliation_service import DataReconciliationService
from financial.services.integration_security_service import FinancialIntegrationSecurityService
from core.services.api_integration_security import APIIntegrationSecurityService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def run_daily_reconciliation_task(self, reconciliation_date_str=None, reconciliation_types=None):
    """
    مهمة تشغيل المطابقة اليومية التلقائية
    
    Args:
        reconciliation_date_str: تاريخ المطابقة بصيغة YYYY-MM-DD
        reconciliation_types: أنواع المطابقة المطلوبة
    """
    
    try:
        # تحديد تاريخ المطابقة
        if reconciliation_date_str:
            reconciliation_date = datetime.strptime(reconciliation_date_str, '%Y-%m-%d').date()
        else:
            # افتراضي: أمس
            reconciliation_date = (timezone.now() - timedelta(days=1)).date()
        
        # تحديد أنواع المطابقة
        if reconciliation_types is None:
            reconciliation_types = DataReconciliationService.RECONCILIATION_TYPES
        
        
        # تشغيل المطابقة
        results = DataReconciliationService.run_daily_reconciliation(
            reconciliation_date=reconciliation_date,
            reconciliation_types=reconciliation_types
        )
        
        # إرسال تقرير بالنتائج
        send_reconciliation_report.delay(results)
        
        # إرجاع النتائج
        task_result = {
            'success': True,
            'reconciliation_date': reconciliation_date.isoformat(),
            'status': results['status'],
            'summary': results['summary'],
            'discrepancies_count': len(results['discrepancies']),
            'execution_time': results.get('end_time')
        }
        
        
        return task_result
        
    except Exception as e:
        logger.error(f'خطأ في مهمة المطابقة اليومية: {e}')
        
        # إعادة المحاولة في حالة الخطأ
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=300, exc=e)  # إعادة المحاولة بعد 5 دقائق
        
        # إرسال تنبيه بالفشل
        send_reconciliation_failure_alert.delay(str(e), reconciliation_date_str)
        
        return {
            'success': False,
            'error': str(e),
            'reconciliation_date': reconciliation_date_str,
            'retries': self.request.retries
        }


@shared_task
def send_reconciliation_report(reconciliation_results):
    """
    إرسال تقرير المطابقة بالبريد الإلكتروني
    """
    
    try:
        # إعداد محتوى البريد
        subject = f'تقرير المطابقة اليومية - {reconciliation_results["date"]}'
        
        # تحديد حالة التقرير
        status = reconciliation_results['status']
        status_emoji = {
            'passed': '✅',
            'warning': '⚠️',
            'failed': '❌',
            'error': '💥'
        }.get(status, '❓')
        
        # بناء محتوى البريد
        message_lines = [
            f'{status_emoji} تقرير المطابقة اليومية',
            f'التاريخ: {reconciliation_results["date"]}',
            f'الحالة: {status}',
            '',
            '📊 الملخص:',
            f'• إجمالي الفحوصات: {reconciliation_results["summary"]["total_checks"]}',
            f'• الفحوصات الناجحة: {reconciliation_results["summary"]["passed_checks"]}',
            f'• الفحوصات الفاشلة: {reconciliation_results["summary"]["failed_checks"]}',
            f'• التحذيرات: {reconciliation_results["summary"]["warnings"]}',
            ''
        ]
        
        # إضافة التناقضات إذا وجدت
        if reconciliation_results['discrepancies']:
            message_lines.append(f'🔍 التناقضات المكتشفة ({len(reconciliation_results["discrepancies"])}):')
            
            for i, discrepancy in enumerate(reconciliation_results['discrepancies'][:10], 1):  # أول 10 فقط
                severity_emoji = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢'
                }.get(discrepancy.get('severity', 'medium'), '⚪')
                
                message_lines.append(f'{i}. {severity_emoji} {discrepancy["description"]}')
            
            if len(reconciliation_results['discrepancies']) > 10:
                message_lines.append(f'... و {len(reconciliation_results["discrepancies"]) - 10} تناقضات أخرى')
            
            message_lines.append('')
        
        # إضافة وقت التنفيذ
        if reconciliation_results.get('end_time'):
            message_lines.append(f'🕒 وقت الانتهاء: {reconciliation_results["end_time"]}')
        
        message = '\n'.join(message_lines)
        
        # الحصول على قائمة المستلمين
        recipients = getattr(settings, 'RECONCILIATION_REPORT_RECIPIENTS', [])
        
        if recipients:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=False
            )
            
        else:
            logger.warning('لا توجد عناوين بريد إلكتروني لإرسال تقرير المطابقة')
        
        return {
            'success': True,
            'recipients_count': len(recipients),
            'status': status
        }
        
    except Exception as e:
        logger.error(f'خطأ في إرسال تقرير المطابقة: {e}')
        return {
            'success': False,
            'error': str(e)
        }


@shared_task
def send_reconciliation_failure_alert(error_message, reconciliation_date_str):
    """
    إرسال تنبيه فشل المطابقة
    """
    
    try:
        subject = f'🚨 فشل في المطابقة اليومية - {reconciliation_date_str}'
        
        message = f"""
تنبيه: فشلت مهمة المطابقة اليومية

التاريخ: {reconciliation_date_str}
الخطأ: {error_message}
الوقت: {timezone.now().isoformat()}

يرجى فحص النظام واتخاذ الإجراءات اللازمة.
        """
        
        # الحصول على قائمة المستلمين للتنبيهات
        recipients = getattr(settings, 'RECONCILIATION_ALERT_RECIPIENTS', [])
        
        if recipients:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=False
            )
            
        
        return {
            'success': True,
            'recipients_count': len(recipients)
        }
        
    except Exception as e:
        logger.error(f'خطأ في إرسال تنبيه فشل المطابقة: {e}')
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(bind=True, max_retries=2)
def check_integration_health_task(self):
    """
    مهمة فحص صحة التكامل التلقائية
    """
    
    try:
        
        # فحص صحة التكامل المالي
        financial_health = FinancialIntegrationSecurityService.get_integration_health_status()
        
        # فحص صحة تكامل APIs
        api_health = APIIntegrationSecurityService.get_api_integration_health()
        
        # تجميع النتائج
        health_results = {
            'timestamp': timezone.now().isoformat(),
            'financial': financial_health,
            'api': api_health
        }
        
        # تحديد الحالة العامة
        statuses = [financial_health['status'], api_health['status']]
        
        if 'critical' in statuses:
            overall_status = 'critical'
        elif 'warning' in statuses:
            overall_status = 'warning'
        else:
            overall_status = 'healthy'
        
        health_results['overall_status'] = overall_status
        
        # إرسال تنبيه إذا كانت الحالة حرجة أو تحذيرية
        if overall_status in ['critical', 'warning']:
            send_integration_health_alert.delay(health_results)
        
        
        return {
            'success': True,
            'overall_status': overall_status,
            'timestamp': health_results['timestamp']
        }
        
    except Exception as e:
        logger.error(f'خطأ في مهمة فحص صحة التكامل: {e}')
        
        # إعادة المحاولة في حالة الخطأ
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=600, exc=e)  # إعادة المحاولة بعد 10 دقائق
        
        return {
            'success': False,
            'error': str(e),
            'retries': self.request.retries
        }


@shared_task
def send_integration_health_alert(health_results):
    """
    إرسال تنبيه حالة صحة التكامل
    """
    
    try:
        overall_status = health_results['overall_status']
        status_emoji = {
            'healthy': '✅',
            'warning': '⚠️',
            'critical': '🔴'
        }.get(overall_status, '❓')
        
        subject = f'{status_emoji} تنبيه حالة التكامل - {overall_status}'
        
        message_lines = [
            f'{status_emoji} تقرير حالة صحة التكامل',
            f'الوقت: {health_results["timestamp"]}',
            f'الحالة العامة: {overall_status}',
            ''
        ]
        
        # إضافة تفاصيل كل خدمة
        for service_name, service_health in health_results.items():
            if service_name in ['financial', 'api']:
                service_status = service_health['status']
                service_emoji = {
                    'healthy': '✅',
                    'warning': '⚠️',
                    'critical': '🔴'
                }.get(service_status, '❓')
                
                message_lines.append(f'{service_emoji} {service_name}: {service_status}')
                
                # إضافة التوصيات
                if service_health.get('recommendations'):
                    for recommendation in service_health['recommendations']:
                        message_lines.append(f'  • {recommendation}')
                
                message_lines.append('')
        
        message = '\n'.join(message_lines)
        
        # الحصول على قائمة المستلمين
        recipients = getattr(settings, 'INTEGRATION_HEALTH_ALERT_RECIPIENTS', [])
        
        if recipients:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=False
            )
            
        
        return {
            'success': True,
            'recipients_count': len(recipients),
            'status': overall_status
        }
        
    except Exception as e:
        logger.error(f'خطأ في إرسال تنبيه حالة التكامل: {e}')
        return {
            'success': False,
            'error': str(e)
        }


@shared_task
def cleanup_old_reconciliation_data():
    """
    تنظيف بيانات المطابقة القديمة
    """
    
    try:
        from django.core.cache import cache
        
        # تنظيف بيانات المطابقة الأقدم من 90 يوم
        cutoff_date = timezone.now().date() - timedelta(days=90)
        
        cleaned_count = 0
        
        # تنظيف cache المطابقة
        for days_back in range(90, 365):  # من 90 إلى 365 يوم
            old_date = timezone.now().date() - timedelta(days=days_back)
            
            cache_keys = [
                f"reconciliation_results:{old_date.isoformat()}",
                f"reconciliation_summary:{old_date.isoformat()}"
            ]
            
            for cache_key in cache_keys:
                if cache.get(cache_key):
                    cache.delete(cache_key)
                    cleaned_count += 1
        
        
        return {
            'success': True,
            'cleaned_count': cleaned_count,
            'cutoff_date': cutoff_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f'خطأ في تنظيف بيانات المطابقة القديمة: {e}')
        return {
            'success': False,
            'error': str(e)
        }