"""
عروض وإدارة مصفوفة وقائمة أسعار خامات وخدمات الموردين في MWHEBA ERP.
Master Service & Substrate Pricing Matrix & Data Quality Audit Engine
"""
import json
import logging
from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, Optional

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_POST, require_GET
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Q, Count

from supplier.models import SupplierService, ServiceType, Supplier
from supplier.decorators import require_printing_pricing_enabled
from printing_pricing.services.bulk_price_updater import BulkPriceUpdaterService
from printing_pricing.models import PaperType, PaperSize, PaperOrigin
from financial.models.currency import Currency, ExchangeRate
from financial.services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger(__name__)


class ServiceSpecAdapter:
    """محول بيانات آمن لاستخراج مواصفات الخدمات من الحقول أو JSON لتفادي AttributeError"""
    @staticmethod
    def get_val(service: SupplierService, key: str, default=None):
        if hasattr(service, key):
            val = getattr(service, key)
            if val is not None:
                return val
        if service.attributes and isinstance(service.attributes, dict) and key in service.attributes:
            return service.attributes[key]
        return default


def _get_rates_map(functional_currency) -> Dict[Any, Decimal]:
    """تحميل أحدث أسعار صرف مقابل العملة الوظيفية في الذاكرة لتفادي N+1 Queries (IAS 21)"""
    rates = {}
    if functional_currency and getattr(functional_currency, 'id', None):
        rates[functional_currency.id] = Decimal('1.0')
        rates[functional_currency.code] = Decimal('1.0')

        qs = ExchangeRate.objects.filter(
            to_currency=functional_currency
        ).order_by('from_currency', '-effective_date')

        for r in qs:
            if r.from_currency_id not in rates:
                rates[r.from_currency_id] = r.rate
                if r.from_currency and r.from_currency.code:
                    rates[r.from_currency.code] = r.rate

    # Fallbacks للعملات النشطة الشائعة إن لم يكن لها سجل
    for c in Currency.objects.filter(is_active=True):
        if c.id not in rates:
            rates[c.id] = Decimal('1.0')
            rates[c.code] = Decimal('1.0')

    return rates


def _convert_to_egp(amount: Optional[Decimal], service: SupplierService, rates_map: Dict[Any, Decimal]) -> Decimal:
    """تحويل السعر اللحظي للجنيه المصري في الذاكرة O(1)"""
    if not amount or amount <= Decimal('0.00'):
        return Decimal('0.00')

    curr = service.effective_currency
    if not curr or getattr(curr, 'is_functional', False) or getattr(curr, 'code', '') == 'EGP':
        return amount

    rate = rates_map.get(getattr(curr, 'id', None)) or rates_map.get(getattr(curr, 'code', 'EGP'), Decimal('1.0'))
    return (Decimal(str(amount)) * rate).quantize(Decimal('0.0001'))


