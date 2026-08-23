from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from supplier.models import Supplier
from purchase.models import Purchase
from core.models import SystemSetting


@login_required
def dashboard(request):
    """
    لوحة التحكم الرئيسية - Corporate ERP
    """
    now = timezone.now()
    current_year = now.year
    current_month = now.month
    today = now.date()

    # إحصائيات المشتريات الشهر الحالي
    purchases_month = Purchase.objects.filter(
        date__month=current_month,
        date__year=current_year
    ).aggregate(
        total=Sum('total'),
        count=Count('id')
    )
    purchases_month_total = purchases_month.get('total') or 0
    purchases_month_count = purchases_month.get('count') or 0

    # إحصائيات الموردين والمنتجات
    suppliers_count = Supplier.objects.filter(is_active=True).count()
    
    try:
        from product.models import Product
        products_count = Product.objects.filter(is_active=True).count()
        
        # المنتجات منخفضة المخزون
        low_stock_products = Product.objects.filter(
            is_active=True,
            stocks__quantity__lt=F('min_stock')
        ).distinct()[:5]
    except Exception:
        products_count = 0
        low_stock_products = []

    # ديون الموردين = مجموع الفواتير المستحقة
    try:
        supplier_dues_total = Purchase.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).aggregate(total=Sum('total'))['total'] or 0
        
        supplier_paid_total = Purchase.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).aggregate(paid=Sum('payments__amount', filter=Q(payments__status='posted')))['paid'] or 0
        
        supplier_dues = supplier_dues_total - supplier_paid_total
    except Exception:
        supplier_dues = 0

    # محاولة جلب بيانات المبيعات والعملاء
    try:
        from sale.models import Sale
        from client.models import Customer
        
        # إحصائيات المبيعات الشهر الحالي
        sales_month = Sale.objects.filter(
            date__month=current_month,
            date__year=current_year
        ).aggregate(
            total=Sum('total'),
            count=Count('id')
        )
        sales_month_total = sales_month.get('total') or 0
        sales_month_count = sales_month.get('count') or 0
        
        # ديون العملاء = مجموع الفواتير المستحقة
        customer_dues_total = Sale.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).aggregate(total=Sum('total'))['total'] or 0
        
        customer_paid_total = Sale.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).aggregate(paid=Sum('payments__amount', filter=Q(payments__status='posted')))['paid'] or 0
        
        customer_dues = customer_dues_total - customer_paid_total
        
        # الفواتير المستحقة للعملاء فقط
        overdue_customer_invoices = Sale.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).select_related('customer').order_by('date')[:5]
        
        # تحضير بيانات جدول فواتير العملاء
        customer_invoices_headers = [
            {'key': 'number', 'label': 'رقم الفاتورة', 'width': '20%', 'format': 'html'},
            {'key': 'customer', 'label': 'العميل', 'width': '25%'},
            {'key': 'date', 'label': 'التاريخ', 'width': '15%', 'class': 'text-center'},
            {'key': 'days_overdue', 'label': 'أيام التأخير', 'width': '15%', 'class': 'text-center', 'format': 'html'},
            {'key': 'amount', 'label': 'المبلغ المستحق', 'width': '25%', 'class': 'text-end fw-bold'}
        ]
        
        customer_invoices_data = []
        curr_sym = SystemSetting.get_currency_symbol()

        for invoice in overdue_customer_invoices:
            days_overdue = (today - invoice.date).days
            
            # تحديد لون البادج حسب عدد الأيام
            if days_overdue > 60:
                badge_class = 'bg-danger'
            elif days_overdue > 30:
                badge_class = 'bg-warning'
            else:
                badge_class = 'bg-info'
            
            # حساب المبلغ المستحق
            remaining = invoice.amount_due
            
            customer_invoices_data.append({
                'number': f'<a href="/sales/{invoice.id}/" class="text-primary">{invoice.number}</a>',
                'customer': invoice.customer.name if invoice.customer else '-',
                'date': invoice.date.strftime('%d-%m-%Y'),
                'days_overdue': f'<span class="badge {badge_class}">{days_overdue} يوم</span>',
                'amount': f'{remaining:,.2f} {curr_sym}'
            })
    except Exception:
        # في حالة عدم وجود موديول المبيعات
        sales_month_total = 0
        sales_month_count = 0
        customer_dues = 0
        customer_invoices_headers = []
        customer_invoices_data = []

    # الفواتير المستحقة للموردين فقط
    overdue_supplier_invoices = Purchase.objects.filter(
        payment_status__in=['unpaid', 'partially_paid']
    ).select_related('supplier').order_by('date')[:5]

    # تحضير بيانات جدول الفواتير المستحقة للموردين
    supplier_invoices_headers = [
        {'key': 'number', 'label': 'رقم الفاتورة', 'width': '20%', 'format': 'html'},
        {'key': 'supplier', 'label': 'المورد', 'width': '25%'},
        {'key': 'date', 'label': 'التاريخ', 'width': '15%', 'class': 'text-center'},
        {'key': 'days_overdue', 'label': 'أيام التأخير', 'width': '15%', 'class': 'text-center', 'format': 'html'},
        {'key': 'amount', 'label': 'المبلغ المستحق', 'width': '25%', 'class': 'text-end fw-bold'}
    ]
    
    supplier_invoices_data = []
    for invoice in overdue_supplier_invoices:
        days_overdue = (today - invoice.date).days
        
        # تحديد لون البادج حسب عدد الأيام
        if days_overdue > 60:
            badge_class = 'bg-danger'
        elif days_overdue > 30:
            badge_class = 'bg-warning'
        else:
            badge_class = 'bg-info'
        
        # حساب المبلغ المستحق
        remaining = invoice.amount_due
        
        supplier_invoices_data.append({
            'number': f'<a href="/purchase/{invoice.id}/" class="text-primary">{invoice.number}</a>',
            'supplier': invoice.supplier.name if invoice.supplier else '-',
            'date': invoice.date.strftime('%d-%m-%Y'),
            'days_overdue': f'<span class="badge {badge_class}">{days_overdue} يوم</span>',
            'amount': f'{remaining:,.2f} {curr_sym}'
        })

    # إجمالي المستحقات
    total_dues = customer_dues + supplier_dues

    # آخر العمليات (آخر 5 فواتير مبيعات ومشتريات)
    recent_activities = []
    
    try:
        from sale.models import Sale
        recent_sales = Sale.objects.select_related('customer').order_by('-created_at')[:3]
        for sale in recent_sales:
            recent_activities.append({
                'icon': 'fa-shopping-cart',
                'title': f'فاتورة مبيعات {sale.number}',
                'description': f'العميل: {sale.customer.name if sale.customer else "-"} - المبلغ: {sale.total:,.2f} {curr_sym}',
                'time': sale.created_at.strftime('%d-%m-%Y %I:%M %p')
            })
    except:
        pass
    
    recent_purchases = Purchase.objects.select_related('supplier').order_by('-created_at')[:3]
    for purchase in recent_purchases:
        recent_activities.append({
            'icon': 'fa-truck',
            'title': f'فاتورة مشتريات {purchase.number}',
            'description': f'المورد: {purchase.supplier.name if purchase.supplier else "-"} - المبلغ: {purchase.total:,.2f} {curr_sym}',
            'time': purchase.created_at.strftime('%d-%m-%Y %I:%M %p')
        })
    
    # ترتيب حسب الوقت
    recent_activities = sorted(recent_activities, key=lambda x: x['time'], reverse=True)[:5]

    context = {
        # إحصائيات أساسية
        "suppliers_count": suppliers_count,
        "products_count": products_count,
        "low_stock_products": low_stock_products,
        
        # إحصائيات المشتريات
        "purchases_month": purchases_month,
        "purchases_month_total": purchases_month_total,
        
        # إحصائيات المبيعات
        "sales_month_total": sales_month_total,
        "sales_month_count": sales_month_count,
        
        # المستحقات
        "supplier_dues": supplier_dues,
        "customer_dues": customer_dues,
        "total_dues": total_dues,
        
        # بيانات الجداول
        "customer_invoices_headers": customer_invoices_headers,
        "customer_invoices_data": customer_invoices_data,
        "supplier_invoices_headers": supplier_invoices_headers,
        "supplier_invoices_data": supplier_invoices_data,
        
        # آخر العمليات
        "recent_activities": recent_activities,
    }

    return render(request, "core/dashboard.html", context)


