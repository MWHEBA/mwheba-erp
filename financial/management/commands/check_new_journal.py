"""
فحص القيد الجديد
"""
from django.core.management.base import BaseCommand
from financial.models import JournalEntry


class Command(BaseCommand):
    help = 'فحص القيد الجديد'

    def handle(self, *args, **options):
        try:
            je = JournalEntry.objects.get(number='SALE-SALE0003-20251026160658')
            self.stdout.write(self.style.SUCCESS(f'\n✅ القيد: {je.number}'))
            self.stdout.write(f'عدد البنود: {je.lines.count()}\n')
            self.stdout.write('البنود:')
            for line in je.lines.all():
                self.stdout.write(
                    f'  {line.account.code} - {line.account.name}: '
                    f'مدين={line.debit}, دائن={line.credit}'
                )
        except JournalEntry.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ القيد غير موجود'))
