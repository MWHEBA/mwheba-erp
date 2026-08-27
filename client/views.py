from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.db.models import Sum, Q
from django.urls import reverse
from django.http import JsonResponse
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)

from utils.templatetags.utils_extras import smart_float
from .models import Customer, CustomerPayment
from .forms import CustomerForm, CustomerAccountChangeForm
from .services import CustomerService
from sale.models import Sale
from financial.models import ChartOfAccounts

# Initialize CustomerService
customer_service = CustomerService()


@login_required
def customer_list(request):
    """
    عرض قائمة العملاء
    """
    status = request.GET.get('status', 'active')
    if not status:
        status = 'active'
    has_debt = request.GET.get('has_debt', '')
    search = request.GET.get('search', '')
    currency_id = request.GET.get('currency', '')
    client_type = request.GET.get('client_type', '')

    customers_qs = Customer.objects.select_related('default_currency').all().order_by('-created_at')

    if status == 'active':
        customers_qs = customers_qs.filter(is_active=True)
    elif status == 'inactive':
        customers_qs = customers_qs.filter(is_active=False)
    # if status == 'all', no filtering is applied

    if currency_id:
        customers_qs = customers_qs.filter(default_currency_id=currency_id)

    if client_type:
        customers_qs = customers_qs.filter(client_type=client_type)

    if search:
        from utils.search import smart_search_filter
        customers_qs = smart_search_filter(
            customers_qs,
            search,
            text_fields=['name', 'company_name', 'contact_person', 'address', 'city'],
            code_fields=['code', 'phone', 'phone_primary', 'phone_secondary', 'tax_number', 'national_id', 'commercial_registry']
        )

    if has_debt == '1':
        customers_qs = customers_qs.filter(balance__gt=0)
    elif has_debt == '0':
        customers_qs = customers_qs.filter(balance__lte=0)

    # جلب العملات والتصنيفات المستخدمة فقط في العملاء
    from financial.models.currency import Currency
    used_currency_ids = Customer.objects.exclude(default_currency__isnull=True).values_list('default_currency_id', flat=True).distinct()
    currencies = Currency.objects.filter(id__in=used_currency_ids).order_by('name')

    used_client_types = Customer.objects.exclude(client_type__isnull=True).exclude(client_type='').values_list('client_type', flat=True).distinct()
    client_types = [choice for choice in Customer.CLIENT_TYPES if choice[0] in used_client_types]
    if not client_types:
        client_types = Customer.CLIENT_TYPES

    # التصدير المزدوج: تصدير كافة البيانات المفلترة من الباك إند
    if request.GET.get('export') == 'excel':
        from utils.export import export_queryset_to_excel
        return export_queryset_to_excel(
            customers_qs,
            filename="customers_export.xlsx",
            fields=["code", "name", "phone", "address", "default_currency__code", "balance", "is_active"],
            headers=["الكود", "اسم العميل", "رقم الهاتف", "العنوان", "العملة", "المديونية", "نشط"]
        )

    active_customers = Customer.objects.filter(is_active=True).count()
    inactive_customers = Customer.objects.filter(is_active=False).count()
    total_debt = customers_qs.aggregate(total=Sum('balance'))['total'] or 0

    # تعريف أعمدة الجدول مع تفعيل الفرز الـ SSR
    headers = [
        {
            "key": "name",
            "label": "اسم العميل",
            "sortable": True,
            "class": "text-center",
            "format": "link",
            "url": "client:customer_detail",
        },
        {"key": "code", "label": "الكود", "sortable": True},
        {"key": "phone", "label": "رقم الهاتف", "sortable": False},
        {"key": "address", "label": "العنوان", "sortable": False},
        {
            "key": "currency_display",
            "label": "العملة",
            "sortable": False,
            "format": "html",
            "class": "text-center",
        },
        {
            "key": "actual_balance_display",
            "label": "المديونية",
            "sortable": True,
            "format": "html",
            "class": "text-center",
        },
    ]

    # تعريف أزرار الإجراءات (تم حذف أزرار العرض والتعديل لأن الصف بالكامل قابل للنقر)
    action_buttons = [
        {
            "type": "button",
            "icon": "fa-undo",
            "class": "action-reactivate text-success",
            "label": "إعادة تنشيط",
            "condition": "is_inactive",
            "data_attrs": 'onclick="reactivateCustomer(this.closest(\'tr\').dataset.id)"',
        },
        {
            "modal": True,
            "icon": "fa-trash-alt",
            "class": "action-delete text-danger",
            "label": "حذف / أرشفة",
        },
    ]

    # Whitelist الفرز الأمني
    allowed_sort_fields = {
        'name': 'name',
        'code': 'code',
        'actual_balance_display': 'balance',
        'is_active': 'is_active',
    }

    # الترقيم والفرز الـ SSR عبر المحرك المركزي
    from core.utils import paginate_queryset, render_paginated_response
    pagination_data = paginate_queryset(
        customers_qs,
        request,
        default_per_page=25,
        allowed_sort_fields=allowed_sort_fields
    )

    page_obj = pagination_data['page_obj']
    
    from financial.services.partner_exposure_service import BusinessPartnerExposureService
    from core.presenters.currency_exposure_presenter import CurrencyExposurePresenter, get_currency_symbol

    page_customer_ids = [c.pk for c in page_obj]
    exposure_map = BusinessPartnerExposureService.get_open_balances("customer", page_customer_ids)

    for c in page_obj:
        curr_code = c.default_currency.code if c.default_currency else "EGP"
        curr_symbol = (c.default_currency.symbol if c.default_currency and c.default_currency.symbol else "") or get_currency_symbol(curr_code)
        c.currency_display = f'<span class="badge bg-light text-dark border">{curr_symbol}</span>'
        customer_dtos = exposure_map.get(c.pk, [])
        c.actual_balance_display = CurrencyExposurePresenter.render_html_badges(customer_dtos)

    customers = page_obj

    from core.models import SystemSetting
    daftra_enabled = SystemSetting.get_setting('daftra_enabled', 'false') == 'true'

    is_archive_view = (status == "inactive")
    header_buttons = []

    if is_archive_view:
        header_buttons.append({
            "url": reverse("client:customer_list"),
            "icon": "fa-users",
            "text": "العملاء النشطون",
            "class": "btn-outline-primary",
        })
    else:
        header_buttons.append({
            "url": reverse("client:customer_add"),
            "icon": "fa-plus",
            "text": "إضافة عميل",
            "class": "btn-primary",
        })
        header_buttons.append({
            "url": reverse("client:customer_list") + "?status=inactive",
            "icon": "fa-archive",
            "text": f"الأرشيف ({inactive_customers})" if inactive_customers > 0 else "الأرشيف",
            "class": "btn-outline-secondary",
        })

    if daftra_enabled:
        header_buttons.append({
            "onclick": "syncWithDaftra('clients')",
            "icon": "fa-sync",
            "text": "مزامنة دفترة",
            "class": "btn-outline-info",
        })

    page_title = "أرشيف العملاء" if is_archive_view else "قائمة العملاء"
    page_subtitle = "عرض وإدارة العملاء المؤرشفين وغير النشطين" if is_archive_view else "إدارة العملاء وعرض بياناتهم ومعاملاتهم المالية"
    page_icon = "fas fa-archive" if is_archive_view else "fas fa-users"

    context = {
        **pagination_data,
        'customers': customers,
        'headers': headers,
        'action_buttons': action_buttons,
        'active_customers': active_customers,
        'inactive_customers': inactive_customers,
        'total_debt': total_debt,
        'currencies': currencies,
        'client_types': client_types,
        'show_export': True,
        'page_title': page_title,
        'page_subtitle': page_subtitle,
        'page_icon': page_icon,
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "العملاء", "url": reverse("client:customer_list") if is_archive_view else None, "active": not is_archive_view},
            *([{"title": "الأرشيف", "active": True}] if is_archive_view else []),
        ],
    }

    return render_paginated_response(
        request,
        'client/customer_list.html',
        context,
        table_template_name='client/partials/customer_table.html'
    )


