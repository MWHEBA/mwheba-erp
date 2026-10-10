# -*- coding: utf-8 -*-
"""
MWHEBA ERP - Stock Allocation Service
Handles intelligent, real-time multi-warehouse stock allocation for sales lines.
"""
from decimal import Decimal
from typing import Dict, List, Optional, Any
from django.db.models import F
import logging

from product.models import Product, Warehouse, Stock

logger = logging.getLogger(__name__)


class StockAllocationService:
    """
    محرك التخصيص التخصصي الذكي للمخزون
    يتولى تحديد أفضل مخزن لكل بند مبيعات وتزويد واجهات البيع بأرصدة المخازن لحظياً
    """

    @classmethod
    def get_best_warehouse_for_product(
        cls,
        product_id: int,
        quantity: Decimal = Decimal('1.00'),
        user: Optional[Any] = None,
        preferred_warehouse_id: Optional[int] = None
    ) -> Optional[Warehouse]:
        """
        تحديد أفضل مخزن للصنف بناءً على قواعد الأولوية الذكية:
        1. المخزن المفضل / مخزن الفرع إن وُجد به رصيد كافٍ.
        2. المخزن الذي يحتوي على أعلى رصيد متاح يغطي الكمية المطلوبة.
        3. المخزن الذي يحتوي على أعلى رصيد متاح إجمالاً.
        4. أول مخزن نشط كـ Fallback في حالة نفاد الرصيد.
        """
        try:
            stocks = Stock.objects.filter(
                product_id=product_id,
                warehouse__is_active=True
            ).select_related('warehouse')

            if not stocks.exists():
                # Fallback to any active warehouse
                if preferred_warehouse_id:
                    return Warehouse.objects.filter(id=preferred_warehouse_id, is_active=True).first()
                return Warehouse.objects.filter(is_active=True).first()

            stocks_list = list(stocks)

            # 1. فحص المخزن المفضل أولاً
            if preferred_warehouse_id:
                for st in stocks_list:
                    avail = max(0, st.quantity - (st.reserved_quantity or 0))
                    if st.warehouse_id == preferred_warehouse_id and avail >= quantity:
                        return st.warehouse

            # 2. فحص المخازن التي تغطي الكمية كاملة وترتيبها بالأعلى رصيداً
            sufficient_stocks = [
                st for st in stocks_list 
                if (st.quantity - (st.reserved_quantity or 0)) >= quantity
            ]
            if sufficient_stocks:
                sufficient_stocks.sort(
                    key=lambda s: (s.quantity - (s.reserved_quantity or 0)), 
                    reverse=True
                )
                return sufficient_stocks[0].warehouse

            # 3. إذا لم يغطِ أي مخزن الكمية كاملة، نختار المخزن صاحب أعلى رصيد إيجابي
            positive_stocks = [
                st for st in stocks_list 
                if (st.quantity - (st.reserved_quantity or 0)) > 0
            ]
            if positive_stocks:
                positive_stocks.sort(
                    key=lambda s: (s.quantity - (s.reserved_quantity or 0)), 
                    reverse=True
                )
                return positive_stocks[0].warehouse

            # 4. Fallback لأول مخزن مسجل للصنف أو المخزن المفضل
            if preferred_warehouse_id:
                pref = Warehouse.objects.filter(id=preferred_warehouse_id, is_active=True).first()
                if pref:
                    return pref
            return stocks_list[0].warehouse

        except Exception as e:
            logger.error(f"Error in get_best_warehouse_for_product: {e}")
            return Warehouse.objects.filter(is_active=True).first()

    @classmethod
    def bulk_get_warehouse_stocks_for_products(
        cls,
        product_ids: List[int],
        user: Optional[Any] = None,
        preferred_warehouse_id: Optional[int] = None
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        جلب أرصدة كافة المخازن لقائمة منتجات دفعة واحدة باستعلام واحد فائق السرعة
        """
        if not product_ids:
            return {}

        all_warehouses = list(Warehouse.objects.filter(is_active=True).order_by('name'))
        stocks = Stock.objects.filter(
            product_id__in=product_ids,
            warehouse__is_active=True
        ).select_related('warehouse')

        # خريطة الأرصدة: (product_id, warehouse_id) -> stock_record
        stock_lookup: Dict[tuple, Stock] = {}
        for st in stocks:
            stock_lookup[(st.product_id, st.warehouse_id)] = st

        result: Dict[int, List[Dict[str, Any]]] = {}

        for pid in product_ids:
            wh_entries = []
            for wh in all_warehouses:
                st = stock_lookup.get((pid, wh.id))
                qty = float(st.quantity) if st else 0.0
                res_qty = float(st.reserved_quantity) if st else 0.0
                avail_qty = max(0.0, qty - res_qty)
                avg_cost = float(st.average_cost) if st and st.average_cost else 0.0

                wh_entries.append({
                    "warehouse_id": wh.id,
                    "warehouse_name": wh.name,
                    "warehouse_code": wh.code or f"WH{wh.id}",
                    "quantity": qty,
                    "reserved_quantity": res_qty,
                    "available_quantity": avail_qty,
                    "average_cost": avg_cost,
                    "is_preferred": (wh.id == preferred_warehouse_id)
                })

            # ترتيب المخازن: المخازن ذات الرصيد المتاح أولاً، ثم حسب الاسم
            wh_entries.sort(key=lambda item: (
                0 if item["is_preferred"] and item["available_quantity"] > 0 else (
                    1 if item["available_quantity"] > 0 else 2
                ),
                -item["available_quantity"],
                item["warehouse_name"]
            ))

            result[pid] = wh_entries

        return result
