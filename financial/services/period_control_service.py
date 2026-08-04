"""
PeriodControlService - خدمة التحكم في الفترات المحاسبية (Financial Core Engine v1.8)
المسؤولة عن حظر القيد والترحيل في الفترات المغلقة، وقفل الفترات والسنوات المالية.
"""

import logging
from django.db import transaction

from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("financial.period_control_service")


class PeriodControlService:
    """
    خدمة الحوكمة والتحكم بالفترات المحاسبية والسنوات المالية
    """

    @classmethod
    def lock_period(cls, period_id: int, user, lock_type: str = "soft_closed"):
        """
        إغلاق/قفل الفترة المحاسبية
        """
        with transaction.atomic():
            period = AccountingPeriod.objects.select_for_update().get(pk=period_id)
            period.status = lock_type
            if lock_type == "hard_closed":
                period.is_closed = True
            period.save(update_fields=["status", "is_closed"])
            logger.info(f"AccountingPeriod '{period.name}' locked with status '{lock_type}' by user {user}")
            return period

    @classmethod
    def validate_date_in_open_period(cls, target_date):
        """
        التحقق من أن تاريخ المعاملة يقع ضمن فترة محاسبية مفتوحة
        """
        period = AccountingPeriod.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date
        ).first()

        if not period:
            raise FinancialCoreError(f"No accounting period found for date {target_date}.")

        if period.status in ["soft_closed", "hard_closed"] or period.is_closed:
            raise FinancialCoreError(f"Accounting period '{period.name}' is closed for postings.")

        return period