def _compute_best_market_prices(services_qs, rates_map: Dict[Any, Decimal]) -> Dict[str, Any]:
    """
    حساب السعر الأدنى لكل مواصفة متطابقة عبر كامل قاعدة البيانات المفلترة (Global Aggregation Pre-pass)
    مع اشتراط وجود منافسين اثنين فأكثر (>= 2) وسعر نشط ساري لمنح شارة الأفضل سعراً.
    """
    spec_groups = {} # spec_key -> list of {service_id, egp_price}

    for s in services_qs:
        code = s.service_type.code if s.service_type else ''
        if code == 'paper':
            spec_key = (
                'paper',
                s.paper_type_ref_id,
                s.paper_size_id,
                s.gsm or (s.paper_weight.gsm if s.paper_weight else None),
                s.paper_origin_id
            )
            sheet_price = s.get_effective_sheet_price()
            egp_price = _convert_to_egp(sheet_price, s, rates_map)
        elif code in ['offset_printing', 'ctp_plates']:
            spec_key = (
                code,
                s.machine_id if code == 'offset_printing' else None,
                s.dimension_id if code == 'offset_printing' else None,
                s.plate_size_id if code == 'ctp_plates' else None
            )
            price = s.set_price or s.base_price
            egp_price = _convert_to_egp(price, s, rates_map)
        else:
            spec_key = (
                'other',
                s.service_type_id,
                s.coating_type_id or s.finishing_type_id or s.packaging_type_id or s.name
            )
            egp_price = _convert_to_egp(s.base_price, s, rates_map)

        if egp_price > Decimal('0.00'):
            if spec_key not in spec_groups:
                spec_groups[spec_key] = []
            spec_groups[spec_key].append({'id': s.id, 'egp_price': egp_price, 'supplier_id': s.supplier_id})

    best_service_ids = set()
    for spec_key, items in spec_groups.items():
        # فحص عدد الموردين المستقلين المتنافسين على نفس المواصفة
        unique_suppliers = set(item['supplier_id'] for item in items)
        if len(unique_suppliers) >= 2:
            min_price = min(item['egp_price'] for item in items)
            for item in items:
                if item['egp_price'] == min_price:
                    best_service_ids.add(item['id'])

    return best_service_ids


def _get_scoped_paper_filters(base_paper_qs, params):
    """
    حساب خيارات فلاتر مواصفات الورق المتاحة فعلياً وفق التصفية الحالية (Faceted Filters)
    بحيث لا يظهر في أي قائمة منسدلة إلا ما له وجود حقيقي مطابق في نتائج الجدول بجد.
    """
    scope_qs = base_paper_qs

    q = params.get('q', '').strip()
    if q:
        q_filter = (
            Q(name__icontains=q) |
            Q(supplier__name__icontains=q) |
            Q(paper_type_ref__name__icontains=q) |
            Q(paper_size__name__icontains=q) |
            Q(paper_origin__name__icontains=q)
        )
        if q.isdigit():
            q_filter |= Q(gsm=int(q)) | Q(paper_weight__gsm=int(q))
        scope_qs = scope_qs.filter(q_filter)

    status = params.get('status')
    if status == 'active':
        scope_qs = scope_qs.filter(is_active=True)
    elif status == 'inactive':
        scope_qs = scope_qs.filter(is_active=False)

    if params.get('preferred_only') == '1':
        scope_qs = scope_qs.filter(supplier__is_preferred=True)

    if params.get('audit_zero') == '1':
        scope_qs = scope_qs.filter(
            Q(base_price=Decimal('0.00')) |
            (Q(pricing_formula='PER_TON') & (Q(price_per_ton__isnull=True) | Q(price_per_ton=Decimal('0.00'))))
        )

    sup_id = int(params['supplier']) if params.get('supplier', '').isdigit() else None
    type_id = int(params['paper_type_ref']) if params.get('paper_type_ref', '').isdigit() else None
    gsm_val = int(params['gsm']) if params.get('gsm', '').isdigit() else None
    size_id = int(params['paper_size']) if params.get('paper_size', '').isdigit() else None
    origin_id = int(params['paper_origin']) if params.get('paper_origin', '').isdigit() else None

    def _build_qs(exclude_field):
        qs = scope_qs
        if sup_id and exclude_field != 'supplier':
            qs = qs.filter(supplier_id=sup_id)
        if type_id and exclude_field != 'paper_type_ref':
            qs = qs.filter(paper_type_ref_id=type_id)
        if gsm_val and exclude_field != 'gsm':
            qs = qs.filter(Q(gsm=gsm_val) | Q(paper_weight__gsm=gsm_val))
        if size_id and exclude_field != 'paper_size':
            qs = qs.filter(paper_size_id=size_id)
        if origin_id and exclude_field != 'paper_origin':
            qs = qs.filter(paper_origin_id=origin_id)
        return qs

    # 1. الموردون المتاحون
    sup_ids = _build_qs('supplier').values_list('supplier_id', flat=True).distinct()
    tab_suppliers = Supplier.objects.filter(id__in=sup_ids, is_active=True).order_by('name')

    # 2. الخامات المتاحة
    type_ids = _build_qs('paper_type_ref').exclude(paper_type_ref__isnull=True).values_list('paper_type_ref_id', flat=True).distinct()
    paper_types = PaperType.objects.filter(id__in=type_ids, is_active=True).order_by('sort_order', 'name')

    # 3. الجرامات المتاحة
    available_gsms = list(
        _build_qs('gsm').exclude(gsm__isnull=True).values_list('gsm', flat=True).distinct().order_by('gsm')
    )

    # 4. المقاسات المتاحة
    size_ids = _build_qs('paper_size').exclude(paper_size__isnull=True).values_list('paper_size_id', flat=True).distinct()
    paper_sizes = PaperSize.objects.filter(id__in=size_ids, is_active=True).order_by('sort_order', 'name')

    # 5. المناشئ المتاحة
    origin_ids = _build_qs('paper_origin').exclude(paper_origin__isnull=True).values_list('paper_origin_id', flat=True).distinct()
    paper_origins = PaperOrigin.objects.filter(id__in=origin_ids, is_active=True).order_by('sort_order', 'name')

    return tab_suppliers, paper_types, available_gsms, paper_sizes, paper_origins


