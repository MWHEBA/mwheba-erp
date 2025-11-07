# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hr', '0015_update_salary_component_to_employee'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contractincrease',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='created_increases',
                to=settings.AUTH_USER_MODEL,
                verbose_name='أنشئ بواسطة'
            ),
        ),
    ]
