"""
FIN-REP-006 v3.0: Enterprise ERP Database Performance & Indexing Strategy Registry
وثيقة ودليل سياسات الفهارس المركبة والجزئية للجداول المالية لضمان أداء الفهارس عند 10M+ سجل
"""

from typing import Dict, Any, List

INDEX_REGISTRY: Dict[str, Dict[str, Any]] = {
    "CustomerTransaction": {
        "purpose": "High-efficiency open receivables lookup and debt aging report",
        "index_name": "idx_customer_open_ar_aging",
        "fields": ["customer", "status", "due_date"],
        "partial_condition": "Q(status='OPEN')",
        "expected_scale_rows": 10000000,
    },
    "RevenueRecognitionSchedule": {
        "purpose": "IFRS 15 schedule line recognition sweep by period and status",
        "index_name": "idx_rev_schedule_status_date",
        "fields": ["status", "recognition_date"],
        "partial_condition": "Q(status='SCHEDULED')",
        "expected_scale_rows": 15000000,
    },
    "InventoryReservation": {
        "purpose": "Real-time ATP soft commitment query and expiration sweep",
        "index_name": "idx_inv_res_active_sweep",
        "fields": ["product", "warehouse", "status", "expires_at"],
        "partial_condition": "Q(status='ACTIVE')",
        "expected_scale_rows": 5000000,
    },
    "TaxDeterminationAudit": {
        "purpose": "Canonical SHA256 audit lookup and correlation event trace",
        "index_name": "idx_tax_audit_corr_time",
        "fields": ["correlation_id", "created_at"],
        "expected_scale_rows": 20000000,
    },
    "CreditNoteAudit": {
        "purpose": "Credit Note financial evidence and correlation search",
        "index_name": "idx_cn_audit_corr_time",
        "fields": ["correlation_id", "created_at"],
        "expected_scale_rows": 10000000,
    },
    "SalesReturnAudit": {
        "purpose": "Sales Return quality inspection evidence correlation search",
        "index_name": "idx_sal_ret_audit_corr_time",
        "fields": ["correlation_id", "created_at"],
        "expected_scale_rows": 10000000,
    },
}