@login_required
def company_settings(request):
    """
    عرض وتعديل إعدادات المنشـأة
    """
    from core.models import SystemSetting
    from django.contrib import messages
    from django.db import transaction
    from django.core.files.storage import default_storage
    
    # التحقق الموحد من صلاحيات المشرفين
    if not (request.user.is_superuser or getattr(request.user, 'is_admin', False) or request.user.is_staff):
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # معالجة حفظ الإعدادات عند POST
    if request.method == "POST":
        settings_fields = [
            "company_name", "company_name_en", "company_address_en", "company_tax_number",
            "company_commercial_register", "company_country",
            "company_address", "company_phone", "company_mobile",
            "company_email", "company_website", "company_whatsapp",
            "company_working_hours", "company_bank_name", "company_bank_account",
            "company_bank_iban", "company_bank_swift",
            "enable_company_stamp",
            # ألوان الـ CSS
            "color_primary", "color_primary_dark", "color_primary_light", "color_primary_hover",
            "color_success", "color_success_dark",
            "color_warning", "color_warning_dark",
            "color_danger", "color_danger_dark",
            "color_info", "color_info_dark",
            "color_bg_body", "color_text", "color_bg_card", "color_border",
            "color_sidebar_bg", "color_header_bg",
        ]
        
        with transaction.atomic():
            for field in settings_fields:
                if field == "enable_company_stamp":
                    value = "true" if "enable_company_stamp" in request.POST else "false"
                    data_type = "boolean"
                else:
                    value = request.POST.get(field, "").strip()
                    data_type = "string"
                
                SystemSetting.objects.update_or_create(
                    key=field,
                    defaults={"value": value, "data_type": data_type, "group": "general", "is_active": True}
                )

            # الحفاظ على التوافق الخلفي لمفاتيح الضرائب والسجل التجاري
            tax_num = request.POST.get("company_tax_number", "").strip()
            if tax_num:
                SystemSetting.objects.update_or_create(
                    key="tax_number",
                    defaults={"value": tax_num, "data_type": "string", "group": "general", "is_active": True}
                )
            cr_num = request.POST.get("company_commercial_register", "").strip()
            if cr_num:
                SystemSetting.objects.update_or_create(
                    key="commercial_register",
                    defaults={"value": cr_num, "data_type": "string", "group": "general", "is_active": True}
                )

            # معالجة رفع ملفات الميديا (الشعارات والختم) مع التحقق الأمني
            allowed_extensions = ['png', 'jpg', 'jpeg', 'svg', 'webp']
            max_size_bytes = 2 * 1024 * 1024  # 2MB
            
            for file_key in ['company_logo', 'company_logo_light', 'company_logo_mini', 'company_stamp']:
                if file_key in request.FILES:
                    uploaded_file = request.FILES[file_key]
                    ext = uploaded_file.name.split('.')[-1].lower()
                    if ext not in allowed_extensions:
                        messages.warning(request, f"امتداد الملف {uploaded_file.name} غير مدعوم. الصيغ المسموحة: {', '.join(allowed_extensions)}")
                        continue
                    if uploaded_file.size > max_size_bytes:
                        messages.warning(request, f"حجم الملف {uploaded_file.name} يتجاوز الحد الأقصى (2 ميجابايت)")
                        continue
                    
                    file_path = default_storage.save(f"company/{file_key}_{uploaded_file.name}", uploaded_file)
                    SystemSetting.objects.update_or_create(
                        key=file_key,
                        defaults={"value": file_path, "data_type": "string", "group": "general", "is_active": True}
                    )

            # تفريغ الكاش الموحد فوراً
            SystemSetting.invalidate_all_system_caches()

        messages.success(request, "تم حفظ إعدادات المنشـأة بنجاح ✅")
        active_tab = request.POST.get("active_tab", "basic")
        return redirect(f"{reverse('core:company_settings')}?tab={active_tab}")

    # جلب الإعدادات الحالية
    settings_dict = {}
    for setting in SystemSetting.objects.all():
        settings_dict[setting.key] = setting.value

    # التحقق من وجود ملفات الشعارات والختم فعلياً على الـ storage
    for logo_key in ['company_logo', 'company_logo_light', 'company_logo_mini', 'company_stamp']:
        if logo_key in settings_dict and settings_dict[logo_key]:
            if not default_storage.exists(settings_dict[logo_key]):
                settings_dict[logo_key] = ""

    # إعداد الهيدر
    header_buttons = [
        {
            'id': 'exportCompanyBtn',
            'icon': 'fa-file-export',
            'text': 'تصدير الإعدادات',
            'class': 'btn-outline-secondary'
        },
        {
            'toggle': 'modal',
            'target': '#importCompanyModal',
            'icon': 'fa-file-import',
            'text': 'استيراد الإعدادات',
            'class': 'btn-outline-primary'
        }
    ]

    # مسار التنقل الموحد (Rule #6)
    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإعدادات', 'icon': 'fas fa-cog'},
        {'title': 'إعدادات المنشـأة', 'active': True}
    ]

    context = {
        "title": "إعدادات المنشـأة",
        "subtitle": "إدارة معلومات المنشـأة، البيانات القانونية، الهوية البصرية والمستندات",
        "icon": "fas fa-building",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "settings": settings_dict,
        "MEDIA_URL": settings.MEDIA_URL,
        "company_name": settings_dict.get("company_name", ""),
        "company_name_en": settings_dict.get("company_name_en", ""),
        "company_tax_number": settings_dict.get("company_tax_number", ""),
        "company_commercial_register": settings_dict.get("company_commercial_register", ""),
        "company_country": settings_dict.get("company_country", ""),
        "company_address": settings_dict.get("company_address", ""),
        "company_address_en": settings_dict.get("company_address_en", ""),
        "company_phone": settings_dict.get("company_phone", ""),
        "company_mobile": settings_dict.get("company_mobile", ""),
        "company_email": settings_dict.get("company_email", ""),
        "company_website": settings_dict.get("company_website", ""),
        "company_whatsapp": settings_dict.get("company_whatsapp", ""),
        "company_working_hours": settings_dict.get("company_working_hours", ""),
        "company_bank_name": settings_dict.get("company_bank_name", ""),
        "company_bank_account": settings_dict.get("company_bank_account", ""),
        "company_bank_iban": settings_dict.get("company_bank_iban", ""),
        "company_bank_swift": settings_dict.get("company_bank_swift", ""),
        "company_logo": settings_dict.get("company_logo", ""),
        "company_logo_light": settings_dict.get("company_logo_light", ""),
        "company_logo_mini": settings_dict.get("company_logo_mini", ""),
        "company_stamp": settings_dict.get("company_stamp", ""),
        "enable_company_stamp": settings_dict.get("enable_company_stamp", "true") == "true",
        # ألوان الـ CSS
        "color_primary": settings_dict.get("color_primary", "#04578d"),
        "color_primary_dark": settings_dict.get("color_primary_dark", "#033d64"),
        "color_primary_light": settings_dict.get("color_primary_light", "#0570b0"),
        "color_primary_hover": settings_dict.get("color_primary_hover", "#0462a0"),
        "color_success": settings_dict.get("color_success", "#22c55e"),
        "color_success_dark": settings_dict.get("color_success_dark", "#059669"),
        "color_warning": settings_dict.get("color_warning", "#f59e0b"),
        "color_warning_dark": settings_dict.get("color_warning_dark", "#d97706"),
        "color_danger": settings_dict.get("color_danger", "#ef4444"),
        "color_danger_dark": settings_dict.get("color_danger_dark", "#dc2626"),
        "color_info": settings_dict.get("color_info", "#0ea5e9"),
        "color_info_dark": settings_dict.get("color_info_dark", "#0284c7"),
        "color_bg_body": settings_dict.get("color_bg_body", "#f9fafb"),
        "color_text": settings_dict.get("color_text", "#374151"),
        "color_bg_card": settings_dict.get("color_bg_card", "#ffffff"),
        "color_border": settings_dict.get("color_border", "#e5e7eb"),
        "color_sidebar_bg": settings_dict.get("color_sidebar_bg", "#ffffff"),
        "color_header_bg": settings_dict.get("color_header_bg", "#ffffff"),
    }

    return render(request, "core/company_settings.html", context)


