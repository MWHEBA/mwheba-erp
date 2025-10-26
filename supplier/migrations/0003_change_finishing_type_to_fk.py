# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def clear_finishing_services(apps, schema_editor):
    """حذف جميع خدمات التشطيب القديمة قبل تغيير النموذج"""
    FinishingServiceDetails = apps.get_model('supplier', 'FinishingServiceDetails')
    FinishingServiceDetails.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0002_add_packaging_service_details'),
    ]

    operations = [
        # حذف البيانات القديمة أولاً
        migrations.RunPython(clear_finishing_services, reverse_code=migrations.RunPython.noop),
        
        # تغيير الحقل من CharField إلى ForeignKey
        migrations.AlterField(
            model_name='finishingservicedetails',
            name='finishing_type',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='finishing_services',
                to='printing_pricing.finishingtype',
                verbose_name='نوع الخدمة'
            ),
        ),
    ]
