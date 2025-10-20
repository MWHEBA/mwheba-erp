# Generated manually to add client field

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('client', '0003_customer_tax_number'),
        ('printing_pricing', '0006_coatingtype_digitalmachinetype_finishingtype_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='printingorder',
            name='client',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='client_printing_orders',
                to='client.customer',
                verbose_name='العميل (client)'
            ),
        ),
    ]
