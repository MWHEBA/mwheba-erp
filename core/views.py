from django.shortcuts import render, redirect
from django.db.models import Sum, Count, Avg, F, Q
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse
from django.contrib import messages

from sale.models import Sale
from purchase.models import Purchase
from client.models import Customer
from supplier.models import Supplier
from product.models import Product, Stock
from .models import SystemSetting, Notification
from utils import create_breadcrumb_item


@login_required
def dashboard(request):
    """
    View for the main dashboard
    """
    # تجميع بيانات الإحصائيات
    
    # إحصائيات المبيعات اليوم
    sales_today = Sale.objects.filter(date=timezone.now().date())
    sales_today_count = sales_today.count()
    sales_today_total = sales_today.aggregate(total=Sum('total'))['total'] or 0
    
    # إحصائيات المشتريات اليوم
    purchases_today = Purchase.objects.filter(date=timezone.now().date())
    purchases_today_count = purchases_today.count()
    purchases_today_total = purchases_today.aggregate(total=Sum('total'))['total'] or 0
    
    # إحصائيات العملاء والمنتجات
    customers_count = Customer.objects.filter(is_active=True).count()
    products_count = Product.objects.filter(is_active=True).count()
    
    # أحدث المبيعات والمشتريات
    recent_sales = Sale.objects.order_by('-date', '-id')[:5]
    recent_purchases = Purchase.objects.order_by('-date', '-id')[:5]
    
    # المنتجات منخفضة المخزون
    stock_condition = Q(stocks__quantity__lt=F('min_stock')) | Q(stocks__quantity=0)
    low_stock_products = Product.objects.filter(
        is_active=True
    ).filter(stock_condition).distinct()[:5]
    
    # المبيعات حسب طريقة الدفع
    sales_by_payment_method = Sale.objects.values('payment_method').annotate(
        count=Count('id'),
        total=Sum('total')
    ).order_by('-total')
    
    context = {
        'sales_today': {
            'count': sales_today_count,
            'total': sales_today_total
        },
        'purchases_today': {
            'count': purchases_today_count,
            'total': purchases_today_total
        },
        'customers_count': customers_count,
        'products_count': products_count,
        'recent_sales': recent_sales,
        'recent_purchases': recent_purchases,
        'low_stock_products': low_stock_products,
        'sales_by_payment_method': sales_by_payment_method,
        # إضافة متغيرات عنوان الصفحة
        'page_title': 'لوحة التحكم',
        'page_icon': 'fas fa-tachometer-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'active': True, 'icon': 'fas fa-home'}
        ]
    }
    
    return render(request, 'core/dashboard.html', context)