@login_required
def operations_settings(request):
    """
    عرض وتعديل سياسات التشغيل والفواتير والطباعة وعروض الأسعار
    """
    from core.models import SystemSetting
    from core.forms import OperationsSettingsForm
    from django.contrib import messages
    from django.db import transaction

    # التحقق الموحد من صلاحيات المشرفين
    if not (request.user.is_superuser or getattr(request.user, 'is_admin', False) or request.user.is_staff):
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # جلب الإعدادات الحالية
    settings_dict = {}
    for setting in SystemSetting.objects.all():
        settings_dict[setting.key] = setting.value

    # تهيئة البيانات الافتراضية للفورم
    initial_data = {
        'sale_invoice_item_types': settings_dict.get('sale_invoice_item_types', 'both'),
        'purchase_invoice_item_types': settings_dict.get('purchase_invoice_item_types', 'both'),
        'invoice_product_code_display': settings_dict.get('invoice_product_code_display', 'sku'),
        'enable_custom_fields': settings_dict.get('enable_custom_fields', 'true') == 'true',
        'custom_fields_display_mode': settings_dict.get('custom_fields_display_mode', 'expanded'),
        'enable_quotations': SystemSetting.get_bool('enable_quotations', False),
        'default_quotation_validity_days': int(settings_dict.get('default_quotation_validity_days', 15)) if settings_dict.get('default_quotation_validity_days') else 15,
        'enable_sales_orders': SystemSetting.get_bool('enable_sales_orders', False),
        'enable_purchase_orders': SystemSetting.get_bool('enable_purchase_orders', False),
        'default_sale_invoice_notes': settings_dict.get('default_sale_invoice_notes', settings_dict.get('invoice_notes', '')),
        'default_sale_invoice_notes_en': settings_dict.get('default_sale_invoice_notes_en', ''),
        'default_quotation_notes': settings_dict.get('default_quotation_notes', ''),
        'default_quotation_notes_en': settings_dict.get('default_quotation_notes_en', ''),
        'default_print_language': settings_dict.get('default_print_language', 'ar'),
        'invoice_title_sale_en': settings_dict.get('invoice_title_sale_en', 'TAX INVOICE'),
        'invoice_title_quotation_en': settings_dict.get('invoice_title_quotation_en', 'QUOTATION'),
        'enable_thermal_printing': settings_dict.get('enable_thermal_printing') == 'true',
        'receipt_paper_width': settings_dict.get('receipt_paper_width', '80'),
    }

    if request.method == "POST":
        form = OperationsSettingsForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                for key, value in form.cleaned_data.items():
                    if isinstance(value, bool):
                        db_value = 'true' if value else 'false'
                        data_type = 'boolean'
                    elif value is None:
                        db_value = ''
                        data_type = 'string'
                    else:
                        db_value = str(value)
                        data_type = 'integer' if isinstance(value, int) else 'string'

                    SystemSetting.objects.update_or_create(
                        key=key,
                        defaults={"value": db_value, "group": "sales", "data_type": data_type, "is_active": True}
                    )

                # تفريغ الكاش الموحد فوراً
                SystemSetting.invalidate_all_system_caches()

            messages.success(request, "تم حفظ سياسات التشغيل بنجاح ✅")
            active_tab = request.POST.get("active_tab", "invoices")
            return redirect(f"{reverse('core:operations_settings')}?tab={active_tab}")
        else:
            messages.error(request, "حدث خطأ أثناء حفظ السياسات، يرجى مراجعة الحقول")
    else:
        form = OperationsSettingsForm(initial=initial_data)

    header_buttons = [
        {
            'id': 'exportOperationsBtn',
            'icon': 'fa-file-export',
            'text': 'تصدير السياسات',
            'class': 'btn-outline-secondary'
        },
        {
            'toggle': 'modal',
            'target': '#importOperationsModal',
            'icon': 'fa-file-import',
            'text': 'استيراد السياسات',
            'class': 'btn-outline-primary'
        }
    ]

    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإعدادات', 'icon': 'fas fa-cog'},
        {'title': 'سياسات التشغيل', 'active': True}
    ]

    context = {
        "title": "سياسات التشغيل",
        "subtitle": "إدارة سياسات الفواتير، المبيعات، الشراء، عروض الأسعار ونماذج الطباعة",
        "icon": "fas fa-sliders-h",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "settings": settings_dict,
        "form": form,
    }

    return render(request, "core/operations_settings.html", context)


