from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Any, Optional


@dataclass
class ARMetricsDTO:
    """
    FIN-EEL: Accounts Receivable Metrics DTO
    """
    total_open_ar: Decimal
    overdue_ar: Decimal
    customer_count_with_balance: int
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_90_plus: Decimal
    currency: str = "EGP"


@dataclass
class InventoryMetricsDTO:
    """
    FIN-EEL: Inventory & ATP Metrics DTO
    """
    total_valuation: Decimal
    active_reservations_count: int
    reserved_quantity_total: Decimal
    low_stock_items_count: int
    currency: str = "EGP"


@dataclass
class TaxMetricsDTO:
    """
    FIN-EEL: Statutory Tax Metrics DTO
    """
    output_vat_total: Decimal
    input_vat_total: Decimal
    net_vat_liability: Decimal
    audit_verification_pass_rate: float
    currency: str = "EGP"


@dataclass
class ExecutiveDashboardDTO:
    """
    FIN-EEL: Executive Dashboard Aggregated DTO
    """
    as_of_date: str
    ar_metrics: ARMetricsDTO
    inventory_metrics: InventoryMetricsDTO
    tax_metrics: TaxMetricsDTO
    pending_approvals_count: int
    total_revenue_mtd: Decimal
    total_cogs_mtd: Decimal
    gross_profit_mtd: Decimal
    currency: str = "EGP"
