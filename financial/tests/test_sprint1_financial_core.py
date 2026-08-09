import pytest
from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod, JournalEntry, JournalEntryLine
from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.services.ledger_core_service import LedgerCoreService
from financial.services.period_control_service import PeriodControlService
from financial.services.opening_balance_service import OpeningBalanceService, OpeningBalanceValidationService
from financial.exceptions import FinancialCoreError, ImmutableLedgerError, PeriodClosedError, UnbalancedEntryError

User = get_user_model()


class FinancialCoreSprint1TestSuite(TestCase):
    """
    مجموعة اختبارات المكونات الأساسية لـ Sprint 1 (Financial Core Engine v1.8)
    """

    def setUp(self):
        self.user = User.objects.create_user(username="fin_admin", password="password123")

        # إنشاء أنواع الحسابات
        self.asset_type = AccountType.objects.create(code="AST_TEST", name="أصول", nature="debit")
        self.equity_type = AccountType.objects.create(code="EQ_TEST", name="حقوق ملكية", nature="credit")

        # إنشاء حسابات أستاذ فرعية فعالة
        self.cash_account = ChartOfAccounts.objects.create(
            code="10100_T", name="الصندوق التجريبي", account_type=self.asset_type, is_active=True, is_leaf=True
        )
        self.capital_account = ChartOfAccounts.objects.create(
            code="30100_T", name="رأس المال التجريبي", account_type=self.equity_type, is_active=True, is_leaf=True
        )

        # إنشاء سنة مالية وفترة محاسبية
        self.fiscal_year = PeriodControlService.create_fiscal_year_with_periods(
            year_code="FY2026_TEST",
            name="السنة المالية 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31)
        )
        self.period = self.fiscal_year.periods.first()

    def test_01_fiscal_year_and_period_generation(self):
        """التحقق من إنشاء السنة المالية وتوليد 12 فترة محاسبية شهرية"""
        self.assertEqual(self.fiscal_year.periods.count(), 12)
        self.assertEqual(self.period.status, "open")
        self.assertTrue(self.period.can_post_entries())

    def test_02_ledger_core_create_draft_and_post_entry(self):
        """التحقق من إنشاء قيد مسودة ونشره بنجاح وحصانته"""
        lines_data = [
            {"account": self.cash_account, "debit": Decimal("1000.00"), "credit": Decimal("0.00")},
            {"account": self.capital_account, "debit": Decimal("0.00"), "credit": Decimal("1000.00")},
        ]
        draft = LedgerCoreService.create_draft_entry(
            date=date(2026, 1, 15),
            description="إيداع رأس مال أول المدة",
            reference="REF-001",
            entry_type="manual",
            created_by=self.user,
            lines_data=lines_data
        )

        self.assertEqual(draft.status, "draft")
        self.assertEqual(draft.total_debit, Decimal("1000.00"))

        posted = LedgerCoreService.post_entry(
            entry_id=draft.id,
            user=self.user,
            posting_source="MANUAL_JOURNAL",
            posting_reference="REF-001"
        )

        self.assertEqual(posted.status, "posted")
        self.assertIsNotNone(posted.posted_at)

        # اختبار حماية ORM (Layer 2 Immutability Protection)
        with self.assertRaises(ImmutableLedgerError):
            posted.description = "تعديل محظور للقيد المرحل"
            posted.save()

        with self.assertRaises(ImmutableLedgerError):
            posted.delete()

    def test_03_unbalanced_entry_raises_exception(self):
        """التحقق من رفض القيد غير المتوازن"""
        lines_data = [
            {"account": self.cash_account, "debit": Decimal("1000.00"), "credit": Decimal("0.00")},
            {"account": self.capital_account, "debit": Decimal("0.00"), "credit": Decimal("500.00")},
        ]
        with self.assertRaises(FinancialCoreError):
            LedgerCoreService.create_draft_entry(
                date=date(2026, 1, 15),
                description="قيد غير متوازن",
                reference="REF-UNBAL",
                entry_type="manual",
                created_by=self.user,
                lines_data=lines_data
            )

    def test_04_controlled_reversal_entry_flow(self):
        """التحقق من تنفيذ العكس المحاسبي المحكوم صراحة عبر القائمة البيضاء"""
        lines_data = [
            {"account": self.cash_account, "debit": Decimal("500.00"), "credit": Decimal("0.00")},
            {"account": self.capital_account, "debit": Decimal("0.00"), "credit": Decimal("500.00")},
        ]
        original = LedgerCoreService.create_draft_entry(
            date=date(2026, 1, 15),
            description="قيد أصلي المراد عكسه",
            reference="REF-ORIG",
            entry_type="manual",
            created_by=self.user,
            lines_data=lines_data
        )
        posted_original = LedgerCoreService.post_entry(original.id, self.user)

        # تنفيذ العكس
        reversal = LedgerCoreService.reverse_entry(
            entry_id=posted_original.id,
            user=self.user,
            reversal_reason="خطأ في الإدخال"
        )

        self.assertEqual(reversal.status, "posted")
        self.assertTrue(reversal.is_reversal)
        self.assertEqual(reversal.original_entry.id, posted_original.id)

        # التحقق من أن القيد الأصلي تم تحديث مرجع العكس الخاص به عبر القائمة البيضاء
        posted_original.refresh_from_db()
        self.assertEqual(posted_original.reversed_by_entry.id, reversal.id)

    def test_05_period_close_draft_guard(self):
        """التحقق من حماية إغلاق الفترة المالية عند وجود مسودات قيود"""
        lines_data = [
            {"account": self.cash_account, "debit": Decimal("100.00"), "credit": Decimal("0.00")},
            {"account": self.capital_account, "debit": Decimal("0.00"), "credit": Decimal("100.00")},
        ]
        LedgerCoreService.create_draft_entry(
            date=self.period.start_date,
            description="مسودة معلقة في الفترة",
            reference="REF-DRAFT",
            entry_type="manual",
            created_by=self.user,
            lines_data=lines_data
        )

        with self.assertRaises(PeriodClosedError):
            PeriodControlService.close_period(self.period.id, user=self.user)

    def test_06_opening_balance_batch_pipeline_and_immutability(self):
        """التحقق من إنشاء ونشر وقفل دفعة الأرصدة الافتتاحية"""
        batch = OpeningBalanceBatch.objects.create(
            fiscal_year=self.fiscal_year,
            batch_number="OB-2026-TEST",
            description="الأرصدة الافتتاحية لسنة 2026",
            status="draft",
            created_by=self.user
        )
        OpeningBalanceLine.objects.create(
            batch=batch,
            account=self.cash_account,
            debit=Decimal("5000.00"),
            credit=Decimal("0.00")
        )
        OpeningBalanceLine.objects.create(
            batch=batch,
            account=self.capital_account,
            debit=Decimal("0.00"),
            credit=Decimal("5000.00")
        )

        self.assertEqual(batch.status, "draft")

        posted_batch = OpeningBalanceService.post(batch.id, self.user)
        self.assertEqual(posted_batch.status, "posted")
        self.assertIsNotNone(posted_batch.journal_entry)
        self.assertEqual(posted_batch.journal_entry.status, "posted")

        # اختارات حصانة الدفعة الافتتاحية المرحِلة
        with self.assertRaises(ImmutableLedgerError):
            posted_batch.description = "تعديل دفعة مرحلة"
            posted_batch.save()

        with self.assertRaises(ImmutableLedgerError):
            posted_batch.delete()
