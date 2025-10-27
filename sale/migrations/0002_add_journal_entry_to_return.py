# Generated migration for adding journal_entry field to SaleReturn

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0001_initial_clean'),
        ('sale', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='salereturn',
            name='journal_entry',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sale_returns',
                to='financial.journalentry',
                verbose_name='القيد المحاسبي'
            ),
        ),
    ]