@login_required
def system_settings(request):
    """
    عرض وتعديل إعدادات النظام والبنية التحتية والأمان
    """
    from core.models import SystemSetting
    from core.forms import SystemSettingsForm
    from django.contrib import messages
    from django.db import transaction
    
    # التحقق الموحد من صلاحيات المشرفين
    if not (request.user.is_superuser or getattr(request.user, 'is_admin', False) or request.user.is_staff):
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # التثبت من وجود أي عمليات مالية أو تجارية بالنظام للقفل المحاسبي (IAS 21)
    from financial.models import JournalEntry, Currency
    from sale.models.sale import Sale
    from sale.models.quotation import Quotation
    from purchase.models.purchase import Purchase

    has_transactions = False
    try:
        has_transactions = (
            JournalEntry.objects.exists() or
            Sale.objects.exists() or
            Purchase.objects.exists() or
            Quotation.objects.exists()
        )
    except Exception:
        pass

    func_curr = None
    try:
        func_curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.first()
    except Exception:
        pass

    # جلب الإعدادات الحالية
    settings_dict = {}
    for setting in SystemSetting.objects.all():
        settings_dict[setting.key] = setting.value

    # تهيئة البيانات الافتراضية للفورم
    initial_data = {
        'site_name': settings_dict.get('site_name', 'موهبة ERP'),
        'language': settings_dict.get('language', 'ar'),
        'timezone': settings_dict.get('system_timezone') or settings_dict.get('timezone', 'Africa/Cairo'),
        'date_format': settings_dict.get('date_format', 'd/m/Y'),
        'time_format': settings_dict.get('time_format', '12'),
        'default_currency': func_curr.id if func_curr else None,
        'maintenance_mode': settings_dict.get('maintenance_mode') == 'true',
        'maintenance_message': settings_dict.get('maintenance_message', ''),
        'session_timeout': int(settings_dict.get('session_timeout', 60)) if settings_dict.get('session_timeout') else 60,
        'enable_two_factor': settings_dict.get('enable_two_factor') == 'true',
        'password_policy': settings_dict.get('password_policy', 'medium'),
        'failed_login_attempts': int(settings_dict.get('failed_login_attempts', 5)) if settings_dict.get('failed_login_attempts') else 5,
        'account_lockout_time': int(settings_dict.get('account_lockout_time', 30)) if settings_dict.get('account_lockout_time') else 30,
        'email_host': settings_dict.get('email_host', ''),
        'email_port': int(settings_dict.get('email_port', 587)) if settings_dict.get('email_port') else 587,
        'email_username': settings_dict.get('email_username', ''),
        'email_password': settings_dict.get('email_password', ''),
        'email_encryption': settings_dict.get('email_encryption', 'tls'),
        'email_from': settings_dict.get('email_from', ''),
        'daftra_enabled': settings_dict.get('daftra_enabled') == 'true',
        'daftra_domain': settings_dict.get('daftra_domain', ''),
        'daftra_api_key': settings_dict.get('daftra_api_key', ''),
    }

    if request.method == "POST":
        form = SystemSettingsForm(request.POST, is_locked=has_transactions)
        if form.is_valid():
            with transaction.atomic():
                for key, value in form.cleaned_data.items():
                    # حماية كلمات المرور من المسح إذا تم ترك الحقل فارغاً
                    if key in ('email_password', 'daftra_api_key') and not value:
                        continue

                    if key == 'timezone':
                        SystemSetting.objects.update_or_create(
                            key='system_timezone',
                            defaults={"value": str(value), "group": "system", "data_type": "string", "is_active": True}
                        )
                        SystemSetting.objects.update_or_create(
                            key='timezone',
                            defaults={"value": str(value), "group": "system", "data_type": "string", "is_active": True}
                        )
                        continue
                    elif key == 'default_currency':
                        if not has_transactions and value:
                            try:
                                if hasattr(value, 'is_functional'):
                                    value.is_functional = True
                                    value.save()
                                    from financial.services.partner_advance_service import PartnerAdvanceService
                                    PartnerAdvanceService.rebuild_all_snapshots()
                            except Exception as e:
                                logger.error(f"Error promoting functional currency: {e}")
                        continue

                    if isinstance(value, bool):
                        db_value = 'true' if value else 'false'
                        data_type = 'boolean'
                    elif value is None:
                        db_value = ''
                        data_type = 'string'
                    else:
                        db_value = str(value)
                        data_type = 'integer' if isinstance(value, int) else 'string'

                    # تحديد المجموعة بدقة
                    if key.startswith('email_') or key.startswith('daftra_') or key in ('maintenance_mode', 'maintenance_message', 'session_timeout', 'failed_login_attempts', 'account_lockout_time', 'enable_two_factor', 'password_policy'):
                        group_val = 'system'
                    else:
                        group_val = 'general'

                    SystemSetting.objects.update_or_create(
                        key=key,
                        defaults={"value": db_value, "group": group_val, "data_type": data_type, "is_active": True}
                    )

                # تفريغ الكاش الموحد فوراً
                SystemSetting.invalidate_all_system_caches()

            messages.success(request, "تم حفظ إعدادات النظام بنجاح ✅")
            active_tab = request.POST.get("active_tab", "general")
            return redirect(f"{reverse('core:system_settings')}?tab={active_tab}")
        else:
            messages.error(request, "حدث خطأ أثناء حفظ الإعدادات، يرجى مراجعة الحقول")
    else:
        form = SystemSettingsForm(initial=initial_data, is_locked=has_transactions)

    header_buttons = [
        {
            'id': 'exportSystemBtn',
            'icon': 'fa-file-export',
            'text': 'تصدير الإعدادات',
            'class': 'btn-outline-secondary'
        },
        {
            'toggle': 'modal',
            'target': '#importSystemModal',
            'icon': 'fa-file-import',
            'text': 'استيراد الإعدادات',
            'class': 'btn-outline-primary'
        }
    ]

    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإعدادات', 'icon': 'fas fa-cog'},
        {'title': 'إعدادات النظام', 'active': True}
    ]

    default_vat_code = None
    try:
        from financial.models import TaxCode
        default_vat_code = TaxCode.objects.filter(tax_type="VAT", is_default=True, is_active=True).first()
    except Exception:
        pass

    context = {
        "title": "إعدادات النظام",
        "subtitle": "إدارة إعدادات النظام العامة، البنية التحتية، الأمان والتكامل",
        "icon": "fas fa-cogs",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "settings": settings_dict,
        "form": form,
        "is_locked": has_transactions,
        "func_curr": func_curr,
        "default_vat_code": default_vat_code,
    }

    return render(request, "core/system_settings.html", context)


