# Generated manually for Historical Data Backfill

from django.db import migrations


def backfill_saleitem_warehouses(apps, schema_editor):
    SaleItem = apps.get_model('sale', 'SaleItem')
    # Update all sale items that have no warehouse to match their parent sale warehouse
    for item in SaleItem.objects.filter(warehouse__isnull=True).select_related('sale'):
        if item.sale and item.sale.warehouse_id:
            item.warehouse_id = item.sale.warehouse_id
            item.save(update_fields=['warehouse'])


def reverse_backfill(apps, schema_editor):
    # Reversal does not need to wipe the backfilled values
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('sale', '0005_saleitem_warehouse_alter_sale_warehouse_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_saleitem_warehouses, reverse_backfill),
    ]