@login_required
@require_printing_pricing_enabled
def service_pricing_matrix_view(request):
    """
    العرض الرئيسي لمصفوفة وقائمة أسعار خامات وخدمات الموردين مع التبويبات المتخصصة.
    """
    from core.utils import paginate_queryset

    service_types = ServiceType.objects.filter(is_active=True).order_by('order', 'name')
    first_st = service_types.first()
    default_tab = first_st.code if first_st else 'paper'

    active_tab = request.GET.get('tab', '').strip()
    active_service_type = None
    if active_tab:
        active_service_type = service_types.filter(code=active_tab).first()

    if not active_service_type:
        active_service_type = first_st
        active_tab = default_tab

    # 1. تصفية الاستعلام الأساسي
    base_qs = SupplierService.objects.select_related(
        'supplier', 'service_type', 'currency', 'machine', 'dimension',
        'paper_type_ref', 'paper_size', 'paper_origin', 'paper_weight',
        'plate_size', 'coating_type', 'finishing_type', 'packaging_type'
    ).prefetch_related('price_tiers')

    # فلاتر البحث والتدقيق الذكي
    search_query = request.GET.get('q', '').strip()
    if search_query:
        q_filter = (
            Q(name__icontains=search_query) |
            Q(supplier__name__icontains=search_query) |
            Q(paper_type_ref__name__icontains=search_query) |
            Q(paper_size__name__icontains=search_query) |
            Q(paper_origin__name__icontains=search_query) |
            Q(machine__name__icontains=search_query) |
            Q(coating_type__name__icontains=search_query) |
            Q(finishing_type__name__icontains=search_query)
        )
        if search_query.isdigit():
            q_filter |= Q(gsm=int(search_query)) | Q(paper_weight__gsm=int(search_query))
        base_qs = base_qs.filter(q_filter)

    supplier_filter = request.GET.get('supplier')
    if supplier_filter and supplier_filter.isdigit():
        base_qs = base_qs.filter(supplier_id=int(supplier_filter))

    status_filter = request.GET.get('status')
    if status_filter == 'active':
        base_qs = base_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        base_qs = base_qs.filter(is_active=False)

    audit_zero = request.GET.get('audit_zero') == '1'
    if audit_zero:
        base_qs = base_qs.filter(
            Q(base_price=Decimal('0.00')) |
            (Q(pricing_formula='PER_TON') & (Q(price_per_ton__isnull=True) | Q(price_per_ton=Decimal('0.00'))))
        )

    preferred_only = request.GET.get('preferred_only') == '1'
    if preferred_only:
        base_qs = base_qs.filter(supplier__is_preferred=True)

    # فلاتر الورق التخصصية
    paper_type_filter = request.GET.get('paper_type_ref')
    if paper_type_filter and paper_type_filter.isdigit():
        base_qs = base_qs.filter(paper_type_ref_id=int(paper_type_filter))

    gsm_filter = request.GET.get('gsm')
    if gsm_filter and gsm_filter.isdigit():
        base_qs = base_qs.filter(Q(gsm=int(gsm_filter)) | Q(paper_weight__gsm=int(gsm_filter)))

    paper_size_filter = request.GET.get('paper_size')
    if paper_size_filter and paper_size_filter.isdigit():
        base_qs = base_qs.filter(paper_size_id=int(paper_size_filter))

    paper_origin_filter = request.GET.get('paper_origin')
    if paper_origin_filter and paper_origin_filter.isdigit():
        base_qs = base_qs.filter(paper_origin_id=int(paper_origin_filter))

    # 2. فلترة التبويب المحدد بنوع الخدمة حصراً (بدون عام)
    if active_service_type:
        tab_qs = base_qs.filter(service_type=active_service_type)
    elif active_tab == 'paper':
        tab_qs = base_qs.filter(service_type__code='paper')
    else:
        tab_qs = base_qs

    # الترتيب الفيزيائي الحتمي
    if active_tab == 'paper':
        tab_qs = tab_qs.order_by(
            'paper_type_ref__name',
            'gsm',
            'paper_size__width',
            'price_per_ton',
            'base_price'
        )
    else:
        tab_qs = tab_qs.order_by('name', 'base_price')

    # 3. محرك العملات IAS 21 والـ Pre-pass ضد كامل حوض السوق
    functional_curr = ExchangeRateService.get_functional_currency()
    rates_map = _get_rates_map(functional_curr)

    # حساب أفضل الأسعار لكامل حوض سوق الخدمة النشطة قبل تصفية المورد الفردي
    global_target_st = active_service_type or (service_types.filter(code='paper').first() or first_st)
    market_pool_qs = SupplierService.objects.filter(
        service_type=global_target_st,
        is_active=True
    ).select_related('currency', 'paper_size', 'dimension', 'paper_weight')
    best_service_ids = _compute_best_market_prices(market_pool_qs, rates_map)

    # 4. تصدير Excel إذا تم طلبه
    if request.GET.get('export') == 'excel':
        return _export_matrix_to_excel(tab_qs, active_tab, rates_map, best_service_ids)

    # 5. التقطيع بـ Server-Side Pagination (رفع الحد الافتراضي إلى 50)
    pagination_context = paginate_queryset(tab_qs, request, default_per_page=50)
    page_obj = pagination_context['page_obj']

    # تزيين عناصر الصفحة الحالية بالحسابات المشتقة السريعة
    now_date = timezone.now().date()
    for item in page_obj.object_list:
        item.is_best_price = item.id in best_service_ids
        item.is_preferred_supplier = getattr(item.supplier, 'is_preferred', False)
        item.effective_sheet_price = item.get_effective_sheet_price()
        item.effective_sheet_price_egp = _convert_to_egp(item.effective_sheet_price, item, rates_map)
        item.base_price_egp = _convert_to_egp(item.base_price, item, rates_map)
        if item.price_per_ton:
            item.price_per_ton_egp = _convert_to_egp(item.price_per_ton, item, rates_map)
        if item.set_price:
            item.set_price_egp = _convert_to_egp(item.set_price, item, rates_map)

        # فحص ركود السعر (> 30 يوم)
        if item.updated_at:
            delta_days = (now_date - item.updated_at.date()).days
            item.is_stale = delta_days > 30
            item.stale_days = delta_days
        else:
            item.is_stale = False
            item.stale_days = 0

    # 6. إحصائيات الـ KPI
    cutoff_stale = timezone.now() - timedelta(days=30)
    total_services = tab_qs.count()
    zero_price_count = tab_qs.filter(
        Q(base_price=Decimal('0.00')) |
        (Q(pricing_formula='PER_TON') & (Q(price_per_ton__isnull=True) | Q(price_per_ton=Decimal('0.00'))))
    ).count()
    stale_price_count = tab_qs.filter(updated_at__lt=cutoff_stale).count()
    preferred_suppliers_count = tab_qs.filter(supplier__is_preferred=True).values('supplier_id').distinct().count()

    # Lookups محصورة حصراً للأصناف والموردين المتوفرين فعلياً في التبويب الحالي وفق الفلاتر النشطة (الموجود بجد في الجدول)
    if active_tab == 'paper':
        base_paper_stock = SupplierService.objects.filter(
            service_type__code='paper',
            is_active=True
        )
        tab_suppliers, paper_types, available_gsms, paper_sizes, paper_origins = _get_scoped_paper_filters(
            base_paper_stock, request.GET
        )
    else:
        other_st_services = SupplierService.objects.filter(
            service_type=active_service_type,
            is_active=True
        )
        if search_query:
            other_st_services = other_st_services.filter(
                Q(name__icontains=search_query) |
                Q(supplier__name__icontains=search_query) |
                Q(machine__name__icontains=search_query) |
                Q(coating_type__name__icontains=search_query) |
                Q(finishing_type__name__icontains=search_query)
            )
        avail_sup_ids = other_st_services.values_list('supplier_id', flat=True).distinct()
        tab_suppliers = Supplier.objects.filter(id__in=avail_sup_ids, is_active=True).order_by('name')
        paper_types = PaperType.objects.none()
        paper_sizes = PaperSize.objects.none()
        paper_origins = PaperOrigin.objects.none()
        available_gsms = []

    context = {
        'page_title': _('أسعار الخدمات'),
        'page_subtitle': _('مقارنة أسعار الموردين وتدقيق تسعير الورق والماكينات والتشطيبات لخدمة محرك المقايسات'),
        'page_icon': 'fas fa-tags',
        'active_menu': 'printing_pricing',
        'active_submenu': 'pricing_matrix',
        'active_tab': active_tab,
        'active_service_type': active_service_type,
        'page_obj': page_obj,
        'services': page_obj.object_list,
        'rates_map': rates_map,
        'functional_curr': functional_curr,
        'total_services': total_services,
        'zero_price_count': zero_price_count,
        'stale_price_count': stale_price_count,
        'preferred_suppliers_count': preferred_suppliers_count,
        'suppliers': tab_suppliers,
        'service_types': service_types,
        'paper_types': paper_types,
        'paper_sizes': paper_sizes,
        'paper_origins': paper_origins,
        'available_gsms': available_gsms,
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('تسعير المطبوعات'), 'url': reverse('supplier:service_type_list'), 'icon': 'fa-calculator'},
            {'title': _('أسعار الخدمات'), 'active': True}
        ],
        'header_buttons': [
            {
                'url': f"?{request.GET.urlencode()}&export=excel" if request.GET else "?export=excel",
                'icon': 'fa-file-excel',
                'text': _('تصدير Excel'),
                'class': 'btn-outline-secondary'
            },
            {
                'onclick': 'openBulkUpdateModal()',
                'icon': 'fa-percentage',
                'text': _('تحديث جماعي للأسعار'),
                'class': 'btn-primary'
            }
        ]
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.GET.get('ajax') == '1':
        # رد AJAX جزئي لتحديث الجدول والصفحات
        if active_tab == 'paper':
            template_name = 'supplier/services/partials/tab_paper.html'
            table_content_template = 'supplier/services/partials/_paper_table_content.html'
        else:
            template_name = 'supplier/services/partials/tab_service.html'
            table_content_template = 'supplier/services/partials/_service_table_content.html'

        table_html = render_to_string(template_name, context, request=request)
        table_wrapper_html = render_to_string(table_content_template, context, request=request)
        pagination_html = render_to_string('partials/pagination.html', {'page_obj': page_obj}, request=request)
        summary_html = render_to_string('supplier/services/partials/_stats_cards.html', context, request=request)
        filters_data = {
            'suppliers': [{'id': s.id, 'name': s.name} for s in tab_suppliers],
            'paper_types': [{'id': pt.id, 'name': pt.name} for pt in paper_types],
            'paper_sizes': [{'id': ps.id, 'name': ps.name} for ps in paper_sizes],
            'paper_origins': [{'id': po.id, 'name': po.name} for po in paper_origins],
            'gsms': [{'id': g, 'name': f"{g} جم"} for g in available_gsms],
        }
        return JsonResponse({
            'success': True,
            'table_html': table_html,
            'table_wrapper_html': table_wrapper_html,
            'pagination_html': pagination_html,
            'summary_html': summary_html,
            'filters_data': filters_data,
        })

    return render(request, 'supplier/services/pricing_matrix.html', context)


