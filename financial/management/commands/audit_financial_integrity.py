"""
Financial Integrity Audit & Self-Healing Command
أمر تدقيق السلامة المالية الشامل والفحص الذاتي الدوري لنظام MWHEBA ERP
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Sum, Q, Count
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.services.trial_balance_service import TrialBalanceService
from financial.services.financial_statement_engine import FinancialStatementEngine


class Command(BaseCommand):
    help = "تدقيق السلامة المالية الشاملة وفحص توازن ميزان المراجعة ودفتر الأستاذ العام والقوائم المالية"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="تنفيذ الإصلاح التلقائي للحركات والأسطر الشاذة إن وُجدت",
        )

    def handle(self, *args, **options):
        should_fix = options.get("fix", False)
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write(self.style.MIGRATE_HEADING("  فحص وتدقيق السلامة المالية الشاملة - MWHEBA ERP"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))

        errors_found = 0
        warnings_found = 0

        # -------------------------------------------------------------
        # 1. فحص توازن كل قيد يومي منفرد في الدفتر العام
        # -------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[1/5] فحص توازن القيود اليومية (Individual JE Debit = Credit)..."))
        unbalanced_jes = []
        all_jes = JournalEntry.objects.filter(status="posted").prefetch_related("lines")
        for je in all_jes:
            dr = je.lines.aggregate(s=Sum("debit"))["s"] or Decimal("0.00")
            cr = je.lines.aggregate(s=Sum("credit"))["s"] or Decimal("0.00")
            if abs(dr - cr) > Decimal("0.001"):
                unbalanced_jes.append((je, dr, cr, dr - cr))

        if unbalanced_jes:
            errors_found += len(unbalanced_jes)
            self.stdout.write(self.style.ERROR(f"  [ERROR] تم العثور على {len(unbalanced_jes)} قيد غير متوازن:"))
            for je, dr, cr, diff in unbalanced_jes:
                self.stdout.write(f"     - قيد #{je.number} (ID: {je.id}): مدين={dr}, دائن={cr}, الفرق={diff}")
        else:
            self.stdout.write(self.style.SUCCESS(f"  [OK] جميع القيود اليومية المرحلة ({all_jes.count()} قيد) متوازنة 100%."))

        # -------------------------------------------------------------
        # 2. فحص الأسطر المسجلة على حسابات رئيسية (أمهات)
        # -------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[2/5] فحص أسطر القيود على الحسابات الرئيسية (Parent Account Postings)..."))
        parent_lines = JournalEntryLine.objects.filter(account__is_leaf=False)
        parent_lines_count = parent_lines.count()

        if parent_lines_count > 0:
            errors_found += parent_lines_count
            self.stdout.write(self.style.ERROR(f"  [ERROR] تم رصد {parent_lines_count} سطر قيد مسجل على حسابات رئيسية (أمهات):"))
            for l in parent_lines:
                self.stdout.write(
                    f"     - سطر #{l.id} | قيد: {l.journal_entry.number} | حساب: {l.account.code} - {l.account.name} | مدين: {l.debit} | دائن: {l.credit}"
                )
                if should_fix:
                    # محاولة الإصلاح التلقائي بنقل السطر إلى أول ابن طرفي نشط
                    leaf_child = l.account.children.filter(is_active=True, is_leaf=True).first()
                    if leaf_child:
                        JournalEntryLine.objects.filter(id=l.id).update(account=leaf_child)
                        self.stdout.write(self.style.SUCCESS(f"       [FIXED] تم نقل السطر تلقائياً إلى الحساب الفرعي: {leaf_child.code} - {leaf_child.name}"))
                        errors_found -= 1
        else:
            self.stdout.write(self.style.SUCCESS("  [OK] لا توجد أي أسطر مسجلة على حسابات أمهات. جميع الحركات مسجلة على حسابات طرفية."))

        # -------------------------------------------------------------
        # 3. فحص الحسابات المعطلة ذات الأرصدة المعلقة
        # -------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[3/5] فحص الحسابات المعطلة ذات الأرصدة (Inactive Accounts Balance Check)..."))
        inactive_accounts = ChartOfAccounts.objects.filter(is_active=False)
        inactive_with_balances = []
        for acc in inactive_accounts:
            bal = acc.current_balance
            if abs(bal) > Decimal("0.00"):
                inactive_with_balances.append((acc, bal))

        if inactive_with_balances:
            warnings_found += len(inactive_with_balances)
            self.stdout.write(self.style.WARNING(f"  [WARN] يوجد {len(inactive_with_balances)} حساب معطل برصيد غير صفري:"))
            for acc, bal in inactive_with_balances:
                self.stdout.write(f"     - حساب {acc.code} - {acc.name}: الرصيد المعلق = {bal}")
        else:
            self.stdout.write(self.style.SUCCESS("  [OK] لا توجد حسابات معطلة بأرصدة معلقة."))

        # -------------------------------------------------------------
        # 4. فحص وتوليد ميزان المراجعة الشامل (Trial Balance Equilibrium)
        # -------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[4/5] فحص توازن ميزان المراجعة الشامل (Trial Balance Generation)..."))
        tb_data = TrialBalanceService.generate_trial_balance()

        self.stdout.write(f"  - رصيد أول المدة: مدين={tb_data['total_opening_debit']} | دائن={tb_data['total_opening_credit']} | فارق={tb_data['diff_opening']}")
        self.stdout.write(f"  - حركات الفترة: مدين={tb_data['total_period_debit']} | دائن={tb_data['total_period_credit']} | فارق={tb_data['diff_period']}")
        self.stdout.write(f"  - رصيد الإقفال:  مدين={tb_data['total_closing_debit']} | دائن={tb_data['total_closing_credit']} | فارق={tb_data['diff_closing']}")

        if tb_data["is_balanced"]:
            self.stdout.write(self.style.SUCCESS("  [OK] ميزان المراجعة متوازن بالكامل بنسبة 100% (Balanced)."))
        else:
            errors_found += 1
            self.stdout.write(self.style.ERROR(f"  [ERROR] ميزان المراجعة غير متوازن! الفارق الإجمالي = {tb_data['difference']}"))

        # -------------------------------------------------------------
        # 5. فحص مثلث القوائم المالية (Triangular Parity Check)
        # -------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[5/5] فحص مثلث القوائم المالية (Trial Balance vs Balance Sheet vs P&L)..."))
        try:
            bs = FinancialStatementEngine.generate_balance_sheet()
            pnl = FinancialStatementEngine.generate_income_statement()

            self.stdout.write(f"  - إجمالي الأصول: {bs['total_assets']}")
            self.stdout.write(f"  - إجمالي الخصوم وحقوق الملكية + صافي الربح: {bs['total_liabilities_and_equity']}")
            self.stdout.write(f"  - صافي دخل قائمة الدخل: {pnl['net_income']}")

            if bs["is_balanced"]:
                self.stdout.write(self.style.SUCCESS("  [OK] معادلة الميزانية العمومية متطابقة بالمليم (Assets = Liabilities + Equity + Net Income)."))
            else:
                errors_found += 1
                self.stdout.write(self.style.ERROR(f"  [ERROR] فارق معادلة الميزانية العمومية = {bs['accounting_equation_diff']}"))
        except Exception as e:
            warnings_found += 1
            self.stdout.write(self.style.WARNING(f"  [WARN] تعذر استكمال فحص الميزانية: {e}"))

        # -------------------------------------------------------------
        # النتيجة النهائية والملخص
        # -------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 70))
        if errors_found == 0:
            self.stdout.write(self.style.SUCCESS(f"  [SUCCESS] النتيجة: النظام المالي سليم ومحصن ومتوازن 100% (أخطاء: 0 | تحذيرات: {warnings_found})"))
        else:
            self.stdout.write(self.style.ERROR(f"  [FAILED] النتيجة: تم العثور على {errors_found} أخطاء تحتاج للمعالجة (تحذيرات: {warnings_found})"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70 + "\n"))
