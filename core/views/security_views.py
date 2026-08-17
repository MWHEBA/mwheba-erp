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


def csrf_failure(request, reason=""):
    """
    ✅ معالج أخطاء CSRF المخصص للنظام - الاسترداد الجذري من أخطاء الرموز الأمنية
    - يمنع ظهور صفحة الخطأ 403 الخام للمستخدمين نهائياً
    - يوجه المستخدمين المسجلين تلقائياً إلى الصفحة السابقة أو لوحة التحكم مع تجديد الرمز
    - يعيد توجيه طلبات صفحة الدخول المكررة أو منتهية الصلاحية بأمان
    - يزود طلبات AJAX بأحدث CSRF Token للمزامنة التلقائية
    """
    from django.shortcuts import redirect, render
    from django.conf import settings
    from django.contrib import messages
    from django.middleware.csrf import get_token

    # توليد رمز CSRF جديد وتثبيته في الطلب الحالي
    new_token = get_token(request)
    login_url = getattr(settings, 'LOGIN_URL', '/login/')

    # 1. إذا كان الطلب AJAX أو API
    if (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
        or request.content_type == 'application/json'
    ):
        response = JsonResponse({
            'error': 'انتهت صلاحية رمز الأمان (CSRF)',
            'code': 'CSRF_FAILURE',
            'csrf_token': new_token,
            'reload_required': False,
            'message': 'تم تحديث رمز الأمان، يرجى إعادة المحاولة.'
        }, status=403)
        response.set_cookie('csrftoken', new_token, samesite='Lax')
        return response

    # 2. إذا كان المستخدم مسجل دخوله بالفعل (أثناء تصفح النظام أو محاولة دخول مكررة)
    if hasattr(request, 'user') and request.user.is_authenticated:
        referer = request.META.get('HTTP_REFERER')
        host = request.get_host()
        if referer and host in referer:
            try:
                messages.info(request, "تم تجديد جلسة الأمان الخاصة بك تلقائياً، يرجى إعادة المحاولة.")
            except Exception:
                pass
            response = redirect(referer)
        else:
            response = redirect(getattr(settings, 'LOGIN_REDIRECT_URL', '/'))
        response.set_cookie('csrftoken', new_token, samesite='Lax')
        return response

    # 3. إذا كان الطلب من صفحة تسجيل الدخول
    if request.path == login_url or request.path.rstrip('/') == login_url.rstrip('/'):
        try:
            messages.info(request, "تم تجديد جلسة الأمان، يرجى تسجيل الدخول.")
        except Exception:
            pass
        response = redirect(login_url)
        response.set_cookie('csrftoken', new_token, samesite='Lax')
        return response

    # 4. إذا كان مستخدم غير مسجل يحاول إرسال نموذج في صفحة محمية
    try:
        messages.warning(request, "انتهت صلاحية الجلسة، يرجى تسجيل الدخول للمتابعة.")
    except Exception:
        pass
    response = redirect(f"{login_url}?next={request.path}")
    response.set_cookie('csrftoken', new_token, samesite='Lax')
    return response