@login_required
def company_settings(request):
    """
    عرض وتعديل إعدادات الشركة
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(request, 'core/permission_denied.html', {
            'title': 'غير مصرح',
            'message': 'ليس لديك صلاحية للوصول إلى هذه الصفحة'
        })
    
    # الحصول على إعدادات الشركة من قاعدة البيانات
    company_settings_list = SystemSetting.objects.filter(group='general')
    
    # تحويل الإعدادات إلى قاموس لتسهيل الوصول إليها في القالب
    settings_dict = {setting.key: setting.value for setting in company_settings_list}
    
    context = {
        'title': 'إعدادات الشركة',
        'page_title': 'إعدادات الشركة',
        'page_icon': 'fas fa-building',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإعدادات', 'url': '#', 'icon': 'fas fa-cogs'},
            {'title': 'إعدادات الشركة', 'active': True}
        ],
        'company_settings': company_settings_list,  # للتوافق مع الكود القديم
        'company_name': settings_dict.get('company_name', ''),
        'company_address': settings_dict.get('company_address', ''),
        'company_phone': settings_dict.get('company_phone', ''),
        'company_email': settings_dict.get('company_email', ''),
        'company_tax_number': settings_dict.get('company_tax_number', ''),
        'company_website': settings_dict.get('company_website', ''),
        'company_logo': settings_dict.get('company_logo', ''),
        'invoice_prefix': settings_dict.get('invoice_prefix', 'INV-'),
        'default_currency': settings_dict.get('default_currency', 'ج.م'),
        'default_tax_rate': settings_dict.get('default_tax_rate', '14'),
        'invoice_notes': settings_dict.get('invoice_notes', ''),
        'active_menu': 'settings',
    }
    
    return render(request, 'core/company_settings.html', context)


@login_required
def system_settings(request):
    """
    عرض وتعديل إعدادات النظام
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(request, 'core/permission_denied.html', {
            'title': 'غير مصرح',
            'message': 'ليس لديك صلاحية للوصول إلى هذه الصفحة'
        })
    
    # الحصول على إعدادات النظام من قاعدة البيانات
    system_settings_list = SystemSetting.objects.filter(group='system')
    
    # تحويل الإعدادات إلى قاموس لتسهيل الوصول إليها في القالب
    settings_dict = {setting.key: setting.value for setting in system_settings_list}
    
    context = {
        'title': 'إعدادات النظام',
        'page_title': 'إعدادات النظام',
        'page_icon': 'fas fa-sliders-h',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإعدادات', 'url': '#', 'icon': 'fas fa-cogs'},
            {'title': 'إعدادات النظام', 'active': True}
        ],
        'system_settings': system_settings_list,  # للتوافق مع الكود القديم
        'language': settings_dict.get('language', 'ar'),
        'timezone': settings_dict.get('timezone', 'Africa/Cairo'),
        'date_format': settings_dict.get('date_format', 'd/m/Y'),
        'maintenance_mode': settings_dict.get('maintenance_mode', 'false'),
        'allow_registration': settings_dict.get('allow_registration', 'false'),
        'session_timeout': settings_dict.get('session_timeout', '1440'),
        'backup_frequency': settings_dict.get('backup_frequency', 'daily'),
        'enable_two_factor': settings_dict.get('enable_two_factor', 'false'),
        'password_policy': settings_dict.get('password_policy', 'medium'),
        'failed_login_attempts': settings_dict.get('failed_login_attempts', '5'),
        'account_lockout_time': settings_dict.get('account_lockout_time', '30'),
        'active_menu': 'settings',
    }
    
    return render(request, 'core/system_settings.html', context)


@login_required
def notifications_list(request):
    """
    عرض قائمة كاملة بجميع الإشعارات للمستخدم الحالي
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return redirect('login')
        
    # جلب جميع الإشعارات للمستخدم
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')
    
    # تقسيم الإشعارات لغير مقروءة ومقروءة
    unread_notifications = notifications.filter(is_read=False)
    read_notifications = notifications.filter(is_read=True)
    
    # عمل تعليم الكل كمقروء إذا كان هناك طلب POST
    if request.method == 'POST' and 'mark_all_read' in request.POST:
        unread_notifications.update(is_read=True)
        messages.success(request, 'تم تعليم جميع الإشعارات كمقروءة بنجاح.')
        return redirect('core:notifications_list')
    
    # تحديد أزرار الإجراءات بناءً على وجود إشعارات غير مقروءة
    action_buttons = None
    if unread_notifications.count() > 0:
        action_buttons = [
            {
                'text': 'تعليم الكل كمقروء',
                'icon': 'fa-check-double',
                'class': 'btn-outline-primary',
                'url': '#',
                'form_id': 'mark_all_read_form'
            }
        ]
    
    context = {
        'page_title': 'إشعاراتي',
        'page_icon': 'fas fa-bell',
        'unread_notifications': unread_notifications,
        'read_notifications': read_notifications,
        'total_count': notifications.count(),
        'unread_count': unread_notifications.count(),
        'action_buttons': action_buttons,
        'breadcrumb_items': [
            create_breadcrumb_item('الرئيسية', reverse('core:dashboard'), 'fas fa-home'),
            create_breadcrumb_item('إشعاراتي', active=True, icon='fas fa-bell'),
        ],
    }
    
    return render(request, 'core/notifications_list.html', context) 