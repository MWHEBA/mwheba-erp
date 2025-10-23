"""
اختبارات النظام المحسن للأرصدة والأداء
"""
import time
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from ..models.chart_of_accounts import ChartOfAccounts, AccountType
from ..models.journal_entry import AccountingPeriod, JournalEntry, JournalEntryLine
from ..models.enhanced_balance import (
    AccountBalanceCache,
    BalanceSnapshot,
    BalanceAuditLog,
)
# محاولة استيراد الخدمات المتقدمة
try:
    from ..services.enhanced_balance_service import EnhancedBalanceService
except ImportError:
    EnhancedBalanceService = None

try:
    from ..services.performance_optimizer import PerformanceOptimizer
except ImportError:
    PerformanceOptimizer = None

try:
    from ..services.redis_cache_service import RedisFinancialCache, CachedBalanceService
except ImportError:
    RedisFinancialCache = None
    CachedBalanceService = None

try:
    from ..services.balance_validation_service import AdvancedBalanceValidationService
except ImportError:
    AdvancedBalanceValidationService = None

User = get_user_model()


class EnhancedBalanceServiceTestCase(TestCase):
    """اختبارات خدمة الأرصدة المحسنة"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # إنشاء أنواع الحسابات
        self.asset_type = AccountType.objects.create(
            code="1000",
            name="الأصول",
            category="asset",
            nature="debit",
            created_by=self.user,
        )

        self.equity_type = AccountType.objects.create(
            code="3000",
            name="حقوق الملكية",
            category="equity",
            nature="credit",
            created_by=self.user,
        )

        # إنشاء الحسابات
        self.cash_account = ChartOfAccounts.objects.create(
            code="1001",
            name="الخزينة",
            account_type=self.asset_type,
            created_by=self.user,
        )

        self.capital_account = ChartOfAccounts.objects.create(
            code="3001",
            name="رأس المال",
            account_type=self.equity_type,
            created_by=self.user,
        )

        # إنشاء فترة محاسبية
        self.period = AccountingPeriod.objects.create(
            name="2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.user,
        )

        # إنشاء قيود تجريبية
        self._create_test_entries()

    def _create_test_entries(self):
        """إنشاء قيود تجريبية للاختبار"""
        # قيد افتتاحي
        entry1 = JournalEntry.objects.create(
            date=date(2025, 1, 1),
            description="قيد افتتاحي",
            accounting_period=self.period,
            status="posted",
            created_by=self.user,
        )

        JournalEntryLine.objects.create(
            journal_entry=entry1,
            account=self.cash_account,
            debit=Decimal("10000"),
            credit=Decimal("0"),
        )

        JournalEntryLine.objects.create(
            journal_entry=entry1,
            account=self.capital_account,
            debit=Decimal("0"),
            credit=Decimal("10000"),
        )

        # قيد إضافي
        entry2 = JournalEntry.objects.create(
            date=date(2025, 1, 15),
            description="قيد إضافي",
            accounting_period=self.period,
            status="posted",
            created_by=self.user,
        )

        JournalEntryLine.objects.create(
            journal_entry=entry2,
            account=self.cash_account,
            debit=Decimal("5000"),
            credit=Decimal("0"),
        )

        JournalEntryLine.objects.create(
            journal_entry=entry2,
            account=self.capital_account,
            debit=Decimal("0"),
            credit=Decimal("5000"),
        )

    def test_get_account_balance_optimized(self):
        """اختبار حساب الرصيد المحسن"""
        balance = EnhancedBalanceService.get_account_balance_optimized(
            self.cash_account, use_cache=False
        )

        self.assertEqual(balance, Decimal("15000"))

    def test_calculate_account_balance_detailed(self):
        """اختبار الحساب التفصيلي للرصيد"""
        details = EnhancedBalanceService.calculate_account_balance_detailed(
            self.cash_account
        )

        self.assertEqual(details["balance"], Decimal("15000"))
        self.assertEqual(details["total_debits"], Decimal("15000"))
        self.assertEqual(details["total_credits"], Decimal("0"))
        self.assertEqual(details["transactions_count"], 2)

    def test_get_trial_balance_optimized(self):
        """اختبار ميزان المراجعة المحسن"""
        trial_balance = EnhancedBalanceService.get_trial_balance_optimized()

        # يجب أن يحتوي على حسابين على الأقل
        self.assertGreaterEqual(len(trial_balance), 2)

        # التحقق من التوازن
        totals = trial_balance[-1]  # آخر عنصر هو الإجماليات
        self.assertEqual(totals["debit_balance"], totals["credit_balance"])

    def test_balance_cache_functionality(self):
        """اختبار وظائف كاش الأرصدة"""
        # إنشاء كاش للحساب
        cache_obj = AccountBalanceCache.objects.create(
            account=self.cash_account,
            current_balance=Decimal("10000"),  # رصيد خاطئ عمداً
            needs_refresh=True,
        )

        # تحديث الكاش
        success = cache_obj.refresh_balance(force=True)
        self.assertTrue(success)

        # التحقق من الرصيد المحدث
        cache_obj.refresh_from_db()
        self.assertEqual(cache_obj.current_balance, Decimal("15000"))
        self.assertTrue(cache_obj.is_valid)
        self.assertFalse(cache_obj.needs_refresh)

    def test_balance_snapshot_creation(self):
        """اختبار إنشاء لقطات الأرصدة"""
        snapshot_date = date(2025, 1, 15)

        success = EnhancedBalanceService.create_balance_snapshot(
            self.cash_account, snapshot_date
        )

        self.assertTrue(success)

        # التحقق من وجود اللقطة
        snapshot = BalanceSnapshot.objects.get(
            account=self.cash_account, snapshot_date=snapshot_date
        )

        self.assertEqual(snapshot.balance, Decimal("15000"))
        self.assertEqual(snapshot.transactions_count, 2)


class PerformanceOptimizerTestCase(TestCase):
    """اختبارات محسن الأداء"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="perfuser", email="perf@example.com", password="testpass123"
        )

        # إنشاء بيانات تجريبية للأداء
        self._create_performance_test_data()

    def _create_performance_test_data(self):
        """إنشاء بيانات لاختبار الأداء"""
        # إنشاء نوع حساب
        asset_type = AccountType.objects.create(
            code="1000",
            name="الأصول",
            category="asset",
            nature="debit",
            created_by=self.user,
        )

        # إنشاء حساب
        self.test_account = ChartOfAccounts.objects.create(
            code="1001",
            name="حساب الاختبار",
            account_type=asset_type,
            created_by=self.user,
        )

        # إنشاء فترة محاسبية
        period = AccountingPeriod.objects.create(
            name="2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.user,
        )

        # إنشاء عدة قيود للاختبار
        for i in range(10):
            entry = JournalEntry.objects.create(
                date=date(2025, 1, 1) + timedelta(days=i),
                description=f"قيد اختبار {i+1}",
                accounting_period=period,
                status="posted",
                created_by=self.user,
            )

            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=self.test_account,
                debit=Decimal("1000") * (i + 1),
                credit=Decimal("0"),
            )

    def test_get_account_running_balances(self):
        """اختبار الأرصدة الجارية"""
        running_balances = PerformanceOptimizer.get_account_running_balances(
            self.test_account.id, limit=5
        )

        self.assertEqual(len(running_balances), 5)

        # التحقق من الرصيد الجاري الأول
        first_balance = running_balances[0]
        self.assertEqual(first_balance["running_balance"], Decimal("1000"))

        # التحقق من الرصيد الجاري الأخير
        last_balance = running_balances[-1]
        self.assertEqual(
            last_balance["running_balance"], Decimal("15000")
        )  # 1000+2000+3000+4000+5000

    def test_get_top_accounts_by_activity(self):
        """اختبار أكثر الحسابات نشاطاً"""
        top_accounts = PerformanceOptimizer.get_top_accounts_by_activity(limit=5)

        self.assertGreater(len(top_accounts), 0)

        # التحقق من وجود حساب الاختبار
        test_account_found = any(
            acc["id"] == self.test_account.id for acc in top_accounts
        )
        self.assertTrue(test_account_found)

    def test_optimize_journal_entry_queries(self):
        """اختبار تحسين استعلامات القيود"""
        result = PerformanceOptimizer.optimize_journal_entry_queries()

        self.assertEqual(result["status"], "completed")
        self.assertGreater(len(result["optimizations_applied"]), 0)


