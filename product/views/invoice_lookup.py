# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.db import models
from ..models import Product, Stock
import logging

logger = logging.getLogger(__name__)


class ProductPriceSource(models.TextChoices):
    PRODUCT_CURRENCY_PRICE = "PRODUCT_CURRENCY_PRICE", "سعر استرشادي معتمد بالعملة"
    NEW_PRICE = "NEW_PRICE", "سعر جديد غير معرّف"
    BASE_CONVERTED = "BASE_CONVERTED", "سعر استرشادي محول"


@login_required
def invoice_product_lookup(request):
    """
    API للبحث الفوري عن المنتجات باستخدام الكود أو الباركود أو الاسم
    محدث لدعم فلترة وترتيب وتحديد مصدر الأسعار بالعملات المخصصة
    """
    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse_id") or request.GET.get("warehouse")
    product_type = request.GET.get("type", "sale") # sale, purchase, service, products, services
    exact = request.GET.get("exact", "false") == "true"
    invoice_id = request.GET.get("invoice_id")
    product_ids = request.GET.get("product_ids")
    currency_id = request.GET.get("currency_id") or request.GET.get("currency")

    if exact and not query and not product_ids:
        return JsonResponse({"products": []})

    try:
        # تحديد العملة وإن كانت عملة محلية أم أجنبية
        currency_obj = None
        if currency_id:
            try:
                from financial.models import Currency
                if str(currency_id).isdigit():
                    currency_obj = Currency.objects.filter(id=currency_id).first()
                else:
                    currency_obj = Currency.objects.filter(code=currency_id).first()
            except Exception:
                currency_obj = None

        # 1. فلترة المنتجات الأساسية
        if product_type in ["service", "services"]:
            qs = Product.objects.filter(is_service=True)
        elif product_type in ["products"]:
            qs = Product.objects.filter(is_service=False, is_bundle=False)
        elif product_type == "purchase":
            from core.models import SystemSetting
            allowed_types = SystemSetting.get_setting('purchase_invoice_item_types', 'both')
            if allowed_types == 'products':
                qs = Product.objects.filter(is_service=False, is_bundle=False)
            elif allowed_types == 'services':
                qs = Product.objects.filter(is_service=True)
            else: # both
                qs = Product.objects.filter(is_bundle=False)
        else: # sale / all
            from core.models import SystemSetting
            allowed_types = SystemSetting.get_setting('sale_invoice_item_types', 'both')
            if allowed_types == 'products':
                qs = Product.objects.filter(is_service=False, is_bundle=False)
            elif allowed_types == 'services':
                qs = Product.objects.filter(is_service=True)
            else: # both
                qs = Product.objects.filter(is_bundle=False)

        # 2. تصفية المنتجات غير النشطة إلا لو كانت مضافة للفاتورة الحالية الجاري تعديلها
        active_filter = Q(is_active=True)
        if invoice_id and invoice_id != "0":
            item_product_ids = []
            if product_type == "purchase":
                try:
                    from purchase.models import PurchaseItem
                    item_product_ids = list(PurchaseItem.objects.filter(purchase_id=invoice_id).values_list("product_id", flat=True))
                except ImportError:
                    pass
            else:
                try:
                    from sale.models import SaleItem
                    item_product_ids = list(SaleItem.objects.filter(sale_id=invoice_id).values_list("product_id", flat=True))
                except ImportError:
                    pass
                try:
                    from sale.models import QuotationItem
                    quot_ids = list(QuotationItem.objects.filter(quotation_id=invoice_id).values_list("product_id", flat=True))
                    item_product_ids.extend(quot_ids)
                except ImportError:
                    pass
            
            if item_product_ids:
                active_filter |= Q(id__in=item_product_ids)

        qs = qs.filter(active_filter)

        # 3. مطابقة الكود/الباركود/الاسم أو تصفية بأرقام تعريف معينة
        if product_ids:
            ids = [int(x) for x in product_ids.split(",") if x.isdigit()]
            qs = qs.filter(id__in=ids)
        elif exact:
            qs = qs.filter(Q(sku__iexact=query) | Q(barcode__iexact=query))
        elif query:
            qs = qs.filter(
                Q(name__icontains=query) |
                Q(name_en__icontains=query) |
                Q(sku__icontains=query) |
                Q(barcode__icontains=query)
            )

        # 4. جلب كميات المخزون
        stock_map = {}
        if warehouse_id:
            stocks = Stock.objects.filter(
                warehouse_id=warehouse_id,
                product__in=qs
            ).values("product_id", "quantity")
            stock_map = {str(s["product_id"]): float(s["quantity"]) for s in stocks}
        else:
            stocks = Stock.objects.filter(
                product__in=qs,
                warehouse__is_active=True
            ).values("product_id").annotate(total_qty=Sum("quantity"))
            stock_map = {str(s["product_id"]): float(s["total_qty"] or 0) for s in stocks}

        # 5. بناء الاستجابة بحد أقصى 50 نتيجة للبحث السريع
        show_all_param = request.GET.get("show_all", "false") == "true"
        show_all = show_all_param or exact or product_ids or (product_type in ["service", "services", "purchase"])
        
        # Prefetch currency prices for efficiency
        qs = qs.prefetch_related('currency_prices__currency')

        raw_results = []
        is_foreign = (currency_obj and not currency_obj.is_functional)
        curr_code = currency_obj.code if currency_obj else None

        for p in qs.select_related('category', 'unit').order_by("name"):
            stock_qty = stock_map.get(str(p.id), 0.0)
            if not show_all and stock_qty <= 0 and not p.is_service:
                continue

            curr_prices = p.get_currency_prices_dict()
            selling_p = float(p.selling_price) if p.selling_price else 0.0
            cost_p = float(p.cost_price) if p.cost_price else 0.0
            price_source = ProductPriceSource.PRODUCT_CURRENCY_PRICE.value
            display_price = selling_p if product_type != "purchase" else cost_p

            if is_foreign and curr_code:
                cp_data = curr_prices.get(curr_code)
                price_key = "selling" if product_type != "purchase" else "cost"
                explicit_val = cp_data.get(price_key) if cp_data else None
                if explicit_val is not None and float(explicit_val) > 0:
                    display_price = float(explicit_val)
                    price_source = ProductPriceSource.PRODUCT_CURRENCY_PRICE.value
                else:
                    display_price = 0.0
                    price_source = ProductPriceSource.NEW_PRICE.value

            raw_results.append({
                "id": p.id,
                "name": p.name,
                "name_en": p.name_en or "",
                "description": p.description or "",
                "description_en": p.description_en or "",
                "code": p.sku,
                "barcode": p.barcode,
                "selling_price": display_price if product_type != "purchase" else selling_p,
                "cost_price": display_price if product_type == "purchase" else cost_p,
                "currency_prices": curr_prices,
                "stock": stock_qty,
                "is_service": p.is_service,
                "unit_name": p.unit.name if p.unit else "",
                "unit_name_en": (p.unit.name_en if p.unit and p.unit.name_en else p.unit.name) if p.unit else "",
                "category_id": p.category_id,
                "category_name": p.category.name if p.category else "",
                "category_name_en": p.category.name_en if p.category and p.category.name_en else "",
                "price_source": price_source,
                "has_currency_price": (price_source == ProductPriceSource.PRODUCT_CURRENCY_PRICE.value),
            })

        # ترتيب النتائج: المنتجات المسعرة بالعملة أولاً، ثم المنتجات غير المسعرة ثانياً
        if is_foreign:
            raw_results.sort(key=lambda x: (0 if x["has_currency_price"] else 1, x["name"]))

        results = raw_results[:50]
        return JsonResponse({"products": results, "is_foreign": is_foreign})

    except Exception as e:
        logger.error(f"Error in invoice product lookup API: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