@require_POST
@login_required
def service_price_quick_update(request, pk):
    """
    تحديث ذري سريع لسعر خدمة معينة وإعادة حساب سعر الفرخ والمعادل بالـ EGP
    وإرجاع السطر المحدث بالكامل row_html لتبديله في الـ DOM.
    """
    service = get_object_or_404(
        SupplierService.objects.select_related(
            'supplier', 'service_type', 'currency', 'machine', 'dimension',
            'paper_type_ref', 'paper_size', 'paper_origin', 'paper_weight',
            'plate_size', 'coating_type', 'finishing_type', 'packaging_type'
        ).prefetch_related('price_tiers'),
        pk=pk
    )

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    field_name = data.get('field', 'base_price')
    new_val = data.get('value')

    if new_val is None:
        return JsonResponse({'success': False, 'message': _('القيمة الجديدة مطلوبة')}, status=400)

    try:
        val_dec = Decimal(str(new_val))
        if val_dec < Decimal('0.00'):
            return JsonResponse({'success': False, 'message': _('السعر لا يمكن أن يكون سالباً')}, status=400)

        kwargs = {'user': request.user}
        if field_name == 'price_per_ton':
            kwargs['price_per_ton'] = val_dec
        elif field_name == 'set_price':
            kwargs['set_price'] = val_dec
        else:
            kwargs['base_price'] = val_dec

        BulkPriceUpdaterService.update_single_service(service, **kwargs)

        # حساب المعادل للسطر
        functional_curr = ExchangeRateService.get_functional_currency()
        rates_map = _get_rates_map(functional_curr)

        service.effective_sheet_price = service.get_effective_sheet_price()
        service.effective_sheet_price_egp = _convert_to_egp(service.effective_sheet_price, service, rates_map)
        service.base_price_egp = _convert_to_egp(service.base_price, service, rates_map)
        if service.price_per_ton:
            service.price_per_ton_egp = _convert_to_egp(service.price_per_ton, service, rates_map)
        if service.set_price:
            service.set_price_egp = _convert_to_egp(service.set_price, service, rates_map)

        # رندر السطر المحدث بالكامل
        row_template = 'supplier/services/partials/_paper_row.html' if service.service_type.code == 'paper' else 'supplier/services/partials/_service_row.html'
        row_html = render_to_string(row_template, {'item': service, 'functional_curr': functional_curr}, request=request)

        return JsonResponse({
            'success': True,
            'message': _('تم تحديث السعر واحتساب سعر الفرخ بنجاح'),
            'row_html': row_html,
            'effective_sheet_price': str(service.effective_sheet_price),
            'effective_sheet_price_egp': str(service.effective_sheet_price_egp),
        })

    except Exception as e:
        logger.exception(f"Error in quick price update: {e}")
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_POST
@login_required
def toggle_preferred_supplier_api(request, pk):
    """
    تبديل أو تعيين حالة المورد المعتمد للمطبعة (supplier__is_preferred) بنقرة واحدة من الجدول.
    """
    service = get_object_or_404(SupplierService.objects.select_related('supplier'), pk=pk)
    supplier = service.supplier

    new_state = not getattr(supplier, 'is_preferred', False)
    supplier.is_preferred = new_state
    supplier.save(update_fields=['is_preferred'])

    return JsonResponse({
        'success': True,
        'is_preferred': new_state,
        'message': _('تم تعيين {} كمورد معتمد للمطبعة بنجاح').format(supplier.name) if new_state else _('تم إلغاء اعتماد المورد كشريك مفضل')
    })