@login_required
def customer_add(request):
    """
    إضافة عميل جديد - متكامل مع CustomerForm و CustomerService
    """
    if request.method == "POST":
        form = CustomerForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                customer = form.save(user=request.user)
                messages.success(request, _("تم إضافة العميل بنجاح"))
                return redirect("client:customer_detail", pk=customer.pk)
            except Exception as e:
                messages.error(request, f"خطأ في إضافة العميل: {str(e)}")
    else:
        form = CustomerForm(user=request.user)

    context = {
        "form": form,
        "page_title": "إضافة عميل جديد",
        "page_subtitle": "إضافة عميل جديد إلى قاعدة بيانات النظام مع ضبط الهوية وشروط الائتمان",
        "page_icon": "fas fa-user-plus",
        "header_buttons": [
            {
                "url": reverse("client:customer_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "العملاء",
                "url": reverse("client:customer_list"),
                "icon": "fas fa-users",
            },
            {"title": "إضافة عميل", "active": True},
        ],
    }

    return render(request, "client/customer_form.html", context)


@login_required
def customer_edit(request, pk):
    """
    تعديل بيانات عميل - متكامل مع حوكمة الائتمان ودليل الحسابات
    """
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer, user=request.user)
        if form.is_valid():
            try:
                customer = form.save(user=request.user)
                messages.success(request, _("تم تعديل بيانات العميل بنجاح"))
                return redirect("client:customer_detail", pk=customer.pk)
            except Exception as e:
                messages.error(request, f"خطأ في تعديل العميل: {str(e)}")
    else:
        form = CustomerForm(instance=customer, user=request.user)

    from client.models import CustomerCreditProfile
    credit_profile = CustomerCreditProfile.objects.filter(customer=customer).first()

    context = {
        "form": form,
        "customer": customer,
        "financial_account": customer.financial_account,
        "credit_profile": credit_profile,
        "page_title": f"تعديل بيانات العميل: {customer.name}",
        "page_subtitle": "تعديل بيانات العميل والهوية وإدارة حساباته وشروط الائتمان",
        "page_icon": "fas fa-user-edit",
        "header_buttons": [
            {
                "url": reverse("client:customer_detail", kwargs={"pk": customer.pk}),
                "icon": "fa-eye",
                "text": "عرض التفاصيل",
                "class": "btn-outline-primary",
            },
            {
                "url": reverse("client:customer_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "العملاء",
                "url": reverse("client:customer_list"),
                "icon": "fas fa-users",
            },
            {
                "title": customer.name,
                "url": reverse("client:customer_detail", kwargs={"pk": customer.pk}),
            },
            {"title": "تعديل", "active": True},
        ],
    }

    return render(request, "client/customer_form.html", context)


@login_required
def customer_delete(request, pk):
    """
    حذف أو أرشفة عميل (فحص سيادي ذكي وتحديث تفاعلي بالـ AJAX)
    """
    customer = get_object_or_404(Customer, pk=pk)

    # 1. طلب الفحص المسبق اللحظي (Pre-check)
    if request.GET.get('precheck') == '1' or (request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.method == 'GET'):
        try:
            can_delete, summary, exposure = CustomerService.can_delete_customer(customer)
            from core.templatetags.custom_filters import smart_float
            from core.presenters.currency_exposure_presenter import get_currency_symbol
            from decimal import Decimal
            curr_code = customer.default_currency.code if customer.default_currency else "EGP"
            curr_sym = (customer.default_currency.symbol if customer.default_currency and customer.default_currency.symbol else "") or get_currency_symbol(curr_code)
            
            debt_str = f"{smart_float(customer.balance)} {curr_sym}" if exposure['has_debt'] else ""
            prepaid_str = f"{smart_float(exposure['available_prepaid'])} {curr_sym}" if exposure['available_prepaid'] > Decimal('0.00') else ""

            return JsonResponse({
                'success': True,
                'id': customer.id,
                'name': customer.name,
                'code': customer.code,
                'can_delete': can_delete,
                'has_debt': exposure['has_debt'],
                'debt_display': debt_str,
                'prepaid_display': prepaid_str,
                'transactions_summary': summary,
            })
        except Exception as e:
            logger.exception(f"خطأ أثناء فحص سجلات العميل {pk}: {e}")
            return JsonResponse({
                'success': False,
                'message': f"حدث خطأ أثناء فحص سجلات العميل: {str(e)}"
            }, status=500)

    # 2. تنفيذ الحذف أو الأرشفة (POST)
    if request.method == "POST":
        try:
            res = CustomerService.delete_or_archive_customer(customer, user=request.user)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'action': res['action'],
                    'message': res['message'],
                    'redirect_url': reverse('client:customer_list'),
                })

            if res['action'] == 'deleted':
                messages.success(request, res['message'])
            else:
                messages.warning(request, res['message'])
            return redirect("client:customer_list")
        except Exception as e:
            logger.exception(f"خطأ أثناء حذف/أرشفة العميل {pk}: {e}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': f"حدث خطأ أثناء تنفيذ الإجراء: {str(e)}"
                }, status=500)
            messages.error(request, f"حدث خطأ أثناء تنفيذ الإجراء: {str(e)}")
            return redirect("client:customer_list")

    # 3. العرض العادي للشاشة المنفصلة (Fallback)
    can_delete, summary, exposure = CustomerService.can_delete_customer(customer)
    context = {
        "customer": customer,
        "can_delete": can_delete,
        "summary": summary,
        "exposure": exposure,
        "page_title": f"حذف / أرشفة العميل: {customer.name}",
        "page_icon": "fas fa-user-times",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "العملاء",
                "url": reverse("client:customer_list"),
                "icon": "fas fa-users",
            },
            {
                "title": customer.name,
                "url": reverse("client:customer_detail", kwargs={"pk": customer.pk}),
            },
            {"title": "حذف / أرشفة", "active": True},
        ],
    }
    return render(request, "client/customer_delete.html", context)


@login_required
def customer_reactivate(request, pk):
    """
    إعادة تنشيط عميل مؤرشف وحسابه المالي التابع
    """
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        res = CustomerService.reactivate_customer(customer, user=request.user)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': res['message']})
        messages.success(request, res['message'])
        return redirect("client:customer_detail", pk=customer.pk)
    return redirect("client:customer_detail", pk=customer.pk)


