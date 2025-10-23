from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.db.models import Sum, Q
from django.urls import reverse
from django.http import JsonResponse
from django.template.loader import render_to_string

from .models import Customer, CustomerPayment
from .forms import CustomerForm, CustomerAccountChangeForm
from sale.models import Sale
from financial.models import ChartOfAccounts
# from printing_pricing.models import PrintingOrder  # مؤقتاً حتى يتم إكمال النظام الجديد

# Create your views here.


@login_required
def customer_list(request):
    """
    عرض قائمة العملاء
    """
    customers = Customer.objects.filter(is_active=True)
    active_customers = customers.filter(is_active=True).count()

    # حساب إجمالي المديونية الفعلية
    total_debt = 0
    for customer in customers:
        customer_debt = customer.actual_balance
        if customer_debt > 0:  # فقط المديونية الموجبة
            total_debt += customer_debt

    # تعريف أعمدة الجدول
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
        {"key": "email", "label": "البريد الإلكتروني", "sortable": False},
        {
            "key": "actual_balance",
            "label": "المديونية",
            "sortable": True,
            "format": "currency",
            "decimals": 2,
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
            "icon": "fa-edit",
            "class": "action-edit",
            "label": "تعديل",
        },
    ]

    context = {
        "customers": customers,
        "headers": headers,
        "action_buttons": action_buttons,
        "active_customers": active_customers,
        "total_debt": total_debt,
        "page_title": "قائمة العملاء",
        "page_icon": "fas fa-users",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "العملاء", "active": True},
        ],
    }

    return render(request, "client/customer_list.html", context)


