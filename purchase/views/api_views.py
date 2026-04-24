"""
Purchase API Views
API endpoints للمشتريات
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import logging

from supplier.models import Supplier
from product.models import Product

logger = logging.getLogger(__name__)


@login_required
def get_supplier_type_api(request, supplier_id):
    """
    API للحصول على نوع المورد وفلترة المنتجات
    Get supplier type and filter products accordingly
    """
    try:
        supplier = Supplier.objects.select_related('primary_type', 'primary_type__settings').get(
            id=supplier_id, 
            is_active=True
        )
        
        # استخدام الـ method الموجود في الـ model - Single Source of Truth
        is_service = supplier.is_service_provider()
        
        # جلب المنتجات/الخدمات المناسبة
        products = Product.objects.filter(
            is_active=True,
            is_service=is_service
        ).values('id', 'name', 'sku', 'cost_price', 'selling_price')
        
        # جلب التصنيفات المالية المناسبة لنوع المورد
        financial_categories = []
        try:
            from financial.models import FinancialCategory
            if is_service:
                # موردين خدميين: خدمات + مصروفات إدارية + تسويق + رواتب + متنوعة
                service_codes = ['services', 'administrative', 'marketing', 'salaries', 'insurance', 'taxes', 'other_expense']
                cats = FinancialCategory.objects.filter(
                    is_active=True,
                    default_expense_account__isnull=False,
                    code__in=service_codes
                ).order_by('display_order', 'name')
            else:
                # موردين منتجات: منتجات فقط
                cats = FinancialCategory.objects.filter(
                    is_active=True,
                    default_expense_account__isnull=False,
                    code='products'
                ).order_by('display_order', 'name')
            
            for cat in cats:
                financial_categories.append({'value': f'cat_{cat.pk}', 'label': f'📁 {cat.name}'})
                for subcat in cat.subcategories.filter(is_active=True).order_by('display_order', 'name'):
                    financial_categories.append({'value': f'sub_{subcat.pk}', 'label': f'   ↳ {subcat.name}'})
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'is_service_provider': is_service,
            'requires_warehouse': not is_service,
            'supplier_type_code': supplier.get_primary_type_code() or 'general',
            'products': list(products),
            'financial_categories': financial_categories,
        })
    except Supplier.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'message': 'المورد غير موجود'
        }, status=404)
    except Exception as e:
        logger.error(f"خطأ في API نوع المورد للمورد {supplier_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'حدث خطأ في جلب بيانات المورد'
        }, status=500)


@login_required
def ajax_create_product(request):
    """
    AJAX endpoint لإنشاء منتج جديد بسرعة من داخل فاتورة الشراء
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مدعومة'}, status=405)

    from product.models import Category, Unit
    from decimal import Decimal
    import uuid

    name = request.POST.get('name', '').strip()
    category_id = request.POST.get('category')
    unit_id = request.POST.get('unit')
    cost_price = request.POST.get('cost_price', '0')
    selling_price = request.POST.get('selling_price', '0')
    is_service = request.POST.get('is_service', 'false') == 'true'

    if not name or not category_id or not unit_id:
        return JsonResponse({'success': False, 'message': 'الاسم والتصنيف والوحدة مطلوبة'})

    try:
        category = Category.objects.get(id=category_id, is_active=True)
        unit = Unit.objects.get(id=unit_id, is_active=True)

        sku = f"PRD-{uuid.uuid4().hex[:8].upper()}"

        product = Product.objects.create(
            name=name,
            category=category,
            unit=unit,
            cost_price=Decimal(cost_price or '0'),
            selling_price=Decimal(selling_price or '0'),
            is_service=is_service,
            is_active=True,
            sku=sku,
            created_by=request.user,
        )

        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'cost_price': float(product.cost_price),
                'selling_price': float(product.selling_price),
                'sku': product.sku,
                'category_id': product.category_id,
                'category_name': product.category.name,
            }
        })

    except (Category.DoesNotExist, Unit.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'التصنيف أو الوحدة غير موجودة'})
    except Exception as e:
        logger.error(f"خطأ في إنشاء المنتج عبر AJAX: {str(e)}")
        return JsonResponse({'success': False, 'message': f'حدث خطأ: {str(e)}'})


@login_required
def ajax_get_form_data(request):
    """
    AJAX endpoint لجلب التصنيفات والوحدات لمودال إضافة منتج
    التصنيفات مرتبة هرمياً: أب ثم أبناؤه تنازلياً حسب عدد المنتجات
    """
    from product.models import Category, Unit
    from django.db.models import Count

    counts = {
        row['id']: row['total']
        for row in Category.objects.annotate(total=Count('products')).values('id', 'total')
    }

    all_cats = list(
        Category.objects.filter(is_active=True)
        .select_related('parent')
        .order_by('name')
    )
    parents = [c for c in all_cats if c.parent_id is None]
    children_map = {}
    for c in all_cats:
        if c.parent_id is not None:
            children_map.setdefault(c.parent_id, []).append(c)

    parents.sort(key=lambda x: counts.get(x.id, 0), reverse=True)

    categories = []
    for parent in parents:
        categories.append({'id': parent.id, 'name': parent.name, 'is_child': False})
        for child in sorted(children_map.get(parent.id, []), key=lambda x: counts.get(x.id, 0), reverse=True):
            categories.append({'id': child.id, 'name': child.name, 'is_child': True})

    units = list(Unit.objects.filter(is_active=True).values('id', 'name', 'symbol'))

    return JsonResponse({'categories': categories, 'units': units})
