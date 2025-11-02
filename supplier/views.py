import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import models
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from .models import (
    Supplier,
    SupplierType,
    SpecializedService,
    PaperServiceDetails,
    DigitalPrintingDetails,
    FinishingServiceDetails,
)
from .forms import SupplierForm, SupplierAccountChangeForm
from purchase.models import Purchase, PurchaseItem
from financial.models import ChartOfAccounts


@login_required
def supplier_list(request):
    """
    عرض قائمة الموردين
    """
    # فلترة بناءً على المعايير
    status = request.GET.get("status", "")
    search = request.GET.get("search", "")
    supplier_type = request.GET.get("supplier_type", "")
    preferred = request.GET.get("preferred", "")
    order_by = request.GET.get("order_by", "balance")
    order_dir = request.GET.get("order_dir", "desc")  # تنازلي افتراضيًا

    suppliers = Supplier.objects.prefetch_related("supplier_types").all()

    if status == "active":
        suppliers = suppliers.filter(is_active=True)
    elif status == "inactive":
        suppliers = suppliers.filter(is_active=False)

    if supplier_type:
        suppliers = suppliers.filter(supplier_types__id=supplier_type)

    if preferred == "1":
        suppliers = suppliers.filter(is_preferred=True)

    if search:
        suppliers = suppliers.filter(
            models.Q(name__icontains=search)
            | models.Q(code__icontains=search)
            | models.Q(phone__icontains=search)
            | models.Q(city__icontains=search)
        )

    # ترتيب النتائج
    if order_by:
        order_field = order_by
        if order_dir == "desc":
            order_field = f"-{order_by}"
        suppliers = suppliers.order_by(order_field)
    else:
        # ترتيب حسب الأعلى استحقاق افتراضيًا
        suppliers = suppliers.order_by("-balance")

    active_suppliers = suppliers.filter(is_active=True).count()
    preferred_suppliers = suppliers.filter(is_preferred=True).count()

    # حساب إجمالي الاستحقاق الفعلي
    total_debt = 0
    for supplier in suppliers:
        supplier_debt = supplier.actual_balance
        if supplier_debt > 0:  # فقط الاستحقاق الموجب
            total_debt += supplier_debt

    total_purchases = 0  # قد تحتاج لحساب إجمالي المشتريات من موديل آخر

    # جلب أنواع الموردين للفلتر من الإعدادات الديناميكية
    supplier_types = SupplierType.objects.filter(
        settings__is_active=True
    ).select_related('settings').order_by('settings__display_order', 'name')

    # تعريف أعمدة الجدول
    headers = [
        {
            "key": "name",
            "label": "اسم المورد",
            "sortable": True,
            "class": "text-center",
            "format": "link",
            "url": "supplier:supplier_detail",
        },
        {"key": "code", "label": "الكود", "sortable": True},
        {
            "key": "supplier_types_display",
            "label": "أنواع الخدمات",
            "sortable": False,
            "format": "html",
        },
        {"key": "phone", "label": "رقم الهاتف", "sortable": False},
        {"key": "city", "label": "المدينة", "sortable": True},
        {
            "key": "is_preferred",
            "label": "مفضل",
            "sortable": True,
            "format": "boolean_badge",
        },
        {
            "key": "actual_balance",
            "label": "الاستحقاق",
            "sortable": True,
            "format": "currency",
            "decimals": 2,
            "variant": "text-danger",
        },
        {"key": "is_active", "label": "الحالة", "sortable": True, "format": "boolean"},
    ]

    # تعريف أزرار الإجراءات
    action_buttons = [
        {
            "url": "supplier:supplier_detail",
            "icon": "fa-eye",
            "class": "action-view",
            "label": "عرض",
        },
        {
            "url": "supplier:supplier_edit",
            "icon": "fa-edit",
            "class": "action-edit",
            "label": "تعديل",
        },
    ]

    context = {
        "suppliers": suppliers,
        "headers": headers,
        "action_buttons": action_buttons,
        "active_suppliers": active_suppliers,
        "preferred_suppliers": preferred_suppliers,
        "total_debt": total_debt,
        "total_purchases": total_purchases,
        "supplier_types": supplier_types,
        "page_title": "قائمة الموردين",
        "page_icon": "fas fa-truck",
        "current_order_by": order_by,
        "current_order_dir": order_dir,
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الموردين", "active": True},
        ],
    }

    # Ajax response
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "html": render_to_string(
                    "supplier/core/supplier_list.html", context, request
                ),
                "success": True,
            }
        )

    return render(request, "supplier/core/supplier_list.html", context)


@login_required
def supplier_add(request):
    """
    إضافة مورد جديد
    """
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.created_by = request.user
            supplier.save()
            messages.success(request, _("تم إضافة المورد بنجاح"))
            return redirect("supplier:supplier_list")
    else:
        form = SupplierForm()

    context = {
        "form": form,
        "page_title": "إضافة مورد جديد",
        "page_icon": "fas fa-user-plus",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {"title": "إضافة مورد", "active": True},
        ],
    }

    return render(request, "supplier/core/supplier_form.html", context)


@login_required
def supplier_edit(request, pk):
    """
    تعديل بيانات مورد
    """
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, _("تم تعديل بيانات المورد بنجاح"))
            return redirect("supplier:supplier_list")
    else:
        form = SupplierForm(instance=supplier)

    context = {
        "form": form,
        "supplier": supplier,
        "page_title": f"تعديل بيانات المورد: {supplier.name}",
        "page_icon": "fas fa-user-edit",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {
                "title": supplier.name,
                "url": reverse("supplier:supplier_detail", kwargs={"pk": supplier.pk}),
            },
            {"title": "تعديل", "active": True},
        ],
    }

    return render(request, "supplier/core/supplier_form.html", context)


@login_required
def supplier_delete(request, pk):
    """
    حذف مورد (تعطيل)
    """
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        supplier.is_active = False
        supplier.save()
        messages.success(request, _("تم حذف المورد بنجاح"))
        return redirect("supplier:supplier_list")

    context = {
        "supplier": supplier,
        "page_title": f"حذف المورد: {supplier.name}",
        "page_icon": "fas fa-user-times",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {
                "title": supplier.name,
                "url": reverse("supplier:supplier_detail", kwargs={"pk": supplier.pk}),
            },
            {"title": "حذف", "active": True},
        ],
    }

    return render(request, "supplier/core/supplier_delete.html", context)


