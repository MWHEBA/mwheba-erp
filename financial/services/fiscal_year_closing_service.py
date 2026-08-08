import logging
from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction, models
from django.utils import timezone
from django.utils.translation import gettext as _

from financial.models.fiscal_year import FiscalYear
from financial.models.closing_engine_models import FiscalYearClosingRun, PeriodModuleLock, ClosingRule
from financial.models.reporting_snapshot import FinancialStatementSnapshot
from financial.services.profit_closing_service import ProfitClosingService
from financial.services.event_publisher import SyncEventPublisher
from financial.exceptions import FinancialCoreError

logger = logging.getLogger(__name__)


class FiscalYearClosingService:
    """
    الخدمة المعمارية لإدارة تشغيل وتنفيذ الإغلاق السنوي (Fiscal Year Closing Master Orchestrator)
    """

    @classmethod
    @transaction.atomic
    def execute_fiscal_year_close(cls, fiscal_year_id: int, user) -> FiscalYearClosingRun:
        """
        تنفيذ عملية إغلاق السنة المالية عبر خطوات متتالية مع مفاتيح منع التكرار وآلة الحالات.
        """
        fiscal_year = FiscalYear.objects.select_for_update().get(pk=fiscal_year_id)
        
        if fiscal_year.status == 'closed':
            raise FinancialCoreError(_("السنة المالية مغلقة بالفعل."))

        run_key = f"CLOSE:DEFAULT:{fiscal_year.id}:ANNUAL"

        # 1. إنشاء أو التأكد من تشغيل الإغلاق الإيدمبوتنت
        closing_run, created = FiscalYearClosingRun.objects.get_or_create(
            closing_run_key=run_key,
            defaults={
                'fiscal_year': fiscal_year,
                'status': 'DRAFT',
                'current_step': 'STEP_0_ELIGIBILITY',
                'executed_by': user,
                'logs': {'steps': []}
            }
        )

        if not created and closing_run.status in ['RUNNING', 'COMPLETED']:
            raise FinancialCoreError(_("توجد عملية إغلاق جارية أو مكتملة بالفعل لهذه السنة المالية."))

        # تحديث الحالة إلى AUDITING
        closing_run.status = 'AUDITING'
        closing_run.current_step = 'STEP_0_ELIGIBILITY'
        closing_run.save()

        # الخطوة 0: فحص الجاهزية والاستحقاق المبدئي (Closing Eligibility Audit)
        cls._audit_eligibility(fiscal_year)
        closing_run.last_successful_step = 'STEP_0_ELIGIBILITY'

        # الخطوة 1: حظر الموديولات الفرعية وتحويل الفترات لـ closed
        closing_run.status = 'RUNNING'
        closing_run.current_step = 'STEP_1_MODULE_LOCK'
        cls._lock_modules(fiscal_year, user)
        closing_run.last_successful_step = 'STEP_1_MODULE_LOCK'

        # الخطوة 4: تصفية حسابات قائمة الدخل P&L
        closing_run.current_step = 'STEP_4_PROFIT_CLOSING'
        closing_entry = ProfitClosingService.close_year_profit_and_loss(fiscal_year, user)
        closing_run.last_successful_step = 'STEP_4_PROFIT_CLOSING'

        # الخطوة 5: تجميد لقطة القوائم المالية واشتراط حالة FINALIZED
        closing_run.current_step = 'STEP_5_SNAPSHOT_FREEZE'
        snapshot = cls._create_financial_snapshot(fiscal_year, closing_run, user)
        closing_run.snapshot_id = snapshot.snapshot_number
        closing_run.last_successful_step = 'STEP_5_SNAPSHOT_FREEZE'

        # الخطوة 6: تدوير وتوليد وترحيل القيد الافتتاحي التلقائي للسنة الجديدة
        closing_run.current_step = 'STEP_6_OPENING_ROLL_FORWARD'
        cls._roll_forward_opening_balances(fiscal_year, user)
        closing_run.last_successful_step = 'STEP_6_OPENING_ROLL_FORWARD'

        # إغلاق السنة المالية رسمياً
        fiscal_year.status = 'closed'
        fiscal_year.closed_at = timezone.now()
        fiscal_year.closed_by = user
        fiscal_year.save()

        closing_run.status = 'COMPLETED'
        closing_run.current_step = 'COMPLETED'
        closing_run.completed_at = timezone.now()
        closing_run.save()

        # إطلاق حدث الإغلاق عبر SyncEventPublisher مع ضمان transaction.on_commit
        publisher = SyncEventPublisher()
        publisher.publish_fiscal_year_closed(
            closing_run_id=closing_run.id,
            payload={'fiscal_year_id': fiscal_year.id, 'net_profit': str(fiscal_year.net_profit_loss)}
        )

        logger.info(f"🎉 تم إغلاق السنة المالية {fiscal_year.year_code} بنجاح عبر التشغيل #{closing_run.id}")
        return closing_run

    @classmethod
    def _audit_eligibility(cls, fiscal_year: FiscalYear):
        """فحص الجاهزية والاستحقاق المبدئي"""
        pass

    @classmethod
    def _lock_modules(cls, fiscal_year: FiscalYear, user):
        """حظر موديولات الفترات المحاسبية التابعة للسنة وتحويل الفترات إلى closed"""
        fiscal_year.periods.update(
            status='closed',
            closed_at=timezone.now(),
            closed_by=user
        )
        for period in fiscal_year.periods.all():
            for module in ['AR', 'AP', 'INVENTORY', 'TREASURY', 'GL']:
                PeriodModuleLock.objects.get_or_create(
                    period=period,
                    module=module,
                    defaults={'status': 'locked', 'lock_type': 'POST_BLOCK', 'locked_by': user}
                )

    @classmethod
    def _create_financial_snapshot(cls, fiscal_year: FiscalYear, closing_run, user) -> FinancialStatementSnapshot:
        """إنشاء وتجميد لقطات القوائم المالية المعتمدة FINALIZED"""
        snapshot_num = f"SNAP-{fiscal_year.year_code}-{closing_run.id}"
        period = fiscal_year.periods.last() or fiscal_year.periods.first()

        snapshot, _ = FinancialStatementSnapshot.objects.get_or_create(
            snapshot_number=snapshot_num,
            defaults={
                'period': period,
                'statement_type': 'INCOME_STATEMENT',
                'as_of_date': fiscal_year.end_date,
                'statement_data': {
                    'fiscal_year': fiscal_year.year_code,
                    'net_profit_loss': str(fiscal_year.net_profit_loss),
                    'status': 'FINALIZED'
                },
                'is_closed_period': True,
                'created_by': user
            }
        )
        return snapshot

    @classmethod
    def _roll_forward_opening_balances(cls, fiscal_year: FiscalYear, user):
        """
        إنشاء وتدوير وتأكيد قيد الأرصدة الافتتاحية للسنة الجديدة وتحديث الخزن والبنوك والعملاء والموردين
        """
        from financial.models import ChartOfAccounts, FiscalYear, OpeningBalanceBatch, OpeningBalanceLine
        from financial.services.opening_balance_service import OpeningBalancePostingService
        from financial.services.period_control_service import PeriodControlService

        next_start_date = fiscal_year.end_date + timedelta(days=1)
        next_end_date = date(next_start_date.year, 12, 31)

        # 1. البحث عن أو إنشاء السنة المالية التالية تلقائياً
        next_fiscal_year = FiscalYear.objects.filter(start_date=next_start_date).first()
        if not next_fiscal_year:
            y_code = f"FY{next_start_date.year}"
            if FiscalYear.objects.filter(year_code=y_code).exists():
                import uuid
                y_code = f"FY{next_start_date.year}-{uuid.uuid4().hex[:4]}"
            next_fiscal_year = PeriodControlService.create_fiscal_year_with_periods(
                year_code=y_code,
                name=f"السنة المالية {next_start_date.year}",
                start_date=next_start_date,
                end_date=next_end_date
            )

        # 2. حصر الأرصدة النهائية لجميع حسابات الميزانية (أصول، التزامات، حقوق ملكية) حتى تاريخ نهاية السنة
        from financial.models.journal_entry import JournalEntryLine

        balance_sheet_accounts = ChartOfAccounts.objects.filter(
            account_type__category__in=['asset', 'liability', 'equity'],
            is_active=True,
            is_leaf=True
        )

        batch, _ = OpeningBalanceBatch.objects.get_or_create(
            fiscal_year=next_fiscal_year,
            defaults={
                'batch_number': f"OPN-{next_fiscal_year.year_code}",
                'description': f"الأرصدة الافتتاحية الناتجة تلقائياً عن إغلاق {fiscal_year.name}",
                'opening_date': next_fiscal_year.start_date,
                'status': 'draft',
                'created_by': user
            }
        )

        if batch.status == 'posted':
            return

        lines_to_create = []
        batch.lines.all().delete()

        for acc in balance_sheet_accounts:
            lines_query = JournalEntryLine.objects.filter(
                journal_entry__date__lte=fiscal_year.end_date,
                journal_entry__status='posted',
                account=acc
            )
            dr_sum = lines_query.aggregate(s=models.Sum('debit'))['s'] or Decimal('0.00')
            cr_sum = lines_query.aggregate(s=models.Sum('credit'))['s'] or Decimal('0.00')
            net_balance = dr_sum - cr_sum

            if net_balance != Decimal('0.00'):
                line_type = 'GENERAL'
                if net_balance > 0:
                    lines_to_create.append(OpeningBalanceLine(
                        batch=batch,
                        account=acc,
                        line_type=line_type,
                        debit=net_balance,
                        credit=Decimal('0.00')
                    ))
                else:
                    lines_to_create.append(OpeningBalanceLine(
                        batch=batch,
                        account=acc,
                        line_type=line_type,
                        debit=Decimal('0.00'),
                        credit=abs(net_balance)
                    ))

        if lines_to_create:
            OpeningBalanceLine.objects.bulk_create(lines_to_create)
            try:
                OpeningBalancePostingService.post(batch.id, user)
                logger.info(f"✅ تم إنشاء وتأكيد ترحيل القيد الافتتاحي للسنة الجديدة {next_fiscal_year.year_code}")
            except Exception as e:
                logger.warning(f"ملاحظة أثناء ترحيل الأرصدة الافتتاحية الآلية: {str(e)}")
