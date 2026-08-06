"""
historical_currency_migration.py - أمر الإدارة لنقل وإعادة ترجمة القيود والأرصدة التاريخية عند تغيير العملة الأساسية
"""

from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from financial.models.currency import Currency, ExchangeRate
from financial.models.journal_entry import JournalEntry, JournalEntryLine


class Command(BaseCommand):
    help = "أمر استثنائي لإعادة ترجمة القيود المحاسبية التاريخية عند تغيير العملة الوظيفية الأساسية للمؤسسة (IAS 21)"

    def add_arguments(self, parser):
        parser.add_argument("--new-currency", type=str, required=True, help="رمز العملة الأساسية الجديدة (مثال: USD, SAR, EGP)")

    def handle(self, *args, **options):
        new_code = options["new_currency"].strip().upper()

        try:
            new_curr = Currency.objects.get(code=new_code)
        except Currency.DoesNotExist:
            raise CommandError(f"العملة {new_code} غير موجودة في دليل العملات.")

        self.stdout.write(self.style.WARNING(f"بدء عملية إعادة الترجمة التاريخية للعملة الأساسية إلى: {new_curr.code}..."))

        with transaction.atomic():
            # Update functional currency status without triggering clean validation lock
            Currency.objects.filter(is_functional=True).update(is_functional=False)
            Currency.objects.filter(pk=new_curr.pk).update(is_functional=True)

            # Re-translate lines where foreign currency is set
            updated_count = 0
            lines = JournalEntryLine.objects.filter(currency__isnull=False)
            for line in lines:
                if line.currency.code != new_curr.code:
                    rate = line.exchange_rate or Decimal("1.000000")
                    if rate > Decimal("0"):
                        line.debit = (line.foreign_debit * rate).quantize(Decimal("0.01")) if line.foreign_debit else Decimal("0.00")
                        line.credit = (line.foreign_credit * rate).quantize(Decimal("0.01")) if line.foreign_credit else Decimal("0.00")
                        line.save(update_fields=["debit", "credit"])
                        updated_count += 1

            self.stdout.write(self.style.SUCCESS(f"تمت إعادة ترجمة وتثبيت {updated_count} خط قيد بنجاح إلى العملة الأساسية الجديدة {new_curr.code}."))
