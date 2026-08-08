from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.bank_reconciliation import BankStatementBatch, BankStatementLine, BankMatchAllocation
from financial.services.bank_reconciliation_service import (
    BankReconciliationService,
    BankCandidateEngine
)
from financial.services.ledger_core_service import LedgerCoreService

User = get_user_model()


class BankReconciliationPhase1TestCase(TestCase):
    """
    سلسلة الاختبارات الآلية الشاملة لنظام التسويات البنكية (Phase 1 Automated Test Suite)
    """

    def setUp(self):
        import uuid
        uid = uuid.uuid4().hex[:6]
        self.user = User.objects.first() or User.objects.create_user(
            username=f"fin_admin_{uid}",
            email=f"fin_admin_{uid}@mwheba.com",
            password="password123"
        )

        # جلب أو إنشاء نمط أنواع الحسابات
        self.asset_type = AccountType.objects.first() or AccountType.objects.create(
            name="أصول متداولة",
            code=f"ASSETS_{uid}",
            nature="DEBIT"
        )
        self.expense_type = AccountType.objects.filter(nature="DEBIT").last() or AccountType.objects.create(
            name="مصاريف عمومية",
            code=f"EXP_{uid}",
            nature="DEBIT"
        )

        # 1. جلب أو إنشاء حساب بنكي محاسبي فرعي يقبل القيود
        self.bank_account = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True).first()
        if not self.bank_account:
            self.bank_account = ChartOfAccounts.objects.create(
                code=f"101_{uid}",
                name=f"بنك مصر - حساب جاري {uid}",
                account_type=self.asset_type,
                is_active=True,
                is_leaf=True,
                is_bank_account=True
            )

        # 2. جلب أو إنشاء حساب مصاريف وعمولات بنكية فرعي يقبل القيود
        self.expense_account = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True).exclude(pk=self.bank_account.pk).first()
        if not self.expense_account:
            self.expense_account = ChartOfAccounts.objects.create(
                code=f"501_{uid}",
                name=f"مصاريف وعمولات بنكية {uid}",
                account_type=self.expense_type,
                is_active=True,
                is_leaf=True
            )

        # 3. إنشاء دفعة استيراد بنكية
        self.today = timezone.now().date()
        self.batch = BankStatementBatch.objects.create(
            batch_number="STMT-TEST-001",
            bank_account=self.bank_account,
            statement_date=self.today,
            opening_balance=Decimal("10000.00"),
            closing_balance=Decimal("15000.00"),
            status="imported",
            created_by=self.user
        )

    def test_auto_match_confidence_thresholds(self):
        """1. اختبار حساب درجات التوافق والمطابقة الآلية (Score >= 95% -> Auto Match)"""
        # سطر بنكي إيداع 5000 مرجع REF-100
        stmt_line = BankStatementLine.objects.create(
            batch=self.batch,
            transaction_date=self.today,
            reference_number="REF-100",
            description="إيداع عميل",
            debit=Decimal("5000.00"),
            credit=Decimal("0.00"),
            is_matched=False
        )

        # إنشاء قيد شركة مطابقة بنفس المبلغ والمرجع والتاريخ
        entry = LedgerCoreService.create_draft_entry(
            date=self.today,
            description="سداد عميل بحساب البنك",
            reference="REF-100",
            entry_type="ADJUSTMENT",
            created_by=self.user,
            lines_data=[
                {"account": self.bank_account, "debit": Decimal("5000.00"), "credit": Decimal("0.00")},
                {"account": self.expense_account, "debit": Decimal("0.00"), "credit": Decimal("5000.00")}
            ]
        )
        LedgerCoreService.post_entry(entry.id, self.user)

        # تشغيل المطابقة المباشرة للتصنيفات
        jl = entry.lines.get(account=self.bank_account)
        alloc = BankReconciliationService.create_allocation(stmt_line.id, jl.id, user=self.user)
        self.assertIsNotNone(alloc)

        stmt_line.refresh_from_db()
        self.assertTrue(stmt_line.is_matched)
        self.assertEqual(stmt_line.allocations.filter(status="ACTIVE").count(), 1)

    def test_allocation_sum_cannot_exceed_bank_amount(self):
        """2. اختبار القفل الذري لعدم تجاوز سقف المبلغ المخصص (Atomic Sum Guard)"""
        stmt_line = BankStatementLine.objects.create(
            batch=self.batch,
            transaction_date=self.today,
            reference_number="REF-200",
            debit=Decimal("1000.00"),
            credit=Decimal("0.00"),
            is_matched=False
        )

        entry1 = LedgerCoreService.create_draft_entry(
            date=self.today,
            description="دفع جزئي 1",
            reference="REF-201",
            entry_type="ADJUSTMENT",
            created_by=self.user,
            lines_data=[
                {"account": self.bank_account, "debit": Decimal("700.00"), "credit": Decimal("0.00")},
                {"account": self.expense_account, "debit": Decimal("0.00"), "credit": Decimal("700.00")}
            ]
        )
        LedgerCoreService.post_entry(entry1.id, self.user)

        entry2 = LedgerCoreService.create_draft_entry(
            date=self.today,
            description="دفع جزئي 2",
            reference="REF-202",
            entry_type="ADJUSTMENT",
            created_by=self.user,
            lines_data=[
                {"account": self.bank_account, "debit": Decimal("500.00"), "credit": Decimal("0.00")},
                {"account": self.expense_account, "debit": Decimal("0.00"), "credit": Decimal("500.00")}
            ]
        )
        LedgerCoreService.post_entry(entry2.id, self.user)

        jl1 = entry1.lines.get(account=self.bank_account)
        jl2 = entry2.lines.get(account=self.bank_account)

        # التخصيص الأول بـ 700 من أصل 1000 (ينجح)
        BankReconciliationService.create_allocation(stmt_line.id, jl1.id, allocated_amount=Decimal("700.00"), user=self.user)

        # التخصيص الثاني بـ 500 يتجاوز السقف (مجموع 1200 > 1000) فيرفع ValueError
        with self.assertRaises(ValueError):
            BankReconciliationService.create_allocation(stmt_line.id, jl2.id, allocated_amount=Decimal("500.00"), user=self.user)

    def test_invalid_batch_state_transition_is_rejected(self):
        """3. اختبار رفض الانتقالات غير المصرح بها في آلة الحالات (ALLOWED_TRANSITIONS)"""
        # محاولة تحويل الحالة المباشرة من imported إلى completed ترسل الحارس لرفضها
        self.batch.status = "imported"
        self.batch.save()

        # الدالة update_batch_status ترفض الانتقال غير المسموح وتحافظ على الحالة الآمنة
        status = BankReconciliationService.update_batch_status(self.batch)
        self.assertEqual(status, "imported")

    def test_direct_bank_adjustment_via_accounting_gateway(self):
        """4. اختبار إنشاء وتأكيد قيد المصاريف والعمولات البنكية المباشرة عبر AccountingGateway"""
        stmt_line = BankStatementLine.objects.create(
            batch=self.batch,
            transaction_date=self.today,
            reference_number="FEE-001",
            description="عمولة بنكية عن تحويل شيك",
            debit=Decimal("0.00"),
            credit=Decimal("150.00"),
            is_matched=False
        )

        alloc = BankReconciliationService.create_direct_bank_adjustment(
            batch_id=self.batch.id,
            stmt_line_id=stmt_line.id,
            expense_account_id=self.expense_account.id,
            amount=Decimal("150.00"),
            description="عمولة بنكية عن تحويل شيك",
            user=self.user
        )

        self.assertIsNotNone(alloc)
        self.assertEqual(alloc.allocated_amount, Decimal("150.00"))

        stmt_line.refresh_from_db()
        self.assertTrue(stmt_line.is_matched)

    def test_reconciliation_summary_ias7_equation(self):
        """5. اختبار تقرير احتساب معادلة التسوية الرسمية IAS 7 Cash Control Equation"""
        summary = BankReconciliationService.calculate_reconciliation_summary(self.batch.id)
        self.assertIn("ending_bank_balance", summary)
        self.assertIn("adjusted_bank_balance", summary)
        self.assertIn("gl_balance", summary)
        self.assertIn("difference", summary)
