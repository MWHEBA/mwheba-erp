# Generated manually to remove design fields from LaserServiceDetails

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0034_remove_design_services'),
    ]

    operations = [
        # حذف حقول التصميم من LaserServiceDetails
        migrations.RemoveField(
            model_name='laserservicedetails',
            name='includes_design',
        ),
        migrations.RemoveField(
            model_name='laserservicedetails',
            name='design_cost_per_hour',
        ),
    ]