@login_required
def customer_add(request):
    """
    إضافة عميل جديد
    """
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.created_by = request.user
            customer.save()
            messages.success(request, _("تم إضافة العميل بنجاح"))
            return redirect("client:customer_list")
    else:
        form = CustomerForm()

    context = {
        "form": form,
        "page_title": "إضافة عميل جديد",
        "page_icon": "fas fa-user-plus",
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
    تعديل بيانات عميل
    """
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, _("تم تعديل بيانات العميل بنجاح"))
            return redirect("client:customer_list")
    else:
        form = CustomerForm(instance=customer)

    context = {
        "form": form,
        "customer": customer,
        "page_title": f"تعديل بيانات العميل: {customer.name}",
        "page_icon": "fas fa-user-edit",
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
    عرض تفاصيل العميل والمدفوعات
    """
    customer = get_object_or_404(Customer, pk=pk)

    # جلب دفعات فواتير المبيعات المرتبطة بالعميل
    from sale.models import SalePayment

    payments = SalePayment.objects.filter(sale__customer=customer).order_by(
        "-payment_date"
    )

    # جلب فواتير البيع المرتبطة بالعميل
    invoices = Sale.objects.filter(customer=customer).order_by("-date")
    invoices_count = invoices.count()

    # جلب طلبات التسعير المرتبطة بالعميل (مؤقتاً معطل)
    # pricing_orders = PrintingOrder.objects.filter(client=customer).order_by("-created_at")
    # pricing_orders_count = pricing_orders.count()
    pricing_orders = []
    pricing_orders_count = 0

    # حساب إجمالي المبيعات
    total_sales = invoices.aggregate(total=Sum("total"))["total"] or 0

    # حساب عدد المنتجات الفريدة في فواتير البيع
    from sale.models import SaleItem
    from django.db.models import Count

    sale_items = SaleItem.objects.filter(sale__customer=customer)
    total_products = sale_items.values("product").distinct().count()

    # تاريخ آخر معاملة
    last_transaction_date = None
    if payments.exists() or invoices.exists():
        last_payment_date = payments.first().payment_date if payments.exists() else None
        last_invoice_date = invoices.first().date if invoices.exists() else None

        if last_payment_date and last_invoice_date:
            last_transaction_date = max(last_payment_date, last_invoice_date)
        elif last_payment_date:
            last_transaction_date = last_payment_date
        else:
            last_transaction_date = last_invoice_date

    total_payments = payments.aggregate(total=Sum("amount"))["total"] or 0

    # جلب القيود المحاسبية المرتبطة بالعميل
    from financial.models import JournalEntry, JournalEntryLine

    journal_entries = []
    journal_entries_count = 0

    try:
        # البحث عن القيود المرتبطة بفواتير العميل - بحث أوسع
        invoice_ids = [inv.id for inv in invoices]
        payment_ids = [pay.id for pay in payments]

        # بناء query للبحث
        query = Q()
        for inv_id in invoice_ids:
            query |= Q(reference__icontains=f"SALE-{inv_id}") | Q(
                reference__icontains=f"{inv_id}"
            )
        for pay_id in payment_ids:
            query |= Q(reference__icontains=f"PAY-{pay_id}") | Q(
                reference__icontains=f"{pay_id}"
            )

        if query:
            journal_entries = (
                JournalEntry.objects.filter(query)
                .prefetch_related("lines")
                .order_by("-date")
            )
            journal_entries_count = journal_entries.count()

            # حساب إجمالي المدين لكل قيد
            for entry in journal_entries:
                entry.total_amount = (
                    entry.lines.aggregate(total=Sum("debit"))["total"] or 0
                )

        # عدد القيود المحاسبية للعميل: {journal_entries_count}
    except Exception as e:
        # خطأ في جلب القيود المحاسبية: {e}
        import traceback

        traceback.print_exc()

    # محاولة الحصول على حساب العميل في دليل الحسابات
    financial_account = None
    try:
        from financial.models import ChartOfAccounts, AccountType

        # البحث بطرق متعددة
        # 1. البحث باسم العميل في حسابات العملاء
        receivables_type = AccountType.objects.filter(code="RECEIVABLES").first()
        if receivables_type:
            financial_account = ChartOfAccounts.objects.filter(
                name__icontains=customer.name,
                account_type=receivables_type,
                is_active=True,
            ).first()

        # 2. إذا لم نجد، نبحث في أي حساب يحتوي على اسم العميل
        if not financial_account:
            financial_account = ChartOfAccounts.objects.filter(
                name__icontains=customer.name, is_active=True
            ).first()

        # 3. إذا لم نجد، نبحث في حسابات العملاء العامة
        if not financial_account and receivables_type:
            financial_account = ChartOfAccounts.objects.filter(
                account_type=receivables_type, is_active=True
            ).first()

        # حساب العميل المالي: {financial_account.name if financial_account else 'لا يوجد'}
    except Exception as e:
        # خطأ في جلب الحساب المالي: {e}
        import traceback

        traceback.print_exc()

    # تجهيز بيانات المعاملات لكشف الحساب
    transactions = []

    # إضافة الفواتير
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
                "balance": 0,  # سيتم حسابه لاحقاً
            }
        )

    # إضافة المدفوعات
    for payment in payments:
        transactions.append(
            {
                "date": payment.created_at,
                "reference": payment.reference_number,
                "type": "payment",
                "description": f"دفعة {payment.get_payment_method_display()}",
                "debit": 0,
                "credit": payment.amount,
                "balance": 0,  # سيتم حسابه لاحقاً
            }
        )

    # ترتيب المعاملات حسب التاريخ (من الأقدم للأحدث)
    transactions.sort(key=lambda x: x["date"])

    # حساب الرصيد التراكمي
    running_balance = 0
    for transaction in transactions:
        running_balance = running_balance + transaction["debit"] - transaction["credit"]
        transaction["balance"] = running_balance

    # عكس ترتيب المعاملات (من الأحدث للأقدم) للعرض
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
            "class": "text-center",
            "template": "components/cells/invoice_reference.html",
            "width": "130px",
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

    # حساب الرصيد المتاح (credit_limit - balance)
    available_credit = customer.credit_limit - customer.balance if customer.credit_limit else 0
    
    context = {
        "customer": customer,
        "available_credit": available_credit,
        "quick_action_buttons": quick_action_buttons,
        "payments": payments,
        "invoices": invoices,
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
        # إعدادات الصفوف القابلة للنقر
        "invoices_clickable": True,
        "invoices_click_url": "sale:sale_detail",
        "payments_clickable": True,
        "payments_click_url": "sale:payment_detail",
        "journal_clickable": True,
        "journal_click_url": "financial:journal_entry_detail",
        "page_title": f"بيانات العميل: {customer.name}",
        "page_icon": "fas fa-user",
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
            {"title": customer.name, "active": True},
        ],
    }

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
        "page_icon": "fas fa-exchange-alt",
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
            customers_account = ChartOfAccounts.objects.filter(code="11030").first()
            
            if not customers_account:
                error_msg = "لا يمكن العثور على حساب العملاء الرئيسي في النظام"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                messages.error(request, error_msg)
                return redirect("client:customer_change_account", pk=customer.pk)
            
            # إنشاء كود فريد للحساب الجديد
            # البحث عن آخر حساب فرعي تحت حساب العملاء
            # النمط المتوقع: 1103001, 1103002, 1103003...
            last_customer_account = ChartOfAccounts.objects.filter(
                parent=customers_account,
                code__regex=r'^1103\d{3}$'  # يبدأ بـ 1103 ويتبعه 3 أرقام
            ).order_by('-code').first()
            
            if last_customer_account:
                # استخراج الرقم التسلسلي من آخر 3 أرقام
                last_number = int(last_customer_account.code[-3:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            # تكوين الكود الجديد: 1103 + رقم تسلسلي من 3 أرقام
            new_code = f"1103{new_number:03d}"
            
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
            customer.financial_account = new_account
            customer.save()
            
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
