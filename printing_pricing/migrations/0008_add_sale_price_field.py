# Generated manually to add sale_price field

from django.core.validators import MinValueValidator
from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('printing_pricing', '0007_add_client_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='printingorder',
            name='sale_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                validators=[MinValueValidator(Decimal('0.00'))],
                verbose_name='سعر البيع'
            ),
        ),
    ]
