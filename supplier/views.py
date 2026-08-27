import logging
from decimal import Decimal

logger = logging.getLogger(__name__)
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

from utils.templatetags.utils_extras import smart_float
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
    status = request.GET.get("status", "active")
    if not status:
        status = "active"
    search = request.GET.get("search", "")
    has_debt = request.GET.get("has_debt", "")
    currency_id = request.GET.get("currency", "")
    entity_type = request.GET.get("entity_type", "")
    primary_type = request.GET.get("primary_type", "")
    order_by = request.GET.get("order_by", "balance")
    order_dir = request.GET.get("order_dir", "desc")

    suppliers = Supplier.objects.select_related("primary_type__settings", "default_currency", "default_payment_term").all()

    if status == "active":
        suppliers = suppliers.filter(is_active=True)
    elif status == "inactive":
        suppliers = suppliers.filter(is_active=False)
    # if status == 'all', no filtering is applied

    if currency_id:
        suppliers = suppliers.filter(default_currency_id=currency_id)

    if entity_type:
        suppliers = suppliers.filter(entity_type=entity_type)

    if primary_type:
        suppliers = suppliers.filter(primary_type_id=primary_type)

    if search:
        from utils.search import smart_search_filter
        suppliers = smart_search_filter(
            suppliers,
            search,
            text_fields=['name', 'contact_person', 'address'],
            code_fields=['code', 'phone', 'secondary_phone', 'tax_number', 'national_id', 'commercial_registry']
        )

    if has_debt == "1":
        suppliers = suppliers.filter(balance__gt=0)
    elif has_debt == "0":
        suppliers = suppliers.filter(balance__lte=0)

    # جلب العملات والتصنيفات المستخدمة فقط في الموردين
    from financial.models.currency import Currency
    used_currency_ids = Supplier.objects.exclude(default_currency__isnull=True).values_list('default_currency_id', flat=True).distinct()
    currencies = Currency.objects.filter(id__in=used_currency_ids).order_by('name')

    used_type_ids = Supplier.objects.exclude(primary_type__isnull=True).values_list('primary_type_id', flat=True).distinct()
    supplier_types = SupplierType.objects.filter(id__in=used_type_ids).order_by('name')
    if not supplier_types.exists():
        supplier_types = SupplierType.objects.filter(is_active=True).order_by('name')

    used_entity_types = Supplier.objects.exclude(entity_type__isnull=True).exclude(entity_type='').values_list('entity_type', flat=True).distinct()
    entity_types = [choice for choice in Supplier.ENTITY_TYPES if choice[0] in used_entity_types]
    if not entity_types:
        entity_types = Supplier.ENTITY_TYPES

    # التصدير المزدوج: تصدير كافة البيانات المفلترة من الباك إند
    if request.GET.get('export') == 'excel':
        from utils.export import export_queryset_to_excel
        return export_queryset_to_excel(
            suppliers,
            filename="suppliers_export.xlsx",
            fields=[
                "code", "name", "entity_type", "primary_type__name", "phone",
                "contact_person", "tax_number", "national_id", "commercial_registry",
                "bank_name", "bank_account_number", "balance", "credit_limit",
                "is_preferred", "is_active"
            ],
            headers=[
                "الكود", "اسم المورد", "الكيان القانوني", "مجال التوريد", "رقم الهاتف",
                "الشخص المسؤول", "الرقم الضريبي", "الرقم القومي", "السجل التجاري",
                "اسم البنك", "رقم الحساب/IBAN", "الاستحقاق الحالي", "سقف التسهيلات",
                "مفضل", "نشط"
            ]
        )

    active_suppliers = suppliers.filter(is_active=True).count()
    preferred_suppliers = suppliers.filter(is_preferred=True).count()
    total_debt = suppliers.aggregate(total=models.Sum('balance'))['total'] or 0
    total_purchases = 0

    # Whitelist الفرز الأمني
    allowed_sort_fields = {
        'name': 'name',
        'code': 'code',
        'is_preferred': 'is_preferred',
        'actual_balance': 'balance',
        'is_active': 'is_active',
    }

    # الترقيم والفرز الـ SSR عبر المحرك المركزي
    from core.utils import paginate_queryset, render_paginated_response
    pagination_data = paginate_queryset(
        suppliers,
        request,
        default_per_page=25,
        allowed_sort_fields=allowed_sort_fields
    )

    page_obj = pagination_data['page_obj']

    from financial.services.partner_exposure_service import BusinessPartnerExposureService
    from core.presenters.currency_exposure_presenter import CurrencyExposurePresenter, get_currency_symbol

    page_supplier_ids = [s.pk for s in page_obj]
    exposure_map = BusinessPartnerExposureService.get_open_balances("supplier", page_supplier_ids)

    # إضافة عدد الخدمات كعناصر سريعة لصفحة العرض الحالية فقط (تحسين أداء كبير)
    from supplier.models import SupplierService
    services_counts = {
        row['supplier_id']: row['cnt']
        for row in SupplierService.objects.filter(
            supplier_id__in=page_supplier_ids,
            is_active=True
        ).values('supplier_id').annotate(cnt=models.Count('id'))
    }
    for s in page_obj:
        cnt = services_counts.get(s.pk, 0)
        s.services_count = f'<span class="badge bg-{"warning text-dark" if cnt > 0 else "secondary"}">{cnt}</span>'
        curr_code = s.default_currency.code if s.default_currency else "EGP"
        curr_symbol = (s.default_currency.symbol if s.default_currency and s.default_currency.symbol else "") or get_currency_symbol(curr_code)
        s.currency_display = f'<span class="badge bg-light text-dark border">{curr_symbol}</span>'
        supplier_dtos = exposure_map.get(s.pk, [])
        s.actual_balance_display = CurrencyExposurePresenter.render_html_badges(supplier_dtos)

    suppliers_page = page_obj

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
            "key": "currency_display",
            "label": "العملة",
            "sortable": False,
            "format": "html",
            "class": "text-center",
        },
        {
            "key": "is_preferred",
            "label": "مفضل",
            "sortable": True,
            "format": "boolean_badge",
        },
        {
            "key": "actual_balance_display",
            "label": "الاستحقاق",
            "sortable": True,
            "format": "html",
            "class": "text-center",
        },
        {
            "key": "services_count",
            "label": "الخدمات",
            "sortable": False,
            "class": "text-center",
            "format": "html",
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
            "data_attrs": 'onclick="reactivateSupplier(this.closest(\'tr\').dataset.id)"',
        },
        {
            "modal": True,
            "icon": "fa-trash-alt",
            "class": "action-delete text-danger",
            "label": "حذف / أرشفة",
        },
    ]

    inactive_suppliers = Supplier.objects.filter(is_active=False).count()
    from core.models import SystemSetting
    daftra_enabled = SystemSetting.get_setting('daftra_enabled', 'false') == 'true'

    is_archive_view = (status == "inactive")
    supplier_header_buttons = []

    if is_archive_view:
        supplier_header_buttons.append({
            "url": reverse("supplier:supplier_list"),
            "icon": "fa-truck",
            "text": "الموردون النشطون",
            "class": "btn-outline-primary",
        })
    else:
        supplier_header_buttons.append({
            "url": reverse("supplier:supplier_add"),
            "icon": "fa-plus",
            "text": "إضافة مورد",
            "class": "btn-primary",
        })
        supplier_header_buttons.append({
            "url": reverse("supplier:supplier_list") + "?status=inactive",
            "icon": "fa-archive",
            "text": f"الأرشيف ({inactive_suppliers})" if inactive_suppliers > 0 else "الأرشيف",
            "class": "btn-outline-secondary",
        })

    if daftra_enabled:
        supplier_header_buttons.append({
            "onclick": "syncWithDaftra('suppliers')",
            "icon": "fa-sync",
            "text": "مزامنة دفترة",
            "class": "btn-outline-info",
        })

    page_title = "أرشيف الموردين" if is_archive_view else "قائمة الموردين"
    page_subtitle = "عرض وإدارة الموردين المؤرشفين وغير النشطين" if is_archive_view else "إدارة الموردين وعرض بياناتهم ومعاملاتهم المالية"
    page_icon = "fas fa-archive" if is_archive_view else "fas fa-truck"

    context = {
        **pagination_data,
        "suppliers": suppliers_page,
        "headers": headers,
        "action_buttons": action_buttons,
        "active_suppliers": active_suppliers,
        "inactive_suppliers": inactive_suppliers,
        "preferred_suppliers": preferred_suppliers,
        "total_debt": total_debt,
        "total_purchases": total_purchases,
        "supplier_types": supplier_types,
        "currencies": currencies,
        "entity_types": entity_types,
        "show_export": True,
        # بيانات الهيدر
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "page_icon": page_icon,
        # أزرار الهيدر
        "header_buttons": supplier_header_buttons,
        # البريدكرمب
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الموردين", "url": reverse("supplier:supplier_list") if is_archive_view else None, "active": not is_archive_view},
            *([{"title": "الأرشيف", "active": True}] if is_archive_view else []),
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
                        'supplier_name': supplier.name,
                        'supplier_code': supplier.code,
                        'payment_terms': supplier.payment_terms or '',
                        'default_currency_id': supplier.default_currency_id,
                        'default_currency_symbol': supplier.default_currency.symbol if supplier.default_currency else '',
                        'tax_number': supplier.tax_number or '',
                        'entity_type': supplier.entity_type,
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
    حذف أو أرشفة مورد (فحص سيادي ذكي وتحديث تفاعلي بالـ AJAX)
    """
    from supplier.services.supplier_service import SupplierService
    supplier = get_object_or_404(Supplier, pk=pk)

    # 1. طلب الفحص المسبق اللحظي (Pre-check)
    if request.GET.get('precheck') == '1' or (request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.method == 'GET'):
        can_delete, summary, exposure = SupplierService.can_delete_supplier(supplier)
        from core.templatetags.custom_filters import smart_float
        from core.presenters.currency_exposure_presenter import get_currency_symbol
        curr_code = supplier.default_currency.code if supplier.default_currency else "EGP"
        curr_sym = (supplier.default_currency.symbol if supplier.default_currency and supplier.default_currency.symbol else "") or get_currency_symbol(curr_code)
        
        debt_str = f"{smart_float(exposure['balance'])} {curr_sym}" if exposure['has_debt'] else ""

        return JsonResponse({
            'success': True,
            'id': supplier.id,
            'name': supplier.name,
            'code': supplier.code,
            'can_delete': can_delete,
            'has_debt': exposure['has_debt'],
            'debt_display': debt_str,
            'prepaid_display': "",
            'transactions_summary': summary,
        })

    # 2. تنفيذ الحذف أو الأرشفة (POST)
    if request.method == "POST":
        res = SupplierService.delete_supplier(supplier, user=request.user)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'action': res['action'],
                'message': res['message'],
                'redirect_url': reverse('supplier:supplier_list'),
            })

        if res['action'] == 'deleted':
            messages.success(request, res['message'])
        else:
            messages.warning(request, res['message'])
        return redirect("supplier:supplier_list")

    # 3. العرض العادي للشاشة المنفصلة (Fallback)
    can_delete, summary, exposure = SupplierService.can_delete_supplier(supplier)
    context = {
        "supplier": supplier,
        "can_delete": can_delete,
        "summary": summary,
        "exposure": exposure,
        "page_title": f"حذف / أرشفة المورد: {supplier.name}",
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
            {"title": "حذف / أرشفة", "active": True},
        ],
    }
    return render(request, "supplier/core/supplier_delete.html", context)


@login_required
def supplier_reactivate(request, pk):
    """
    إعادة تنشيط مورد مؤرشف وحسابه المالي التابع
    """
    from supplier.services.supplier_service import SupplierService
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST":
        res = SupplierService.reactivate_supplier(supplier, user=request.user)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': res['message']})
        messages.success(request, res['message'])
        return redirect("supplier:supplier_detail", pk=supplier.pk)
    return redirect("supplier:supplier_detail", pk=supplier.pk)


@login_required
def supplier_detail(request, pk):
    """
    عرض تفاصيل المورد ودفعات الفواتير
    """
    from django.db.models import Sum, Count, Q, Max
    from decimal import Decimal

    supplier = get_object_or_404(
        Supplier.objects.select_related(
            "primary_type__settings"
        ),
        pk=pk,
    )
    unallocated_prepaid = supplier.available_prepaid_balance

    # جلب دفعات فواتير المشتريات والدفعات المباشرة/تحت الحساب المرتبطة بالمورد
    from purchase.models import PurchasePayment
    from supplier.models import SupplierAdvancePayment

    purchase_payments = list(PurchasePayment.objects.filter(purchase__supplier=supplier).select_related("purchase", "currency", "purchase__currency", "created_by").order_by("-payment_date"))
    advance_payments = list(SupplierAdvancePayment.objects.filter(supplier=supplier).select_related("currency", "created_by").order_by("-payment_date"))

    # توحيد قائمة المدفوعات لعرضها في التاب والتصدير
    payments_list = []
    for pp in purchase_payments:
        curr = pp.currency or (pp.purchase.currency if pp.purchase else None)
        payments_list.append({
            "id": pp.id,
            "payment_date": pp.payment_date,
            "created_at": pp.created_at,
            "amount": pp.amount,
            "currency": curr,
            "currency_symbol": curr.symbol if curr else "ج.م",
            "payment_method": pp.source_display_info if hasattr(pp, "source_display_info") else "سداد فاتورة",
            "reference_number": pp.reference_number or f"PAY-{pp.id}",
            "notes": pp.notes or "-",
            "purchase_id": pp.purchase.id if pp.purchase else None,
            "purchase_number": pp.purchase.number if pp.purchase else "-",
            "type_display": "سداد فاتورة",
            "raw_object": pp,
        })

    for sap in advance_payments:
        curr = sap.currency
        payments_list.append({
            "id": sap.id,
            "payment_date": sap.payment_date,
            "created_at": sap.created_at,
            "amount": sap.amount,
            "currency": curr,
            "currency_symbol": curr.symbol if curr else "ج.م",
            "payment_method": "رصيد مسبق / دفعة مقدمة",
            "reference_number": sap.reference_number or f"ADV-{sap.id}",
            "notes": sap.notes or "دفعة من تحت الحساب للمورد",
            "purchase_id": None,
            "purchase_number": "دفعة مقدمة (تحت الحساب)",
            "type_display": "دفعة مقدمة",
            "raw_object": sap,
        })

    payments_list.sort(key=lambda x: str(x["payment_date"] or ""), reverse=True)

    pur_pay_total = sum(
        pp.amount for pp in purchase_payments
        if pp.payment_method != "prepaid_balance" and getattr(pp, "source_type", None) != "PREPAID_BALANCE"
    )
    adv_pay_total = sum(sap.amount for sap in advance_payments)
    total_payments = pur_pay_total + adv_pay_total



    # جلب فواتير الشراء المؤكدة المرتبطة بالمورد
    purchases = Purchase.objects.filter(supplier=supplier, status="confirmed").order_by("-date")
    purchases_count = purchases.count()

    # حساب إجمالي المشتريات
    total_purchases = purchases.aggregate(total=Sum("total"))["total"] or 0

    # حساب عدد المنتجات الفريدة في فواتير الشراء
    purchase_items = PurchaseItem.objects.filter(purchase__supplier=supplier)
    products_count = purchase_items.values("product").distinct().count()

    # جلب المنتجات مع تفاصيل الشراء
    from django.db.models import Max, Min, Avg, Count

    supplier_products = list(
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
    )

    # تحديد عملة الشراء الفعلية لكل منتج من فواتير المورد
    item_currencies = {}
    for pi in purchase_items.select_related('purchase__currency').order_by('purchase__created_at'):
        if pi.purchase and pi.purchase.currency:
            item_currencies[pi.product_id] = pi.purchase.currency.symbol or pi.purchase.currency.code

    for prod in supplier_products:
        p_id = prod.get("product__id")
        prod["currency_symbol"] = item_currencies.get(p_id) or (supplier.default_currency.symbol if supplier.default_currency else "ج.م")

    # تاريخ آخر معاملة
    last_transaction_date = None
    if payments_list or purchases.exists():
        last_payment_date = payments_list[0]["payment_date"] if payments_list else None
        last_purchase_date = purchases.first().date if purchases.exists() else None

        if last_payment_date and last_purchase_date:
            last_transaction_date = max(last_payment_date, last_purchase_date)
        elif last_payment_date:
            last_transaction_date = last_payment_date
        else:
            last_transaction_date = last_purchase_date

    # الحصول المباشر على الحساب المالي للمورد
    financial_account = supplier.financial_account

    # جلب القيود المحاسبية المرتبطة بالمورد
    from financial.models import JournalEntry
    journal_entries = []
    journal_entries_count = 0

    try:
        purchase_ids = [p.id for p in purchases]
        query = Q()
        if financial_account:
            query |= Q(lines__account=financial_account)
        for p_id in purchase_ids:
            query |= Q(reference__icontains=f"PURCH-{p_id}") | Q(reference__icontains=f"{p_id}")

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

    # 1. جلب الأرصدة الافتتاحية من الأستاذ المساعد للمورد
    from supplier.models import SupplierTransaction
    op_txns = SupplierTransaction.objects.filter(
        supplier=supplier,
        transaction_number__iregex=r'^(OPN|OPB)'
    )
    for op_tx in op_txns:
        curr_code = op_tx.currency or "EGP"
        curr_sym = get_currency_symbol(curr_code)
        is_bill = (op_tx.transaction_type == "BILL")
        # في محاسبة الموردين: فاتورة الشراء دائن (مستحقات للمورد) والسداد/الدفعة مدين
        credit_val = op_tx.functional_amount if is_bill else Decimal("0.00")
        debit_val = op_tx.functional_amount if not is_bill else Decimal("0.00")
        f_credit = op_tx.foreign_amount if is_bill else Decimal("0.00")
        f_debit = op_tx.foreign_amount if not is_bill else Decimal("0.00")
        ledger_url = (reverse("financial:ledger_report") + f"?account={supplier.financial_account.id}") if supplier.financial_account else "#"
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

    # 2. جلب فواتير الشراء المؤكدة
    for purchase in purchases:
        curr_code = purchase.currency.code if (hasattr(purchase, 'currency') and purchase.currency) else (getattr(purchase, 'currency', None) or "EGP")
        curr_sym = (purchase.currency.symbol if (hasattr(purchase, 'currency') and purchase.currency and purchase.currency.symbol) else None) or get_currency_symbol(curr_code)
        raw_rate = getattr(purchase, 'exchange_rate', Decimal("1.000000")) or Decimal("1.000000")
        rate = Decimal(str(raw_rate))
        func_total = getattr(purchase, 'total_functional', None) or (Decimal(str(purchase.total)) * rate).quantize(Decimal("0.01"))
        purch_url = reverse("purchase:purchase_detail", kwargs={"pk": purchase.id})
        transactions.append(
            {
                "date": purchase.created_at or purchase.date,
                "reference": purchase.number,
                "purchase_id": purchase.id,
                "type": "purchase",
                "description": f"فاتورة شراء رقم {purchase.number}",
                "currency": curr_code,
                "currency_symbol": curr_sym,
                "debit": Decimal("0.00"),
                "credit": func_total,
                "foreign_debit": Decimal("0.00"),
                "foreign_credit": purchase.total if curr_code != "EGP" else Decimal("0.00"),
                "exchange_rate": rate,
                "balance": Decimal("0.00"),
                "foreign_balance": Decimal("0.00"),
                "url": purch_url,
            }
        )

    # 3. جلب مرتجعات المشتريات المؤكدة
    try:
        from purchase.models import PurchaseReturn
        purchase_returns = PurchaseReturn.objects.filter(
            purchase__supplier=supplier,
            status="confirmed"
        ).select_related("purchase", "purchase__currency")
        for pr in purchase_returns:
            purch_obj = pr.purchase
            curr_code = purch_obj.currency.code if (purch_obj and purch_obj.currency) else "EGP"
            curr_sym = get_currency_symbol(curr_code)
            raw_rate = getattr(purch_obj, 'exchange_rate', Decimal("1.000000")) if purch_obj else Decimal("1.000000")
            rate = Decimal(str(raw_rate or "1.000000"))
            func_total = (Decimal(str(pr.total or "0.00")) * rate).quantize(Decimal("0.01"))
            pr_url = reverse("purchase:purchase_return_detail", kwargs={"pk": pr.id})
            purch_num = purch_obj.number if purch_obj else "-"
            transactions.append({
                "date": pr.created_at or pr.date,
                "reference": pr.number,
                "type": "purchase_return",
                "description": f"مرتجع مشتريات رقم {pr.number} (فاتورة {purch_num})",
                "currency": curr_code,
                "currency_symbol": curr_sym,
                "debit": func_total,
                "credit": Decimal("0.00"),
                "foreign_debit": pr.total if curr_code != "EGP" else Decimal("0.00"),
                "foreign_credit": Decimal("0.00"),
                "exchange_rate": rate,
                "balance": Decimal("0.00"),
                "foreign_balance": Decimal("0.00"),
                "url": pr_url,
            })
    except Exception as e:
        logger.warning(f"Error loading PurchaseReturns for supplier statement: {e}")

    # 4. جلب المدفوعات النقدية والبنكية مع استبعاد سدادات الرصيد المسبق الداخلية
    for pp in purchase_payments:
        if pp.payment_method == "prepaid_balance" or getattr(pp, "source_type", None) == "PREPAID_BALANCE" or pp.payment_method == "advance_balance":
            continue

        pur_curr = pp.purchase.currency.code if (pp.purchase and pp.purchase.currency) else "EGP"
        pay_curr = pp.payment_currency.code if hasattr(pp, 'payment_currency') and pp.payment_currency else (pp.currency.code if hasattr(pp, 'currency') and pp.currency else pur_curr)
        curr_code = pur_curr if pur_curr != "EGP" else pay_curr
        curr_sym = get_currency_symbol(curr_code)
        rate = getattr(pp, 'payment_exchange_rate', None) or (pp.purchase.exchange_rate if pp.purchase else Decimal("1.000000")) or Decimal("1.000000")

        settled_val = getattr(pp, 'amount_settled_purchase_currency', None) or getattr(pp, 'amount_settled_invoice_currency', None)
        if not settled_val or settled_val <= Decimal("0.00"):
            settled_val = pp.amount
        func_val = getattr(pp, 'amount_functional', None)
        if not func_val or func_val <= Decimal("0.00"):
            func_val = (settled_val * Decimal(str(rate))).quantize(Decimal("0.01"))

        pay_url = reverse("purchase:payment_detail", kwargs={"pk": pp.id})
        transactions.append({
            "date": pp.created_at or pp.payment_date,
            "reference": pp.reference_number or f"PAY-{pp.id}",
            "type": "payment",
            "description": f"سداد فاتورة مشتريات ({pp.purchase.number if pp.purchase else '-'}) - {pp.get_payment_method_display() if hasattr(pp, 'get_payment_method_display') else pp.payment_method}",
            "currency": curr_code,
            "currency_symbol": curr_sym,
            "debit": func_val,
            "credit": Decimal("0.00"),
            "foreign_debit": settled_val if curr_code != "EGP" else Decimal("0.00"),
            "foreign_credit": Decimal("0.00"),
            "exchange_rate": rate,
            "balance": Decimal("0.00"),
            "foreign_balance": Decimal("0.00"),
            "url": pay_url,
        })

    for sap in advance_payments:
        curr_code = sap.currency.code if (hasattr(sap, 'currency') and sap.currency) else "EGP"
        curr_sym = get_currency_symbol(curr_code)
        rate = getattr(sap, 'exchange_rate', Decimal("1.000000")) or Decimal("1.000000")
        amt = Decimal(str(sap.amount or "0.00"))
        func_amt = (amt * Decimal(str(rate))).quantize(Decimal("0.01"))
        if getattr(sap, 'journal_entry_id', None):
            sap_url = reverse("financial:journal_entries_detail", kwargs={"pk": sap.journal_entry_id})
        elif getattr(supplier, 'financial_account_id', None):
            sap_url = reverse("financial:ledger_report") + f"?account={supplier.financial_account_id}"
        else:
            sap_url = "#"

        transactions.append({
            "date": getattr(sap, 'created_at', None) or sap.payment_date,
            "reference": sap.reference_number or f"SAP-{sap.id}",
            "type": "payment",
            "description": f"دفعة مقدمة للمورد تحت الحساب ({getattr(sap, 'notes', '') or 'رصيد مسبق'})",
            "currency": curr_code,
            "currency_symbol": curr_sym,
            "debit": func_amt,
            "credit": Decimal("0.00"),
            "foreign_debit": amt if curr_code != "EGP" else Decimal("0.00"),
            "foreign_credit": Decimal("0.00"),
            "exchange_rate": rate,
            "balance": Decimal("0.00"),
            "foreign_balance": Decimal("0.00"),
            "url": sap_url,
        })

    # 5. جلب قيود التسوية اليدوية المباشرة على حساب المورد
    if financial_account:
        try:
            from financial.models.journal_entry import JournalEntryLine
            manual_lines = JournalEntryLine.objects.filter(
                account=financial_account,
                journal_entry__status='posted'
            ).exclude(
                journal_entry__reference__istartswith='PURCH-'
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
            logger.warning(f"Error loading manual JVs for supplier statement: {e}")

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
    def get_supplier_txn_sort_key(t):
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

    filtered_transactions.sort(key=get_supplier_txn_sort_key)

    # 9. حساب الرصيد التراكمي للمورد (دائن - مدين)
    running_balance = Decimal("0.00")
    running_foreign_balance = Decimal("0.00")
    for t in filtered_transactions:
        running_balance = running_balance + Decimal(str(t["credit"])) - Decimal(str(t["debit"]))
        running_foreign_balance = running_foreign_balance + Decimal(str(t.get("foreign_credit", 0))) - Decimal(str(t.get("foreign_debit", 0)))
        t["balance"] = running_balance
        t["foreign_balance"] = running_foreign_balance

    filtered_transactions.reverse()

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
    for pay_item in payments_list:
        purchase_num = pay_item.get("purchase_number", "-")
        if pay_item.get("purchase_id"):
            purchase_number_html = f'<a href="{reverse("purchase:purchase_detail", args=[pay_item["purchase_id"]])}" class="text-decoration-none text-nowrap"><code class="bg-light px-2 py-1 rounded text-nowrap" style="white-space: nowrap !important;">{purchase_num}</code></a>'
        elif purchase_num != "-":
            purchase_number_html = f'<span class="badge bg-secondary-subtle text-secondary">{purchase_num}</span>'
        else:
            purchase_number_html = "لا يوجد"

        raw_obj = pay_item.get("raw_object")
        payment_method_display = pay_item.get("payment_method", "غير محدد")
        if raw_obj and getattr(raw_obj, "financial_account", None):
            payment_method_display = raw_obj.financial_account.name
        elif raw_obj and getattr(raw_obj, "payment_method", None):
            try:
                from financial.models import ChartOfAccounts
                account = ChartOfAccounts.objects.filter(code=raw_obj.payment_method).first()
                if account:
                    payment_method_display = account.name
            except Exception:
                pass

        method_html = f'<span class="badge bg-info">{payment_method_display}</span>' if not str(payment_method_display).startswith('<span') else payment_method_display

        payments_data.append({
            "id": pay_item["id"],
            "created_at": pay_item["created_at"] or pay_item["payment_date"],
            "purchase__number": purchase_number_html,
            "amount": pay_item["amount"],
            "currency": pay_item.get("currency"),
            "currency_symbol": pay_item.get("currency_symbol", "ج.م"),
            "payment_method": method_html,
            "notes": pay_item.get("notes") or "لا توجد ملاحظات",
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
            "label": "التاريخ",
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
            "width": "140px",
        },
        {
            "key": "purchase__number",
            "label": "رقم الفاتورة",
            "sortable": True,
            "class": "text-center text-nowrap",
            "format": "html",
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

    # شارات وأزرار الإجراءات السريعة للمورد في الهيدر
    if not supplier.is_active:
        header_badges = [
            {
                "text": "مورد مؤرشف ومعطل",
                "class": "bg-warning text-dark fw-bold",
                "icon": "fas fa-archive",
                "title": "هذا المورد غير نشط ومؤرشف",
            }
        ]
        header_buttons = [
            {
                "url": "#",
                "icon": "fa-undo",
                "text": "إعادة تنشيط المورد",
                "class": "btn-success fw-bold",
                "id": "btn-reactivate-supplier",
                "onclick": "const f = document.getElementById('reactivate-supplier-form'); if(f) { f.submit(); } else { const nf = document.createElement('form'); nf.method='POST'; nf.action='" + reverse('supplier:supplier_reactivate', kwargs={'pk': supplier.pk}) + "'; const c = document.querySelector('[name=csrfmiddlewaretoken]'); if(c) { const i = document.createElement('input'); i.type='hidden'; i.name='csrfmiddlewaretoken'; i.value=c.value; nf.appendChild(i); } document.body.appendChild(nf); nf.submit(); }",
                "title": "إعادة تنشيط المورد وحسابه المالي",
            }
        ]
    else:
        header_badges = []
        header_buttons = [
            {
                "url": "#",
                "icon": "fa-plus-circle",
                "text": "إضافة رصيد مسبق",
                "class": "btn-primary",
                "toggle": "modal",
                "target": "#addSupplierAdvanceModal",
                "title": "إضافة رصيد مسبق / دفعة مقدمة للمورد",
            },
            {
                "url": reverse("purchase:purchase_create_for_supplier", kwargs={"supplier_id": supplier.id}),
                "icon": "fa-plus",
                "text": "فاتورة مشتريات",
                "class": "btn-success",
                "title": "إنشاء فاتورة مشتريات جديدة من هذا المورد",
            },
            {
                "url": "#",
                "icon": "fa-ellipsis-v",
                "text": "",
                "class": "btn-outline-secondary",
                "id": "actions-menu-btn",
                "toggle": "modal",
                "target": "#actionsModal",
                "title": "خيارات وإجراءات إضافية",
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
    credit_limit = getattr(supplier, 'credit_limit', Decimal('0.00')) or Decimal('0.00')
    available_credit = credit_limit - total_purchases + total_payments

    from financial.services.account_helper import AccountHelperService
    financial_accounts_list = list(
        AccountHelperService.get_expense_and_settlement_accounts()
    )

    context = {
        "supplier": supplier,
        "financial_accounts": financial_accounts_list,
        "available_credit": available_credit,
        "header_badges": header_badges,
        "header_buttons": header_buttons,
        "quick_action_buttons": header_buttons,
        "payments": payments_data,  # استخدام البيانات المحولة
        "purchases": purchases,
        "purchases_count": purchases_count,
        "total_purchases": total_purchases,
        "products_count": products_count,
        "supplier_products": supplier_products,
        "total_payments": total_payments,
        "transactions": filtered_transactions,
        "available_currencies": available_currencies,
        "active_currency": active_currency,
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
        "journal_click_url": "financial:journal_entries_detail",
        # بيانات الهيدر
        "page_title": f"{supplier.name}",
        "page_subtitle": "معلومات وبيانات المورد الكاملة",
        "page_icon": "fas fa-truck",
        "unallocated_prepaid": unallocated_prepaid,
        # نوع المورد (للعرض على اليسار)
        "supplier_type_badge": {
            "text": supplier.primary_type.settings.name if supplier.primary_type and supplier.primary_type.settings else (supplier.primary_type.name if supplier.primary_type else "غير محدد"),
            "icon": supplier.primary_type.settings.icon if supplier.primary_type and supplier.primary_type.settings else (supplier.primary_type.icon if supplier.primary_type else "fas fa-industry"),
            "color": supplier.primary_type.settings.color if supplier.primary_type and supplier.primary_type.settings else (supplier.primary_type.color if supplier.primary_type else "#6c757d"),
        } if supplier.primary_type else None,
    }

    from core.models import SystemSetting
    currency_symbol = SystemSetting.get_currency_symbol()

    from financial.services.partner_exposure_service import BusinessPartnerExposureService
    from core.presenters.currency_exposure_presenter import CurrencyExposurePresenter

    # Badges في الهيدر
    header_badges = [
        {
            "text": f"{supplier.code}",
            "class": "bg-primary",
            "icon": "fas fa-hashtag",
        },
    ]

    from django.utils.safestring import mark_safe
    dtos = BusinessPartnerExposureService.get_open_balances("supplier", [supplier.id]).get(supplier.id, [])
    vms = CurrencyExposurePresenter.build_view_models(dtos)
    if vms:
        vms_sorted = sorted(vms, key=lambda vm: 0 if (getattr(vm, 'currency_symbol', '') == 'ج.م' or getattr(vm, 'currency_code', '') == 'EGP' or getattr(vm, 'currency', '') == 'EGP') else 1)
        due_parts = [f'<span class="badge-amount-pill">{vm.formatted_amount} {vm.currency_symbol}</span>' for vm in vms_sorted]
        header_badges.append({
            "is_badge": True,
            "icon": "fas fa-hand-holding-usd",
            "text": mark_safe(f"مستحق للمورد: {' '.join(due_parts)}"),
            "class": "bg-danger text-white",
            "title": "إجمالي الفواتير المستحقة للمورد حسب العملات",
        })
    elif supplier.actual_balance != Decimal("0.00"):
        header_badges.append({
            "text": mark_safe(f"الاستحقاق: <span class=\"badge-amount-pill\">{smart_float(supplier.actual_balance)} {currency_symbol}</span>"),
            "class": "bg-danger" if supplier.actual_balance > 0 else "bg-success",
            "icon": "fas fa-arrow-up" if supplier.actual_balance > 0 else "fas fa-arrow-down",
        })

    from financial.services.partner_advance_service import PartnerAdvanceService
    prepaid_bals = PartnerAdvanceService.get_all_balances(supplier)

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
    context["header_badges"] = header_badges
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

    from financial.services.partner_advance_service import PartnerAdvanceService
    from financial.models import Currency
    context["prepaid_balances"] = PartnerAdvanceService.get_all_balances(supplier)
    context["currencies"] = Currency.objects.filter(is_active=True)

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
            from supplier.services.supplier_service import SupplierService
            new_account = SupplierService.create_financial_account_for_supplier(
                supplier=supplier,
                user=request.user
            )

            if not new_account:
                error_msg = "فشل في إنشاء الحساب المحاسبي للمورد"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                messages.error(request, error_msg)
                return redirect("supplier:supplier_change_account", pk=supplier.pk)

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


@login_required
def supplier_aging_api(request, pk):
    """
    API لكشف شرائح أعمار ديون المورد الكسول (Lazy Supplier Aging Buckets)
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.services.supplier_aging_service import SupplierAgingService
    aging_data = SupplierAgingService.get_supplier_aging_report(supplier_ids=[supplier.id])
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
def add_supplier_advance_action(request, pk):
    """
    إضافة رصيد مسبق / دفعة مقدمة جديدة للمورد باختيار العملة وسعر الصرف
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST":
        from decimal import Decimal
        from financial.models import Currency
        from supplier.models import SupplierAdvancePayment
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

                advance = SupplierAdvancePayment.objects.create(
                    supplier=supplier,
                    amount=amt,
                    transaction_amount=amt,
                    currency=curr,
                    exchange_rate_snapshot=rate,
                    payment_date=payment_date_str if payment_date_str else timezone.now().date(),
                    payment_method=payment_method,
                    financial_account_id=fin_acc_id,
                    reference_number=reference_number,
                    notes=notes,
                    created_by=request.user,
                )
                PartnerAdvanceService.rebuild_snapshot(supplier, currency=curr)
                messages.success(request, f"تم تسجيل دفعة مقدمة بقيمة {amt} {curr.code if curr else ''} للمورد بنجاح (مرجع #{advance.id}).")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء إضافة الدفعة المقدمة: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء إضافة الدفعة المقدمة: {str(e)}")
        else:
            messages.error(request, "يرجى إدخال مبلغ الدفعة المقدمة بشكل صحيح.")

    return redirect("supplier:supplier_detail", pk=pk)


@login_required
def allocate_supplier_prepaid_action(request, pk):
    """
    تخصيص الدفعات المقدمة للمورد على الفواتير المفتوحة (تخصيص جماعي أو فردي)
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST":
        from supplier.services.supplier_allocation_service import SupplierAllocationService
        from financial.services.partner_advance_service import PartnerAdvanceService
        from decimal import Decimal

        purchase_ids = request.POST.getlist("purchase_ids[]") or request.POST.getlist("purchase_ids")
        amounts = request.POST.getlist("amounts[]") or request.POST.getlist("amounts")

        allocations_dict = {}
        if purchase_ids and amounts and len(purchase_ids) == len(amounts):
            for pid, amt_s in zip(purchase_ids, amounts):
                if pid and amt_s:
                    try:
                        d_amt = Decimal(str(amt_s))
                        if d_amt > Decimal("0.00"):
                            allocations_dict[int(pid)] = d_amt
                    except Exception:
                        pass

        if allocations_dict:
            try:
                audits = SupplierAllocationService.allocate_prepaid_bulk(
                    supplier_id=supplier.id,
                    allocations_dict=allocations_dict,
                    user=request.user
                )
                total_alloc = sum(a.allocated_amount for a in audits)
                PartnerAdvanceService.rebuild_all_snapshots(supplier)
                messages.success(request, f"تم التوزيع الجماعي بقيمة إجمالية {total_alloc} على {len(audits)} معاملة بنجاح.")
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء التوزيع الجماعي: {str(e)}")
        else:
            purchase_id = request.POST.get("purchase_id")
            amount_str = request.POST.get("amount")

            if purchase_id:
                from purchase.models import Purchase
                purchase = get_object_or_404(Purchase, pk=purchase_id, supplier=supplier)
                avail = supplier.available_prepaid_balance
                alloc = Decimal(amount_str) if amount_str else min(avail, purchase.amount_due)
                if alloc <= Decimal("0.00"):
                    messages.error(request, "يرجى إدخال مبلغ تخصيص أكبر من صفر.")
                elif alloc > avail:
                    messages.error(request, f"المبلغ المطلوب ({alloc}) يتجاوز رصيد الدفعات المقدمة المتاح ({avail}).")
                else:
                    try:
                        SupplierAllocationService.allocate_advance_to_purchase_bill(
                            purchase=purchase,
                            amount_to_allocate=alloc,
                            user=request.user
                        )
                        PartnerAdvanceService.rebuild_all_snapshots(supplier)
                        messages.success(request, f"تم تخصيص {alloc} من الدفعات المقدمة على الفاتورة #{purchase.number} بنجاح.")
                    except Exception as e:
                        messages.error(request, f"حدث خطأ أثناء التخصيص: {str(e)}")

    return redirect("supplier:supplier_detail", pk=pk)


