"""
أمر Django لإصلاح البيانات المكررة في بنود الراتب
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from collections import defaultdict
from hr.models import SalaryComponent


class Command(BaseCommand):
    help = 'إصلاح البيانات المكررة في بنود الراتب'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض التغييرات بدون تطبيقها',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('تشغيل تجريبي - لن يتم حفظ التغييرات')
            )
        
        # العثور على البيانات المكررة
        duplicates = defaultdict(list)
        
        for component in SalaryComponent.objects.all():
            key = (component.employee_id, component.code)
            duplicates[key].append(component)
        
        # إحصائيات
        total_duplicates = 0
        fixed_count = 0
        
        for key, components in duplicates.items():
            if len(components) > 1:
                total_duplicates += len(components) - 1
                employee_id, code = key
                
                self.stdout.write(
                    f'موظف {employee_id} - كود {code}: {len(components)} بند مكرر'
                )
                
                if not dry_run:
                    with transaction.atomic():
                        # الاحتفاظ بالأحدث وحذف الباقي
                        latest = max(components, key=lambda x: x.id)
                        
                        for comp in components:
                            if comp.id != latest.id:
                                self.stdout.write(
                                    f'  - حذف البند {comp.id}: {comp.name}'
                                )
                                comp.delete()
                                fixed_count += 1
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'تم العثور على {total_duplicates} بند مكرر'
                )
            )
            self.stdout.write(
                'استخدم الأمر بدون --dry-run لتطبيق التغييرات'
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'تم إصلاح {fixed_count} بند مكرر'
                )
            )
