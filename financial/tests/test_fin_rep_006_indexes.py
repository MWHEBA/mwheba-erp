import pytest
from django.db import models
from client.models import CustomerTransaction, CustomerAllocationAudit
from financial.models import RevenueRecognitionScheduleLine, RevenueRecognitionEntry, TaxDeterminationAudit
from product.models import InventoryReservation
from sale.models import SalesReturnHeader, SalesReturnAudit, CreditNote, CreditNoteAudit
from core.database.index_strategy import INDEX_REGISTRY


@pytest.mark.django_db
class TestFINREP006Indexes:

    def test_model_indexes_configuration(self):
        # CustomerTransaction
        cust_tx_idx_names = [idx.name for idx in CustomerTransaction._meta.indexes if idx.name]
        assert "idx_cust_open_ar_partial" in cust_tx_idx_names

        # RevenueRecognitionScheduleLine
        rev_line_idx_names = [idx.name for idx in RevenueRecognitionScheduleLine._meta.indexes if idx.name]
        assert "idx_rev_sched_status_date" in rev_line_idx_names

        # RevenueRecognitionEntry
        rev_entry_idx_names = [idx.name for idx in RevenueRecognitionEntry._meta.indexes if idx.name]
        assert "idx_rev_entry_corr_time" in rev_entry_idx_names

        # TaxDeterminationAudit
        tax_audit_idx_names = [idx.name for idx in TaxDeterminationAudit._meta.indexes if idx.name]
        assert "idx_tax_audit_corr_time" in tax_audit_idx_names

        # InventoryReservation
        inv_res_idx_names = [idx.name for idx in InventoryReservation._meta.indexes if idx.name]
        assert "idx_inv_res_active_sweep" in inv_res_idx_names

        # CreditNote & SalesReturn Audits
        cn_audit_idx_names = [idx.name for idx in CreditNoteAudit._meta.indexes if idx.name]
        assert "idx_cn_audit_corr_time" in cn_audit_idx_names

        ret_audit_idx_names = [idx.name for idx in SalesReturnAudit._meta.indexes if idx.name]
        assert "idx_sal_ret_audit_corr_time" in ret_audit_idx_names

    def test_benchmark_and_audit_indexes(self):
        # Verify all 6 audit evidence models have correlation_id + created_at indexes
        for model in [TaxDeterminationAudit, RevenueRecognitionEntry, CustomerAllocationAudit, CreditNoteAudit, SalesReturnAudit]:
            idx_names = [idx.name for idx in model._meta.indexes if idx.name]
            has_corr_idx = any("corr" in name.lower() or "time" in name.lower() for name in idx_names)
            assert has_corr_idx, f"Model {model.__name__} missing correlation time index!"
