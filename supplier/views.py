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
    has_debt = request.GET.get("has_debt", "")
    order_by = request.GET.get("order_by", "balance")
    order_dir = request.GET.get("order_dir", "desc")

    suppliers = Supplier.objects.select_related("primary_type__settings").all()

    if status == "active":
        suppliers = suppliers.filter(is_active=True)
    elif status == "inactive":
        suppliers = suppliers.filter(is_active=False)

    if search:
        suppliers = suppliers.filter(
            models.Q(name__icontains=search)
            | models.Q(code__icontains=search)
            | models.Q(phone__icontains=search)
        )

    if has_debt == "1":
        suppliers = suppliers.filter(balance__gt=0)
    elif has_debt == "0":
        suppliers = suppliers.filter(balance__lte=0)

    # ترتيب النتائج
    if order_by:
        order_field = f"-{order_by}" if order_dir == "desc" else order_by
        suppliers = suppliers.order_by(order_field)
    else:
        suppliers = suppliers.order_by("-balance")

    # إضافة عدد الخدمات لكل مورد
    from supplier.models import SupplierService
    services_counts = {
        row['supplier_id']: row['cnt']
        for row in SupplierService.objects.filter(is_active=True).values('supplier_id').annotate(cnt=models.Count('id'))
    }
    for s in suppliers:
        cnt = services_counts.get(s.pk, 0)
        s.services_count = f'<span class="badge bg-{"warning text-dark" if cnt > 0 else "secondary"}">{cnt}</span>'

    active_suppliers = suppliers.filter(is_active=True).count()
    preferred_suppliers = suppliers.filter(is_preferred=True).count()
    total_debt = suppliers.aggregate(total=models.Sum('balance'))['total'] or 0
    total_purchases = 0

    # DB-level pagination
    from django.core.paginator import Paginator
    paginator = Paginator(suppliers, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    suppliers = page_obj

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
            "label": "نوع المورد",
            "sortable": False,
            "format": "html",
        },
        {"key": "phone", "label": "رقم الهاتف", "sortable": False},
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

    # إضافة عمود عدد الخدمات
    headers.insert(-1, {
        "key": "services_count",
        "label": "الخدمات",
        "sortable": False,
        "class": "text-center",
        "format": "html",
    })

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

    # Ajax response - بعد تعريف headers و action_buttons
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        table_html = render_to_string('supplier/core/partials/supplier_table.html', {
            'suppliers': suppliers,
            'headers': headers,
            'action_buttons': action_buttons,
        }, request=request)
        pagination_html = render_to_string('partials/pagination.html', {
            'page_obj': page_obj,
            'align': 'center',
        }, request=request) if paginator.num_pages > 1 else ''
        return JsonResponse({
            'table_html': table_html,
            'pagination_html': pagination_html,
            'count': paginator.count,
        })

    context = {
        "suppliers": suppliers,
        "page_obj": page_obj,
        "paginator": paginator,
        "headers": headers,
        "action_buttons": action_buttons,
        "active_suppliers": active_suppliers,
        "preferred_suppliers": preferred_suppliers,
        "total_debt": total_debt,
        "total_purchases": total_purchases,
        "supplier_types": supplier_types,
        "current_order_by": order_by,
        "current_order_dir": order_dir,
        # بيانات الهيدر
        "page_title": "قائمة الموردين",
        "page_subtitle": "إدارة الموردين وعرض بياناتهم ومعاملاتهم المالية",
        "page_icon": "fas fa-truck",
        # أزرار الهيدر
        "header_buttons": [
            {
                "url": reverse("supplier:supplier_add"),
                "icon": "fa-plus",
                "text": "إضافة مورد",
                "class": "btn-primary",
            },
            {
                "onclick": "syncWithDaftra('suppliers')",
                "icon": "fa-sync",
                "text": "مزامنة دفترة",
                "class": "btn-outline-info",
            },
        ],
        # البريدكرمب
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الموردين", "active": True},
        ],
    }

    return render(request, "supplier/core/supplier_list.html", context)


