"""
InventoryValuationService - محرك تقييم المخزون وحساب تكلفة البضاعة المباعة FIFO & AVCO (FIN-INV-001 & FIN-INV-004)
يتولى إدارة طبقات التكلفة واستهلاك التكلفة FIFO وحسابات المتوسط المتحرك وتتبع الاستهلاك
"""

import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from product.models.product_core import Product
from product.models.stock_management import Warehouse, Stock
from product.models.stock_ledger import StockLedgerEntry
from product.models.cost_layer import InventoryCostLayer, InventoryCostConsumption
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("product.valuation_service")


class InventoryValuationService:
    """
    محرك التقييم المحاسبي للمخزون (FIFO / AVCO Costing Engine)
    """

    @classmethod
    def generate_consumption_number(cls) -> str:
        date_prefix = timezone.now().strftime("%Y%m%d")
        unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
        return f"COST-CONS-{date_prefix}-{unique_suffix}"

    @classmethod
    def create_receipt_cost_layer(
        cls,
        product: Product,
        warehouse: Warehouse,
        stock_ledger_entry: StockLedgerEntry,
        quantity: Decimal,
        unit_cost: Decimal,
        receipt_date: Optional[Any] = None
    ) -> InventoryCostLayer:
        """
        إنشاء طبقة تكلفة جديدة للوارد الفعلي (FIFO Physical Receipt Layer)
        ملاحظة حوكمة: يتم إنشاء طبقة التكلفة عند الاستلام الفعلي للمخزن (Physical Receipt) وليس عند فاتورة المورد (Supplier Invoice).
        """
        with transaction.atomic():
            layer = InventoryCostLayer.objects.create(
                product=product,
                warehouse=warehouse,
                receipt_date=receipt_date or timezone.now(),
                stock_ledger_entry=stock_ledger_entry,
                original_qty=quantity,
                remaining_qty=quantity,
                unit_cost=unit_cost,
                status="OPEN"
            )

            # تحديث المتوسط المتحرك على مستوى نموذج Stock (AVCO Update)
            cls.update_moving_average_cost(product, warehouse, quantity, unit_cost)

            logger.info(f"InventoryCostLayer created: #{layer.id} for Product#{product.id} ({quantity} @ {unit_cost})")
            return layer

    @classmethod
    def update_moving_average_cost(
        cls,
        product: Product,
        warehouse: Warehouse,
        received_qty: Decimal,
        received_unit_cost: Decimal
    ) -> Decimal:
        """
        تحديث المتوسط المتحرك للتكلفة عند استلام شحنة جديدة (AVCO Formula)
        New Cost = (Current Qty * Current Cost + Received Qty * Received Cost) / (Current Qty + Received Qty)
        """
        stock_obj, _ = Stock.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={"quantity": Decimal('0.00'), "average_cost": Decimal('0.00')}
        )

        current_qty = stock_obj.quantity
        current_avg_cost = getattr(stock_obj, 'average_cost', Decimal('0.00')) or Decimal('0.00')

        new_total_qty = current_qty + received_qty
        if new_total_qty <= Decimal('0.0000'):
            new_avg_cost = received_unit_cost
        else:
            current_total_val = current_qty * current_avg_cost
            received_total_val = received_qty * received_unit_cost
            new_avg_cost = ((current_total_val + received_total_val) / new_total_qty).quantize(Decimal('0.0001'))

        stock_obj.quantity = new_total_qty
        if hasattr(stock_obj, 'average_cost'):
            stock_obj.average_cost = new_avg_cost
        stock_obj.save()

        return new_avg_cost

    @classmethod
    def get_valuation_method(cls, product: Product) -> str:
        """
        تحديد طريقة التقييم المحاسبي الفعالة للمنتج وفق التدرج الهرمي (FIN-INV-013)
        Hierarchy: Product Override -> Category Policy -> System Default ('FIFO')
        """
        if hasattr(product, 'get_effective_valuation_method'):
            return product.get_effective_valuation_method()
        return getattr(product, 'valuation_method', 'FIFO') or 'FIFO'

    @classmethod
    def get_valuation_control_report(
        cls,
        product: Optional[Product] = None,
        warehouse: Optional[Warehouse] = None
    ) -> Dict[str, Any]:
        """
        تقرير الرقابة والتحكم لتقييم المخزون الموحد (FIN-INV-010)
        يجمع بين طبقات التكلفة، وأرصدة الأستاذ، وتسويات التقييم والمطابقة المالي
        """
        from product.models.valuation_adjustment import InventoryValuationAdjustment
        from product.services.inventory_reconciliation_service import InventoryReconciliationService

        layers_qs = InventoryCostLayer.objects.filter(status="OPEN")
        if product:
            layers_qs = layers_qs.filter(product=product)
        if warehouse:
            layers_qs = layers_qs.filter(warehouse=warehouse)

        total_active_layer_qty = Decimal("0.0000")
        total_active_layer_valuation = Decimal("0.00")

        for layer in layers_qs:
            total_active_layer_qty += layer.remaining_qty
            total_active_layer_valuation += (layer.remaining_qty * layer.unit_cost).quantize(Decimal("0.01"))

        adjustments_qs = InventoryValuationAdjustment.objects.all()
        if product:
            adjustments_qs = adjustments_qs.filter(product=product)
        if warehouse:
            adjustments_qs = adjustments_qs.filter(warehouse=warehouse)

        total_adjustment_cost = adjustments_qs.aggregate(total=Sum("cost_adjusted"))["total"] or Decimal("0.00")

        recon_res = InventoryReconciliationService.reconcile_inventory_control_account(account_code="11040_INV")

        return {
            "total_active_layer_qty": total_active_layer_qty,
            "total_active_layer_valuation": total_active_layer_valuation,
            "total_valuation_adjustments": total_adjustment_cost,
            "gl_reconciliation": recon_res
        }

    @classmethod
    def process_sales_return(
        cls,
        product: Product,
        warehouse: Warehouse,
        return_quantity: Decimal,
        original_issue_ledger_entry: StockLedgerEntry
    ) -> InventoryCostLayer:
        """
        معالجة مرتجع المبيعات وتتبع التكلفة التاريخية الأصلية (FIN-INV-011)
        تربط المرتجع بسجلات الاستهلاك الأصلية وتستعيد التكلفة لطبقة جديدة
        """
        if return_quantity <= Decimal('0.0000'):
            raise FinancialCoreError("Return quantity must be greater than zero.")

        with transaction.atomic():
            consumptions = InventoryCostConsumption.objects.filter(
                stock_ledger_entry=original_issue_ledger_entry
            ).order_by("-created_at")

            if consumptions.exists():
                unit_cost = consumptions.first().unit_cost
            else:
                unit_cost = getattr(product, 'cost_price', Decimal('0.00')) or Decimal('0.00')

            from product.services.stock_ledger_service import StockLedgerService
            return_entry = StockLedgerService.record_movement_entry(
                product=product,
                warehouse=warehouse,
                movement_type="RECEIPT",
                quantity=return_quantity,
                unit_cost=unit_cost,
                movement_service_ref=f"RET-{original_issue_ledger_entry.id}"
            )

            new_layer = cls.create_receipt_cost_layer(
                product=product,
                warehouse=warehouse,
                stock_ledger_entry=return_entry,
                quantity=return_quantity,
                unit_cost=unit_cost
            )

            logger.info(f"Sales return cost layer created: #{new_layer.id} for Product#{product.id} @ {unit_cost}")
            return new_layer

    @classmethod
    def consume_fifo_layers(
        cls,
        product: Product,
        warehouse: Warehouse,
        issue_quantity: Decimal,
        issue_ledger_entry: StockLedgerEntry
    ) -> Dict[str, Any]:
        """
        صرف المخزون وفق نموذج التقييم المعتمد للمنتج (FIFO أو AVCO) واستهلاك أقدم الطبقات المفتوحة (FIN-INV-004)
        """
        if issue_quantity <= Decimal('0.0000'):
            raise FinancialCoreError("Issue quantity must be greater than zero.")

        with transaction.atomic():
            open_layers = InventoryCostLayer.objects.select_for_update().filter(
                product=product,
                warehouse=warehouse,
                status="OPEN"
            ).order_by("receipt_date", "id")

            total_available = open_layers.aggregate(total=Sum('remaining_qty'))['total'] or Decimal('0.0000')

            if total_available < issue_quantity:
                raise FinancialCoreError(
                    f"INSUFFICIENT_STOCK_LAYERS: Required {issue_quantity}, but available open layers sum to {total_available}."
                )

            remaining_to_consume = issue_quantity
            total_cogs = Decimal('0.00')
            consumptions = []

            for layer in open_layers:
                if remaining_to_consume <= Decimal('0.0000'):
                    break

                consume_qty = min(layer.remaining_qty, remaining_to_consume)
                layer_cost = (consume_qty * layer.unit_cost).quantize(Decimal('0.01'))

                # تحديث طبقة التكلفة
                layer.remaining_qty -= consume_qty
                if layer.remaining_qty == Decimal('0.0000'):
                    layer.status = "DEPLETED"
                layer.save(update_fields=['remaining_qty', 'status'])

                # إنشاء سجل تتبع الاستهلاك (FIN-INV-004 Cost Consumption Tracking)
                cons_num = cls.generate_consumption_number()
                consumption = InventoryCostConsumption.objects.create(
                    consumption_number=cons_num,
                    cost_layer=layer,
                    stock_ledger_entry=issue_ledger_entry,
                    consumed_qty=consume_qty,
                    unit_cost=layer.unit_cost,
                    total_cost=layer_cost
                )
                consumptions.append(consumption)

                total_cogs += layer_cost
                remaining_to_consume -= consume_qty

            avg_unit_cost = (total_cogs / issue_quantity).quantize(Decimal('0.0001'))

            # تحديث كمية Stock كاش
            stock_obj = Stock.objects.filter(product=product, warehouse=warehouse).first()
            if stock_obj:
                stock_obj.quantity = max(Decimal('0.00'), stock_obj.quantity - issue_quantity)
                stock_obj.save(update_fields=['quantity'])

            return {
                'total_cogs': total_cogs,
                'avg_unit_cost': avg_unit_cost,
                'consumptions_count': len(consumptions),
                'issue_quantity': issue_quantity
            }
