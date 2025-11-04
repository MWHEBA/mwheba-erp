# Generated manually for leave accrual system

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0003_contract_contractamendment_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='leavebalance',
            name='accrued_days',
            field=models.IntegerField(default=0, verbose_name='الأيام المستحقة'),
        ),
        migrations.AddField(
            model_name='leavebalance',
            name='accrual_start_date',
            field=models.DateField(blank=True, null=True, verbose_name='تاريخ بداية الاستحقاق'),
        ),
        migrations.AddField(
            model_name='leavebalance',
            name='last_accrual_date',
            field=models.DateField(blank=True, null=True, verbose_name='آخر تاريخ استحقاق'),
        ),
    ]
