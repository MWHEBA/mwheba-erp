"""عروض إدارة أنواع خدمات التسعير (ServiceType) — مودال"""
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string

from supplier.models import ServiceType
from supplier.decorators import require_printing_pricing_enabled


# ── helpers ──────────────────────────────────────────────────────

def _settings_url():
    return reverse('supplier:service_type_list')


def _get_available_sources():
    source_map = {
        'PaperType':          'أنواع الورق',
        'PaperSize':          'مقاسات الورق',
        'PaperWeight':        'أوزان الورق',
        'PaperOrigin':        'مناشئ الورق',
        'OffsetMachineType':  'أنواع ماكينات الأوفست',
        'DigitalMachineType': 'أنواع ماكينات الديجيتال',
        'CoatingType':        'أنواع التغطية',
        'FinishingType':      'أنواع التشطيب',
        'PackagingType':      'أنواع التقفيل',
        'PlateSize':          'مقاسات الزنكات',
        'PieceSize':          'مقاسات القطع وتفصيل السلندر',
    }
    try:
        import printing_pricing.models as sm
        sources = []
        for model_name, label in source_map.items():
            model = getattr(sm, model_name, None)
            if model:
                count = model.objects.filter(is_active=True).count() if hasattr(model, 'is_active') else model.objects.count()
                sources.append({'value': model_name, 'label': f'{label} ({count})'})
        return sources
    except Exception:
        return [{'value': k, 'label': v} for k, v in source_map.items()]


# ── List — صفحة رئيسية مستقلة لخدمات وقدرات التسعير ───────────────

@login_required
@require_printing_pricing_enabled
def service_type_list(request):
    """عرض قائمة خدمات وقدرات التسعير — صفحة رئيسية مستقلة"""
    from django.db.models import Count
    from core.utils import paginate_queryset

    service_types_qs = (
        ServiceType.objects.all()
        .annotate(
            services_count=Count('supplier_services', distinct=True),
            suppliers_count=Count('supplier_services__supplier', distinct=True)
        )
        .order_by('order', 'name')
    )

    # إحصائيات KPI (Rule 7)
    total_services = service_types_qs.count()
    active_services = service_types_qs.filter(is_active=True).count()
    printing_services = service_types_qs.filter(category='printing').count()
    total_approved_suppliers = sum(st.suppliers_count for st in service_types_qs)

    stats = {
        'total': total_services,
        'active': active_services,
        'printing': printing_services,
        'suppliers_total': total_approved_suppliers,
    }

    pagination_context = paginate_queryset(service_types_qs, request, default_per_page=25)
    page_obj = pagination_context["page_obj"]

    context = {
        'page_obj': page_obj,
        'service_types': page_obj.object_list,
        **pagination_context,
        'stats': stats,
        'page_title': 'خدمات وقدرات التسعير',
        'page_subtitle': 'إدارة وتوصيف أنواع الخدمات الصناعية والقدرات الإنتاجية المعتمدة للموردين',
        'page_icon': 'fas fa-tags',
        'active_menu': 'printing_pricing',
        'active_submenu': 'service_types',
        'header_buttons': [
            {
                'onclick': "openServiceTypeModal()",
                'icon': 'fa-plus',
                'text': 'إضافة نوع خدمة',
                'class': 'btn-primary',
            },
            {
                'url': reverse('printing_pricing:settings_home'),
                'icon': 'fa-cog',
                'text': 'إعدادات التسعير',
                'class': 'btn-outline-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'تسعير المطبوعات', 'url': reverse('printing_pricing:order_list'), 'icon': 'fas fa-print'},
            {'title': 'خدمات وقدرات التسعير', 'active': True},
        ],
    }
    return render(request, 'supplier/settings/service_types/list.html', context)


# ── Create (AJAX modal) ───────────────────────────────────────────

@login_required
@require_printing_pricing_enabled
def service_type_create(request):
    """إضافة نوع خدمة — يعمل كـ AJAX modal أو redirect للصفحة الموحدة"""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        name      = request.POST.get('name', '').strip()
        code      = request.POST.get('code', '').strip()
        category  = request.POST.get('category', 'general')
        icon      = request.POST.get('icon', 'fas fa-cog').strip()
        desc      = request.POST.get('description', '').strip()
        order     = int(request.POST.get('order', 0) or 0)
        is_active = request.POST.get('is_active') == 'on'

        errors = {}
        if not name: errors['name'] = 'الاسم مطلوب'
        if not code: errors['code'] = 'الرمز مطلوب'
        elif ServiceType.objects.filter(code=code).exists():
            errors['code'] = 'هذا الرمز مستخدم بالفعل'

        if not errors:
            st = ServiceType.objects.create(
                name=name, code=code, category=category,
                icon=icon, description=desc, order=order, is_active=is_active,
            )
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f'تم إضافة "{name}" بنجاح',
                    'schema_url': reverse('supplier:service_type_schema', kwargs={'pk': st.pk}),
                    'pk': st.pk,
                })
            messages.success(request, f'تم إضافة نوع الخدمة "{name}" بنجاح')
            return redirect(reverse('supplier:service_type_schema', kwargs={'pk': st.pk}))

        if is_ajax:
            return JsonResponse({'success': False, 'errors': errors})
        for msg in errors.values():
            messages.error(request, msg)

    # GET — إرجاع HTML المودال
    form_data = {
        'name':        request.POST.get('name', ''),
        'code':        request.POST.get('code', ''),
        'category':    request.POST.get('category', 'general'),
        'icon':        request.POST.get('icon', 'fas fa-cog'),
        'description': request.POST.get('description', ''),
        'order':       request.POST.get('order', '0'),
        'is_active':   True,
    }
    ctx = {
        'form_data':  form_data,
        'categories': ServiceType.CATEGORY_CHOICES,
        'action_url': reverse('supplier:service_type_create'),
        'modal_title': 'إضافة نوع خدمة جديد',
    }
    if is_ajax:
        html = render_to_string('supplier/settings/service_types/modal_form.html', ctx, request=request)
        return JsonResponse({'html': html})

    # fallback — redirect للصفحة الموحدة
    return redirect(_settings_url())


