from django.core.management.base import BaseCommand
from django.db import transaction
from financial.models import ChartOfAccounts, JournalEntryLine


class Command(BaseCommand):
    help = "مراجعة وتنظيف الحسابات المكررة وغير المرغوبة"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="تأكيد حذف الحسابات",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض الحسابات المراد حذفها دون تنفيذ الحذف",
        )

    def handle(self, *args, **options):
        if not options["confirm"] and not options["dry_run"]:
            self.stdout.write(
                self.style.ERROR(
                    "يجب استخدام --confirm لتأكيد الحذف أو --dry-run لمعاينة العملية"
                )
            )
            return

        if options["dry_run"]:
            self.review_accounts()
        else:
            self.stdout.write(
                self.style.WARNING("سيتم حذف الحسابات المكررة وغير المرغوبة!")
            )
            response = input('هل أنت متأكد؟ اكتب "نعم" للمتابعة: ')
            if response.lower() in ["نعم", "yes", "y"]:
                self.cleanup_accounts()
            else:
                self.stdout.write(self.style.SUCCESS("تم إلغاء العملية"))

    def get_correct_accounts(self):
        """الحسابات الصحيحة التي يجب الاحتفاظ بها"""
        return {
            "الصندوق": "1010",
            "البنك": "1020",
            "مخزون البضاعة": "1030",
            "العملاء": "1040",
            "الموردين": "2010",
            "رأس المال": "3010",
            "إيرادات المبيعات": "4010",
            "تكلفة البضاعة المباعة": "5010",
            "مصروفات عمومية": "5020",
        }

    def get_unwanted_keywords(self):
        """الكلمات المفتاحية للحسابات غير المرغوبة"""
        return [
            "مبيعات خدمات",
            "خدمات",
            "service",
            "مصروفات إدارية",
            "إدارية",
            "admin",
            "مصروفات تسويق",
            "تسويق",
            "marketing",
            "selling",
            "مصروفات المشتريات",
            "إيرادات أخرى",
        ]

    def review_accounts(self):
        """مراجعة الحسابات"""
        self.stdout.write(self.style.HTTP_INFO("\n=== مراجعة دليل الحسابات ===\n"))

        all_accounts = ChartOfAccounts.objects.all().order_by("code")

        self.stdout.write(
            self.style.SUCCESS(f"📊 إجمالي الحسابات: {all_accounts.count()}\n")
        )

        # عرض جميع الحسابات
        self.stdout.write(self.style.HTTP_INFO("📋 جميع الحسابات:\n"))
        for account in all_accounts:
            status = "✅" if account.is_active else "❌"
            leaf = "🍃" if account.is_leaf else "🌳"
            cash = "💰" if account.is_cash_account else ""
            bank = "🏦" if account.is_bank_account else ""

            self.stdout.write(
                f"  {status} {leaf} [{account.code}] {account.name} "
                f"{cash}{bank} ({account.account_type.name})"
            )

        # تحديد الحسابات الصحيحة
        correct_accounts_map = self.get_correct_accounts()
        correct_codes = set(correct_accounts_map.values())

        # البحث عن التكرارات والحسابات القديمة
        self.stdout.write(self.style.WARNING(f"\n\n🔍 تحليل الحسابات:\n"))

        duplicates = []
        old_accounts = []

        for account in all_accounts:
            name_lower = account.name.lower().strip()

            # التحقق من أن الحساب ليس من الحسابات الصحيحة
            if account.code not in correct_codes:
                # البحث عن الحساب الصحيح المقابل
                for correct_name, correct_code in correct_accounts_map.items():
                    if (
                        correct_name.lower() in name_lower
                        or name_lower in correct_name.lower()
                    ):
                        # وجدنا حساب قديم له بديل صحيح
                        try:
                            correct_account = ChartOfAccounts.objects.get(
                                code=correct_code
                            )
                            duplicates.append({"old": account, "new": correct_account})
                        except ChartOfAccounts.DoesNotExist:
                            old_accounts.append(account)
                        break

        if duplicates:
            self.stdout.write(f"⚠️  وجدنا {len(duplicates)} حساب قديم له بديل:\n")
            for dup in duplicates:
                entries_count = JournalEntryLine.objects.filter(
                    account=dup["old"]
                ).count()
                warning = f" [{entries_count} قيد]" if entries_count > 0 else ""
                self.stdout.write(
                    f'  - [{dup["old"].code}] {dup["old"].name}{warning} '
                    f'→ سينقل إلى [{dup["new"].code}] {dup["new"].name}'
                )
        else:
            self.stdout.write("✅ لا توجد حسابات قديمة مكررة")

        # البحث عن الحسابات غير المرغوبة
        self.stdout.write(self.style.WARNING(f"\n\n🗑️  الحسابات غير المرغوبة:\n"))

        unwanted_keywords = self.get_unwanted_keywords()
        unwanted_accounts = []

        for account in all_accounts:
            for keyword in unwanted_keywords:
                if keyword.lower() in account.name.lower():
                    unwanted_accounts.append(account)
                    break

        if unwanted_accounts:
            self.stdout.write(f"❌ وجدنا {len(unwanted_accounts)} حساب غير مرغوب:\n")
            for account in unwanted_accounts:
                # التحقق من الاستخدام في قيود
                entries_count = JournalEntryLine.objects.filter(account=account).count()
                warning = f" ⚠️  [{entries_count} قيد]" if entries_count > 0 else ""

                self.stdout.write(f"  - [{account.code}] {account.name}{warning}")
        else:
            self.stdout.write("✅ لا توجد حسابات غير مرغوبة")

        # الملخص
        self.stdout.write(self.style.HTTP_INFO(f"\n\n📊 الملخص:\n"))
        self.stdout.write(f"  - إجمالي الحسابات: {all_accounts.count()}")
        self.stdout.write(
            f"  - حسابات نشطة: {all_accounts.filter(is_active=True).count()}"
        )
        self.stdout.write(f"  - حسابات مكررة: {len(duplicates)}")
        self.stdout.write(f"  - حسابات غير مرغوبة: {len(unwanted_accounts)}")

        # الحسابات المقترح حذفها/نقلها
        to_migrate = []  # حسابات قديمة ستنقل قيودها
        to_delete = []  # حسابات ستحذف مباشرة

        # إضافة الحسابات القديمة المكررة
        for dup in duplicates:
            to_migrate.append(dup)

        # إضافة الحسابات غير المرغوبة
        for account in unwanted_accounts:
            # التحقق من أنه ليس في قائمة المكررات
            is_duplicate = any(dup["old"] == account for dup in duplicates)
            if not is_duplicate:
                to_delete.append(account)

        if to_migrate:
            self.stdout.write(
                self.style.HTTP_INFO(
                    f"\n\n🔄 سيتم نقل القيود من {len(to_migrate)} حساب:\n"
                )
            )
            for dup in to_migrate:
                entries_count = JournalEntryLine.objects.filter(
                    account=dup["old"]
                ).count()
                self.stdout.write(
                    f'  🔄 [{dup["old"].code}] {dup["old"].name} ({entries_count} قيد) '
                    f'→ [{dup["new"].code}] {dup["new"].name}'
                )

        if to_delete:
            self.stdout.write(
                self.style.WARNING(f"\n\n🗑️  سيتم حذف {len(to_delete)} حساب:\n")
            )
            for account in to_delete:
                entries_count = JournalEntryLine.objects.filter(account=account).count()
                if entries_count > 0:
                    self.stdout.write(
                        f"  ⚠️  [{account.code}] {account.name} - سيتم تعطيله ({entries_count} قيد)"
                    )
                else:
                    self.stdout.write(
                        f"  ✅ [{account.code}] {account.name} - سيتم حذفه"
                    )

    def cleanup_accounts(self):
        """تنظيف الحسابات مع نقل القيود"""
        self.stdout.write(self.style.HTTP_INFO("\n=== بدء تنظيف الحسابات ===\n"))

        try:
            with transaction.atomic():
                all_accounts = ChartOfAccounts.objects.all().order_by("code")
                correct_accounts_map = self.get_correct_accounts()
                correct_codes = set(correct_accounts_map.values())

                # البحث عن الحسابات القديمة المكررة
                duplicates = []

                for account in all_accounts:
                    name_lower = account.name.lower().strip()

                    if account.code not in correct_codes:
                        for correct_name, correct_code in correct_accounts_map.items():
                            if (
                                correct_name.lower() in name_lower
                                or name_lower in correct_name.lower()
                            ):
                                try:
                                    correct_account = ChartOfAccounts.objects.get(
                                        code=correct_code
                                    )
                                    duplicates.append(
                                        {"old": account, "new": correct_account}
                                    )
                                except ChartOfAccounts.DoesNotExist:
                                    pass
                                break

                # نقل القيود والمدفوعات من الحسابات القديمة للجديدة
                migrated_count = 0

                if duplicates:
                    self.stdout.write(
                        self.style.HTTP_INFO("\n🔄 نقل القيود والمدفوعات:\n")
                    )

                    # استيراد نماذج المدفوعات
                    from sale.models import SalePayment
                    from purchase.models import PurchasePayment
                    from financial.models.cash_movements import CashMovement

                    for dup in duplicates:
                        old_account = dup["old"]
                        new_account = dup["new"]

                        # نقل القيود المحاسبية
                        entries = JournalEntryLine.objects.filter(account=old_account)
                        entries_count = entries.count()

                        if entries_count > 0:
                            entries.update(account=new_account)
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  ✅ [{old_account.code}] → [{new_account.code}] - تم نقل {entries_count} قيد"
                                )
                            )
                            migrated_count += entries_count

                        # نقل مدفوعات المبيعات
                        sale_payments = SalePayment.objects.filter(
                            financial_account=old_account
                        )
                        sale_payments_count = sale_payments.count()
                        if sale_payments_count > 0:
                            sale_payments.update(financial_account=new_account)
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  💰 [{old_account.code}] → [{new_account.code}] - تم نقل {sale_payments_count} دفعة مبيعات"
                                )
                            )

                        # نقل مدفوعات المشتريات
                        purchase_payments = PurchasePayment.objects.filter(
                            financial_account=old_account
                        )
                        purchase_payments_count = purchase_payments.count()
                        if purchase_payments_count > 0:
                            purchase_payments.update(financial_account=new_account)
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  💰 [{old_account.code}] → [{new_account.code}] - تم نقل {purchase_payments_count} دفعة مشتريات"
                                )
                            )

                        # نقل الحركات النقدية
                        cash_movements = CashMovement.objects.filter(
                            account=old_account
                        )
                        cash_movements_count = cash_movements.count()
                        if cash_movements_count > 0:
                            cash_movements.update(account=new_account)
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  💵 [{old_account.code}] → [{new_account.code}] - تم نقل {cash_movements_count} حركة نقدية"
                                )
                            )

                        # نقل الرصيد الافتتاحي إذا كان موجود
                        if (
                            old_account.opening_balance
                            and old_account.opening_balance != 0
                        ):
                            # إضافة الرصيد القديم للرصيد الجديد
                            new_account.opening_balance = (
                                new_account.opening_balance or 0
                            ) + old_account.opening_balance
                            new_account.save()
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  💰 [{old_account.code}] → [{new_account.code}] - تم نقل الرصيد الافتتاحي: {old_account.opening_balance}"
                                )
                            )

                        # حذف الحساب القديم
                        code = old_account.code
                        name = old_account.name
                        old_account.delete()
                        self.stdout.write(
                            self.style.SUCCESS(f"  🗑️  [{code}] {name} - تم الحذف")
                        )

                # البحث عن الحسابات غير المرغوبة
                unwanted_keywords = self.get_unwanted_keywords()
                unwanted_accounts = []

                for account in all_accounts:
                    # تخطي الحسابات المحذوفة بالفعل
                    if not ChartOfAccounts.objects.filter(id=account.id).exists():
                        continue

                    for keyword in unwanted_keywords:
                        if keyword.lower() in account.name.lower():
                            unwanted_accounts.append(account)
                            break

                # حذف الحسابات غير المرغوبة
                deleted_count = 0
                deactivated_count = 0

                if unwanted_accounts:
                    self.stdout.write(
                        self.style.HTTP_INFO("\n\n🗑️  حذف الحسابات غير المرغوبة:\n")
                    )
                    for account in unwanted_accounts:
                        entries_count = JournalEntryLine.objects.filter(
                            account=account
                        ).count()

                        if entries_count > 0:
                            # تعطيل الحساب
                            if account.is_active:
                                account.is_active = False
                                account.save()
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"  ⚠️  [{account.code}] {account.name} - تم التعطيل ({entries_count} قيد)"
                                    )
                                )
                                deactivated_count += 1
                        else:
                            # حذف الحساب
                            code = account.code
                            name = account.name
                            account.delete()
                            self.stdout.write(
                                self.style.SUCCESS(f"  ✅ [{code}] {name} - تم الحذف")
                            )
                            deleted_count += 1

                self.stdout.write(self.style.HTTP_INFO(f"\n📊 النتيجة النهائية:"))
                self.stdout.write(f"  - قيود تم نقلها: {migrated_count}")
                self.stdout.write(
                    f"  - حسابات تم حذفها: {deleted_count + len(duplicates)}"
                )
                self.stdout.write(f"  - حسابات تم تعطيلها: {deactivated_count}")

                self.stdout.write(self.style.SUCCESS("\n🎉 تم تنظيف الحسابات بنجاح!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ حدث خطأ أثناء التنظيف: {str(e)}"))
            raise
