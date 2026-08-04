"""
LandedCostService - محرك توزيع التكاليف الإضافية والتحميل على أصل المخزون أو فروقات COGS (FIN-INV-001)
يدير مستندات وتوزيع الشحن والجمارك والتأمين
"""

import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from product.models.landed_cost import LandedCostDocument, LandedCostAllocation
from product.models.stock_ledger import StockLedgerEntry
from product.models.cost_layer import InventoryCostLayer
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("product.landed_cost_service")


class LandedCostService:
    """
    خدمة محرك التكاليف الإضافية والشحن (Landed Cost Allocation Service)
    """

    @classmethod
    def generate_voucher_number(cls) -> str:
        date_prefix = timezone.now().strftime("%Y%m%d")
        unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
        return f"LC-VOUCHER-{date_prefix}-{unique_suffix}"

    @classmethod
    def create_landed_cost_voucher(
        cls,
        total_landed_cost: Decimal,
        allocation_method: str,
        user,
        supplier=None
    ) -> LandedCostDocument:
        """
        إنشاء مستند تكاليف إضافية جديد (مسودة)
        """
        if total_landed_cost <= Decimal('0.00'):
            raise FinancialCoreError("Total landed cost must be greater than zero.")

        voucher_num = cls.generate_voucher_number()

        doc = LandedCostDocument.objects.create(
            voucher_number=voucher_num,
            supplier=supplier,
            allocation_method=allocation_method,
            total_landed_cost=total_landed_cost,
            status="DRAFT",
            created_by=user
        )

        logger.info(f"LandedCostDocument created: #{voucher_num} with total {total_landed_cost} EGP.")
        return doc

    @classmethod
    def allocate_and_post_landed_cost(
        cls,
        voucher_id: int,
        receipt_ledger_entry_ids: List[int],
        user
    ) -> Dict[str, Any]:
        """
        توزيع التكاليف الإضافية على أسطر شحنات الاستلام:
        - للبضاعة المتبقية بالمخزن: تضاف لتقييم أصل المخزون وتعدل طبقة التكلفة.
        - للبضاعة المباعة سابقاً: تُرحل المبالغ صراحة لفروق تكلفة البضاعة المباعة (50110 COGS Variance).
        """
        with transaction.atomic():
            doc = LandedCostDocument.objects.select_for_update().get(pk=voucher_id)
            if doc.status == "POSTED":
                raise FinancialCoreError("Landed Cost voucher is already posted.")

            entries = StockLedgerEntry.objects.filter(pk__in=receipt_ledger_entry_ids, movement_type="RECEIPT")
            if not entries.exists():
                raise FinancialCoreError("No valid receipt stock ledger entries provided for allocation.")

            total_cost_pool = doc.total_landed_cost
            allocations_data = []
            total_asset_portion = Decimal('0.00')
            total_variance_portion = Decimal('0.00')

            # توزيع القيمة حسب أسلوب التوزيع (Default VALUE based)
            if doc.allocation_method == "QUANTITY":
                total_basis = entries.aggregate(sum_base=Sum('quantity'))['sum_base'] or Decimal('1.0000')
            else:
                total_basis = entries.aggregate(sum_base=Sum('total_cost'))['sum_base'] or Decimal('1.00')

            for entry in entries:
                basis_val = entry.quantity if doc.allocation_method == "QUANTITY" else entry.total_cost
                allocated_fee = (total_cost_pool * (basis_val / total_basis)).quantize(Decimal('0.01'))

                # فحص حالة طبقة التكلفة المقابلة
                layer = InventoryCostLayer.objects.filter(stock_ledger_entry=entry).first()

                asset_portion = Decimal('0.00')
                variance_portion = Decimal('0.00')

                if layer and layer.original_qty > Decimal('0.0000'):
                    ratio_remaining = layer.remaining_qty / layer.original_qty
                    asset_portion = (allocated_fee * ratio_remaining).quantize(Decimal('0.01'))
                    variance_portion = allocated_fee - asset_portion

                    # تعديل تكلفة الوحدة في الطبقة المتبقية بالمخزن
                    if layer.remaining_qty > Decimal('0.0000'):
                        unit_cost_increase = asset_portion / layer.remaining_qty
                        layer.unit_cost += unit_cost_increase
                        layer.save(update_fields=['unit_cost'])
                else:
                    variance_portion = allocated_fee

                alloc_rec = LandedCostAllocation.objects.create(
                    landed_cost_doc=doc,
                    stock_ledger_entry=entry,
                    allocated_cost=allocated_fee,
                    allocated_to_asset=asset_portion,
                    allocated_to_variance=variance_portion
                )
                allocations_data.append(alloc_rec)

                total_asset_portion += asset_portion
                total_variance_portion += variance_portion

            doc.status = "POSTED"
            doc.save(update_fields=['status'])

            logger.info(
                f"Landed Cost Voucher #{doc.voucher_number} posted successfully: "
                f"Asset Portion = {total_asset_portion}, COGS Variance Portion = {total_variance_portion}."
            )

            return {
                'voucher_id': doc.id,
                'total_landed_cost': total_cost_pool,
                'total_asset_portion': total_asset_portion,
                'total_variance_portion': total_variance_portion,
                'allocations_count': len(allocations_data)
            }
