"""
StockLedgerService - خدمة إدارة أستاذ المخزون المحاسبي غير القابل للتعديل (FIN-INV-001)
تتولى تسجيل وتقييدات أستاذ المخزون التراكمي وإحصاء الأرصدة المشتقة
"""

import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from product.models.stock_ledger import StockLedgerEntry
from product.models.product_core import Product, ProductVariant, Unit
from product.models.stock_management import Warehouse
from financial.models.journal_entry import JournalEntry
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("product.stock_ledger_service")


class StockLedgerService:
    """
    خدمة أستاذ المخزون المعيارية (Immutable Stock Ledger Service)
    """

    @classmethod
    def generate_entry_number(cls) -> str:
        date_prefix = timezone.now().strftime("%Y%m%d")
        unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
        return f"STK-LEDGER-{date_prefix}-{unique_suffix}"

    @classmethod
    def record_movement_entry(
        cls,
        product: Product,
        warehouse: Warehouse,
        movement_type: str,
        quantity: Decimal,
        unit_cost: Decimal,
        movement_service_ref: str,
        variant: Optional[ProductVariant] = None,
        base_uom: Optional[Unit] = None,
        journal_entry: Optional[JournalEntry] = None
    ) -> StockLedgerEntry:
        """
        تسجيل سطر جديد بأستاذ المخزون (Append-only Immutable Entry)
        """
        if quantity == Decimal('0.0000'):
            raise FinancialCoreError("Quantity change cannot be zero.")

        total_cost = (abs(quantity) * unit_cost).quantize(Decimal('0.01'))
        signed_quantity = quantity if movement_type in ["RECEIPT", "TRANSFER_IN", "ADJUSTMENT_IN"] else -abs(quantity)

        with transaction.atomic():
            # (Inventory Idempotency Protection): Prevent duplicate StockLedgerEntry on retry/duplicate requests
            existing_entry = StockLedgerEntry.objects.filter(
                movement_service_ref=movement_service_ref,
                product=product,
                warehouse=warehouse,
                movement_type=movement_type
            ).first()

            if existing_entry:
                logger.info(f"Duplicate inventory movement detected for ref #{movement_service_ref}, returning existing ledger entry.")
                return existing_entry

            # حساب الأرصدة التراكمية كبيانات مشتقة للكاش فقط
            current_qty_agg = StockLedgerEntry.objects.filter(
                product=product,
                warehouse=warehouse
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0.0000')

            current_val_agg = StockLedgerEntry.objects.filter(
                product=product,
                warehouse=warehouse
            ).aggregate(total=Sum('total_cost'))['total'] or Decimal('0.00')

            qty_balance_cache = current_qty_agg + signed_quantity
            val_balance_cache = current_val_agg + (total_cost if signed_quantity > 0 else -total_cost)

            entry_num = cls.generate_entry_number()

            entry = StockLedgerEntry.objects.create(
                entry_number=entry_num,
                movement_service_ref=movement_service_ref,
                product=product,
                variant=variant,
                warehouse=warehouse,
                base_uom=base_uom or getattr(product, 'unit', None),
                movement_type=movement_type,
                quantity=signed_quantity,
                unit_cost=unit_cost,
                total_cost=total_cost,
                qty_balance_after=qty_balance_cache,
                val_balance_after=val_balance_cache,
                journal_entry=journal_entry
            )

            logger.info(
                f"StockLedgerEntry recorded: #{entry_num} for Product#{product.id} "
                f"({signed_quantity} @ {unit_cost} EGP)"
            )
            return entry

    @classmethod
    def get_product_stock_balance(cls, product: Product, warehouse: Warehouse) -> Decimal:
        """
        حساب رصيد كمية المخزون الفعلي من واقع مجموع سجلات أستاذ المخزون
        """
        total_qty = StockLedgerEntry.objects.filter(
            product=product,
            warehouse=warehouse
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0.0000')

        return total_qty
