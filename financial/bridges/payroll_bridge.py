"""
PayrollAccountingBridge - جسر التوجيه المحاسبي للرواتب والأجور والمستحقات
يولد القيود المزدوجة المحوكمة لمسيرات الرواتب والمستحقات العمالية.
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone
from django.db import transaction

from financial.services.ledger_core_service import LedgerCoreService

logger = logging.getLogger("financial.bridges.payroll")


class PayrollAccountingBridge:
    """
    جسر التوجيه المحاسبي المعزول للرواتب والأجور
    """

    @classmethod
    def post_payroll_run(
        cls,
        payroll_run_id: str,
        total_salaries: Decimal,
        total_allowances: Decimal,
        total_deductions: Decimal,
        net_payable: Decimal,
        entry_date=None,
        user=None
    ) -> Dict[str, Any]:
        """
        إنشاء وترحيل قيد مسير الرواتب والأجور: Dr. مصروف الرواتب / Cr. مستحقات الرواتب والاستقطاعات
        """
        entry_date = entry_date or timezone.now().date()

        lines = [
            # 1. Salaries Expense (Dr)
            {
                "account_code": "52010_SALARIES_EXPENSE",
                "debit": total_salaries + total_allowances,
                "credit": Decimal("0.00"),
                "description": f"إجمالي مصروف الرواتب والبدلات - مسير #{payroll_run_id}"
            },
            # 2. Salary Deductions Liability (Cr)
            {
                "account_code": "22020_PAYROLL_DEDUCTIONS",
                "debit": Decimal("0.00"),
                "credit": total_deductions,
                "description": f"استقطاعات واستقطاعات الرواتب - مسير #{payroll_run_id}"
            } if total_deductions > Decimal("0.00") else None,
            # 3. Net Salaries Payable Liability (Cr)
            {
                "account_code": "22010_SALARIES_PAYABLE",
                "debit": Decimal("0.00"),
                "credit": net_payable,
                "description": f"صافي الرواتب والأجور المستحقة - مسير #{payroll_run_id}"
            },
        ]

        # Filter out None lines
        lines_data = [line for line in lines if line is not None]

        draft_entry = LedgerCoreService.create_draft_entry(
            date=entry_date,
            description=f"قيد مسير الرواتب والأجور رقم #{payroll_run_id}",
            reference=f"PAYROLL-{payroll_run_id}",
            entry_type="GENERAL",
            created_by=user,
            lines_data=lines_data,
            source_module="PAYROLL",
            source_model="PayrollRun",
            source_id=1
        )
        posted_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

        logger.info(f"Posted Payroll Accounting Bridge entry #{posted_entry.id} for Payroll Run #{payroll_run_id}")
        return {"status": "POSTED", "journal_entry_id": posted_entry.id}
