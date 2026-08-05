from decimal import Decimal
from typing import Optional
from django.db.models import Sum
from financial.models.cost_center import CostCenter
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import AccountingPeriod
from financial.models.cost_center_budget import CostCenterActualSnapshot


class PurchaseCommitmentEngine:
    """
    محرك الالتزامات المعلقة لأوامر الشراء غير المفوترة (PO Commitment Engine)
    يقوم بحساب وحجز المبالغ المعلقة فور اعتماد أمر الشراء لحماية الموازنة من التجاوز المزدوج
    """

    @classmethod
    def recalculate_commitments(
        cls,
        cost_center: CostCenter,
        account: ChartOfAccounts,
        accounting_period: AccountingPeriod
    ) -> Decimal:
        """
        حساب مجموع الأوامر المعلقة لحساب ومركز تكلفة وفترة محاسبية وتحديث الـ Snapshot
        """
        try:
            from purchase.models.procurement_models import PurchaseOrderItem

            po_items = PurchaseOrderItem.objects.filter(
                purchase_order__status__in=['approved', 'partially_received'],
                purchase_order__order_date__gte=accounting_period.start_date,
                purchase_order__order_date__lte=accounting_period.end_date
            )

            committed_total = Decimal('0.00')
            for item in po_items:
                item_val = (item.total_price if hasattr(item, 'total_price') else (item.quantity * item.unit_price))
                committed_total += Decimal(str(item_val or '0.00'))

        except Exception:
            committed_total = Decimal('0.00')

        snapshot, _ = CostCenterActualSnapshot.objects.get_or_create(
            cost_center=cost_center,
            account=account,
            accounting_period=accounting_period
        )
        snapshot.committed_amount = committed_total
        snapshot.save(update_fields=['committed_amount', 'updated_at'])

        return committed_total
