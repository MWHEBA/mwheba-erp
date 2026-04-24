"""
# واجهة برمجة التطبيقات (API) لتطبيق core
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Count, Sum
from django.utils.dateparse import parse_datetime
from datetime import timedelta
from utils.email_utils import get_email_settings_from_db
import logging
import psutil
import os

logger = logging.getLogger(__name__)

from utils.throttling import SustainedRateThrottle, BurstRateThrottle
from purchase.models import Purchase
from supplier.models import Supplier
from product.models import Product
from .models import DashboardStat, Notification, SystemSetting
from rest_framework import status


class DashboardStatsAPIView(APIView):
    """
    # واجهة برمجة التطبيق لعرض إحصائيات لوحة التحكم
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def get(self, request):
        today = timezone.now().date()
        this_month_start = today.replace(day=1)

        # إحصائيات المبيعات - معطلة مؤقتاً
        sales_this_month = {'count': 0, 'total': 0}

        # إحصائيات المشتريات
        purchases_this_month = Purchase.objects.filter(
            date__gte=this_month_start
        ).aggregate(count=Count("id"), total=Sum("total"))

        # إحصائيات العملاء والموردين والمنتجات
        customers_count = 0  # Customers module removed
        suppliers_count = Supplier.objects.filter(is_active=True).count()
        products_count = Product.objects.filter(is_active=True).count()

        # إعداد البيانات للاستجابة
        data = {
            "sales": {
                "this_month_count": sales_this_month["count"] or 0,
                "this_month_total": sales_this_month["total"] or 0,
            },
            "purchases": {
                "this_month_count": purchases_this_month["count"] or 0,
                "this_month_total": purchases_this_month["total"] or 0,
            },
            "counts": {
                "customers": customers_count,
                "suppliers": suppliers_count,
                "products": products_count,
            },
            "timestamp": timezone.now(),
        }

        return Response(data, status=status.HTTP_200_OK)


class SystemHealthAPIView(APIView):
    """
    # واجهة برمجة التطبيق لعرض صحة النظام
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [BurstRateThrottle]

    def get(self, request):
        # بيانات صحة النظام البسيطة
        data = {
            "status": "healthy",
            "version": "1.0.0",
            "timestamp": timezone.now(),
            "uptime": "24 hours",  # يمكن استبدالها بقياس فعلي لوقت تشغيل النظام
        }

        return Response(data, status=status.HTTP_200_OK)


def get_dashboard_stats(request):
    """
    API لجلب إحصائيات لوحة التحكم
    """
    stats = {}

    try:
        # جلب الإحصائيات من قاعدة البيانات
        dashboard_stats = DashboardStat.objects.filter(is_active=True).order_by("order")

        for stat in dashboard_stats:
            stats[stat.key] = {
                "title": stat.title,
                "value": stat.value,
                "icon": stat.icon,
                "color": stat.color,
                "change": stat.change,
                "change_type": stat.change_type,
                "has_chart": stat.has_chart,
                "chart_data": stat.chart_data,
                "chart_type": stat.chart_type,
            }
    except Exception as e:
        # في حال حدوث خطأ
        return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "success", "stats": stats})


def get_recent_activity(request, days=7):
    """
    API لجلب نشاطات المستخدم الأخيرة
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "message": _("يجب تسجيل الدخول")})

    # جلب النشاطات
    activities = []

    # هنا سيتم استبدال هذا بالنموذج الفعلي للنشاطات
    # مثال افتراضي:
    recent_date = timezone.now()
    for i in range(5):
        activities.append(
            {
                "title": f"نشاط {i+1}",
                "time": (recent_date - timedelta(hours=i * 3)).isoformat(),
                "icon": "fas fa-check-circle",
                "color": "success",
            }
        )

    return JsonResponse({"status": "success", "activities": activities})


# API لإدارة الإشعارات