@login_required
def get_current_time(request):
    """
    API للحصول على الوقت الحالي
    """
    from django.http import JsonResponse
    
    return JsonResponse({
        'success': True,
        'time': timezone.now().isoformat(),
        'timestamp': timezone.now().timestamp()
    })


@login_required
def system_reset(request):
    """
    تفريغ وتصفير الحركات والمعاملات التجريبية (للمدير العام فقط)
    مع الحفاظ الكامل على الإعدادات والمستخدمين وشجرة الحسابات والعملات.
    """
    from django.contrib import messages
    from django.http import JsonResponse
    from core.services.system_reset_service import SystemResetService
    
    if not request.user.is_superuser:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'success': False, 'message': 'عفواً، هذه العملية مقتصرة على المدير العام فقط.'}, status=403)
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )
    
    if request.method == "POST":
        confirmation = request.POST.get("confirmation", "").strip()
        if confirmation not in ["تأكيد", "RESET", "reset"]:
            msg = "يرجى كتابة كلمة 'تأكيد' أو 'RESET' للموافقة على تفريغ الحركات."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg}, status=400)
            messages.error(request, msg)
            return redirect("core:system_reset")
        
        try:
            summary = SystemResetService.reset_test_transactions(user=request.user)
            total_deleted = sum(summary.values())
            success_msg = f"تم تفريغ وتصفير الحركات والمعاملات بنجاح ({total_deleted} سجل). تم الحفاظ على الإعدادات وشجرة الحسابات والمستخدمين."
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'total_deleted': total_deleted,
                    'redirect_url': reverse('core:dashboard')
                })
            
            messages.success(request, success_msg)
            return redirect("core:dashboard")
        except Exception as e:
            error_msg = f"حدث خطأ أثناء تفريغ البيانات: {str(e)}"
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            messages.error(request, error_msg)
            return redirect("core:system_reset")
    
    context = {
        "title": "تفريغ وتصفير الحركات التجريبية",
        "subtitle": "تصفير الفواتير والسندات والقيود مع الحفاظ التام على الإعدادات وشجرة الحسابات",
        "icon": "fas fa-trash-restore",
        "breadcrumb_items": [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'إعدادات النظام', 'url': reverse('core:system_settings'), 'icon': 'fas fa-cogs'},
            {'title': 'تفريغ الحركات', 'active': True}
        ]
    }
    
    return render(request, "core/system_reset.html", context)



