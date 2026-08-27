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
    API للبحث الفوري عن المنتجات والمتغيرات باستخدام الكود أو الباركود أو الاسم
    محدث لدعم فلترة وترتيب وتحديد مصدر الأسعار بالعملات المخصصة، وباركود المتغيرات، وآخر سعر شراء للمورد (LPP)
    """
    from ..models import ProductVariant

    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse_id") or request.GET.get("warehouse")
    product_type = request.GET.get("type", "sale") # sale, purchase, service, products, services
    exact = request.GET.get("exact", "false") == "true"
    invoice_id = request.GET.get("invoice_id")
    product_ids = request.GET.get("product_ids")
    currency_id = request.GET.get("currency_id") or request.GET.get("currency")
    supplier_id = request.GET.get("supplier_id") or request.GET.get("supplier")
    customer_id = request.GET.get("customer_id") or request.GET.get("customer")
    price_list_id = request.GET.get("price_list_id") or request.GET.get("price_list")

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

        # 2. تصفية المنتجات غير النشطة إلا لو كانت مضافة للفاتورة/أمر الشراء الحالي الجاري تعديله
        active_filter = Q(is_active=True)
        if invoice_id and invoice_id != "0":
            item_product_ids = []
            if product_type == "purchase":
                try:
                    from purchase.models import PurchaseItem
                    item_product_ids.extend(list(PurchaseItem.objects.filter(purchase_id=invoice_id).values_list("product_id", flat=True)))
                except Exception:
                    pass
                try:
                    from purchase.models.procurement_models import PurchaseOrderItem
                    item_product_ids.extend(list(PurchaseOrderItem.objects.filter(purchase_order_id=invoice_id).values_list("product_id", flat=True)))
                except Exception:
                    pass
            else:
                try:
                    from sale.models import SaleItem
                    item_product_ids.extend(list(SaleItem.objects.filter(sale_id=invoice_id).values_list("product_id", flat=True)))
                except Exception:
                    pass
                try:
                    from sale.models import QuotationItem
                    quot_ids = list(QuotationItem.objects.filter(quotation_id=invoice_id).values_list("product_id", flat=True))
                    item_product_ids.extend(quot_ids)
                except Exception:
                    pass
            
            if item_product_ids:
                active_filter |= Q(id__in=item_product_ids)

        qs = qs.filter(active_filter)

        # 3. مطابقة الكود/الباركود/الاسم بما يشمل باركودات المتغيرات (ProductVariant)
        variant_matches = {}
        matched_variant_product_ids = set()

        if query:
            from utils.search import build_smart_search_query
            # البحث في المتغيرات
            v_qs = ProductVariant.objects.filter(is_active=True)
            if exact:
                v_qs = v_qs.filter(Q(sku__iexact=query) | Q(barcode__iexact=query))
            else:
                v_query = build_smart_search_query(query, text_fields=["name"], code_fields=["sku", "barcode"])
                v_qs = v_qs.filter(v_query)
            
            for v in v_qs.select_related("product")[:20]:
                variant_matches[v.id] = v
                matched_variant_product_ids.add(v.product_id)

        if product_ids:
            ids = [int(x) for x in product_ids.split(",") if x.isdigit()]
            qs = qs.filter(id__in=ids)
        elif exact:
            qs = qs.filter(Q(sku__iexact=query) | Q(barcode__iexact=query) | Q(id__in=matched_variant_product_ids))
        elif query:
            from utils.search import build_smart_search_query
            prod_query = build_smart_search_query(query, text_fields=["name", "name_en", "description"], code_fields=["sku", "barcode"])
            if matched_variant_product_ids:
                prod_query |= Q(id__in=matched_variant_product_ids)
            qs = qs.filter(prod_query)

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

        # 5. جلب آخر سعر شراء للمورد (Supplier Last Purchase Price - LPP) بـ Subquery مجمعة واحدة
        supplier_lpp_map = {}
        if supplier_id and product_type == "purchase":
            try:
                from purchase.models import PurchaseItem
                from purchase.models.procurement_models import PurchaseOrderItem

                # آخر أسعار فواتير الشراء
                pi_prices = (
                    PurchaseItem.objects.filter(purchase__supplier_id=supplier_id, product__in=qs)
                    .order_by("product_id", "-purchase__date", "-id")
                    .values("product_id", "unit_price")
                )
                for row in pi_prices:
                    p_id = str(row["product_id"])
                    if p_id not in supplier_lpp_map:
                        supplier_lpp_map[p_id] = float(row["unit_price"])

                # آخر أسعار أوامر الشراء
                po_prices = (
                    PurchaseOrderItem.objects.filter(purchase_order__supplier_id=supplier_id, product__in=qs)
                    .order_by("product_id", "-purchase_order__order_date", "-id")
                    .values("product_id", "unit_price")
                )
                for row in po_prices:
                    p_id = str(row["product_id"])
                    if p_id not in supplier_lpp_map:
                        supplier_lpp_map[p_id] = float(row["unit_price"])
            except Exception as e:
                logger.warning(f"Failed to fetch supplier LPP: {e}")

        # 6. بناء الاستجابة بحد أقصى 50 نتيجة
        show_all_param = request.GET.get("show_all", "false") == "true"
        show_all = show_all_param or exact or product_ids or (product_type in ["service", "services", "purchase"])
        
        # Prefetch currency prices and variants for efficiency
        qs = qs.prefetch_related('currency_prices__currency', 'variants').select_related('category', 'unit', 'tax_code')

        # تجهيز كاش التسعير للطلبات غير الشرائية
        pricing_cache = None
        if product_type != "purchase":
            try:
                from sale.services.pricing_service import PricingService
                c_id_int = int(customer_id) if (customer_id and str(customer_id).isdigit()) else None
                pl_id_int = int(price_list_id) if (price_list_id and str(price_list_id).isdigit()) else None
                pricing_cache = PricingService.get_pricing_context_cache(customer_id=c_id_int, price_list_id=pl_id_int)
            except Exception as e:
                logger.warning(f"Failed to build pricing cache in lookup: {e}")

        raw_results = []
        is_foreign = (currency_obj and not currency_obj.is_functional)
        curr_code = currency_obj.code if currency_obj else None

        for p in qs.order_by("name"):
            stock_qty = stock_map.get(str(p.id), 0.0)
            if not show_all and stock_qty <= 0 and not p.is_service:
                continue

            curr_prices = p.get_currency_prices_dict()
            selling_p = float(p.selling_price) if p.selling_price else 0.0
            cost_p = float(p.cost_price) if p.cost_price else 0.0
            discount_amount = 0.0
            discount_percentage = 0.0
            rule_name = ""
            rule_id = None
            is_below_cost = False
            price_snapshot = {}

            # تطبيق محرك التسعير المركزي للمبيعات
            if product_type != "purchase" and pricing_cache:
                try:
                    p_info = PricingService.get_sales_price(
                        product_id=p.id,
                        customer_id=c_id_int,
                        price_list_id=pl_id_int,
                        currency=curr_code or "EGP",
                        context_cache=pricing_cache
                    )
                    selling_p = float(p_info["base_price"])
                    discount_amount = float(p_info["discount_amount"])
                    discount_percentage = float(p_info["discount_percentage"])
                    rule_name = p_info["rule_name"]
                    rule_id = p_info["rule_id"]
                    is_below_cost = p_info["is_below_cost"]
                    price_snapshot = p_info["price_snapshot"]
                except Exception as ex:
                    logger.debug(f"PricingService fallback for product {p.id}: {ex}")

            # تطبيق سعر المورد الأخير إن وجد
            if product_type == "purchase" and str(p.id) in supplier_lpp_map:
                cost_p = supplier_lpp_map[str(p.id)]

            price_source = ProductPriceSource.PRODUCT_CURRENCY_PRICE.value
            display_price = selling_p if product_type != "purchase" else cost_p

            if is_foreign and curr_code and (product_type == "purchase" or not pricing_cache or not pricing_cache.get("price_list_id")):
                cp_data = curr_prices.get(curr_code)
                price_key = "selling" if product_type != "purchase" else "cost"
                explicit_val = cp_data.get(price_key) if cp_data else None
                if explicit_val is not None and float(explicit_val) > 0:
                    display_price = float(explicit_val)
                    price_source = ProductPriceSource.PRODUCT_CURRENCY_PRICE.value
                else:
                    display_price = 0.0
                    price_source = ProductPriceSource.NEW_PRICE.value

            # تجهيز قائمة المتغيرات المرتبطة
            variants_data = []
            for v in p.variants.filter(is_active=True):
                v_cost = float(v.cost_price) if v.cost_price else cost_p
                v_sell = float(v.selling_price) if v.selling_price else selling_p
                variants_data.append({
                    "id": v.id,
                    "name": v.name,
                    "sku": v.sku,
                    "barcode": v.barcode or "",
                    "cost_price": v_cost,
                    "selling_price": v_sell,
                    "stock": getattr(v, "stock", 0)
                })

            effective_tax = float(getattr(p, "effective_tax_rate", 14.0) or 0.0)
            is_exempt = bool(getattr(p, "is_tax_exempt", False))

            base_item = {
                "id": p.id,
                "name": p.name,
                "name_en": p.name_en or "",
                "description": p.description or "",
                "description_en": p.description_en or "",
                "code": p.sku,
                "barcode": p.barcode or "",
                "selling_price": display_price if product_type != "purchase" else selling_p,
                "cost_price": display_price if product_type == "purchase" else cost_p,
                "discount_amount": discount_amount,
                "discount_percentage": discount_percentage,
                "rule_name": rule_name,
                "rule_id": rule_id,
                "is_below_cost": is_below_cost,
                "price_snapshot": price_snapshot,
                "currency_prices": curr_prices,
                "stock": stock_qty,
                "is_service": p.is_service,
                "tax_rate": effective_tax,
                "tax_code": p.tax_code.code if p.tax_code else "",
                "is_taxable": (not is_exempt) and (effective_tax > 0),
                "is_tax_exempt": is_exempt,
                "unit_id": p.unit_id if p.unit else None,
                "unit_name": p.unit.name if p.unit else "",
                "unit_symbol": p.unit.symbol if p.unit and hasattr(p.unit, 'symbol') else (p.unit.name if p.unit else ""),
                "unit_name_en": (p.unit.name_en if p.unit and p.unit.name_en else p.unit.name) if p.unit else "",
                "category_id": p.category_id,
                "category_name": p.category.name if p.category else "",
                "category_name_en": p.category.name_en if p.category and p.category.name_en else "",
                "reorder_point": getattr(p, "reorder_point", 0) or 0,
                "price_source": price_source,
                "has_currency_price": (price_source == ProductPriceSource.PRODUCT_CURRENCY_PRICE.value),
                "variants": variants_data,
                "has_variants": bool(variants_data),
            }

            # إذا كانت هناك متغيرات مطابقة خصيصاً بالباركود/الكود، نضيف كرت المتغير كبند محدد
            matched_v_for_p = [v for v in variant_matches.values() if v.product_id == p.id]
            if matched_v_for_p and (exact or query):
                for mv in matched_v_for_p:
                    mv_cost = float(mv.cost_price) if mv.cost_price else cost_p
                    mv_sell = float(mv.selling_price) if mv.selling_price else selling_p
                    v_item = dict(base_item)
                    v_item["name"] = f"{p.name} - {mv.name}"
                    v_item["variant_id"] = mv.id
                    v_item["variant_name"] = mv.name
                    v_item["code"] = mv.sku
                    v_item["barcode"] = mv.barcode or ""
                    v_item["cost_price"] = mv_cost if product_type == "purchase" else base_item["cost_price"]
                    v_item["selling_price"] = mv_sell if product_type != "purchase" else base_item["selling_price"]
                    raw_results.append(v_item)

            raw_results.append(base_item)

        # ترتيب النتائج: المنتجات المسعرة بالعملة أولاً، ثم المنتجات غير المسعرة ثانياً
        if is_foreign:
            raw_results.sort(key=lambda x: (0 if x.get("has_currency_price") else 1, x["name"]))

        results = raw_results[:50]
        return JsonResponse({"products": results, "is_foreign": is_foreign})

    except Exception as e:
        logger.error(f"Error in invoice product lookup API: {str(e)}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)
