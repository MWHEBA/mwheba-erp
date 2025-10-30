from django.shortcuts import render, redirect
from django.db.models import Sum, Count, Avg, F, Q
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
import subprocess
import os
import sys

from sale.models import Sale
from purchase.models import Purchase
from client.models import Customer
from supplier.models import Supplier
from product.models import Product, Stock
from .models import SystemSetting, Notification
# تم حذف create_breadcrumb_item واستبدالها بـ dict مباشر


@login_required
def dashboard(request):
    """
    View for the main dashboard
    """
    # تجميع بيانات الإحصائيات

    # إحصائيات المبيعات اليوم
    sales_today = Sale.objects.filter(date=timezone.now().date())
    sales_today_count = sales_today.count()
    sales_today_total = sales_today.aggregate(total=Sum("total"))["total"] or 0

    # إحصائيات المشتريات اليوم
    purchases_today = Purchase.objects.filter(date=timezone.now().date())
    purchases_today_count = purchases_today.count()
    purchases_today_total = purchases_today.aggregate(total=Sum("total"))["total"] or 0

    # إحصائيات العملاء والمنتجات
    customers_count = Customer.objects.filter(is_active=True).count()
    products_count = Product.objects.filter(is_active=True).count()

    # أحدث المبيعات والمشتريات
    recent_sales = Sale.objects.order_by("-date", "-id")[:5]
    recent_purchases = Purchase.objects.order_by("-date", "-id")[:5]

    # المنتجات منخفضة المخزون
    stock_condition = Q(stocks__quantity__lt=F("min_stock")) | Q(stocks__quantity=0)
    low_stock_products = (
        Product.objects.filter(is_active=True).filter(stock_condition).distinct()[:5]
    )

    # المبيعات حسب طريقة الدفع
    sales_by_payment_method = (
        Sale.objects.values("payment_method")
        .annotate(count=Count("id"), total=Sum("total"))
        .order_by("-total")
    )

    context = {
        "sales_today": {"count": sales_today_count, "total": sales_today_total},
        "purchases_today": {
            "count": purchases_today_count,
            "total": purchases_today_total,
        },
        "customers_count": customers_count,
        "products_count": products_count,
        "recent_sales": recent_sales,
        "recent_purchases": recent_purchases,
        "low_stock_products": low_stock_products,
        "sales_by_payment_method": sales_by_payment_method,
        # إضافة متغيرات عنوان الصفحة
        "page_title": "لوحة التحكم",
        "page_icon": "fas fa-tachometer-alt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "active": True, "icon": "fas fa-home"}
        ],
    }

    return render(request, "core/dashboard.html", context)


@login_required
def company_settings(request):
    """
    عرض وتعديل إعدادات الشركة
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # معالجة حفظ الإعدادات عند POST
    if request.method == "POST":
        # قائمة الحقول المطلوب حفظها
        settings_fields = [
            "company_name",
            "company_address",
            "company_phone",
            "company_email",
            "company_tax_number",
            "company_website",
            "invoice_prefix",
            "default_currency",
            "default_tax_rate",
            "invoice_notes",
        ]
        
        # حفظ كل إعداد
        for field in settings_fields:
            value = request.POST.get(field, "")
            if value:  # فقط إذا كانت القيمة موجودة
                setting, created = SystemSetting.objects.get_or_create(
                    key=field,
                    defaults={
                        "value": value,
                        "group": "general",
                        "data_type": "string",
                    }
                )
                if not created:
                    setting.value = value
                    setting.save()
        
        messages.success(request, "تم حفظ إعدادات الشركة بنجاح")
        return redirect("core:company_settings")

    # الحصول على إعدادات الشركة من قاعدة البيانات
    company_settings_list = SystemSetting.objects.filter(group="general")

    # تحويل الإعدادات إلى قاموس لتسهيل الوصول إليها في القالب
    settings_dict = {setting.key: setting.value for setting in company_settings_list}

    context = {
        "title": "إعدادات الشركة",
        "page_title": "إعدادات الشركة",
        "page_icon": "fas fa-building",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإعدادات", "url": "#", "icon": "fas fa-cogs"},
            {"title": "إعدادات الشركة", "active": True},
        ],
        "company_settings": company_settings_list,  # للتوافق مع الكود القديم
        "company_name": settings_dict.get("company_name", ""),
        "company_address": settings_dict.get("company_address", ""),
        "company_phone": settings_dict.get("company_phone", ""),
        "company_email": settings_dict.get("company_email", ""),
        "company_tax_number": settings_dict.get("company_tax_number", ""),
        "company_website": settings_dict.get("company_website", ""),
        "company_logo": settings_dict.get("company_logo", ""),
        "invoice_prefix": settings_dict.get("invoice_prefix", "INV-"),
        "default_currency": settings_dict.get("default_currency", "ج.م"),
        "default_tax_rate": settings_dict.get("default_tax_rate", "14"),
        "invoice_notes": settings_dict.get("invoice_notes", ""),
        "active_menu": "settings",
    }

    return render(request, "core/company_settings.html", context)


@login_required
def system_settings(request):
    """
    عرض وتعديل إعدادات النظام
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # الحصول على إعدادات النظام من قاعدة البيانات
    system_settings_list = SystemSetting.objects.filter(group="system")

    # تحويل الإعدادات إلى قاموس لتسهيل الوصول إليها في القالب
    settings_dict = {setting.key: setting.value for setting in system_settings_list}

    context = {
        "title": "إعدادات النظام",
        "page_title": "إعدادات النظام",
        "page_icon": "fas fa-sliders-h",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإعدادات", "url": "#", "icon": "fas fa-cogs"},
            {"title": "إعدادات النظام", "active": True},
        ],
        "system_settings": system_settings_list,  # للتوافق مع الكود القديم
        "language": settings_dict.get("language", "ar"),
        "timezone": settings_dict.get("timezone", "Africa/Cairo"),
        "date_format": settings_dict.get("date_format", "d/m/Y"),
        "maintenance_mode": settings_dict.get("maintenance_mode", "false"),
        "allow_registration": settings_dict.get("allow_registration", "false"),
        "session_timeout": settings_dict.get("session_timeout", "1440"),
        "backup_frequency": settings_dict.get("backup_frequency", "daily"),
        "enable_two_factor": settings_dict.get("enable_two_factor", "false"),
        "password_policy": settings_dict.get("password_policy", "medium"),
        "failed_login_attempts": settings_dict.get("failed_login_attempts", "5"),
        "account_lockout_time": settings_dict.get("account_lockout_time", "30"),
        "active_menu": "settings",
    }

    return render(request, "core/system_settings.html", context)