@login_required
def supplier_detail(request, pk):
    """
    عرض تفاصيل المورد ودفعات الفواتير
    """
    supplier = get_object_or_404(
        Supplier.objects.prefetch_related(
            "specialized_services__paper_details",
            "specialized_services__offset_details",
            "specialized_services__digital_details",
            "specialized_services__category",
        ).select_related(
            "primary_type__settings"
        ).prefetch_related(
            "supplier_types__settings"
        ),
        pk=pk,
    )

    # جلب دفعات فواتير المشتريات المرتبطة بالمورد
    from purchase.models import PurchasePayment

    payments = PurchasePayment.objects.filter(purchase__supplier=supplier).order_by(
        "-payment_date"
    )

    # جلب فواتير الشراء المرتبطة بالمورد
    purchases = Purchase.objects.filter(supplier=supplier).order_by("-date")
    purchases_count = purchases.count()

    # حساب إجمالي المشتريات
    total_purchases = purchases.aggregate(total=Sum("total"))["total"] or 0

    # حساب عدد المنتجات الفريدة في فواتير الشراء
    purchase_items = PurchaseItem.objects.filter(purchase__supplier=supplier)
    products_count = purchase_items.values("product").distinct().count()

    # جلب المنتجات مع تفاصيل الشراء
    from django.db.models import Max, Min, Avg, Count

    supplier_products = (
        purchase_items.values(
            "product__id", "product__name", "product__sku", "product__category__name"
        )
        .annotate(
            total_quantity=Sum("quantity"),
            total_purchases=Count("purchase", distinct=True),
            last_purchase_date=Max("purchase__created_at"),
            first_purchase_date=Min("purchase__created_at"),
            avg_price=Avg("unit_price"),
            last_price=Max("unit_price"),
            min_price=Min("unit_price"),
            max_price=Max("unit_price"),
        )
        .order_by("-last_purchase_date")[:20]
    )  # أحدث 20 منتج

    # تاريخ آخر معاملة
    last_transaction_date = None
    if payments.exists() or purchases.exists():
        last_payment_date = payments.first().payment_date if payments.exists() else None
        last_purchase_date = purchases.first().date if purchases.exists() else None

        if last_payment_date and last_purchase_date:
            last_transaction_date = max(last_payment_date, last_purchase_date)
        elif last_payment_date:
            last_transaction_date = last_payment_date
        else:
            last_transaction_date = last_purchase_date

    total_payments = payments.aggregate(total=Sum("amount"))["total"] or 0

    # جلب القيود المحاسبية المرتبطة بالمورد
    from financial.models import JournalEntry, JournalEntryLine

    journal_entries = []
    journal_entries_count = 0

    try:
        # البحث عن القيود المرتبطة بفواتير المورد - بحث أوسع
        # نبحث بـ contains عشان نلاقي أي قيد فيه رقم الفاتورة أو الدفعة
        purchase_ids = [p.id for p in purchases]
        payment_ids = [pay.id for pay in payments]

        # بناء query للبحث
        query = Q()
        for p_id in purchase_ids:
            query |= Q(reference__icontains=f"PURCH-{p_id}") | Q(
                reference__icontains=f"{p_id}"
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

        # Debug: طباعة عدد القيود
        # عدد القيود المحاسبية للمورد
    except Exception as e:
        # خطأ في جلب القيود المحاسبية
        import traceback

        traceback.print_exc()

    # محاولة الحصول على حساب المورد في دليل الحسابات
    financial_account = None
    try:
        from financial.models import ChartOfAccounts, AccountType

        # البحث بطرق متعددة
        # 1. البحث باسم المورد في حسابات الموردين
        payables_type = AccountType.objects.filter(code="PAYABLES").first()
        if payables_type:
            financial_account = ChartOfAccounts.objects.filter(
                name__icontains=supplier.name,
                account_type=payables_type,
                is_active=True,
            ).first()

        # 2. إذا لم نجد، نبحث في أي حساب يحتوي على اسم المورد
        if not financial_account:
            financial_account = ChartOfAccounts.objects.filter(
                name__icontains=supplier.name, is_active=True
            ).first()

        # 3. إذا لم نجد، نبحث في حسابات الموردين العامة
        if not financial_account and payables_type:
            # نجيب أول حساب موردين نشط
            financial_account = ChartOfAccounts.objects.filter(
                account_type=payables_type, is_active=True
            ).first()

        # Debug
        # حساب المورد المالي
    except Exception as e:
        # خطأ في جلب الحساب المالي
        import traceback

        traceback.print_exc()

    # تجهيز بيانات المعاملات لكشف الحساب
    transactions = []

    # إضافة فواتير الشراء
    for purchase in purchases:
        transactions.append(
            {
                "date": purchase.created_at,
                "reference": purchase.number,
                "purchase_id": purchase.id,
                "type": "purchase",
                "description": f"فاتورة شراء رقم {purchase.number}",
                "debit": purchase.total,
                "credit": 0,
                "balance": 0,  # سيتم حسابه لاحقاً
            }
        )

    # إضافة المدفوعات
    for payment in payments:
        payment_desc = f"دفعة {payment.get_payment_method_display()}"
        if payment.purchase:
            payment_desc += f" - فاتورة {payment.purchase.number}"

        transactions.append(
            {
                "date": payment.created_at,
                "reference": payment.reference_number,
                "payment_id": payment.id,
                "purchase_id": payment.purchase.id if payment.purchase else None,
                "type": "payment",
                "description": payment_desc,
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

    # حساب عدد أنواع الخدمات المتخصصة (عدد الفئات المختلفة)
    supplier_service_categories_count = 0
    try:
        # الحصول على عدد الفئات المختلفة للخدمات المتخصصة
        supplier_service_categories_count = (
            supplier.specialized_services.filter(is_active=True)
            .values("category")
            .distinct()
            .count()
        )
    except Exception as e:
        # خطأ في حساب عدد أنواع الخدمات
        pass

    # تعريف أعمدة جدول المشتريات للنظام المحسن
    purchase_headers = [
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
            "app": "purchase",
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

    # تعريف أزرار الإجراءات لجدول المشتريات
    purchase_action_buttons = [
        {
            "url": "purchase:purchase_detail",
            "icon": "fa-eye",
            "class": "action-view",
            "label": "عرض الفاتورة",
        },
        {
            "url": "purchase:purchase_add_payment",
            "icon": "fa-money-bill",
            "class": "action-paid",
            "label": "إضافة دفعة",
            "condition": "not_fully_paid",
        },
    ]

    # تعريف أعمدة جدول المنتجات للنظام المحسن
    products_headers = [
        {
            "key": "product__sku",
            "label": "كود المنتج",
            "sortable": True,
            "class": "text-center",
            "width": "100px",
        },
        {
            "key": "product__name",
            "label": "اسم المنتج",
            "sortable": True,
            "class": "text-start",
        },
        {
            "key": "product__category__name",
            "label": "التصنيف",
            "sortable": True,
            "class": "text-center",
        },
        {
            "key": "total_quantity",
            "label": "إجمالي الكمية",
            "sortable": True,
            "class": "text-center",
        },
        {
            "key": "total_purchases",
            "label": "عدد الفواتير",
            "sortable": True,
            "class": "text-center",
        },
        {
            "key": "last_purchase_date",
            "label": "آخر شراء",
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
        },
        {
            "key": "avg_price",
            "label": "متوسط السعر",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
        },
        {
            "key": "last_price",
            "label": "آخر سعر",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
        },
    ]

    # إضافة أزرار إجراءات للمنتجات (معطلة مؤقتاً - namespace غير موجود)
    products_action_buttons = []

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
            "key": "purchase__number",
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

    # أزرار إجراءات القيود المحاسبية (معطلة مؤقتاً - للتحقق من namespace)
    journal_action_buttons = []

    # تعريف أعمدة جدول الخدمات المتخصصة للنظام المحسن
    # أعمدة الأوفست
    offset_services_headers = [
        {
            "key": "name",
            "label": "اسم الماكينة",
            "sortable": True,
            "class": "text-start",
            "width": "35%",
        },
        {
            "key": "sheet_size",
            "label": "المقاس",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/offset_sheet_size.html",
            "width": "15%",
        },
        {
            "key": "colors_capacity",
            "label": "عدد الألوان",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/offset_colors.html",
            "width": "12%",
        },
        {
            "key": "impression_cost",
            "label": "سعر التراج",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/offset_impression_cost.html",
            "width": "18%",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "format": "status",
            "width": "10%",
        },
        {
            "key": "actions",
            "label": "الإجراءات",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/service_actions.html",
            "width": "10%",
        },
    ]

    # أعمدة الديجيتال
    digital_services_headers = [
        {
            "key": "name",
            "label": "اسم الماكينة",
            "sortable": True,
            "class": "text-start",
            "width": "35%",
        },
        {
            "key": "paper_size",
            "label": "المقاس",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/digital_sheet_size.html",
            "width": "15%",
        },
        {
            "key": "price_tiers_count",
            "label": "عدد الشرائح",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/digital_tiers_count.html",
            "width": "12%",
        },
        {
            "key": "price_range",
            "label": "السعر",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/digital_price_range.html",
            "width": "18%",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "format": "status",
            "width": "10%",
        },
        {
            "key": "actions",
            "label": "الإجراءات",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/service_actions.html",
            "width": "10%",
        },
    ]

    # أعمدة الورق
    paper_services_headers = [
        {
            "key": "name",
            "label": "اسم الورق",
            "sortable": True,
            "class": "text-start",
            "width": "25%",
        },
        {
            "key": "paper_details.paper_type",
            "label": "النوع",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/paper_type.html",
            "width": "15%",
        },
        {
            "key": "paper_details.sheet_size",
            "label": "المقاس",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/paper_size_simple.html",
            "width": "20%",
        },
        {
            "key": "paper_details.gsm",
            "label": "الوزن",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/paper_weight.html",
            "width": "12%",
        },
        {
            "key": "paper_details.price_per_sheet",
            "label": "السعر/فرخ",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/paper_price.html",
            "width": "15%",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "format": "status",
            "width": "8%",
        },
        {
            "key": "actions",
            "label": "الإجراءات",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/service_actions.html",
            "width": "15%",
        },
    ]

    # أعمدة الزنكات CTP
    plates_services_headers = [
        {
            "key": "name",
            "label": "اسم الخدمة",
            "sortable": True,
            "class": "text-start",
            "width": "25%",
        },
        {
            "key": "plate_details.plate_size",
            "label": "مقاس الزنك",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/plate_size_simple.html",
            "width": "20%",
        },
        {
            "key": "plate_details.price_per_plate",
            "label": "سعر الزنك",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/plate_price.html",
            "width": "15%",
        },
        {
            "key": "plate_details.set_price",
            "label": "سعر الطقم",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/plate_set_price.html",
            "width": "15%",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "format": "status",
            "width": "10%",
        },
        {
            "key": "actions",
            "label": "الإجراءات",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/service_actions.html",
            "width": "15%",
        },
    ]

    # أعمدة التغطية
    coating_services_headers = [
        {
            "key": "name",
            "label": "اسم الخدمة",
            "sortable": True,
            "class": "text-start fw-bold",
            "width": "20%",
        },
        {
            "key": "coating_details",
            "label": "نوع التغطية",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/coating_type.html",
            "width": "15%",
        },
        {
            "key": "coating_details",
            "label": "طريقة الحساب",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/coating_calculation.html",
            "width": "15%",
        },
        {
            "key": "coating_details",
            "label": "سعر الوحدة",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/coating_price.html",
            "width": "15%",
        },
        {
            "key": "setup_cost",
            "label": "تكلفة التجهيز",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "decimals": 2,
            "width": "15%",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "class": "text-center",
            "template": "components/cells/active_status.html",
            "width": "10%",
        },
        {
            "key": "actions",
            "label": "الإجراءات",
            "class": "text-center",
            "template": "components/cells/service_actions.html",
            "width": "10%",
        },
    ]

    # أعمدة خدمات التشطيب (قص، ريجة، تكسير، إلخ)
    finishing_services_headers = [
        {
            "key": "name",
            "label": "اسم الخدمة",
            "sortable": True,
            "class": "text-start fw-bold",
            "width": "20%",
        },
        {
            "key": "finishing_details",
            "label": "نوع الخدمة",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/finishing_type.html",
            "width": "15%",
        },
        {
            "key": "finishing_details",
            "label": "طريقة الحساب",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/finishing_calculation.html",
            "width": "15%",
        },
        {
            "key": "finishing_details",
            "label": "سعر الوحدة",
            "sortable": False,
            "class": "text-center",
            "template": "components/cells/finishing_price.html",
            "width": "15%",
        },
        {
            "key": "setup_cost",
            "label": "تكلفة التجهيز",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "decimals": 2,
            "width": "15%",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "class": "text-center",
            "template": "components/cells/active_status.html",
            "width": "10%",
        },
        {
            "key": "actions",
            "label": "الإجراءات",
            "class": "text-center",
            "template": "components/cells/service_actions.html",
            "width": "10%",
        },
    ]

    # Headers افتراضية (للأوفست)
    services_headers = offset_services_headers

    # أزرار إجراءات الخدمات المتخصصة (تعديل وحذف فقط)
    services_action_buttons = []

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

    # أزرار الإجراءات السريعة للمورد
    quick_action_buttons = [
        {
            "url": reverse("purchase:purchase_create_for_supplier", kwargs={"supplier_id": supplier.id}),
            "icon": "fas fa-plus-circle",
            "label": "إنشاء فاتورة مشتريات",
            "class": "btn btn-success",
            "title": "إنشاء فاتورة مشتريات جديدة من هذا المورد"
        },
        {
            "url": reverse("supplier:supplier_edit", kwargs={"pk": supplier.pk}),
            "icon": "fas fa-edit",
            "label": "تعديل بيانات المورد",
            "class": "btn btn-primary",
            "title": "تعديل بيانات المورد"
        },
    ]

    # تجميع الخدمات المتخصصة حسب الفئة للعرض (نفس طريقة regroup)
    from itertools import groupby
    specialized_services = supplier.specialized_services.filter(is_active=True).select_related(
        'category', 'finishing_details', 'digital_details', 'offset_details', 'paper_details', 'plate_details'
    ).order_by('category__name')
    services_by_category = []
    
    for category, services_group in groupby(specialized_services, key=lambda x: x.category):
        services_by_category.append({
            'grouper': category,
            'list': list(services_group)
        })

    context = {
        "supplier": supplier,
        "quick_action_buttons": quick_action_buttons,
        "payments": payments,
        "purchases": purchases,
        "purchases_count": purchases_count,
        "total_purchases": total_purchases,
        "products_count": products_count,
        "supplier_products": supplier_products,
        "total_payments": total_payments,
        "last_transaction_date": last_transaction_date,
        "transactions": transactions,
        "journal_entries": journal_entries,
        "journal_entries_count": journal_entries_count,
        "financial_account": financial_account,
        "supplier_services_count": supplier.get_specialized_services_count(),  # عدد الخدمات الإجمالي
        "supplier_service_categories_count": supplier_service_categories_count,  # عدد أنواع الخدمات (الفئات)
        "services_by_category": services_by_category,  # الخدمات مجمعة حسب الفئة
        "purchase_headers": purchase_headers,  # أعمدة جدول المشتريات
        "purchase_action_buttons": purchase_action_buttons,  # أزرار إجراءات المشتريات
        "products_headers": products_headers,  # أعمدة جدول المنتجات
        "products_action_buttons": products_action_buttons,  # أزرار إجراءات المنتجات
        "payments_headers": payments_headers,  # أعمدة جدول المدفوعات
        "journal_headers": journal_headers,  # أعمدة جدول القيود المحاسبية
        "journal_action_buttons": journal_action_buttons,  # أزرار إجراءات القيود
        "services_headers": services_headers,  # أعمدة جدول الخدمات المتخصصة (افتراضي للأوفست)
        "offset_services_headers": offset_services_headers,  # أعمدة جدول الأوفست
        "digital_services_headers": digital_services_headers,  # أعمدة جدول الديجيتال
        "paper_services_headers": paper_services_headers,  # أعمدة جدول الورق
        "plates_services_headers": plates_services_headers,  # أعمدة جدول الزنكات CTP
        "coating_services_headers": coating_services_headers,  # أعمدة جدول التغطية
        "finishing_services_headers": finishing_services_headers,  # أعمدة جدول خدمات التشطيب
        "services_action_buttons": services_action_buttons,  # أزرار إجراءات الخدمات
        "statement_headers": statement_headers,  # أعمدة جدول كشف الحساب
        "primary_key": "id",  # المفتاح الأساسي للجداول
        "products_primary_key": "product__id",  # المفتاح الأساسي لجدول المنتجات
        # إعدادات الصفوف القابلة للنقر
        "purchases_clickable": True,
        "purchases_click_url": "purchase:purchase_detail",
        "payments_clickable": True,
        "payments_click_url": "purchase:payment_detail",
        "journal_clickable": True,
        "journal_click_url": "financial:journal_entry_detail",
        "page_title": f"بيانات المورد: {supplier.name}",
        "page_icon": "fas fa-truck",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {"title": supplier.name, "active": True},
        ],
    }

    return render(request, "supplier/core/supplier_detail.html", context)


@login_required
def supplier_list_api(request):
    """
    API لإرجاع قائمة الموردين النشطين
    """
    from django.http import JsonResponse

    try:
        suppliers = Supplier.objects.filter(is_active=True).order_by("name")

        suppliers_data = []
        for supplier in suppliers:
            suppliers_data.append(
                {
                    "id": supplier.id,
                    "name": supplier.name,
                    "code": supplier.code,
                    "phone": supplier.phone,
                    "balance": float(supplier.balance) if supplier.balance else 0,
                }
            )

        return JsonResponse({"success": True, "suppliers": suppliers_data})

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في تحميل الموردين: خطأ في العملية"}
        )


@login_required
def supplier_change_account(request, pk):
    """
    تغيير الحساب المحاسبي للمورد
    """
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        form = SupplierAccountChangeForm(request.POST, instance=supplier)
        if form.is_valid():
            old_account = supplier.financial_account
            form.save()

            # رسالة تأكيد
            if old_account:
                messages.success(
                    request,
                    f'تم تغيير الحساب المحاسبي من "{old_account.name}" إلى "{supplier.financial_account.name}" بنجاح',
                )
            else:
                messages.success(
                    request,
                    f'تم ربط المورد بالحساب المحاسبي "{supplier.financial_account.name}" بنجاح',
                )

            return redirect("supplier:supplier_detail", pk=supplier.pk)
    else:
        form = SupplierAccountChangeForm(instance=supplier)

    context = {
        "form": form,
        "supplier": supplier,
        "page_title": f"تغيير الحساب المحاسبي للمورد: {supplier.name}",
        "page_icon": "fas fa-exchange-alt",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {
                "title": supplier.name,
                "url": reverse("supplier:supplier_detail", kwargs={"pk": supplier.pk}),
            },
            {"title": "تغيير الحساب المحاسبي", "active": True},
        ],
    }

    return render(request, "supplier/core/supplier_change_account.html", context)


@login_required
def supplier_create_account(request, pk):
    """
    إنشاء حساب محاسبي جديد للمورد (AJAX)
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    
    # التحقق من أن المورد لا يملك حساب بالفعل
    if supplier.financial_account:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False, 
                'message': f'المورد "{supplier.name}" مربوط بالفعل بحساب محاسبي'
            })
        messages.warning(request, f'المورد "{supplier.name}" مربوط بالفعل بحساب محاسبي')
        return redirect("supplier:supplier_change_account", pk=supplier.pk)
    
    if request.method == "POST":
        try:
            # البحث عن حساب الموردين الرئيسي
            suppliers_account = ChartOfAccounts.objects.filter(code="21010").first()
            
            if not suppliers_account:
                error_msg = "لا يمكن العثور على حساب الموردين الرئيسي في النظام"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                messages.error(request, error_msg)
                return redirect("supplier:supplier_change_account", pk=supplier.pk)
            
            # إنشاء كود فريد للحساب الجديد
            # البحث عن آخر حساب فرعي تحت حساب الموردين
            # النمط المتوقع: 2101001, 2101002, 2101003...
            last_supplier_account = ChartOfAccounts.objects.filter(
                parent=suppliers_account,
                code__regex=r'^2101\d{3}$'  # يبدأ بـ 2101 ويتبعه 3 أرقام
            ).order_by('-code').first()
            
            if last_supplier_account:
                # استخراج الرقم التسلسلي من آخر 3 أرقام
                last_number = int(last_supplier_account.code[-3:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            # تكوين الكود الجديد: 2101 + رقم تسلسلي من 3 أرقام
            new_code = f"2101{new_number:03d}"
            
            # إنشاء اسم مناسب للحساب
            account_name = f"مورد - {supplier.name}"
            
            # إنشاء الحساب الجديد
            new_account = ChartOfAccounts.objects.create(
                code=new_code,
                name=account_name,
                parent=suppliers_account,
                account_type=suppliers_account.account_type,
                is_active=True,
                is_leaf=True,
                description=f"حساب محاسبي للمورد: {supplier.name} (كود المورد: {supplier.code})"
            )
            
            # ربط المورد بالحساب الجديد
            supplier.financial_account = new_account
            supplier.save()
            
            success_msg = f'تم إنشاء حساب محاسبي جديد "{new_account.code} - {new_account.name}" وربطه بالمورد بنجاح'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_msg})
            
            messages.success(request, success_msg)
            return redirect("supplier:supplier_detail", pk=supplier.pk)
            
        except Exception as e:
            error_msg = f"حدث خطأ أثناء إنشاء الحساب: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            messages.error(request, error_msg)
            return redirect("supplier:supplier_change_account", pk=supplier.pk)
    
    # للطلبات GET - إرجاع مودال التأكيد
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('supplier/core/supplier_create_account_modal.html', {
            'supplier': supplier
        }, request=request)
        return JsonResponse({'html': html})
    
    # إعادة توجيه للصفحة العادية
    return redirect("supplier:supplier_change_account", pk=supplier.pk)


# ===== تم حذف النظام القديم واستبداله بالنظام المتخصص الجديد =====
# الخدمات المتخصصة الجديدة متاحة في views_pricing.py


# ===== الخدمات المتخصصة الجديدة =====


@login_required
def supplier_services_detail(request, pk):
    """عرض تفاصيل خدمات مورد معين"""

    supplier = get_object_or_404(Supplier, pk=pk)
    services = supplier.specialized_services.filter(is_active=True).select_related(
        "category"
    )

    # تجميع الخدمات حسب الفئة
    services_by_category = {}
    for service in services:
        category_name = service.category.name
        if category_name not in services_by_category:
            services_by_category[category_name] = []

        service_data = {"service": service}

        # إضافة التفاصيل المتخصصة
        if hasattr(service, "paper_details"):
            service_data["details"] = service.paper_details
        elif hasattr(service, "offset_details"):
            service_data["details"] = service.offset_details
        elif hasattr(service, "digital_details"):
            service_data["details"] = service.digital_details
        elif hasattr(service, "finishing_details"):
            service_data["details"] = service.finishing_details

        services_by_category[category_name].append(service_data)

    context = {
        "supplier": supplier,
        "services_by_category": services_by_category,
        "total_services": services.count(),
        "contact_methods": supplier.get_contact_methods(),
        "page_title": f"خدمات {supplier.name}",
        "page_icon": "fas fa-tools",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {
                "title": supplier.name,
                "url": reverse("supplier:supplier_detail", kwargs={"pk": supplier.pk}),
            },
            {"title": "الخدمات المتخصصة", "active": True},
        ],
    }

    return render(request, "supplier/analysis/supplier_services_detail.html", context)


# ===== النظام الديناميكي للخدمات المتخصصة =====


@login_required
def add_specialized_service(request, supplier_id, service_id=None):
    """إضافة/تعديل خدمة متخصصة - النظام الديناميكي الموحد"""
    supplier = get_object_or_404(Supplier, id=supplier_id)

    # تحديد ما إذا كان تعديل أم إضافة
    service = None
    is_edit = service_id is not None

    if is_edit:
        service = get_object_or_404(
            SpecializedService, id=service_id, supplier=supplier
        )

    # جلب التصنيفات المتاحة
    categories = SupplierType.objects.filter(is_active=True).order_by("display_order")

    # تحديد العنوان والأيقونة
    if is_edit:
        page_title = f"تعديل خدمة - {service.name}"
        page_icon = "fas fa-edit"
        breadcrumb_title = f"تعديل خدمة - {service.name}"
        selected_category = service.category.code
    else:
        page_title = f"إضافة خدمة متخصصة - {supplier.name}"
        page_icon = "fas fa-plus-circle"
        breadcrumb_title = "إضافة خدمة متخصصة"
        selected_category = request.GET.get("category", "")

    # تحديد template النموذج حسب نوع الخدمة
    form_template = None
    category_code = None

    if is_edit and service:
        category_code = service.category.code
    elif selected_category:
        category_code = selected_category

    # تحديد template بناءً على نوع الخدمة
    if category_code:
        if category_code == "offset_printing":
            form_template = "supplier/forms/offset_form.html"
        elif category_code == "digital_printing":
            form_template = "supplier/forms/digital_form.html"
        elif category_code == "paper":
            form_template = "supplier/forms/paper_form.html"
        elif category_code == "finishing":
            form_template = "supplier/forms/finishing_form.html"
        elif category_code == "plates":
            form_template = "supplier/forms/plates_form.html"
        elif category_code == "packaging":
            form_template = "supplier/forms/packaging_form.html"
        elif category_code == "coating":
            form_template = "supplier/forms/coating_form.html"

    # إضافة form_choices للنماذج
    form_choices = {}
    if category_code == "plates":
        # استخدام النظام الموحد لجلب بيانات الزنكات
        from .forms.dynamic_forms import ServiceFormFactory
        form_choices = ServiceFormFactory.get_unified_ctp_choices()
    elif category_code == "paper":
        # استخدام النظام الموحد لجلب بيانات الورق
        from .forms.dynamic_forms import ServiceFormFactory
        form_choices = ServiceFormFactory.get_unified_paper_choices()
    elif category_code == "finishing":
        # جلب أنواع خدمات الطباعة من الإعدادات
        try:
            from printing_pricing.models.settings_models import FinishingType
            finishing_types = FinishingType.objects.filter(is_active=True).order_by('name')
            
            if finishing_types.exists():
                form_choices.update({
                    "finishing_types": [(ft.id, ft.name) for ft in finishing_types]
                })
            else:
                # بيانات افتراضية في حالة عدم وجود بيانات
                form_choices.update({
                    "finishing_types": [
                        ("cutting", "قص"),
                        ("creasing", "ريجة"),
                        ("perforation", "تثقيب"),
                        ("die_cutting", "تكسير"),
                        ("numbering", "ترقيم"),
                    ]
                })
        except Exception as e:
            # في حالة الخطأ، استخدام البيانات الافتراضية
            form_choices.update({
                "finishing_types": [
                    ("cutting", "قص"),
                    ("creasing", "ريجة"),
                    ("perforation", "تثقيب"),
                    ("die_cutting", "تكسير"),
                    ("numbering", "ترقيم"),
                ]
            })
    elif category_code == "coating":
        # جلب أنواع التغطية من الإعدادات
        try:
            from printing_pricing.models.settings_models import CoatingType
            coating_types = CoatingType.objects.filter(is_active=True).order_by('name')
            
            if coating_types.exists():
                form_choices.update({
                    "coating_types": [(ct.id, ct.name) for ct in coating_types]
                })
            else:
                # بيانات افتراضية في حالة عدم وجود بيانات
                form_choices.update({
                    "coating_types": [
                        ("varnish", "ورنيش"),
                        ("uv_coating", "طلاء UV"),
                        ("aqueous_coating", "طلاء مائي"),
                        ("spot_uv", "UV نقطي"),
                        ("matte_coating", "طلاء مطفي"),
                    ]
                })
        except Exception as e:
            # في حالة الخطأ، استخدام البيانات الافتراضية
            form_choices.update({
                "coating_types": [
                    ("varnish", "ورنيش"),
                    ("uv_coating", "طلاء UV"),
                    ("aqueous_coating", "طلاء مائي"),
                    ("spot_uv", "UV نقطي"),
                    ("matte_coating", "طلاء مطفي"),
                ]
            })

    context = {
        "supplier": supplier,
        "service": service,
        "categories": categories,
        "selected_category": selected_category,
        "is_edit": is_edit,
        "page_title": page_title,
        "page_icon": page_icon,
        "form_template": form_template,
        "form_choices": form_choices,
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {
                "title": supplier.name,
                "url": reverse("supplier:supplier_detail", kwargs={"pk": supplier.pk}),
            },
            {"title": breadcrumb_title, "active": True},
        ],
    }

    return render(request, "supplier/services/dynamic_service_form.html", context)


@login_required
def edit_specialized_service(request, supplier_id, service_id):
    """تعديل خدمة متخصصة - النظام الديناميكي الموحد"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    service = get_object_or_404(SpecializedService, id=service_id, supplier=supplier)

    # إعادة توجيه لنفس view الإضافة مع معامل التعديل
    return add_specialized_service(request, supplier_id, service_id=service_id)


# ===== APIs للنظام الديناميكي =====

# استيراد APIs مع معالجة الأخطاء
try:
    from .api_views import (
        get_category_form_api,
        save_specialized_service_api,
        update_specialized_service_api,
        delete_specialized_service_api,
        get_service_details_api,
    )
except ImportError as e:
    # في حالة فشل الاستيراد، إنشاء دوال بديلة
    def get_category_form_api(request):
        return JsonResponse({"error": "API not available"}, status=500)

    def save_specialized_service_api(request):
        return JsonResponse({"error": "API not available"}, status=500)

    def update_specialized_service_api(request, service_id):
        return JsonResponse({"error": "API not available"}, status=500)

    def delete_specialized_service_api(request, service_id):
        return JsonResponse({"error": "API not available"}, status=500)

    def get_service_details_api(request, service_id):
        return JsonResponse({"error": "API not available"}, status=500)


@login_required
def get_paper_sheet_sizes_api(request):
    """
    API لجلب مقاسات الورق المتاحة للمورد ونوع الورق المحددين
    بغض النظر عن الجرامات، مع ضمان النتائج الفريدة
    """
    try:
        paper_type_id = request.GET.get("paper_type_id")
        paper_supplier_id = request.GET.get("paper_supplier_id")

        if not paper_type_id or not paper_supplier_id:
            return JsonResponse(
                {"success": False, "error": "مطلوب تحديد نوع الورق والمورد"}
            )

        # الحصول على نوع الورق
        try:
            from printing_pricing.models.settings_models import PaperType

            paper_type = PaperType.objects.get(id=paper_type_id)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in views.py: {str(e)}", exc_info=True)
            return JsonResponse(
                {"success": False, "error": "نوع الورق غير موجود: خطأ في العملية"}
            )

        # الحصول على المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({"success": False, "error": "المورد غير موجود"})

        # البحث في خدمات الورق للمورد المحدد ونوع الورق المحدد
        paper_services = (
            PaperServiceDetails.objects.filter(
                service__supplier=supplier,
                service__is_active=True,
                paper_type__icontains=paper_type.name.lower(),
            )
            .values("sheet_size")
            .distinct()
            .order_by("sheet_size")
        )

        # تجميع المقاسات الفريدة
        unique_sizes = []
        seen_sizes = set()

        for service in paper_services:
            size_code = service["sheet_size"]

            if size_code and size_code not in seen_sizes:
                seen_sizes.add(size_code)

                # الحصول على اسم المقاس من الـ choices
                size_name = dict(PaperServiceDetails.SHEET_SIZE_CHOICES).get(
                    size_code, size_code
                )

                unique_sizes.append({"id": size_code, "name": size_name})

        return JsonResponse(
            {"success": True, "sizes": unique_sizes, "count": len(unique_sizes)}
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب مقاسات الورق: خطأ في العملية"}
        )


@login_required
def get_paper_weights_api(request):
    """
    API لجلب جرامات الورق المتاحة للمورد ونوع الورق والمقاس المحددين
    بغض النظر عن بلد المنشأ، مع ضمان النتائج الفريدة
    """
    try:
        paper_type_id = request.GET.get("paper_type_id")
        paper_supplier_id = request.GET.get("paper_supplier_id")
        paper_sheet_size = request.GET.get("paper_sheet_size")

        if not paper_type_id or not paper_supplier_id or not paper_sheet_size:
            return JsonResponse(
                {"success": False, "error": "مطلوب تحديد نوع الورق والمورد والمقاس"}
            )

        # الحصول على نوع الورق
        try:
            from printing_pricing.models.settings_models import PaperType

            paper_type = PaperType.objects.get(id=paper_type_id)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in views.py: {str(e)}", exc_info=True)
            return JsonResponse(
                {"success": False, "error": "نوع الورق غير موجود: خطأ في العملية"}
            )

        # الحصول على المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({"success": False, "error": "المورد غير موجود"})

        # البحث في خدمات الورق للمورد المحدد ونوع الورق والمقاس المحددين
        paper_services = (
            PaperServiceDetails.objects.filter(
                service__supplier=supplier,
                service__is_active=True,
                paper_type__icontains=paper_type.name.lower(),
                sheet_size=paper_sheet_size,
            )
            .values("gsm")
            .distinct()
            .order_by("gsm")
        )

        # تجميع الجرامات الفريدة
        unique_weights = []
        seen_weights = set()

        for service in paper_services:
            weight = service["gsm"]

            if weight and weight not in seen_weights:
                seen_weights.add(weight)
                unique_weights.append({"id": weight, "name": f"{weight} جم"})

        return JsonResponse(
            {"success": True, "weights": unique_weights, "count": len(unique_weights)}
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب جرامات الورق: خطأ في العملية"}
        )


@login_required
def get_paper_origins_api(request):
    """
    API لجلب منشأ الورق المتاح للمورد ونوع الورق والمقاس والجرام المحددين
    مع ضمان النتائج الفريدة
    """
    try:
        paper_type_id = request.GET.get("paper_type_id")
        paper_supplier_id = request.GET.get("paper_supplier_id")
        paper_sheet_size = request.GET.get("paper_sheet_size")
        paper_weight = request.GET.get("paper_weight")

        if (
            not paper_type_id
            or not paper_supplier_id
            or not paper_sheet_size
            or not paper_weight
        ):
            return JsonResponse(
                {
                    "success": False,
                    "error": "مطلوب تحديد نوع الورق والمورد والمقاس والوزن",
                }
            )

        # الحصول على نوع الورق
        try:
            from printing_pricing.models.settings_models import PaperType

            paper_type = PaperType.objects.get(id=paper_type_id)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in views.py: {str(e)}", exc_info=True)
            return JsonResponse(
                {"success": False, "error": "نوع الورق غير موجود: خطأ في العملية"}
            )

        # الحصول على المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({"success": False, "error": "المورد غير موجود"})

        # البحث في خدمات الورق للمورد المحدد ونوع الورق والمقاس والوزن المحددين
        paper_services = (
            PaperServiceDetails.objects.filter(
                service__supplier=supplier,
                service__is_active=True,
                paper_type__icontains=paper_type.name.lower(),
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
            )
            .values("country_of_origin")
            .distinct()
            .order_by("country_of_origin")
        )

        # تجميع منشأ الورق الفريد
        unique_origins = []
        seen_origins = set()

        for service in paper_services:
            origin_name = service["country_of_origin"]

            if origin_name and origin_name.strip() and origin_name not in seen_origins:
                seen_origins.add(origin_name)

                # البحث عن منشأ الورق في النموذج للحصول على الاسم الكامل
                try:
                    from printing_pricing.models.settings_models import PaperOrigin

                    paper_origin = PaperOrigin.objects.filter(
                        Q(name__icontains=origin_name) | Q(code__iexact=origin_name)
                    ).first()

                    if paper_origin:
                        display_name = paper_origin.name
                        origin_id = paper_origin.id
                    else:
                        # إذا لم يوجد في النموذج، استخدم الاسم كما هو
                        display_name = origin_name
                        origin_id = origin_name

                except Exception:
                    # في حالة الخطأ، استخدم الاسم كما هو
                    display_name = origin_name
                    origin_id = origin_name

                unique_origins.append({"id": origin_id, "name": display_name})

        return JsonResponse(
            {"success": True, "origins": unique_origins, "count": len(unique_origins)}
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب منشأ الورق: خطأ في العملية"}
        )


@login_required
def get_paper_price_api(request):
    """
    API لجلب سعر الورق بناءً على جميع المواصفات المحددة
    (نوع الورق، المورد، المقاس، الوزن، المنشأ)
    """
    try:
        paper_type_id = request.GET.get("paper_type_id")
        paper_supplier_id = request.GET.get("paper_supplier_id")
        paper_sheet_size = request.GET.get("paper_sheet_size")
        paper_weight = request.GET.get("paper_weight")
        paper_origin = request.GET.get("paper_origin")

        if not all(
            [
                paper_type_id,
                paper_supplier_id,
                paper_sheet_size,
                paper_weight,
                paper_origin,
            ]
        ):
            return JsonResponse(
                {
                    "success": False,
                    "error": "مطلوب تحديد جميع مواصفات الورق (النوع، المورد، المقاس، الوزن، المنشأ)",
                }
            )

        # الحصول على نوع الورق
        try:
            from printing_pricing.models.settings_models import PaperType

            paper_type = PaperType.objects.get(id=paper_type_id)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in views.py: {str(e)}", exc_info=True)
            return JsonResponse(
                {"success": False, "error": "نوع الورق غير موجود: خطأ في العملية"}
            )

        # الحصول على المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({"success": False, "error": "المورد غير موجود"})

        # البحث عن خدمة الورق بالمواصفات المحددة
        # أولاً نحاول البحث بالـ ID إذا كان رقم
        paper_service = None
        origin_name = paper_origin

        try:
            # إذا كان paper_origin رقم، نبحث عن اسم المنشأ
            if paper_origin.isdigit():
                from printing_pricing.models.settings_models import PaperOrigin

                paper_origin_obj = PaperOrigin.objects.get(id=int(paper_origin))
                origin_name = paper_origin_obj.name
                # تم تحويل ID إلى اسم
            else:
                origin_name = paper_origin
                # استخدام الاسم مباشرة

            # البحث بالاسم أولاً
            paper_service = PaperServiceDetails.objects.filter(
                service__supplier=supplier,
                service__is_active=True,
                paper_type__icontains=paper_type.name.lower(),
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
                country_of_origin__icontains=origin_name,
            ).first()


            # إذا لم نجد، نحاول البحث بكود الدولة
            if not paper_service and paper_origin.isdigit():
                try:
                    from printing_pricing.models.settings_models import PaperOrigin

                    paper_origin_obj = PaperOrigin.objects.get(id=int(paper_origin))
                    origin_code = (
                        paper_origin_obj.code
                        if hasattr(paper_origin_obj, "code")
                        else None
                    )

                    if origin_code:
                        paper_service = PaperServiceDetails.objects.filter(
                            service__supplier=supplier,
                            service__is_active=True,
                            paper_type__icontains=paper_type.name.lower(),
                            sheet_size=paper_sheet_size,
                            gsm=int(paper_weight),
                            country_of_origin__iexact=origin_code,
                        ).first()
                        # البحث الثاني بكود الدولة ونتيجته
                except Exception as e:
                    # خطأ في البحث بكود الدولة
                    pass

            # إذا لم نجد، نحاول البحث بالقيمة الأصلية
            if not paper_service:
                paper_service = PaperServiceDetails.objects.filter(
                    service__supplier=supplier,
                    service__is_active=True,
                    paper_type__icontains=paper_type.name.lower(),
                    sheet_size=paper_sheet_size,
                    gsm=int(paper_weight),
                    country_of_origin=paper_origin,
                ).first()
                # البحث الثالث بالقيمة الأصلية ونتيجته

            # البحث الأخير: بدون منشأ الورق (كما نجح في التحليل)
            if not paper_service:
                paper_service = PaperServiceDetails.objects.filter(
                    service__supplier=supplier,
                    service__is_active=True,
                    paper_type__icontains=paper_type.name.lower(),
                    sheet_size=paper_sheet_size,
                    gsm=int(paper_weight),
                ).first()
                # البحث الرابع بدون منشأ الورق ونتيجته

        except Exception as e:
            # خطأ في البحث
            # في حالة الخطأ، نحاول البحث بالقيمة الأصلية
            paper_service = PaperServiceDetails.objects.filter(
                service__supplier=supplier,
                service__is_active=True,
                paper_type__icontains=paper_type.name.lower(),
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
                country_of_origin=paper_origin,
            ).first()
            # البحث الاحتياطي

        # طباعة جميع الخدمات المتاحة للمورد للتشخيص
        all_services = PaperServiceDetails.objects.filter(
            service__supplier=supplier, service__is_active=True
        ).values(
            "paper_type", "sheet_size", "gsm", "country_of_origin", "price_per_sheet"
        )
        # جميع خدمات الورق للمورد
        for service in all_services:
            pass  # للتصحيح فقط

        if paper_service:
            # تحضير معلومات السعر
            from core.utils import get_default_currency
            price_info = {
                "price_per_sheet": float(paper_service.price_per_sheet),
                "currency": get_default_currency(),
                "supplier_name": supplier.name,
                "paper_type": paper_type.name,
                "sheet_size": dict(PaperServiceDetails.SHEET_SIZE_CHOICES).get(
                    paper_sheet_size, paper_sheet_size
                ),
                "weight": f"{paper_weight} جم",
                "origin": paper_origin,
                "brand": paper_service.brand or "غير محدد",
                "service_id": paper_service.service.id,
                "last_updated": paper_service.service.updated_at.strftime("%Y-%m-%d")
                if paper_service.service.updated_at
                else "غير محدد",
            }

            return JsonResponse(
                {
                    "success": True,
                    "price_info": price_info,
                    "formatted_price": f'{price_info["price_per_sheet"]:.2f} {price_info["currency"]}',
                }
            )
        else:
            return JsonResponse(
                {
                    "success": False,
                    "error": "لا يوجد سعر متاح لهذه المواصفات لدى هذا المورد",
                    "suggestion": "تأكد من أن المورد يوفر هذا النوع من الورق بهذه المواصفات",
                    "debug_info": {
                        "searched_for": {
                            "paper_type": paper_type.name,
                            "supplier": supplier.name,
                            "sheet_size": paper_sheet_size,
                            "weight": paper_weight,
                            "origin_id": paper_origin,
                            "origin_name": origin_name,
                        },
                        "available_services_count": all_services.count()
                        if "all_services" in locals()
                        else 0,
                    },
                }
            )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب سعر الورق: خطأ في العملية"}
        )


