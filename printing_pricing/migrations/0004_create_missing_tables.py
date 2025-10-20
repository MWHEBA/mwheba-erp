# Generated manually to create missing tables

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('printing_pricing', '0003_record_missing_tables'),
    ]

    operations = [
        # Mark tables as created (they were created manually)
        migrations.RunSQL(
            "-- Tables created manually: offsetmachinetype, digitalmachinetype, offsetsheetsize, digitalsheetsize, systemsetting",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
