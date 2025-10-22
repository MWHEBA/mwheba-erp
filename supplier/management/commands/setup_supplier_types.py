"""
أمر إنشاء أنواع الموردين الافتراضية
"""
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from supplier.models import SupplierTypeSettings, SupplierType


class Command(BaseCommand):
    help = 'إنشاء أنواع الموردين الافتراضية ومزامنتها'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='إعادة تعيين جميع الأنواع (حذف الموجود وإنشاء جديد)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 بدء إعداد أنواع الموردين...')
        )

        if options['reset']:
            self.stdout.write('⚠️  إعادة تعيين الأنواع الموجودة...')
            SupplierTypeSettings.objects.all().delete()
            SupplierType.objects.all().delete()

        # إنشاء الأنواع الافتراضية
        created_count = SupplierTypeSettings.create_default_types()
        
        if created_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم إنشاء {created_count} نوع مورد جديد')
            )
        else:
            self.stdout.write(
                self.style.WARNING('ℹ️  جميع الأنواع موجودة بالفعل')
            )

        # مزامنة مع النظام القديم
        self.stdout.write('🔄 مزامنة مع النظام القديم...')
        SupplierType.sync_with_settings()

        # إحصائيات
        total_settings = SupplierTypeSettings.objects.count()
        active_settings = SupplierTypeSettings.objects.filter(is_active=True).count()
        total_types = SupplierType.objects.count()

        self.stdout.write('\n📊 الإحصائيات:')
        self.stdout.write(f'   • إعدادات الأنواع: {total_settings}')
        self.stdout.write(f'   • الأنواع النشطة: {active_settings}')
        self.stdout.write(f'   • أنواع النظام القديم: {total_types}')

        self.stdout.write(
            self.style.SUCCESS('\n🎉 تم إعداد أنواع الموردين بنجاح!')
        )
        
        self.stdout.write('\n🔗 يمكنك الآن الوصول للإعدادات عبر:')
        self.stdout.write('   • الرابط: /supplier/settings/types/')
        self.stdout.write('   • القائمة الجانبية: الموردين > إعدادات أنواع الموردين')
