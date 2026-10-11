"""
HR payroll accounting integration using AccountingGateway.
Provides enterprise-grade journal entry creation, dynamic account resolution via AccountRoleRegistry,
expense offset for absence/penalties, and automated rounding difference handling.
"""
from decimal import Decimal
import logging
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

from governance.services.accounting_gateway import (
    AccountingGateway,
    JournalEntryLineData
)
from governance.exceptions import (
    AuthorityViolationError,
    ValidationError as GovValidationError,
    IdempotencyError
)
from financial.models import ChartOfAccounts, JournalEntry, JournalEntryLine, FinancialCategory, FinancialSubcategory
from financial.services.role_registry import AccountRoleRegistry

logger = logging.getLogger(__name__)


class PayrollAccountingService:
    """
    Service for creating payroll journal entries via AccountingGateway.
    """

    def __init__(self):
        self.gateway = AccountingGateway()

    @staticmethod
    def _get_account_by_role(role_name: str, fallback_codes: Optional[List[str]] = None) -> Optional[ChartOfAccounts]:
        """
        Resolve ChartOfAccounts dynamically using AccountRoleRegistry with fallback codes.
        """
        try:
            account = AccountRoleRegistry.get_account(role_name)
            if account and account.is_active:
                return account
        except Exception as e:
            logger.debug(f"AccountRoleRegistry lookup failed for {role_name}: {e}")

        if fallback_codes:
            for code in fallback_codes:
                acc = ChartOfAccounts.objects.filter(code=code, is_active=True).first()
                if acc:
                    return acc
        return None

    def create_payroll_journal_entry(self, payroll, created_by) -> Optional[JournalEntry]:
        """
        Create journal entry for payroll record.
        Ensures idempotency, atomic transaction safety, and structural balance.
        """
        try:
            # 1. Check if journal entry already exists
            if payroll.journal_entry:
                je = payroll.journal_entry
                if je.status == 'posted':
                    logger.debug(f"Payroll {payroll.id} has posted JE {je.number} — skipping creation")
                    return je

                # Check if unposted entry is balanced
                lines_db = list(je.lines.all())
                td = sum(line.debit for line in lines_db)
                tc = sum(line.credit for line in lines_db)
                if abs(td - tc) < Decimal('0.01') and lines_db:
                    logger.debug(f"Payroll {payroll.id} JE {je.number} already balanced — skipping")
                    return je

                # Unbalanced unposted entry -> Rebuild
                logger.warning(
                    f"Payroll {payroll.id} JE {je.number} unbalanced "
                    f"(debit={td} credit={tc}) — rebuilding lines"
                )
                return self._rebuild_unposted_entry(payroll, je, created_by)

            # 2. Prepare balanced journal lines
            lines = self._prepare_journal_lines(payroll)
            if not lines:
                msg = f"Failed to prepare journal lines for payroll {payroll.id}"
                logger.error(msg)
                raise GovValidationError(msg)

            idempotency_key = f"JE:hr:Payroll:{payroll.id}:create"

            # 3. Resolve Category & Subcategory Parent Guard
            financial_subcategory, financial_category = self._resolve_categories(payroll)

            # 4. Create Entry via AccountingGateway
            entry_date = payroll.payment_date or (payroll.paid_at.date() if payroll.paid_at else timezone.now().date())

            entry = self.gateway.create_journal_entry(
                source_module='hr',
                source_model='Payroll',
                source_id=payroll.id,
                lines=lines,
                idempotency_key=idempotency_key,
                user=created_by,
                entry_type='payroll',
                description=self._generate_description(payroll),
                reference=f"PAY-{payroll.id}",
                date=entry_date,
                financial_category=financial_category,
                financial_subcategory=financial_subcategory
            )

            payroll.journal_entry = entry
            payroll.save(update_fields=['journal_entry'])
            logger.info(f"Created journal entry {entry.number} for payroll {payroll.id}")
            return entry

        except AuthorityViolationError as e:
            logger.error(f"Authority violation for payroll {payroll.id}: {e}")
            raise
        except GovValidationError as e:
            logger.error(f"Validation error for payroll {payroll.id}: {e}")
            raise
        except IdempotencyError as e:
            logger.warning(f"Idempotency notice for payroll {payroll.id}: {e}")
            return payroll.journal_entry if payroll.journal_entry else None
        except Exception as e:
            logger.error(f"Unexpected error creating journal entry for payroll {payroll.id}: {e}", exc_info=True)
            raise

    def _resolve_categories(self, payroll):
        """
        Resolve FinancialCategory and FinancialSubcategory ensuring parent-child compatibility.
        """
        dept = getattr(payroll.employee, 'department', None)
        dept_subcategory = getattr(dept, 'financial_subcategory', None) if dept else None
        payroll_category = getattr(payroll, 'financial_category', None)

        if not payroll_category:
            payroll_category = (
                FinancialCategory.objects.filter(code='salaries', is_active=True).first()
                or FinancialCategory.objects.filter(code='payroll_hr', is_active=True).first()
            )

        financial_subcategory = None
        financial_category = payroll_category

        if dept_subcategory:
            # Check if subcategory has parent matching payroll_category
            parent = getattr(dept_subcategory, 'category', None) or getattr(dept_subcategory, 'parent_category', None)
            if payroll_category and parent and parent.id == payroll_category.id:
                financial_subcategory = dept_subcategory
                financial_category = payroll_category
            elif parent:
                financial_subcategory = dept_subcategory
                financial_category = parent
            else:
                financial_subcategory = None
                financial_category = payroll_category

        return financial_subcategory, financial_category

    def _rebuild_unposted_entry(self, payroll, journal_entry, user):
        """
        Delete lines of an unposted unbalanced entry and rebuild them cleanly.
        """
        if journal_entry.status == 'posted':
            logger.error(f"Cannot rebuild posted entry {journal_entry.number}")
            return journal_entry

        try:
            with transaction.atomic():
                new_lines = self._prepare_journal_lines(payroll)
                if not new_lines:
                    logger.warning(f"No lines prepared when rebuilding JE {journal_entry.number}")
                    return journal_entry

                fin_sub, fin_cat = self._resolve_categories(payroll)
                update_fields = []
                if fin_sub and journal_entry.financial_subcategory_id != fin_sub.id:
                    journal_entry.financial_subcategory = fin_sub
                    update_fields.append('financial_subcategory')
                if fin_cat and journal_entry.financial_category_id != fin_cat.id:
                    journal_entry.financial_category = fin_cat
                    update_fields.append('financial_category')
                if update_fields:
                    journal_entry.save(update_fields=update_fields)

                # Delete old lines and recreate
                journal_entry.lines.all().delete()

                for ld in new_lines:
                    account = ChartOfAccounts.objects.filter(code=ld.account_code, is_active=True).first()
                    if not account:
                        raise GovValidationError(f"Account {ld.account_code} not found in Chart of Accounts")

                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=account,
                        debit=ld.debit,
                        credit=ld.credit,
                        description=ld.description or '',
                        currency=ld.currency,
                        exchange_rate=ld.exchange_rate,
                        foreign_debit=ld.foreign_debit,
                        foreign_credit=ld.foreign_credit
                    )

                logger.info(f"Rebuilt JE {journal_entry.number} for payroll {payroll.id} with {len(new_lines)} lines")
                return journal_entry

        except Exception as e:
            logger.error(f"Failed to rebuild JE {journal_entry.number} for payroll {payroll.id}: {e}", exc_info=True)
            raise

    def _prepare_journal_lines(self, payroll) -> List[JournalEntryLineData]:
        """
        Prepare perfectly balanced journal entry lines for payroll.

        Standard Financial Architecture:
          Debit:
            52100 - Salary Expense (Basic Salary, Allowances, Bonuses, Encashments)
            52200 - Social Insurance Expense (Employer share, if applicable)
          Credit:
            payment_account - Net Salary (Actual cash/bank outflow, omitted if Net == 0)
            21420 - Social Insurance Payable (Employee + Employer share)
            21320 - Income Tax Payable (Withheld taxes)
            11230 - Employee Advances (Withheld advance installments)
            52100 - Salary Expense (Expense offset for absence, late deductions, penalties)
            54400 - Rounding Differences (Penny discrepancies <= 0.05 EGP)
        """
        lines = []

        # ── 1. Resolve Accounts dynamically via AccountRoleRegistry ──────────
        acc_salary_expense = self._get_account_by_role("SALARY_EXPENSE", ['52100', '50200', '50210'])
        acc_ins_expense = self._get_account_by_role("SOCIAL_INSURANCE_EXPENSE", ['52200', '50240'])
        acc_ins_payable = self._get_account_by_role("SOCIAL_INSURANCE", ['21420', '20210'])
        acc_tax_payable = self._get_account_by_role("INCOME_TAX", ['21320', '20220'])
        acc_advance = self._get_account_by_role("EMPLOYEE_ADVANCE", ['11230', '10350'])
        acc_payables = self._get_account_by_role("SALARY_PAYABLES", ['21410', '20200'])
        acc_rounding = self._get_account_by_role("ROUNDING_DIFFERENCE_ACCOUNT", ['54400', '59000'])

        if not acc_salary_expense:
            raise GovValidationError("Salary Expense account (52100) not found in Chart of Accounts.")

        emp_name = payroll.employee.get_full_name_ar()
        correct_net = Decimal(str(getattr(payroll, 'correct_net_salary', payroll.net_salary) or 0))
        basic_salary = Decimal(str(getattr(payroll, 'basic_salary', 0) or 0))

        # ── 2. DEBIT SIDE: Gross Earnings Breakdown ─────────────────────────
        earning_lines = list(
            payroll.lines.filter(component_type='earning')
            .exclude(code__in=['INSURABLE_SALARY', 'BASIC_SALARY'])
        ) if hasattr(payroll, 'lines') else []

        # Basic Salary Line
        if basic_salary > 0:
            lines.append(JournalEntryLineData(
                account_code=acc_salary_expense.code,
                debit=basic_salary,
                credit=Decimal('0'),
                description=f"الأجر الأساسي - {emp_name}"
            ))

        # Earning lines (Allowances, Overtime, Bonuses, Encashments)
        if earning_lines:
            for el in earning_lines:
                amount = Decimal(str(el.amount or 0))
                if amount <= 0:
                    continue
                lines.append(JournalEntryLineData(
                    account_code=acc_salary_expense.code,
                    debit=amount,
                    credit=Decimal('0'),
                    description=f"{el.name or 'استحقاقات'} - {emp_name}"
                ))
        else:
            # Fallback for payrolls without PayrollLine items:
            # Additions = Allowances + Overtime + Bonus
            allowances = Decimal(str(getattr(payroll, 'allowances', 0) or 0))
            overtime_amt = Decimal(str(getattr(payroll, 'overtime_amount', 0) or 0))
            bonus = Decimal(str(getattr(payroll, 'bonus', 0) or 0))
            total_other_earnings = allowances + overtime_amt + bonus

            if total_other_earnings > 0:
                lines.append(JournalEntryLineData(
                    account_code=acc_salary_expense.code,
                    debit=total_other_earnings,
                    credit=Decimal('0'),
                    description=f"البدلات والحوافز والإضافي - {emp_name}"
                ))

        # ── 3. CREDIT SIDE: Net Salary Payment ──────────────────────────────
        # Zero Net Salary Guard: Only add cash/bank credit if net > 0
        if correct_net > 0:
            payment_acc = getattr(payroll, 'payment_account', None)
            if payment_acc:
                net_acc_code = payment_acc.code
            elif acc_payables:
                net_acc_code = acc_payables.code
            else:
                default_cash = self._get_account_by_role("DEFAULT_CASH_DRAWER", ['11110'])
                net_acc_code = default_cash.code if default_cash else acc_salary_expense.code

            lines.append(JournalEntryLineData(
                account_code=net_acc_code,
                debit=Decimal('0'),
                credit=correct_net,
                description=f"صافي راتب {emp_name}"
            ))

        # ── 4. CREDIT SIDE: Deductions Breakdown ────────────────────────────
        deduction_lines = list(
            payroll.lines.filter(component_type='deduction').order_by('order')
        ) if hasattr(payroll, 'lines') else []

        if deduction_lines:
            for dl in deduction_lines:
                amount = Decimal(str(dl.amount or 0))
                if amount <= 0:
                    continue

                code = str(dl.code or '').upper()

                # Social insurance
                if code in ('SOCIAL_INSURANCE', 'SOCIAL_INSURANCE_EMP'):
                    target_acc = acc_ins_payable or acc_salary_expense
                # Income tax
                elif code in ('TAX', 'INCOME_TAX'):
                    target_acc = acc_tax_payable or acc_salary_expense
                # Advance deductions
                elif code.startswith('ADVANCE_') or code == 'ADVANCE_DEDUCTION':
                    target_acc = acc_advance or acc_salary_expense
                # Absence, late, penalties, and other deductions -> Expense Offset (52100)
                elif code in ('ABSENCE_DEDUCTION', 'LATE_DEDUCTION', 'PENALTY', 'OTHER_DEDUCTIONS') or 'ABSENCE' in code or 'PENALTY' in code or 'LATE' in code:
                    target_acc = acc_salary_expense
                else:
                    # Default unclassified deduction -> Expense Offset
                    target_acc = acc_salary_expense

                lines.append(JournalEntryLineData(
                    account_code=target_acc.code,
                    debit=Decimal('0'),
                    credit=amount,
                    description=f"{dl.name or 'استقطاع'} - {emp_name}"
                ))
        else:
            # Fallback for payroll records without line details:
            soc_ins = Decimal(str(getattr(payroll, 'social_insurance', 0) or 0))
            tax_amt = Decimal(str(getattr(payroll, 'tax', 0) or 0))
            adv_amt = Decimal(str(getattr(payroll, 'advance_deduction', 0) or 0))
            abs_amt = Decimal(str(getattr(payroll, 'absence_deduction', 0) or 0))
            late_amt = Decimal(str(getattr(payroll, 'late_deduction', 0) or 0))
            oth_amt = Decimal(str(getattr(payroll, 'other_deductions', 0) or 0))

            if soc_ins > 0:
                acc = acc_ins_payable or acc_salary_expense
                lines.append(JournalEntryLineData(
                    account_code=acc.code,
                    debit=Decimal('0'),
                    credit=soc_ins,
                    description=f"تأمينات اجتماعية - {emp_name}"
                ))

            if tax_amt > 0:
                acc = acc_tax_payable or acc_salary_expense
                lines.append(JournalEntryLineData(
                    account_code=acc.code,
                    debit=Decimal('0'),
                    credit=tax_amt,
                    description=f"ضريبة كسب العمل - {emp_name}"
                ))

            if adv_amt > 0:
                acc = acc_advance or acc_salary_expense
                lines.append(JournalEntryLineData(
                    account_code=acc.code,
                    debit=Decimal('0'),
                    credit=adv_amt,
                    description=f"خصم سلفة - {emp_name}"
                ))

            # Expense Offsets for Disciplinary & Absence
            expense_offsets = abs_amt + late_amt + oth_amt
            if expense_offsets > 0:
                lines.append(JournalEntryLineData(
                    account_code=acc_salary_expense.code,
                    debit=Decimal('0'),
                    credit=expense_offsets,
                    description=f"استقطاعات غياب وتأخيرات وجزاءات - {emp_name}"
                ))

        # ── 5. ROUNDING DIFFERENCE GUARD (Penny Discrepancy <= 0.05 EGP) ────
        total_debit = sum(l.debit for l in lines)
        total_credit = sum(l.credit for l in lines)
        diff = (total_debit - total_credit).quantize(Decimal('0.01'))

        if abs(diff) >= Decimal('0.01'):
            if acc_rounding:
                if diff > 0:
                    # Debit is larger -> Credit rounding
                    lines.append(JournalEntryLineData(
                        account_code=acc_rounding.code,
                        debit=Decimal('0'),
                        credit=diff,
                        description="فروق تقريب رواتب"
                    ))
                else:
                    # Credit is larger -> Debit rounding
                    lines.append(JournalEntryLineData(
                        account_code=acc_rounding.code,
                        debit=abs(diff),
                        credit=Decimal('0'),
                        description="فروق تقريب رواتب"
                    ))
                logger.debug(f"Payroll {payroll.id}: balanced rounding diff {diff} -> {acc_rounding.code}")
            else:
                logger.warning(f"Payroll {payroll.id}: rounding diff {diff} but rounding account not found")

        return lines

    def _generate_description(self, payroll) -> str:
        """Generate descriptive reference string for journal entry."""
        emp_name = payroll.employee.get_full_name_ar()
        month_str = payroll.month.strftime("%Y-%m") if hasattr(payroll.month, 'strftime') else str(payroll.month)
        return f"راتب {emp_name} - شهر {month_str}"