class RedisFinancialCacheTestCase(TestCase):
    """اختبارات Redis Cache المالي"""

    def setUp(self):
        self.cache = RedisFinancialCache()
        self.test_data = {
            "balance": Decimal("1000.50"),
            "account_id": 123,
            "date": date.today(),
        }

    def test_cache_set_and_get(self):
        """اختبار حفظ واسترجاع البيانات"""
        # حفظ البيانات
        success = self.cache.set(
            "test_balance", self.test_data, account_id=123, date=date.today()
        )

        if self.cache.redis_available:
            self.assertTrue(success)

            # استرجاع البيانات
            retrieved_data = self.cache.get(
                "test_balance", account_id=123, date=date.today()
            )

            self.assertIsNotNone(retrieved_data)
            self.assertEqual(retrieved_data["balance"], Decimal("1000.50"))
            self.assertEqual(retrieved_data["account_id"], 123)
        else:
            # Redis غير متاح - تخطي الاختبار
            self.skipTest("Redis غير متاح")

    def test_cache_delete(self):
        """اختبار حذف البيانات من الكاش"""
        if not self.cache.redis_available:
            self.skipTest("Redis غير متاح")

        # حفظ البيانات أولاً
        self.cache.set("test_delete", self.test_data, account_id=123)

        # حذف البيانات
        deleted = self.cache.delete("test_delete", account_id=123)
        self.assertTrue(deleted)

        # التحقق من الحذف
        retrieved = self.cache.get("test_delete", account_id=123)
        self.assertIsNone(retrieved)

    def test_cached_balance_service(self):
        """اختبار خدمة الأرصدة مع الكاش"""
        # إنشاء بيانات تجريبية
        user = User.objects.create_user(username="cacheuser", password="test123")

        asset_type = AccountType.objects.create(
            code="1000",
            name="الأصول",
            category="asset",
            nature="debit",
            created_by=user,
        )

        account = ChartOfAccounts.objects.create(
            code="1001", name="حساب الكاش", account_type=asset_type, created_by=user
        )

        # اختبار الحصول على الرصيد مع الكاش
        balance1 = CachedBalanceService.get_account_balance(account.id, use_cache=True)
        balance2 = CachedBalanceService.get_account_balance(account.id, use_cache=True)

        # يجب أن يكون الرصيدان متساويين
        self.assertEqual(balance1, balance2)


