"""
اختبارات الأداء والضغط الشاملة للنظام المالي
"""
import time
import threading
import concurrent.futures
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction, connections
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import statistics

from ..models.chart_of_accounts import ChartOfAccounts, AccountType
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..services.enhanced_balance_service import EnhancedBalanceService
from ..services.advanced_reports_service import AdvancedReportsService
from ..services.payment_sync_service import PaymentSyncService
from ..services.redis_cache_service import financial_cache

User = get_user_model()


class PerformanceTestCase(TransactionTestCase):
    """اختبارات الأداء الأساسية"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="perfuser", password="testpass123"
        )

        # إنشاء بيانات أساسية للاختبار
        self._create_test_data()

    def _create_test_data(self):
        """إنشاء بيانات اختبار الأداء"""
        # إنشاء أنواع الحسابات
        self.asset_type = AccountType.objects.create(
            code="1000",
            name="الأصول",
            category="asset",
            nature="debit",
            created_by=self.user,
        )

        self.revenue_type = AccountType.objects.create(
            code="4000",
            name="الإيرادات",
            category="revenue",
            nature="credit",
            created_by=self.user,
        )

        # إنشاء حسابات للاختبار
        self.accounts = []
        for i in range(10):
            account = ChartOfAccounts.objects.create(
                code=f"100{i+1}",
                name=f"حساب اختبار {i+1}",
                account_type=self.asset_type,
                created_by=self.user,
            )
            self.accounts.append(account)

        # إنشاء فترة محاسبية
        self.period = AccountingPeriod.objects.create(
            name="2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.user,
        )

    def test_balance_calculation_performance(self):
        """اختبار أداء حساب الأرصدة"""
        # إنشاء عدد كبير من القيود
        self._create_bulk_journal_entries(100)

        # قياس وقت حساب الأرصدة
        start_time = time.time()

        for account in self.accounts:
            balance = EnhancedBalanceService.get_account_balance_optimized(
                account, use_cache=False
            )
            self.assertIsInstance(balance, Decimal)

        end_time = time.time()
        execution_time = end_time - start_time

        print(f"وقت حساب أرصدة {len(self.accounts)} حساب: {execution_time:.3f} ثانية")

        # يجب أن يكون أقل من ثانية واحدة
        self.assertLess(
            execution_time, 1.0, f"حساب الأرصدة بطيء جداً: {execution_time:.3f}s"
        )

    def test_trial_balance_performance(self):
        """اختبار أداء ميزان المراجعة"""
        # إنشاء بيانات للاختبار
        self._create_bulk_journal_entries(200)

        # قياس وقت ميزان المراجعة
        start_time = time.time()

        trial_balance = AdvancedReportsService.generate_comprehensive_trial_balance()

        end_time = time.time()
        execution_time = end_time - start_time

        print(f"وقت إنشاء ميزان المراجعة: {execution_time:.3f} ثانية")

        # التحقق من النتائج
        self.assertIsInstance(trial_balance, dict)
        self.assertIn("accounts", trial_balance)
        self.assertGreater(len(trial_balance["accounts"]), 0)

        # يجب أن يكون أقل من 3 ثوانٍ
        self.assertLess(
            execution_time, 3.0, f"ميزان المراجعة بطيء جداً: {execution_time:.3f}s"
        )

    def test_cache_performance(self):
        """اختبار أداء النظام مع الكاش"""
        account = self.accounts[0]

        # إنشاء بيانات
        self._create_bulk_journal_entries(50)

        # الاستعلام الأول (بدون كاش)
        start_time = time.time()
        balance1 = EnhancedBalanceService.get_account_balance_optimized(
            account, use_cache=False
        )
        first_query_time = time.time() - start_time

        # الاستعلام الثاني (مع الكاش)
        start_time = time.time()
        balance2 = EnhancedBalanceService.get_account_balance_optimized(
            account, use_cache=True
        )
        cached_query_time = time.time() - start_time

        # التحقق من النتائج
        self.assertEqual(balance1, balance2)

        print(f"الاستعلام الأول: {first_query_time:.3f}s")
        print(f"الاستعلام المكاش: {cached_query_time:.3f}s")
        print(f"تحسن الأداء: {(first_query_time / cached_query_time):.1f}x")

        # الكاش يجب أن يكون أسرع
        self.assertLess(cached_query_time, first_query_time)

    def _create_bulk_journal_entries(self, count: int):
        """إنشاء عدد كبير من القيود للاختبار"""
        entries = []
        lines = []

        for i in range(count):
            entry = JournalEntry(
                date=date.today() - timedelta(days=i % 365),
                description=f"قيد اختبار أداء {i+1}",
                accounting_period=self.period,
                status="posted",
                created_by=self.user,
            )
            entries.append(entry)

        # إنشاء القيود بشكل مجمع
        JournalEntry.objects.bulk_create(entries)

        # إنشاء البنود
        for entry in JournalEntry.objects.filter(
            description__startswith="قيد اختبار أداء"
        ):
            account1 = self.accounts[entry.id % len(self.accounts)]
            account2 = self.accounts[(entry.id + 1) % len(self.accounts)]

            lines.extend(
                [
                    JournalEntryLine(
                        journal_entry=entry,
                        account=account1,
                        debit=Decimal("1000"),
                        credit=Decimal("0"),
                    ),
                    JournalEntryLine(
                        journal_entry=entry,
                        account=account2,
                        debit=Decimal("0"),
                        credit=Decimal("1000"),
                    ),
                ]
            )

        JournalEntryLine.objects.bulk_create(lines)


class StressTestCase(TransactionTestCase):
    """اختبارات الضغط والتحمل"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="stressuser", password="testpass123"
        )

        # إنشاء بيانات أساسية
        self._create_stress_test_data()

    def _create_stress_test_data(self):
        """إنشاء بيانات اختبار الضغط"""
        # إنشاء نوع حساب
        self.account_type = AccountType.objects.create(
            code="1000",
            name="حسابات الضغط",
            category="asset",
            nature="debit",
            created_by=self.user,
        )

        # إنشاء عدد كبير من الحسابات
        accounts_data = []
        for i in range(100):
            accounts_data.append(
                ChartOfAccounts(
                    code=f"1{i+1:03d}",
                    name=f"حساب ضغط {i+1}",
                    account_type=self.account_type,
                    created_by=self.user,
                )
            )

        self.accounts = ChartOfAccounts.objects.bulk_create(accounts_data)

        # إنشاء فترة محاسبية
        self.period = AccountingPeriod.objects.create(
            name="2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.user,
        )

    def test_concurrent_balance_calculations(self):
        """اختبار حسابات الأرصدة المتزامنة"""
        # إنشاء بيانات كبيرة
        self._create_massive_journal_entries(500)

        # دالة حساب الرصيد
        def calculate_balance(account):
            return EnhancedBalanceService.get_account_balance_optimized(
                account, use_cache=False
            )

        # تشغيل متزامن
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(calculate_balance, account)
                for account in self.accounts[:20]
            ]

            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        end_time = time.time()
        execution_time = end_time - start_time

        print(f"حساب 20 رصيد متزامن: {execution_time:.3f} ثانية")

        # التحقق من النتائج
        self.assertEqual(len(results), 20)
        for result in results:
            self.assertIsInstance(result, Decimal)

        # يجب أن يكون أقل من 5 ثوانٍ
        self.assertLess(execution_time, 5.0)

    def test_database_connection_stress(self):
        """اختبار ضغط اتصالات قاعدة البيانات"""

        def perform_database_operations():
            # عمليات قاعدة بيانات متنوعة
            account_count = ChartOfAccounts.objects.count()
            entry_count = JournalEntry.objects.count()

            # حساب رصيد
            if self.accounts:
                balance = EnhancedBalanceService.get_account_balance_optimized(
                    self.accounts[0], use_cache=False
                )

            return account_count + entry_count

        # تشغيل عمليات متزامنة
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(perform_database_operations) for _ in range(50)]

            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        end_time = time.time()
        execution_time = end_time - start_time

        print(f"50 عملية قاعدة بيانات متزامنة: {execution_time:.3f} ثانية")

        # التحقق من النتائج
        self.assertEqual(len(results), 50)

        # يجب أن تكتمل خلال 10 ثوانٍ
        self.assertLess(execution_time, 10.0)

    def test_memory_usage_under_load(self):
        """اختبار استهلاك الذاكرة تحت الضغط"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # إنشاء حمولة كبيرة
        self._create_massive_journal_entries(1000)

        # عمليات كثيفة
        for i in range(10):
            trial_balance = (
                AdvancedReportsService.generate_comprehensive_trial_balance()
            )

            # حساب أرصدة متعددة
            for account in self.accounts[:10]:
                balance = EnhancedBalanceService.get_account_balance_optimized(account)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        print(f"الذاكرة الأولية: {initial_memory:.1f} MB")
        print(f"الذاكرة النهائية: {final_memory:.1f} MB")
        print(f"زيادة الذاكرة: {memory_increase:.1f} MB")

        # يجب ألا تزيد الذاكرة عن 100 MB
        self.assertLess(
            memory_increase, 100, f"استهلاك ذاكرة مفرط: {memory_increase:.1f} MB"
        )

    def _create_massive_journal_entries(self, count: int):
        """إنشاء عدد ضخم من القيود"""
        batch_size = 100

        for batch_start in range(0, count, batch_size):
            batch_end = min(batch_start + batch_size, count)

            entries = []
            for i in range(batch_start, batch_end):
                entry = JournalEntry(
                    date=date.today() - timedelta(days=i % 365),
                    description=f"قيد ضغط {i+1}",
                    accounting_period=self.period,
                    status="posted",
                    created_by=self.user,
                )
                entries.append(entry)

            # إنشاء القيود
            created_entries = JournalEntry.objects.bulk_create(entries)

            # إنشاء البنود
            lines = []
            for entry in created_entries:
                account1 = self.accounts[entry.id % len(self.accounts)]
                account2 = self.accounts[(entry.id + 1) % len(self.accounts)]

                lines.extend(
                    [
                        JournalEntryLine(
                            journal_entry=entry,
                            account=account1,
                            debit=Decimal("1000"),
                            credit=Decimal("0"),
                        ),
                        JournalEntryLine(
                            journal_entry=entry,
                            account=account2,
                            debit=Decimal("0"),
                            credit=Decimal("1000"),
                        ),
                    ]
                )

            JournalEntryLine.objects.bulk_create(lines)


class PaymentSyncStressTestCase(TransactionTestCase):
    """اختبارات ضغط نظام تزامن المدفوعات"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="paymentsyncuser", password="testpass123"
        )

        self.sync_service = PaymentSyncService()

    def test_concurrent_payment_sync(self):
        """اختبار تزامن المدفوعات المتزامن"""

        def sync_payment(payment_id):
            # محاكاة دفعة
            mock_payment = MagicMock()
            mock_payment.id = payment_id
            mock_payment.amount = Decimal("1000")
            mock_payment.payment_date = date.today()
            mock_payment.__class__.__name__ = "SalePayment"

            # محاكاة العمليات لتجنب الأخطاء
            with patch.multiple(
                self.sync_service,
                _sync_to_customer_payment=MagicMock(),
                _sync_to_journal_entry=MagicMock(),
                _update_balance_cache=MagicMock(),
            ):
                return self.sync_service.sync_payment(
                    mock_payment, "create_payment", self.user
                )

        # تشغيل متزامن
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(sync_payment, i) for i in range(20)]

            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        end_time = time.time()
        execution_time = end_time - start_time

        print(f"تزامن 20 دفعة متزامنة: {execution_time:.3f} ثانية")

        # التحقق من النتائج
        self.assertEqual(len(results), 20)
        for result in results:
            self.assertIsNotNone(result)

        # يجب أن يكتمل خلال 10 ثوانٍ
        self.assertLess(execution_time, 10.0)


