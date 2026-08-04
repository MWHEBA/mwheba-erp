"""
FinancialSnapshotService - خدمة تجميد لقطات القوائم المالية الفترية والتاريخية (FIN-REP-003)
تنشئ السجلات المجمدة للقوائم المالية للتحفظ والمراجعة التاريخية بعد إغلاق الفترة
"""

import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction

from financial.models.reporting_snapshot import FinancialStatementSnapshot
from financial.models.journal_entry import AccountingPeriod
from financial.services.financial_statement_engine import FinancialStatementEngine
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("financial.snapshot_service")


class FinancialSnapshotService:
    """
    خدمة تجميد لقطات القوائم المالية الفترية (Financial Statement Snapshot Service)
    """

    @classmethod
    def generate_snapshot_number(cls, statement_type: str) -> str:
        date_prefix = timezone.now().strftime("%Y%m%d")
        unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
        return f"SNAP-{statement_type[:3]}-{date_prefix}-{unique_suffix}"

    @classmethod
    def create_statement_snapshot(
        cls,
        period: AccountingPeriod,
        statement_type: str,
        user,
        as_of_date: Optional[Any] = None
    ) -> FinancialStatementSnapshot:
        """
        إنشاء وتجميد لقطة مالية سريعة للقائمة المالية المحددة
        """
        target_date = as_of_date or getattr(period, 'end_date', None) or timezone.now().date()

        if statement_type == "TRIAL_BALANCE":
            stmt_data = FinancialStatementEngine.generate_trial_balance(as_of_date=target_date)
        elif statement_type == "INCOME_STATEMENT":
            stmt_data = FinancialStatementEngine.generate_income_statement(as_of_date=target_date)
        elif statement_type == "BALANCE_SHEET":
            stmt_data = FinancialStatementEngine.generate_balance_sheet(as_of_date=target_date)
        else:
            raise FinancialCoreError(f"Unsupported statement_type: {statement_type}")

        snap_num = cls.generate_snapshot_number(statement_type)

        # تحويل الأرصدة إلى strings لسهولة حفظ الـ JSON
        def convert_decimals(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(item) for item in obj]
            return obj

        json_data = convert_decimals(stmt_data)

        with transaction.atomic():
            snapshot = FinancialStatementSnapshot.objects.create(
                snapshot_number=snap_num,
                period=period,
                statement_type=statement_type,
                as_of_date=target_date,
                statement_data=json_data,
                is_closed_period=getattr(period, 'is_closed', False),
                created_by=user
            )

            logger.info(f"FinancialStatementSnapshot created: #{snap_num} for period {period.name} ({statement_type})")
            return snapshot
