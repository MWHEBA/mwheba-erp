"""
أمر Django لإعداد النظام المحاسبي الأساسي
يقوم بإنشاء الحسابات والفترات المحاسبية الأساسية
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date, datetime
import logging

from financial.models import AccountType, ChartOfAccounts, AccountingPeriod
from financial.services.accounting_integration_service import (
    AccountingIntegrationService,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "إعداد النظام المحاسبي الأساسي مع الحسابات والفترات المحاسبية"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="إعادة إنشاء الحسابات حتى لو كانت موجودة",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=timezone.now().year,
            help="السنة المالية لإنشاء الفترة المحاسبية",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 بدء إعداد النظام المحاسبي الأساسي..."))

        try:
            with transaction.atomic():
                # 1. إنشاء أنواع الحسابات الأساسية
                self.create_account_types(options["force"])

                # 2. إنشاء الحسابات المحاسبية الأساسية
                self.create_basic_accounts(options["force"])

                # 3. إنشاء الفترة المحاسبية
                self.create_accounting_period(options["year"])

                # 4. التحقق من سلامة النظام
                self.verify_system_integrity()

                self.stdout.write(
                    self.style.SUCCESS("✅ تم إعداد النظام المحاسبي بنجاح!")
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ خطأ في إعداد النظام المحاسبي: {str(e)}")
            )
            logger.error(f"خطأ في إعداد النظام المحاسبي: {str(e)}")
            raise

    def create_account_types(self, force=False):
        """إنشاء أنواع الحسابات الأساسية"""
        self.stdout.write("📋 إنشاء أنواع الحسابات الأساسية...")

        account_types_data = [
            {
                "code": "ASSET",
                "name": "أصول",
                "category": "asset",
                "nature": "debit",
                "level": 1,
            },
            {
                "code": "LIABILITY",
                "name": "خصوم",
                "category": "liability",
                "nature": "credit",
                "level": 1,
            },
            {
                "code": "EQUITY",
                "name": "حقوق الملكية",
                "category": "equity",
                "nature": "credit",
                "level": 1,
            },
            {
                "code": "REVENUE",
                "name": "إيرادات",
                "category": "revenue",
                "nature": "credit",
                "level": 1,
            },
            {
                "code": "EXPENSE",
                "name": "مصروفات",
                "category": "expense",
                "nature": "debit",
                "level": 1,
            },
        ]

        created_count = 0
        for type_data in account_types_data:
            account_type, created = AccountType.objects.get_or_create(
                code=type_data["code"],
                defaults={
                    "name": type_data["name"],
                    "category": type_data["category"],
                    "nature": type_data["nature"],
                    "level": type_data["level"],
                    "is_active": True,
                },
            )

            if created or force:
                if force and not created:
                    # تحديث البيانات الموجودة
                    for key, value in type_data.items():
                        if key != "code":
                            setattr(account_type, key, value)
                    account_type.save()

                created_count += 1
                self.stdout.write(f"  ✓ {account_type.name} ({account_type.code})")

        self.stdout.write(f"📋 تم إنشاء/تحديث {created_count} نوع حساب")

    def create_basic_accounts(self, force=False):
        """إنشاء الحسابات المحاسبية الأساسية"""
        self.stdout.write("💰 إنشاء الحسابات المحاسبية الأساسية...")

        # الحصول على أنواع الحسابات
        asset_type = AccountType.objects.get(code="ASSET")
        liability_type = AccountType.objects.get(code="LIABILITY")
        revenue_type = AccountType.objects.get(code="REVENUE")
        expense_type = AccountType.objects.get(code="EXPENSE")

        accounts_data = [
            # الأصول
            {
                "code": "1001",
                "name": "الصندوق",
                "name_en": "Cash",
                "account_type": asset_type,
                "is_cash_account": True,
                "is_leaf": True,
                "description": "النقدية في الصندوق",
            },
            {
                "code": "1002",
                "name": "البنك",
                "name_en": "Bank",
                "account_type": asset_type,
                "is_bank_account": True,
                "is_reconcilable": True,
                "is_leaf": True,
                "description": "الأرصدة البنكية",
            },
            {
                "code": "1201",
                "name": "العملاء",
                "name_en": "Accounts Receivable",
                "account_type": asset_type,
                "is_leaf": True,
                "description": "المبالغ المستحقة من العملاء",
            },
            {
                "code": "1301",
                "name": "المخزون",
                "name_en": "Inventory",
                "account_type": asset_type,
                "is_leaf": True,
                "description": "قيمة البضائع المخزنة",
            },
            # الخصوم
            {
                "code": "2101",
                "name": "الموردين",
                "name_en": "Accounts Payable",
                "account_type": liability_type,
                "is_leaf": True,
                "description": "المبالغ المستحقة للموردين",
            },
            # الإيرادات
            {
                "code": "4001",
                "name": "إيرادات المبيعات",
                "name_en": "Sales Revenue",
                "account_type": revenue_type,
                "is_leaf": True,
                "description": "إيرادات من بيع البضائع والخدمات",
            },
            # المصروفات
            {
                "code": "5001",
                "name": "تكلفة البضاعة المباعة",
                "name_en": "Cost of Goods Sold",
                "account_type": expense_type,
                "is_leaf": True,
                "description": "تكلفة البضائع التي تم بيعها",
            },
            {
                "code": "5002",
                "name": "مصروفات المشتريات",
                "name_en": "Purchase Expenses",
                "account_type": expense_type,
                "is_leaf": True,
                "description": "مصروفات متعلقة بالمشتريات",
            },
        ]

        created_count = 0
        for account_data in accounts_data:
            account, created = ChartOfAccounts.objects.get_or_create(
                code=account_data["code"], defaults=account_data
            )

            if created or force:
                if force and not created:
                    # تحديث البيانات الموجودة
                    for key, value in account_data.items():
                        if key != "code":
                            setattr(account, key, value)
                    account.save()

                created_count += 1
                self.stdout.write(f"  ✓ {account.code} - {account.name}")

        self.stdout.write(f"💰 تم إنشاء/تحديث {created_count} حساب محاسبي")

    def create_accounting_period(self, year):
        """إنشاء الفترة المحاسبية للسنة المحددة"""
        self.stdout.write(f"📅 إنشاء الفترة المحاسبية لسنة {year}...")

        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

        period, created = AccountingPeriod.objects.get_or_create(
            start_date=start_date,
            end_date=end_date,
            defaults={"name": f"السنة المالية {year}", "status": "open"},
        )

        if created:
            self.stdout.write(f"  ✓ تم إنشاء الفترة المحاسبية: {period.name}")
        else:
            self.stdout.write(f"  ℹ️ الفترة المحاسبية موجودة مسبقاً: {period.name}")

    def verify_system_integrity(self):
        """التحقق من سلامة النظام المحاسبي"""
        self.stdout.write("🔍 التحقق من سلامة النظام المحاسبي...")

        # التحقق من وجود أنواع الحسابات
        account_types_count = AccountType.objects.filter(is_active=True).count()
        self.stdout.write(f"  ✓ أنواع الحسابات النشطة: {account_types_count}")

        # التحقق من وجود الحسابات الأساسية
        basic_accounts_count = ChartOfAccounts.objects.filter(
            code__in=["1001", "1002", "1201", "1301", "2101", "4001", "5001", "5002"],
            is_active=True,
        ).count()
        self.stdout.write(f"  ✓ الحسابات الأساسية: {basic_accounts_count}/8")

        # التحقق من وجود فترة محاسبية مفتوحة
        open_periods = AccountingPeriod.objects.filter(status="open").count()
        self.stdout.write(f"  ✓ الفترات المحاسبية المفتوحة: {open_periods}")

        # اختبار خدمة التكامل المحاسبي
        try:
            accounts = AccountingIntegrationService._get_required_accounts_for_sale()
            if accounts and len(accounts) >= 4:
                self.stdout.write("  ✓ خدمة التكامل المحاسبي جاهزة للمبيعات")
            else:
                self.stdout.write(
                    "  ⚠️ خدمة التكامل المحاسبي تحتاج حسابات إضافية للمبيعات"
                )

            accounts = (
                AccountingIntegrationService._get_required_accounts_for_purchase()
            )
            if accounts and len(accounts) >= 4:
                self.stdout.write("  ✓ خدمة التكامل المحاسبي جاهزة للمشتريات")
            else:
                self.stdout.write(
                    "  ⚠️ خدمة التكامل المحاسبي تحتاج حسابات إضافية للمشتريات"
                )

        except Exception as e:
            self.stdout.write(f"  ❌ خطأ في اختبار خدمة التكامل: {str(e)}")

        if basic_accounts_count == 8 and open_periods > 0:
            self.stdout.write("🔍 النظام المحاسبي جاهز للعمل!")
        else:
            self.stdout.write("⚠️ النظام المحاسبي يحتاج إعداد إضافي")
