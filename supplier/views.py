import logging
from decimal import Decimal
from functools import wraps

logger = logging.getLogger(__name__)
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import models, transaction
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from utils.templatetags.utils_extras import smart_float
from .models import (
    Supplier,
    SupplierType,
    ServiceType,
)
from .forms import SupplierForm, SupplierAccountChangeForm
from purchase.models import Purchase, PurchaseItem
from financial.models import ChartOfAccounts, Currency
from .decorators import require_printing_pricing_enabled


def _get_pricing_types_map():
    from core.models import SystemModule
    if not SystemModule.objects.filter(code='printing_pricing', is_enabled=True).exists():
        return {}
    from .models import SupplierType, ServiceType
    type_service_map = {
        'press': ['offset_printing', 'ctp_plates'],
        'offset': ['offset_printing', 'ctp_plates'],
        'paper': ['paper'],
        'ctp': ['ctp_plates'],
        'coat': ['coating'],
        'cellophan': ['coating'],
        'laminat': ['coating'],
        'finish': ['finishing'],
        'pack': ['packaging'],
        'digital': ['digital_printing'],
    }
    code_to_id = {s.code: s.id for s in ServiceType.objects.filter(is_active=True)}
    pricing_types_map = {}
    for t in SupplierType.objects.filter(is_active=True).select_related('settings'):
        is_pricing = getattr(t.settings, 'is_pricing_related', False) if hasattr(t, 'settings') else False
        recommended_ids = []
        t_code = t.code.lower()
        for key, svc_codes in type_service_map.items():
            if key in t_code:
                for sc in svc_codes:
                    if sc in code_to_id and code_to_id[sc] not in recommended_ids:
                        recommended_ids.append(code_to_id[sc])
        pricing_types_map[str(t.id)] = {
            'is_pricing': is_pricing,
            'recommended_service_ids': recommended_ids
        }
    return pricing_types_map



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
    provided_service = request.GET.get("provided_service", "")
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

    if provided_service:
        suppliers = suppliers.filter(provided_services__code=provided_service)

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
        "provided_services_list": ServiceType.objects.filter(is_active=True).order_by('order', 'name'),
        "selected_provided_service": provided_service,
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

    return render_paginated_response(
        request,
        "supplier/core/supplier_list.html",
        context,
        table_template_name="supplier/core/partials/supplier_table.html"
    )


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
                    form.save_m2m()
                    if supplier.is_pricing_supplier and not supplier.provided_services.exists():
                        from .models import ServiceType
                        allowed = supplier.get_allowed_service_codes()
                        if allowed:
                            supplier.provided_services.set(ServiceType.objects.filter(code__in=allowed, is_active=True))
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
        "pricing_types_map": _get_pricing_types_map(),
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        context['is_modal'] = True
        html = render_to_string("supplier/core/supplier_modal_form.html", context, request=request)
        return JsonResponse({'html': html})
    
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
                with transaction.atomic():
                    supplier = form.save(commit=False)
                    supplier.created_by = request.user
                    supplier.save()
                    form.save_m2m()
                    if supplier.is_pricing_supplier and not supplier.provided_services.exists():
                        from .models import ServiceType
                        allowed = supplier.get_allowed_service_codes()
                        if allowed:
                            supplier.provided_services.set(ServiceType.objects.filter(code__in=allowed, is_active=True))
                
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
                        'is_pricing': supplier.is_pricing_supplier,
                        'detail_url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk}),
                        'redirect_url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk}) + ('?action=seed_matrix' if supplier.is_pricing_supplier else ''),
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
        "pricing_types_map": _get_pricing_types_map(),
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
            supplier = form.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'تم تعديل بيانات المورد "{supplier.name}" بنجاح',
                    'supplier_id': supplier.id,
                    'supplier_name': supplier.name,
                    'supplier_code': supplier.code,
                    'is_pricing': supplier.is_pricing_supplier,
                    'detail_url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk}),
                })
            messages.success(request, _("تم تعديل بيانات المورد بنجاح"))
            return redirect("supplier:supplier_list")
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                })
    else:
        form = SupplierForm(instance=supplier)

    context = {
        "form": form,
        "supplier": supplier,
        "pricing_types_map": _get_pricing_types_map(),
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

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        context['is_modal'] = True
        html = render_to_string("supplier/core/supplier_modal_form.html", context, request=request)
        return JsonResponse({'html': html})
    
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
            "currency_symbol": curr.symbol if curr else (supplier.default_currency.symbol if (supplier.default_currency and supplier.default_currency.symbol) else get_currency_symbol(None)),
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
            "currency_symbol": curr.symbol if curr else (supplier.default_currency.symbol if (supplier.default_currency and supplier.default_currency.symbol) else get_currency_symbol(None)),
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
    purchases_qs = Purchase.objects.filter(supplier=supplier, status="confirmed").order_by("-date").prefetch_related('items__product__unit')
    purchases = []
    for p in purchases_qs:
        badges = []
        for it in p.items.all():
            p_name = it.product.name if it.product else 'منتج'
            badges.append(
                f'<span class="badge bg-light text-dark border me-1 mb-1" style="font-size: 0.85rem;">'
                f'<i class="fas fa-box text-primary me-1"></i>{p_name}'
                f'</span>'
            )
        p.items_summary = "".join(badges) if badges else '<span class="text-muted">-</span>'
        purchases.append(p)
    purchases_count = len(purchases)

    # حساب إجمالي المشتريات
    total_purchases = purchases_qs.aggregate(total=Sum("total"))["total"] or 0

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
        prod["currency_symbol"] = item_currencies.get(p_id) or (supplier.default_currency.symbol if (supplier.default_currency and supplier.default_currency.symbol) else get_currency_symbol(None))

    # تاريخ آخر معاملة
    last_transaction_date = None
    if payments_list or purchases:
        last_payment_date = payments_list[0]["payment_date"] if payments_list else None
        last_purchase_date = purchases[0].date if purchases else None

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
            "key": "items_summary",
            "label": "الأصناف والبنود",
            "sortable": False,
            "class": "text-start",
            "format": "html",
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
            "currency_symbol": pay_item.get("currency_symbol") or (supplier.default_currency.symbol if (supplier.default_currency and supplier.default_currency.symbol) else get_currency_symbol(None)),
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

    # جلب خدمات المورد — المرحلة الثانية (فقط إذا كان موديول التسعير مفعلاً)
    from core.models import SystemModule
    printing_pricing_enabled = SystemModule.objects.filter(code='printing_pricing', is_enabled=True).exists()
    if printing_pricing_enabled:
        from supplier.models import SupplierService, ServiceType
        supplier_services = SupplierService.objects.filter(
            supplier=supplier
        ).select_related(
            'service_type', 'machine', 'dimension', 'paper_type_ref',
            'paper_size', 'paper_origin', 'coating_type', 'finishing_type',
            'packaging_type', 'plate_size', 'currency'
        ).prefetch_related('price_tiers').order_by(
            'service_type__order', 'name'
        )
        supplier_services_count = supplier_services.count()
        allowed_service_codes = supplier.get_allowed_service_codes()
        service_types_available = ServiceType.objects.filter(is_active=True, code__in=allowed_service_codes).order_by('order', 'name')
        if not service_types_available.exists():
            service_types_available = ServiceType.objects.filter(is_active=True).order_by('order', 'name')

        # حساب مؤشرات الأداء للخدمات (KPIs)
        active_svcs = [s for s in supplier_services if s.is_active]
        offset_svcs = [s for s in active_svcs if s.service_type.code == 'offset_printing']
        avg_tirage = (sum(s.base_price for s in offset_svcs) / len(offset_svcs)) if offset_svcs else Decimal('0.00')
        services_kpis = {
            'total_services': len(supplier_services),
            'active_services': len(active_svcs),
            'active_presses': len(offset_svcs),
            'avg_tirage': avg_tirage,
            'tiered_services_count': sum(1 for s in supplier_services if s.price_tiers.filter(is_active=True).exists()),
        }

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

        # أعمدة جدول الخدمات الموحد المحدث
        supplier_services_headers = [
            {'key': 'service_type_name', 'label': 'نوع الخدمة',      'sortable': True,  'class': 'text-center', 'format': 'html',     'width': '14%'},
            {'key': 'name',              'label': 'اسم الخدمة والمواصفات', 'sortable': True,  'class': 'text-start',  'format': 'html',     'width': '24%'},
            {'key': 'pricing_formula',   'label': 'وحدة التسعير',    'sortable': True,  'class': 'text-center', 'format': 'html',     'width': '12%'},
            {'key': 'base_price',        'label': 'السعر / الوحدة',   'sortable': True,  'class': 'text-center', 'format': 'html',     'width': '13%'},
            {'key': 'setup_cost',        'label': 'فتحة الماكينة',   'sortable': True,  'class': 'text-center', 'format': 'currency', 'width': '11%'},
            {'key': 'minimum_charge',    'label': 'الحد الأدنى',     'sortable': True,  'class': 'text-center', 'format': 'currency', 'width': '10%'},
            {'key': 'tiers_count',       'label': 'الشرائح',          'sortable': False, 'class': 'text-center', 'format': 'html',     'width': '6%'},
            {'key': 'is_active',         'label': 'الحالة',           'sortable': True,  'class': 'text-center', 'format': 'status',   'width': '5%'},
            {'key': 'actions',           'label': 'الإجراءات',        'sortable': False, 'class': 'text-center', 'width': '5%'},
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
            formula_badge = f'<span class="badge bg-light text-dark border">{svc.get_pricing_formula_display()}</span>'
            sym = svc.currency_symbol
            price_html = f'<span class="fw-bold">{svc.base_price:,.2f}</span> <small class="text-muted">{sym}</small>'
            if svc.pricing_formula == 'PER_TON' and svc.price_per_ton:
                price_html += f'<br><small class="text-primary">{svc.price_per_ton:,.0f} {sym}/طن</small>'
            if svc.set_price and svc.set_price > 0:
                tir_lbl = f' (يشمل {svc.set_included_tirages} تيرم)' if (svc.service_type.code == 'offset_printing' and svc.set_included_tirages) else ''
                price_html += f'<br><span class="badge bg-success-subtle text-success border border-success-subtle mt-1" style="font-size:0.75rem;"><i class="fas fa-box-open me-1"></i>طقم: {svc.set_price:,.2f} {sym}{tir_lbl}</span>'
            
            # المواصفات الفنية المدمجة تحت الاسم
            specs_badges = []
            dim_label = svc.dimension.name if svc.dimension else svc.attributes.get('sheet_size', '')
            if dim_label:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-ruler me-1"></i>{dim_label}</span>')
            if svc.plate_size:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-layer-group me-1"></i>زنك: {svc.plate_size.name}</span>')
            if svc.coating_type:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-fill-drip me-1"></i>سلوفان: {svc.coating_type.name}</span>')
            if svc.finishing_type:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-magic me-1"></i>تشطيب: {svc.finishing_type.name}</span>')
            if svc.packaging_type:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-box me-1"></i>تعبئة: {svc.packaging_type.name}</span>')
            if svc.paper_type_ref:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-scroll me-1"></i>{svc.paper_type_ref.name}</span>')
            if svc.paper_size:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-expand me-1"></i>{svc.paper_size.name}</span>')
            if svc.paper_origin:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-globe me-1"></i>{svc.paper_origin.name}</span>')
            gsm_val = svc.gsm or (svc.paper_weight.gsm if svc.paper_weight else None)
            if gsm_val:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-weight-hanging me-1"></i>{gsm_val} جرام</span>')
            if svc.price_per_click_bw:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-print me-1"></i>كليك B&W: {svc.price_per_click_bw}</span>')
            if svc.price_per_click_color:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-palette me-1"></i>كليك ألوان: {svc.price_per_click_color}</span>')
            if svc.tooling_cost and svc.tooling_cost > 0:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-tools me-1"></i>اسطمبة: {svc.tooling_cost:,.2f}</span>')
            colors_count = svc.attributes.get('max_colors')
            if colors_count:
                specs_badges.append(f'<span class="badge bg-light text-dark border me-1" style="font-size:0.75rem;"><i class="fas fa-palette me-1"></i>{colors_count} ألوان</span>')
            specs_html = f'<div class="mt-1 d-flex flex-wrap gap-1">{"".join(specs_badges)}</div>' if specs_badges else ''
            name_html = f'<div class="fw-bold">{svc.name}</div>{specs_html}'

            actions_html = (
                f'<a href="{reverse("supplier:supplier_service_edit", kwargs={"pk": supplier.pk, "service_pk": svc.pk})}" '
                f'class="btn btn-sm btn-outline-primary" title="تعديل"><i class="fas fa-edit"></i></a>'
            )
            supplier_services_table_data.append({
                'id':                svc.pk,
                'service_type_name': type_badge,
                'name':              name_html,
                'pricing_formula':   formula_badge,
                'base_price':        price_html,
                'setup_cost':        svc.setup_cost,
                'minimum_charge':    svc.minimum_charge,
                'currency_symbol':   sym,
                'currency_code':     svc.currency_code,
                'tiers_count':       tiers_badge,
                'is_active':         svc.is_active,
                'actions':           actions_html,
                '_row_url':          reverse("supplier:supplier_service_detail", kwargs={"pk": supplier.pk, "service_pk": svc.pk}),
            })
    else:
        supplier_services = []
        supplier_services_count = 0
        service_types_available = []
        services_kpis = {
            'total_services': 0,
            'active_services': 0,
            'active_presses': 0,
            'avg_tirage': Decimal('0.00'),
            'tiered_services_count': 0,
        }
        services_by_type = {}
        supplier_services_headers = []
        supplier_services_table_data = []

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
        "services_kpis": services_kpis,
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
        from financial.services.exchange_rate_service import ExchangeRateService
        fc = ExchangeRateService.get_functional_currency()
        fc_code = fc.code if fc else 'EGP'
        fc_sym = fc.symbol if fc else 'ج.م'
        vms_sorted = sorted(vms, key=lambda vm: 0 if (getattr(vm, 'currency_code', '') == fc_code or getattr(vm, 'currency_symbol', '') == fc_sym) else 1)
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
    from printing_pricing.models import PaperType, PaperSize, PaperOrigin, PaperWeight
    context["prepaid_balances"] = PartnerAdvanceService.get_all_balances(supplier)
    context["currencies"] = Currency.objects.filter(is_active=True)
    context["seed_paper_types"] = PaperType.objects.filter(is_active=True).order_by('sort_order', 'name')
    context["seed_paper_origins"] = PaperOrigin.objects.filter(is_active=True).order_by('sort_order', 'name')
    context["seed_paper_sizes"] = PaperSize.objects.filter(is_active=True).order_by('sort_order', 'name')
    context["seed_paper_weights"] = PaperWeight.objects.filter(is_active=True).order_by('gsm')

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


def _clean_decimal_input(val_str, default='0.00', field_name='القيمة'):
    from decimal import Decimal, InvalidOperation
    if not val_str:
        return Decimal(default), None
    cleaned = str(val_str).replace(',', '.').replace('،', '.').strip()
    try:
        dec = Decimal(cleaned)
        if dec < Decimal('0.00'):
            return Decimal(default), f'{field_name} لا يمكن أن تكون سالبة'
        return dec, None
    except (InvalidOperation, ValueError):
        return Decimal(default), f'{field_name} غير صحيحة، يرجى إدخال رقم صحيح'


def _get_allowed_service_type_codes(supplier, show_all=False):
    """إرجاع أكواد الخدمات المسموح بها للمورد بحسب تخصصه مع دعم المنشآت المتكاملة"""
    if show_all:
        return ['offset_printing', 'digital_printing', 'ctp_plates', 'coating', 'finishing', 'packaging', 'paper']

    allowed = supplier.get_allowed_service_codes()
    if allowed:
        return list(allowed)

    sup_type = getattr(supplier, 'primary_type', None)
    if not sup_type or not sup_type.code:
        return ['offset_printing', 'digital_printing', 'ctp_plates', 'coating', 'finishing', 'packaging', 'paper']

    type_code = sup_type.code
    mapping = {
        'offset_press': ['offset_printing', 'ctp_plates'],
        'paper_supplier': ['paper'],
        'digital_center': ['digital_printing'],
        'ctp_center': ['ctp_plates'],
        'finishing_workshop': ['coating', 'finishing', 'packaging'],
    }
    return mapping.get(type_code, ['offset_printing', 'digital_printing', 'ctp_plates', 'coating', 'finishing', 'packaging', 'paper'])


def _get_preinjected_lookups():
    """استرجاع كافة كائنات الإعدادات بنماذجها الحقيقية وحقولها المالية والفيزيائية"""
    from core.models import SystemModule
    if not SystemModule.objects.filter(code='printing_pricing', is_enabled=True).exists():
        return {}
    try:
        from printing_pricing.models import (
            PrintingMachine, MachineDimension, PaperType, PaperWeight,
            PaperSize, PaperOrigin, CoatingType, FinishingType, PackagingType
        )
        offset_machines = list(PrintingMachine.objects.filter(machine_category='offset', is_active=True).values('id', 'name', 'code', 'colors_capacity', 'max_sheet_size'))
        for m in offset_machines:
            m['max_sheet_width'] = 0
            m['max_sheet_length'] = 0
            if m.get('max_sheet_size'):
                try:
                    parts = str(m['max_sheet_size']).lower().replace('×', 'x').split('x')
                    if len(parts) == 2:
                        m['max_sheet_width'] = float(parts[0])
                        m['max_sheet_length'] = float(parts[1])
                except Exception:
                    pass
        digital_machines = list(PrintingMachine.objects.filter(machine_category='digital', is_active=True).values('id', 'name', 'code', 'colors_capacity'))
        offset_dimensions = list(MachineDimension.objects.filter(dimension_type__in=['offset_sheet', 'sheet'], is_active=True).values('id', 'name', 'code', 'width', 'height', 'machine_id'))
        plate_sizes = list(MachineDimension.objects.filter(dimension_type='plate', is_active=True).values('id', 'name', 'code', 'width', 'height', 'machine_id'))
        paper_types = list(PaperType.objects.filter(is_active=True).values('id', 'name'))
        paper_weights = list(PaperWeight.objects.filter(is_active=True).values('id', 'gsm', 'sheets_per_pack'))
        paper_sizes = list(PaperSize.objects.filter(is_active=True).values('id', 'name', 'width', 'height'))
        paper_origins = list(PaperOrigin.objects.filter(is_active=True).values('id', 'name', 'code'))
        coating_types = list(CoatingType.objects.filter(is_active=True).values('id', 'name', 'unit_rate', 'minimum_charge'))
        finishing_types = list(FinishingType.objects.filter(is_active=True).values('id', 'name', 'unit_rate', 'setup_cost', 'tooling_cost', 'minimum_charge'))
        packaging_types = list(PackagingType.objects.filter(is_active=True).values('id', 'name', 'unit_rate', 'setup_cost', 'minimum_charge'))

        from financial.models import Currency
        from financial.services.exchange_rate_service import ExchangeRateService
        active_currencies = list(Currency.objects.filter(is_active=True).values('id', 'code', 'name', 'symbol', 'is_functional'))
        func_curr = ExchangeRateService.get_functional_currency()
        func_currency_dict = {
            'code': func_curr.code if func_curr else 'EGP',
            'symbol': func_curr.symbol if func_curr else 'ج.م',
            'name': func_curr.name if func_curr else 'جنيه مصري',
        } if func_curr else {'code': 'EGP', 'symbol': 'ج.م', 'name': 'جنيه مصري'}

        return {
            'offset_machines': offset_machines,
            'digital_machines': digital_machines,
            'offset_dimensions': offset_dimensions,
            'plate_sizes': plate_sizes,
            'paper_types': paper_types,
            'paper_weights': paper_weights,
            'paper_sizes': paper_sizes,
            'paper_origins': paper_origins,
            'coating_types': coating_types,
            'finishing_types': finishing_types,
            'packaging_types': packaging_types,
            'currencies': active_currencies,
            'functional_currency': func_currency_dict,
        }
    except Exception as e:
        logger.warning(f"فشل استرجاع lookups موديول التسعير: {e}")
        return {}


@login_required
@require_printing_pricing_enabled
def supplier_service_add(request, pk):
    """إضافة خدمة جديدة للمورد مع الربط العلائقي الكامل وضمان سلامة التسعير الصناعي"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServiceType, ServicePriceTier
    from django.db import transaction
    import json

    show_all = request.GET.get('show_all') == '1' or request.POST.get('show_all') == '1'
    allowed_codes = _get_allowed_service_type_codes(supplier, show_all=show_all)

    service_types = ServiceType.objects.filter(is_active=True).order_by('order', 'name')
    if not show_all:
        filtered_service_types = service_types.filter(code__in=allowed_codes)
    else:
        filtered_service_types = service_types

    if request.method == 'POST':
        service_type_id = request.POST.get('service_type')
        name            = request.POST.get('name', '').strip()
        base_price_raw  = request.POST.get('base_price', '0') or '0'
        setup_cost_raw  = request.POST.get('setup_cost', '0') or '0'
        min_charge_raw  = request.POST.get('minimum_charge', '0') or '0'
        price_ton_raw   = request.POST.get('price_per_ton', '0') or '0'
        sheets_pack_raw = request.POST.get('sheets_per_pack', '500') or '500'
        tooling_cost_raw = request.POST.get('tooling_cost', '0') or '0'
        click_bw_raw    = request.POST.get('price_per_click_bw', '') or ''
        click_color_raw = request.POST.get('price_per_click_color', '') or ''
        gsm_raw         = request.POST.get('gsm', '') or ''
        pricing_formula = request.POST.get('pricing_formula') or 'PER_THOUSAND'
        if pricing_formula == 'PER_UNIT':
            pricing_formula = 'PER_PIECE'
        elif pricing_formula == 'FLAT_FEE':
            pricing_formula = 'FIXED_TOOLING'
        set_price_raw   = request.POST.get('set_price') or request.POST.get('offset_set_price') or request.POST.get('ctp_set_price') or '0'
        set_inc_tir_raw = request.POST.get('set_included_tirages') or request.POST.get('offset_set_included_tirages') or '1'
        notes           = request.POST.get('notes', '')
        is_active       = request.POST.get('is_active') == 'on'

        machine_id      = request.POST.get('machine_id')
        dimension_id    = request.POST.get('dimension_id')
        paper_type_id   = request.POST.get('paper_type_id')
        coating_type_id = request.POST.get('coating_type_id')
        finishing_type_id = request.POST.get('finishing_type_id')
        packaging_type_id = request.POST.get('packaging_type_id')
        paper_size_id   = request.POST.get('paper_size_id')
        paper_origin_id = request.POST.get('paper_origin_id')
        paper_weight_id = request.POST.get('paper_weight_id')
        plate_size_id   = request.POST.get('plate_size_id')

        attributes = {}
        for key, val in request.POST.items():
            if key.startswith('attr_'):
                attributes[key[5:]] = val

        errors = {}
        if not service_type_id:
            errors['service_type'] = 'نوع الخدمة مطلوب'
        else:
            st_check = service_types.filter(pk=service_type_id).first()
            if st_check and not show_all and st_check.code not in allowed_codes:
                errors['service_type'] = f'نوع الخدمة "{st_check.name}" غير معتمد لهذا المورد'

        bp, err_bp = _clean_decimal_input(base_price_raw, '0.00', 'السعر الأساسي')
        if err_bp:
            errors['base_price'] = err_bp
        sc, err_sc = _clean_decimal_input(setup_cost_raw, '0.00', 'تكلفة الإعداد / فتحة الماكينة')
        if err_sc:
            errors['setup_cost'] = err_sc
        mc, err_mc = _clean_decimal_input(min_charge_raw, '0.00', 'الحد الأدنى للتشغيل')
        if err_mc:
            errors['minimum_charge'] = err_mc
        pt, err_pt = _clean_decimal_input(price_ton_raw, '0.00', 'سعر الطن')
        if err_pt:
            errors['price_per_ton'] = err_pt
        tc, err_tc = _clean_decimal_input(tooling_cost_raw, '0.00', 'تكلفة الفورمة / الكليشيه')
        if err_tc:
            errors['tooling_cost'] = err_tc

        sp_val = None
        if set_price_raw and str(set_price_raw).strip() not in ('', '0', '0.00'):
            sp_val, err_sp = _clean_decimal_input(set_price_raw, '0.00', 'سعر الطقم')
            if err_sp:
                errors['set_price'] = err_sp

        try:
            set_inc_tir_val = int(set_inc_tir_raw) if set_inc_tir_raw else 1
            if set_inc_tir_val < 1:
                set_inc_tir_val = 1
        except (ValueError, TypeError):
            set_inc_tir_val = 1

        cbw = None
        if click_bw_raw:
            cbw, err_cbw = _clean_decimal_input(click_bw_raw, '0.00', 'سعر النقرة أبيض وأسود')
            if err_cbw:
                errors['price_per_click_bw'] = err_cbw

        ccol = None
        if click_color_raw:
            ccol, err_ccol = _clean_decimal_input(click_color_raw, '0.00', 'سعر النقرة ألوان')
            if err_ccol:
                errors['price_per_click_color'] = err_ccol

        try:
            sp = int(sheets_pack_raw) if sheets_pack_raw else 500
        except ValueError:
            sp = 500

        gsm_val = None
        if gsm_raw and str(gsm_raw).isdigit():
            gsm_val = int(gsm_raw)

        # استرجاع وربط كائنات النماذج
        machine_obj = None
        dim_obj = None
        paper_obj = None
        coating_obj = None
        finishing_obj = None
        packaging_obj = None
        paper_size_obj = None
        paper_origin_obj = None
        paper_weight_obj = None
        plate_size_obj = None

        try:
            from printing_pricing.models import (
                PrintingMachine, MachineDimension, PaperType,
                CoatingType, FinishingType, PackagingType,
                PaperSize, PaperOrigin, PaperWeight
            )
            if machine_id and str(machine_id).isdigit():
                machine_obj = PrintingMachine.objects.filter(id=int(machine_id), is_active=True).first()
            if dimension_id and str(dimension_id).isdigit():
                dim_obj = MachineDimension.objects.filter(id=int(dimension_id), is_active=True).first()
            if paper_type_id and str(paper_type_id).isdigit():
                paper_obj = PaperType.objects.filter(id=int(paper_type_id), is_active=True).first()
            if coating_type_id and str(coating_type_id).isdigit():
                coating_obj = CoatingType.objects.filter(id=int(coating_type_id), is_active=True).first()
            if finishing_type_id and str(finishing_type_id).isdigit():
                finishing_obj = FinishingType.objects.filter(id=int(finishing_type_id), is_active=True).first()
            if packaging_type_id and str(packaging_type_id).isdigit():
                packaging_obj = PackagingType.objects.filter(id=int(packaging_type_id), is_active=True).first()
            if paper_size_id and str(paper_size_id).isdigit():
                paper_size_obj = PaperSize.objects.filter(id=int(paper_size_id), is_active=True).first()
            if paper_origin_id and str(paper_origin_id).isdigit():
                paper_origin_obj = PaperOrigin.objects.filter(id=int(paper_origin_id), is_active=True).first()
            if paper_weight_id and str(paper_weight_id).isdigit():
                paper_weight_obj = PaperWeight.objects.filter(id=int(paper_weight_id), is_active=True).first()
                if not gsm_val and paper_weight_obj:
                    gsm_val = paper_weight_obj.gsm
            if plate_size_id and str(plate_size_id).isdigit():
                plate_size_obj = MachineDimension.objects.filter(id=int(plate_size_id), dimension_type='plate', is_active=True).first()

            # فحص فيزيائي لأبعاد الماكينة مقابل الشيت
            if machine_obj and dim_obj and getattr(machine_obj, 'max_sheet_size', None):
                try:
                    parts = machine_obj.max_sheet_size.lower().replace('×', 'x').split('x')
                    if len(parts) == 2:
                        max_w, max_l = float(parts[0]), float(parts[1])
                        if dim_obj.width and dim_obj.width > max_w:
                            errors['dimension'] = f'عرض المقاس ({dim_obj.width} سم) يتجاوز السعة القصوى لماكينة {machine_obj.name} ({max_w} سم)'
                        if dim_obj.height and dim_obj.height > max_l:
                            errors['dimension'] = f'طول المقاس ({dim_obj.height} سم) يتجاوز السعة القصوى لماكينة {machine_obj.name} ({max_l} سم)'
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"خطأ أثناء التحقق من lookups: {e}")

        # التوليد الذكي التلقائي للاسم إن لم يُدخل
        if not name:
            st_obj = service_types.filter(pk=service_type_id).first()
            st_code = st_obj.code if st_obj else ''
            if st_code == 'offset_printing' and machine_obj:
                colors = attributes.get('max_colors') or machine_obj.colors_capacity or 4
                size_lbl = dim_obj.name if dim_obj else ''
                name = f"{machine_obj.name} — {colors} لون — {size_lbl}".strip(' —')
            elif st_code == 'ctp_plates' and plate_size_obj:
                name = f"زنكة CTP — {plate_size_obj.name}"
            elif st_code == 'coating' and coating_obj:
                name = f"سلوفان — {coating_obj.name}"
            elif st_code == 'finishing' and finishing_obj:
                name = f"تشطيب — {finishing_obj.name}"
            elif st_code == 'packaging' and packaging_obj:
                name = f"تقفيل — {packaging_obj.name}"
            elif st_code == 'digital_printing' and machine_obj:
                name = f"ديجيتال — {machine_obj.name}"
            elif st_code == 'paper' and paper_obj:
                ps_lbl = f" — {paper_size_obj.name}" if paper_size_obj else ""
                gsm_lbl = f" {gsm_val} جم" if gsm_val else ""
                name = f"{paper_obj.name}{gsm_lbl}{ps_lbl}".strip()
            else:
                errors['name'] = 'اسم الخدمة مطلوب'

        # معالجة الشرائح السعرية المدمجة
        inline_tiers_data = []
        tiers_json = request.POST.get('inline_tiers_json')
        if tiers_json:
            try:
                raw_tiers = json.loads(tiers_json)
                if isinstance(raw_tiers, list) and raw_tiers:
                    sorted_tiers = sorted(raw_tiers, key=lambda x: int(x.get('min_quantity', 0)))
                    for i, t in enumerate(sorted_tiers):
                        t_min = int(t.get('min_quantity', 0))
                        t_max = int(t.get('max_quantity')) if t.get('max_quantity') else None
                        t_price, err_tp = _clean_decimal_input(t.get('price_per_unit'), '0.00', 'سعر الشريحة')
                        if err_tp:
                            errors['tiers'] = err_tp
                            break
                        if t_max and t_max < t_min:
                            errors['tiers'] = f'الشريحة {t_min}-{t_max}: الحد الأقصى يجب أن يكون أكبر من الحد الأدنى'
                            break
                        if i > 0:
                            prev_t = sorted_tiers[i-1]
                            prev_max = int(prev_t.get('max_quantity')) if prev_t.get('max_quantity') else None
                            if prev_max is None or prev_max >= t_min:
                                errors['tiers'] = f'تداخل في الشرائح: الشريحة من {t_min} تتقاطع مع الشريحة السابقة!'
                                break
                        inline_tiers_data.append({'min_quantity': t_min, 'max_quantity': t_max, 'price_per_unit': t_price})
            except Exception as e:
                errors['tiers'] = f'خطأ في معالجة الشرائح السعرية: {e}'

        if not errors:
            try:
                service_type = ServiceType.objects.get(pk=service_type_id, is_active=True)
                with transaction.atomic():
                    svc = SupplierService(
                        supplier=supplier,
                        service_type=service_type,
                        name=name,
                        base_price=bp,
                        setup_cost=sc,
                        minimum_charge=mc,
                        set_price=sp_val,
                        set_included_tirages=set_inc_tir_val if sp_val else 1,
                        pricing_formula=pricing_formula,
                        price_per_ton=pt if pricing_formula == 'PER_TON' else None,
                        sheets_per_pack=sp if pricing_formula == 'PER_REAM' else None,
                        machine=machine_obj,
                        dimension=dim_obj,
                        paper_type_ref=paper_obj,
                        coating_type=coating_obj,
                        finishing_type=finishing_obj,
                        packaging_type=packaging_obj,
                        paper_size=paper_size_obj,
                        paper_origin=paper_origin_obj,
                        paper_weight=paper_weight_obj,
                        plate_size=plate_size_obj,
                        gsm=gsm_val,
                        tooling_cost=tc,
                        price_per_click_bw=cbw,
                        price_per_click_color=ccol,
                        attributes=attributes,
                        notes=notes,
                        is_active=is_active,
                    )
                    svc.full_clean()
                    svc.save()

                    for t in inline_tiers_data:
                        ServicePriceTier.objects.create(
                            service=svc,
                            min_quantity=t['min_quantity'],
                            max_quantity=t['max_quantity'],
                            price_per_unit=t['price_per_unit'],
                            is_active=True
                        )

                messages.success(request, f'تم إضافة الخدمة "{name}" بنجاح')
                return redirect(reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane')
            except ServiceType.DoesNotExist:
                errors['service_type'] = 'نوع الخدمة غير موجود'
            except ValidationError as ve:
                for k, v in ve.message_dict.items():
                    errors[k] = ', '.join(v)
            except Exception as e:
                errors['__all__'] = str(e)

        for field, msg in errors.items():
            messages.error(request, msg)

    # تجميع حسب الفئة لعرض optgroups
    from collections import defaultdict
    category_labels = dict(ServiceType.CATEGORY_CHOICES)
    _grouped = defaultdict(list)
    for st in filtered_service_types:
        _grouped[st.category].append(st)
    service_types_grouped = [
        {'category': cat, 'label': category_labels.get(cat, cat), 'types': types}
        for cat, types in _grouped.items()
    ]

    # ترشيح الخدمة الافتراضية
    default_service_type = request.POST.get('service_type', '')
    if not default_service_type and allowed_codes and request.method == 'GET':
        matching_st = filtered_service_types.filter(code__in=allowed_codes).first()
        if matching_st:
            default_service_type = str(matching_st.pk)

    form_data = {
        'name':                  request.POST.get('name', '') if request.method == 'POST' else '',
        'base_price':            request.POST.get('base_price', '0') if request.method == 'POST' else '0',
        'setup_cost':            request.POST.get('setup_cost', '0') if request.method == 'POST' else '0',
        'minimum_charge':        request.POST.get('minimum_charge', '0') if request.method == 'POST' else '0',
        'price_per_ton':         request.POST.get('price_per_ton', '0') if request.method == 'POST' else '0',
        'sheets_per_pack':       request.POST.get('sheets_per_pack', '500') if request.method == 'POST' else '500',
        'tooling_cost':          request.POST.get('tooling_cost', '0') if request.method == 'POST' else '0',
        'price_per_click_bw':    request.POST.get('price_per_click_bw', '') if request.method == 'POST' else '',
        'price_per_click_color': request.POST.get('price_per_click_color', '') if request.method == 'POST' else '',
        'gsm':                   request.POST.get('gsm', '') if request.method == 'POST' else '',
        'max_colors':            request.POST.get('attr_max_colors', '4') if request.method == 'POST' else '4',
        'sheet_size':            request.POST.get('attr_sheet_size', '') if request.method == 'POST' else '',
        'machine_type':          request.POST.get('attr_machine_type', '') if request.method == 'POST' else '',
        'pricing_formula':       request.POST.get('pricing_formula', 'PER_THOUSAND') if request.method == 'POST' else 'PER_THOUSAND',
        'notes':                 request.POST.get('notes', '') if request.method == 'POST' else '',
        'is_active':             True,
        'service_type':          default_service_type,
        'attributes':            attributes if request.method == 'POST' else {},
        'machine_id':            request.POST.get('machine_id', '') if request.method == 'POST' else '',
        'dimension_id':          request.POST.get('dimension_id', '') if request.method == 'POST' else '',
        'paper_type_id':         request.POST.get('paper_type_id', '') if request.method == 'POST' else '',
        'coating_type_id':       request.POST.get('coating_type_id', '') if request.method == 'POST' else '',
        'finishing_type_id':     request.POST.get('finishing_type_id', '') if request.method == 'POST' else '',
        'packaging_type_id':     request.POST.get('packaging_type_id', '') if request.method == 'POST' else '',
        'paper_size_id':         request.POST.get('paper_size_id', '') if request.method == 'POST' else '',
        'paper_origin_id':       request.POST.get('paper_origin_id', '') if request.method == 'POST' else '',
        'paper_weight_id':       request.POST.get('paper_weight_id', '') if request.method == 'POST' else '',
        'plate_size_id':         request.POST.get('plate_size_id', '') if request.method == 'POST' else '',
        'currency_id':           request.POST.get('currency_id', '') if request.method == 'POST' else '',
        'set_price':             request.POST.get('set_price') or request.POST.get('offset_set_price') or request.POST.get('ctp_set_price') or '0' if request.method == 'POST' else '0',
        'set_included_tirages':  request.POST.get('set_included_tirages') or request.POST.get('offset_set_included_tirages') or '1' if request.method == 'POST' else '1',
        'inline_tiers_json':     request.POST.get('inline_tiers_json', '[]') if request.method == 'POST' else '[]',
    }

    lookups_dict = _get_preinjected_lookups()
    func_info = lookups_dict.get('functional_currency', {})
    fallback_sym = func_info.get('symbol', 'ج.م')
    service_curr_sym = supplier.default_currency.symbol if (supplier.default_currency and supplier.default_currency.symbol) else fallback_sym

    context = {
        'supplier':               supplier,
        'service_types':          filtered_service_types,
        'service_types_grouped':  service_types_grouped,
        'service_types_schemas':  json.dumps({str(st.pk): st.attribute_schema for st in service_types}, ensure_ascii=False),
        'form_data':              form_data,
        'lookups':                lookups_dict,
        'currencies':             Currency.objects.filter(is_active=True).order_by('-is_functional', 'code'),
        'show_all':               show_all,
        'allowed_codes':          allowed_codes,
        'currency_symbol':        service_curr_sym,
        'page_title':             f'إضافة خدمة — {supplier.name}',
        'page_icon':              'fas fa-plus-circle',
        'header_buttons': [
            {'url': reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane', 'icon': 'fa-arrow-right', 'text': 'العودة لبروفايل المورد', 'class': 'btn-secondary'},
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
@require_printing_pricing_enabled
def supplier_service_edit(request, pk, service_pk):
    """تعديل خدمة مورد مع تحديث الحقول الصناعية والربط العلائقي الكامل وشرائح الكميات"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServiceType, ServicePriceTier
    from django.db import transaction
    import json
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)

    show_all = request.GET.get('show_all') == '1' or request.POST.get('show_all') == '1'
    allowed_codes = _get_allowed_service_type_codes(supplier, show_all=show_all)
    if service.service_type and service.service_type.code not in allowed_codes:
        allowed_codes.append(service.service_type.code)

    service_types = ServiceType.objects.filter(is_active=True).order_by('order', 'name')
    if not show_all:
        filtered_service_types = service_types.filter(code__in=allowed_codes)
    else:
        filtered_service_types = service_types

    from collections import defaultdict
    category_labels = dict(ServiceType.CATEGORY_CHOICES)
    _grouped = defaultdict(list)
    for st in filtered_service_types:
        _grouped[st.category].append(st)
    service_types_grouped = [
        {'category': cat, 'label': category_labels.get(cat, cat) if cat else 'خدمات عامة', 'types': types}
        for cat, types in _grouped.items()
    ]

    if request.method == 'POST':
        name            = request.POST.get('name', '').strip()
        base_price_raw  = request.POST.get('base_price', '0') or '0'
        setup_cost_raw  = request.POST.get('setup_cost', '0') or '0'
        min_charge_raw  = request.POST.get('minimum_charge', '0') or '0'
        price_ton_raw   = request.POST.get('price_per_ton', '0') or '0'
        sheets_pack_raw = request.POST.get('sheets_per_pack', '500') or '500'
        tooling_cost_raw = request.POST.get('tooling_cost', '0') or '0'
        click_bw_raw    = request.POST.get('price_per_click_bw', '') or ''
        click_color_raw = request.POST.get('price_per_click_color', '') or ''
        gsm_raw         = request.POST.get('gsm', '') or ''
        pricing_formula = request.POST.get('pricing_formula') or service.pricing_formula or 'PER_THOUSAND'
        if pricing_formula == 'PER_UNIT':
            pricing_formula = 'PER_PIECE'
        elif pricing_formula == 'FLAT_FEE':
            pricing_formula = 'FIXED_TOOLING'
        set_price_raw   = request.POST.get('set_price') or request.POST.get('offset_set_price') or request.POST.get('ctp_set_price') or '0'
        set_inc_tir_raw = request.POST.get('set_included_tirages') or request.POST.get('offset_set_included_tirages') or '1'
        notes           = request.POST.get('notes', '')
        is_active       = request.POST.get('is_active') == 'on'

        machine_id      = request.POST.get('machine_id')
        dimension_id    = request.POST.get('dimension_id')
        paper_type_id   = request.POST.get('paper_type_id')
        coating_type_id = request.POST.get('coating_type_id')
        finishing_type_id = request.POST.get('finishing_type_id')
        packaging_type_id = request.POST.get('packaging_type_id')
        paper_size_id   = request.POST.get('paper_size_id')
        paper_origin_id = request.POST.get('paper_origin_id')
        paper_weight_id = request.POST.get('paper_weight_id')
        plate_size_id   = request.POST.get('plate_size_id')
        currency_id     = request.POST.get('currency_id')

        from financial.models import Currency
        currency_obj = Currency.objects.filter(id=currency_id, is_active=True).first() if currency_id else None

        attributes = {}
        for key, val in request.POST.items():
            if key.startswith('attr_'):
                attributes[key[5:]] = val

        errors = {}
        if not name:
            errors['name'] = 'اسم الخدمة مطلوب'

        bp, err_bp = _clean_decimal_input(base_price_raw, '0.00', 'السعر الأساسي')
        if err_bp:
            errors['base_price'] = err_bp
        sc, err_sc = _clean_decimal_input(setup_cost_raw, '0.00', 'تكلفة الإعداد / فتحة الماكينة')
        if err_sc:
            errors['setup_cost'] = err_sc
        mc, err_mc = _clean_decimal_input(min_charge_raw, '0.00', 'الحد الأدنى للتشغيل')
        if err_mc:
            errors['minimum_charge'] = err_mc
        pt, err_pt = _clean_decimal_input(price_ton_raw, '0.00', 'سعر الطن')
        if err_pt:
            errors['price_per_ton'] = err_pt
        tc, err_tc = _clean_decimal_input(tooling_cost_raw, '0.00', 'تكلفة الفورمة / الكليشيه')
        if err_tc:
            errors['tooling_cost'] = err_tc

        sp_val = None
        if set_price_raw and str(set_price_raw).strip() not in ('', '0', '0.00'):
            sp_val, err_sp = _clean_decimal_input(set_price_raw, '0.00', 'سعر الطقم')
            if err_sp:
                errors['set_price'] = err_sp

        try:
            set_inc_tir_val = int(set_inc_tir_raw) if set_inc_tir_raw else 1
            if set_inc_tir_val < 1:
                set_inc_tir_val = 1
        except (ValueError, TypeError):
            set_inc_tir_val = 1

        cbw = None
        if click_bw_raw:
            cbw, err_cbw = _clean_decimal_input(click_bw_raw, '0.00', 'سعر النقرة أبيض وأسود')
            if err_cbw:
                errors['price_per_click_bw'] = err_cbw

        ccol = None
        if click_color_raw:
            ccol, err_ccol = _clean_decimal_input(click_color_raw, '0.00', 'سعر النقرة ألوان')
            if err_ccol:
                errors['price_per_click_color'] = err_ccol

        try:
            sp = int(sheets_pack_raw) if sheets_pack_raw else 500
        except ValueError:
            sp = 500

        gsm_val = None
        if gsm_raw and str(gsm_raw).isdigit():
            gsm_val = int(gsm_raw)

        machine_obj = service.machine
        if machine_id:
            from printing_pricing.models import PrintingMachine
            machine_obj = PrintingMachine.objects.filter(id=machine_id, is_active=True).first()

        dim_obj = service.dimension
        if dimension_id:
            from printing_pricing.models import MachineDimension
            dim_obj = MachineDimension.objects.filter(id=dimension_id, is_active=True).first()

        plate_size_obj = service.plate_size
        if plate_size_id:
            from printing_pricing.models import MachineDimension
            plate_size_obj = MachineDimension.objects.filter(id=plate_size_id, dimension_type='plate', is_active=True).first()

        paper_obj = service.paper_type_ref
        if paper_type_id:
            from printing_pricing.models import PaperType
            paper_obj = PaperType.objects.filter(id=paper_type_id, is_active=True).first()

        coating_obj = service.coating_type
        if coating_type_id:
            from printing_pricing.models import CoatingType
            coating_obj = CoatingType.objects.filter(id=coating_type_id, is_active=True).first()

        finishing_obj = service.finishing_type
        if finishing_type_id:
            from printing_pricing.models import FinishingType
            finishing_obj = FinishingType.objects.filter(id=finishing_type_id, is_active=True).first()

        packaging_obj = service.packaging_type
        if packaging_type_id:
            from printing_pricing.models import PackagingType
            packaging_obj = PackagingType.objects.filter(id=packaging_type_id, is_active=True).first()

        paper_size_obj = service.paper_size
        if paper_size_id:
            from printing_pricing.models import PaperSize
            paper_size_obj = PaperSize.objects.filter(id=paper_size_id, is_active=True).first()

        paper_origin_obj = service.paper_origin
        if paper_origin_id:
            from printing_pricing.models import PaperOrigin
            paper_origin_obj = PaperOrigin.objects.filter(id=paper_origin_id, is_active=True).first()

        paper_weight_obj = service.paper_weight
        if paper_weight_id:
            from printing_pricing.models import PaperWeight
            paper_weight_obj = PaperWeight.objects.filter(id=paper_weight_id, is_active=True).first()

        inline_tiers_data = []
        tiers_parse_success = False
        tiers_json = request.POST.get('inline_tiers_json')
        if tiers_json is not None:
            try:
                parsed_tiers = json.loads(tiers_json)
                if isinstance(parsed_tiers, list):
                    for t in parsed_tiers:
                        min_q = int(t.get('min_quantity', 1))
                        max_q = int(t.get('max_quantity')) if t.get('max_quantity') else None
                        p_unit = Decimal(str(t.get('price_per_unit', '0')))
                        if p_unit > 0:
                            inline_tiers_data.append({
                                'min_quantity': min_q,
                                'max_quantity': max_q,
                                'price_per_unit': p_unit
                            })
                    tiers_parse_success = True
            except Exception as e:
                logger.warning(f"فشل معالجة الشرائح السعرية المضمنة: {e}")

        if not errors:
            try:
                with transaction.atomic():
                    service.name                  = name
                    service.base_price            = bp
                    service.setup_cost            = sc
                    service.minimum_charge        = mc
                    service.set_price             = sp_val
                    service.set_included_tirages  = set_inc_tir_val if sp_val else 1
                    service.pricing_formula       = pricing_formula
                    service.price_per_ton         = pt if pricing_formula == 'PER_TON' else None
                    service.sheets_per_pack       = sp if pricing_formula == 'PER_REAM' else None
                    service.machine               = machine_obj
                    service.dimension             = dim_obj
                    service.paper_type_ref        = paper_obj
                    service.coating_type          = coating_obj
                    service.finishing_type        = finishing_obj
                    service.packaging_type        = packaging_obj
                    service.paper_size            = paper_size_obj
                    service.paper_origin          = paper_origin_obj
                    service.paper_weight          = paper_weight_obj
                    service.plate_size            = plate_size_obj
                    service.currency              = currency_obj
                    service.gsm                   = gsm_val
                    service.tooling_cost          = tc
                    service.price_per_click_bw    = cbw
                    service.price_per_click_color = ccol
                    service.attributes            = attributes
                    service.notes                 = notes
                    service.is_active             = is_active
                    service.full_clean()
                    service.save()

                    # تحديث الشرائح السعرية بأمان
                    if tiers_parse_success:
                        service.price_tiers.all().delete()
                        for t in inline_tiers_data:
                            ServicePriceTier.objects.create(
                                service=service,
                                min_quantity=t['min_quantity'],
                                max_quantity=t['max_quantity'],
                                price_per_unit=t['price_per_unit'],
                                is_active=True
                            )

                messages.success(request, f'تم تحديث الخدمة "{name}" بنجاح')
                return redirect(reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane')
            except ValidationError as ve:
                for k, v in ve.message_dict.items():
                    errors[k] = ', '.join(v)
            except Exception as e:
                errors['__all__'] = str(e)

        for field, msg in errors.items():
            messages.error(request, msg)

    # استرجاع الشرائح القائمة
    existing_tiers = list(service.price_tiers.filter(is_active=True).order_by('min_quantity').values('min_quantity', 'max_quantity', 'price_per_unit'))
    for t in existing_tiers:
        t['price_per_unit'] = str(t['price_per_unit'])

    from financial.models import Currency
    form_data = {
        'name':                  service.name,
        'base_price':            service.base_price,
        'setup_cost':            service.setup_cost,
        'minimum_charge':        service.minimum_charge,
        'price_per_ton':         service.price_per_ton or '0',
        'sheets_per_pack':       service.sheets_per_pack or 500,
        'tooling_cost':          service.tooling_cost or '0',
        'price_per_click_bw':    service.price_per_click_bw or '',
        'price_per_click_color': service.price_per_click_color or '',
        'gsm':                   service.gsm or (service.paper_weight.gsm if service.paper_weight else (service.attributes or {}).get('gsm', '')),
        'max_colors':            (service.attributes or {}).get('max_colors', (service.machine.colors_capacity if service.machine else '4')),
        'sheet_size':            (service.attributes or {}).get('sheet_size', (service.dimension.name if service.dimension else '')),
        'machine_type':          (service.attributes or {}).get('machine_type', (service.machine.name if service.machine else '')),
        'pricing_formula':       service.pricing_formula,
        'notes':                 service.notes,
        'is_active':             service.is_active,
        'service_type':          str(service.service_type.pk),
        'attributes':            service.attributes or {},
        'machine_id':            service.machine.id if service.machine else '',
        'dimension_id':          service.dimension.id if service.dimension else '',
        'paper_type_id':         service.paper_type_ref.id if service.paper_type_ref else '',
        'coating_type_id':       service.coating_type.id if service.coating_type else '',
        'finishing_type_id':     service.finishing_type.id if service.finishing_type else '',
        'packaging_type_id':     service.packaging_type.id if service.packaging_type else '',
        'paper_size_id':         service.paper_size.id if service.paper_size else '',
        'paper_origin_id':       service.paper_origin.id if service.paper_origin else '',
        'paper_weight_id':       service.paper_weight.id if service.paper_weight else '',
        'plate_size_id':         service.plate_size.id if service.plate_size else '',
        'currency_id':           service.currency.id if service.currency else '',
        'set_price':             (request.POST.get('set_price') or request.POST.get('offset_set_price') or request.POST.get('ctp_set_price')) if request.method == 'POST' else (str(service.set_price) if service.set_price else '0'),
        'set_included_tirages':  (request.POST.get('set_included_tirages') or request.POST.get('offset_set_included_tirages')) if request.method == 'POST' else (service.set_included_tirages or 1),
        'inline_tiers_json':     json.dumps(existing_tiers),
    }
    context = {
        'supplier':               supplier,
        'service':                service,
        'service_types':          filtered_service_types,
        'service_types_grouped':  service_types_grouped,
        'service_types_schemas':  json.dumps({str(st.pk): st.attribute_schema for st in service_types}, ensure_ascii=False),
        'form_data':              form_data,
        'lookups':                _get_preinjected_lookups(),
        'currencies':             Currency.objects.filter(is_active=True).order_by('-is_functional', 'code'),
        'currency_symbol':        service.currency_symbol,
        'allowed_codes':          allowed_codes,
        'show_all':               show_all,
        'page_title':             f'تعديل خدمة — {supplier.name}',
        'page_icon':              'fas fa-edit',
        'header_buttons': [
            {'url': reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane', 'icon': 'fa-arrow-right', 'text': 'العودة لبروفايل المورد', 'class': 'btn-secondary'},
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
@require_printing_pricing_enabled
def supplier_service_delete(request, pk, service_pk):
    """حذف خدمة مورد (POST فقط) مع حماية السجلات التاريخية"""
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService
    service = get_object_or_404(SupplierService, pk=service_pk, supplier=supplier)

    if request.method == 'POST':
        name = service.name
        has_orders = False
        try:
            from printing_pricing.models import OrderService
            has_orders = OrderService.objects.filter(supplier_service=service).exists()
        except Exception:
            pass

        if has_orders:
            service.is_active = False
            service.save(update_fields=['is_active'])
            msg = f'تم إيقاف تفعيل الخدمة "{name}" بدلاً من حذفها لاقترانها بأوامر تشغيل سابقة.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': msg, 'soft_deleted': True})
            messages.warning(request, msg)
        else:
            service.delete()
            msg = f'تم حذف الخدمة "{name}" بنجاح'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': msg, 'soft_deleted': False})
            messages.success(request, msg)

    return redirect(reverse('supplier:supplier_detail', kwargs={'pk': pk}) + '#services-tab-pane')


@login_required
@require_printing_pricing_enabled
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
@require_printing_pricing_enabled
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
            'id':              s.id,
            'name':            s.name,
            'service_type':    s.service_type.code,
            'base_price':      float(s.base_price),
            'setup_cost':      float(s.setup_cost),
            'minimum_charge':  float(s.minimum_charge) if s.minimum_charge else 0.0,
            'pricing_formula': s.pricing_formula,
            'price_per_ton':   float(s.price_per_ton) if s.price_per_ton else 0.0,
            'sheets_per_pack': s.sheets_per_pack,
            'attributes':      s.attributes,
            'currency_code':   s.effective_currency.code if s.effective_currency else 'EGP',
            'currency_symbol': s.currency_symbol,
        }
        for s in qs.order_by('service_type__order', 'name')
    ]
    return JsonResponse({'success': True, 'services': data, 'total_count': len(data)})


# ================================================================
# المرحلة 5 — الشرائح السعرية (ServicePriceTier)
# ================================================================

@login_required
@require_printing_pricing_enabled
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
        'currency_symbol': service.currency_symbol,
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
@require_printing_pricing_enabled
def price_tier_add(request, pk, service_pk):
    """إضافة شريحة سعرية جديدة مع التحقق من عدم التداخل"""
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

        # التحقق من عدم تداخل الشرائح السعرية
        if not errors:
            new_min = int(min_q)
            new_max = int(max_q) if max_q else None
            existing_tiers = service.price_tiers.filter(is_active=True)
            for ext in existing_tiers:
                ext_min = ext.min_quantity
                ext_max = ext.max_quantity
                overlap = (new_max is None or new_max >= ext_min) and (ext_max is None or ext_max >= new_min)
                if overlap:
                    ext_range = f"{ext_min} - {ext_max or 'ما لا نهاية'}"
                    errors['overlap'] = f'تداخل في الشرائح: الشريحة المدخلة تتقاطع مع الشريحة الحالية ({ext_range})'
                    break

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
        'currency_symbol': service.currency_symbol,
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
@require_printing_pricing_enabled
def price_tier_edit(request, pk, service_pk, tier_pk):
    """تعديل شريحة سعرية مع التحقق من عدم التداخل"""
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

        # التحقق من عدم تداخل الشرائح السعرية
        if not errors:
            new_min = int(min_q)
            new_max = int(max_q) if max_q else None
            existing_tiers = service.price_tiers.filter(is_active=True).exclude(pk=tier.pk)
            for ext in existing_tiers:
                ext_min = ext.min_quantity
                ext_max = ext.max_quantity
                overlap = (new_max is None or new_max >= ext_min) and (ext_max is None or ext_max >= new_min)
                if overlap:
                    ext_range = f"{ext_min} - {ext_max or 'ما لا نهاية'}"
                    errors['overlap'] = f'تداخل في الشرائح: الشريحة المدخلة تتقاطع مع الشريحة الحالية ({ext_range})'
                    break

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
        'currency_symbol': service.currency_symbol,
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
@require_printing_pricing_enabled
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
@require_printing_pricing_enabled
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
@require_printing_pricing_enabled
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
        import printing_pricing.models as sm
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
@require_printing_pricing_enabled
def service_type_schema_options_api(request):
    """
    API — جلب خيارات حقل source معين من printing_pricing.
    GET /suppliers/api/schema-options/?source=PaperType
    """
    source = request.GET.get('source', '').strip()
    if not source:
        return JsonResponse({'success': False, 'options': []})

    try:
        import printing_pricing.models as sm
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


@login_required
@require_printing_pricing_enabled
def supplier_services_bulk_update(request, pk):
    """
    تحديث أو إضافة مصفوفة من الخدمات لمورد دفعة واحدة (Bulk Price Matrix)
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService, ServiceType
    from decimal import Decimal, InvalidOperation
    import json

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            services_data = data.get('services', [])
        else:
            services_raw = request.POST.get('services_json', '[]')
            services_data = json.loads(services_raw)

        if not services_data or not isinstance(services_data, list):
            return JsonResponse({'success': False, 'error': 'بيانات الخدمات غير صالحة أو فارغة'}, status=400)

        created_count = 0
        updated_count = 0
        has_explicit = supplier.provided_services.exists()
        allowed_codes = set(supplier.provided_services.values_list('code', flat=True)) if has_explicit else None

        with transaction.atomic():
            for item in services_data:
                svc_id = item.get('id')
                service_type_id = item.get('service_type_id')
                name = item.get('name', '').strip()
                if not name:
                    continue

                try:
                    bp = Decimal(str(item.get('base_price', '0') or '0'))
                    sc = Decimal(str(item.get('setup_cost', '0') or '0'))
                    mc = Decimal(str(item.get('minimum_charge', '0') or '0'))
                    ppt = Decimal(str(item.get('price_per_ton', '0') or '0')) if item.get('price_per_ton') else None
                except (InvalidOperation, ValueError):
                    bp, sc, mc, ppt = Decimal('0'), Decimal('0'), Decimal('0'), None

                formula = item.get('pricing_formula', 'PER_PIECE')
                if formula == 'PER_UNIT':
                    formula = 'PER_PIECE'
                elif formula == 'FLAT_FEE':
                    formula = 'FIXED_TOOLING'
                sheets_pack = int(item.get('sheets_per_pack', 500) or 500)
                attrs = item.get('attributes', {})
                if not isinstance(attrs, dict):
                    attrs = {}

                set_p_raw = item.get('set_price')
                set_p = None
                if set_p_raw not in (None, '', 'null'):
                    try:
                        set_p = Decimal(str(set_p_raw))
                    except (InvalidOperation, ValueError):
                        set_p = None

                set_inc_tir_raw = item.get('set_included_tirages')
                set_inc_tir = 1
                if set_inc_tir_raw not in (None, '', 'null'):
                    try:
                        set_inc_tir = max(1, int(set_inc_tir_raw))
                    except (ValueError, TypeError):
                        set_inc_tir = 1

                if svc_id:
                    # Update existing
                    svc = SupplierService.objects.filter(pk=svc_id, supplier=supplier).first()
                    if svc:
                        svc.name = name
                        svc.base_price = bp
                        svc.setup_cost = sc
                        svc.minimum_charge = mc
                        svc.pricing_formula = formula
                        svc.sheets_per_pack = sheets_pack
                        if ppt:
                            svc.price_per_ton = ppt
                        if set_p is not None:
                            svc.set_price = set_p
                            svc.set_included_tirages = set_inc_tir
                        if attrs:
                            svc.attributes.update(attrs)
                        svc.save()
                        updated_count += 1
                else:
                    # Create new
                    if not service_type_id:
                        continue
                    st = ServiceType.objects.filter(pk=service_type_id, is_active=True).first()
                    if not st:
                        continue
                    if allowed_codes is not None and st.code not in allowed_codes:
                        continue

                    SupplierService.objects.create(
                        supplier=supplier,
                        service_type=st,
                        name=name,
                        pricing_formula=formula,
                        base_price=bp,
                        setup_cost=sc,
                        minimum_charge=mc,
                        set_price=set_p,
                        set_included_tirages=set_inc_tir if set_p else 1,
                        sheets_per_pack=sheets_pack,
                        price_per_ton=ppt,
                        attributes=attrs,
                        is_active=True
                    )
                    created_count += 1

        messages.success(request, f'تم حفظ قائمة الأسعار بنجاح (إضافة: {created_count}، تحديث: {updated_count})')
        return JsonResponse({
            'success': True,
            'message': f'تم الحفظ بنجاح ({created_count} جديد، {updated_count} محدث)',
            'created_count': created_count,
            'updated_count': updated_count
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_printing_pricing_enabled
def supplier_services_bulk_adjust(request, pk):
    """
    تعديل نسبي مجمع لأسعار خدمات المورد لمواجهة التضخم أو تقلبات السوق (+/- X%)
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    from supplier.models import SupplierService
    from decimal import Decimal, InvalidOperation

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)

    try:
        percentage_str = request.POST.get('percentage', '0')
        service_type_id = request.POST.get('service_type_id')
        apply_to_setup = request.POST.get('apply_to_setup') in ['on', 'true', True]

        try:
            pct = Decimal(percentage_str)
        except InvalidOperation:
            return JsonResponse({'success': False, 'error': 'نسبة التعديل غير صحيحة'}, status=400)

        if pct == Decimal('0'):
            return JsonResponse({'success': False, 'error': 'يجب تحديد نسبة تعديل أكبر أو أقل من صفر'}, status=400)

        multiplier = Decimal('1') + (pct / Decimal('100'))

        services_qs = SupplierService.objects.filter(supplier=supplier, is_active=True)
        if service_type_id:
            services_qs = services_qs.filter(service_type_id=service_type_id)

        count = 0
        with transaction.atomic():
            for svc in services_qs:
                svc.base_price = (svc.base_price * multiplier).quantize(Decimal('0.01'))
                if apply_to_setup and svc.setup_cost > Decimal('0'):
                    svc.setup_cost = (svc.setup_cost * multiplier).quantize(Decimal('0.01'))
                if svc.minimum_charge > Decimal('0'):
                    svc.minimum_charge = (svc.minimum_charge * multiplier).quantize(Decimal('0.01'))
                if svc.price_per_ton and svc.price_per_ton > Decimal('0'):
                    svc.price_per_ton = (svc.price_per_ton * multiplier).quantize(Decimal('0.01'))
                if svc.set_price and svc.set_price > Decimal('0'):
                    svc.set_price = (svc.set_price * multiplier).quantize(Decimal('0.01'))
                svc.save()
                for tier in svc.price_tiers.all():
                    tier.price_per_unit = (tier.price_per_unit * multiplier).quantize(Decimal('0.01'))
                    tier.save(update_fields=['price_per_unit'])
                count += 1

        pct_sign = f"+{pct}%" if pct > 0 else f"{pct}%"
        msg = f"تم تعديل أسعار {count} خدمة للمورد بنسبة {pct_sign} بنجاح."
        messages.success(request, msg)
        return JsonResponse({'success': True, 'message': msg, 'adjusted_count': count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_printing_pricing_enabled
def supplier_seed_standard_presses(request, pk):
    """
    تهيئة فورية للماكينات القياسية (Heidelberg SM 74 و CD 102) للمطابع ومقاولي الباطن
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)

    allowed_codes = supplier.get_allowed_service_codes()
    if 'offset_printing' not in allowed_codes:
        return JsonResponse({
            'success': False,
            'error': 'هذا المورد غير معتمد لخدمات طباعة الأوفست، لا يمكن تهيئة ماكينات قياسية له.'
        }, status=403)

    from supplier.models import SupplierService, ServiceType
    from printing_pricing.models import PrintingMachine, MachineDimension
    from decimal import Decimal
    from django.db import transaction

    try:
        offset_st = ServiceType.objects.filter(code='offset_printing', is_active=True).first()
        if not offset_st:
            return JsonResponse({'success': False, 'error': 'نوع خدمة الطباعة الأوفست غير معرف بالنظام'}, status=400)

        p_50x70_price = request.POST.get('press_50x70_price', '45.00') or '45.00'
        p_50x70_setup = request.POST.get('press_50x70_setup', '0.00') or '0.00'
        p_70x100_price = request.POST.get('press_70x100_price', '75.00') or '75.00'
        p_70x100_setup = request.POST.get('press_70x100_setup', '0.00') or '0.00'

        dec_50x70_p, _ = _clean_decimal_input(p_50x70_price, '45.00')
        dec_50x70_s, _ = _clean_decimal_input(p_50x70_setup, '0.00')
        dec_70x100_p, _ = _clean_decimal_input(p_70x100_price, '75.00')
        dec_70x100_s, _ = _clean_decimal_input(p_70x100_setup, '0.00')

        # Relational lookups
        sm74 = PrintingMachine.objects.filter(name__icontains='SM 74', is_active=True).first()
        if not sm74:
            sm74 = PrintingMachine.objects.filter(machine_category='offset', is_active=True).first()

        cd102 = PrintingMachine.objects.filter(name__icontains='CD 102', is_active=True).first()
        if not cd102:
            cd102 = PrintingMachine.objects.filter(machine_category='offset', is_active=True).last()

        dim_50x70 = MachineDimension.objects.filter(code='50x70', is_active=True).first()
        dim_70x100 = MachineDimension.objects.filter(code='70x100', is_active=True).first()

        created_count = 0
        with transaction.atomic():
            # 1. SM 74 (50x70)
            svc_50x70, c1 = SupplierService.objects.get_or_create(
                supplier=supplier,
                service_type=offset_st,
                name="Heidelberg Speedmaster SM 74 — 4 لون — 50×70 سم",
                defaults={
                    'base_price': dec_50x70_p,
                    'setup_cost': dec_50x70_s,
                    'minimum_charge': Decimal('150.00'),
                    'pricing_formula': 'PER_THOUSAND',
                    'machine': sm74,
                    'dimension': dim_50x70,
                    'attributes': {'sheet_size': '50x70', 'machine_type': 'هايدلبرج SM 74', 'max_colors': 4},
                    'is_active': True,
                }
            )
            if c1:
                created_count += 1
            else:
                svc_50x70.base_price = dec_50x70_p
                svc_50x70.setup_cost = dec_50x70_s
                svc_50x70.machine = sm74
                svc_50x70.dimension = dim_50x70
                svc_50x70.save()

            # 2. CD 102 (70x100)
            svc_70x100, c2 = SupplierService.objects.get_or_create(
                supplier=supplier,
                service_type=offset_st,
                name="Heidelberg Speedmaster CD 102 — 4 لون — 70×100 سم",
                defaults={
                    'base_price': dec_70x100_p,
                    'setup_cost': dec_70x100_s,
                    'minimum_charge': Decimal('250.00'),
                    'pricing_formula': 'PER_THOUSAND',
                    'machine': cd102,
                    'dimension': dim_70x100,
                    'attributes': {'sheet_size': '70x100', 'machine_type': 'هايدلبرج CD 102', 'max_colors': 4},
                    'is_active': True,
                }
            )
            if c2:
                created_count += 1
            else:
                svc_70x100.base_price = dec_70x100_p
                svc_70x100.setup_cost = dec_70x100_s
                svc_70x100.machine = cd102
                svc_70x100.dimension = dim_70x100
                svc_70x100.save()

        msg = f"تمت تهيئة ماكينات الطباعة القياسية للمورد {supplier.name} بنجاح!"
        messages.success(request, msg)
        return JsonResponse({'success': True, 'message': msg, 'created_count': created_count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@login_required
@require_printing_pricing_enabled
def supplier_seed_paper_matrix(request, pk):
    """
    توليد مصفوفة أسعار الورق التلقائية للمورد (سعر الطن + نوع الورق + المقاسات + الجراماجات)
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)

    from supplier.models import SupplierService, ServiceType
    from printing_pricing.models import PaperType, PaperSize, PaperOrigin, PaperWeight
    from decimal import Decimal, InvalidOperation

    paper_type_id = request.POST.get('paper_type_id')
    paper_origin_id = request.POST.get('paper_origin_id')
    price_per_ton_raw = request.POST.get('price_per_ton', '').strip()
    size_ids = request.POST.getlist('paper_sizes')
    weight_ids = request.POST.getlist('paper_weights')

    if not paper_type_id or not price_per_ton_raw:
        return JsonResponse({'success': False, 'error': 'يجب تحديد نوع الورق وسعر الطن'}, status=400)

    try:
        price_per_ton = Decimal(str(price_per_ton_raw))
        if price_per_ton <= Decimal('0.00'):
            raise ValueError()
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'error': 'سعر الطن يجب أن يكون رقماً موجباً أكبر من الصفر'}, status=400)

    paper_type = get_object_or_404(PaperType, pk=paper_type_id)
    paper_origin = PaperOrigin.objects.filter(pk=paper_origin_id).first() if paper_origin_id else None

    paper_st = ServiceType.objects.filter(code='paper', is_active=True).first()
    if not paper_st:
        return JsonResponse({'success': False, 'error': 'نوع خدمة الورق غير معرف في النظام'}, status=400)

    sizes = PaperSize.objects.filter(id__in=size_ids, is_active=True) if size_ids else PaperSize.objects.filter(is_active=True)[:2]
    weights = PaperWeight.objects.filter(id__in=weight_ids, is_active=True) if weight_ids else PaperWeight.objects.filter(is_active=True)[:4]

    if not sizes.exists() or not weights.exists():
        return JsonResponse({'success': False, 'error': 'يجب اختيار مقاس واحد ووزن جراماج واحد على الأقل'}, status=400)

    created_count = 0
    updated_count = 0

    with transaction.atomic():
        for s in sizes:
            for w in weights:
                w_cm = s.width
                h_cm = s.height
                g = w.gsm
                sheet_weight_kg = (Decimal(str(w_cm)) * Decimal(str(h_cm)) * Decimal(str(g))) / Decimal('10000000')
                sheet_price = (sheet_weight_kg * (price_per_ton / Decimal('1000'))).quantize(Decimal('0.0001'))

                origin_suffix = f" ({paper_origin.name})" if paper_origin else ""
                svc_name = f"{paper_type.name} — {s.name} — {g} جم{origin_suffix}"

                w_int = int(s.width) if s.width == int(s.width) else float(s.width)
                h_int = int(s.height) if s.height == int(s.height) else float(s.height)

                svc, created = SupplierService.objects.get_or_create(
                    supplier=supplier,
                    service_type=paper_st,
                    paper_type_ref=paper_type,
                    paper_size=s,
                    gsm=g,
                    defaults={
                        'name': svc_name,
                        'pricing_formula': 'PER_TON',
                        'price_per_ton': price_per_ton,
                        'base_price': sheet_price,
                        'paper_weight': w,
                        'paper_origin': paper_origin,
                        'currency': supplier.default_currency,
                        'is_active': True,
                        'attributes': {
                            'paper_type': paper_type.name,
                            'sheet_size': f"{w_int}x{h_int}",
                            'parent_sheet_size': s.name,
                            'gsm': g,
                            'origin': paper_origin.name if paper_origin else '',
                        }
                    }
                )
                if created:
                    created_count += 1
                else:
                    svc.price_per_ton = price_per_ton
                    svc.base_price = sheet_price
                    svc.pricing_formula = 'PER_TON'
                    svc.paper_weight = w
                    svc.paper_origin = paper_origin
                    svc.currency = supplier.default_currency
                    svc.is_active = True
                    svc.save()
                    updated_count += 1

        if supplier.is_pricing_supplier:
            supplier.provided_services.add(paper_st)

    msg = f"تم توليد مصفوفة أسعار الورق بنجاح: إضافة {created_count} صنف وتحديث {updated_count} صنف."
    messages.success(request, msg)
    return JsonResponse({'success': True, 'message': msg, 'created_count': created_count, 'updated_count': updated_count})
