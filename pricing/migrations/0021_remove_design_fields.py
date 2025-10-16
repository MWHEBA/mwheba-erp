# Generated manually to remove design-related fields and data

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0020_update_packaging_terminology'),
    ]

    operations = [
        # حذف حقول التصميم من PricingOrder
        migrations.RemoveField(
            model_name='pricingorder',
            name='design_price',
        ),
        migrations.RemoveField(
            model_name='pricingorder',
            name='internal_design_price',
        ),
    ]
