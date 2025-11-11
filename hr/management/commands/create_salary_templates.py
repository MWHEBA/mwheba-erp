"""
أمر لإنشاء قوالب مكونات الراتب الافتراضية المحدثة
"""
from django.core.management.base import BaseCommand
from hr.models import SalaryComponentTemplate
from decimal import Decimal


class Command(BaseCommand):
    help = 'إنشاء قوالب مكونات الراتب الافتراضية المحدثة مع الحسابات المحاسبية'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='حذف جميع القوالب الموجودة قبل الإنشاء',
        )

    def handle(self, *args, **options):
        if options['reset']:
            deleted_count = SalaryComponentTemplate.objects.all().delete()[0]
            self.stdout.write(
                self.style.WARNING(f'🗑️ تم حذف {deleted_count} قالب موجود')
            )
        
        # قوالب الخصومات الافتراضية
        deduction_templates = [
            {
                'code': 'UNION_FEE',
                'name': 'اشتراك النقابة',
                'component_type': 'deduction',
                'default_amount': Decimal('50.00'),
                'default_account_code': '21033',
                'description': 'اشتراك النقابة الشهري للموظفين',
                'order': 1,
                'is_active': True
            },
            {
                'code': 'MEDICAL_INS',
                'name': 'التأمين الطبي',
                'component_type': 'deduction',
                'default_amount': Decimal('100.00'),
                'default_account_code': '21034',
                'description': 'اشتراك التأمين الطبي الشامل',
                'order': 2,
                'is_active': True
            },
            {
                'code': 'SOCIAL_INS',
                'name': 'التأمينات الاجتماعية',
                'component_type': 'deduction',
                'formula': 'basic * 0.14',
                'default_amount': Decimal('0.00'),
                'default_account_code': '21031',
                'description': 'التأمينات الاجتماعية 14% من الراتب الأساسي',
                'order': 3,
                'is_active': True
            },
            {
                'code': 'INCOME_TAX',
                'name': 'ضريبة الدخل',
                'component_type': 'deduction',
                'formula': 'basic * 0.10',
                'default_amount': Decimal('0.00'),
                'default_account_code': '21032',
                'description': 'ضريبة الدخل 10% من الراتب الأساسي',
                'order': 4,
                'is_active': True
            },
            {
                'code': 'ABSENCE_PENALTY',
                'name': 'خصم غياب',
                'component_type': 'deduction',
                'default_amount': Decimal('0.00'),
                'default_account_code': '21020',
                'description': 'خصم أيام الغياب بدون إذن',
                'order': 6,
                'is_active': True
            },
            {
                'code': 'LATE_PENALTY',
                'name': 'خصم تأخير',
                'component_type': 'deduction',
                'default_amount': Decimal('0.00'),
                'default_account_code': '21020',
                'description': 'خصم التأخير عن العمل',
                'order': 7,
                'is_active': True
            }
        ]
        
        # قوالب المستحقات الافتراضية (النظام المبسط)
        earning_templates = [
            {
                'code': 'TRANSPORT_ALLOWANCE',
                'name': 'بدل انتقال',
                'component_type': 'earning',
                'default_amount': Decimal('300.00'),
                'default_account_code': '52021',
                'description': 'بدل المواصلات الشهري للموظفين',
                'order': 1,
                'is_active': True
            },
            {
                'code': 'MEAL_ALLOWANCE',
                'name': 'بدل وجبات',
                'component_type': 'earning',
                'default_amount': Decimal('200.00'),
                'default_account_code': '52021',
                'description': 'بدل الوجبات اليومي للموظفين',
                'order': 2,
                'is_active': True
            },
            {
                'code': 'PHONE_ALLOWANCE',
                'name': 'بدل هاتف',
                'component_type': 'earning',
                'default_amount': Decimal('150.00'),
                'default_account_code': '52021',
                'description': 'بدل الهاتف والاتصالات',
                'order': 3,
                'is_active': True
            },
            {
                'code': 'OVERTIME_PAY',
                'name': 'أجر إضافي',
                'component_type': 'earning',
                'formula': 'basic * 0.05',
                'default_amount': Decimal('0.00'),
                'default_account_code': '52022',
                'description': 'الأجر الإضافي 5% من الراتب الأساسي',
                'order': 5,
                'is_active': True
            },
            {
                'code': 'PERFORMANCE_BONUS',
                'name': 'مكافأة أداء',
                'component_type': 'earning',
                'default_amount': Decimal('500.00'),
                'default_account_code': '52022',
                'description': 'مكافأة الأداء المتميز',
                'order': 6,
                'is_active': True
            },
            {
                'code': 'ANNUAL_BONUS',
                'name': 'مكافأة سنوية',
                'component_type': 'earning',
                'formula': 'basic * 1.0',
                'default_amount': Decimal('0.00'),
                'default_account_code': '52022',
                'description': 'المكافأة السنوية (راتب شهر)',
                'order': 7,
                'is_active': True
            },
            {
                'code': 'HOUSING_ALLOWANCE',
                'name': 'بدل سكن',
                'component_type': 'earning',
                'formula': 'basic * 0.25',
                'default_amount': Decimal('0.00'),
                'default_account_code': '52023',
                'description': 'بدل السكن 25% من الراتب الأساسي',
                'order': 8,
                'is_active': True
            }
        ]
        
        # دمج جميع القوالب
        all_templates = deduction_templates + earning_templates
        
        # إنشاء القوالب (أو تحديثها إذا كانت موجودة)
        created_count = 0
        updated_count = 0
        
        for template_data in all_templates:
            template, created = SalaryComponentTemplate.objects.get_or_create(
                code=template_data['code'],
                defaults=template_data
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✅ تم إنشاء قالب: {template.name}')
                )
            else:
                # تحديث القالب الموجود بالبيانات الجديدة
                for key, value in template_data.items():
                    if key != 'code':  # لا نغير الكود
                        setattr(template, key, value)
                template.save()
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'🔄 تم تحديث قالب: {template.name}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎉 تم إنشاء {created_count} قالب جديد وتحديث {updated_count} قالب موجود'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'📋 إجمالي القوالب: {len(all_templates)} ({len(earning_templates)} مستحق + {len(deduction_templates)} خصم)'
            )
        )
