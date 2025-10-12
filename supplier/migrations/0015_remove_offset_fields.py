# Generated migration for removing fields from OffsetPrintingDetails

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("supplier", "0009_remove_duplicate_category"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="offsetprintingdetails",
            name="machine_model",
        ),
        migrations.RemoveField(
            model_name="offsetprintingdetails",
            name="plate_cost",
        ),
        migrations.RemoveField(
            model_name="offsetprintingdetails",
            name="min_impressions",
        ),
        migrations.RemoveField(
            model_name="specializedservice",
            name="base_price",
        ),
        migrations.RemoveField(
            model_name="specializedservice",
            name="min_quantity",
        ),
    ]