def mark_notification_read(request, notification_id):
    """
    API لتعليم إشعار كمقروء
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": _("يجب تسجيل الدخول")})

    # التحقق من طريقة الطلب
    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("طريقة طلب غير صالحة")})

    try:
        # البحث عن الإشعار
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.is_read = True
        notification.save()

        return JsonResponse(
            {
                "success": True,
                "message": _("تم تعليم الإشعار كمقروء"),
                "redirect_url": notification.link
                if hasattr(notification, "link")
                else None,
            }
        )
    except Notification.DoesNotExist:
        return JsonResponse({"success": False, "message": _("الإشعار غير موجود")})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


def mark_notification_unread(request, notification_id):
    """
    API لتعليم إشعار كغير مقروء
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": _("يجب تسجيل الدخول")})

    # التحقق من طريقة الطلب
    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("طريقة طلب غير صالحة")})

    try:
        # البحث عن الإشعار
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.is_read = False
        notification.save()

        return JsonResponse(
            {
                "success": True,
                "message": _("تم تعليم الإشعار كغير مقروء")
            }
        )
    except Notification.DoesNotExist:
        return JsonResponse({"success": False, "message": _("الإشعار غير موجود")})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


def mark_all_notifications_read(request):
    """
    API لتعليم جميع الإشعارات كمقروءة
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": _("يجب تسجيل الدخول")})

    # التحقق من طريقة الطلب
    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("طريقة طلب غير صالحة")})

    try:
        # تحديث جميع الإشعارات غير المقروءة للمستخدم
        Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True
        )

        return JsonResponse(
            {"success": True, "message": _("تم تعليم جميع الإشعارات كمقروءة")}
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


@require_http_methods(["GET"])
def get_notifications_count(request):
    """
    API لجلب عدد الإشعارات غير المقروءة
    Rate limited to prevent excessive polling
    """
    # التحقق من تسجيل الدخول - إرجاع 200 مع count=0 بدل redirect أو 500
    if not request.user.is_authenticated:
        return JsonResponse({"success": True, "count": 0})

    try:
        from django.db.utils import OperationalError, ProgrammingError

        try:
            unread_count = Notification.objects.filter(
                user=request.user, is_read=False
            ).count()
            return JsonResponse({"success": True, "count": unread_count})
        except (OperationalError, ProgrammingError):
            return JsonResponse({"success": True, "count": 0})
        except AttributeError:
            return JsonResponse({"success": True, "count": 0})

    except Exception as e:
        logger.error(f"خطأ في جلب عدد الإشعارات: {str(e)}")
        return JsonResponse({"success": True, "count": 0})


@login_required
@require_POST
def delete_old_read_notifications(request):
    """
    API لحذف الإشعارات المقروءة الأقدم من أسبوع
    """
    try:
        # حساب تاريخ قبل أسبوع
        one_week_ago = timezone.now() - timedelta(days=7)
        
        # حذف الإشعارات المقروءة الأقدم من أسبوع
        deleted_count = Notification.objects.filter(
            user=request.user,
            is_read=True,
            created_at__lt=one_week_ago
        ).delete()[0]
        
        return JsonResponse({
            "success": True,
            "message": f"تم حذف {deleted_count} إشعار مقروء",
            "deleted_count": deleted_count
        })
    except Exception as e:
        logger.error(f"خطأ في حذف الإشعارات القديمة: {str(e)}")
        return JsonResponse({
            "success": False,
            "message": "حدث خطأ أثناء حذف الإشعارات"
        })


def test_email_settings(request):
    """
    API لاختبار إعدادات الإيميل
    """
    from django.contrib.auth.decorators import login_required
    from django.views.decorators.http import require_POST
    from utils.email_utils import send_email
    
    # التحقق من تسجيل الدخول والصلاحيات
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "يجب تسجيل الدخول"})
    
    if not (request.user.is_admin or request.user.is_superuser):
        return JsonResponse({"success": False, "message": "ليس لديك صلاحية لتنفيذ هذا الإجراء"})
    
    if request.method != 'POST':
        return JsonResponse({"success": False, "message": "طريقة الطلب غير صحيحة"})
    
    try:
        import json
        from utils.email_utils import get_email_settings_from_db
        from django.conf import settings as django_settings
        
        data = json.loads(request.body)
        test_email = data.get('test_email', request.user.email)
        
        if not test_email:
            return JsonResponse({"success": False, "message": "يرجى إدخال بريد إلكتروني للاختبار"})
        
        # التحقق من وجود إعدادات الإيميل
        db_settings = get_email_settings_from_db()
        
        if not db_settings and not django_settings.EMAIL_HOST:
            return JsonResponse({
                "success": False,
                "message": "❌ لم يتم العثور على إعدادات الإيميل. يرجى ملء الإعدادات أولاً."
            })
        
        # عرض الإعدادات المستخدمة للتشخيص
        if db_settings:
            encryption = db_settings.get('email_encryption', 'tls')
            encryption_text = {
                'none': 'بدون تشفير',
                'tls': 'TLS',
                'ssl': 'SSL'
            }.get(encryption, encryption)
            
            current_settings = db_settings
        else:
            use_tls = getattr(django_settings, 'EMAIL_USE_TLS', False)
            use_ssl = getattr(django_settings, 'EMAIL_USE_SSL', False)
            if use_ssl:
                encryption_text = 'SSL'
            elif use_tls:
                encryption_text = 'TLS'
            else:
                encryption_text = 'بدون تشفير'
                
            current_settings = {
                'email_host': django_settings.EMAIL_HOST,
                'email_port': django_settings.EMAIL_PORT,
                'email_username': django_settings.EMAIL_HOST_USER,
                'email_from': django_settings.DEFAULT_FROM_EMAIL,
            }
        
        settings_info = f"""
