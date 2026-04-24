"""
🔒 Views للأمان المتقدم
معالجة تقارير CSP وأحداث الأمان
"""

import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from datetime import datetime, timedelta

logger = logging.getLogger('security')


@csrf_exempt  # ✅ SECURITY: Required for CSP reports from browsers - this is safe
@require_http_methods(["POST"])
def csp_report_handler(request):
    """
    ✅ معالج تقارير Content Security Policy
    Note: @csrf_exempt is required here as browsers send CSP reports without CSRF tokens
    """
    try:
        # قراءة تقرير CSP
        report_data = json.loads(request.body.decode('utf-8'))
        csp_report = report_data.get('csp-report', {})
        
        # استخراج معلومات مهمة
        violated_directive = csp_report.get('violated-directive', '')
        blocked_uri = csp_report.get('blocked-uri', '')
        document_uri = csp_report.get('document-uri', '')
        source_file = csp_report.get('source-file', '')
        line_number = csp_report.get('line-number', '')
        
        # تسجيل انتهاك CSP
        logger.warning(
            f"🚨 CSP Violation: {violated_directive}",
            extra={
                'event_type': 'CSP_VIOLATION',
                'violated_directive': violated_directive,
                'blocked_uri': blocked_uri,
                'document_uri': document_uri,
                'source_file': source_file,
                'line_number': line_number,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'ip_address': get_client_ip(request),
                'timestamp': datetime.now().isoformat(),
            }
        )
        
        # حفظ في cache للتحليل
        cache_key = f"csp_violation_{datetime.now().strftime('%Y%m%d_%H')}"
        violations = cache.get(cache_key, [])
        violations.append({
            'violated_directive': violated_directive,
            'blocked_uri': blocked_uri,
            'document_uri': document_uri,
            'timestamp': datetime.now().isoformat(),
            'ip': get_client_ip(request),
        })
        cache.set(cache_key, violations, 3600)  # حفظ لساعة واحدة
        
        return HttpResponse(status=204)  # No Content
        
    except Exception as e:
        logger.error(f"خطأ في معالجة تقرير CSP: {str(e)}")
        return HttpResponse(status=400)


@method_decorator([login_required, csrf_exempt], name='dispatch')
class SecurityLogView(View):
    """
    ✅ API لتسجيل الأحداث الأمنية من JavaScript
    """
    
    def post(self, request):
        """تسجيل حدث أمني"""
        try:
            data = json.loads(request.body.decode('utf-8'))
            
            event_type = data.get('event', 'UNKNOWN')
            details = data.get('details', '')
            timestamp = data.get('timestamp', datetime.now().isoformat())
            
            # التحقق من صحة البيانات
            if not event_type or len(event_type) > 100:
                return JsonResponse({'error': 'Invalid event type'}, status=400)
            
            # تسجيل الحدث
            logger.warning(
                f"🔒 Client Security Event: {event_type}",
                extra={
                    'event_type': f'CLIENT_{event_type}',
                    'details': details,
                    'user': request.user.username if request.user.is_authenticated else 'Anonymous',
                    'ip_address': get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'timestamp': timestamp,
                    'url': data.get('url', ''),
                }
            )
            
            return JsonResponse({'status': 'logged'})
            
        except Exception as e:
            logger.error(f"خطأ في تسجيل الحدث الأمني: {str(e)}")
            return JsonResponse({'error': 'Logging failed'}, status=500)


@login_required
def security_dashboard(request):
    """
    ✅ لوحة تحكم الأمان (للمديرين فقط)
    """
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        # جمع إحصائيات الأمان من cache
        current_hour = datetime.now().strftime('%Y%m%d_%H')
        
        # انتهاكات CSP
        csp_violations = cache.get(f"csp_violation_{current_hour}", [])
        
        # أحداث أمنية أخرى (يمكن إضافة المزيد)
        security_stats = {
            'csp_violations': len(csp_violations),
            'recent_violations': csp_violations[-10:],  # آخر 10 انتهاكات
            'timestamp': datetime.now().isoformat(),
        }
        
        return JsonResponse(security_stats)
        
    except Exception as e:
        logger.error(f"خطأ في لوحة تحكم الأمان: {str(e)}")
        return JsonResponse({'error': 'Dashboard error'}, status=500)


@login_required
def security_report(request):
    """
    ✅ تقرير أمني مفصل (للمديرين فقط)
    """
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        # جمع تقرير شامل للـ 24 ساعة الماضية
        report_data = {
            'period': '24 hours',
            'generated_at': datetime.now().isoformat(),
            'csp_violations': [],
            'security_events': [],
            'summary': {
                'total_violations': 0,
                'unique_ips': set(),
                'top_violated_directives': {},
            }
        }
        
        # جمع البيانات من آخر 24 ساعة
        for i in range(24):
            hour_key = (datetime.now() - timedelta(hours=i)).strftime('%Y%m%d_%H')
            violations = cache.get(f"csp_violation_{hour_key}", [])
            
            report_data['csp_violations'].extend(violations)
            report_data['summary']['total_violations'] += len(violations)
            
            # تحليل البيانات
            for violation in violations:
                ip = violation.get('ip', 'unknown')
                directive = violation.get('violated_directive', 'unknown')
                
                report_data['summary']['unique_ips'].add(ip)
                
                if directive in report_data['summary']['top_violated_directives']:
                    report_data['summary']['top_violated_directives'][directive] += 1
                else:
                    report_data['summary']['top_violated_directives'][directive] = 1
        
        # تحويل set إلى list للـ JSON
        report_data['summary']['unique_ips'] = len(report_data['summary']['unique_ips'])
        
        return JsonResponse(report_data)
        
    except Exception as e:
        logger.error(f"خطأ في إنشاء التقرير الأمني: {str(e)}")
        return JsonResponse({'error': 'Report generation failed'}, status=500)


def get_client_ip(request):
    """
    ✅ الحصول على IP الحقيقي للعميل
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
    return ip


@csrf_exempt
@require_http_methods(["POST"])
def security_incident_report(request):
    """
    ✅ تقرير حوادث أمنية من العملاء
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        
        incident_type = data.get('type', 'UNKNOWN')
        description = data.get('description', '')
        severity = data.get('severity', 'medium')
        
        # تسجيل الحادث
        logger.critical(
            f"🚨 Security Incident Reported: {incident_type}",
            extra={
                'event_type': 'SECURITY_INCIDENT',
                'incident_type': incident_type,
                'description': description,
                'severity': severity,
                'ip_address': get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'timestamp': datetime.now().isoformat(),
            }
        )
        
        # إشعار فوري للمديرين (يمكن إضافة email/SMS)
        if severity == 'critical':
            # TODO: إرسال إشعار فوري
            pass
        
        return JsonResponse({'status': 'incident_logged', 'id': datetime.now().timestamp()})
        
    except Exception as e:
        logger.error(f"خطأ في تسجيل الحادث الأمني: {str(e)}")
        return JsonResponse({'error': 'Incident logging failed'}, status=500)