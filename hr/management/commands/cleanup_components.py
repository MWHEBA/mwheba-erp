from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from hr.models import SalaryComponent
from hr.services.component_classification_service import ComponentClassificationService


class Command(BaseCommand):
    help = 'أداة تنظيف وصيانة بنود الراتب'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض النتائج بدون تطبيق التغييرات',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='عدد الأيام للبنود المنتهية (افتراضي: 30)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days_threshold = options['days']
        
        self.stdout.write(
            self.style.SUCCESS(f'🧹 بدء تنظيف بنود الراتب (البنود المنتهية منذ {days_threshold} يوم)')
        )
        
        # تحديد البنود المنتهية
        cutoff_date = timezone.now().date() - timedelta(days=days_threshold)
        expired_components = SalaryComponent.objects.filter(
            effective_to__lt=cutoff_date,
            is_active=True
        )
        
        self.stdout.write(f'📊 تم العثور على {expired_components.count()} بند منتهي الصلاحية')
        
        if expired_components.exists():
            for component in expired_components:
                self.stdout.write(
                    f'  • {component.employee.name} - {component.name} '
                    f'(انتهى في: {component.effective_to})'
                )
            
            if not dry_run:
                # إلغاء تفعيل البنود المنتهية
                updated_count = expired_components.update(is_active=False)
                self.stdout.write(
                    self.style.SUCCESS(f'✅ تم إلغاء تفعيل {updated_count} بند منتهي')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('⚠️ وضع المعاينة - لم يتم تطبيق التغييرات')
                )
        
        # تصنيف البنود غير المصنفة
        unclassified_components = SalaryComponent.objects.filter(source='contract')
        self.stdout.write(f'📋 فحص {unclassified_components.count()} بند للتصنيف التلقائي')
        
        classification_service = ComponentClassificationService()
        
        for component in unclassified_components:
            old_source = component.source
            suggested_source = classification_service.suggest_component_source(component)
            
            if suggested_source != old_source:
                self.stdout.write(
                    f'  • {component.name}: {old_source} → {suggested_source}'
                )
                
                if not dry_run:
                    component.source = suggested_source
                    component.save()
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS('✅ تم إكمال تنظيف بنود الراتب بنجاح')
            )
        else:
            self.stdout.write(
                self.style.WARNING('⚠️ معاينة فقط - استخدم بدون --dry-run للتطبيق الفعلي')
            )
        
        # إحصائيات نهائية
        self.show_statistics()
    
    def show_statistics(self):
        """عرض إحصائيات بنود الراتب"""
        self.stdout.write('\n📊 إحصائيات بنود الراتب:')
        
        total_components = SalaryComponent.objects.count()
        active_components = SalaryComponent.objects.filter(is_active=True).count()
        
        self.stdout.write(f'  • إجمالي البنود: {total_components}')
        self.stdout.write(f'  • البنود النشطة: {active_components}')
        self.stdout.write(f'  • البنود المعطلة: {total_components - active_components}')
        
        # إحصائيات حسب النوع
        for source, name in SalaryComponent.COMPONENT_SOURCE_CHOICES:
            count = SalaryComponent.objects.filter(source=source, is_active=True).count()
            self.stdout.write(f'  • {name}: {count}')
