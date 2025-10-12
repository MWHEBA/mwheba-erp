"""
أمر Django لاختبار التكامل المحاسبي الشامل
يختبر إنشاء القيود المحاسبية والتزامن والأرصدة
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging

from financial.models import (
    ChartOfAccounts,
    JournalEntry,
    JournalEntryLine,
    AccountingPeriod,
)
from financial.services.accounting_integration_service import (
    AccountingIntegrationService,
)
from financial.services.payment_sync_service import PaymentSyncService

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "اختبار التكامل المحاسبي الشامل مع المبيعات والمشتريات"

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-test-data", action="store_true", help="إنشاء بيانات اختبار وهمية"
        )
        parser.add_argument(
            "--test-balance-calculation",
            action="store_true",
            help="اختبار حساب الأرصدة",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🧪 بدء اختبار التكامل المحاسبي الشامل..."))

        try:
            # 1. اختبار النظام الأساسي
            self.test_basic_system()

            # 2. اختبار خدمة التكامل المحاسبي
            self.test_accounting_integration_service()

            # 3. اختبار حساب الأرصدة
            if options["test_balance_calculation"]:
                self.test_balance_calculation()

            # 4. اختبار نظام التزامن
            self.test_payment_sync_system()

            # 5. إنشاء بيانات اختبار
            if options["create_test_data"]:
                self.create_test_data()

            self.stdout.write(
                self.style.SUCCESS("✅ اكتمل اختبار التكامل المحاسبي بنجاح!")
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ خطأ في الاختبار: {str(e)}"))
            logger.error(f"خطأ في اختبار التكامل المحاسبي: {str(e)}")
            raise

    def test_basic_system(self):
        """اختبار النظام الأساسي"""
        self.stdout.write("🔧 اختبار النظام الأساسي...")

        # التحقق من وجود الحسابات الأساسية
        required_accounts = [
            "1001",
            "1002",
            "1201",
            "1301",
            "2101",
            "4001",
            "5001",
            "5002",
        ]
        missing_accounts = []

        for code in required_accounts:
            if not ChartOfAccounts.objects.filter(code=code, is_active=True).exists():
                missing_accounts.append(code)

        if missing_accounts:
            self.stdout.write(
                self.style.WARNING(f'  ⚠️ حسابات مفقودة: {", ".join(missing_accounts)}')
            )
        else:
            self.stdout.write("  ✓ جميع الحسابات الأساسية موجودة")

        # التحقق من وجود فترة محاسبية مفتوحة
        open_period = AccountingPeriod.objects.filter(status="open").first()
        if open_period:
            self.stdout.write(f"  ✓ فترة محاسبية مفتوحة: {open_period.name}")
        else:
            self.stdout.write("  ⚠️ لا توجد فترة محاسبية مفتوحة")

    def test_accounting_integration_service(self):
        """اختبار خدمة التكامل المحاسبي"""
        self.stdout.write("⚙️ اختبار خدمة التكامل المحاسبي...")

        # اختبار الحصول على الحسابات المطلوبة للمبيعات
        sale_accounts = AccountingIntegrationService._get_required_accounts_for_sale()
        if sale_accounts and len(sale_accounts) >= 4:
            self.stdout.write("  ✓ حسابات المبيعات جاهزة")
        else:
            self.stdout.write("  ❌ حسابات المبيعات غير مكتملة")

        # اختبار الحصول على الحسابات المطلوبة للمشتريات
        purchase_accounts = (
            AccountingIntegrationService._get_required_accounts_for_purchase()
        )
        if purchase_accounts and len(purchase_accounts) >= 4:
            self.stdout.write("  ✓ حسابات المشتريات جاهزة")
        else:
            self.stdout.write("  ❌ حسابات المشتريات غير مكتملة")

        # اختبار الحصول على الحسابات المطلوبة للمدفوعات
        payment_accounts = (
            AccountingIntegrationService._get_required_accounts_for_payment()
        )
        if payment_accounts and len(payment_accounts) >= 3:
            self.stdout.write("  ✓ حسابات المدفوعات جاهزة")
        else:
            self.stdout.write("  ❌ حسابات المدفوعات غير مكتملة")

    def test_balance_calculation(self):
        """اختبار حساب الأرصدة"""
        self.stdout.write("💰 اختبار حساب الأرصدة...")

        # اختبار حساب رصيد الصندوق
        try:
            cash_account = ChartOfAccounts.objects.get(code="1001")
            balance = cash_account.get_balance()
            self.stdout.write(f"  ✓ رصيد الصندوق: {balance}")
        except ChartOfAccounts.DoesNotExist:
            self.stdout.write("  ❌ حساب الصندوق غير موجود")
        except Exception as e:
            self.stdout.write(f"  ❌ خطأ في حساب رصيد الصندوق: {str(e)}")

        # اختبار حساب رصيد العملاء
        try:
            receivable_account = ChartOfAccounts.objects.get(code="1201")
            balance = receivable_account.get_balance()
            self.stdout.write(f"  ✓ رصيد العملاء: {balance}")
        except ChartOfAccounts.DoesNotExist:
            self.stdout.write("  ❌ حساب العملاء غير موجود")
        except Exception as e:
            self.stdout.write(f"  ❌ خطأ في حساب رصيد العملاء: {str(e)}")

    def test_payment_sync_system(self):
        """اختبار نظام تزامن المدفوعات"""
        self.stdout.write("🔄 اختبار نظام تزامن المدفوعات...")

        try:
            from financial.models.payment_sync import PaymentSyncRule

            # التحقق من وجود قواعد التزامن
            active_rules = PaymentSyncRule.objects.filter(is_active=True).count()
            self.stdout.write(f"  ✓ قواعد التزامن النشطة: {active_rules}")

            # اختبار خدمة التزامن
            sync_service = PaymentSyncService()
            self.stdout.write("  ✓ خدمة التزامن متاحة")

        except Exception as e:
            self.stdout.write(f"  ❌ خطأ في نظام التزامن: {str(e)}")

    def create_test_data(self):
        """إنشاء بيانات اختبار وهمية"""
        self.stdout.write("📝 إنشاء بيانات اختبار وهمية...")

        try:
            with transaction.atomic():
                # الحصول على مستخدم للاختبار
                user = User.objects.first()
                if not user:
                    self.stdout.write("  ⚠️ لا يوجد مستخدمين في النظام")
                    return

                # إنشاء قيد اختبار
                journal_entry = JournalEntry.objects.create(
                    number="TEST-001",
                    date=timezone.now().date(),
                    entry_type="manual",
                    description="قيد اختبار للنظام المحاسبي",
                    reference="TEST-INTEGRATION",
                    created_by=user,
                )

                # الحصول على الحسابات
                cash_account = ChartOfAccounts.objects.get(code="1001")
                revenue_account = ChartOfAccounts.objects.get(code="4001")

                # إنشاء بنود القيد
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=cash_account,
                    debit=Decimal("1000.00"),
                    credit=Decimal("0.00"),
                    description="اختبار - مدين الصندوق",
                )

                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=revenue_account,
                    debit=Decimal("0.00"),
                    credit=Decimal("1000.00"),
                    description="اختبار - دائن الإيرادات",
                )

                # ترحيل القيد
                journal_entry.post(user)

                self.stdout.write(f"  ✓ تم إنشاء قيد اختبار: {journal_entry.number}")

                # اختبار الأرصدة بعد القيد
                cash_balance = cash_account.get_balance()
                revenue_balance = revenue_account.get_balance()

                self.stdout.write(f"  ✓ رصيد الصندوق بعد القيد: {cash_balance}")
                self.stdout.write(f"  ✓ رصيد الإيرادات بعد القيد: {revenue_balance}")

        except Exception as e:
            self.stdout.write(f"  ❌ خطأ في إنشاء بيانات الاختبار: {str(e)}")

    def generate_test_report(self):
        """إنشاء تقرير اختبار شامل"""
        self.stdout.write("📊 إنشاء تقرير الاختبار...")

        report = {
            "timestamp": timezone.now(),
            "accounts_count": ChartOfAccounts.objects.filter(is_active=True).count(),
            "journal_entries_count": JournalEntry.objects.count(),
            "posted_entries_count": JournalEntry.objects.filter(
                status="posted"
            ).count(),
            "open_periods_count": AccountingPeriod.objects.filter(
                status="open"
            ).count(),
        }

        self.stdout.write("📊 تقرير الاختبار:")
        for key, value in report.items():
            self.stdout.write(f"  • {key}: {value}")

        return report