📧 الإعدادات المستخدمة:
- Host: {current_settings.get('email_host', 'غير محدد')}
- Port: {current_settings.get('email_port', 'غير محدد')}
- Username: {current_settings.get('email_username', 'غير محدد')}
- التشفير: {encryption_text}
- From: {current_settings.get('email_from', 'غير محدد')}
- المصدر: {'قاعدة البيانات' if db_settings else '.env'}
        """
        
        # إرسال إيميل تجريبي
        subject = "اختبار إعدادات الإيميل - Corporate ERP"
        message = f"""
مرحباً،

هذا إيميل تجريبي من نظام Corporate ERP للتأكد من صحة إعدادات الإيميل.

إذا وصلك هذا الإيميل، فهذا يعني أن الإعدادات تعمل بشكل صحيح! ✅

تم الإرسال بواسطة: {request.user.get_full_name() or request.user.username}
التاريخ: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}

---
فريق Corporate ERP
        """
        
        html_message = f"""
        <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
            <h2 style="color: #0e3178;">اختبار إعدادات الإيميل</h2>
            <p>مرحباً،</p>
            <p>هذا إيميل تجريبي من نظام <strong>Corporate ERP</strong> للتأكد من صحة إعدادات الإيميل.</p>
            <div style="background-color: #dffcf0; border-right: 4px solid #22c55e; padding: 15px; margin: 20px 0; border-radius: 8px;">
                <strong style="color: #22c55e;">✓ نجح!</strong>
                <p style="margin: 10px 0 0;">إذا وصلك هذا الإيميل، فهذا يعني أن الإعدادات تعمل بشكل صحيح!</p>
            </div>
            <p><small>تم الإرسال بواسطة: {request.user.get_full_name() or request.user.username}</small></p>
            <p><small>التاريخ: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
            <hr>
            <p style="color: #6b7280; font-size: 12px;">فريق Corporate ERP</p>
        </div>
        """
        
        # محاولة الإرسال مع التقاط الأخطاء التفصيلية
        try:
            result = send_email(
                subject=subject,
                message=message,
                html_message=html_message,
                recipient_list=[test_email],
                fail_silently=False
            )
            
            if result:
                return JsonResponse({
                    "success": True,
                    "message": f"✅ تم إرسال إيميل تجريبي بنجاح إلى {test_email}. تحقق من صندوق الوارد (أو Spam).\n\n{settings_info}"
                })
            else:
                return JsonResponse({
                    "success": False,
                    "message": "❌ فشل إرسال الإيميل. يرجى التحقق من الإعدادات في قاعدة البيانات أو .env"
                })
        except Exception as email_error:
            # التقاط أخطاء الإرسال التفصيلية
            error_details = str(email_error)
            
            # رسائل خطأ مفهومة حسب نوع الخطأ
            if "authentication" in error_details.lower() or "username" in error_details.lower():
                error_msg = "❌ خطأ في المصادقة: اسم المستخدم أو كلمة المرور غير صحيحة"
            elif "connection" in error_details.lower() or "refused" in error_details.lower():
                error_msg = "❌ خطأ في الاتصال: تحقق من SMTP Host و Port"
            elif "tls" in error_details.lower() or "ssl" in error_details.lower():
                error_msg = "❌ خطأ في TLS/SSL: تحقق من إعدادات التشفير"
            elif "timeout" in error_details.lower():
                error_msg = "❌ انتهت مهلة الاتصال: الخادم لا يستجيب"
            else:
                error_msg = f"❌ خطأ: {error_details}"
            
            return JsonResponse({
                "success": False,
                "message": error_msg
            })
            
    except Exception as e:
        return JsonResponse({
            "success": False,
            "message": f"❌ حدث خطأ غير متوقع: {str(e)}"
        })


@login_required
@require_http_methods(["GET"])
def get_system_info(request):
    """
    API endpoint لجلب معلومات النظام المحدثة
    """
    try:
        disk_usage = psutil.disk_usage('/')
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        
        return JsonResponse({
            "success": True,
            "data": {
                "cpu": f"{cpu_percent}%",
                "memory": f"{memory.percent}%",
                "disk": f"{disk_usage.percent}%",
                "memory_used": f"{memory.used / (1024**3):.1f} GB",
                "memory_total": f"{memory.total / (1024**3):.1f} GB",
                "disk_used": f"{disk_usage.used / (1024**3):.1f} GB",
                "disk_total": f"{disk_usage.total / (1024**3):.1f} GB",
            }
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "message": str(e)
        })


@login_required
@require_POST
def upload_company_logo(request):
    """
    API endpoint لرفع شعارات الشركة عبر AJAX
    يدعم: company_logo, company_logo_light, company_logo_mini
    """
    try:
        # التحقق من الصلاحيات
        if not request.user.is_admin and not request.user.is_superuser:
            return JsonResponse({
                "success": False,
                "message": "ليس لديك صلاحية لتنفيذ هذا الإجراء"
            }, status=403)
        
        # تحديد نوع الشعار
        logo_types = ['company_logo', 'company_logo_light', 'company_logo_mini']
        logo_type = None
        logo_file = None
        
        for lt in logo_types:
            if lt in request.FILES:
                logo_type = lt
                logo_file = request.FILES[lt]
                break
        
        # التحقق من وجود الملف
        if not logo_file or not logo_type:
            return JsonResponse({
                "success": False,
                "message": "لم يتم اختيار ملف"
            }, status=400)
        
        # التحقق من نوع الملف
        allowed_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/svg+xml']
        if logo_file.content_type not in allowed_types:
            return JsonResponse({
                "success": False,
                "message": "نوع الملف غير مدعوم. يرجى استخدام PNG, JPG, أو SVG"
            }, status=400)
        
        # التحقق من حجم الملف (2MB)
        if logo_file.size > 2 * 1024 * 1024:
            return JsonResponse({
                "success": False,
                "message": "حجم الملف كبير جداً. الحد الأقصى 2 ميجابايت"
            }, status=400)
        
        # حذف الشعار القديم إن وُجد
        old_logo_setting = SystemSetting.objects.filter(key=logo_type).first()
        if old_logo_setting and old_logo_setting.value:
            old_logo_path = old_logo_setting.value
            if default_storage.exists(old_logo_path):
                default_storage.delete(old_logo_path)
        
        # حفظ الشعار الجديد
        file_name = f"{logo_type}_{logo_file.name}"
        file_path = os.path.join('company', file_name)
        saved_path = default_storage.save(file_path, logo_file)
        
        # حفظ المسار في الإعدادات
        setting, created = SystemSetting.objects.get_or_create(
            key=logo_type,
            defaults={
                'value': saved_path,
                'group': 'general',
                'data_type': 'string',
            }
        )
        if not created:
            setting.value = saved_path
            setting.save()
        
        # رسائل مخصصة حسب نوع الشعار
        messages_map = {
            'company_logo': 'تم رفع الشعار الأساسي بنجاح',
            'company_logo_light': 'تم رفع الشعار الفاتح بنجاح',
            'company_logo_mini': 'تم رفع الشعار المصغر بنجاح'
        }
        
        # إرجاع النتيجة
        return JsonResponse({
            "success": True,
            "message": messages_map.get(logo_type, "تم رفع الشعار بنجاح"),
            "logo_url": f"/media/{saved_path}",
            "logo_path": saved_path,
            "logo_type": logo_type
        })
        
    except Exception as e:
        logger.error(f"خطأ في رفع شعار الشركة: {str(e)}")
        return JsonResponse({
            "success": False,
            "message": f"حدث خطأ أثناء رفع الشعار: {str(e)}"
        }, status=500)