# ── Edit (AJAX modal) ─────────────────────────────────────────────

@login_required
@require_printing_pricing_enabled
def service_type_edit(request, pk):
    """تعديل نوع خدمة — يعمل كـ AJAX modal"""
    st = get_object_or_404(ServiceType, pk=pk)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        name      = request.POST.get('name', '').strip()
        code      = request.POST.get('code', '').strip()
        category  = request.POST.get('category', 'general')
        icon      = request.POST.get('icon', 'fas fa-cog').strip()
        desc      = request.POST.get('description', '').strip()
        order     = int(request.POST.get('order', 0) or 0)
        is_active = request.POST.get('is_active') == 'on'

        errors = {}
        if not name: errors['name'] = 'الاسم مطلوب'
        if not code: errors['code'] = 'الرمز مطلوب'
        elif ServiceType.objects.filter(code=code).exclude(pk=pk).exists():
            errors['code'] = 'هذا الرمز مستخدم بالفعل'

        if not errors:
            st.name = name; st.code = code; st.category = category
            st.icon = icon; st.description = desc
            st.order = order; st.is_active = is_active
            st.save()
            if is_ajax:
                return JsonResponse({'success': True, 'message': f'تم تحديث "{name}" بنجاح'})
            messages.success(request, f'تم تحديث نوع الخدمة "{name}" بنجاح')
            return redirect(_settings_url())

        if is_ajax:
            return JsonResponse({'success': False, 'errors': errors})
        for msg in errors.values():
            messages.error(request, msg)

    # GET — إرجاع HTML المودال
    ctx = {
        'form_data': {
            'name':        st.name,
            'code':        st.code,
            'category':    st.category,
            'icon':        st.icon,
            'description': st.description,
            'order':       st.order,
            'is_active':   st.is_active,
        },
        'categories':  ServiceType.CATEGORY_CHOICES,
        'action_url':  reverse('supplier:service_type_edit', kwargs={'pk': pk}),
        'modal_title': f'تعديل: {st.name}',
        'service_type': st,
    }
    if is_ajax:
        html = render_to_string('supplier/settings/service_types/modal_form.html', ctx, request=request)
        return JsonResponse({'html': html})

    return redirect(_settings_url())


# ── Delete ────────────────────────────────────────────────────────

@login_required
@require_POST
@require_printing_pricing_enabled
def service_type_delete(request, pk):
    st = get_object_or_404(ServiceType, pk=pk)
    svc_count = st.supplier_services.count()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if svc_count > 0:
        msg = f'لا يمكن الحذف — يوجد {svc_count} خدمة مرتبطة'
        if is_ajax:
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect(_settings_url())

    name = st.name
    st.delete()
    if is_ajax:
        return JsonResponse({'success': True, 'message': f'تم حذف "{name}" بنجاح'})
    messages.success(request, f'تم حذف "{name}" بنجاح')
    return redirect(_settings_url())


# ── Schema Editor ─────────────────────────────────────────────────

@login_required
@require_printing_pricing_enabled
def service_type_schema(request, pk):
    """واجهة تعريف attribute_schema — صفحة كاملة (مش مودال لأنها معقدة)"""
    st = get_object_or_404(ServiceType, pk=pk)

    if request.method == 'POST':
        try:
            schema = json.loads(request.POST.get('schema_json', '{}'))
            st.attribute_schema = schema
            st.save()
            messages.success(request, f'تم حفظ حقول "{st.name}" بنجاح')
            return redirect(_settings_url())
        except json.JSONDecodeError:
            messages.error(request, 'JSON غير صحيح — تحقق من الحقول')

    from django.urls import reverse as _rev
    ctx = {
        'page_title':   f'حقول الخدمة: {st.name}',
        'page_icon':    'fas fa-sliders-h',
        'service_type': st,
        'schema_json':  json.dumps(st.attribute_schema, ensure_ascii=False, indent=2),
        'sources':      _get_available_sources(),
        'header_buttons': [
            {'url': _settings_url(), 'icon': 'fa-arrow-right', 'text': 'العودة لقائمة الخدمات', 'class': 'btn-secondary'},
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': _rev('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'تسعير المطبوعات', 'url': _rev('printing_pricing:order_list'), 'icon': 'fas fa-print'},
            {'title': 'خدمات وقدرات التسعير', 'url': _rev('supplier:service_type_list'), 'icon': 'fas fa-tags'},
            {'title': f'حقول: {st.name}', 'active': True},
        ],
    }
    return render(request, 'supplier/settings/service_types/schema_editor.html', ctx)


# ── API: sources ──────────────────────────────────────────────────

@login_required
@require_printing_pricing_enabled
def service_type_schema_sources_api(request):
    return JsonResponse({'success': True, 'sources': _get_available_sources()})
