from django.core.management.base import BaseCommand
from django.db.models import Sum
from financial.models import ChartOfAccounts, JournalEntryLine


class Command(BaseCommand):
    help = "تصفير الأرصدة الافتتاحية (الرصيد الحقيقي يُحسب من القيود)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="تصفير جميع الأرصدة الافتتاحية",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.reset_opening_balances()
        else:
            self.show_current_balances()

    def reset_opening_balances(self):
        """تصفير جميع الأرصدة الافتتاحية"""
        self.stdout.write(self.style.HTTP_INFO("\n=== تصفير الأرصدة الافتتاحية ===\n"))

        accounts = ChartOfAccounts.objects.all()
        updated_count = 0

        for account in accounts:
            if account.opening_balance and account.opening_balance != 0:
                old_balance = account.opening_balance
                account.opening_balance = 0
                account.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ [{account.code}] {account.name}: {old_balance} → 0"
                    )
                )
                updated_count += 1

        self.stdout.write(self.style.HTTP_INFO(f"\n📊 النتيجة:"))
        self.stdout.write(f"  - إجمالي الحسابات: {accounts.count()}")
        self.stdout.write(f"  - تم تصفيرها: {updated_count}")

        self.stdout.write(self.style.SUCCESS("\n🎉 تم تصفير الأرصدة الافتتاحية بنجاح!"))
        self.stdout.write(
            self.style.HTTP_INFO("\n💡 الرصيد الحقيقي لكل حساب يُحسب من القيود المرحلة")
        )

    def show_current_balances(self):
        """عرض الأرصدة الحالية (من القيود المرحلة)"""
        self.stdout.write(
            self.style.HTTP_INFO("\n=== الأرصدة الحالية (من القيود المرحلة) ===\n")
        )

        accounts = ChartOfAccounts.objects.all().order_by("code")

        for account in accounts:
            # حساب الرصيد من القيود المرحلة فقط
            lines = JournalEntryLine.objects.filter(
                account=account, journal_entry__status="posted"
            )
            total_debit = lines.aggregate(Sum("debit"))["debit__sum"] or 0
            total_credit = lines.aggregate(Sum("credit"))["credit__sum"] or 0

            # حساب الرصيد حسب طبيعة الحساب
            if account.account_type.nature == "debit":
                current_balance = total_debit - total_credit
            else:
                current_balance = total_credit - total_debit

            # عرض الرصيد
            if current_balance != 0:
                icon = (
                    "💰"
                    if account.is_cash_account
                    else "🏦"
                    if account.is_bank_account
                    else "📊"
                )
                self.stdout.write(
                    f"{icon} [{account.code}] {account.name}: {current_balance:,.2f}"
                )

        self.stdout.write(self.style.HTTP_INFO(f"\n💡 ملاحظة:"))
        self.stdout.write("  - هذه الأرصدة محسوبة من القيود المرحلة فقط")
        self.stdout.write(
            "  - الرصيد الافتتاحي = 0 (يُستخدم فقط للرصيد قبل بداية النظام)"
        )
        self.stdout.write(
            "  - لتصفير الأرصدة الافتتاحية: python manage.py recalculate_balances --reset"
        )