@login_required
def notifications_list(request):
    """
    قائمة الإشعارات للمستخدم
    """
    from core.models import Notification
    
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')[:50]
    
    # إعداد الهيدر
    header_buttons = [
        {
            'url': reverse('core:dashboard'),
            'icon': 'fa-arrow-right',
            'text': 'العودة للوحة التحكم',
            'class': 'btn-outline-secondary'
        }
    ]

    # مسار التنقل
    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإشعارات', 'active': True}
    ]

    context = {
        "title": "الإشعارات",
        "subtitle": "جميع إشعاراتك",
        "icon": "fas fa-bell",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "notifications": notifications,
    }

    return render(request, "core/notifications_list.html", context)


@login_required
def notification_settings(request):
    """
    إعدادات الإشعارات للمستخدم
    """
    from django.contrib import messages
    
    if request.method == "POST":
        # حفظ إعدادات الإشعارات
        messages.success(request, "تم حفظ إعدادات الإشعارات بنجاح")
        return redirect("core:notification_settings")
    
    # إعداد الهيدر
    header_buttons = [
        {
            'url': reverse('core:notifications_list'),
            'icon': 'fa-arrow-right',
            'text': 'العودة للإشعارات',
            'class': 'btn-outline-secondary'
        }
    ]

    # مسار التنقل
    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإشعارات', 'url': reverse('core:notifications_list'), 'icon': 'fas fa-bell'},
        {'title': 'الإعدادات', 'active': True}
    ]

    context = {
        "title": "إعدادات الإشعارات",
        "subtitle": "إدارة تفضيلات الإشعارات",
        "icon": "fas fa-cog",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
    }

    return render(request, "core/notification_settings.html", context)


