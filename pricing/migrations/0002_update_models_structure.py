# Generated manually for pricing models update

from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0001_initial'),
        ('supplier', '0001_initial'),
        ('users', '0001_initial'),
    ]

    operations = [
        # إنشاء PaperServiceDetails فقط (الجداول المفقودة)
        migrations.CreateModel(
            name='PaperServiceDetails',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weight', models.PositiveIntegerField(verbose_name='الوزن (جرام)')),
                ('sheet_type', models.CharField(
                    choices=[('sheet', 'ورقة'), ('roll', 'رول')],
                    default='sheet',
                    max_length=10,
                    verbose_name='نوع الورقة'
                )),
                ('origin', models.CharField(
                    choices=[('local', 'محلي'), ('imported', 'مستورد')],
                    default='local',
                    max_length=10,
                    verbose_name='المنشأ'
                )),
                ('price_per_sheet', models.DecimalField(
                    decimal_places=4,
                    default=Decimal('0.0000'),
                    max_digits=10,
                    verbose_name='سعر الورقة'
                )),
                ('price_per_kg', models.DecimalField(
                    decimal_places=2,
                    default=Decimal('0.00'),
                    max_digits=10,
                    verbose_name='سعر الكيلو'
                )),
                ('minimum_quantity', models.PositiveIntegerField(default=1, verbose_name='الحد الأدنى للكمية')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('paper_size', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='services',
                    to='pricing.papersize',
                    verbose_name='مقاس الورق'
                )),
                ('paper_type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='services',
                    to='pricing.papertype',
                    verbose_name='نوع الورق'
                )),
                ('supplier', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='paper_services',
                    to='supplier.supplier',
                    verbose_name='المورد'
                )),
            ],
            options={
                'verbose_name': 'تفاصيل خدمة الورق',
                'verbose_name_plural': 'تفاصيل خدمات الورق',
                'ordering': ['supplier', 'paper_type', 'weight'],
            },
        ),
        
        # إنشاء DigitalPrintingDetails
        migrations.CreateModel(
            name='DigitalPrintingDetails',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('color_type', models.CharField(
                    choices=[('bw', 'أبيض وأسود'), ('color', 'ملون')],
                    default='color',
                    max_length=20,
                    verbose_name='نوع الألوان'
                )),
                ('price_per_copy', models.DecimalField(
                    decimal_places=4,
                    default=Decimal('0.0000'),
                    max_digits=10,
                    verbose_name='سعر النسخة'
                )),
                ('minimum_quantity', models.PositiveIntegerField(default=1, verbose_name='الحد الأدنى للكمية')),
                ('maximum_quantity', models.PositiveIntegerField(
                    blank=True,
                    null=True,
                    verbose_name='الحد الأقصى للكمية'
                )),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('paper_size', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='digital_services',
                    to='pricing.papersize',
                    verbose_name='مقاس الورق'
                )),
                ('supplier', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='digital_services',
                    to='supplier.supplier',
                    verbose_name='المورد'
                )),
            ],
            options={
                'verbose_name': 'تفاصيل الطباعة الرقمية',
                'verbose_name_plural': 'تفاصيل الطباعة الرقمية',
                'ordering': ['supplier', 'paper_size', 'color_type'],
            },
        ),
        
        # إنشاء VATSetting
        migrations.CreateModel(
            name='VATSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=False, verbose_name='مفعل')),
                ('percentage', models.DecimalField(
                    decimal_places=2,
                    default=Decimal('15.00'),
                    max_digits=5,
                    verbose_name='النسبة المئوية'
                )),
                ('description', models.TextField(blank=True, verbose_name='الوصف')),
                ('effective_date', models.DateField(auto_now_add=True, verbose_name='تاريخ السريان')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='vat_settings',
                    to='users.user',
                    verbose_name='تم الإنشاء بواسطة'
                )),
            ],
            options={
                'verbose_name': 'إعداد ضريبة القيمة المضافة',
                'verbose_name_plural': 'إعدادات ضريبة القيمة المضافة',
                'ordering': ['-created_at'],
            },
        ),
        
        # إضافة unique constraints
        migrations.AddConstraint(
            model_name='paperservicedetails',
            constraint=models.UniqueConstraint(
                fields=['supplier', 'paper_type', 'paper_size', 'weight', 'origin'],
                name='unique_paper_service'
            ),
        ),
        migrations.AddConstraint(
            model_name='digitalprintingdetails',
            constraint=models.UniqueConstraint(
                fields=['supplier', 'paper_size', 'color_type'],
                name='unique_digital_service'
            ),
        ),
    ]