@login_required
def debug_paper_services_api(request):
    """
    API للتشخيص - عرض جميع خدمات الورق المتاحة
    """
    try:
        supplier_id = request.GET.get("supplier_id")

        if not supplier_id:
            return JsonResponse({"success": False, "error": "مطلوب تحديد المورد"})

        try:
            supplier = Supplier.objects.get(id=supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({"success": False, "error": "المورد غير موجود"})

        # جلب جميع خدمات الورق للمورد
        paper_services = PaperServiceDetails.objects.filter(
            service__supplier=supplier, service__is_active=True
        ).select_related("service")

        services_data = []
        for service in paper_services:
            services_data.append(
                {
                    "service_id": service.service.id,
                    "service_name": service.service.name,
                    "paper_type": service.paper_type,
                    "gsm": service.gsm,
                    "sheet_size": service.sheet_size,
                    "sheet_size_display": dict(
                        PaperServiceDetails.SHEET_SIZE_CHOICES
                    ).get(service.sheet_size, service.sheet_size),
                    "country_of_origin": service.country_of_origin,
                    "brand": service.brand,
                    "price_per_sheet": float(service.price_per_sheet),
                    "custom_width": float(service.custom_width)
                    if service.custom_width
                    else None,
                    "custom_height": float(service.custom_height)
                    if service.custom_height
                    else None,
                }
            )

        return JsonResponse(
            {
                "success": True,
                "supplier": {"id": supplier.id, "name": supplier.name},
                "services": services_data,
                "count": len(services_data),
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في التشخيص: خطأ في العملية"}
        )


@login_required
def root_cause_analysis_api(request):
    """
    تحليل جذري شامل لمشكلة سعر الورق
    """
    try:
        # البيانات من الطلب
        paper_type_id = request.GET.get("paper_type_id", "2")
        paper_supplier_id = request.GET.get("paper_supplier_id", "3")
        paper_sheet_size = request.GET.get("paper_sheet_size", "quarter_35x50")
        paper_weight = request.GET.get("paper_weight", "80")
        paper_origin = request.GET.get("paper_origin", "2")

        analysis = {
            "request_data": {
                "paper_type_id": paper_type_id,
                "paper_supplier_id": paper_supplier_id,
                "paper_sheet_size": paper_sheet_size,
                "paper_weight": paper_weight,
                "paper_origin": paper_origin,
            },
            "database_checks": {},
            "search_attempts": [],
            "final_diagnosis": "",
        }

        # 1. فحص نوع الورق
        try:
            from printing_pricing.models.settings_models import PaperType

            paper_type = PaperType.objects.get(id=paper_type_id)
            analysis["database_checks"]["paper_type"] = {
                "found": True,
                "id": paper_type.id,
                "name": paper_type.name,
                "name_lower": paper_type.name.lower(),
            }
        except Exception as e:
            analysis["database_checks"]["paper_type"] = {
                "found": False,
                "error": "خطأ في العملية",
            }

        # 2. فحص المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
            analysis["database_checks"]["supplier"] = {
                "found": True,
                "id": supplier.id,
                "name": supplier.name,
            }
        except Exception as e:
            analysis["database_checks"]["supplier"] = {
                "found": False,
                "error": "خطأ في العملية",
            }

        # 3. فحص منشأ الورق
        origin_name = paper_origin
        try:
            if paper_origin.isdigit():
                from printing_pricing.models.settings_models import PaperOrigin

                paper_origin_obj = PaperOrigin.objects.get(id=int(paper_origin))
                origin_name = paper_origin_obj.name
                analysis["database_checks"]["paper_origin"] = {
                    "found": True,
                    "id": paper_origin_obj.id,
                    "name": paper_origin_obj.name,
                    "converted_from_id": True,
                }
            else:
                analysis["database_checks"]["paper_origin"] = {
                    "found": True,
                    "name": paper_origin,
                    "converted_from_id": False,
                }
        except Exception as e:
            analysis["database_checks"]["paper_origin"] = {
                "found": False,
                "error": "خطأ في العملية",
                "fallback_name": paper_origin,
            }

        # 4. فحص جميع خدمات الورق للمورد
        all_services = PaperServiceDetails.objects.filter(
            service__supplier_id=paper_supplier_id, service__is_active=True
        ).values(
            "service__id",
            "service__name",
            "paper_type",
            "gsm",
            "sheet_size",
            "country_of_origin",
            "price_per_sheet",
            "brand",
        )

        analysis["database_checks"]["all_services"] = list(all_services)
        analysis["database_checks"]["services_count"] = len(
            analysis["database_checks"]["all_services"]
        )

        # 5. محاولات البحث المختلفة
        if (
            analysis["database_checks"]["paper_type"]["found"]
            and analysis["database_checks"]["supplier"]["found"]
        ):

            # محاولة 1: البحث الدقيق
            search1 = PaperServiceDetails.objects.filter(
                service__supplier_id=paper_supplier_id,
                service__is_active=True,
                paper_type__icontains=analysis["database_checks"]["paper_type"][
                    "name_lower"
                ],
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
                country_of_origin__icontains=origin_name,
            ).values(
                "service__name",
                "paper_type",
                "gsm",
                "sheet_size",
                "country_of_origin",
                "price_per_sheet",
            )

            analysis["search_attempts"].append(
                {
                    "method": "البحث الدقيق مع icontains",
                    "criteria": {
                        "paper_type__icontains": analysis["database_checks"][
                            "paper_type"
                        ]["name_lower"],
                        "sheet_size": paper_sheet_size,
                        "gsm": int(paper_weight),
                        "country_of_origin__icontains": origin_name,
                    },
                    "results": list(search1),
                    "count": len(list(search1)),
                }
            )

            # محاولة 2: البحث بدون icontains
            search2 = PaperServiceDetails.objects.filter(
                service__supplier_id=paper_supplier_id,
                service__is_active=True,
                paper_type=analysis["database_checks"]["paper_type"]["name"],
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
                country_of_origin=origin_name,
            ).values(
                "service__name",
                "paper_type",
                "gsm",
                "sheet_size",
                "country_of_origin",
                "price_per_sheet",
            )

            analysis["search_attempts"].append(
                {
                    "method": "البحث الدقيق بدون icontains",
                    "criteria": {
                        "paper_type": analysis["database_checks"]["paper_type"]["name"],
                        "sheet_size": paper_sheet_size,
                        "gsm": int(paper_weight),
                        "country_of_origin": origin_name,
                    },
                    "results": list(search2),
                    "count": len(list(search2)),
                }
            )

            # محاولة 3: البحث بدون منشأ الورق
            search3 = PaperServiceDetails.objects.filter(
                service__supplier_id=paper_supplier_id,
                service__is_active=True,
                paper_type__icontains=analysis["database_checks"]["paper_type"][
                    "name_lower"
                ],
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
            ).values(
                "service__name",
                "paper_type",
                "gsm",
                "sheet_size",
                "country_of_origin",
                "price_per_sheet",
            )

            analysis["search_attempts"].append(
                {
                    "method": "البحث بدون منشأ الورق",
                    "criteria": {
                        "paper_type__icontains": analysis["database_checks"][
                            "paper_type"
                        ]["name_lower"],
                        "sheet_size": paper_sheet_size,
                        "gsm": int(paper_weight),
                    },
                    "results": list(search3),
                    "count": len(list(search3)),
                }
            )

        # 6. التشخيص النهائي
        successful_searches = [s for s in analysis["search_attempts"] if s["count"] > 0]
        if successful_searches:
            analysis[
                "final_diagnosis"
            ] = f"تم العثور على {len(successful_searches)} طريقة بحث ناجحة"
            analysis["recommended_fix"] = "المشكلة في معايير البحث في الكود الأصلي"
        else:
            analysis["final_diagnosis"] = "لا توجد بيانات تطابق المعايير المطلوبة"
            analysis[
                "recommended_fix"
            ] = "يجب إضافة بيانات جديدة أو تعديل البيانات الموجودة"

        return JsonResponse({"success": True, "analysis": analysis})

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في التحليل الجذري: خطأ في العملية"}
        )


@login_required
def get_suppliers_by_service_type(request):
    """
    API لجلب الموردين حسب نوع الخدمة
    """
    try:
        service_type = request.GET.get('service_type')
        
        if not service_type:
            return JsonResponse({
                'success': False,
                'error': 'نوع الخدمة مطلوب'
            })
        
        # البحث عن الموردين الذين لديهم خدمات من النوع المطلوب
        from .models import Supplier, SupplierType
        
        # جلب نوع المورد (مثلاً: coating)
        supplier_type = SupplierType.objects.filter(code=service_type, is_active=True).first()
        
        if not supplier_type:
            return JsonResponse({
                'success': True,
                'suppliers': [],
                'message': f'لا يوجد نوع مورد بكود: {service_type}'
            })
        
        # جلب الموردين النشطين من هذا النوع
        suppliers = Supplier.objects.filter(
            supplier_types=supplier_type,
            is_active=True
        ).distinct().values('id', 'name').order_by('name')
        
        return JsonResponse({
            'success': True,
            'suppliers': list(suppliers),
            'count': len(suppliers)
        })
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_suppliers_by_service_type: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب الموردين: {str(e)}'
        })


@login_required
def get_supplier_coating_services(request):
    """API لجلب خدمات التغطية لمورد معين"""
    try:
        supplier_id = request.GET.get('supplier_id')
        if not supplier_id:
            return JsonResponse({'success': False, 'error': 'معرف المورد مطلوب'})
        
        from .models import Supplier, SpecializedService
        supplier = Supplier.objects.filter(id=supplier_id, is_active=True).first()
        if not supplier:
            return JsonResponse({'success': False, 'error': 'المورد غير موجود'})
        
        services = SpecializedService.objects.filter(
            supplier=supplier, category__code='coating', is_active=True
        ).select_related('finishing_details').values(
            'id', 'name', 'finishing_details__price_per_unit', 'finishing_details__finishing_type'
        )
        
        services_list = [{
            'id': s['id'], 'name': s['name'],
            'price': float(s['finishing_details__price_per_unit'] or 0),
            'type': s['finishing_details__finishing_type']
        } for s in services]
        
        return JsonResponse({'success': True, 'services': services_list, 'count': len(services_list)})
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_supplier_coating_services: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'خطأ في جلب الخدمات: {str(e)}'})
