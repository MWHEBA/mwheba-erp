"""
أمر Django لحذف صلاحيات Django الافتراضية والإبقاء على المخصصة فقط
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = "حذف صلاحيات Django الافتراضية والإبقاء على المخصصة بالعربي فقط"

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='تأكيد الحذف',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("=" * 70))
        self.stdout.write(self.style.WARNING("⚠️  تحذير: هذا الأمر سيحذف صلاحيات Django الافتراضية"))
        self.stdout.write(self.style.WARNING("=" * 70))
        
        # الحصول على ContentType للمستخدم (الصلاحيات المخصصة)
        from users.models import User
        user_content_type = ContentType.objects.get_for_model(User)
        
        # عد الصلاحيات
        custom_perms = Permission.objects.filter(content_type=user_content_type)
        django_perms = Permission.objects.exclude(content_type=user_content_type)
        
        self.stdout.write(f"\n📊 الإحصائيات الحالية:")
        self.stdout.write(f"   ✅ الصلاحيات المخصصة بالعربي: {custom_perms.count()} صلاحية")
        self.stdout.write(f"   ❌ صلاحيات Django الافتراضية: {django_perms.count()} صلاحية")
        
        if not options['confirm']:
            self.stdout.write("\n" + self.style.WARNING("💡 لتنفيذ الحذف، أضف --confirm"))
            self.stdout.write(self.style.WARNING("   مثال: python manage.py cleanup_django_permissions --confirm"))
            return
        
        self.stdout.write("\n" + self.style.SUCCESS("🗑️  بدء حذف صلاحيات Django الافتراضية..."))
        
        # حذف الصلاحيات الافتراضية
        deleted_count = 0
        for perm in django_perms:
            perm_name = f"{perm.content_type.app_label}.{perm.codename}"
            perm.delete()
            deleted_count += 1
            if deleted_count % 50 == 0:
                self.stdout.write(f"   تم حذف {deleted_count} صلاحية...")
        
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS(f"✅ تم حذف {deleted_count} صلاحية Django افتراضية"))
        self.stdout.write(self.style.SUCCESS(f"✅ تم الإبقاء على {custom_perms.count()} صلاحية مخصصة بالعربي"))
        
        # النتيجة النهائية
        total_remaining = Permission.objects.count()
        self.stdout.write(f"\n📊 إجمالي الصلاحيات المتبقية: {total_remaining} صلاحية")
        self.stdout.write("=" * 70)
        
        self.stdout.write("\n" + self.style.SUCCESS("🎉 تم التنظيف بنجاح!"))
        self.stdout.write(self.style.SUCCESS("💡 الآن لديك صلاحيات مخصصة بالعربي فقط"))
        self.stdout.write("=" * 70)