@login_required
def customer_detail(request, pk):
    """
    عرض تفاصيل العميل والمدفوعات - Updated to use CustomerService
    """
    customer = get_object_or_404(Customer, pk=pk)
    
    # استخدام CustomerService للحصول على الإحصائيات
    customer_stats = customer_service.get_customer_statistics(customer)
    
    # جلب دفعات فواتير المبيعات والدفعات المباشرة/تحت الحساب المرتبطة بالعميل
    from sale.models import SalePayment
    from client.models import CustomerPayment

    sale_payments = list(SalePayment.objects.filter(sale__customer=customer).select_related("sale", "currency", "sale__currency", "created_by").order_by("-payment_date"))
    advance_payments = list(CustomerPayment.objects.filter(customer=customer).select_related("currency", "created_by").order_by("-payment_date"))

    # توحيد قائمة المدفوعات لعرضها في التاب والتصدير
    payments = []
    for sp in sale_payments:
        curr = sp.currency or (sp.sale.currency if sp.sale else None)
        payments.append({
            "id": sp.id,
            "payment_date": sp.payment_date,
            "created_at": sp.created_at,
            "amount": sp.amount,
            "currency": curr,
            "currency_symbol": curr.symbol if curr else "ج.م",
            "payment_method": sp.source_display_info if hasattr(sp, "source_display_info") else sp.get_payment_method_display(),
            "reference_number": sp.reference_number or f"PAY-{sp.id}",
            "notes": sp.notes or "-",
            "sale__number": sp.sale.number if sp.sale else "-",
            "type_display": "سداد فاتورة",
        })

    for cp in advance_payments:
        curr = cp.currency
        payments.append({
            "id": cp.id,
            "payment_date": cp.payment_date,
            "created_at": cp.created_at,
            "amount": cp.amount,
            "currency": curr,
            "currency_symbol": curr.symbol if curr else "ج.م",
            "payment_method": cp.source_display_info if hasattr(cp, "source_display_info") else "رصيد مسبق",
            "reference_number": cp.reference_number or f"CP-{cp.id}",
            "notes": cp.notes or "دفعة من تحت الحساب",
            "sale__number": "دفعة مقدمة (تحت الحساب)",
            "type_display": "دفعة مقدمة",
        })

    payments.sort(key=lambda x: str(x["payment_date"] or ""), reverse=True)

    sale_pay_total = sum(
        sp.amount for sp in sale_payments
        if sp.payment_method != "prepaid_balance" and getattr(sp, "source_type", None) != "PREPAID_BALANCE"
    )
    adv_pay_total = sum(cp.amount for cp in advance_payments)
    total_payments = sale_pay_total + adv_pay_total



    # جلب فواتير البيع المؤكدة المرتبطة بالعميل
    from sale.models import Sale
    invoices = Sale.objects.with_list_details().filter(customer=customer, status="confirmed").order_by("-date")
    invoices_count = invoices.count()

    # جلب طلبات التسعير المرتبطة بالعميل (مؤقتاً معطل)
    pricing_orders = []
    pricing_orders_count = 0

    # جلب عروض الأسعار المرتبطة بالعميل إذا كانت الميزة مفعلة
    from core.models import SystemSetting
    enable_quotations = SystemSetting.get_bool('enable_quotations', False)
    quotations = []
    quotations_count = 0
    quotations_headers = []
    quotations_action_buttons = []
    
    if enable_quotations:
        from sale.models import Quotation
        quotations = Quotation.objects.with_list_details().filter(customer=customer).order_by("-date", "-number")
        quotations_count = quotations.count()
        
        quotations_headers = [
            {
                "key": "id",
                "label": "#",
                "sortable": True,
                "class": "text-center",
                "width": "60px",
            },
            {
                "key": "date",
                "label": "التاريخ",
                "sortable": True,
                "class": "text-center",
                "format": "date",
            },
            {
                "key": "number",
                "label": "رقم العرض",
                "sortable": True,
                "class": "text-center",
                "format": "reference",
                "variant": "highlight-code",
                "app": "sale",
            },
            {
                "key": "valid_until",
                "label": "صلاحية العرض",
                "sortable": True,
                "class": "text-center",
                "format": "date",
            },
            {
                "key": "total",
                "label": "الإجمالي",
                "sortable": True,
                "class": "text-center",
                "format": "currency",
            },
            {
                "key": "status",
                "label": "الحالة",
                "sortable": True,
                "class": "text-center",
                "format": "status",
            },
        ]
        
        quotations_action_buttons = [
            {
                "url": "sale:quotation_detail",
                "icon": "fa-eye",
                "class": "action-view",
                "label": "عرض عرض السعر",
            },
            {
                "url": "sale:quotation_edit",
                "icon": "fa-edit",
                "class": "action-edit",
                "label": "تعديل",
            },
        ]

    # جلب أوامر البيع المرتبطة بالعميل
    from sale.models.sales_models import SalesOrder
    sales_orders = SalesOrder.objects.filter(customer=customer).select_related("warehouse", "salesman").order_by("-order_date", "-id")
    sales_orders_count = sales_orders.count()
    sales_orders_headers = [
        {"key": "id", "label": "#", "sortable": True, "class": "text-center", "width": "60px"},
        {"key": "order_date", "label": "التاريخ", "sortable": True, "class": "text-center", "format": "date"},
        {"key": "order_number", "label": "رقم الأمر", "sortable": True, "class": "text-center", "format": "reference", "variant": "highlight-code", "app": "sale"},
        {"key": "warehouse__name", "label": "المخزن", "sortable": True, "class": "text-center"},
        {"key": "total_amount", "label": "الإجمالي", "sortable": True, "class": "text-center", "format": "currency"},
        {"key": "status", "label": "الحالة", "sortable": True, "class": "text-center", "format": "status"},
    ]
    sales_orders_action_buttons = [
        {"url": "sale:sales_order_detail", "icon": "fa-eye", "class": "action-view", "label": "عرض أمر البيع"},
        {"url": "sale:sales_order_print", "icon": "fa-print", "class": "action-print", "label": "طباعة"},
    ]

    # حساب إجمالي المبيعات
    total_sales = invoices.aggregate(total=Sum("total"))["total"] or 0

    # حساب عدد المنتجات الفريدة في فواتير البيع
    from sale.models import SaleItem
    sale_items = SaleItem.objects.filter(sale__customer=customer)
    total_products = sale_items.values("product").distinct().count()

    # حساب إجمالي الرصيد المسبق المتاح للعميل
    unallocated_prepaid = customer.available_prepaid_balance

    # تاريخ آخر معاملة
    last_transaction_date = None
    if payments or invoices.exists():
        last_payment_date = payments[0]["payment_date"] if payments else None
        last_invoice_date = invoices.first().date if invoices.exists() else None

        if last_payment_date and last_invoice_date:
            last_transaction_date = max(last_payment_date, last_invoice_date)
        elif last_payment_date:
            last_transaction_date = last_payment_date
        else:
            last_transaction_date = last_invoice_date

    # الحصول المباشر على الحساب المالي للعميل
    financial_account = customer.financial_account

    # جلب القيود المحاسبية المرتبطة بالعميل
    from financial.models import JournalEntry
    from django.db.models import Q
    journal_entries = []
    journal_entries_count = 0

    try:
        invoice_ids = [inv.id for inv in invoices]
        query = Q()
        if financial_account:
            query |= Q(lines__account=financial_account)
        for inv_id in invoice_ids:
            query |= Q(reference__icontains=f"SALE-{inv_id}") | Q(reference__icontains=f"{inv_id}")

        if query:
            journal_entries = (
                JournalEntry.objects.filter(query)
                .distinct()
                .prefetch_related("lines")
                .order_by("-date", "-created_at")
            )
            journal_entries_count = journal_entries.count()
    except Exception as e:
        import traceback
        traceback.print_exc()

    # تجهيز بيانات المعاملات لكشف الحساب
    transactions = []

    from core.presenters.currency_exposure_presenter import get_currency_symbol

    # 1. جلب الأرصدة الافتتاحية من الأستاذ المساعد للعميل
    from client.models import CustomerTransaction
    op_txns = CustomerTransaction.objects.filter(
        customer=customer,
        reference_type="OPENING_BALANCE"
    )
    for op_tx in op_txns:
        curr_code = op_tx.currency or "EGP"
        curr_sym = get_currency_symbol(curr_code)
        is_inv = (op_tx.transaction_type == "INVOICE")
        debit_val = op_tx.functional_amount if is_inv else Decimal("0.00")
        credit_val = op_tx.functional_amount if not is_inv else Decimal("0.00")
        f_debit = op_tx.foreign_amount if is_inv else Decimal("0.00")
        f_credit = op_tx.foreign_amount if not is_inv else Decimal("0.00")
        ledger_url = (reverse("financial:ledger_report") + f"?account={customer.financial_account.id}") if customer.financial_account else "#"
        transactions.append({
            "date": op_tx.issue_date,
            "created_at": op_tx.created_at,
            "reference": op_tx.transaction_number,
            "type": "opening_balance",
            "description": f"رصيد افتتاحي مرحل ({op_tx.transaction_number})",
            "currency": curr_code,
            "currency_symbol": curr_sym,
            "debit": debit_val,
            "credit": credit_val,
            "foreign_debit": f_debit,
            "foreign_credit": f_credit,
            "exchange_rate": op_tx.exchange_rate,
            "balance": Decimal("0.00"),
            "foreign_balance": Decimal("0.00"),
            "url": ledger_url,
        })

    # 2. جلب فواتير البيع المؤكدة
    for invoice in invoices:
        curr_code = invoice.currency.code if invoice.currency else "EGP"
        curr_sym = (invoice.currency.symbol if (invoice.currency and invoice.currency.symbol) else None) or get_currency_symbol(curr_code)
        rate = invoice.exchange_rate or Decimal("1.000000")
        func_total = getattr(invoice, 'total_functional', None) or (invoice.total * rate).quantize(Decimal("0.01"))
        inv_url = reverse("sale:sale_detail", kwargs={"pk": invoice.id})
        transactions.append(
            {
                "date": invoice.created_at or invoice.date,
                "reference": invoice.number,
                "invoice_id": invoice.id,
                "type": "invoice",
                "description": f"فاتورة بيع رقم {invoice.number}",
                "currency": curr_code,
                "currency_symbol": curr_sym,
                "debit": func_total,
                "credit": Decimal("0.00"),
                "foreign_debit": invoice.total if curr_code != "EGP" else Decimal("0.00"),
                "foreign_credit": Decimal("0.00"),
                "exchange_rate": rate,
                "balance": Decimal("0.00"),
                "foreign_balance": Decimal("0.00"),
                "url": inv_url,
            }
        )

    # 3. جلب الإشعارات الدائنة المالية المعتمدة والمرحلة
    try:
        from sale.models import CreditNote
        credit_notes = CreditNote.objects.filter(
            customer=customer,
            status__in=['POSTED', 'PARTIALLY_APPLIED', 'FULLY_APPLIED', 'APPROVED']
        )
        for cn in credit_notes:
            curr_code = cn.currency or "EGP"
            curr_sym = get_currency_symbol(curr_code)
            rate = cn.exchange_rate or Decimal("1.000000")
            func_total = (cn.total_amount * rate).quantize(Decimal("0.01"))
            cn_url = reverse("sale:credit_note_detail", kwargs={"pk": cn.id})
            transactions.append({
                "date": cn.created_at,
                "reference": cn.credit_note_number,
                "type": "credit_note",
                "description": f"إشعار دائن رقم {cn.credit_note_number} ({cn.get_source_type_display()})",
                "currency": curr_code,
                "currency_symbol": curr_sym,
                "debit": Decimal("0.00"),
                "credit": func_total,
                "foreign_debit": Decimal("0.00"),
                "foreign_credit": cn.total_amount if curr_code != "EGP" else Decimal("0.00"),
                "exchange_rate": rate,
                "balance": Decimal("0.00"),
                "foreign_balance": Decimal("0.00"),
                "url": cn_url,
            })
    except Exception as e:
        logger.warning(f"Error loading CreditNotes for customer statement: {e}")

    # 4. جلب المدفوعات النقدية والبنكية مع استبعاد سدادات الرصيد المسبق الداخلية
    for sp in sale_payments:
        if sp.payment_method == "prepaid_balance" or getattr(sp, "source_type", None) == "PREPAID_BALANCE":
            continue

        inv_curr = sp.sale.currency.code if (sp.sale and sp.sale.currency) else "EGP"
        pay_curr = sp.payment_currency.code if sp.payment_currency else (sp.currency.code if sp.currency else inv_curr)
        curr_code = inv_curr if inv_curr != "EGP" else pay_curr
        curr_sym = get_currency_symbol(curr_code)
        rate = sp.payment_exchange_rate or (sp.sale.exchange_rate if sp.sale else Decimal("1.000000")) or Decimal("1.000000")

        settled_val = getattr(sp, 'amount_settled_invoice_currency', None)
        if not settled_val or settled_val <= Decimal("0.00"):
            settled_val = sp.amount
        func_val = getattr(sp, 'amount_functional', None)
        if not func_val or func_val <= Decimal("0.00"):
            func_val = (settled_val * rate).quantize(Decimal("0.01"))

        pay_url = reverse("sale:payment_detail", kwargs={"pk": sp.id})
        transactions.append({
            "date": sp.created_at or sp.payment_date,
            "reference": sp.reference_number or f"PAY-{sp.id}",
            "type": "payment",
            "description": f"سداد فاتورة ({sp.sale.number if sp.sale else '-'}) - {sp.source_display_info if hasattr(sp, 'source_display_info') else sp.get_payment_method_display()}",
            "currency": curr_code,
            "currency_symbol": curr_sym,
            "debit": Decimal("0.00"),
            "credit": func_val,
            "foreign_debit": Decimal("0.00"),
            "foreign_credit": settled_val if curr_code != "EGP" else Decimal("0.00"),
            "exchange_rate": rate,
            "balance": Decimal("0.00"),
            "foreign_balance": Decimal("0.00"),
            "url": pay_url,
        })

    for cp in advance_payments:
        curr_code = cp.currency.code if cp.currency else "EGP"
        curr_sym = get_currency_symbol(curr_code)
        rate = getattr(cp, 'exchange_rate', Decimal("1.000000")) or Decimal("1.000000")
        amt = Decimal(str(cp.amount or "0.00"))
        func_amt = (amt * rate).quantize(Decimal("0.01"))
        cp_url = (reverse("financial:ledger_report") + f"?account={customer.financial_account.id}") if customer.financial_account else "#"

        transactions.append({
            "date": cp.created_at or cp.payment_date,
            "reference": cp.reference_number or f"CP-{cp.id}",
            "type": "payment",
            "description": f"دفعة مقدمة تحت الحساب ({cp.source_display_info if hasattr(cp, 'source_display_info') else 'رصيد مسبق'})",
            "currency": curr_code,
            "currency_symbol": curr_sym,
            "debit": Decimal("0.00"),
            "credit": func_amt,
            "foreign_debit": Decimal("0.00"),
            "foreign_credit": amt if curr_code != "EGP" else Decimal("0.00"),
            "exchange_rate": rate,
            "balance": Decimal("0.00"),
            "foreign_balance": Decimal("0.00"),
            "url": cp_url,
        })

    # 5. جلب قيود التسوية اليدوية المباشرة على حساب العميل (Direct Manual JVs)
    if financial_account:
        try:
            from financial.models.journal_entry import JournalEntryLine
            manual_lines = JournalEntryLine.objects.filter(
                account=financial_account,
                journal_entry__status='posted'
            ).exclude(
                journal_entry__reference__istartswith='SALE-'
            ).exclude(
                journal_entry__reference__istartswith='PAY-'
            ).exclude(
                journal_entry__reference__istartswith='OPN-'
            ).exclude(
                journal_entry__reference__istartswith='REV-'
            ).select_related('journal_entry')

            for jl in manual_lines:
                curr_code = str(jl.currency or "EGP")
                curr_sym = get_currency_symbol(curr_code)
                rate = jl.exchange_rate or Decimal("1.000000")
                func_dr = jl.debit or Decimal("0.00")
                func_cr = jl.credit or Decimal("0.00")
                f_dr = jl.foreign_debit if (jl.foreign_debit and jl.foreign_debit > 0) else (func_dr if curr_code != "EGP" else Decimal("0.00"))
                f_cr = jl.foreign_credit if (jl.foreign_credit and jl.foreign_credit > 0) else (func_cr if curr_code != "EGP" else Decimal("0.00"))
                jv_url = reverse("financial:journal_entries_detail", kwargs={"pk": jl.journal_entry.id})

                transactions.append({
                    "date": jl.journal_entry.date,
                    "reference": jl.journal_entry.number or f"JV-{jl.journal_entry.id}",
                    "type": "manual_jv",
                    "description": f"تسوية قيد يومية: {jl.description or jl.journal_entry.description or jl.journal_entry.number}",
                    "currency": curr_code,
                    "currency_symbol": curr_sym,
                    "debit": func_dr,
                    "credit": func_cr,
                    "foreign_debit": f_dr,
                    "foreign_credit": f_cr,
                    "exchange_rate": rate,
                    "balance": Decimal("0.00"),
                    "foreign_balance": Decimal("0.00"),
                    "url": jv_url,
                })
        except Exception as e:
            logger.warning(f"Error loading manual JVs for customer statement: {e}")

    # 6. استخراج كافة العملات المتاحة وتحديد العملة النشطة
    all_currencies_set = set()
    for t in transactions:
        if t.get("currency"):
            all_currencies_set.add(t["currency"])
    
    available_currencies = sorted(list(all_currencies_set))
    
    req_curr = request.GET.get("currency", "").strip().upper()
    if req_curr and (req_curr in available_currencies or req_curr == "ALL"):
        active_currency = req_curr
    elif len(available_currencies) == 1 and available_currencies[0] != "EGP":
        active_currency = available_currencies[0]
    elif len(available_currencies) == 1 and available_currencies[0] == "EGP":
        active_currency = "EGP"
    else:
        active_currency = "ALL"

    # 7. تصفية الحركات حسب العملة النشطة
    if active_currency not in ["ALL", ""]:
        filtered_transactions = [t for t in transactions if t.get("currency") == active_currency]
    else:
        filtered_transactions = transactions

    # 8. الترتيب الزمني الهرمي لحركات اليوم الواحد
    def get_txn_sort_key(t):
        t_date = t.get("date")
        if hasattr(t_date, "strftime"):
            date_str = t_date.strftime("%Y-%m-%d")
            time_str = t_date.strftime("%H:%M:%S") if hasattr(t_date, "hour") else "00:00:00"
        else:
            d_str = str(t_date or "")[:19]
            date_str = d_str[:10]
            time_str = d_str[11:19] if len(d_str) >= 19 else "00:00:00"

        t_type = t.get("type")
        if t_type in ["opening_balance", "balance_bf"]:
            priority = 1
        elif t_type in ["invoice", "purchase"]:
            priority = 2
        elif t_type == "manual_jv":
            priority = 3
        elif t_type == "payment":
            priority = 4
        else:
            priority = 5

        return (date_str, priority, time_str, str(t.get("reference", "")))

    filtered_transactions.sort(key=get_txn_sort_key)

    # 9. احتساب الرصيد التراكمي المزدوج بأمان
    running_balance = Decimal("0.00")
    running_foreign_balance = Decimal("0.00")
    for t in filtered_transactions:
        running_balance = running_balance + Decimal(str(t["debit"])) - Decimal(str(t["credit"]))
        running_foreign_balance = running_foreign_balance + Decimal(str(t.get("foreign_debit", 0))) - Decimal(str(t.get("foreign_credit", 0)))
        t["balance"] = running_balance
        t["foreign_balance"] = running_foreign_balance

    filtered_transactions.reverse()

    # تعريف أعمدة جدول الفواتير للنظام المحسن
    invoices_headers = [
        {
            "key": "id",
            "label": "#",
            "sortable": True,
            "class": "text-center",
            "width": "60px",
        },
        {
            "key": "created_at",
            "label": "التاريخ",
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
        },
        {
            "key": "number",
            "label": "رقم الفاتورة",
            "sortable": True,
            "class": "text-center",
            "format": "reference",
            "variant": "highlight-code",
            "app": "sale",
        },
        {
            "key": "total",
            "label": "المبلغ",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
        },
        {
            "key": "amount_paid",
            "label": "المدفوع",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
        },
        {
            "key": "amount_due",
            "label": "المتبقي",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "variant": "negative",
        },
        {
            "key": "payment_status",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "format": "status",
        },
    ]

    # تعريف أزرار الإجراءات لجدول الفواتير
    invoices_action_buttons = [
        {
            "url": "sale:sale_detail",
            "icon": "fa-eye",
            "class": "action-view",
            "label": "عرض الفاتورة",
        },
        {
            "url": "sale:sale_add_payment",
            "icon": "fa-money-bill",
            "class": "action-paid",
            "label": "إضافة دفعة",
            "condition": "not_fully_paid",
        },
    ]

    # تعريف أعمدة جدول المدفوعات للنظام المحسن
    payments_headers = [
        {
            "key": "id",
            "label": "#",
            "sortable": True,
            "class": "text-center",
            "width": "50px",
        },
        {
            "key": "created_at",
            "label": "التاريخ",
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
            "width": "140px",
        },
        {
            "key": "sale__number",
            "label": "رقم الفاتورة",
            "sortable": True,
            "class": "text-center text-nowrap",
            "template": "components/cells/invoice_reference.html",
            "width": "150px",
        },
        {
            "key": "amount",
            "label": "المبلغ",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/payment_amount.html",
            "width": "120px",
        },
        {
            "key": "payment_method",
            "label": "طريقة الدفع",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/payment_method.html",
            "width": "120px",
        },
        {"key": "notes", "label": "ملاحظات", "sortable": False, "class": "text-start"},
    ]

    # تعريف أعمدة جدول القيود المحاسبية للنظام المحسن
    journal_headers = [
        {
            "key": "id",
            "label": "#",
            "sortable": True,
            "class": "text-center",
            "width": "50px",
        },
        {
            "key": "number",
            "label": "رقم القيد",
            "sortable": True,
            "class": "text-center",
            "width": "140px",
        },
        {
            "key": "created_at",
            "label": "التاريخ",
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
            "width": "140px",
        },
        {
            "key": "status",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/journal_status.html",
            "width": "90px",
        },
        {
            "key": "reference",
            "label": "المرجع",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/journal_reference.html",
            "width": "150px",
        },
        {
            "key": "description",
            "label": "الوصف",
            "sortable": False,
            "class": "text-start",
        },
        {
            "key": "total_amount",
            "label": "المبلغ",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/journal_amount.html",
            "width": "110px",
        },
    ]

    # أزرار إجراءات القيود المحاسبية
    journal_action_buttons = []

    # تعريف أعمدة جدول كشف الحساب للنظام المحسن
    statement_headers = [
        {
            "key": "date",
            "label": "التاريخ",
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
            "width": "140px",
        },
        {
            "key": "reference",
            "label": "المرجع",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/statement_reference.html",
            "width": "120px",
        },
        {
            "key": "type",
            "label": "نوع الحركة",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/statement_type.html",
            "width": "100px",
        },
        {
            "key": "description",
            "label": "الوصف",
            "sortable": True,
            "class": "text-center",
        },
        {
            "key": "debit",
            "label": "مدين",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/statement_debit.html",
            "width": "120px",
        },
        {
            "key": "credit",
            "label": "دائن",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/statement_credit.html",
            "width": "120px",
        },
        {
            "key": "balance",
            "label": "الرصيد",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/statement_balance.html",
            "width": "120px",
        },
    ]

    # تعريف أعمدة جدول طلبات التسعير للنظام المحسن
    pricing_orders_headers = [
        {
            "key": "id",
            "label": "#",
            "sortable": True,
            "class": "text-center",
            "width": "60px",
        },
        {
            "key": "order_number",
            "label": "رقم الطلب",
            "sortable": True,
            "class": "text-center",
            "width": "120px",
        },
        {
            "key": "title",
            "label": "عنوان الطلب",
            "sortable": True,
            "class": "text-start",
        },
        {
            "key": "order_type",
            "label": "نوع الطلب",
            "sortable": True,
            "class": "text-center",
            "width": "100px",
        },
        {
            "key": "status",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "width": "100px",
        },
        {
            "key": "quantity",
            "label": "الكمية",
            "sortable": True,
            "class": "text-center",
            "width": "80px",
        },
        {
            "key": "created_at",
            "label": "تاريخ الطلب",
            "sortable": True,
            "class": "text-center",
            "format": "date",
            "width": "120px",
        },
        {
            "key": "required_delivery_date",
            "label": "تاريخ التسليم",
            "sortable": True,
            "class": "text-center",
            "format": "date",
            "width": "120px",
        },
    ]

    # تعريف أزرار إجراءات جدول طلبات التسعير
    pricing_orders_action_buttons = [
        {
            "url": "printing_pricing:order_detail",
            "icon": "fa-eye",
            "class": "action-view",
            "label": "عرض",
        },
        {
            "url": "printing_pricing:order_update",
            "icon": "fa-edit",
            "class": "action-edit",
            "label": "تعديل",
        },
        {
            "url": "printing_pricing:order_delete",
            "icon": "fa-trash",
            "class": "action-delete",
            "label": "حذف",
        },
    ]

    # أزرار الإجراءات السريعة للعميل
    quick_action_buttons = [
        {
            "url": reverse("sale:sale_create_for_customer", kwargs={"customer_id": customer.id}),
            "icon": "fas fa-plus-circle",
            "label": "إنشاء فاتورة مبيعات",
            "class": "btn btn-success",
            "title": "إنشاء فاتورة مبيعات جديدة لهذا العميل"
        },
        {
            "url": reverse("client:customer_edit", kwargs={"pk": customer.pk}),
            "icon": "fas fa-edit",
            "label": "تعديل بيانات العميل",
            "class": "btn btn-primary",
            "title": "تعديل بيانات العميل"
        },
    ]

    # حساب الرصيد المتاح (credit_limit - المديونية الفعلية)
    # المديونية = إجمالي المبيعات - إجمالي المدفوعات (فواتير + تحت الحساب)
    actual_debt = total_sales - total_payments
    available_credit = customer.credit_limit - actual_debt if customer.credit_limit else 0
    
    context = {
        "customer": customer,
        "available_credit": available_credit,
        "quick_action_buttons": quick_action_buttons,
        "payments": payments,
        "invoices": invoices,
        "sale_invoices": invoices,
        "invoices_count": invoices_count,
        "pricing_orders": pricing_orders,
        "pricing_orders_count": pricing_orders_count,
        "total_payments": total_payments,
        "total_sales": total_sales,
        "total_products": total_products,
        "transactions": filtered_transactions,
        "available_currencies": available_currencies,
        "active_currency": active_currency,
        "journal_entries": journal_entries,
        "journal_entries_count": journal_entries_count,
        "financial_account": financial_account,
        "invoices_headers": invoices_headers,  # أعمدة جدول الفواتير
        "invoices_action_buttons": invoices_action_buttons,  # أزرار إجراءات الفواتير
        "payments_headers": payments_headers,  # أعمدة جدول المدفوعات
        "journal_headers": journal_headers,  # أعمدة جدول القيود المحاسبية
        "journal_action_buttons": journal_action_buttons,  # أزرار إجراءات القيود
        "statement_headers": statement_headers,  # أعمدة جدول كشف الحساب
        "pricing_orders_headers": pricing_orders_headers,  # أعمدة جدول طلبات التسعير
        "pricing_orders_action_buttons": pricing_orders_action_buttons,  # أزرار إجراءات طلبات التسعير
        "primary_key": "id",  # المفتاح الأساسي للجداول
        "enable_quotations": enable_quotations,
        "quotations": quotations,
        "quotations_count": quotations_count,
        "quotations_headers": quotations_headers,
        "quotations_action_buttons": quotations_action_buttons,
        "quotations_clickable": True,
        "quotations_click_url": "sale:quotation_detail",
        "sales_orders": sales_orders,
        "sales_orders_count": sales_orders_count,
        "sales_orders_headers": sales_orders_headers,
        "sales_orders_action_buttons": sales_orders_action_buttons,
        "sales_orders_clickable": True,
        "sales_orders_click_url": "sale:sales_order_detail",
        # إعدادات الصفوف القابلة للنقر
        "invoices_clickable": True,
        "invoices_click_url": "sale:sale_detail",
        "payments_clickable": True,
        "payments_click_url": "sale:payment_detail",
        "journal_clickable": True,
        "journal_click_url": "financial:journal_entries_detail",
        # بيانات الهيدر
        "page_title": f"{customer.name}",
        "page_subtitle": "معلومات وبيانات العميل الكاملة",
        "page_icon": "fas fa-user",
        "unallocated_prepaid": unallocated_prepaid,
    }

    from financial.models import ChartOfAccounts
    from django.db.models import Q
    context["financial_accounts"] = list(
        ChartOfAccounts.objects.filter(
            Q(is_cash_account=True) | Q(is_bank_account=True) | Q(code__startswith="101"),
            is_active=True
        ).order_by("code")
    )

    from core.models import SystemSetting
    currency_symbol = SystemSetting.get_currency_symbol()

    # Badges في الهيدر
    header_badges = [
        {
            "text": f"{customer.code}",
            "class": "bg-primary",
            "icon": "fas fa-hashtag",
        },
    ]

    from financial.services.partner_exposure_service import BusinessPartnerExposureService
    from core.presenters.currency_exposure_presenter import CurrencyExposurePresenter

    customer_dtos = BusinessPartnerExposureService.get_open_balances("customer", [customer.id]).get(customer.id, [])
    from django.utils.safestring import mark_safe
    vms = CurrencyExposurePresenter.build_view_models(customer_dtos)
    if vms:
        vms_sorted = sorted(vms, key=lambda vm: 0 if (getattr(vm, 'currency_symbol', '') == 'ج.م' or getattr(vm, 'currency_code', '') == 'EGP' or getattr(vm, 'currency', '') == 'EGP') else 1)
        debt_parts = [f'<span class="badge-amount-pill">{vm.formatted_amount} {vm.currency_symbol}</span>' for vm in vms_sorted]
        header_badges.append({
            "is_badge": True,
            "icon": "fas fa-hand-holding-usd",
            "text": mark_safe(f"مطلوب: {' '.join(debt_parts)}"),
            "class": "bg-danger text-white",
            "title": "إجمالي الفواتير المستحقة على العميل حسب العملات",
        })
    elif customer.actual_balance != Decimal("0.00"):
        header_badges.append({
            "text": mark_safe(f"المديونية: <span class=\"badge-amount-pill\">{smart_float(customer.actual_balance)} {currency_symbol}</span>"),
            "class": "bg-success" if customer.actual_balance <= 0 else "bg-danger",
            "icon": "fas fa-arrow-down" if customer.actual_balance <= 0 else "fas fa-arrow-up",
        })

    from financial.services.partner_advance_service import PartnerAdvanceService
    prepaid_bals = PartnerAdvanceService.get_all_balances(customer)

    prepaid_parts = []
    sorted_prepaid = sorted(
        prepaid_bals.items(),
        key=lambda item: 0 if item[0] == "EGP" else 1
    )
    for curr_code, item in sorted_prepaid:
        bal = item["balance"] if isinstance(item, dict) else item
        sym = item.get("symbol", curr_code) if isinstance(item, dict) else curr_code
        if bal > Decimal("0.00"):
            prepaid_parts.append(f'<span class="badge-amount-pill">{smart_float(bal)} {sym}</span>')

    if prepaid_parts:
        header_badges.append({
            "text": mark_safe(f"رصيد مسبق: {' '.join(prepaid_parts)}"),
            "class": "bg-success text-white",
            "icon": "fas fa-wallet",
            "title": "إجمالي الأرصدة المسبقة المتاحة حسب العملات",
            "action_text": "توزيع",
            "action_icon": "fas fa-random",
            "action_class": "bg-success-subtle text-success border border-success-subtle",
            "action_onclick": "const m = document.getElementById('prepaidAllocationModal'); if(m){ new bootstrap.Modal(m).show(); }",
            "action_title": "توزيع الرصيد المسبق على الفواتير المفتوحة",
        })

    context["prepaid_balances"] = prepaid_bals
    if not customer.is_active:
        context["header_badges"] = [
            {
                "text": "عميل مؤرشف ومعطل",
                "class": "bg-warning text-dark fw-bold",
                "icon": "fas fa-archive",
                "title": "هذا العميل غير نشط ومؤرشف",
            }
        ]
        context["header_buttons"] = [
            {
                "url": "#",
                "icon": "fa-undo",
                "text": "إعادة تنشيط العميل",
                "class": "btn-success fw-bold",
                "id": "btn-reactivate-customer",
                "onclick": "const f = document.getElementById('reactivate-customer-form'); if(f) { f.submit(); } else { const nf = document.createElement('form'); nf.method='POST'; nf.action='" + reverse('client:customer_reactivate', kwargs={'pk': customer.pk}) + "'; const c = document.querySelector('[name=csrfmiddlewaretoken]'); if(c) { const i = document.createElement('input'); i.type='hidden'; i.name='csrfmiddlewaretoken'; i.value=c.value; nf.appendChild(i); } document.body.appendChild(nf); nf.submit(); }",
                "title": "إعادة تنشيط العميل وحسابه المالي",
            }
        ]
    else:
        context["header_badges"] = header_badges
        context["header_buttons"] = [
            {
                "url": "#",
                "icon": "fa-plus-circle",
                "text": "تحصيل رصيد مسبق",
                "class": "btn-primary",
                "toggle": "modal",
                "target": "#addCustomerAdvanceModal",
                "title": "تحصيل رصيد مسبق / دفعة مقدمة من العميل",
            },
            {
                "url": reverse("sale:sale_create_for_customer", kwargs={"customer_id": customer.id}),
                "icon": "fa-file-invoice-dollar",
                "text": "فاتورة بيع",
                "class": "btn-success",
            },
            {
                "url": "#",
                "icon": "fa-ellipsis-v",
                "text": "",
                "class": "btn-outline-secondary",
                "id": "actions-menu-btn",
                "toggle": "modal",
                "target": "#actionsModal",
            },
        ]
    context["breadcrumb_items"] = [
        {
            "title": "الرئيسية",
            "url": reverse("core:dashboard"),
            "icon": "fas fa-home",
        },
        {
            "title": "العملاء",
            "url": reverse("client:customer_list"),
            "icon": "fas fa-users",
        },
        {"title": customer.name, "active": True},
    ]

    from financial.services.partner_advance_service import PartnerAdvanceService
    from financial.models import Currency
    context["prepaid_balances"] = PartnerAdvanceService.get_all_balances(customer)
    context["currencies"] = Currency.objects.filter(is_active=True)

    return render(request, "client/customer_detail.html", context)


