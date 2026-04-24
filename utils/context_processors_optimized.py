"""
Utils Context Processors محسّنة للأداء
✅ إزالة الاستعلامات الثقيلة وتقليل العمليات
"""
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


def common_variables(request):
    """
    إضافة متغيرات مشتركة للاستخدام في جميع القوالب
    ✅ تحسين: إزالة counts الثقيلة - نقلها لصفحة Dashboard فقط
    """
    # متغيرات ثابتة - لا تحتاج cache
    current_date = timezone.now()
    
    # بيانات المؤسسة - يمكن cache لمدة طويلة
    cache_key = 'company_info_v1'
    company_info = cache.get(cache_key)
    
    if company_info is None:
        company_info = {
            'name': "موهبة ERP",
            'slogan': "نظام إدارة المبيعات والمخزون",
            'logo': settings.STATIC_URL + "img/logo.png",
            'address': "القاهرة، مصر",
            'phone': "+201234567890",
            'email': "info@mwheba-erp.com",
            'website': "www.mwheba-erp.com",
        }
        # Cache لمدة ساعة
        cache.set(cache_key, company_info, 3600)
    
    # ❌ إزالة main_models counts - ثقيلة جداً
    # ✅ بدلاً منها، استخدم AJAX في Dashboard فقط
    
    return {
        "current_date": current_date,
        "current_year": current_date.year,
        "currency_symbol": "ج.م",
        "company_name": company_info['name'],
        "company_slogan": company_info['slogan'],
        "company_logo": company_info['logo'],
        "company_address": company_info['address'],
        "company_phone": company_info['phone'],
        "company_email": company_info['email'],
        "company_website": company_info['website'],
        "debug": settings.DEBUG,
    }


def user_permissions(request):
    """
    إضافة صلاحيات المستخدم للاستخدام في القوالب
    ⚠️ هذا context processor معطل حالياً في settings.py
    ✅ استخدم {% if perms.app.permission %} مباشرة في القوالب
    """
    if not request.user.is_authenticated:
        return {"user_perms": {}}

    # Cache صلاحيات المستخدم
    cache_key = f'user_perms_{request.user.id}_v1'
    user_perms = cache.get(cache_key)
    
    if user_perms is None:
        user = request.user
        user_perms = {
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
        }
        
        # Cache لمدة 5 دقائق
        cache.set(cache_key, user_perms, 300)

    return {"user_perms": user_perms}


def breadcrumb_context(request):
    """
    توفير سياق شريط التنقل (Breadcrumb) للقوالب
    ⚠️ هذا context processor معطل حالياً في settings.py
    ✅ أفضل: إنشاء breadcrumb يدوياً في كل view حسب الحاجة
    """
    # لا حاجة لإنشاء breadcrumb للصفحة الرئيسية
    if request.path in ['/', '/login/', '/logout/']:
        return {"generated_breadcrumb_items": []}

    # ❌ إزالة المعالجة التلقائية - ثقيلة
    # ✅ بدلاً منها، أضف breadcrumb_items في context كل view
    
    return {"generated_breadcrumb_items": []}


# ✅ دالة مساعدة لـ Dashboard فقط
def get_dashboard_counts():
    """
    جلب الإحصائيات للـ Dashboard فقط
    استخدمها في dashboard view بدلاً من context processor
    """
    from django.apps import apps
    
    cache_key = 'dashboard_counts_v1'
    counts = cache.get(cache_key)
    
    if counts is None:
        counts = {}
        
        try:
            # استخدام aggregate بدلاً من count() - أسرع
            from django.db.models import Count
            
            if apps.is_installed('product'):
                Product = apps.get_model('product', 'Product')
                counts['products'] = Product.objects.aggregate(
                    total=Count('id')
                )['total']
            
            if apps.is_installed('client'):
                Customer = apps.get_model('client', 'Customer')
                counts['customers'] = Customer.objects.filter(
                    is_active=True
                ).aggregate(total=Count('id'))['total']
            
            if apps.is_installed('supplier'):
                Supplier = apps.get_model('supplier', 'Supplier')
                counts['suppliers'] = Supplier.objects.aggregate(
                    total=Count('id')
                )['total']
            
            if apps.is_installed('sale'):
                Sale = apps.get_model('sale', 'Sale')
                counts['sales'] = Sale.objects.aggregate(
                    total=Count('id')
                )['total']
            
            if apps.is_installed('purchase'):
                Purchase = apps.get_model('purchase', 'Purchase')
                counts['purchases'] = Purchase.objects.aggregate(
                    total=Count('id')
                )['total']
                
        except Exception as e:
            logger.error(f"Error getting dashboard counts: {e}")
        
        # Cache لمدة 5 دقائق
        cache.set(cache_key, counts, 300)
    
    return counts
