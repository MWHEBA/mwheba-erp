# Generated manually to add biometric_user_id field
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0011_add_biometric_user_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='biometric_user_id',
            field=models.CharField(
                blank=True,
                help_text='رقم تعريف الموظف في نظام البصمة',
                max_length=50,
                null=True,
                verbose_name='رقم الموظف في جهاز البصمة'
            ),
        ),
    ]
