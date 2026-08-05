import logging
from decimal import Decimal
from typing import List, Dict, Any, Tuple
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models.fiscal_year import FiscalYear
from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.services.ledger_core_service import LedgerCoreService
from financial.exceptions import FinancialCoreError, UnbalancedEntryError, ImmutableLedgerError

logger = logging.getLogger("financial.opening_balance_service")


class OpeningBalanceValidationService:
    """
    خدمة التحقق من الأرصدة الافتتاحية
    """

    @classmethod
    def validate_batch(cls, batch: OpeningBalanceBatch) -> Tuple[bool, List[str]]:
        """
        فحص دفعة الأرصدة الافتتاحية (توازن المدين/الدائن، الحسابات الفعالة والنهائية، وعدم تكرار أسطر الحسابات)
        """
        errors = []
        lines = batch.lines.select_related('account').all()

        if not lines.exists():
            errors.append("دفعة الأرصدة الافتتاحية فارغة ولا تحتوي على أسطر.")
            return False, errors

        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        seen_account_ids = set()

        for line in lines:
            account = line.account

            if not account.is_active:
                errors.append(f"الحساب المحاسبي {account.name} ({account.code}) غير مفعّل.")

            if not account.is_leaf:
                errors.append(f"الحساب المحاسبي {account.name} ({account.code}) ليس حساباً نهائياً (Leaf Account).")

            if account.id in seen_account_ids:
                errors.append(f"الحساب المحاسبي {account.name} ({account.code}) مكرر في الدفعة.")
            seen_account_ids.add(account.id)

            if line.debit < 0 or line.credit < 0:
                errors.append(f"مبالغ الحساب {account.code} يجب أن تكون موجبة.")

            if line.debit > 0 and line.credit > 0:
                errors.append(f"الحساب {account.code} لا يمكن أن يكون مديناً ودائماً في نفس السطر.")

            total_debit += line.debit
            total_credit += line.credit

        if total_debit != total_credit:
            errors.append(f"دفعة الأرصدة الافتتاحية غير متوازنة: إجمالي المدين ({total_debit}) != إجمالي الدائن ({total_credit}).")

        is_valid = len(errors) == 0
        return is_valid, errors


class OpeningBalanceService:
    """
    خدمة الأرصدة الافتتاحية وإدارتها
    """

    @classmethod
    @transaction.atomic
    def create_batch(
        cls,
        fiscal_year: FiscalYear,
        batch_number: str,
        description: str,
        lines_data: List[Dict[str, Any]]
    ) -> OpeningBalanceBatch:
        """
        إنشاء دفعة أرصدة افتتاحية مسودة
        """
        batch = OpeningBalanceBatch.objects.create(
            fiscal_year=fiscal_year,
            batch_number=batch_number,
            description=description,
            status='draft'
        )

        for item in lines_data:
            account = item.get('account')
            if not account and item.get('account_code'):
                account = ChartOfAccounts.objects.get(code=item['account_code'])

            debit = Decimal(str(item.get('debit', 0)))
            credit = Decimal(str(item.get('credit', 0)))

            OpeningBalanceLine.objects.create(
                batch=batch,
                account=account,
                debit=debit,
                credit=credit
            )

        logger.info(f"✅ تم إنشاء مسودة دفعة أرصدة افتتاحية: {batch_number}")
        return batch

    @classmethod
    @transaction.atomic
    def post_batch(cls, batch_id: int, user) -> OpeningBalanceBatch:
        """
        اعتماد ونشر دفعة الأرصدة الافتتاحية وتحويلها إلى قيد مرحل حصين عبر LedgerCoreService
        """
        batch = OpeningBalanceBatch.objects.select_for_update().get(pk=batch_id)

        if batch.status == 'posted':
            from financial.exceptions import ImmutableLedgerError
            raise ImmutableLedgerError(_("الدفعة الافتتاحية مرحلة بالفعل وحصينة ولا يمكن إعادة ترحيلها."))

        # 1. الفحص الصارم عبر OpeningBalanceValidationService
        is_valid, errors = OpeningBalanceValidationService.validate_batch(batch)
        if not is_valid:
            raise UnbalancedEntryError(f"فشل التحقق من دفعة الأرصدة الافتتاحية: {'; '.join(errors)}")

        # 2. تجهيز بنود القيد
        lines_data = []
        for line in batch.lines.select_related('account').all():
            lines_data.append({
                'account': line.account,
                'debit': line.debit,
                'credit': line.credit,
                'description': f"رصيد افتتاحي - {line.account.name}"
            })

        # 3. إنشاء قيد مسودة ونشره عبر LedgerCoreService
        draft_entry = LedgerCoreService.create_draft_entry(
            date=batch.fiscal_year.start_date,
            description=f"قيد الأرصدة الافتتاحية لسنة {batch.fiscal_year.name}",
            reference=batch.batch_number,
            entry_type='opening',
            created_by=user,
            lines_data=lines_data
        )

        posted_entry = LedgerCoreService.post_entry(
            entry_id=draft_entry.id,
            user=user,
            posting_source='OPENING_BALANCE',
            posting_reference=batch.batch_number
        )

        # 4. تحديث الدفعة وحصانتها
        batch.journal_entry = posted_entry
        batch.status = 'posted'
        batch.save(update_fields=['journal_entry', 'status'])

        logger.info(f"🔒 تم ترحيل وحصانة دفعة الأرصدة الافتتاحية: {batch.batch_number}")
        return batch
