import logging
from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone
from django.utils.translation import gettext as _

from financial.models.fiscal_year import FiscalYear
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.exceptions import FinancialCoreError
from core.services.sequence_service import SequenceService
from core.enums.document_types import DocumentType

logger = logging.getLogger(__name__)


class ProfitClosingService:
    """
    خدمة تصفية أرباح وخسائر السنة المالية (P&L Income Statement Closing Service)
    مسؤولة عن تصفية كافة حسابات الإيرادات والمصروفات بالعملة الأساسية (EGP)
    وترحيل صافي الربح / الخسارة إلى حساب الأرباح والخسائر المرحلة المعين.
    """

    @classmethod
    @transaction.atomic
    def close_year_profit_and_loss(cls, fiscal_year: FiscalYear, user) -> JournalEntry:
        """
        إنهاء وتصفية حسابات الإيرادات والمصروفات وتوليد قيد التصفية السنوي
        """
        # 1. الحصول على حساب الأرباح المرحلة المعتمد
        retained_account = fiscal_year.get_effective_retained_earnings_account()
        if not retained_account:
            raise FinancialCoreError(_("لا يوجد حساب معتمد للأرباح والخسائر المرحلة للسنة المالية."))

        # 2. حصر جميع الحسابات ذات الحركة من نوع الإيرادات والمصروفات
        revenue_accounts = ChartOfAccounts.objects.filter(
            account_type__category='revenue',
            is_active=True
        )
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category='expense',
            is_active=True
        )

        lines_to_create = []
        total_revenue_egp = Decimal('0.00')
        total_expense_egp = Decimal('0.00')

        # 3. توليد رقم قيد اليومية عبر SequenceService
        jv_number = SequenceService.get_next_number(DocumentType.JOURNAL_ENTRY, date=fiscal_year.end_date)

        closing_entry = JournalEntry.objects.create(
            number=jv_number,
            date=fiscal_year.end_date,
            entry_type='closing',
            status='posted',
            description=f"قيد تصفية أرباح وخسائر السنة المالية {fiscal_year.name} ({fiscal_year.year_code})",
            reference=fiscal_year.year_code,
            reference_type='FISCAL_YEAR_CLOSE',
            reference_id=fiscal_year.id,
            source_module='financial',
            source_model='FiscalYear',
            source_id=fiscal_year.id,
            created_by=user,
            posted_by=user,
            posted_at=timezone.now()
        )

        # 4. تصفية حسابات الإيرادات (الدائنة بطبيعتها -> تجعل مدينة)
        for acc in revenue_accounts:
            # حصر صافي الحركة للسنة المالية
            lines_query = JournalEntryLine.objects.filter(
                journal_entry__date__range=(fiscal_year.start_date, fiscal_year.end_date),
                journal_entry__status='posted',
                account=acc
            ).exclude(journal_entry__entry_type='closing')

            dr_sum = lines_query.aggregate(s=models.Sum('debit'))['s'] or Decimal('0.00')
            cr_sum = lines_query.aggregate(s=models.Sum('credit'))['s'] or Decimal('0.00')
            net_balance = cr_sum - dr_sum  # الرصيد الدائن الصافي للإيراد

            if net_balance != Decimal('0.00'):
                total_revenue_egp += net_balance
                if net_balance > 0:
                    lines_to_create.append(JournalEntryLine(
                        journal_entry=closing_entry,
                        account=acc,
                        debit=net_balance,
                        credit=Decimal('0.00'),
                        description=f"إقفال حساب الإيراد {acc.code} - {acc.name}"
                    ))
                else:
                    lines_to_create.append(JournalEntryLine(
                        journal_entry=closing_entry,
                        account=acc,
                        debit=Decimal('0.00'),
                        credit=abs(net_balance),
                        description=f"إقفال حساب الإيراد {acc.code} - {acc.name}"
                    ))

        # 5. تصفية حسابات المصروفات (المدينة بطبيعتها -> تجعل دائنة)
        for acc in expense_accounts:
            lines_query = JournalEntryLine.objects.filter(
                journal_entry__date__range=(fiscal_year.start_date, fiscal_year.end_date),
                journal_entry__status='posted',
                account=acc
            ).exclude(journal_entry__entry_type='closing')

            dr_sum = lines_query.aggregate(s=models.Sum('debit'))['s'] or Decimal('0.00')
            cr_sum = lines_query.aggregate(s=models.Sum('credit'))['s'] or Decimal('0.00')
            net_balance = dr_sum - cr_sum  # الرصيد المدين الصافي للمصروف

            if net_balance != Decimal('0.00'):
                total_expense_egp += net_balance
                if net_balance > 0:
                    lines_to_create.append(JournalEntryLine(
                        journal_entry=closing_entry,
                        account=acc,
                        debit=Decimal('0.00'),
                        credit=net_balance,
                        description=f"إقفال حساب المصروف {acc.code} - {acc.name}"
                    ))
                else:
                    lines_to_create.append(JournalEntryLine(
                        journal_entry=closing_entry,
                        account=acc,
                        debit=abs(net_balance),
                        credit=Decimal('0.00'),
                        description=f"إقفال حساب المصروف {acc.code} - {acc.name}"
                    ))

        # 6. حساب صافي الربح أو الخسارة وترحيله لحساب الأرباح المرحلة
        net_profit = total_revenue_egp - total_expense_egp

        if net_profit > 0:
            # ربح صاِف -> دائن في حساب الأرباح المرحلة
            lines_to_create.append(JournalEntryLine(
                journal_entry=closing_entry,
                account=retained_account,
                debit=Decimal('0.00'),
                credit=net_profit,
                description=f"ترحيل صافي أرباح العام للسنة المالية {fiscal_year.name}"
            ))
        elif net_profit < 0:
            # خسارة صافية -> مدين في حساب الأرباح المرحلة
            lines_to_create.append(JournalEntryLine(
                journal_entry=closing_entry,
                account=retained_account,
                debit=abs(net_profit),
                credit=Decimal('0.00'),
                description=f"ترحيل صافي خسائر العام للسنة المالية {fiscal_year.name}"
            ))

        JournalEntryLine.objects.bulk_create(lines_to_create)

        # 7. تحديث السنة المالية بصافي الربح/الخسارة وقيد الإغلاق
        fiscal_year.net_profit_loss = net_profit
        fiscal_year.closing_journal_entry = closing_entry
        fiscal_year.save(update_fields=['net_profit_loss', 'closing_journal_entry'])

        logger.info(f"✅ تم إنشاء قيد تصفية الأرباح والخسائر #{closing_entry.number} بصافي: {net_profit} EGP")
        return closing_entry