@login_required
def customer_change_account(request, pk):
    """
    تغيير الحساب المحاسبي للعميل
    """
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == "POST":
        form = CustomerAccountChangeForm(request.POST, instance=customer)
        if form.is_valid():
            old_account = customer.financial_account
            form.save()

            # رسالة تأكيد
            if old_account:
                messages.success(
                    request,
                    f'تم تغيير الحساب المحاسبي من "{old_account.name}" إلى "{customer.financial_account.name}" بنجاح',
                )
            else:
                messages.success(
                    request,
                    f'تم ربط العميل بالحساب المحاسبي "{customer.financial_account.name}" بنجاح',
                )

            return redirect("client:customer_detail", pk=customer.pk)
    else:
        form = CustomerAccountChangeForm(instance=customer)

    context = {
        "form": form,
        "customer": customer,
        "page_title": f"تغيير الحساب المحاسبي للعميل: {customer.name}",
        "page_subtitle": "ربط العميل بحساب محاسبي أو تغيير الحساب الحالي",
        "page_icon": "fas fa-exchange-alt",
        "header_buttons": [
            {
                "url": reverse("client:customer_detail", kwargs={"pk": customer.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة للعميل",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "العملاء",
                "url": reverse("client:customer_list"),
                "icon": "fas fa-users",
            },
            {
                "title": customer.name,
                "url": reverse("client:customer_detail", kwargs={"pk": customer.pk}),
            },
            {"title": "تغيير الحساب المحاسبي", "active": True},
        ],
    }

    return render(request, "client/customer_change_account.html", context)


@login_required
def customer_create_account(request, pk):
    """
    إنشاء حساب محاسبي جديد للعميل (AJAX)
    """
    customer = get_object_or_404(Customer, pk=pk)
    
    # التحقق من أن العميل لا يملك حساب بالفعل
    if customer.financial_account:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False, 
                'message': f'العميل "{customer.name}" مربوط بالفعل بحساب محاسبي'
            })
        messages.warning(request, f'العميل "{customer.name}" مربوط بالفعل بحساب محاسبي')
        return redirect("client:customer_change_account", pk=customer.pk)
    
    if request.method == "POST":
        try:
            from client.services.customer_service import CustomerService
            new_account = CustomerService.create_financial_account_for_customer(customer, user=request.user)
            
            if not new_account:
                error_msg = "فشل في إنشاء الحساب المحاسبي للعميل"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                messages.error(request, error_msg)
                return redirect("client:customer_change_account", pk=customer.pk)
            
            customer.financial_account = new_account
            success_msg = f'تم إنشاء حساب محاسبي جديد "{new_account.code} - {new_account.name}" وربطه بالعميل بنجاح'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_msg})
            
            messages.success(request, success_msg)
            return redirect("client:customer_detail", pk=customer.pk)
            
        except Exception as e:
            error_msg = f"حدث خطأ أثناء إنشاء الحساب: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            messages.error(request, error_msg)
            return redirect("client:customer_change_account", pk=customer.pk)
    
    # للطلبات GET - إرجاع مودال التأكيد
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('client/customer_create_account_modal.html', {
            'customer': customer
        }, request=request)
        return JsonResponse({'html': html})
    
    # إعادة توجيه للصفحة العادية
    return redirect("client:customer_change_account", pk=customer.pk)


