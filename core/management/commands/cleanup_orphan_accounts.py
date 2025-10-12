from django.core.management.base import BaseCommand
from django.db import transaction
from financial.models import ChartOfAccounts, AccountType


class Command(BaseCommand):
    help = "حذف الحسابات المرتبطة بأنواع محذوفة أو غير موجودة"

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
        parser.add_argument(
            "--deactivate",
            action="store_true",
            help="تعطيل الحسابات بدلاً من حذفها",
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
            self.preview_cleanup()
        else:
            action = "تعطيل" if options["deactivate"] else "حذف"
            self.stdout.write(self.style.WARNING(f"سيتم {action} الحسابات اليتيمة!"))
            response = input('هل أنت متأكد؟ اكتب "نعم" للمتابعة: ')
            if response.lower() in ["نعم", "yes", "y"]:
                self.cleanup_accounts(deactivate=options["deactivate"])
            else:
                self.stdout.write(self.style.SUCCESS("تم إلغاء العملية"))

    def preview_cleanup(self):
        """معاينة الحسابات المراد حذفها"""
        self.stdout.write(self.style.HTTP_INFO("\n=== معاينة الحسابات اليتيمة ===\n"))

        # الحصول على الأنواع النشطة
        active_types = set(
            AccountType.objects.filter(is_active=True).values_list("id", flat=True)
        )

        # الحصول على جميع الحسابات
        all_accounts = ChartOfAccounts.objects.select_related("account_type").all()

        orphan_accounts = []
        inactive_type_accounts = []

        for account in all_accounts:
            if account.account_type_id not in active_types:
                try:
                    if account.account_type.is_active:
                        orphan_accounts.append(account)
                    else:
                        inactive_type_accounts.append(account)
                except:
                    orphan_accounts.append(account)

        # عرض الحسابات المرتبطة بأنواع غير نشطة
        if inactive_type_accounts:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  حسابات مرتبطة بأنواع غير نشطة ({len(inactive_type_accounts)}):\n"
                )
            )
            for account in inactive_type_accounts:
                self.stdout.write(
                    f"  [{account.code}] {account.name} "
                    f"← {account.account_type.name} (غير نشط)"
                )

        # عرض الحسابات اليتيمة
        if orphan_accounts:
            self.stdout.write(
                self.style.ERROR(f"\n❌ حسابات يتيمة ({len(orphan_accounts)}):\n")
            )
            for account in orphan_accounts:
                try:
                    type_name = account.account_type.name
                except:
                    type_name = "نوع محذوف"
                self.stdout.write(f"  [{account.code}] {account.name} ← {type_name}")

        # التحقق من الحسابات المستخدمة في القيود
        from financial.models import JournalEntryLine

        all_problem_accounts = orphan_accounts + inactive_type_accounts
        accounts_with_entries = []

        for account in all_problem_accounts:
            entries_count = JournalEntryLine.objects.filter(account=account).count()
            if entries_count > 0:
                accounts_with_entries.append((account, entries_count))

        if accounts_with_entries:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  حسابات مستخدمة في قيود ({len(accounts_with_entries)}):\n"
                )
            )
            for account, count in accounts_with_entries:
                self.stdout.write(f"  [{account.code}] {account.name} - {count} قيد")
            self.stdout.write(
                self.style.HTTP_INFO(
                    "\n💡 توصية: استخدم --deactivate لتعطيل هذه الحسابات بدلاً من حذفها"
                )
            )

        # الملخص
        self.stdout.write(self.style.HTTP_INFO(f"\n📊 الملخص:"))
        self.stdout.write(f"  - إجمالي الحسابات: {all_accounts.count()}")
        self.stdout.write(
            f"  - حسابات سليمة: {all_accounts.count() - len(all_problem_accounts)}"
        )
        self.stdout.write(f"  - حسابات بأنواع غير نشطة: {len(inactive_type_accounts)}")
        self.stdout.write(f"  - حسابات يتيمة: {len(orphan_accounts)}")
        self.stdout.write(f"  - حسابات مستخدمة في قيود: {len(accounts_with_entries)}")

    def cleanup_accounts(self, deactivate=False):
        """حذف أو تعطيل الحسابات اليتيمة"""
        action = "تعطيل" if deactivate else "حذف"
        self.stdout.write(
            self.style.HTTP_INFO(f"\n=== بدء {action} الحسابات اليتيمة ===\n")
        )

        try:
            with transaction.atomic():
                # الحصول على الأنواع النشطة
                active_types = set(
                    AccountType.objects.filter(is_active=True).values_list(
                        "id", flat=True
                    )
                )

                # الحصول على جميع الحسابات
                all_accounts = ChartOfAccounts.objects.select_related(
                    "account_type"
                ).all()

                problem_accounts = []

                for account in all_accounts:
                    if account.account_type_id not in active_types:
                        problem_accounts.append(account)

                if not problem_accounts:
                    self.stdout.write(self.style.SUCCESS("✅ لا توجد حسابات يتيمة!"))
                    return

                # التحقق من الحسابات المستخدمة في القيود
                from financial.models import JournalEntryLine

                deactivated_count = 0
                deleted_count = 0
                skipped_count = 0

                for account in problem_accounts:
                    entries_count = JournalEntryLine.objects.filter(
                        account=account
                    ).count()

                    if entries_count > 0:
                        # الحسابات المستخدمة في قيود: تعطيل فقط
                        if not account.is_active:
                            self.stdout.write(
                                f"  ⏭️  [{account.code}] {account.name} - معطل بالفعل"
                            )
                            skipped_count += 1
                        else:
                            account.is_active = False
                            account.save()
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  ⚠️  [{account.code}] {account.name} - تم التعطيل ({entries_count} قيد)"
                                )
                            )
                            deactivated_count += 1
                    else:
                        # الحسابات غير المستخدمة
                        if deactivate:
                            if not account.is_active:
                                skipped_count += 1
                            else:
                                account.is_active = False
                                account.save()
                                self.stdout.write(
                                    f"  🔒 [{account.code}] {account.name} - تم التعطيل"
                                )
                                deactivated_count += 1
                        else:
                            account.delete()
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  ✅ [{account.code}] {account.name} - تم الحذف"
                                )
                            )
                            deleted_count += 1

                self.stdout.write(self.style.HTTP_INFO(f"\n📊 النتيجة النهائية:"))
                if deactivate:
                    self.stdout.write(f"  - تم التعطيل: {deactivated_count}")
                    self.stdout.write(f"  - معطلة مسبقاً: {skipped_count}")
                else:
                    self.stdout.write(f"  - تم الحذف: {deleted_count}")
                    self.stdout.write(f"  - تم التعطيل (مستخدمة): {deactivated_count}")
                    self.stdout.write(f"  - معطلة مسبقاً: {skipped_count}")

                self.stdout.write(
                    self.style.SUCCESS(f"\n🎉 تم {action} الحسابات اليتيمة بنجاح!")
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ حدث خطأ أثناء {action}: {str(e)}"))
            raise