class ReportsPerformanceTestCase(TestCase):
    """اختبارات أداء التقارير"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="reportsuser", password="testpass123"
        )

        # إنشاء بيانات للتقارير
        self._create_reports_test_data()

    def _create_reports_test_data(self):
        """إنشاء بيانات اختبار التقارير"""
        # إنشاء أنواع حسابات متنوعة
        account_types = [
            ("1000", "الأصول", "asset", "debit"),
            ("2000", "الخصوم", "liability", "credit"),
            ("3000", "حقوق الملكية", "equity", "credit"),
            ("4000", "الإيرادات", "revenue", "credit"),
            ("5000", "المصروفات", "expense", "debit"),
        ]

        self.account_types = {}
        for code, name, category, nature in account_types:
            account_type = AccountType.objects.create(
                code=code,
                name=name,
                category=category,
                nature=nature,
                created_by=self.user,
            )
            self.account_types[category] = account_type

        # إنشاء حسابات لكل نوع
        self.accounts = {}
        for category, account_type in self.account_types.items():
            accounts = []
            for i in range(5):
                account = ChartOfAccounts.objects.create(
                    code=f"{account_type.code[0]}{i+1:03d}",
                    name=f"{account_type.name} {i+1}",
                    account_type=account_type,
                    created_by=self.user,
                )
                accounts.append(account)
            self.accounts[category] = accounts

    def test_comprehensive_trial_balance_performance(self):
        """اختبار أداء ميزان المراجعة الشامل"""
        start_time = time.time()

        trial_balance = AdvancedReportsService.generate_comprehensive_trial_balance(
            include_zero_balances=True, group_by_type=True
        )

        end_time = time.time()
        execution_time = end_time - start_time

        print(f"ميزان المراجعة الشامل: {execution_time:.3f} ثانية")

        # التحقق من النتائج
        self.assertIsInstance(trial_balance, dict)
        self.assertIn("accounts", trial_balance)
        self.assertIn("category_totals", trial_balance)

        # يجب أن يكون سريعاً
        self.assertLess(execution_time, 2.0)

    def test_multiple_reports_generation(self):
        """اختبار إنشاء تقارير متعددة"""
        reports_to_generate = [
            (
                "trial_balance",
                lambda: AdvancedReportsService.generate_comprehensive_trial_balance(),
            ),
            (
                "balance_sheet",
                lambda: AdvancedReportsService.generate_balance_sheet(date.today()),
            ),
            (
                "income_statement",
                lambda: AdvancedReportsService.generate_income_statement(
                    date.today() - timedelta(days=30), date.today()
                ),
            ),
        ]

        execution_times = {}

        for report_name, report_func in reports_to_generate:
            start_time = time.time()
            report = report_func()
            end_time = time.time()

            execution_times[report_name] = end_time - start_time

            # التحقق من وجود البيانات
            self.assertIsInstance(report, dict)
            self.assertIn("report_info", report)

        total_time = sum(execution_times.values())

        print("أوقات التقارير:")
        for report_name, exec_time in execution_times.items():
            print(f"  {report_name}: {exec_time:.3f}s")
        print(f"الإجمالي: {total_time:.3f}s")

        # يجب أن يكتمل الكل خلال 5 ثوانٍ
        self.assertLess(total_time, 5.0)


class CacheStressTestCase(TestCase):
    """اختبارات ضغط نظام الكاش"""

    def test_cache_under_heavy_load(self):
        """اختبار الكاش تحت حمولة ثقيلة"""
        # إنشاء عدد كبير من المفاتيح
        cache_operations = []

        start_time = time.time()

        # كتابة كثيفة
        for i in range(1000):
            key = f"test_key_{i}"
            value = {"data": f"test_value_{i}", "number": i}

            financial_cache.set("stress_test", value, timeout=300, key_id=i)
            cache_operations.append(("set", key))

        # قراءة كثيفة
        for i in range(1000):
            value = financial_cache.get("stress_test", key_id=i)
            cache_operations.append(("get", f"test_key_{i}"))

        end_time = time.time()
        execution_time = end_time - start_time

        print(f"2000 عملية كاش: {execution_time:.3f} ثانية")
        print(f"معدل العمليات: {len(cache_operations)/execution_time:.0f} عملية/ثانية")

        # يجب أن يكون سريعاً
        self.assertLess(execution_time, 5.0)
