from django.core.management.base import BaseCommand
from django.db import transaction
from financial.models import ChartOfAccounts, AccountType
from datetime import date


class Command(BaseCommand):
    help = "إضافة الحسابات الأساسية لنظام إدارة المخزون"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="تأكيد إضافة الحسابات",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض الحسابات المراد إضافتها دون تنفيذ الإضافة",
        )

    def handle(self, *args, **options):
        if not options["confirm"] and not options["dry_run"]:
            self.stdout.write(
                self.style.ERROR(
                    "يجب استخدام --confirm لتأكيد الإضافة أو --dry-run لمعاينة العملية"
                )
            )
            return

        if options["dry_run"]:
            self.preview_accounts()
        else:
            self.stdout.write(self.style.WARNING("سيتم إضافة الحسابات الأساسية!"))
            response = input('هل أنت متأكد؟ اكتب "نعم" للمتابعة: ')
            if response.lower() in ["نعم", "yes", "y"]:
                self.create_accounts()
            else:
                self.stdout.write(self.style.SUCCESS("تم إلغاء العملية"))

    def get_essential_accounts(self):
        """قائمة الحسابات الأساسية"""
        return [
            # الأصول - النقدية
            {
                "code": "1010",
                "name": "الصندوق",
                "type_code": "CASH",
                "is_cash_account": True,
                "is_leaf": True,
                "priority": "عالية",
            },
            # الأصول - البنوك
            {
                "code": "1020",
                "name": "البنك",
                "type_code": "BANK",
                "is_bank_account": True,
                "is_leaf": True,
                "priority": "عالية",
            },
            # الأصول - المخزون
            {
                "code": "1030",
                "name": "مخزون البضاعة",
                "type_code": "INVENTORY",
                "is_leaf": True,
                "priority": "عالية",
            },
            # الأصول - العملاء
            {
                "code": "1040",
                "name": "العملاء",
                "type_code": "RECEIVABLES",
                "is_leaf": True,
                "priority": "عالية",
            },
            # الخصوم - الموردين
            {
                "code": "2010",
                "name": "الموردين",
                "type_code": "PAYABLES",
                "is_leaf": True,
                "priority": "عالية",
            },
            # حقوق الملكية
            {
                "code": "3010",
                "name": "رأس المال",
                "type_code": "CAPITAL",
                "is_leaf": True,
                "priority": "عالية",
            },
            # الإيرادات
            {
                "code": "4010",
                "name": "إيرادات المبيعات",
                "type_code": "SALES_REVENUE",
                "is_leaf": True,
                "priority": "عالية",
            },
            # المصروفات - تكلفة البضاعة
            {
                "code": "5010",
                "name": "تكلفة البضاعة المباعة",
                "type_code": "COGS",
                "is_leaf": True,
                "priority": "عالية",
            },
            # المصروفات - التشغيلية
            {
                "code": "5020",
                "name": "مصروفات عمومية",
                "type_code": "OPERATING_EXPENSE",
                "is_leaf": True,
                "priority": "عالية",
            },
        ]

    def preview_accounts(self):
        """معاينة الحسابات المراد إضافتها"""
        self.stdout.write(self.style.HTTP_INFO("\n=== معاينة الحسابات الأساسية ===\n"))

        accounts = self.get_essential_accounts()

        to_add = []
        existing = []

        for account_data in accounts:
            exists = ChartOfAccounts.objects.filter(code=account_data["code"]).exists()

            if exists:
                existing.append(account_data)
            else:
                to_add.append(account_data)

        # عرض الحسابات الموجودة
        if existing:
            self.stdout.write(
                self.style.SUCCESS(f"\n✅ حسابات موجودة بالفعل ({len(existing)}):\n")
            )
            for acc in existing:
                self.stdout.write(f'  [{acc["code"]}] {acc["name"]}')

        # عرض الحسابات المراد إضافتها
        if to_add:
            self.stdout.write(
                self.style.WARNING(f"\n➕ حسابات سيتم إضافتها ({len(to_add)}):\n")
            )

            current_type = None
            for acc in to_add:
                try:
                    acc_type = AccountType.objects.get(code=acc["type_code"])
                    if acc_type != current_type:
                        current_type = acc_type
                        self.stdout.write(
                            f'\n{self.get_icon(acc["type_code"])} {acc_type.name}:'
                        )

                    priority_icon = {"عالية": "🔴", "متوسطة": "🟡", "منخفضة": "🟢"}.get(
                        acc["priority"], "⚪"
                    )

                    self.stdout.write(
                        f'  {priority_icon} [{acc["code"]}] {acc["name"]} '
                        f'({acc["priority"]} الأولوية)'
                    )
                except AccountType.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(
                            f'  ❌ [{acc["code"]}] {acc["name"]} - النوع {acc["type_code"]} غير موجود!'
                        )
                    )
        else:
            self.stdout.write(
                self.style.SUCCESS("\n✅ جميع الحسابات الأساسية موجودة بالفعل!")
            )

        self.stdout.write(self.style.HTTP_INFO(f"\n📊 الملخص:"))
        self.stdout.write(f"  - إجمالي الحسابات: {len(accounts)}")
        self.stdout.write(f"  - موجودة: {len(existing)}")
        self.stdout.write(f"  - سيتم إضافتها: {len(to_add)}")

    def create_accounts(self):
        """إنشاء الحسابات الأساسية"""
        self.stdout.write(
            self.style.HTTP_INFO("\n=== بدء إضافة الحسابات الأساسية ===\n")
        )

        try:
            with transaction.atomic():
                accounts = self.get_essential_accounts()
                added_count = 0
                skipped_count = 0
                error_count = 0

                for account_data in accounts:
                    # التحقق من وجود الحساب
                    if ChartOfAccounts.objects.filter(
                        code=account_data["code"]
                    ).exists():
                        self.stdout.write(
                            f'  ⏭️  [{account_data["code"]}] {account_data["name"]} - موجود بالفعل'
                        )
                        skipped_count += 1
                        continue

                    try:
                        # الحصول على نوع الحساب
                        account_type = AccountType.objects.get(
                            code=account_data["type_code"]
                        )

                        # إنشاء الحساب
                        account = ChartOfAccounts.objects.create(
                            code=account_data["code"],
                            name=account_data["name"],
                            account_type=account_type,
                            is_leaf=account_data.get("is_leaf", True),
                            is_cash_account=account_data.get("is_cash_account", False),
                            is_bank_account=account_data.get("is_bank_account", False),
                            is_active=True,
                            opening_balance=0.00,
                            opening_balance_date=date.today(),
                        )

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✅ [{account.code}] {account.name} - تم الإضافة"
                            )
                        )
                        added_count += 1

                    except AccountType.DoesNotExist:
                        self.stdout.write(
                            self.style.ERROR(
                                f'  ❌ [{account_data["code"]}] {account_data["name"]} - النوع غير موجود!'
                            )
                        )
                        error_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'  ❌ [{account_data["code"]}] {account_data["name"]} - خطأ: {str(e)}'
                            )
                        )
                        error_count += 1

                self.stdout.write(self.style.HTTP_INFO(f"\n📊 النتيجة النهائية:"))
                self.stdout.write(f"  - تم إضافتها: {added_count}")
                self.stdout.write(f"  - موجودة مسبقاً: {skipped_count}")
                self.stdout.write(f"  - أخطاء: {error_count}")

                if error_count == 0:
                    self.stdout.write(
                        self.style.SUCCESS("\n🎉 تم إضافة الحسابات الأساسية بنجاح!")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"\n⚠️  تمت الإضافة مع {error_count} خطأ")
                    )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ حدث خطأ أثناء الإضافة: {str(e)}"))
            raise

    def get_icon(self, code):
        """الحصول على أيقونة النوع"""
        icons = {
            "CASH": "💰",
            "BANK": "🏦",
            "INVENTORY": "📦",
            "RECEIVABLES": "👥",
            "PAYABLES": "🏪",
            "CAPITAL": "💎",
            "SALES_REVENUE": "💸",
            "COGS": "📉",
            "OPERATING_EXPENSE": "🔧",
        }
        return icons.get(code, "📁")
