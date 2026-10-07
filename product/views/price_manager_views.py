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
from users.decorators import require_permission


@login_required
@require_permission('product.view_product')
def price_manager(request):
    """
    واجهة مدير الأسعار — مفلترة بالتصنيف
    type=product  → من صفحة المنتجات
    type=service  → من صفحة الخدمات
    """
    if not getattr(request.user, 'can_view_selling_price', True):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("ليس لديك صلاحية للوصول إلى مدير الأسعار.")

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
    else:
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        else:
            qs = Product.objects.none()

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(qs, request, default_per_page=50)
    items = pagination_context["page_obj"]

    back_url = reverse('product:service_list') if is_service else reverse('product:product_list')
    title    = 'تحديث أسعار الخدمات' if is_service else 'تحديث أسعار المنتجات'

    context = {
        'title': title,
        'items': items,
        'page_obj': items,
        **pagination_context,
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
            context,
            request=request,
        )
        return JsonResponse({'table_html': table_html, 'pagination_html': pagination_html})

    return render(request, 'product/price_manager.html', context)


@login_required
@require_POST
def price_manager_update_api(request):
    """
    تحديث سعر منتج/خدمة واحدة — يُستدعى عند تغيير الخلية (onchange)
    يشترط الصلاحية الاستراتيجية لتعديل المنتجات product.change_product
    """
    can_change_price = (
        (
            request.user.is_superuser
            or request.user.has_perm('product.change_product')
            or getattr(request.user, 'is_financial_manager', False)
        )
        and getattr(request.user, 'can_view_selling_price', True)
    )
    if not can_change_price:
        return JsonResponse({'success': False, 'error': 'غير مصرح لك بتعديل الأسعار الأساسية لكتالوج الأصناف'}, status=403)

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

    with transaction.atomic():
        setattr(product, field, new_val)
        product.save(update_fields=[field])  # updated_at هو auto_now — Django يتعامل معه تلقائياً

        # تسجيل حركة التغير في سجل تاريخ الأسعار الموحد PriceHistory
        if field in ('cost_price', 'selling_price'):
            from product.services.pricing_service import PricingService
            PricingService.log_price_change(
                product=product,
                old_price=old_val,
                new_price=new_val,
                source_type="CATALOG_BASE",
                change_reason="manual_update",
                notes=f"تحديث {field} من مدير الأسعار",
                user=request.user,
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
    يشترط الصلاحية الاستراتيجية لتعديل المنتجات product.change_product
    """
    can_change_price = (
        (
            request.user.is_superuser
            or request.user.has_perm('product.change_product')
            or getattr(request.user, 'is_financial_manager', False)
        )
        and getattr(request.user, 'can_view_selling_price', True)
    )
    if not can_change_price:
        return JsonResponse({'success': False, 'error': 'غير مصرح لك بتعديل الأسعار الأساسية لكتالوج الأصناف'}, status=403)

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

    products = Product.objects.filter(pk__in=product_ids).select_related('pricing_currency')
    updated  = 0

    from product.services.pricing_service import PricingService
    from product.models.product_currency_price import ProductCurrencyPrice
    from financial.services.exchange_rate_service import ExchangeRateService

    with transaction.atomic():
        for product in products:
            old_price = getattr(product, field)
            
            # إذا كان الصنف مسعراً بالعملة الأجنبية
            if product.is_foreign_currency_priced and product.pricing_currency:
                cp = ProductCurrencyPrice.objects.filter(product=product, currency=product.pricing_currency).first()
                curr_rate = Decimal(str(ExchangeRateService.get_exchange_rate(product.pricing_currency) or 1.0))

                if cp:
                    target_foreign_field = "indicative_selling_price" if field == "selling_price" else "indicative_cost_price"
                    old_foreign = getattr(cp, target_foreign_field) or Decimal("0.00")
                    
                    if mode == 'fixed':
                        new_foreign = val
                    elif mode == 'percent_increase':
                        new_foreign = (old_foreign * (1 + val / 100)).quantize(Decimal('0.01'))
                    else:
                        new_foreign = (old_foreign * (1 - val / 100)).quantize(Decimal('0.01'))

                    if new_foreign <= 0:
                        continue

                    setattr(cp, target_foreign_field, new_foreign)
                    cp.updated_by = request.user
                    cp.save()

                    # المعادل بالجنيه بعد تطبيق نسبة التعديل
                    new_price = (new_foreign * curr_rate).quantize(Decimal('0.01'))
                else:
                    if mode == 'fixed':
                        new_price = val
                    elif mode == 'percent_increase':
                        new_price = (old_price * (1 + val / 100)).quantize(Decimal('0.01'))
                    else:  # percent_decrease
                        new_price = (old_price * (1 - val / 100)).quantize(Decimal('0.01'))
            else:
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
            
            PricingService.log_price_change(
                product=product,
                old_price=old_price,
                new_price=new_price,
                currency=product.pricing_currency if product.is_foreign_currency_priced else None,
                source_type="CATALOG_FX" if product.is_foreign_currency_priced else "CATALOG_BASE",
                change_reason="bulk_update",
                notes=f"تحديث جماعي ({mode}) لـ {field} بقيمة {val}",
                user=request.user,
            )
            updated += 1

    return JsonResponse({'success': True, 'updated': updated})