@login_required
def customer_add_ajax(request):
    """
    إضافة عميل جديد عبر AJAX وتوليد الكود تلقائياً
    """
    if request.method == "POST":
        form = CustomerForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                customer = form.save(user=request.user)
                return JsonResponse({
                    'success': True,
                    'customer': {
                        'id': customer.pk,
                        'name': customer.name,
                        'phone': customer.phone,
                        'code': customer.code,
                        'currency_id': customer.default_currency_id,
                        'currency_code': customer.default_currency.code if customer.default_currency else 'EGP'
                    },
                    'message': _('تم إضافة العميل بنجاح')
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f"خطأ في إضافة العميل: {str(e)}"
                })
        else:
            errors = {}
            for field, field_errors in form.errors.items():
                errors[field] = [str(err) for err in field_errors]
            return JsonResponse({
                'success': False,
                'errors': errors,
                'message': 'يرجى تصحيح الأخطاء في النموذج.'
            })
    
    # GET request - return next generated code
    last_customer = Customer.objects.filter(
        code__startswith='CUST'
    ).order_by('-id').first()
    new_number = 1
    if last_customer and last_customer.code:
        try:
            digits = ''.join(filter(str.isdigit, last_customer.code))
            if digits:
                new_number = int(digits) + 1
        except Exception:
            pass
    code = f'CUST{new_number:04d}'
    return JsonResponse({
        'success': True,
        'code': code
    })


