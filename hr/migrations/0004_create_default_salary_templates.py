# Generated manually for default salary component templates

from django.db import migrations


def create_default_salary_component_templates(apps, schema_editor):
    """إنشاء قوالب مكونات الراتب الافتراضية"""
    SalaryComponentTemplate = apps.get_model('hr', 'SalaryComponentTemplate')
    
    # قوالب المستحقات
    earnings_templates = [
        {
            'name': 'الراتب الأساسي',
            'code': 'BASIC_SALARY',
            'component_type': 'earning',
            'formula': '',
            'default_amount': 0,
            'default_account_code': '52020',
            'order': 1,
            'description': 'الراتب الأساسي للموظف'
        },
        {
            'name': 'بدل السكن',
            'code': 'HOUSING_ALLOWANCE',
            'component_type': 'earning',
            'formula': 'basic * 0.25',
            'default_amount': 0,
            'default_account_code': '52023',
            'order': 2,
            'description': 'بدل السكن (25% من الراتب الأساسي)'
        },
        {
            'name': 'بدل المواصلات',
            'code': 'TRANSPORT_ALLOWANCE',
            'component_type': 'earning',
            'formula': '',
            'default_amount': 300,
            'default_account_code': '52021',
            'order': 3,
            'description': 'بدل المواصلات الثابت'
        },
        {
            'name': 'بدل الطعام',
            'code': 'MEAL_ALLOWANCE',
            'component_type': 'earning',
            'formula': '',
            'default_amount': 200,
            'default_account_code': '52021',
            'order': 4,
            'description': 'بدل الطعام اليومي'
        },
        {
            'name': 'العمل الإضافي',
            'code': 'OVERTIME',
            'component_type': 'earning',
            'formula': '',
            'default_amount': 0,
            'default_account_code': '52020',
            'order': 5,
            'description': 'ساعات العمل الإضافي'
        },
        {
            'name': 'المكافآت',
            'code': 'BONUS',
            'component_type': 'earning',
            'formula': '',
            'default_amount': 0,
            'default_account_code': '52022',
            'order': 6,
            'description': 'المكافآت والحوافز'
        },
    ]
    
    # قوالب الاستقطاعات
    deductions_templates = [
        {
            'name': 'التأمينات الاجتماعية - حصة العامل',
            'code': 'SOCIAL_INSURANCE_EMPLOYEE',
            'component_type': 'deduction',
            'formula': 'basic * 0.11',
            'default_amount': 0,
            'default_account_code': '21031',
            'order': 1,
            'description': 'حصة العامل في التأمينات الاجتماعية (11%)'
        },
        {
            'name': 'ضريبة الدخل',
            'code': 'INCOME_TAX',
            'component_type': 'deduction',
            'formula': '',
            'default_amount': 0,
            'default_account_code': '21032',
            'order': 2,
            'description': 'ضريبة الدخل حسب الشرائح'
        },
        {
            'name': 'اشتراك النقابة',
            'code': 'UNION_SUBSCRIPTION',
            'component_type': 'deduction',
            'formula': '',
            'default_amount': 50,
            'default_account_code': '21033',
            'order': 3,
            'description': 'اشتراك النقابة المهنية'
        },
        {
            'name': 'التأمين الطبي',
            'code': 'MEDICAL_INSURANCE',
            'component_type': 'deduction',
            'formula': '',
            'default_amount': 100,
            'default_account_code': '21034',
            'order': 4,
            'description': 'اشتراك التأمين الطبي'
        },
        {
            'name': 'خصم التأخير',
            'code': 'DELAY_DEDUCTION',
            'component_type': 'deduction',
            'formula': '',
            'default_amount': 0,
            'default_account_code': '52024',
            'order': 5,
            'description': 'خصم ساعات التأخير'
        },
        {
            'name': 'خصم الغياب',
            'code': 'ABSENCE_DEDUCTION',
            'component_type': 'deduction',
            'formula': '',
            'default_amount': 0,
            'default_account_code': '52024',
            'order': 6,
            'description': 'خصم أيام الغياب'
        },
        {
            'name': 'السلف والقروض',
            'code': 'ADVANCE_DEDUCTION',
            'component_type': 'deduction',
            'formula': '',
            'default_amount': 0,
            'default_account_code': '52024',
            'order': 7,
            'description': 'خصم أقساط السلف والقروض'
        },
    ]
    
    # إنشاء قوالب المستحقات
    for template_data in earnings_templates:
        SalaryComponentTemplate.objects.get_or_create(
            code=template_data['code'],
            defaults=template_data
        )
    
    # إنشاء قوالب الاستقطاعات
    for template_data in deductions_templates:
        SalaryComponentTemplate.objects.get_or_create(
            code=template_data['code'],
            defaults=template_data
        )
    
    print(f"✅ تم إنشاء {len(earnings_templates)} قالب مستحقات")
    print(f"✅ تم إنشاء {len(deductions_templates)} قالب استقطاعات")
    print(f"📊 إجمالي القوالب: {len(earnings_templates) + len(deductions_templates)}")


def remove_default_salary_component_templates(apps, schema_editor):
    """حذف قوالب مكونات الراتب الافتراضية"""
    SalaryComponentTemplate = apps.get_model('hr', 'SalaryComponentTemplate')
    
    # أكواد القوالب المراد حذفها
    template_codes = [
        'BASIC_SALARY', 'HOUSING_ALLOWANCE', 'TRANSPORT_ALLOWANCE', 
        'MEAL_ALLOWANCE', 'OVERTIME', 'BONUS',
        'SOCIAL_INSURANCE_EMPLOYEE', 'INCOME_TAX', 'UNION_SUBSCRIPTION',
        'MEDICAL_INSURANCE', 'DELAY_DEDUCTION', 'ABSENCE_DEDUCTION',
        'ADVANCE_DEDUCTION'
    ]
    
    deleted_count = SalaryComponentTemplate.objects.filter(
        code__in=template_codes
    ).delete()[0]
    
    print(f"🗑️ تم حذف {deleted_count} قالب")


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0003_create_payroll_period_payment'),
    ]

    operations = [
        migrations.RunPython(
            create_default_salary_component_templates,
            remove_default_salary_component_templates,
        ),
    ]
