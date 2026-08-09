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
    status = request.GET.get('status', '')
    has_debt = request.GET.get('has_debt', '')
    search = request.GET.get('search', '')

    customers_qs = Customer.objects.all().order_by('-created_at')

    if status == 'active':
        customers_qs = customers_qs.filter(is_active=True)
    elif status == 'inactive':
        customers_qs = customers_qs.filter(is_active=False)

    if search:
        customers_qs = customers_qs.filter(
            Q(name__icontains=search) |
            Q(phone_primary__icontains=search) |
            Q(phone__icontains=search) |
            Q(code__icontains=search)
        )

    if has_debt == '1':
        customers_qs = customers_qs.filter(balance__gt=0)
    elif has_debt == '0':
        customers_qs = customers_qs.filter(balance__lte=0)

    # التصدير المزدوج: تصدير كافة البيانات المفلترة من الباك إند
    if request.GET.get('export') == 'excel':
        from utils.export import export_queryset_to_excel
        return export_queryset_to_excel(
            customers_qs,
            filename="customers_export.xlsx",
            fields=["code", "name", "phone", "address", "balance", "is_active"],
            headers=["الكود", "اسم العميل", "رقم الهاتف", "العنوان", "المديونية", "نشط"]
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
            "key": "actual_balance_display",
            "label": "المديونية",
            "sortable": True,
            "format": "html",
            "class": "text-center",
        },
        {"key": "is_active", "label": "الحالة", "sortable": True, "format": "boolean"},
    ]

    # تعريف أزرار الإجراءات
    action_buttons = [
        {
            "url": "client:customer_detail",
            "icon": "fa-eye",
            "class": "action-view",
            "label": "عرض",
        },
        {
            "url": "client:customer_edit",
            "icon": "fa-pen",
            "class": "action-edit",
            "label": "تعديل",
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
    from core.presenters.currency_exposure_presenter import CurrencyExposurePresenter

    page_customer_ids = [c.pk for c in page_obj]
    exposure_map = BusinessPartnerExposureService.get_open_balances("customer", page_customer_ids)

    for c in page_obj:
        customer_dtos = exposure_map.get(c.pk, [])
        c.actual_balance_display = CurrencyExposurePresenter.render_html_badges(customer_dtos)

    customers = page_obj

    from core.models import SystemSetting
    daftra_enabled = SystemSetting.get_setting('daftra_enabled', 'false') == 'true'
    header_buttons = [
        {
            "url": reverse("client:customer_add"),
            "icon": "fa-plus",
            "text": "إضافة عميل",
            "class": "btn-primary",
        },
    ]
    if daftra_enabled:
        header_buttons.append({
            "onclick": "syncWithDaftra('clients')",
            "icon": "fa-sync",
            "text": "مزامنة دفترة",
            "class": "btn-outline-info",
        })

    context = {
        **pagination_data,
        'customers': customers,
        'headers': headers,
        'action_buttons': action_buttons,
        'active_customers': active_customers,
        'inactive_customers': inactive_customers,
        'total_debt': total_debt,
        'show_export': True,
        'page_title': "قائمة العملاء",
        'page_subtitle': "إدارة العملاء وعرض بياناتهم ومعاملاتهم المالية",
        'page_icon': "fas fa-users",
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "العملاء", "active": True},
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
    إضافة عميل جديد - Updated to use CustomerService
    """
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            try:
                # استخدام CustomerService لإنشاء العميل
                # الحساب المحاسبي سيتم إنشاؤه تلقائياً عبر post_save signal
                customer = customer_service.create_customer(
                    name=form.cleaned_data['name'],
                    code=form.cleaned_data['code'],
                    user=request.user,
                    phone=form.cleaned_data.get('phone', ''),
                    email=form.cleaned_data.get('email', ''),
                    address=form.cleaned_data.get('address', ''),
                    credit_limit=form.cleaned_data.get('credit_limit', 0),
                    tax_number=form.cleaned_data.get('tax_number', ''),
                    notes=form.cleaned_data.get('notes', '')
                )
                messages.success(request, _("تم إضافة العميل بنجاح"))
                return redirect("client:customer_detail", pk=customer.pk)
            except Exception as e:
                messages.error(request, f"خطأ في إضافة العميل: {str(e)}")
    else:
        form = CustomerForm()

    context = {
        "form": form,
        "page_title": "إضافة عميل جديد",
        "page_subtitle": "إضافة عميل جديد إلى قاعدة بيانات النظام",
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
    تعديل بيانات عميل - Updated to use CustomerService
    """
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            try:
                # استخدام CustomerService لتحديث العميل
                update_fields = {
                    key: value for key, value in form.cleaned_data.items()
                    if key != 'financial_account'  # لا نحدث الحساب المالي هنا
                }
                customer_service.update_customer(
                    customer=customer,
                    user=request.user,
                    **update_fields
                )
                messages.success(request, _("تم تعديل بيانات العميل بنجاح"))
                return redirect("client:customer_detail", pk=customer.pk)
            except Exception as e:
                messages.error(request, f"خطأ في تعديل العميل: {str(e)}")
    else:
        form = CustomerForm(instance=customer)

    context = {
        "form": form,
        "customer": customer,
        "page_title": f"تعديل بيانات العميل: {customer.name}",
        "page_subtitle": "تعديل بيانات العميل وإدارة حساباته",
        "page_icon": "fas fa-user-edit",
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
    حذف عميل (تعطيل)
    """
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == "POST":
        customer.is_active = False
        customer.save()
        messages.success(request, _("تم حذف العميل بنجاح"))
        return redirect("client:customer_list")

    context = {
        "customer": customer,
        "page_title": f"حذف العميل: {customer.name}",
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
            {"title": "حذف", "active": True},
        ],
    }

    return render(request, "client/customer_delete.html", context)


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

    sale_payments = list(SalePayment.objects.filter(sale__customer=customer).select_related("sale", "created_by").order_by("-payment_date"))
    advance_payments = list(CustomerPayment.objects.filter(customer=customer).select_related("created_by").order_by("-payment_date"))

    # توحيد قائمة المدفوعات لعرضها في التاب والتصدير
    payments = []
    for sp in sale_payments:
        payments.append({
            "id": sp.id,
            "payment_date": sp.payment_date,
            "created_at": sp.created_at,
            "amount": sp.amount,
            "payment_method": sp.source_display_info if hasattr(sp, "source_display_info") else sp.get_payment_method_display(),
            "reference_number": sp.reference_number or f"PAY-{sp.id}",
            "notes": sp.notes or "-",
            "sale__number": sp.sale.number if sp.sale else "-",
            "type_display": "سداد فاتورة",
        })

    for cp in advance_payments:
        payments.append({
            "id": cp.id,
            "payment_date": cp.payment_date,
            "created_at": cp.created_at,
            "amount": cp.amount,
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



    # جلب فواتير البيع المرتبطة بالعميل
    from sale.models import Sale
    invoices = Sale.objects.with_list_details().filter(customer=customer).order_by("-date")
    invoices_count = invoices.count()

    # جلب طلبات التسعير المرتبطة بالعميل (مؤقتاً معطل)
    pricing_orders = []
    pricing_orders_count = 0

    # جلب عروض الأسعار المرتبطة بالعميل إذا كانت الميزة مفعلة
    from core.models import SystemSetting
    enable_quotations = SystemSetting.get_setting('enable_quotations', 'false') == 'true'
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

    for invoice in invoices:
        transactions.append(
            {
                "date": invoice.created_at,
                "reference": invoice.number,
                "invoice_id": invoice.id,
                "type": "invoice",
                "description": f"فاتورة بيع رقم {invoice.number}",
                "debit": invoice.total,
                "credit": 0,
                "balance": 0,
            }
        )

    for payment_item in payments:
        transactions.append(
            {
                "date": payment_item["created_at"] or payment_item["payment_date"],
                "reference": payment_item["reference_number"],
                "type": "payment",
                "description": f"{payment_item['type_display']} ({payment_item['payment_method']})",
                "debit": 0,
                "credit": payment_item["amount"],
                "balance": 0,
            }
        )

    transactions.sort(key=lambda x: str(x["date"] or ""))
    running_balance = 0
    for transaction in transactions:
        running_balance = running_balance + transaction["debit"] - transaction["credit"]
        transaction["balance"] = running_balance

    transactions.reverse()

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
            "label": "التاريخ والوقت",
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
            "label": "تاريخ ووقت الدفع",
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
            "label": "التاريخ والوقت",
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
            "label": "التاريخ والوقت",
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
            "class": "text-start",
        },
        {
            "key": "debit",
            "label": "مدين",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/statement_amount.html",
            "width": "120px",
        },
        {
            "key": "credit",
            "label": "دائن",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/statement_amount.html",
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
        "last_transaction_date": last_transaction_date,
        "transactions": transactions,
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
        # إعدادات الصفوف القابلة للنقر
        "invoices_clickable": True,
        "invoices_click_url": "sale:sale_detail",
        "payments_clickable": True,
        "payments_click_url": "sale:payment_detail",
        "journal_clickable": True,
        "journal_click_url": "financial:journal_entry_detail",
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
    for vm in CurrencyExposurePresenter.build_view_models(customer_dtos):
        header_badges.append({
            "is_badge": True,
            "icon": vm.icon,
            "text": f"{vm.label}: {vm.formatted_amount} {vm.currency_symbol}",
            "class": vm.variant
        })

    if not customer_dtos and customer.actual_balance != Decimal("0.00"):
        header_badges.append({
            "text": f"المديونية: {smart_float(customer.actual_balance)} {currency_symbol}",
            "class": "bg-success" if customer.actual_balance <= 0 else "bg-danger",
            "icon": "fas fa-arrow-down" if customer.actual_balance <= 0 else "fas fa-arrow-up",
        })
    if unallocated_prepaid > Decimal("0.00"):
        header_badges.append({
            "text": f"رصيد مسبق: {smart_float(unallocated_prepaid)} {currency_symbol}",
            "class": "bg-warning text-dark",
            "icon": "fas fa-wallet",
            "title": "إجمالي الرصيد المسبق المتاح للفواتير",
            "action_text": "توزيع",
            "action_icon": "fas fa-random",
            "action_class": "bg-warning-subtle text-dark border border-warning-subtle",
            "action_onclick": "const m = document.getElementById('prepaidAllocationModal'); if(m){ new bootstrap.Modal(m).show(); }",
            "action_title": "توزيع الرصيد المسبق على الفواتير المفتوحة",
        })
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
            # البحث عن حساب العملاء الرئيسي
            customers_account = ChartOfAccounts.objects.filter(code="10300").first()
            
            if not customers_account:
                error_msg = "لا يمكن العثور على حساب العملاء الرئيسي في النظام"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                messages.error(request, error_msg)
                return redirect("client:customer_change_account", pk=customer.pk)
            
            # البحث عن آخر حساب فرعي تحت حساب العملاء - النمط: 1030XXXX
            last_customer_account = ChartOfAccounts.objects.filter(
                parent=customers_account,
                code__startswith='1030'
            ).exclude(code='10300').order_by('-code').first()
            
            if last_customer_account:
                last_number = int(last_customer_account.code[-4:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            new_code = f"1030{new_number:04d}"
            
            # إنشاء اسم مناسب للحساب
            account_name = f"عميل - {customer.name}"
            
            # إنشاء الحساب الجديد
            new_account = ChartOfAccounts.objects.create(
                code=new_code,
                name=account_name,
                parent=customers_account,
                account_type=customers_account.account_type,
                is_active=True,
                is_leaf=True,
                description=f"حساب محاسبي للعميل: {customer.name} (كود العميل: {customer.code})"
            )
            
            # ربط العميل بالحساب الجديد
            # استخدام update() بدلاً من save() لتجنب تشغيل الـ signal
            Customer.objects.filter(pk=customer.pk).update(financial_account=new_account)
            customer.financial_account = new_account  # تحديث الـ instance في الذاكرة
            
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
        form = CustomerForm(request.POST)
        if form.is_valid():
            try:
                customer = customer_service.create_customer(
                    name=form.cleaned_data['name'],
                    code=form.cleaned_data['code'],
                    user=request.user,
                    phone=form.cleaned_data.get('phone', ''),
                    email=form.cleaned_data.get('email', ''),
                    address=form.cleaned_data.get('address', ''),
                    credit_limit=form.cleaned_data.get('credit_limit', 0),
                    tax_number=form.cleaned_data.get('tax_number', ''),
                    notes=form.cleaned_data.get('notes', '')
                )
                return JsonResponse({
                    'success': True,
                    'customer': {
                        'id': customer.pk,
                        'name': customer.name,
                        'phone': customer.phone,
                        'code': customer.code
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
    إضافة رصيد مسبق / مقبوضات مقدمة جديدة للعميل
    """
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        from client.services.customer_allocation_audit_service import CustomerAllocationAuditService
        from decimal import Decimal

        amount_str = request.POST.get("amount")
        payment_date_str = request.POST.get("payment_date")
        payment_method = request.POST.get("payment_method", "cash")
        financial_account_id = request.POST.get("financial_account")
        reference_number = request.POST.get("reference_number")
        notes = request.POST.get("notes")

        if amount_str:
            try:
                amt = Decimal(amount_str)
                fin_acc_id = int(financial_account_id) if (financial_account_id and str(financial_account_id).isdigit()) else None
                
                payment = CustomerAllocationAuditService.create_customer_advance_payment(
                    customer_id=customer.id,
                    amount=amt,
                    payment_date=payment_date_str if payment_date_str else None,
                    payment_method=payment_method,
                    financial_account_id=fin_acc_id,
                    reference_number=reference_number,
                    notes=notes,
                    user=request.user
                )
                messages.success(request, f"تم تحصيل رصيد مسبق بقيمة {amt} ج.م من العميل بنجاح (مرجع #{payment.id}).")
            except Exception as e:
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
                messages.success(request, f"تم التوزيع الجماعي بقيمة إجمالية {total_alloc} ج.م على {len(audits)} معاملة بنجاح.")
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
                        messages.success(request, f"تم تخصيص {alloc} ج.م من الرصيد المسبق على الفاتورة #{sale.number} بنجاح.")
                    except Exception as e:
                        messages.error(request, f"حدث خطأ أثناء التخصيص: {str(e)}")

    return redirect("client:customer_detail", pk=pk)