@require_POST
@login_required
def service_price_bulk_update_api(request):
    """
    تحديث جماعي لأسعار خامات وخدمات الموردين بنسبة مئوية مع تحديث شرائح الكميات التابعة.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    percentage = data.get('percentage')
    service_ids = data.get('service_ids', [])

    if percentage is None:
        return JsonResponse({'success': False, 'message': _('نسبة الزيادة أو التخفيض مطلوبة')}, status=400)

    try:
        pct_dec = Decimal(str(percentage))
        result = BulkPriceUpdaterService.bulk_update_supplier_services(
            service_ids=service_ids,
            percentage_change=pct_dec,
            user=request.user
        )
        return JsonResponse(result)
    except Exception as e:
        logger.exception(f"Error in bulk price update API: {e}")
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def _export_matrix_to_excel(qs, tab: str, rates_map: Dict[Any, Decimal], best_service_ids: set) -> HttpResponse:
    """تصدير مصفوفة الأسعار لملف Excel احترافي"""
    import csv

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"pricing_matrix_{tab}_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    functional_curr = ExchangeRateService.get_functional_currency()
    fc_sym = (getattr(functional_curr, 'symbol', None) or getattr(functional_curr, 'code', '')) if functional_curr else ''

    if tab == 'paper':
        writer.writerow([
            'المورد', 'خامة الورق', 'المنشأ', 'الجراماج', 'المقاس (سم)',
            'سعر الطن (العملة)', 'العملة', f'سعر الطن ({fc_sym})' if fc_sym else 'سعر الطن المعادل', f'سعر الفرخ ({fc_sym})' if fc_sym else 'سعر الفرخ المعادل',
            'سعر الرزمة', 'الأفضل سعراً', 'مورد معتمد', 'تاريخ التحديث'
        ])
        for s in qs:
            sheet_p = s.get_effective_sheet_price()
            sheet_egp = _convert_to_egp(sheet_p, s, rates_map)
            ton_egp = _convert_to_egp(s.price_per_ton, s, rates_map) if s.price_per_ton else ''
            writer.writerow([
                s.supplier.name,
                s.paper_type_ref.name if s.paper_type_ref else s.name,
                s.paper_origin.name if s.paper_origin else '',
                s.gsm or '',
                f"{s.paper_size.width}x{s.paper_size.height}" if s.paper_size else '',
                s.price_per_ton or '',
                s.currency_code,
                ton_egp,
                sheet_egp,
                s.base_price if s.pricing_formula == 'PER_REAM' else '',
                'نعم' if s.id in best_service_ids else 'لا',
                'نعم' if getattr(s.supplier, 'is_preferred', False) else 'لا',
                s.updated_at.strftime('%Y-%m-%d') if s.updated_at else ''
            ])
    else:
        writer.writerow([
            'المورد', 'الخدمة', 'نوع الخدمة', 'السعر الأساسي', 'سعر الطقم',
            'العملة', f'السعر المعادل ({fc_sym})' if fc_sym else 'السعر المعادل', 'الحد الأدنى', 'تاريخ التحديث'
        ])
        for s in qs:
            base_egp = _convert_to_egp(s.base_price, s, rates_map)
            writer.writerow([
                s.supplier.name,
                s.name,
                s.service_type.name if s.service_type else '',
                s.base_price,
                s.set_price or '',
                s.currency_code,
                base_egp,
                s.minimum_charge or '',
                s.updated_at.strftime('%Y-%m-%d') if s.updated_at else ''
            ])

    return response