@login_required
def customer_aging_api(request, pk):
    """
    API لكشف شرائح أعمار ديون العميل الكسول (Lazy Aging Buckets)
    """
    customer = get_object_or_404(Customer, pk=pk)
    from client.services.customer_aging_service import CustomerAgingService
    aging_data = CustomerAgingService.get_customer_aging_report(customer_ids=[customer.id])
    rows = aging_data.get('rows', [])
    row = rows[0] if rows else {}
    return JsonResponse({
        'success': True,
        'aging': {
            'bucket_current': float(row.get('bucket_current') or 0),
            'bucket_0_30': float(row.get('bucket_0_30') or 0),
            'bucket_31_60': float(row.get('bucket_31_60') or 0),
            'bucket_61_90': float(row.get('bucket_61_90') or 0),
            'bucket_90_plus': float(row.get('bucket_90_plus') or 0),
            'credit_balance': float(row.get('credit_balance') or 0),
            'total_balance': float(row.get('total_balance') or 0),
        }
    })


@login_required
def add_customer_advance_action(request, pk):
    """
    إضافة رصيد مسبق / مقبوضات مقدمة جديدة للعميل باختيار العملة وسعر الصرف
    """
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        from decimal import Decimal
        from financial.models import Currency
        from financial.services.partner_advance_service import PartnerAdvanceService

        amount_str = request.POST.get("amount")
        currency_id = request.POST.get("currency")
        rate_str = request.POST.get("exchange_rate_snapshot")
        payment_date_str = request.POST.get("payment_date")
        payment_method = request.POST.get("payment_method", "cash")
        financial_account_id = request.POST.get("financial_account")
        reference_number = request.POST.get("reference_number")
        notes = request.POST.get("notes")

        if amount_str:
            try:
                amt = Decimal(amount_str)
                fin_acc_id = int(financial_account_id) if (financial_account_id and str(financial_account_id).isdigit()) else None
                from financial.services.exchange_rate_service import ExchangeRateService
                curr = Currency.objects.filter(pk=currency_id).first() if currency_id else None
                if not curr:
                    curr = ExchangeRateService.get_functional_currency()
                rate = ExchangeRateService.get_exchange_rate(curr) if curr else Decimal("1.000000")

                payment = CustomerPayment.objects.create(
                    customer=customer,
                    amount=amt,
                    transaction_amount=amt,
                    currency=curr,
                    exchange_rate_snapshot=rate,
                    payment_date=payment_date_str if payment_date_str else timezone.now().date(),
                    payment_method=payment_method,
                    financial_account_id=fin_acc_id,
                    reference_number=reference_number,
                    notes=notes,
                    status="posted",
                    created_by=request.user,
                )
                PartnerAdvanceService.rebuild_snapshot(customer, currency=curr)
                messages.success(request, f"تم تحصيل رصيد مسبق بقيمة {amt} {curr.code if curr else ''} من العميل بنجاح (مرجع #{payment.id}).")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء تحصيل الرصيد المسبق: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء تحصيل الرصيد المسبق: {str(e)}")
        else:
            messages.error(request, "يرجى إدخال مبلغ الرصيد المسبق بشكل صحيح.")

    return redirect("client:customer_detail", pk=pk)


