"""
أمر إداري لإنشاء الصلاحيات المخصصة للنظام المالي
"""
from django.core.management.base import BaseCommand
from financial.permissions import create_custom_permissions


class Command(BaseCommand):
    help = 'إنشاء الصلاحيات المخصصة للنظام المالي'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔄 جاري إنشاء الصلاحيات المخصصة...'))
        
        try:
            create_custom_permissions()
            self.stdout.write(self.style.SUCCESS('✅ تم إنشاء الصلاحيات بنجاح'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ خطأ: {str(e)}'))