class BalanceValidationTestCase(TestCase):
    """اختبارات التحقق من صحة الأرصدة"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="validuser", email="valid@example.com", password="testpass123"
        )

        # إنشاء بيانات للتحقق
        self._create_validation_test_data()

    def _create_validation_test_data(self):
        """إنشاء بيانات لاختبار التحقق"""
        # إنشاء أنواع الحسابات
        asset_type = AccountType.objects.create(
            code="1000",
            name="الأصول",
            category="asset",
            nature="debit",
            created_by=self.user,
        )

        liability_type = AccountType.objects.create(
            code="2000",
            name="الخصوم",
            category="liability",
            nature="credit",
            created_by=self.user,
        )

        # إنشاء الحسابات
        self.asset_account = ChartOfAccounts.objects.create(
            code="1001", name="الأصول", account_type=asset_type, created_by=self.user
        )

        self.liability_account = ChartOfAccounts.objects.create(
            code="2001",
            name="الخصوم",
            account_type=liability_type,
            created_by=self.user,
        )

        # إنشاء فترة محاسبية
        period = AccountingPeriod.objects.create(
            name="2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.user,
        )

        # إنشاء قيد متوازن
        entry = JournalEntry.objects.create(
            date=date.today(),
            description="قيد متوازن",
            accounting_period=period,
            status="posted",
            created_by=self.user,
        )

        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.asset_account,
            debit=Decimal("5000"),
            credit=Decimal("0"),
        )

        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.liability_account,
            debit=Decimal("0"),
            credit=Decimal("5000"),
        )

    def test_validate_trial_balance_integrity(self):
        """اختبار التحقق من سلامة ميزان المراجعة"""
        result = AdvancedBalanceValidationService.validate_trial_balance_integrity()

        self.assertTrue(result["is_balanced"])
        self.assertEqual(result["difference"], Decimal("0"))
        self.assertGreaterEqual(result["accounts_count"], 2)

    def test_validate_all_balances(self):
        """اختبار التحقق من جميع الأرصدة"""
        result = AdvancedBalanceValidationService.validate_all_balances()

        self.assertGreaterEqual(result["total_accounts"], 2)
        self.assertEqual(result["invalid_accounts"], 0)  # يجب ألا يكون هناك أخطاء
        self.assertEqual(len(result["errors"]), 0)

    def test_generate_balance_health_report(self):
        """اختبار تقرير صحة الأرصدة"""
        report = AdvancedBalanceValidationService.generate_balance_health_report()

        self.assertIn("report_date", report)
        self.assertIn("health_score", report)
        self.assertIn("recommendations", report)

        # النظام يجب أن يكون في حالة جيدة
        self.assertGreaterEqual(report["health_score"], 80)


class PerformanceBenchmarkTestCase(TransactionTestCase):
    """اختبارات قياس الأداء"""

    def setUp(self):
        self.user = User.objects.create_user(username="benchuser", password="test123")

        # إنشاء بيانات كبيرة للاختبار
        self._create_large_dataset()

    def _create_large_dataset(self):
        """إنشاء مجموعة بيانات كبيرة لاختبار الأداء"""
        # إنشاء نوع حساب
        asset_type = AccountType.objects.create(
            code="1000",
            name="الأصول",
            category="asset",
            nature="debit",
            created_by=self.user,
        )

        # إنشاء عدة حسابات
        self.accounts = []
        for i in range(5):
            account = ChartOfAccounts.objects.create(
                code=f"100{i+1}",
                name=f"حساب {i+1}",
                account_type=asset_type,
                created_by=self.user,
            )
            self.accounts.append(account)

        # إنشاء فترة محاسبية
        period = AccountingPeriod.objects.create(
            name="2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.user,
        )

        # إنشاء عدد كبير من القيود
        for i in range(100):
            entry = JournalEntry.objects.create(
                date=date(2025, 1, 1) + timedelta(days=i % 365),
                description=f"قيد أداء {i+1}",
                accounting_period=period,
                status="posted",
                created_by=self.user,
            )

            # إضافة بنود للقيد
            account = self.accounts[i % len(self.accounts)]
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=account,
                debit=Decimal("1000"),
                credit=Decimal("0"),
            )

    def test_balance_calculation_performance(self):
        """اختبار أداء حساب الأرصدة"""
        start_time = time.time()

        # حساب أرصدة جميع الحسابات
        for account in self.accounts:
            balance = EnhancedBalanceService.get_account_balance_optimized(
                account, use_cache=False
            )
            self.assertIsInstance(balance, Decimal)

        end_time = time.time()
        execution_time = end_time - start_time

        # يجب أن يكتمل خلال ثانية واحدة
        self.assertLess(
            execution_time, 1.0, f"حساب الأرصدة استغرق {execution_time:.2f} ثانية"
        )

    def test_trial_balance_performance(self):
        """اختبار أداء ميزان المراجعة"""
        start_time = time.time()

        trial_balance = EnhancedBalanceService.get_trial_balance_optimized()

        end_time = time.time()
        execution_time = end_time - start_time

        self.assertGreater(len(trial_balance), 0)
        self.assertLess(
            execution_time, 2.0, f"ميزان المراجعة استغرق {execution_time:.2f} ثانية"
        )

    def test_bulk_balance_refresh_performance(self):
        """اختبار أداء التحديث المجمع للأرصدة"""
        start_time = time.time()

        results = EnhancedBalanceService.bulk_refresh_balances(self.accounts)

        end_time = time.time()
        execution_time = end_time - start_time

        self.assertEqual(results["success"], len(self.accounts))
        self.assertEqual(results["failed"], 0)
        self.assertLess(
            execution_time, 3.0, f"التحديث المجمع استغرق {execution_time:.2f} ثانية"
        )