@login_required
def allocate_customer_prepaid(request, pk):
    """
    تخصيص الرصيد المسبق للعميل على الفواتير المفتوحة (تخصيص جماعي أو فردي)
    """
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        from client.services.customer_allocation_audit_service import CustomerAllocationAuditService
        from financial.services.partner_advance_service import PartnerAdvanceService
        from decimal import Decimal

        sale_ids = request.POST.getlist("sale_ids[]") or request.POST.getlist("sale_ids")
        amounts = request.POST.getlist("amounts[]") or request.POST.getlist("amounts")

        allocations_dict = {}
        if sale_ids and amounts and len(sale_ids) == len(amounts):
            for sid, amt_s in zip(sale_ids, amounts):
                if sid and amt_s:
                    try:
                        d_amt = Decimal(str(amt_s))
                        if d_amt > Decimal("0.00"):
                            allocations_dict[int(sid)] = d_amt
                    except Exception:
                        pass

        if allocations_dict:
            try:
                audits = CustomerAllocationAuditService.allocate_prepaid_bulk(
                    customer_id=customer.id,
                    allocations_dict=allocations_dict,
                    user=request.user
                )
                total_alloc = sum(a.allocated_amount for a in audits)
                PartnerAdvanceService.rebuild_all_snapshots(customer)
                messages.success(request, f"تم التوزيع الجماعي بقيمة إجمالية {total_alloc} على {len(audits)} معاملة بنجاح.")
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء التوزيع الجماعي: {str(e)}")
        else:
            sale_id = request.POST.get("sale_id")
            amount_str = request.POST.get("amount")

            if sale_id:
                from sale.models import Sale
                sale = get_object_or_404(Sale, pk=sale_id, customer=customer)
                avail = customer.available_prepaid_balance
                alloc = Decimal(amount_str) if amount_str else min(avail, sale.amount_due)
                if alloc <= Decimal("0.00"):
                    messages.error(request, "يرجى إدخال مبلغ تخصيص أكبر من صفر.")
                elif alloc > avail:
                    messages.error(request, f"المبلغ المطلوب ({alloc}) يتجاوز الرصيد المسبق المتاح ({avail}).")
                else:
                    try:
                        CustomerAllocationAuditService.allocate_customer_prepaid_balance_to_sale(
                            sale=sale,
                            amount_to_allocate=alloc,
                            user=request.user
                        )
                        PartnerAdvanceService.rebuild_all_snapshots(customer)
                        messages.success(request, f"تم تخصيص {alloc} من الرصيد المسبق على الفاتورة #{sale.number} بنجاح.")
                    except Exception as e:
                        messages.error(request, f"حدث خطأ أثناء التخصيص: {str(e)}")

    return redirect("client:customer_detail", pk=pk)


