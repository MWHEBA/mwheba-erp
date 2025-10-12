# Generated manually to remove notes fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("supplier", "0019_add_floor_price_to_service_price_tier"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="supplier",
            name="notes",
        ),
        migrations.RemoveField(
            model_name="specializedservice",
            name="notes",
        ),
    ]
