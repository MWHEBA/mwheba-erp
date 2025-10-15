# Generated migration to remove choices constraints from OffsetPrintingDetails

from django.db import migrations, models
import django.utils.translation


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0027_unify_offset_printing_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='offsetprintingdetails',
            name='machine_type',
            field=models.CharField(max_length=30, verbose_name=django.utils.translation.gettext_lazy('نوع الماكينة')),
        ),
        migrations.AlterField(
            model_name='offsetprintingdetails',
            name='sheet_size',
            field=models.CharField(max_length=20, verbose_name=django.utils.translation.gettext_lazy('مقاس الفرخ')),
        ),
    ]
