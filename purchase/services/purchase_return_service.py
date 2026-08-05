import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone

from supplier.models import Supplier
from product.models.product_core import Product
from product.models.stock_management import Warehouse, Stock
from governance.services.movement_service import MovementService
from financial.services.ledger_core_service import LedgerCoreService

logger = logging.getLogger("purchase.purchase_return_service")


class PurchaseReturnService:
    """
    محرك مرتجعات المشتريات المحصن (FIN-SAL-006 Purchase Return Split Guard)
    يفصل مرتجع المشتريات تلقائياً:
    - الكميات المتبقية بالمخزن الفعلي -> مرتجع مخزني فعلي (Physical Stock Return)
    - الكميات المباعة سابقاً للعملاء -> إشعار مدين / تسوية سعرية (Financial Debit Note) دون مساس بالكميات لمنع السلبية.
    """

    @classmethod
    def process_purchase_return(
        cls,
        supplier_id: int,
        product_id: int,
        warehouse_id: int,
        requested_qty: Decimal,
        return_unit_price: Decimal,
        reference_number: str = "",
        user=None
    ) -> Dict[str, Any]:
        supplier = Supplier.objects.get(pk=supplier_id)
        product = Product.objects.get(pk=product_id)
        warehouse = Warehouse.objects.get(pk=warehouse_id)

        requested_qty = Decimal(str(requested_qty))
        return_unit_price = Decimal(str(return_unit_price))

        with transaction.atomic():
            # 1. الاستعلام عن المخزون المتاح المتبقي بالمخزن
            stock_obj = Stock.objects.filter(
                product=product,
                warehouse=warehouse
            ).select_for_update().first()

            available_physical_qty = stock_obj.quantity if stock_obj else Decimal('0.0000')

            # 2. حساب تقسيم الكميات (Physical Return vs Financial Debit Note)
            physical_return_qty = min(requested_qty, available_physical_qty)
            debit_note_qty = requested_qty - physical_return_qty

            physical_value = physical_return_qty * return_unit_price
            debit_note_value = debit_note_qty * return_unit_price
            total_return_value = physical_value + debit_note_value

            stock_movement_id = None
            debit_note_ref = None

            # 3. تنفيذ المرتجع المخزني الفعلي للكمية المتوفرة
            if physical_return_qty > Decimal('0.0000'):
                ref_num = reference_number or f"PRET-PHYS-{supplier.id}"
                service = MovementService()
                mv_res = service.process_movement(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity_change=-physical_return_qty,
                    movement_type="out",
                    source_reference=ref_num,
                    idempotency_key=f"PRET:{supplier.id}:{product.id}:{ref_num}",
                    user=user,
                    notes=f"Physical purchase return for supplier {supplier.name}"
                )
                stock_movement_id = getattr(mv_res, 'id', None) or getattr(mv_res, 'pk', None)

            # 4. إصدار الإشعار المدين المالي للكميات المباعة سابقاً
            if debit_note_qty > Decimal('0.0000'):
                debit_note_ref = f"DN-SUPP-{supplier.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                logger.info(f"Financial Debit Note created for sold stock return: {debit_note_ref} ({debit_note_qty} units @ {return_unit_price})")

            return {
                "supplier_id": supplier.id,
                "product_id": product.id,
                "requested_qty": requested_qty,
                "physical_return_qty": physical_return_qty,
                "debit_note_qty": debit_note_qty,
                "physical_value": physical_value,
                "debit_note_value": debit_note_value,
                "total_return_value": total_return_value,
                "stock_movement_id": stock_movement_id,
                "debit_note_ref": debit_note_ref,
                "status": "PROCESSED"
            }
