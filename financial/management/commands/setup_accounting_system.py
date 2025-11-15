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
        """إنشاء الحسابات المحاسبية الأساسية - طبق الأصل من قاعدة البيانات الحالية"""
        self.stdout.write("💰 إنشاء الحسابات المحاسبية الأساسية...")

        # الحصول على أنواع الحسابات بالـ ID المطابق للـ migration
        try:
            asset_type = AccountType.objects.get(pk=1)  # الأصول
            current_asset_type = AccountType.objects.get(pk=2)  # الأصول المتداولة
            cash_type = AccountType.objects.get(pk=3)  # الخزينة
            bank_type = AccountType.objects.get(pk=4)  # البنوك
            receivables_type = AccountType.objects.get(pk=5)  # العملاء
            inventory_type = AccountType.objects.get(pk=6)  # المخزون
            liability_type = AccountType.objects.get(pk=7)  # الخصوم
            current_liability_type = AccountType.objects.get(pk=8)  # الخصوم المتداولة
            payables_type = AccountType.objects.get(pk=9)  # الموردون
            equity_type = AccountType.objects.get(pk=10)  # حقوق الملكية
            capital_type = AccountType.objects.get(pk=11)  # رأس المال
            partner_type = AccountType.objects.get(pk=12)  # حساب جاري الشريك
            revenue_type = AccountType.objects.get(pk=13)  # الإيرادات
            sales_revenue_type = AccountType.objects.get(pk=14)  # إيرادات المبيعات
            other_revenue_type = AccountType.objects.get(pk=15)  # إيرادات متنوعة
            expense_type = AccountType.objects.get(pk=16)  # المصروفات
            cogs_type = AccountType.objects.get(pk=17)  # تكلفة البضاعة المباعة
            other_expense_type = AccountType.objects.get(pk=18)  # مصروفات متنوعة
        except AccountType.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f"نوع حساب مفقود: {e}"))
            return

        accounts_data = [
            # الحسابات الرئيسية
            {
                "code": "10000",
                "name": "الأصول",
                "name_en": "",
                "account_type": asset_type,
                "parent": None,
                "is_leaf": False,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "20000",
                "name": "الخصوم",
                "name_en": "",
                "account_type": liability_type,
                "parent": None,
                "is_leaf": False,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "30000",
                "name": "حقوق الملكية",
                "name_en": "",
                "account_type": equity_type,
                "parent": None,
                "is_leaf": False,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "40000",
                "name": "الإيرادات",
                "name_en": "",
                "account_type": revenue_type,
                "parent": None,
                "is_leaf": False,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "50000",
                "name": "المصروفات",
                "name_en": "",
                "account_type": expense_type,
                "parent": None,
                "is_leaf": False,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            # الحسابات الفرعية - الأصول
            {
                "code": "11011",
                "name": "الصندوق الرئيسي",
                "name_en": "Main Cash Box",
                "account_type": cash_type,
                "parent_code": "10000",
                "is_leaf": True,
                "is_cash_account": True,
                "is_bank_account": False,
            },
            {
                "code": "11021",
                "name": "البنك الأهلي",
                "name_en": "National Bank",
                "account_type": bank_type,
                "parent_code": "10000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": True,
            },
            {
                "code": "11030",
                "name": "العملاء",
                "name_en": "Customers",
                "account_type": receivables_type,
                "parent_code": "10000",
                "is_leaf": False,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "11051",
                "name": "مخزون البضاعة",
                "name_en": "Inventory",
                "account_type": inventory_type,
                "parent_code": "10000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            # الحسابات الفرعية - الخصوم
            {
                "code": "21010",
                "name": "الموردون",
                "name_en": "Suppliers",
                "account_type": payables_type,
                "parent_code": "20000",
                "is_leaf": False,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "21020",
                "name": "مستحقات الرواتب",
                "name_en": "Salaries Payable",
                "account_type": current_liability_type,
                "parent_code": "20000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "22010",
                "name": "القروض طويلة الأجل",
                "name_en": "Long-term Loans",
                "account_type": liability_type,
                "parent_code": "20000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            # الحسابات الفرعية - حقوق الملكية
            {
                "code": "31010",
                "name": "رأس المال",
                "name_en": "Capital",
                "account_type": capital_type,
                "parent_code": "30000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "31020",
                "name": "جاري الشريك",
                "name_en": "Partner Current Account",
                "account_type": partner_type,
                "parent_code": "30000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            # الحسابات الفرعية - الإيرادات
            {
                "code": "41010",
                "name": "إيرادات المبيعات",
                "name_en": "Sales Revenue",
                "account_type": sales_revenue_type,
                "parent_code": "40000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "42010",
                "name": "إيرادات متنوعة",
                "name_en": "Other Revenue",
                "account_type": other_revenue_type,
                "parent_code": "40000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            # الحسابات الفرعية - المصروفات
            {
                "code": "51010",
                "name": "تكلفة البضاعة المباعة",
                "name_en": "Cost of Goods Sold",
                "account_type": cogs_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "52010",
                "name": "مصروفات الشحن",
                "name_en": "Shipping Expenses",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "52020",
                "name": "الرواتب والأجور",
                "name_en": "Salaries and Wages",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "53010",
                "name": "المصروفات التسويقية",
                "name_en": "Marketing Expenses",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "54010",
                "name": "مصروفات متنوعة",
                "name_en": "General Expenses",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            
            # حسابات الرواتب - المصروفات
            {
                "code": "52021",
                "name": "البدلات الثابتة",
                "name_en": "Fixed Allowances",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "52022",
                "name": "المكافآت والحوافز",
                "name_en": "Bonuses and Incentives",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "52023",
                "name": "بدل السكن",
                "name_en": "Housing Allowance",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "52024",
                "name": "بدل النقل",
                "name_en": "Transportation Allowance",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "52025",
                "name": "التأمينات الاجتماعية",
                "name_en": "Social Insurance",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "52026",
                "name": "ضريبة الدخل",
                "name_en": "Income Tax",
                "account_type": other_expense_type,
                "parent_code": "50000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            
            # حسابات الرواتب - الخصوم
            {
                "code": "21030",
                "name": "سلف الموظفين",
                "name_en": "Employee Advances",
                "account_type": current_liability_type,
                "parent_code": "20000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "21031",
                "name": "مستحقات الرواتب الإضافية",
                "name_en": "Additional Salaries Payable",
                "account_type": current_liability_type,
                "parent_code": "20000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "21032",
                "name": "التأمينات الاجتماعية مستحقة",
                "name_en": "Social Insurance Payable",
                "account_type": current_liability_type,
                "parent_code": "20000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "21033",
                "name": "اشتراكات النقابة",
                "name_en": "Union Subscriptions",
                "account_type": current_liability_type,
                "parent_code": "20000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
            {
                "code": "21034",
                "name": "التأمين الطبي",
                "name_en": "Medical Insurance",
                "account_type": current_liability_type,
                "parent_code": "20000",
                "is_leaf": True,
                "is_cash_account": False,
                "is_bank_account": False,
            },
        ]

        created_count = 0
        
        # إنشاء الحسابات الرئيسية أولاً
        main_accounts = {}
        for account_data in accounts_data:
            if account_data.get("parent") is None and "parent_code" not in account_data:
                # إنشاء الحساب الرئيسي
                account_dict = {
                    "code": account_data["code"],
                    "name": account_data["name"],
                    "name_en": account_data["name_en"],
                    "account_type": account_data["account_type"],
                    "parent": None,
                    "is_active": True,
                    "is_leaf": account_data["is_leaf"],
                    "is_cash_account": account_data["is_cash_account"],
                    "is_bank_account": account_data["is_bank_account"],
                    "opening_balance": 0.0,
                }
                
                account, created = ChartOfAccounts.objects.get_or_create(
                    code=account_data["code"], 
                    defaults=account_dict
                )
                
                main_accounts[account_data["code"]] = account
                
                if created or force:
                    if force and not created:
                        for key, value in account_dict.items():
                            if key != "code":
                                setattr(account, key, value)
                        account.save()
                    
                    created_count += 1
                    self.stdout.write(f"  ✓ {account.code} - {account.name}")
        
        # إنشاء الحسابات الفرعية
        for account_data in accounts_data:
            if "parent_code" in account_data:
                parent_account = main_accounts.get(account_data["parent_code"])
                if not parent_account:
                    self.stdout.write(self.style.ERROR(f"الحساب الأب غير موجود: {account_data['parent_code']}"))
                    continue
                
                account_dict = {
                    "code": account_data["code"],
                    "name": account_data["name"],
                    "name_en": account_data["name_en"],
                    "account_type": account_data["account_type"],
                    "parent": parent_account,
                    "is_active": True,
                    "is_leaf": account_data["is_leaf"],
                    "is_cash_account": account_data["is_cash_account"],
                    "is_bank_account": account_data["is_bank_account"],
                    "opening_balance": 0.0,
                }
                
                account, created = ChartOfAccounts.objects.get_or_create(
                    code=account_data["code"], 
                    defaults=account_dict
                )
                
                if created or force:
                    if force and not created:
                        for key, value in account_dict.items():
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

        # التحقق من وجود الحسابات الأساسية - طبق الأصل من قاعدة البيانات
        expected_accounts = [
            "10000", "11011", "11021", "11030", "11051",  # الأصول
            "20000", "21010", "21020", "22010",           # الخصوم الأساسية
            "21030", "21031", "21032", "21033", "21034", # حسابات الرواتب - الخصوم
            "30000", "31010", "31020",                    # حقوق الملكية
            "40000", "41010", "42010",                    # الإيرادات
            "50000", "51010", "52010", "52020", "53010", "54010",  # المصروفات الأساسية
            "52021", "52022", "52023", "52024", "52025", "52026"   # حسابات الرواتب - المصروفات
        ]
        
        basic_accounts_count = ChartOfAccounts.objects.filter(
            code__in=expected_accounts,
            is_active=True,
        ).count()
        self.stdout.write(f"  ✓ الحسابات الأساسية: {basic_accounts_count}/{len(expected_accounts)}")

        # التحقق من الحسابات الحرجة
        critical_accounts = ["11011", "11021", "11030", "21010", "41010", "51010"]
        critical_count = ChartOfAccounts.objects.filter(
            code__in=critical_accounts,
            is_active=True,
        ).count()
        self.stdout.write(f"  ✓ الحسابات الحرجة: {critical_count}/{len(critical_accounts)}")

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

        # التحقق النهائي
        if basic_accounts_count == len(expected_accounts) and critical_count == len(critical_accounts) and open_periods > 0:
            self.stdout.write("🔍 النظام المحاسبي جاهز للعمل! (طبق الأصل من قاعدة البيانات)")
        else:
            self.stdout.write("⚠️ النظام المحاسبي يحتاج إعداد إضافي")
            if basic_accounts_count < len(expected_accounts):
                missing = len(expected_accounts) - basic_accounts_count
                self.stdout.write(f"  - ينقص {missing} حساب أساسي")
            if critical_count < len(critical_accounts):
                missing = len(critical_accounts) - critical_count
                self.stdout.write(f"  - ينقص {missing} حساب حرج")
