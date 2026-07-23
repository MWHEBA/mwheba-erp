# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Sum
from ..models import Product, Stock
import logging

logger = logging.getLogger(__name__)

@login_required
def invoice_product_lookup(request):
    """
    API للبحث الفوري عن المنتجات باستخدام الكود أو الباركود أو الاسم
    """
    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse_id") or request.GET.get("warehouse")
    product_type = request.GET.get("type", "sale") # sale, purchase, service, products, services
    exact = request.GET.get("exact", "false") == "true"
    invoice_id = request.GET.get("invoice_id")
    product_ids = request.GET.get("product_ids")

    if exact and not query and not product_ids:
        return JsonResponse({"products": []})

    try:
        # 1. فلترة المنتجات الأساسية
        if product_type in ["service", "services"]:
            qs = Product.objects.filter(is_service=True)
        elif product_type in ["purchase", "products"]:
            qs = Product.objects.filter(is_service=False, is_bundle=False)
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
        
        results = []
        for p in qs.select_related('category').order_by("name"):
            stock_qty = stock_map.get(str(p.id), 0.0)
            if not show_all and stock_qty <= 0:
                continue
                
            results.append({
                "id": p.id,
                "name": p.name,
                "code": p.sku,
                "barcode": p.barcode,
                "selling_price": float(p.selling_price) if p.selling_price else 0.0,
                "cost_price": float(p.cost_price) if p.cost_price else 0.0,
                "stock": stock_qty,
                "is_service": p.is_service,
                "category_id": p.category_id,
                "category_name": p.category.name if p.category else "",
            })
            if len(results) >= 50:
                break

        return JsonResponse({"products": results})

    except Exception as e:
        logger.error(f"Error in invoice product lookup API: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
