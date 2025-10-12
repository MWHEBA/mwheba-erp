# Generated manually for pricing enhancements

from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0006_alter_coatingtype_options_and_more'),
        ('product', '0001_initial'),
    ]

    operations = [
        # إضافة الحقول الجديدة لنموذج PricingOrder
        migrations.AddField(
            model_name='pricingorder',
            name='product',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pricing_orders',
                to='product.product',
                verbose_name='المنتج'
            ),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='paper_weight',
            field=models.PositiveIntegerField(default=80, verbose_name='وزن الورق (جرام)'),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='custom_width',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=8,
                null=True,
                verbose_name='العرض المخصص (سم)'
            ),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='custom_height',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=8,
                null=True,
                verbose_name='الطول المخصص (سم)'
            ),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='montage_info',
            field=models.TextField(blank=True, verbose_name='معلومات المونتاج'),
        ),
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
        migrations.AddField(
            model_name='pricingorder',
            name='plates_cost',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=12,
                verbose_name='تكلفة الزنكات'
            ),
        ),
    ]
