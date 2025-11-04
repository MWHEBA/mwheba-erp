from django.shortcuts import render, redirect
from django.db.models import Sum, Count, Avg, F, Q
from django.db.models.functions import TruncMonth
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
import json

from sale.models import Sale
from purchase.models import Purchase
from client.models import Customer
from supplier.models import Supplier
from product.models import Product, Stock
from .models import SystemSetting, Notification, NotificationPreference
from .forms import NotificationSettingsForm
# تم حذف create_breadcrumb_item واستبدالها بـ dict مباشر


@login_required
def dashboard(request):
    """
    View for the main dashboard
    """
    # تجميع بيانات الإحصائيات
    now = timezone.now()
    current_year = now.year
    current_month = now.month

    # إحصائيات المبيعات الشهر الحالي
    sales_today = Sale.objects.filter(date__month=current_month, date__year=current_year)
    sales_today_count = sales_today.count()
    sales_today_total = sales_today.aggregate(total=Sum("total"))["total"] or 0

    # إحصائيات المشتريات الشهر الحالي
    purchases_today = Purchase.objects.filter(date__month=current_month, date__year=current_year)
    purchases_today_count = purchases_today.count()
    purchases_today_total = purchases_today.aggregate(total=Sum("total"))["total"] or 0

    # إحصائيات العملاء والمنتجات
    customers_count = Customer.objects.filter(is_active=True).count()
    products_count = Product.objects.filter(is_active=True).count()

    # أحدث المبيعات والمشتريات
    recent_sales = Sale.objects.select_related('customer').order_by("-date", "-id")[:5]
    recent_purchases = Purchase.objects.select_related('supplier').order_by("-date", "-id")[:5]

    # المنتجات منخفضة المخزون (فقط المنتجات التي الكمية أقل من الحد الأدنى)
    stock_condition = Q(stocks__quantity__lt=F("min_stock"))
    low_stock_products = (
        Product.objects.filter(is_active=True).filter(stock_condition).distinct()[:5]
    )

    # إحصائيات الشهر الحالي
    sales_month = Sale.objects.filter(
        date__month=current_month,
        date__year=current_year
    ).aggregate(
        total=Sum('total'),
        count=Count('id')
    )
    
    purchases_month = Purchase.objects.filter(
        date__month=current_month,
        date__year=current_year
    ).aggregate(
        total=Sum('total'),
        count=Count('id')
    )
    
    # صافي الربح (تقريبي)
    profit_month = (sales_month['total'] or 0) - (purchases_month['total'] or 0)

    # ديون العملاء والموردين
    # ديون العملاء = الرصيد الموجب فقط (العملاء اللي عليهم فلوس)
    customer_debts = Customer.objects.filter(balance__gt=0).aggregate(
        total=Sum('balance')
    )['total'] or 0
    
    # ديون الموردين = الرصيد الموجب فقط (الموردين اللي إحنا مديونين ليهم)
    supplier_debts = Supplier.objects.filter(balance__gt=0).aggregate(
        total=Sum('balance')
    )['total'] or 0

    # بيانات المبيعات والمشتريات الشهرية للرسم البياني
    sales_by_month = Sale.objects.filter(
        date__year=current_year
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        total=Sum('total')
    ).order_by('month')
    
    purchases_by_month = Purchase.objects.filter(
        date__year=current_year
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        total=Sum('total')
    ).order_by('month')
    
    # تحويل البيانات لـ JSON للرسم البياني
    months_ar = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 
                 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
    
    sales_data = [0] * 12
    for item in sales_by_month:
        month_index = item['month'].month - 1
        sales_data[month_index] = float(item['total'] or 0)
    
    purchases_data = [0] * 12
    for item in purchases_by_month:
        month_index = item['month'].month - 1
        purchases_data[month_index] = float(item['total'] or 0)
    
    # بيانات اليوم (آخر 7 ساعات)
    from datetime import datetime, timedelta
    today_start = now.replace(hour=8, minute=0, second=0, microsecond=0)
    sales_by_hour = []
    purchases_by_hour = []
    for i in range(7):
        hour_start = today_start + timedelta(hours=i*2)
        hour_end = hour_start + timedelta(hours=2)
        sales_hour = Sale.objects.filter(date=now.date(), created_at__gte=hour_start, created_at__lt=hour_end).aggregate(total=Sum('total'))['total'] or 0
        purchases_hour = Purchase.objects.filter(date=now.date(), created_at__gte=hour_start, created_at__lt=hour_end).aggregate(total=Sum('total'))['total'] or 0
        sales_by_hour.append(float(sales_hour))
        purchases_by_hour.append(float(purchases_hour))
    
    # بيانات الأسبوع (آخر 7 أيام)
    week_start = now.date() - timedelta(days=6)
    sales_by_day = []
    purchases_by_day = []
    days_ar = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        sales_day = Sale.objects.filter(date=day).aggregate(total=Sum('total'))['total'] or 0
        purchases_day = Purchase.objects.filter(date=day).aggregate(total=Sum('total'))['total'] or 0
        sales_by_day.append(float(sales_day))
        purchases_by_day.append(float(purchases_day))
        days_ar.append(['السبت', 'الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة'][day.weekday()])
    
    # بيانات الشهر (كل يوم من أيام الشهر الحالي)
    from calendar import monthrange
    days_in_month = monthrange(current_year, current_month)[1]
    
    sales_by_week = []
    purchases_by_week = []
    week_labels = []
    
    # تقسيم الشهر إلى 4 أجزاء متساوية تقريباً
    days_per_part = days_in_month // 4
    
    for i in range(4):
        start_day = i * days_per_part + 1
        if i == 3:  # الجزء الأخير يأخذ باقي الأيام
            end_day = days_in_month
        else:
            end_day = (i + 1) * days_per_part
        
        week_start_date = now.date().replace(day=start_day)
        week_end_date = now.date().replace(day=end_day)
        
        sales_week = Sale.objects.filter(date__gte=week_start_date, date__lte=week_end_date).aggregate(total=Sum('total'))['total'] or 0
        purchases_week = Purchase.objects.filter(date__gte=week_start_date, date__lte=week_end_date).aggregate(total=Sum('total'))['total'] or 0
        
        sales_by_week.append(float(sales_week))
        purchases_by_week.append(float(purchases_week))
        week_labels.append(f"{start_day}-{end_day} {months_ar[current_month-1]}")
    
    # أفضل 5 منتجات مبيعاً
    from sale.models import SaleItem
    top_products = SaleItem.objects.select_related('product').values('product__name').annotate(
        total_sales=Sum(F('quantity') * F('unit_price'))
    ).order_by('-total_sales')[:5]
    
    top_products_labels = [item['product__name'] or 'منتج غير معروف' for item in top_products]
    top_products_data = [float(item['total_sales'] or 0) for item in top_products]
    
    # أفضل 5 عملاء
    top_customers = Sale.objects.select_related('customer').values('customer__name').annotate(
        total_sales=Sum('total')
    ).order_by('-total_sales')[:5]
    
    top_customers_labels = [item['customer__name'] or 'عميل غير معروف' for item in top_customers]
    top_customers_data = [float(item['total_sales'] or 0) for item in top_customers]

    # إعدادات النظام
    from core.models import SystemSetting
    light_logo = SystemSetting.get_light_logo()
    site_name = SystemSetting.get_site_name()
    
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
        
        # إعدادات النظام
        "light_logo": light_logo,
        "site_name": site_name,
        
        # إحصائيات الشهر
        "sales_month": sales_month,
        "purchases_month": purchases_month,
        "profit_month": profit_month,
        
        # الديون
        "customer_debts": customer_debts,
        "supplier_debts": supplier_debts,
        
        # بيانات الرسم البياني
        "chart_months": json.dumps(months_ar),
        "chart_sales_data": json.dumps(sales_data),
        "chart_purchases_data": json.dumps(purchases_data),
        
        # بيانات اليوم والأسبوع والشهر
        "chart_sales_by_hour": json.dumps(sales_by_hour),
        "chart_purchases_by_hour": json.dumps(purchases_by_hour),
        "chart_sales_by_day": json.dumps(sales_by_day),
        "chart_purchases_by_day": json.dumps(purchases_by_day),
        "chart_days": json.dumps(days_ar),
        "chart_sales_by_week": json.dumps(sales_by_week),
        "chart_purchases_by_week": json.dumps(purchases_by_week),
        "chart_week_labels": json.dumps(week_labels),
        
        # أفضل المنتجات والعملاء
        "top_products_labels": json.dumps(top_products_labels),
        "top_products_data": json.dumps(top_products_data),
        "top_customers_labels": json.dumps(top_customers_labels),
        "top_customers_data": json.dumps(top_customers_data),
        
        # عنوان الصفحة
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
            # معلومات أساسية
            "company_name",
            "company_name_en",
            "company_tax_number",
            "company_commercial_register",
            "company_country",
            "company_city",
            "company_state",
            # بيانات الاتصال
            "company_address",
            "company_phone",
            "company_mobile",
            "company_email",
            "company_website",
            "company_whatsapp",
            "company_working_hours",
            # المعلومات البنكية
            "company_bank_name",
            "company_bank_account",
            "company_bank_iban",
            "company_bank_swift",
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
        "company_settings": company_settings_list,
        # معلومات أساسية
        "company_name": settings_dict.get("company_name", ""),
        "company_name_en": settings_dict.get("company_name_en", ""),
        "company_tax_number": settings_dict.get("company_tax_number", ""),
        "company_commercial_register": settings_dict.get("company_commercial_register", ""),
        "company_country": settings_dict.get("company_country", "مصر"),
        "company_city": settings_dict.get("company_city", ""),
        "company_state": settings_dict.get("company_state", ""),
        # بيانات الاتصال
        "company_address": settings_dict.get("company_address", ""),
        "company_phone": settings_dict.get("company_phone", ""),
        "company_mobile": settings_dict.get("company_mobile", ""),
        "company_email": settings_dict.get("company_email", ""),
        "company_website": settings_dict.get("company_website", ""),
        "company_whatsapp": settings_dict.get("company_whatsapp", ""),
        "company_working_hours": settings_dict.get("company_working_hours", ""),
        # المعلومات البنكية
        "company_bank_name": settings_dict.get("company_bank_name", ""),
        "company_bank_account": settings_dict.get("company_bank_account", ""),
        "company_bank_iban": settings_dict.get("company_bank_iban", ""),
        "company_bank_swift": settings_dict.get("company_bank_swift", ""),
        # الشعارات
        "company_logo": settings_dict.get("company_logo", ""),
        "company_logo_light": settings_dict.get("company_logo_light", ""),
        "company_logo_mini": settings_dict.get("company_logo_mini", ""),
        "active_menu": "settings",
    }

    return render(request, "core/company_settings.html", context)


