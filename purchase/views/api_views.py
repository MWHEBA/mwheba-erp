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
            'default_currency_id': supplier.default_currency_id if hasattr(supplier, 'default_currency_id') and supplier.default_currency_id else None,
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
    AJAX endpoint متكامل لإنشاء منتج مادي أو خدمة جديدة بسرعة من داخل الفواتير
    يدعم كافة إمكانيات نظام المنتجات والخدمات وتسعير الموردين وتعدد العملات
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مدعومة'}, status=405)

    from product.models import Category, Unit, Product
    from product.models.supplier_pricing import SupplierProductPrice
    from product.models.product_currency_price import ProductCurrencyPrice
    from financial.models import Currency
    from supplier.models import Supplier
    from django.db import transaction
    from decimal import Decimal
    import uuid

    name = request.POST.get('name', '').strip()
    name_en = request.POST.get('name_en', '').strip()
    category_id = request.POST.get('category')
    unit_id = request.POST.get('unit')
    
    is_service_val = request.POST.get('is_service', 'false')
    is_service = str(is_service_val).lower() in ('true', '1', 'service')
    
    sku = request.POST.get('sku', '').strip()
    barcode = request.POST.get('barcode', '').strip() if not is_service else ''
    
    cost_price_raw = request.POST.get('cost_price', '0').strip() or '0'
    selling_price_raw = request.POST.get('selling_price', '0').strip() or '0'
    tax_rate_raw = request.POST.get('tax_rate', '0').strip() or '0'
    min_stock_raw = request.POST.get('min_stock', '0').strip() or '0'
    
    item_type = request.POST.get('item_type', 'general').strip() or 'general'
    description = request.POST.get('description', '').strip()
    description_en = request.POST.get('description_en', '').strip()
    
    uniform_size = request.POST.get('uniform_size', '').strip()
    uniform_gender = request.POST.get('uniform_gender', '').strip()
    educational_subject = request.POST.get('educational_subject', '').strip()
    suitable_for_grades = request.POST.get('suitable_for_grades', '').strip()
    
    supplier_id = request.POST.get('supplier_id')
    currency_id = request.POST.get('currency_id') or request.POST.get('currency')
    exchange_rate_raw = request.POST.get('exchange_rate', '1.0').strip() or '1.0'

    if not name:
        return JsonResponse({'success': False, 'message': 'يرجى كتابة اسم الصنف'})
    if not category_id:
        return JsonResponse({'success': False, 'message': 'يرجى اختيار التصنيف'})
    if not is_service and not unit_id:
        return JsonResponse({'success': False, 'message': 'يرجى تحديد وحدة القياس للمنتجات المادية'})

    try:
        with transaction.atomic():
            category = Category.objects.get(id=category_id, is_active=True)

            # معالجة وحدة القياس للخدمات والمنتجات
            if is_service:
                if unit_id:
                    unit = Unit.objects.filter(id=unit_id, is_active=True).first()
                else:
                    unit = None
                if not unit:
                    unit, _ = Unit.objects.get_or_create(
                        name="خدمة",
                        defaults={"symbol": "خدمة", "is_active": True}
                    )
            else:
                unit = Unit.objects.get(id=unit_id, is_active=True)

            # توليد كود SKU تلقائياً إن ترك فارغاً
            if not sku:
                if is_service:
                    srv_code = category.code if (hasattr(category, 'code') and category.code) else 'SRV'
                    srv_count = Product.objects.filter(is_service=True).count() + 1
                    sku = f"{srv_code}-{srv_count:04d}"
                    while Product.objects.filter(sku=sku).exists():
                        srv_count += 1
                        sku = f"{srv_code}-{srv_count:04d}"
                else:
                    sku = Product.generate_sku(category)

            # التحقق من عدم تكرار الكود
            if Product.objects.filter(sku=sku).exists():
                sku = f"{sku}-{uuid.uuid4().hex[:4].upper()}"

            # تحويل القيم الرقمية
            cost_decimal = Decimal(cost_price_raw)
            selling_decimal = Decimal(selling_price_raw)
            tax_rate_decimal = Decimal(tax_rate_raw)
            min_stock_val = int(min_stock_raw) if not is_service else 0
            rate_decimal = Decimal(exchange_rate_raw) if Decimal(exchange_rate_raw) > 0 else Decimal('1.0')

            # معالجة العملة الاسترشادية وقيمة التكلفة بالعملة الوظيفية (IAS 21)
            currency_obj = None
            if currency_id:
                if str(currency_id).isdigit():
                    currency_obj = Currency.objects.filter(id=currency_id).first()
                else:
                    currency_obj = Currency.objects.filter(code=currency_id).first()

            is_foreign = bool(currency_obj and not currency_obj.is_functional)
            
            # إذا كان الإدخال بعملة أجنبية، يتم تحويل التكلفة والبيع للعملة الوظيفية (EGP)
            base_cost = (cost_decimal * rate_decimal) if is_foreign else cost_decimal
            base_selling = (selling_decimal * rate_decimal) if is_foreign else selling_decimal

            # المورد الافتراضي
            default_supplier_obj = None
            if supplier_id:
                default_supplier_obj = Supplier.objects.filter(id=supplier_id, is_active=True).first()

            product = Product.objects.create(
                name=name,
                name_en=name_en if name_en else None,
                category=category,
                unit=unit,
                sku=sku,
                barcode=barcode if barcode else None,
                cost_price=base_cost,
                selling_price=base_selling,
                tax_rate=tax_rate_decimal,
                min_stock=min_stock_val,
                is_service=is_service,
                is_active=True,
                item_type=item_type,
                description=description if description else None,
                description_en=description_en if description_en else None,
                uniform_size=uniform_size if uniform_size else '',
                uniform_gender=uniform_gender if uniform_gender else '',
                educational_subject=educational_subject if educational_subject else '',
                suitable_for_grades=suitable_for_grades if suitable_for_grades else '',
                default_supplier=default_supplier_obj,
                created_by=request.user,
            )

            # إنشاء سجل تسعير العملة الأجنبية إذا كانت الفاتورة بعملة أجنبية
            if is_foreign and currency_obj:
                ProductCurrencyPrice.objects.update_or_create(
                    product=product,
                    currency=currency_obj,
                    defaults={
                        'indicative_cost_price': cost_decimal,
                        'indicative_selling_price': selling_decimal,
                        'created_by': request.user,
                    }
                )

            # إنشاء سجل تسعير المورد إن وجد
            if default_supplier_obj:
                SupplierProductPrice.objects.update_or_create(
                    product=product,
                    supplier=default_supplier_obj,
                    defaults={
                        'cost_price': cost_decimal if cost_decimal > 0 else Decimal('0.01'),
                        'is_default': True,
                        'is_active': True,
                        'created_by': request.user,
                    }
                )

            item_title = "الخدمة" if product.is_service else "المنتج"
            return JsonResponse({
                'success': True,
                'message': f'تم إضافة {item_title} "{product.name}" بنجاح',
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'name_en': product.name_en or '',
                    'code': product.sku,
                    'sku': product.sku,
                    'barcode': product.barcode or '',
                    'cost_price': float(cost_decimal),
                    'selling_price': float(selling_decimal),
                    'price': float(cost_decimal),
                    'tax_rate': float(product.tax_rate or 0),
                    'stock': 0 if product.is_service else product.current_stock,
                    'is_service': product.is_service,
                    'unit_id': product.unit_id if product.unit else None,
                    'unit_name': product.unit.name if product.unit else '',
                    'category_id': product.category_id,
                    'category_name': product.category.name if product.category else '',
                    'item_type': product.item_type,
                }
            })

    except Category.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'التصنيف غير موجود أو غير نشط'})
    except Unit.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'وحدة القياس غير موجودة أو غير نشطة'})
    except Exception as e:
        logger.error(f"خطأ في إنشاء المنتج عبر AJAX: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'حدث خطأ أثناء الحفظ: {str(e)}'})


@login_required
def ajax_get_form_data(request):
    """
    AJAX endpoint لجلب التصنيفات والوحدات وخيارات الأنواع والضرائب لمودال إضافة منتج/خدمة
    التصنيفات مرتبة هرمياً: أب ثم أبناؤه
    """
    from product.models import Category, Unit, Product
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
        code_str = f" ({parent.code})" if parent.code else ""
        categories.append({
            'id': parent.id, 
            'name': parent.name + code_str, 
            'code': parent.code or '',
            'is_child': False
        })
        for child in sorted(children_map.get(parent.id, []), key=lambda x: counts.get(x.id, 0), reverse=True):
            child_code = f" ({child.code})" if child.code else ""
            categories.append({
                'id': child.id, 
                'name': child.name + child_code, 
                'code': child.code or '',
                'is_child': True
            })

    units = list(Unit.objects.filter(is_active=True).values('id', 'name', 'symbol'))
    
    item_types = [
        {'id': code, 'name': str(label)}
        for code, label in Product.ITEM_TYPES
    ]

    return JsonResponse({
        'categories': categories, 
        'units': units,
        'item_types': item_types,
    })