@login_required
def whatsapp_settings(request):
    """
    إعدادات تكامل WhatsApp عبر Kapso
    للمديرين فقط - تخزن الإعدادات في SystemSetting
    """
    from django.contrib import messages
    from django.http import JsonResponse
    from core.models import SystemSetting
    from core.services.whatsapp_service import WhatsAppService

    if not request.user.is_admin and not request.user.is_superuser:
        return render(request, "core/permission_denied.html", {
            "title": "غير مصرح",
            "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"
        })

    # اختبار الاتصال (AJAX)
    if request.method == "POST" and request.POST.get("action") == "test_connection":
        result = WhatsAppService.test_connection(
            api_key=request.POST.get("api_key", ""),
            phone_number_id=request.POST.get("phone_number_id", ""),
        )
        return JsonResponse(result)

    # إرسال رسالة تجريبية (AJAX)
    if request.method == "POST" and request.POST.get("action") == "send_test":
        result = WhatsAppService.send_test_message(
            phone=request.POST.get("test_phone", "")
        )
        return JsonResponse(result)

    # جلب الـ templates (AJAX)
    if request.method == "GET" and request.GET.get("action") == "get_templates":
        templates = WhatsAppService.get_templates()
        return JsonResponse({"templates": templates})

    # حفظ الإعدادات
    if request.method == "POST" and request.POST.get("action") != "test_connection":
        whatsapp_settings_map = {
            "whatsapp_enabled":                ("boolean", request.POST.get("whatsapp_enabled") == "on"),
            "whatsapp_api_key":                ("string",  request.POST.get("whatsapp_api_key", "").strip()),
            "whatsapp_phone_number_id":        ("string",  request.POST.get("whatsapp_phone_number_id", "").strip()),
            "whatsapp_send_invoice":           ("boolean", request.POST.get("whatsapp_send_invoice") == "on"),
            "whatsapp_send_payment":           ("boolean", request.POST.get("whatsapp_send_payment") == "on"),
            "whatsapp_send_overdue":           ("boolean", request.POST.get("whatsapp_send_overdue") == "on"),
            "whatsapp_overdue_days":           ("integer", request.POST.get("whatsapp_overdue_days", "7")),
            "whatsapp_fallback_template":      ("string",  request.POST.get("whatsapp_fallback_template", "").strip()),
            "whatsapp_fallback_template_lang": ("string",  request.POST.get("whatsapp_fallback_template_lang", "ar").strip()),
        }

        for key, (data_type, value) in whatsapp_settings_map.items():
            str_value = str(value).lower() if isinstance(value, bool) else str(value)
            setting, _ = SystemSetting.objects.get_or_create(
                key=key,
                defaults={"value": str_value, "data_type": data_type, "group": "whatsapp", "is_active": True}
            )
            setting.value = str_value
            setting.data_type = data_type
            setting.group = "whatsapp"
            setting.is_active = True
            setting.save()

        messages.success(request, "تم حفظ إعدادات WhatsApp بنجاح ✅")
        return redirect("core:whatsapp_settings")

    # جلب الإعدادات الحالية
    config = WhatsAppService.get_config()
    config["fallback_template"] = SystemSetting.get_setting("whatsapp_fallback_template", "")
    config["fallback_template_lang"] = SystemSetting.get_setting("whatsapp_fallback_template_lang", "ar")

    header_buttons = [
        {
            'url': reverse('core:system_settings'),
            'icon': 'fa-arrow-right',
            'text': 'إعدادات النظام',
            'class': 'btn-outline-secondary'
        }
    ]

    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإعدادات', 'url': reverse('core:system_settings'), 'icon': 'fas fa-cog'},
        {'title': 'إعدادات WhatsApp', 'active': True}
    ]

    context = {
        "title": "إعدادات WhatsApp",
        "subtitle": "تكامل إشعارات العملاء عبر واتساب (Kapso)",
        "icon": "fab fa-whatsapp",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "config": config,
        "is_connected": WhatsAppService.is_enabled(),
    }

    return render(request, "core/whatsapp_settings.html", context)


@csrf_exempt
def whatsapp_webhook(request):
    """
    Webhook لاستقبال delivery status من Kapso/Meta.
    Meta بتبعت الـ delivery failures هنا بعد الإرسال.
    """
    import json
    from django.http import HttpResponse

    # GET = verification challenge من Meta
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        expected_token = SystemSetting.get_setting("whatsapp_webhook_verify_token", "")
        if mode == "subscribe" and token == expected_token:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("Forbidden", status=403)

    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        data = json.loads(request.body)
        logger.info(f"WhatsApp webhook received: {data}")

        # استخراج الـ statuses من الـ payload
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    msg_status = status.get("status")
                    msg_id = status.get("id", "")
                    recipient = status.get("recipient_id", "")
                    errors = status.get("errors", [])

                    if msg_status == "failed" and errors:
                        for err in errors:
                            code = err.get("code")
                            title = err.get("title", "")
                            logger.warning(
                                f"WhatsApp delivery FAILED - msg:{msg_id} to:{recipient} "
                                f"code:{code} title:{title}"
                            )
                    elif msg_status in ("delivered", "read"):
                        logger.info(f"WhatsApp {msg_status} - msg:{msg_id} to:{recipient}")

    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")

    return HttpResponse("OK", status=200)
