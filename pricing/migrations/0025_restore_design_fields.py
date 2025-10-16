# Generated manually to restore design fields

from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0024_merge_20251016_0338'),
    ]

    operations = [
        # إعادة حقول التصميم إلى PricingOrder
        migrations.AddField(
            model_name='pricingorder',
            name='design_price',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=10,
                verbose_name='سعر التصميم'
            ),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='internal_design_price',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=10,
                verbose_name='سعر التصميم الداخلي'
            ),
        ),
    ]