@login_required
def system_settings(request):
    """
    عرض وتعديل إعدادات النظام
    """
    from .forms import SystemSettingsForm
    import platform
    
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # الحصول على إعدادات النظام من قاعدة البيانات
    system_settings_list = SystemSetting.objects.filter(group="system")
    settings_dict = {setting.key: setting.value for setting in system_settings_list}
    
    # معالجة حفظ الإعدادات عند POST
    if request.method == "POST":
        form = SystemSettingsForm(request.POST)
        if form.is_valid():
            # حفظ كل إعداد في قاعدة البيانات
            for field_name, value in form.cleaned_data.items():
                # تحديد نوع البيانات
                if isinstance(value, bool):
                    data_type = 'boolean'
                    value = 'true' if value else 'false'
                elif isinstance(value, int):
                    data_type = 'integer'
                elif isinstance(value, float):
                    data_type = 'decimal'
                elif value is None:
                    continue
                else:
                    data_type = 'string'
                
                # معالجة خاصة لكلمة مرور الإيميل
                # إذا كانت فارغة، لا نحفظها (نحتفظ بالقديمة)
                if field_name == 'email_password' and not value:
                    continue
                    
                setting, created = SystemSetting.objects.get_or_create(
                    key=field_name,
                    defaults={
                        'value': str(value),
                        'group': 'system',
                        'data_type': data_type,
                    }
                )
                if not created:
                    setting.value = str(value)
                    setting.data_type = data_type
                    setting.save()
            
            messages.success(request, 'تم حفظ إعدادات النظام بنجاح')
            return redirect('core:system_settings')
    else:
        # ملء النموذج بالقيم الحالية
        initial_data = {
            'language': settings_dict.get('language', 'ar'),
            'timezone': settings_dict.get('timezone', 'Africa/Cairo'),
            'date_format': settings_dict.get('date_format', 'd/m/Y'),
            'invoice_prefix': settings_dict.get('invoice_prefix', 'INV-'),
            'default_currency': settings_dict.get('default_currency', 'ج.م'),
            'default_tax_rate': float(settings_dict.get('default_tax_rate', '14')),
            'invoice_notes': settings_dict.get('invoice_notes', ''),
            'maintenance_mode': settings_dict.get('maintenance_mode', 'false') == 'true',
            'session_timeout': int(settings_dict.get('session_timeout', '1440')),
            'backup_frequency': settings_dict.get('backup_frequency', 'daily'),
            'enable_two_factor': settings_dict.get('enable_two_factor', 'false') == 'true',
            'password_policy': settings_dict.get('password_policy', 'medium'),
            'failed_login_attempts': int(settings_dict.get('failed_login_attempts', '5')),
            'account_lockout_time': int(settings_dict.get('account_lockout_time', '30')),
            'email_host': settings_dict.get('email_host', ''),
            'email_port': int(settings_dict.get('email_port', '587')) if settings_dict.get('email_port') else 587,
            'email_username': settings_dict.get('email_username', ''),
            'email_encryption': settings_dict.get('email_encryption', 'tls'),
            'email_from': settings_dict.get('email_from', ''),
        }
        form = SystemSettingsForm(initial=initial_data)
    
    # معلومات النظام
    try:
        import psutil
        disk_usage = psutil.disk_usage('/')
        memory = psutil.virtual_memory()
        system_info = {
            'python_version': platform.python_version(),
            'django_version': '4.2',  # يمكن الحصول عليها من django.VERSION
            'os': platform.system() + ' ' + platform.release(),
            'cpu_count': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_total': round(memory.total / (1024**3), 2),  # GB
            'memory_used': round(memory.used / (1024**3), 2),  # GB
            'memory_percent': memory.percent,
            'disk_total': round(disk_usage.total / (1024**3), 2),  # GB
            'disk_used': round(disk_usage.used / (1024**3), 2),  # GB
            'disk_percent': disk_usage.percent,
        }
    except ImportError:
        # psutil غير مثبت - عرض معلومات أساسية فقط
        system_info = {
            'python_version': platform.python_version(),
            'django_version': '4.2',
            'os': platform.system() + ' ' + platform.release(),
            'cpu_count': 'N/A',
            'cpu_percent': 0,
            'memory_total': 0,
            'memory_used': 0,
            'memory_percent': 0,
            'disk_total': 0,
            'disk_used': 0,
            'disk_percent': 0,
        }
    except Exception as e:
        system_info = None

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
        "form": form,
        "system_info": system_info,
        "settings_dict": settings_dict,  # لعرض حالة كلمة المرور
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

    # عمل تعليم الكل كمقروء إذا كان هناك طلب POST
    if request.method == "POST" and "mark_all_read" in request.POST:
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        messages.success(request, "تم تعليم جميع الإشعارات كمقروءة بنجاح.")
        return redirect("core:notifications_list")

    # الحصول على الفلتر المحدد
    filter_type = request.GET.get('filter', 'unread')  # unread, read (الافتراضي: غير مقروء)
    notification_type = request.GET.get('type', 'all')  # all, info, success, warning, danger, etc.

    # جلب جميع الإشعارات للمستخدم مع تحسين الأداء
    notifications = Notification.objects.filter(user=request.user).select_related('user').order_by(
        "-created_at"
    )

    # تطبيق فلتر النوع أولاً
    if notification_type != 'all':
        notifications = notifications.filter(type=notification_type)

    # تقسيم الإشعارات لغير مقروءة ومقروءة (للعرض) قبل تطبيق فلتر الحالة
    if filter_type == 'unread':
        # عرض غير المقروء فقط
        unread_notifications = notifications.filter(is_read=False)
        read_notifications = Notification.objects.none()  # QuerySet فارغ
    elif filter_type == 'read':
        # عرض المقروء فقط
        unread_notifications = Notification.objects.none()  # QuerySet فارغ
        read_notifications = notifications.filter(is_read=True)
    else:
        # الافتراضي: عرض غير المقروء فقط
        unread_notifications = notifications.filter(is_read=False)
        read_notifications = Notification.objects.none()
    
    # حساب عدد الإشعارات المفلترة
    filtered_count = unread_notifications.count() + read_notifications.count()
    
    # حساب الأعداد الكلية (بدون فلتر)
    all_notifications = Notification.objects.filter(user=request.user)
    unread_count = all_notifications.filter(is_read=False).count()
    total_count = all_notifications.count()
    read_count = all_notifications.filter(is_read=True).count()
    
    # حساب عدد كل نوع
    type_counts = {}
    for choice in Notification.TYPE_CHOICES:
        type_key = choice[0]
        type_counts[type_key] = all_notifications.filter(type=type_key).count()

    # تحديد أزرار الإجراءات بناءً على وجود إشعارات غير مقروءة
    action_buttons = None
    if unread_count > 0:
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
        "total_count": total_count,
        "unread_count": unread_count,
        "read_count": read_count,
        "filtered_count": filtered_count,
        "action_buttons": action_buttons,
        "filter_type": filter_type,
        "notification_type": notification_type,
        "type_counts": type_counts,
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


