"""
أمر لإنشاء قوالب مكونات الراتب الافتراضية
"""
from django.core.management.base import BaseCommand
from hr.models import SalaryComponentTemplate


class Command(BaseCommand):
    help = 'إنشاء قوالب مكونات الراتب الافتراضية'

    def handle(self, *args, **options):
        # حذف القوالب القديمة
        SalaryComponentTemplate.objects.all().delete()
        
        # قوالب المستحقات
        earnings = [
            {
                'name': 'بدل السكن',
                'component_type': 'earning',
                'formula': 'basic * 0.25',
                'default_amount': 0,
                'description': '25% من الراتب الأساسي',
                'order': 1
            },
            {
                'name': 'بدل المواصلات',
                'component_type': 'earning',
                'formula': 'basic * 0.10',
                'default_amount': 0,
                'description': '10% من الراتب الأساسي',
                'order': 2
            },
            {
                'name': 'بدل الطعام',
                'component_type': 'earning',
                'formula': '',
                'default_amount': 500,
                'description': 'مبلغ ثابت شهرياً',
                'order': 3
            },
            {
                'name': 'بدل الهاتف',
                'component_type': 'earning',
                'formula': '',
                'default_amount': 200,
                'description': 'مبلغ ثابت شهرياً',
                'order': 4
            },
            {
                'name': 'علاوة',
                'component_type': 'earning',
                'formula': 'basic * 0.05',
                'default_amount': 0,
                'description': '5% من الراتب الأساسي',
                'order': 5
            },
            {
                'name': 'حافز',
                'component_type': 'earning',
                'formula': '',
                'default_amount': 1000,
                'description': 'حافز شهري',
                'order': 6
            },
        ]
        
        # قوالب الاستقطاعات
        deductions = [
            {
                'name': 'التأمينات الاجتماعية',
                'component_type': 'deduction',
                'formula': 'basic * 0.11',
                'default_amount': 0,
                'description': '11% من الراتب الأساسي',
                'order': 1
            },
            {
                'name': 'ضريبة الدخل',
                'component_type': 'deduction',
                'formula': 'basic * 0.05',
                'default_amount': 0,
                'description': '5% من الراتب الأساسي',
                'order': 2
            },
            {
                'name': 'سلفة',
                'component_type': 'deduction',
                'formula': '',
                'default_amount': 500,
                'description': 'خصم سلفة شهرية',
                'order': 3
            },
            {
                'name': 'غياب',
                'component_type': 'deduction',
                'formula': '',
                'default_amount': 0,
                'description': 'خصم أيام الغياب',
                'order': 4
            },
            {
                'name': 'تأخير',
                'component_type': 'deduction',
                'formula': '',
                'default_amount': 0,
                'description': 'خصم التأخير',
                'order': 5
            },
        ]
        
        # إنشاء المستحقات
        for earning in earnings:
            SalaryComponentTemplate.objects.create(**earning)
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم إنشاء قالب المستحق: {earning["name"]}')
            )
        
        # إنشاء الاستقطاعات
        for deduction in deductions:
            SalaryComponentTemplate.objects.create(**deduction)
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم إنشاء قالب الاستقطاع: {deduction["name"]}')
            )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎉 تم إنشاء {len(earnings)} قالب مستحق و {len(deductions)} قالب استقطاع بنجاح!'
            )
        )
