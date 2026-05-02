# -*- coding: utf-8 -*-
"""
مدير الأسعار الموحد
تحديث أسعار المنتجات والخدمات من واجهة شبيهة بالإكسل مفلترة بالتصنيف
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db.models import Q

from product.models import Product, Category
from product.models.supplier_pricing import SupplierProductPrice, PriceHistory


@login_required
def price_manager(request):
    """
    واجهة مدير الأسعار — مفلترة بالتصنيف
    type=product  → من صفحة المنتجات
    type=service  → من صفحة الخدمات
    """
    item_type   = request.GET.get('type', 'product')
    category_id = request.GET.get('category', '')
    search      = request.GET.get('q', '').strip()

    is_service = (item_type == 'service')

    qs = (
        Product.objects
        .select_related('category', 'unit')
        .filter(is_service=is_service, is_active=True)
        .order_by('name')
    )

    # التصنيفات الرئيسية فقط (parent=None) مع has_children
    categories_qs = (
        Category.objects
        .filter(
            is_active=True,
            parent__isnull=True,
        )
        .filter(
            Q(children__products__is_service=is_service) |
            Q(products__is_service=is_service)
        )
        .prefetch_related('children')
        .distinct()
        .order_by('name')
    )
    categories = list(categories_qs)
    for cat in categories:
        cat.has_children = cat.children.filter(is_active=True).count()

    paginator = None
    if category_id:
        # دعم التصنيفات الفرعية
        try:
            cat_int = int(category_id)
            selected_cat = Category.objects.get(id=cat_int)
            if selected_cat.parent is None:
                qs = qs.filter(
                    Q(category_id=cat_int) | Q(category__parent_id=cat_int)
                )
            else:
                qs = qs.filter(category_id=cat_int)
        except (ValueError, Category.DoesNotExist):
            pass

        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        paginator   = Paginator(qs, 50)
        page_number = request.GET.get('page', 1)
        items       = paginator.get_page(page_number)
    else:
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
            paginator   = Paginator(qs, 50)
            page_number = request.GET.get('page', 1)
            items       = paginator.get_page(page_number)
        else:
            items = Product.objects.none()

    back_url = reverse('product:service_list') if is_service else reverse('product:product_list')
    title    = 'تحديث أسعار الخدمات' if is_service else 'تحديث أسعار المنتجات'

    context = {
        'title': title,
        'items': items,
        'paginator': paginator,
        'categories': categories,
        'selected_category': category_id,
        'item_type': item_type,
        'search': search,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {
                'title': 'الخدمات' if is_service else 'المنتجات',
                'url': back_url,
                'icon': 'fas fa-concierge-bell' if is_service else 'fas fa-box',
            },
            {'title': title, 'active': True},
        ],
        'header_buttons': [
            {'url': back_url, 'icon': 'fa-arrow-right', 'text': 'رجوع', 'class': 'btn-outline-secondary'},
        ],
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        table_html = render_to_string(
            'product/partials/price_manager_table.html',
            {'items': items},
            request=request,
        )
        pagination_html = render_to_string(
            'partials/pagination.html',
            {'page_obj': items, 'align': 'center'},
            request=request,
        ) if paginator and paginator.num_pages > 1 else ''
        return JsonResponse({'table_html': table_html, 'pagination_html': pagination_html})

    return render(request, 'product/price_manager.html', context)


@login_required
@require_POST
def price_manager_update_api(request):
    """
    تحديث سعر منتج/خدمة واحدة — يُستدعى عند تغيير الخلية (onchange)
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'بيانات غير صحيحة'})

    product_id = data.get('id')
    field      = data.get('field')
    value      = data.get('value')

    ALLOWED = {'selling_price', 'cost_price', 'tax_rate', 'discount_rate'}
    if field not in ALLOWED:
        return JsonResponse({'success': False, 'error': 'حقل غير مسموح'})

    product = get_object_or_404(Product, pk=product_id)
    old_val = getattr(product, field)

    try:
        new_val = Decimal(str(value))
        if new_val < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'error': 'قيمة غير صحيحة'})

    if old_val == new_val:
        return JsonResponse({'success': True, 'changed': False})

    setattr(product, field, new_val)
    product.save(update_fields=[field])  # updated_at هو auto_now — Django يتعامل معه تلقائياً

    # تسجيل في PriceHistory لـ cost_price فقط إذا كان للمنتج مورد افتراضي
    if field == 'cost_price':
        default_supplier_price = SupplierProductPrice.objects.filter(
            product=product, is_default=True
        ).first()
        if default_supplier_price:
            PriceHistory.objects.create(
                supplier_product_price=default_supplier_price,
                old_price=old_val,
                new_price=new_val,
                change_reason='manual_update',
                changed_by=request.user,
            )

    # حساب هامش الربح المحدّث
    profit_margin = None
    try:
        profit_margin = str(round(product.profit_margin, 2))
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'changed': True,
        'profit_margin': profit_margin,
    })


@login_required
@require_POST
def price_manager_bulk_update_api(request):
    """
    تحديث جماعي — زيادة/خفض بنسبة مئوية أو سعر ثابت على منتجات محددة
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'بيانات غير صحيحة'})

    product_ids = data.get('ids', [])
    field       = data.get('field')
    mode        = data.get('mode')   # 'fixed' | 'percent_increase' | 'percent_decrease'
    value       = data.get('value')

    ALLOWED = {'selling_price', 'cost_price'}
    if field not in ALLOWED:
        return JsonResponse({'success': False, 'error': 'حقل غير مسموح'})

    if mode not in ('fixed', 'percent_increase', 'percent_decrease'):
        return JsonResponse({'success': False, 'error': 'عملية غير مسموحة'})

    try:
        val = Decimal(str(value))
        if val < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'error': 'قيمة غير صحيحة'})

    products = Product.objects.filter(pk__in=product_ids)
    updated  = 0

    with transaction.atomic():
        for product in products:
            old_price = getattr(product, field)
            if mode == 'fixed':
                new_price = val
            elif mode == 'percent_increase':
                new_price = (old_price * (1 + val / 100)).quantize(Decimal('0.01'))
            else:  # percent_decrease
                new_price = (old_price * (1 - val / 100)).quantize(Decimal('0.01'))

            if new_price <= 0:
                continue

            setattr(product, field, new_price)
            product.save(update_fields=[field])  # updated_at هو auto_now
            updated += 1

    return JsonResponse({'success': True, 'updated': updated})
