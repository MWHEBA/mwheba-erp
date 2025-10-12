# Generated manually to add client fields to PricingOrder

from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0004_add_new_pricing_models'),
        ('supplier', '0004_supplier_financial_account'),
    ]

    operations = [
        # إضافة الحقول الجديدة للعملاء في PricingOrder
        migrations.AddField(
            model_name='pricingorder',
            name='client_contact_person',
            field=models.CharField(blank=True, max_length=100, verbose_name='الشخص المسؤول'),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='client_phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='هاتف العميل'),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='client_email',
            field=models.EmailField(blank=True, verbose_name='بريد العميل'),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='client_type',
            field=models.CharField(
                choices=[
                    ('regular', 'عميل عادي'),
                    ('vip', 'عميل مميز'),
                    ('corporate', 'شركة'),
                    ('government', 'جهة حكومية')
                ],
                default='regular',
                max_length=20,
                verbose_name='نوع العميل'
            ),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='client_notes',
            field=models.TextField(blank=True, verbose_name='ملاحظات العميل'),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='supplier_notes',
            field=models.TextField(blank=True, verbose_name='ملاحظات الموردين'),
        ),
        migrations.AddField(
            model_name='pricingorder',
            name='primary_supplier',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='primary_orders',
                to='supplier.supplier',
                verbose_name='المورد الأساسي'
            ),
        ),
        
        # إضافة الحقول المفقودة في PricingQuotation
        migrations.AddField(
            model_name='pricingquotation',
            name='sent_date',
            field=models.DateField(blank=True, null=True, verbose_name='تاريخ الإرسال'),
        ),
        migrations.AddField(
            model_name='pricingquotation',
            name='accepted_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاريخ القبول'),
        ),
        migrations.AddField(
            model_name='pricingquotation',
            name='rejected_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الرفض'),
        ),
        migrations.AddField(
            model_name='pricingquotation',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='مبلغ الخصم'),
        ),
        migrations.AddField(
            model_name='pricingquotation',
            name='final_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='السعر النهائي'),
        ),
    ]
