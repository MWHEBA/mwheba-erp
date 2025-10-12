# Generated manually to remove price_per_kg field

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0020_remove_notes_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='paperservicedetails',
            name='price_per_kg',
        ),
    ]