@login_required
def notification_settings(request):
    """
    صفحة إعدادات الإشعارات للمستخدم
    """
    # الحصول على تفضيلات المستخدم أو إنشاؤها
    preference = NotificationPreference.get_or_create_for_user(request.user)
    
    if request.method == 'POST':
        form = NotificationSettingsForm(request.POST, instance=preference)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم حفظ إعدادات الإشعارات بنجاح')
            return redirect('core:notification_settings')
    else:
        form = NotificationSettingsForm(instance=preference)
    
    # إحصائيات الإشعارات
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    user_notifications = Notification.objects.filter(user=request.user, created_at__gte=thirty_days_ago)
    total_notifications = user_notifications.count()
    read_notifications = user_notifications.filter(is_read=True).count()
    unread_notifications = user_notifications.filter(is_read=False).count()
    
    # أكثر الأنواع شيوعاً
    type_stats = []
    for choice in Notification.TYPE_CHOICES:
        type_key = choice[0]
        type_label = choice[1]
        count = user_notifications.filter(type=type_key).count()
        if count > 0:
            type_stats.append({
                'type': type_key,
                'label': type_label,
                'count': count
            })
    
    # ترتيب حسب العدد
    type_stats.sort(key=lambda x: x['count'], reverse=True)
    
    # Breadcrumbs
    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإشعارات', 'url': reverse('core:notifications_list'), 'icon': 'fas fa-bell'},
        {'title': 'إعدادات الإشعارات', 'active': True, 'icon': 'fas fa-cog'}
    ]
    
    context = {
        'page_title': 'إعدادات الإشعارات',
        'page_icon': 'fas fa-cog',
        'breadcrumb_items': breadcrumb_items,
        'form': form,
        'preference': preference,
        'total_notifications': total_notifications,
        'read_notifications': read_notifications,
        'unread_notifications': unread_notifications,
        'read_percentage': round((read_notifications / total_notifications * 100) if total_notifications > 0 else 0),
        'type_stats': type_stats[:5],  # أعلى 5 أنواع
    }
    
    return render(request, 'core/notification_settings.html', context)
