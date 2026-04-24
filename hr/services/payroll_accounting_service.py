"""
HR payroll accounting integration using AccountingGateway.
"""
from governance.services.accounting_gateway import (
    AccountingGateway,
    JournalEntryLineData
)
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class PayrollAccountingService:
    """
    Service for creating payroll journal entries via AccountingGateway.
    """
    
    def __init__(self):
        self.gateway = AccountingGateway()
    
    def create_payroll_journal_entry(self, payroll, created_by):
        """
        Create journal entry for payroll. If an unposted entry already exists
        but is unbalanced, rebuild it automatically.
        """
        from governance.exceptions import AuthorityViolationError, ValidationError as GovValidationError, IdempotencyError

        try:
            # إذا كان القيد موجود — تحقق من توازنه
            if payroll.journal_entry:
                je = payroll.journal_entry
                if je.is_posted:
                    # مرحّل — لا نلمسه
                    logger.debug(f'Payroll {payroll.id} has posted JE {je.number} — skipping')
                    return je

                # غير مرحّل — تحقق من التوازن
                lines_db = list(je.lines.all())
                td = sum(l.debit for l in lines_db)
                tc = sum(l.credit for l in lines_db)
                if abs(td - tc) < Decimal('0.01'):
                    logger.debug(f'Payroll {payroll.id} JE {je.number} already balanced — skipping')
                    return je

                # غير متوازن — أعد بناءه
                logger.warning(
                    f'Payroll {payroll.id} JE {je.number} unbalanced '
                    f'(debit={td} credit={tc}) — rebuilding lines'
                )
                return self._rebuild_unposted_entry(payroll, je, created_by)

            # لا يوجد قيد — أنشئ جديد
            lines = self._prepare_journal_lines(payroll)
            if not lines:
                logger.warning(f'No journal lines prepared for payroll {payroll.id}')
                return None

            idempotency_key = f'JE:hr:Payroll:{payroll.id}:create'

            financial_subcategory = None
            financial_category = None
            dept = getattr(payroll.employee, 'department', None)
            if dept and getattr(dept, 'financial_subcategory', None):
                financial_subcategory = dept.financial_subcategory
                financial_category = financial_subcategory.parent_category
            else:
                financial_category = getattr(payroll, 'financial_category', None)
                if not financial_category:
                    try:
                        from financial.models import FinancialCategory
                        financial_category = FinancialCategory.objects.filter(
                            code='salaries', is_active=True
                        ).first()
                    except Exception:
                        financial_category = None

            entry = self.gateway.create_journal_entry(
                source_module='hr',
                source_model='Payroll',
                source_id=payroll.id,
                lines=lines,
                idempotency_key=idempotency_key,
                user=created_by,
                entry_type='automatic',
                description=self._generate_description(payroll),
                reference=f'PAY-{payroll.id}',
                date=payroll.payment_date or payroll.paid_at.date() if payroll.paid_at else None,
                financial_category=financial_category,
                financial_subcategory=financial_subcategory
            )

            payroll.journal_entry = entry
            payroll.save(update_fields=['journal_entry'])
            logger.info(f'Created journal entry {entry.number} for payroll {payroll.id}')
            return entry

        except AuthorityViolationError as e:
            logger.error(f'Authority violation for payroll {payroll.id}: {e}')
            return None
        except GovValidationError as e:
            logger.error(f'Validation error for payroll {payroll.id}: {e}')
            return None
        except IdempotencyError as e:
            logger.warning(f'Idempotency error for payroll {payroll.id}: {e}')
            return payroll.journal_entry if payroll.journal_entry else None
        except Exception as e:
            logger.error(f'Unexpected error for payroll {payroll.id}: {e}', exc_info=True)
            return None

    def _rebuild_unposted_entry(self, payroll, journal_entry, user):
        """
        Delete all lines of an unposted unbalanced entry and rebuild them correctly.
        Also updates financial_subcategory on the entry if missing.
        Only works on unposted entries.
        """
        from django.db import transaction

        if journal_entry.is_posted:
            logger.error(f'Cannot rebuild posted entry {journal_entry.number}')
            return journal_entry

        try:
            with transaction.atomic():
                new_lines = self._prepare_journal_lines(payroll)
                if not new_lines:
                    logger.warning(f'No lines prepared when rebuilding JE {journal_entry.number}')
                    return journal_entry

                # تحديث التصنيف المالي الفرعي لو ناقص
                update_fields = []
                dept = getattr(payroll.employee, 'department', None)
                fin_sub = getattr(dept, 'financial_subcategory', None) if dept else None
                if fin_sub and not journal_entry.financial_subcategory:
                    journal_entry.financial_subcategory = fin_sub
                    update_fields.append('financial_subcategory')
                if fin_sub and not journal_entry.financial_category:
                    journal_entry.financial_category = fin_sub.parent_category
                    update_fields.append('financial_category')
                if update_fields:
                    journal_entry.save(update_fields=update_fields)

                # حذف البنود القديمة وإعادة الإنشاء
                journal_entry.lines.all().delete()

                from financial.models import ChartOfAccounts, JournalEntryLine
                for ld in new_lines:
                    account = ChartOfAccounts.objects.filter(
                        code=ld.account_code, is_active=True
                    ).first()
                    if not account:
                        logger.error(f'Account {ld.account_code} not found — aborting rebuild')
                        raise ValueError(f'Account {ld.account_code} not found')

                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=account,
                        debit=ld.debit,
                        credit=ld.credit,
                        description=ld.description or '',
                    )

                logger.info(
                    f'Rebuilt JE {journal_entry.number} for payroll {payroll.id} '
                    f'with {len(new_lines)} lines'
                )
                return journal_entry

        except Exception as e:
            logger.error(
                f'Failed to rebuild JE {journal_entry.number} '
                f'for payroll {payroll.id}: {e}',
                exc_info=True
            )
            return journal_entry
    
    def _prepare_journal_lines(self, payroll):
        """
        Prepare journal entry lines for payroll.

        Debit side  — broken down by earning type to leaf accounts:
          50210  Salary Expense (basic salary)
          50220  Allowances (non-basic earnings)
          50230  Bonuses (REWARD_ lines)
          50240  Social Insurance (employer share — if any)

        Credit side — net + each deduction line + rounding diff:
          payment_account  net salary
          20210            social insurance payable (employee share)
          10350            advance deductions
          20200            other deductions
          59000            rounding difference
        """
        from financial.models import ChartOfAccounts

        lines = []

        try:
            # ── Load accounts once ────────────────────────────────────────────
            def get_acc(code):
                return ChartOfAccounts.objects.filter(code=code, is_active=True).first()

            acc_basic      = get_acc('50210')   # الراتب الأساسي
            acc_allowances = get_acc('50220')   # البدلات
            acc_bonus      = get_acc('50230')   # المكافآت
            acc_ins_exp    = get_acc('50240')   # التأمينات (حصة صاحب العمل)
            acc_ins_pay    = get_acc('20210')   # التأمينات مستحقة الدفع
            acc_deductions = get_acc('20200')   # مستحقات الرواتب
            acc_advance    = get_acc('10350')   # سلف الموظفين
            acc_rounding   = get_acc('59000')   # فروق التقريب

            if not acc_basic:
                logger.error('Salary account 50210 not found')
                return []

            emp_name       = payroll.employee.get_full_name_ar()
            correct_gross  = payroll.correct_gross_salary
            correct_net    = payroll.correct_net_salary

            # ── Debit: break gross into leaf accounts ─────────────────────────
            earning_lines = list(
                payroll.lines.filter(component_type='earning')
                .exclude(code__in=['INSURABLE_SALARY', 'BASIC_SALARY'])
            )

            # Basic salary → 50210
            if acc_basic:
                lines.append(JournalEntryLineData(
                    account_code=acc_basic.code,
                    debit=payroll.basic_salary,
                    credit=Decimal('0'),
                    description=f'الأجر الأساسي - {emp_name}'
                ))

            # Earning lines → 50220 (allowances) or 50230 (rewards/bonuses)
            for el in earning_lines:
                if el.amount <= 0:
                    continue
                if el.code.startswith('REWARD_') and acc_bonus:
                    acc_code = acc_bonus.code
                elif acc_allowances:
                    acc_code = acc_allowances.code
                else:
                    acc_code = acc_basic.code   # fallback
                lines.append(JournalEntryLineData(
                    account_code=acc_code,
                    debit=el.amount,
                    credit=Decimal('0'),
                    description=f'{el.name} - {emp_name}'
                ))

            # ── Credit: net salary ────────────────────────────────────────────
            if payroll.payment_account:
                lines.append(JournalEntryLineData(
                    account_code=payroll.payment_account.code,
                    debit=Decimal('0'),
                    credit=correct_net,
                    description=f'صافي راتب {emp_name}'
                ))
            else:
                logger.warning(f'Payroll {payroll.id} has no payment account — net credit skipped')

            # ── Credit: each deduction line ───────────────────────────────────
            deduction_lines = payroll.lines.filter(
                component_type='deduction'
            ).order_by('order')

            for dl in deduction_lines:
                if dl.amount <= 0:
                    continue

                if dl.code in ('SOCIAL_INSURANCE', 'SOCIAL_INSURANCE_EMP') and acc_ins_pay:
                    acc_code = acc_ins_pay.code
                elif dl.code.startswith('ADVANCE_') and acc_advance:
                    acc_code = acc_advance.code
                elif acc_deductions:
                    acc_code = acc_deductions.code
                else:
                    logger.warning(f'No account for deduction {dl.code} on payroll {payroll.id}')
                    continue

                lines.append(JournalEntryLineData(
                    account_code=acc_code,
                    debit=Decimal('0'),
                    credit=dl.amount,
                    description=f'{dl.name} - {emp_name}'
                ))

            # ── Rounding difference → 59000 ───────────────────────────────────
            total_debit  = sum(l.debit  for l in lines)
            total_credit = sum(l.credit for l in lines)
            diff = (total_debit - total_credit).quantize(Decimal('0.01'))

            if abs(diff) >= Decimal('0.01'):
                if not acc_rounding:
                    logger.warning(f'Payroll {payroll.id}: rounding diff {diff} but 59000 not found')
                elif diff > 0:
                    lines.append(JournalEntryLineData(
                        account_code=acc_rounding.code,
                        debit=Decimal('0'),
                        credit=diff,
                        description='فرق تقريب رواتب'
                    ))
                else:
                    lines.append(JournalEntryLineData(
                        account_code=acc_rounding.code,
                        debit=abs(diff),
                        credit=Decimal('0'),
                        description='فرق تقريب رواتب'
                    ))
                logger.debug(f'Payroll {payroll.id}: rounding diff {diff} → 59000')

        except Exception as e:
            logger.error(f'Error preparing journal lines for payroll {payroll.id}: {e}', exc_info=True)
            return []

        return lines
    
    def _generate_description(self, payroll):
        """Generate journal entry description."""
        return (
            f'راتب {payroll.employee.get_full_name_ar()} - '
            f'{payroll.month.strftime("%Y-%m")}'
        )
