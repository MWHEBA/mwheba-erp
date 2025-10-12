"""
# واجهة برمجة التطبيقات (API) لتطبيق core
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _

from utils.throttling import SustainedRateThrottle, BurstRateThrottle
from sale.models import Sale
from purchase.models import Purchase
from client.models import Customer
from supplier.models import Supplier
from product.models import Product
from .models import DashboardStat, Notification


class DashboardStatsAPIView(APIView):
    """
    # واجهة برمجة التطبيق لعرض إحصائيات لوحة التحكم
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def get(self, request):
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        
        # إحصائيات المبيعات
        sales_this_month = Sale.objects.filter(date__gte=this_month_start).aggregate(
            count=Count('id'),
            total=Sum('total')
        )
        
        # إحصائيات المشتريات
        purchases_this_month = Purchase.objects.filter(date__gte=this_month_start).aggregate(
            count=Count('id'),
            total=Sum('total')
        )
        
        # إحصائيات العملاء والموردين والمنتجات
        customers_count = Customer.objects.filter(is_active=True).count()
        suppliers_count = Supplier.objects.filter(is_active=True).count()
        products_count = Product.objects.filter(is_active=True).count()
        
        # إعداد البيانات للاستجابة
        data = {
            'sales': {
                'this_month_count': sales_this_month['count'] or 0,
                'this_month_total': sales_this_month['total'] or 0,
            },
            'purchases': {
                'this_month_count': purchases_this_month['count'] or 0,
                'this_month_total': purchases_this_month['total'] or 0,
            },
            'counts': {
                'customers': customers_count,
                'suppliers': suppliers_count,
                'products': products_count,
            },
            'timestamp': timezone.now(),
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
            'status': 'healthy',
            'version': '1.0.0',
            'timestamp': timezone.now(),
            'uptime': '24 hours',  # يمكن استبدالها بقياس فعلي لوقت تشغيل النظام
        }
        
        return Response(data, status=status.HTTP_200_OK)


def get_dashboard_stats(request):
    """
    API لجلب إحصائيات لوحة التحكم
    """
    stats = {}
    
    try:
        # جلب الإحصائيات من قاعدة البيانات
        dashboard_stats = DashboardStat.objects.filter(is_active=True).order_by('order')
        
        for stat in dashboard_stats:
            stats[stat.key] = {
                'title': stat.title,
                'value': stat.value,
                'icon': stat.icon,
                'color': stat.color,
                'change': stat.change,
                'change_type': stat.change_type,
                'has_chart': stat.has_chart,
                'chart_data': stat.chart_data,
                'chart_type': stat.chart_type
            }
    except Exception as e:
        # في حال حدوث خطأ
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })
    
    return JsonResponse({
        'status': 'success',
        'stats': stats
    })

def get_recent_activity(request, days=7):
    """
    API لجلب نشاطات المستخدم الأخيرة
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({
            'status': 'error',
            'message': _('يجب تسجيل الدخول')
        })
    
    # جلب النشاطات
    activities = []
    
    # هنا سيتم استبدال هذا بالنموذج الفعلي للنشاطات
    # مثال افتراضي:
    recent_date = timezone.now()
    for i in range(5):
        activities.append({
            'title': f'نشاط {i+1}',
            'time': (recent_date - timedelta(hours=i*3)).isoformat(),
            'icon': 'fas fa-check-circle',
            'color': 'success'
        })
    
    return JsonResponse({
        'status': 'success',
        'activities': activities
    })

# API لإدارة الإشعارات

def mark_notification_read(request, notification_id):
    """
    API لتعليم إشعار كمقروء
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'message': _('يجب تسجيل الدخول')
        })
    
    # التحقق من طريقة الطلب
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': _('طريقة طلب غير صالحة')
        })
    
    try:
        # البحث عن الإشعار
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.is_read = True
        notification.save()
        
        return JsonResponse({
            'success': True,
            'message': _('تم تعليم الإشعار كمقروء'),
            'redirect_url': notification.link if hasattr(notification, 'link') else None
        })
    except Notification.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': _('الإشعار غير موجود')
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

def mark_all_notifications_read(request):
    """
    API لتعليم جميع الإشعارات كمقروءة
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'message': _('يجب تسجيل الدخول')
        })
    
    # التحقق من طريقة الطلب
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': _('طريقة طلب غير صالحة')
        })
    
    try:
        # تحديث جميع الإشعارات غير المقروءة للمستخدم
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        
        return JsonResponse({
            'success': True,
            'message': _('تم تعليم جميع الإشعارات كمقروءة')
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

def get_notifications_count(request):
    """
    API لجلب عدد الإشعارات غير المقروءة
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'message': _('يجب تسجيل الدخول')
        })
    
    try:
        # حساب عدد الإشعارات غير المقروءة
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        
        return JsonResponse({
            'success': True,
            'count': unread_count
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }) 