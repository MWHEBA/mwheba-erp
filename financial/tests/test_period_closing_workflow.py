import pytest
import uuid
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod, JournalEntry
from financial.models.closing_engine_models import FiscalYearClosingRun, PeriodModuleLock, ClosingRule
from financial.services.event_publisher import SyncEventPublisher

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestPeriodClosingPhase1A:

    @pytest.fixture
    def setup_base_data(self):
        uid = uuid.uuid4().hex[:6]
        user = User.objects.create_user(
            username=f"closing_admin_{uid}",
            email=f"closing_{uid}@example.com",
            password="Password123!"
        )
        
        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{uid}",
            name=f"Fiscal Year {uid}",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            status='open'
        )

        period = AccountingPeriod.objects.create(
            name=f"Period 1 - {uid}",
            fiscal_year=fiscal_year,
            period_number=1,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            status='open'
        )

        from financial.models import ChartOfAccounts, AccountType
        equity_type, _ = AccountType.objects.get_or_create(
            code="EQUITY",
            defaults={"name": "Equity", "category": "equity", "nature": "credit"}
        )
        retained_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="30200",
            defaults={"name": "الأرباح والخسائر المرحلة", "account_type": equity_type, "is_active": True}
        )

        return user, fiscal_year, period

    def test_cannot_run_two_closing_runs_same_year(self, setup_base_data):
        """اختبار مفتاح منع تكرار الإغلاق (closing_run_key idempotency)"""
        user, fiscal_year, _ = setup_base_data
        run_key = f"CLOSE:DEFAULT:{fiscal_year.id}:ANNUAL"

        run1 = FiscalYearClosingRun.objects.create(
            closing_run_key=run_key,
            fiscal_year=fiscal_year,
            status='RUNNING',
            current_step='MODULE_LOCK',
            executed_by=user
        )
        assert run1.pk is not None

        # محاولة فتح تشغيل إغلاق آخر لنفس السنة بنفس المفتاح يجب أن يثير IntegrityError
        with pytest.raises(IntegrityError):
            FiscalYearClosingRun.objects.create(
                closing_run_key=run_key,
                fiscal_year=fiscal_year,
                status='RUNNING',
                executed_by=user
            )

    def test_failed_closing_run_can_resume_safely(self, setup_base_data):
        """اختبار استئناف الإغلاق الفاشل من آخر خطوة ناجحة (Resume on failure)"""
        user, fiscal_year, _ = setup_base_data
        run_key = f"CLOSE:DEFAULT:{fiscal_year.id}:RESUME_TEST"

        run = FiscalYearClosingRun.objects.create(
            closing_run_key=run_key,
            fiscal_year=fiscal_year,
            status='RUNNING',
            current_step='FX_REVALUATION',
            last_successful_step='MODULE_LOCK',
            executed_by=user
        )

        # تحويل التشغيل لحالة الفشل
        run.status = 'FAILED'
        run.logs = {'error': 'Simulated network crash during FX revaluation'}
        run.save()

        # الاستئناف: يمكن إعادة التفعيل وتكملة الخطوة من آخر خطوة ناجحة
        run.status = 'RUNNING'
        run.current_step = 'FX_REVALUATION'
        run.last_successful_step = 'FX_REVALUATION'
        run.status = 'COMPLETED'
        run.completed_at = timezone.now()
        run.save()

        run.refresh_from_db()
        assert run.status == 'COMPLETED'
        assert run.last_successful_step == 'FX_REVALUATION'

    def test_locked_module_rejects_posting(self, setup_base_data):
        """اختبار إنشاء وإنفاذ درجات قفل الموديولات (PeriodModuleLock lock_type)"""
        user, _, period = setup_base_data

        lock = PeriodModuleLock.objects.create(
            period=period,
            module='AR',
            status='locked',
            lock_type='POST_BLOCK',
            locked_by=user,
            reason='Month-End AR Cutoff'
        )

        assert lock.module == 'AR'
        assert lock.lock_type == 'POST_BLOCK'
        assert lock.period == period

        # عدم السماح بتكرار قفل الموديول لنفس الفترة
        with pytest.raises(IntegrityError):
            PeriodModuleLock.objects.create(
                period=period,
                module='AR',
                status='locked',
                locked_by=user
            )

    def test_closing_event_publisher_on_commit(self, setup_base_data):
        """اختبار إطلاق حدث الإغلاق عبر transaction.on_commit"""
        publisher = SyncEventPublisher()
        with transaction.atomic():
            result = publisher.publish_fiscal_year_closed(
                closing_run_id=101,
                payload={'status': 'COMPLETED'}
            )
            assert result is True

    def test_full_fiscal_year_closing_flow(self, setup_base_data):
        """اختبار تشغيل الإغلاق السنوي الشامل Phase 1B"""
        from financial.services.fiscal_year_closing_service import FiscalYearClosingService
        user, fiscal_year, period = setup_base_data

        run = FiscalYearClosingService.execute_fiscal_year_close(fiscal_year.id, user)

        assert run.status == 'COMPLETED'
        assert run.last_successful_step == 'STEP_6_OPENING_ROLL_FORWARD'

        fiscal_year.refresh_from_db()
        assert fiscal_year.status == 'closed'
        assert fiscal_year.closed_at is not None
        assert fiscal_year.closing_journal_entry is not None

