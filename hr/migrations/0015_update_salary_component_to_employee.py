# Generated manually

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def populate_employee_field(apps, schema_editor):
    """ملء حقل employee من العقد الموجود"""
    SalaryComponent = apps.get_model('hr', 'SalaryComponent')
    
    for component in SalaryComponent.objects.all():
        if component.contract:
            component.employee_id = component.contract.employee_id
            component.save(update_fields=['employee_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0014_add_automatic_annual_increase'),
    ]

    operations = [
        # إضافة حقل employee (nullable مؤقتاً)
        migrations.AddField(
            model_name='salarycomponent',
            name='employee',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='salary_components',
                to='hr.employee',
                verbose_name='الموظف'
            ),
        ),
        
        # ملء البيانات
        migrations.RunPython(populate_employee_field, migrations.RunPython.noop),
        
        # جعل employee إلزامي
        migrations.AlterField(
            model_name='salarycomponent',
            name='employee',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='salary_components',
                to='hr.employee',
                verbose_name='الموظف'
            ),
        ),
        
        # تعديل contract ليكون اختياري
        migrations.AlterField(
            model_name='salarycomponent',
            name='contract',
            field=models.ForeignKey(
                blank=True,
                help_text='العقد الذي تم إضافة البند فيه (اختياري)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='contract_components',
                to='hr.contract',
                verbose_name='العقد'
            ),
        ),
        
        # إضافة الحقول الجديدة
        migrations.AddField(
            model_name='salarycomponent',
            name='is_taxable',
            field=models.BooleanField(default=True, verbose_name='خاضع للضريبة'),
        ),
        migrations.AddField(
            model_name='salarycomponent',
            name='is_fixed',
            field=models.BooleanField(default=True, verbose_name='ثابت شهرياً'),
        ),
        migrations.AddField(
            model_name='salarycomponent',
            name='notes',
            field=models.TextField(blank=True, verbose_name='ملاحظات'),
        ),
        migrations.AddField(
            model_name='salarycomponent',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=timezone.now, verbose_name='تاريخ الإضافة'),
            preserve_default=False,
        ),
        
        # تحديث الـ indexes
        migrations.RemoveIndex(
            model_name='salarycomponent',
            name='hr_salaryco_contrac_748bfb_idx',
        ),
        migrations.AddIndex(
            model_name='salarycomponent',
            index=models.Index(fields=['employee', 'component_type'], name='hr_salaryco_employe_736ac5_idx'),
        ),
        migrations.AddIndex(
            model_name='salarycomponent',
            index=models.Index(fields=['contract'], name='hr_salaryco_contrac_8d98d2_idx'),
        ),
    ]