@login_required
def notifications_list(request):
    """
    عرض قائمة كاملة بجميع الإشعارات للمستخدم الحالي
    """
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return redirect("login")

    # جلب جميع الإشعارات للمستخدم
    notifications = Notification.objects.filter(user=request.user).order_by(
        "-created_at"
    )

    # تقسيم الإشعارات لغير مقروءة ومقروءة
    unread_notifications = notifications.filter(is_read=False)
    read_notifications = notifications.filter(is_read=True)

    # عمل تعليم الكل كمقروء إذا كان هناك طلب POST
    if request.method == "POST" and "mark_all_read" in request.POST:
        unread_notifications.update(is_read=True)
        messages.success(request, "تم تعليم جميع الإشعارات كمقروءة بنجاح.")
        return redirect("core:notifications_list")

    # تحديد أزرار الإجراءات بناءً على وجود إشعارات غير مقروءة
    action_buttons = None
    if unread_notifications.count() > 0:
        action_buttons = [
            {
                "text": "تعليم الكل كمقروء",
                "icon": "fa-check-double",
                "class": "btn-outline-primary",
                "url": "#",
                "form_id": "mark_all_read_form",
            }
        ]

    context = {
        "page_title": "إشعاراتي",
        "page_icon": "fas fa-bell",
        "unread_notifications": unread_notifications,
        "read_notifications": read_notifications,
        "total_count": notifications.count(),
        "unread_count": unread_notifications.count(),
        "action_buttons": action_buttons,
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
                "active": False
            },
            {
                "title": "إشعاراتي",
                "icon": "fas fa-bell",
                "active": True
            },
        ],
    }

    return render(request, "core/notifications_list.html", context)


@login_required
def system_reset(request):
    """
    إعادة تهيئة النظام - استعادة ضبط المصنع
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة الطلب غير صحيحة'})
    
    # التحقق من صلاحيات المدير
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'ليس لديك صلاحية لتنفيذ هذا الإجراء'})
    
    try:
        # تحديد السكريبت
        base_dir = settings.BASE_DIR
        script_name = 'setup_development.py'
        script_path = os.path.join(base_dir, script_name)
        
        # التحقق من وجود السكريبت
        if not os.path.exists(script_path):
            return JsonResponse({
                'success': False, 
                'message': f'لم يتم العثور على السكريبت: {script_name}'
            })
        
        # تشغيل السكريبت في الخلفية
        python_executable = sys.executable
        
        # تشغيل السكريبت في الخلفية بدون انتظار
        import time
        import logging
        
        logger = logging.getLogger(__name__)
        logger.info(f"🔄 بدء تشغيل سكريبت إعادة التهيئة: {script_name}")
        
        # إنشاء ملف log لتتبع العملية
        log_file = os.path.join(base_dir, 'system_reset.log')
        
        if os.name == 'nt':  # Windows
            # على Windows، نستخدم CREATE_NEW_PROCESS_GROUP فقط (بدون DETACHED)
            # عشان نقدر نشوف الـ output في terminal جديد
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NO_WINDOW = 0x08000000
            
            # فتح ملف log للكتابة
            log_handle = open(log_file, 'w', encoding='utf-8')
            
            process = subprocess.Popen(
                [python_executable, script_path, '--auto'],
                cwd=base_dir,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=CREATE_NEW_PROCESS_GROUP
            )
            
            logger.info(f"✅ تم بدء العملية - PID: {process.pid}")
            logger.info(f"📝 يمكنك متابعة التقدم في: {log_file}")
            
        else:  # Linux/Mac
            log_handle = open(log_file, 'w', encoding='utf-8')
            
            process = subprocess.Popen(
                [python_executable, script_path, '--auto'],
                cwd=base_dir,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True
            )
            
            logger.info(f"✅ تم بدء العملية - PID: {process.pid}")
        
        # إرجاع استجابة فورية بدون انتظار
        return JsonResponse({
            'success': True,
            'message': 'تم بدء عملية إعادة التهيئة',
            'details': 'العملية تعمل في الخلفية. سيتم إعادة تشغيل الخادم تلقائياً عند الانتهاء.',
            'log_file': 'system_reset.log',
            'pid': process.pid
        })
                
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء تشغيل السكريبت: {str(e)}'
        })
