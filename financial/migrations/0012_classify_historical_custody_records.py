# Generated manually for Phase 4 Custody Hardening

from decimal import Decimal
from django.db import migrations


def classify_historical_custody_records(apps, schema_editor):
    EmployeeCustodyAdvance = apps.get_model('financial', 'EmployeeCustodyAdvance')
    PettyCashSettlement = apps.get_model('financial', 'PettyCashSettlement')
    Currency = apps.get_model('financial', 'Currency')

    functional_currency = Currency.objects.filter(is_functional=True).first()
    if not functional_currency:
        functional_currency = Currency.objects.first()

    # 1. تصنيف السلف التاريخية واحتساب أصل التمويل الخاضع للتسوية
    for adv in EmployeeCustodyAdvance.objects.all():
        updated = False
        if adv.custody_account_id and adv.custody_type != 'permanent':
            adv.custody_type = 'permanent'
            updated = True
        elif not adv.custody_account_id and adv.custody_type != 'temporary':
            adv.custody_type = 'temporary'
            updated = True

        if adv.settlement_principal_amount is None:
            per_diem = adv.per_diem_amount or Decimal('0.00')
            adv.settlement_principal_amount = max(Decimal('0.00'), adv.amount - per_diem)
            updated = True

        if updated:
            adv.save(update_fields=['custody_type', 'settlement_principal_amount'])

    # 2. ملء عملة التسويات القديمة حيثما كانت null
    for stl in PettyCashSettlement.objects.filter(currency__isnull=True):
        target_currency = None
        if stl.custody_advance_id and stl.custody_advance.currency_id:
            target_currency = stl.custody_advance.currency
        elif stl.custody_account_id and stl.custody_account.currency_id:
            target_currency = stl.custody_account.currency
        else:
            target_currency = functional_currency

        if target_currency:
            stl.currency = target_currency
            stl.save(update_fields=['currency'])


def reverse_classification(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0011_alter_employeecustodyadvance_options_and_more'),
    ]

    operations = [
        migrations.RunPython(
            classify_historical_custody_records,
            reverse_code=reverse_classification,
        ),
    ]
