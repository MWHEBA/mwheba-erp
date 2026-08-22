# Generated for MWHEBA ERP Subledger Alignment

from decimal import Decimal
from django.db import migrations, models


def fix_opening_balance_egp_subledger(apps, schema_editor):
    CustomerTransaction = apps.get_model('client', 'CustomerTransaction')
    SupplierTransaction = apps.get_model('supplier', 'SupplierTransaction')

    # 1. تصحيح حركات الأستاذ المساعد للعملاء بالجنيه المصري
    cust_txns = CustomerTransaction.objects.filter(
        reference_type="OPENING_BALANCE",
        open_amount_foreign=Decimal('0.00'),
        open_amount_functional__gt=Decimal('0.00')
    )
    for ctx in cust_txns:
        ctx.open_amount_foreign = ctx.open_amount_functional
        if ctx.foreign_amount == Decimal('0.00'):
            ctx.foreign_amount = ctx.functional_amount
        ctx.save(update_fields=['open_amount_foreign', 'foreign_amount'])

    # 2. تصحيح حركات الأستاذ المساعد للموردين بالجنيه المصري
    supp_txns = SupplierTransaction.objects.filter(
        transaction_number__startswith="OPN-",
        open_amount_foreign=Decimal('0.00'),
        open_amount_functional__gt=Decimal('0.00')
    )
    for stx in supp_txns:
        stx.open_amount_foreign = stx.open_amount_functional
        if stx.foreign_amount == Decimal('0.00'):
            stx.foreign_amount = stx.functional_amount
        stx.save(update_fields=['open_amount_foreign', 'foreign_amount'])


def reverse_fix(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("financial", "0007_alter_financialcategory_code_and_more"),
        ("client", "0001_initial"),
        ("supplier", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(fix_opening_balance_egp_subledger, reverse_fix),
    ]
