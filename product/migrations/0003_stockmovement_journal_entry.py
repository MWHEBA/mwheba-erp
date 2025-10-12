# Generated manually for adding journal_entry field to StockMovement

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0002_initial'),
        ('product', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockmovement',
            name='journal_entry',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_movements', to='financial.journalentry', verbose_name='القيد المحاسبي'),
        ),
    ]
