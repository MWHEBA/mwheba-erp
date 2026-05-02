"""
أمر لإصلاح مسارات الشعارات في قاعدة البيانات
يمسح المسارات القديمة التي تحتوي على suffix عشوائي
"""
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage


class Command(BaseCommand):
    help = 'إصلاح مسارات الشعارات في قاعدة البيانات'

    def handle(self, *args, **options):
        from core.models import SystemSetting

        logo_keys = ['company_logo', 'company_logo_light', 'company_logo_mini']

        for key in logo_keys:
            setting = SystemSetting.objects.filter(key=key).first()
            if not setting:
                self.stdout.write(f'  ⚪ {key}: غير موجود')
                continue

            old_path = setting.value
            if not old_path:
                self.stdout.write(f'  ⚪ {key}: فارغ')
                continue

            # تحديد الامتداد من المسار القديم
            import os
            ext = os.path.splitext(old_path)[1].lower() or '.png'
            correct_path = f"company/{key}{ext}"

            if old_path == correct_path:
                # المسار صح - تحقق من وجود الملف
                if default_storage.exists(correct_path):
                    self.stdout.write(f'  ✅ {key}: صح ({correct_path})')
                else:
                    self.stdout.write(f'  ⚠️  {key}: المسار صح لكن الملف مش موجود - مسح من DB')
                    setting.value = ''
                    setting.save()
            else:
                # المسار قديم - تحقق هل الملف الصحيح موجود
                if default_storage.exists(correct_path):
                    self.stdout.write(f'  🔧 {key}: تحديث المسار → {correct_path}')
                    setting.value = correct_path
                    setting.save()
                else:
                    # الملف الصحيح مش موجود - مسح القيمة القديمة
                    self.stdout.write(f'  🗑️  {key}: مسح المسار القديم ({old_path})')
                    setting.value = ''
                    setting.save()

        self.stdout.write(self.style.SUCCESS('\n✅ تم إصلاح مسارات الشعارات'))