@login_required
def supplier_add(request):
    """
    إضافة مورد جديد
    """
    from financial.exceptions import FinancialValidationError
    from django.db import transaction
    
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    supplier = form.save(commit=False)
                    supplier.created_by = request.user
                    supplier.save()
                messages.success(request, _("تم إضافة المورد بنجاح"))
                return redirect("supplier:supplier_list")
            except FinancialValidationError as e:
                messages.error(request, f"خطأ في التحقق المالي: {str(e)}")
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء إضافة المورد: {str(e)}")
        else:
            # عرض أخطاء الـ form للمستخدم
            for field, errors in form.errors.items():
                for error in errors:
                    if field == '__all__':
                        messages.error(request, error)
                    else:
                        field_label = form.fields[field].label if field in form.fields else field
                        messages.error(request, f"{field_label}: {error}")
    else:
        form = SupplierForm()

    context = {
        "form": form,
        "page_title": "إضافة مورد جديد",
        "page_subtitle": "إضافة مورد جديد وتحديد أنواع الخدمات المقدمة",
        "page_icon": "fas fa-user-plus",
        "header_buttons": [
            {
                "url": reverse("supplier:supplier_list"),
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
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {"title": "إضافة مورد", "active": True},
        ],
    }

    return render(request, "supplier/core/supplier_form.html", context)


@login_required
def supplier_create_modal(request):
    """
    إضافة مورد جديد عبر المودال
    """
    from financial.exceptions import FinancialValidationError
    
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            try:
                supplier = form.save(commit=False)
                supplier.created_by = request.user
                supplier.save()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f'تم إضافة المورد "{supplier.name}" بنجاح',
                        'supplier_id': supplier.id,
                        'supplier_name': supplier.name
                    })
                else:
                    messages.success(request, _("تم إضافة المورد بنجاح"))
                    return redirect("supplier:supplier_list")
            except FinancialValidationError as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': {'__all__': [f'خطأ في التحقق المالي: {str(e)}']}
                    })
                messages.error(request, f"خطأ في التحقق المالي: {str(e)}")
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': {'__all__': [f'حدث خطأ: {str(e)}']}
                    })
                messages.error(request, f"حدث خطأ: {str(e)}")
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                })
    else:
        form = SupplierForm()

    context = {
        "form": form,
        "page_title": "إضافة مورد جديد",
        "is_modal": True,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string("supplier/core/supplier_modal_form.html", context, request=request)
        return JsonResponse({'html': html})
    
    return render(request, "supplier/core/supplier_modal_form.html", context)


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
        "page_subtitle": "تعديل بيانات المورد وأنواع الخدمات المقدمة",
        "page_icon": "fas fa-user-edit",
        "header_buttons": [
            {
                "url": reverse("supplier:supplier_list"),
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
    حذف مورد - حذف فعلي إذا لم يكن مرتبط بمعاملات، وإلا تعطيل فقط
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    
    # فحص المعاملات المرتبطة
    has_purchases = supplier.purchases.exists()
    has_payments = hasattr(supplier, 'supplier_payments') and supplier.supplier_payments.exists()
    has_activities = hasattr(supplier, 'activities') and supplier.activities.exists()
    
    # تحديد إذا كان المورد مرتبط بأي معاملات
    has_transactions = has_purchases or has_payments or has_activities
    can_delete_permanently = not has_transactions

    if request.method == "POST":
        action = request.POST.get('action', 'deactivate')
        
        if action == 'delete' and can_delete_permanently:
            # حذف نهائي
            supplier_name = supplier.name
            supplier.delete()
            messages.success(request, _(f"تم حذف المورد '{supplier_name}' نهائياً"))
        else:
            # تعطيل فقط
            supplier.is_active = False
            supplier.save()
            messages.warning(request, _("تم تعطيل المورد (لا يمكن الحذف النهائي لوجود معاملات مرتبطة)"))
        
        return redirect("supplier:supplier_list")

    # إعداد معلومات المعاملات للعرض
    transactions_info = []
    if has_purchases:
        purchases_count = supplier.purchases.count()
        transactions_info.append(f"{purchases_count} فاتورة مشتريات")
    if has_payments:
        payments_count = supplier.supplier_payments.count()
        transactions_info.append(f"{payments_count} دفعة")
    if has_activities:
        activities_count = supplier.activities.count()
        transactions_info.append(f"{activities_count} نشاط")

    context = {
        "supplier": supplier,
        "can_delete_permanently": can_delete_permanently,
        "has_transactions": has_transactions,
        "transactions_info": transactions_info,
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
        Supplier.objects.select_related(
            "primary_type__settings"
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

            # ملاحظة: total_amount هو property محسوب تلقائياً من lines
            # لا حاجة لحسابه يدوياً

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
        # تحديد طريقة الدفع من الحساب المالي أو من payment_method
        if payment.financial_account:
            payment_method = payment.financial_account.name
        elif payment.payment_method:
            # محاولة الحصول على اسم الحساب من الكود
            try:
                account = ChartOfAccounts.objects.filter(code=payment.payment_method).first()
                payment_method = account.name if account else payment.payment_method
            except:
                payment_method = payment.payment_method
        else:
            payment_method = "غير محدد"
        
        payment_desc = f"دفعة {payment_method}"
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
    # Note: Specialized services have been removed as part of supplier categories cleanup
    supplier_service_categories_count = 0

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

    # تحويل المدفوعات لـ list of dicts للعرض في الجدول
    payments_data = []
    for payment in payments:
        # تحديد طريقة الدفع من الحساب المالي أو من payment_method
        if payment.financial_account:
            payment_method_display = payment.financial_account.name
        elif payment.payment_method:
            # محاولة الحصول على اسم الحساب من الكود
            try:
                from financial.models import ChartOfAccounts
                account = ChartOfAccounts.objects.filter(code=payment.payment_method).first()
                payment_method_display = account.name if account else payment.payment_method
            except:
                payment_method_display = payment.payment_method
        else:
            payment_method_display = "غير محدد"
        
        # تنسيق رقم الفاتورة كـ HTML
        purchase_number_html = f'<a href="{reverse("purchase:purchase_detail", args=[payment.purchase.id])}" class="text-decoration-none"><code class="bg-light px-2 py-1 rounded">{payment.purchase.number}</code></a>' if payment.purchase else "لا يوجد"
        
        payments_data.append({
            "id": payment.id,
            "created_at": payment.created_at,
            "purchase__number": purchase_number_html,
            "amount": payment.amount,
            "payment_method": f'<span class="badge bg-info">{payment_method_display}</span>',
            "notes": payment.notes or "لا توجد ملاحظات",
        })
    
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
            "format": "html",
            "width": "130px",
        },
        {
            "key": "amount",
            "label": "المبلغ",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "width": "120px",
        },
        {
            "key": "payment_method",
            "label": "طريقة الدفع",
            "sortable": False,
            "class": "text-center",
            "format": "html",
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
            "format": "status",
            "width": "90px",
        },
        {
            "key": "reference",
            "label": "المرجع",
            "sortable": True,
            "class": "text-center",
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
            "format": "currency",
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
            "width": "120px",
        },
        {
            "key": "type",
            "label": "نوع الحركة",
            "sortable": True,
            "class": "text-center",
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
            "format": "currency",
            "width": "120px",
        },
        {
            "key": "credit",
            "label": "دائن",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "width": "120px",
        },
        {
            "key": "balance",
            "label": "الرصيد",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
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

    # جلب خدمات المورد — المرحلة الثانية
    from supplier.models import SupplierService, ServiceType
    supplier_services = SupplierService.objects.filter(
        supplier=supplier
    ).select_related('service_type').prefetch_related('price_tiers').order_by(
        'service_type__order', 'name'
    )
    supplier_services_count = supplier_services.count()
    service_types_available = ServiceType.objects.filter(is_active=True).order_by('order', 'name')

    # تجميع الخدمات حسب نوعها
    services_by_type = {}
    for svc in supplier_services:
        code = svc.service_type.code
        if code not in services_by_type:
            services_by_type[code] = {
                'service_type': svc.service_type,
                'services': [],
            }
        services_by_type[code]['services'].append(svc)

    # أعمدة جدول الخدمات الموحد
    supplier_services_headers = [
        {'key': 'service_type_name', 'label': 'نوع الخدمة',  'sortable': True,  'class': 'text-center', 'format': 'html', 'width': '20%'},
        {'key': 'name',              'label': 'اسم الخدمة',  'sortable': True,  'class': 'text-start',  'width': '35%'},
        {'key': 'base_price',        'label': 'السعر الأساسي','sortable': True,  'class': 'text-center', 'format': 'currency', 'width': '18%'},
        {'key': 'tiers_count',       'label': 'الشرائح',      'sortable': False, 'class': 'text-center', 'format': 'html',     'width': '12%'},
        {'key': 'is_active',         'label': 'الحالة',       'sortable': True,  'class': 'text-center', 'format': 'status',   'width': '10%'},
        {'key': 'actions',           'label': 'الإجراءات',    'sortable': False, 'class': 'text-center', 'width': '5%'},
    ]

    supplier_services_table_data = []
    for svc in supplier_services:
        tiers = svc.price_tiers.filter(is_active=True)
        tiers_count = tiers.count()
        detail_url = reverse("supplier:supplier_service_detail", kwargs={"pk": supplier.pk, "service_pk": svc.pk})
        tiers_badge = (
            f'<a href="{detail_url}" class="badge bg-info text-decoration-none">{tiers_count} شريحة</a>'
            if tiers_count > 0
            else f'<a href="{detail_url}" class="badge bg-secondary text-decoration-none">0</a>'
        )
        icon = svc.service_type.icon
        type_badge = f'<span class="badge" style="background:var(--bs-primary);"><i class="{icon} me-1"></i>{svc.service_type.name}</span>'
        actions_html = (
            f'<a href="{reverse("supplier:supplier_service_edit", kwargs={"pk": supplier.pk, "service_pk": svc.pk})}" '
            f'class="btn btn-sm btn-outline-primary" title="تعديل"><i class="fas fa-edit"></i></a>'
        )
        supplier_services_table_data.append({
            'id':               svc.pk,
            'service_type_name': type_badge,
            'name':             svc.name,
            'base_price':       svc.base_price,
            'setup_cost':       svc.setup_cost,
            'tiers_count':      tiers_badge,
            'is_active':        svc.is_active,
            'actions':          actions_html,
            '_row_url':         reverse("supplier:supplier_service_detail", kwargs={"pk": supplier.pk, "service_pk": svc.pk}),
        })

    # تجميع الخدمات حسب الفئة للعرض (نفس طريقة regroup)
    # Note: Specialized services have been removed as part of supplier categories cleanup
    services_by_category = []

    context = {
        "supplier": supplier,
        "quick_action_buttons": quick_action_buttons,
        "payments": payments_data,  # استخدام البيانات المحولة
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
        "supplier_services_count": supplier_services_count,
        "supplier_service_categories_count": supplier_service_categories_count,
        "services_by_category": services_by_category,
        "supplier_services": supplier_services,
        "supplier_services_table_data": supplier_services_table_data,
        "supplier_services_headers": supplier_services_headers,
        "services_by_type": services_by_type,
        "service_types_available": service_types_available,
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
        # بيانات الهيدر
        "page_title": f"{supplier.name}",
        "page_subtitle": "معلومات وبيانات المورد الكاملة",
        "page_icon": "fas fa-truck",
        # Badges في الهيدر
        "header_badges": [
            {
                "text": f"{supplier.code}",
                "class": "bg-primary",
                "icon": "fas fa-hashtag",
            },
            {
                "text": f"الاستحقاق: {supplier.actual_balance}",
                "class": "bg-danger" if supplier.actual_balance > 0 else "bg-success",
                "icon": "fas fa-arrow-up" if supplier.actual_balance > 0 else "fas fa-arrow-down",
            },
            {
                "text": "دليل الحسابات" if financial_account else "إنشاء حساب محاسبي",
                "class": "bg-success" if financial_account else "bg-info",
                "icon": "fas fa-link" if financial_account else "fas fa-plus-circle",
                "url": reverse("financial:account_detail", kwargs={"pk": financial_account.pk}) if financial_account else "#",
                "onclick": None if financial_account else f"openCreateAccountModal({supplier.pk})",
            },
        ],
        # نوع المورد (للعرض على اليسار)
        "supplier_type_badge": {
            "text": supplier.primary_type.settings.name if supplier.primary_type and supplier.primary_type.settings else (supplier.primary_type.name if supplier.primary_type else "غير محدد"),
            "icon": supplier.primary_type.settings.icon if supplier.primary_type and supplier.primary_type.settings else (supplier.primary_type.icon if supplier.primary_type else "fas fa-industry"),
            "color": supplier.primary_type.settings.color if supplier.primary_type and supplier.primary_type.settings else (supplier.primary_type.color if supplier.primary_type else "#6c757d"),
        } if supplier.primary_type else None,
    }
    
    # أزرار الهيدر
    header_buttons = [
        {
            "url": reverse("purchase:purchase_create_for_supplier", kwargs={"supplier_id": supplier.id}),
            "icon": "fa-shopping-cart",
            "text": "فاتورة شراء",
            "class": "btn-success",
        }
    ]
    
    header_buttons.append({
        "url": "#",
        "icon": "fa-ellipsis-v",
        "text": "",
        "class": "btn-outline-secondary",
        "id": "actions-menu-btn",
        "toggle": "modal",
        "target": "#actionsModal",
    })
    
    context["header_buttons"] = header_buttons
    
    # البريدكرمب
    context["breadcrumb_items"] = [
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
    ]

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
        "page_subtitle": "ربط المورد بحساب محاسبي أو تغيير الحساب الحالي",
        "page_icon": "fas fa-exchange-alt",
        "header_buttons": [
            {
                "url": reverse("supplier:supplier_detail", kwargs={"pk": supplier.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة للمورد",
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
            suppliers_account = ChartOfAccounts.objects.filter(code="20100").first()
            
            if not suppliers_account:
                error_msg = "لا يمكن العثور على حساب الموردين الرئيسي في النظام"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                messages.error(request, error_msg)
                return redirect("supplier:supplier_change_account", pk=supplier.pk)
            
            # البحث عن آخر حساب فرعي تحت حساب الموردين - النمط: 2010XXXX
            last_supplier_account = ChartOfAccounts.objects.filter(
                parent=suppliers_account,
                code__startswith='2010'
            ).exclude(code='20100').order_by('-code').first()
            
            if last_supplier_account:
                last_number = int(last_supplier_account.code[-4:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            new_code = f"2010{new_number:04d}"
            
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
            # استخدام update() بدلاً من save() لتجنب تشغيل الـ signal
            from supplier.models import Supplier
            Supplier.objects.filter(pk=supplier.pk).update(financial_account=new_account)
            supplier.financial_account = new_account  # تحديث الـ instance في الذاكرة
            
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
# Note: Specialized services functionality has been removed as part of supplier categories cleanup


# ===== النظام الديناميكي للخدمات المتخصصة =====
# Note: All specialized service functions have been removed as part of supplier categories cleanup


# Removed functions:
# - supplier_services_detail
# - add_specialized_service
# - edit_specialized_service  
# - get_paper_sheet_sizes_api
# - get_paper_weights_api
# - get_paper_origins_api
# - get_paper_price_api
# - debug_paper_services_api
# - root_cause_analysis_api


# ===================================================================
# خدمات الموردين — المرحلة الثانية
# ===================================================================

@login_required
def supplier_service_add(request, pk):
    """إضافة خدمة جديدة للمورد"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServiceType

    if request.method == 'POST':
        service_type_id = request.POST.get('service_type')
        name            = request.POST.get('name', '').strip()
        base_price      = request.POST.get('base_price', '0') or '0'
        setup_cost      = request.POST.get('setup_cost', '0') or '0'
        notes           = request.POST.get('notes', '')
        is_active       = request.POST.get('is_active') == 'on'

        attributes = {}
        for key, val in request.POST.items():
            if key.startswith('attr_'):
                attributes[key[5:]] = val

        errors = {}
        if not service_type_id:
            errors['service_type'] = 'نوع الخدمة مطلوب'
        if not name:
            errors['name'] = 'اسم الخدمة مطلوب'

        if not errors:
            try:
                service_type = ServiceType.objects.get(pk=service_type_id, is_active=True)
                from decimal import Decimal, InvalidOperation
                try:
                    bp = Decimal(base_price)
                    sc = Decimal(setup_cost)
                except InvalidOperation:
                    bp = Decimal('0')
                    sc = Decimal('0')

                SupplierService.objects.create(
                    supplier=supplier,
                    service_type=service_type,
                    name=name,
                    base_price=bp,
                    setup_cost=sc,
                    attributes=attributes,
                    notes=notes,
                    is_active=is_active,
                )
                messages.success(request, f'تم إضافة الخدمة "{name}" بنجاح')
                return redirect(reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane')
            except ServiceType.DoesNotExist:
                errors['service_type'] = 'نوع الخدمة غير موجود'
            except Exception as e:
                errors['__all__'] = str(e)

        for field, msg in errors.items():
            messages.error(request, msg)

    service_types = ServiceType.objects.filter(is_active=True).order_by('order', 'name')

    # تجميع حسب الفئة لعرض optgroups
    from collections import defaultdict
    category_labels = dict(ServiceType.CATEGORY_CHOICES)
    _grouped = defaultdict(list)
    for st in service_types:
        _grouped[st.category].append(st)
    service_types_grouped = [
        {'category': cat, 'label': category_labels.get(cat, cat), 'types': types}
        for cat, types in _grouped.items()
    ]

    form_data = {
        'name':         request.POST.get('name', ''),
        'base_price':   request.POST.get('base_price', '0'),
        'setup_cost':   request.POST.get('setup_cost', '0'),
        'notes':        request.POST.get('notes', ''),
        'is_active':    True,
        'service_type': request.POST.get('service_type', ''),
    }
    import json
    context = {
        'supplier':               supplier,
        'service_types':          service_types,
        'service_types_grouped':  service_types_grouped,
        'service_types_schemas':  json.dumps({str(st.pk): st.attribute_schema for st in service_types}, ensure_ascii=False),
        'form_data':              form_data,
        'page_title':             f'إضافة خدمة — {supplier.name}',
        'page_icon':              'fas fa-plus-circle',
        'header_buttons': [
            {'url': reverse('supplier:supplier_detail', kwargs={'pk': pk}), 'icon': 'fa-arrow-right', 'text': 'العودة', 'class': 'btn-secondary'},
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': pk})},
            {'title': 'إضافة خدمة', 'active': True},
        ],
    }
    return render(request, 'supplier/services/service_form.html', context)


@login_required
def supplier_service_edit(request, pk, service_pk):
    """تعديل خدمة مورد"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServiceType
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)

    if request.method == 'POST':
        name       = request.POST.get('name', '').strip()
        base_price = request.POST.get('base_price', '0') or '0'
        setup_cost = request.POST.get('setup_cost', '0') or '0'
        notes      = request.POST.get('notes', '')
        is_active  = request.POST.get('is_active') == 'on'

        attributes = {}
        for key, val in request.POST.items():
            if key.startswith('attr_'):
                attributes[key[5:]] = val

        if not name:
            messages.error(request, 'اسم الخدمة مطلوب')
        else:
            try:
                from decimal import Decimal
                service.name       = name
                service.base_price = Decimal(base_price) if base_price else Decimal('0')
                service.setup_cost = Decimal(setup_cost) if setup_cost else Decimal('0')
                service.attributes = attributes
                service.notes      = notes
                service.is_active  = is_active
                service.save()
                messages.success(request, f'تم تحديث الخدمة "{name}" بنجاح')
                return redirect(reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane')
            except Exception as e:
                messages.error(request, str(e))

    service_types = ServiceType.objects.filter(is_active=True).order_by('order', 'name')
    form_data = {
        'name':       service.name,
        'base_price': service.base_price,
        'setup_cost': service.setup_cost,
        'notes':      service.notes,
        'is_active':  service.is_active,
    }
    import json
    context = {
        'supplier':       supplier,
        'service':        service,
        'service_types':  service_types,
        'service_types_schemas': json.dumps({str(st.pk): st.attribute_schema for st in service_types}, ensure_ascii=False),
        'form_data':      form_data,
        'schema_sources': _get_schema_sources(service.service_type.attribute_schema),
        'page_title':     f'تعديل خدمة — {supplier.name}',
        'page_icon':      'fas fa-edit',
        'header_buttons': [
            {'url': reverse('supplier:supplier_detail', kwargs={'pk': pk}), 'icon': 'fa-arrow-right', 'text': 'العودة', 'class': 'btn-secondary'},
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': pk})},
            {'title': 'تعديل خدمة', 'active': True},
        ],
    }
    return render(request, 'supplier/services/service_form.html', context)


@login_required
def supplier_service_delete(request, pk, service_pk):
    """حذف خدمة مورد (POST فقط)"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)

    if request.method == 'POST':
        name = service.name
        service.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f'تم حذف الخدمة "{name}" بنجاح'})
        messages.success(request, f'تم حذف الخدمة "{name}" بنجاح')

    return redirect(reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane')


@login_required
def supplier_service_toggle(request, pk, service_pk):
    """تفعيل/تعطيل خدمة مورد (AJAX POST)"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)

    if request.method == 'POST':
        service.is_active = not service.is_active
        service.save(update_fields=['is_active'])
        status = 'نشطة' if service.is_active else 'معطلة'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'is_active': service.is_active, 'message': f'الخدمة أصبحت {status}'})

    return redirect(reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane')


@login_required
def supplier_services_api(request, pk):
    """API — جلب خدمات مورد معين (JSON)"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService
    service_type_code = request.GET.get('service_type', '')

    qs = SupplierService.objects.filter(supplier=supplier, is_active=True).select_related('service_type')
    if service_type_code:
        qs = qs.filter(service_type__code=service_type_code)

    data = [
        {
            'id':           s.id,
            'name':         s.name,
            'service_type': s.service_type.code,
            'base_price':   float(s.base_price),
            'setup_cost':   float(s.setup_cost),
            'attributes':   s.attributes,
        }
        for s in qs.order_by('service_type__order', 'name')
    ]
    return JsonResponse({'success': True, 'services': data, 'total_count': len(data)})


# ================================================================
# المرحلة 5 — الشرائح السعرية (ServicePriceTier)
# ================================================================

@login_required
def supplier_service_detail(request, pk, service_pk):
    """صفحة تفاصيل الخدمة مع جدول الشرائح السعرية"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServicePriceTier
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)

    tiers = service.price_tiers.all().order_by('min_quantity')

    tiers_headers = [
        {'key': 'min_quantity',   'label': 'الحد الأدنى',  'sortable': True,  'class': 'text-center', 'width': '20%'},
        {'key': 'max_quantity',   'label': 'الحد الأقصى',  'sortable': True,  'class': 'text-center', 'width': '20%'},
        {'key': 'price_per_unit', 'label': 'السعر/وحدة',   'sortable': True,  'class': 'text-center', 'format': 'currency', 'width': '20%'},
        {'key': 'is_active',      'label': 'الحالة',        'sortable': True,  'class': 'text-center', 'format': 'status',   'width': '15%'},
        {'key': 'actions',        'label': 'الإجراءات',     'sortable': False, 'class': 'text-center', 'width': '25%'},
    ]

    tiers_data = []
    for tier in tiers:
        max_q = tier.max_quantity if tier.max_quantity else '∞'
        actions_html = (
            f'<a href="{reverse("supplier:price_tier_edit", kwargs={"pk": pk, "service_pk": service_pk, "tier_pk": tier.pk})}" '
            f'class="btn btn-sm btn-outline-primary me-1" title="تعديل"><i class="fas fa-edit"></i></a>'
            f'<button onclick="deleteTier({tier.pk}, \'{tier.min_quantity}–{max_q}\')" '
            f'class="btn btn-sm btn-outline-danger" title="حذف"><i class="fas fa-trash"></i></button>'
        )
        tiers_data.append({
            'id':            tier.pk,
            'min_quantity':  tier.min_quantity,
            'max_quantity':  tier.max_quantity if tier.max_quantity else '—',
            'price_per_unit': tier.price_per_unit,
            'is_active':     tier.is_active,
            'actions':       actions_html,
        })

    context = {
        'supplier':    supplier,
        'service':     service,
        'tiers':       tiers,
        'tiers_headers': tiers_headers,
        'tiers_data':  tiers_data,
        'title':       f'خدمة: {service.name}',
        'page_icon':   service.service_type.icon,
        'header_buttons': [
            {'url': reverse('supplier:price_tier_add', kwargs={'pk': pk, 'service_pk': service_pk}), 'icon': 'fa-plus', 'text': 'إضافة شريحة', 'class': 'btn-success'},
            {'url': reverse('supplier:supplier_service_edit', kwargs={'pk': pk, 'service_pk': service_pk}), 'icon': 'fa-edit', 'text': 'تعديل الخدمة', 'class': 'btn-primary'},
            {'url': reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane', 'icon': 'fa-arrow-right', 'text': 'العودة', 'class': 'btn-secondary'},
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': pk})},
            {'title': 'خدمات التسعير', 'url': reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane'},
            {'title': service.name, 'active': True},
        ],
    }
    return render(request, 'supplier/services/service_detail.html', context)


@login_required
def price_tier_add(request, pk, service_pk):
    """إضافة شريحة سعرية جديدة"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServicePriceTier
    from decimal import Decimal, InvalidOperation
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)

    if request.method == 'POST':
        min_q  = request.POST.get('min_quantity', '').strip()
        max_q  = request.POST.get('max_quantity', '').strip()
        price  = request.POST.get('price_per_unit', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        errors = {}
        if not min_q or not min_q.isdigit():
            errors['min_quantity'] = 'الحد الأدنى مطلوب ويجب أن يكون رقماً صحيحاً'
        if max_q and not max_q.isdigit():
            errors['max_quantity'] = 'الحد الأقصى يجب أن يكون رقماً صحيحاً'
        if max_q and min_q and int(max_q) < int(min_q):
            errors['max_quantity'] = 'الحد الأقصى يجب أن يكون أكبر من أو يساوي الحد الأدنى'
        try:
            price_val = Decimal(price)
            if price_val < 0:
                errors['price_per_unit'] = 'السعر يجب أن يكون موجباً'
        except (InvalidOperation, ValueError):
            errors['price_per_unit'] = 'السعر مطلوب ويجب أن يكون رقماً'

        if not errors:
            ServicePriceTier.objects.create(
                service=service,
                min_quantity=int(min_q),
                max_quantity=int(max_q) if max_q else None,
                price_per_unit=price_val,
                is_active=is_active,
            )
            messages.success(request, 'تم إضافة الشريحة السعرية بنجاح')
            return redirect(reverse('supplier:supplier_service_detail', kwargs={'pk': pk, 'service_pk': service_pk}))

        for msg in errors.values():
            messages.error(request, msg)

    context = {
        'supplier': supplier,
        'service':  service,
        'form_data': {
            'min_quantity':   request.POST.get('min_quantity', ''),
            'max_quantity':   request.POST.get('max_quantity', ''),
            'price_per_unit': request.POST.get('price_per_unit', ''),
            'is_active':      True,
        },
        'is_edit':   False,
        'title':     f'إضافة شريحة — {service.name}',
        'page_icon': 'fas fa-plus-circle',
        'header_buttons': [
            {'url': reverse('supplier:supplier_service_detail', kwargs={'pk': pk, 'service_pk': service_pk}), 'icon': 'fa-arrow-right', 'text': 'العودة', 'class': 'btn-secondary'},
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': pk})},
            {'title': service.name, 'url': reverse('supplier:supplier_service_detail', kwargs={'pk': pk, 'service_pk': service_pk})},
            {'title': 'إضافة شريحة', 'active': True},
        ],
    }
    return render(request, 'supplier/services/price_tier_form.html', context)


@login_required
def price_tier_edit(request, pk, service_pk, tier_pk):
    """تعديل شريحة سعرية"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServicePriceTier
    from decimal import Decimal, InvalidOperation
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)
    tier    = get_object_or_404(ServicePriceTier, pk=tier_pk, service=service)

    if request.method == 'POST':
        min_q  = request.POST.get('min_quantity', '').strip()
        max_q  = request.POST.get('max_quantity', '').strip()
        price  = request.POST.get('price_per_unit', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        errors = {}
        if not min_q or not min_q.isdigit():
            errors['min_quantity'] = 'الحد الأدنى مطلوب ويجب أن يكون رقماً صحيحاً'
        if max_q and not max_q.isdigit():
            errors['max_quantity'] = 'الحد الأقصى يجب أن يكون رقماً صحيحاً'
        if max_q and min_q and int(max_q) < int(min_q):
            errors['max_quantity'] = 'الحد الأقصى يجب أن يكون أكبر من أو يساوي الحد الأدنى'
        try:
            price_val = Decimal(price)
            if price_val < 0:
                errors['price_per_unit'] = 'السعر يجب أن يكون موجباً'
        except (InvalidOperation, ValueError):
            errors['price_per_unit'] = 'السعر مطلوب ويجب أن يكون رقماً'

        if not errors:
            tier.min_quantity   = int(min_q)
            tier.max_quantity   = int(max_q) if max_q else None
            tier.price_per_unit = price_val
            tier.is_active      = is_active
            tier.save()
            messages.success(request, 'تم تحديث الشريحة السعرية بنجاح')
            return redirect(reverse('supplier:supplier_service_detail', kwargs={'pk': pk, 'service_pk': service_pk}))

        for msg in errors.values():
            messages.error(request, msg)

    context = {
        'supplier': supplier,
        'service':  service,
        'tier':     tier,
        'form_data': {
            'min_quantity':   request.POST.get('min_quantity', tier.min_quantity),
            'max_quantity':   request.POST.get('max_quantity', tier.max_quantity or ''),
            'price_per_unit': request.POST.get('price_per_unit', tier.price_per_unit),
            'is_active':      tier.is_active,
        },
        'is_edit':   True,
        'title':     f'تعديل شريحة — {service.name}',
        'page_icon': 'fas fa-edit',
        'header_buttons': [
            {'url': reverse('supplier:supplier_service_detail', kwargs={'pk': pk, 'service_pk': service_pk}), 'icon': 'fa-arrow-right', 'text': 'العودة', 'class': 'btn-secondary'},
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': pk})},
            {'title': service.name, 'url': reverse('supplier:supplier_service_detail', kwargs={'pk': pk, 'service_pk': service_pk})},
            {'title': 'تعديل شريحة', 'active': True},
        ],
    }
    return render(request, 'supplier/services/price_tier_form.html', context)


@login_required
def price_tier_delete(request, pk, service_pk, tier_pk):
    """حذف شريحة سعرية (POST فقط)"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServicePriceTier
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)
    tier    = get_object_or_404(ServicePriceTier, pk=tier_pk, service=service)

    if request.method == 'POST':
        tier.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم حذف الشريحة بنجاح'})
        messages.success(request, 'تم حذف الشريحة السعرية بنجاح')

    return redirect(reverse('supplier:supplier_service_detail', kwargs={'pk': pk, 'service_pk': service_pk}))


@login_required
def price_tier_toggle(request, pk, service_pk, tier_pk):
    """تفعيل/تعطيل شريحة سعرية (AJAX POST)"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServicePriceTier
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)
    tier    = get_object_or_404(ServicePriceTier, pk=tier_pk, service=service)

    if request.method == 'POST':
        tier.is_active = not tier.is_active
        tier.save(update_fields=['is_active'])
        status = 'نشطة' if tier.is_active else 'معطلة'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'is_active': tier.is_active, 'message': f'الشريحة أصبحت {status}'})

    return redirect(reverse('supplier:supplier_service_detail', kwargs={'pk': pk, 'service_pk': service_pk}))


@login_required
def service_price_api(request, service_pk):
    """API — جلب سعر خدمة لكمية معينة"""
    from supplier.services.supplier_service import SupplierService as SupplierServiceClass
    quantity = int(request.GET.get('quantity', 1))
    result = SupplierServiceClass.get_service_price(service_pk, quantity)
    if result:
        return JsonResponse({'success': True, **{k: float(v) if hasattr(v, '__float__') else v for k, v in result.items()}})
    return JsonResponse({'success': False, 'message': 'الخدمة غير موجودة'}, status=404)


def _get_schema_sources(schema):
    """جلب خيارات حقول source من printing_pricing لاستخدامها في server-side rendering."""
    sources = {}
    try:
        import printing_pricing.models.settings_models as sm
        for key, defn in schema.items():
            if defn.get('type') == 'select' and defn.get('source'):
                src = defn['source']
                if src not in sources:
                    model = getattr(sm, src, None)
                    if model:
                        qs = model.objects.all()
                        if hasattr(model, 'is_active'):
                            qs = qs.filter(is_active=True)
                        name_field = 'name' if hasattr(model, 'name') else 'pk'
                        sources[src] = [str(obj) for obj in qs.order_by(name_field)]
                    else:
                        sources[src] = []
    except Exception:
        pass
    return sources


@login_required
def service_type_schema_options_api(request):
    """
    API — جلب خيارات حقل source معين من printing_pricing.
    GET /supplier/api/schema-options/?source=PaperType
    """
    source = request.GET.get('source', '').strip()
    if not source:
        return JsonResponse({'success': False, 'options': []})

    try:
        import printing_pricing.models.settings_models as sm
        model = getattr(sm, source, None)
        if not model:
            return JsonResponse({'success': False, 'options': [], 'message': f'{source} غير موجود'})

        qs = model.objects.all()
        if hasattr(model, 'is_active'):
            qs = qs.filter(is_active=True)

        # محاولة جلب الاسم من حقل name أو __str__
        name_field = 'name' if hasattr(model, 'name') else None
        options = []
        for obj in qs.order_by(name_field or 'pk'):
            options.append({'value': str(obj), 'label': str(obj)})

        return JsonResponse({'success': True, 'options': options})
    except Exception as e:
        return JsonResponse({'success': False, 'options': [], 'message': str(e)})
