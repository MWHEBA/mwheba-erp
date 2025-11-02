"""
أمر Django لتحديث الأدوار باستخدام الصلاحيات المخصصة المبسطة
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from users.models import Role


class Command(BaseCommand):
    help = "تحديث الأدوار باستخدام الصلاحيات المخصصة"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("بدء تحديث الأدوار بالصلاحيات المخصصة..."))

        # تعريف الأدوار بالصلاحيات المخصصة (بالعربي)
        roles_config = {
            'admin': {
                'display_name': 'مدير النظام',
                'description': 'صلاحيات كاملة لإدارة النظام',
                'is_system_role': True,
                'permissions': 'all'  # جميع الصلاحيات المخصصة
            },
            'accountant': {
                'display_name': 'محاسب',
                'description': 'إدارة المعاملات المالية والقيود المحاسبية',
                'is_system_role': True,
                'permissions': [
                    'ادارة_المحاسبة',
                    'ادارة_المصروفات',
                    'ادارة_الايرادات',
                    'ادارة_الخزن_والحسابات',
                    'عرض_التقارير_المالية',
                    'عرض_المبيعات',
                    'عرض_المشتريات',
                    'عرض_العملاء',
                    'عرض_الموردين',
                ]
            },
            'inventory_manager': {
                'display_name': 'أمين مخزن',
                'description': 'إدارة المخزون وحركة المنتجات',
                'is_system_role': True,
                'permissions': [
                    'ادارة_المنتجات',
                    'ادارة_المخزون',
                    'ادارة_المخازن',
                    'ادارة_المشتريات',
                    'عرض_الموردين',
                    'عرض_تقارير_المخزون',
                ]
            },
            'sales_rep': {
                'display_name': 'مندوب مبيعات',
                'description': 'إدارة المبيعات والعملاء',
                'is_system_role': True,
                'permissions': [
                    'ادارة_المبيعات',
                    'ادارة_مرتجعات_المبيعات',
                    'ادارة_العملاء',
                    'ادارة_مدفوعات_العملاء',
                    'عرض_المنتجات',
                    'عرض_تقارير_المبيعات',
                    'عرض_تقارير_العملاء',
                ]
            },
            'financial_manager': {
                'display_name': 'مدير مالي',
                'description': 'إدارة شاملة للشؤون المالية والمحاسبية',
                'is_system_role': True,
                'permissions': [
                    'ادارة_المحاسبة',
                    'ادارة_المصروفات',
                    'ادارة_الايرادات',
                    'ادارة_الخزن_والحسابات',
                    'ادارة_الفترات_المحاسبية',
                    'عرض_التقارير_المالية',
                    'عرض_تقارير_المبيعات',
                    'عرض_تقارير_المشتريات',
                    'عرض_تقارير_العملاء',
                    'عرض_تقارير_الموردين',
                    'ادارة_مدفوعات_العملاء',
                    'ادارة_مدفوعات_الموردين',
                    'اعتماد_المعاملات',
                ]
            },
            'viewer': {
                'display_name': 'مستخدم عرض فقط',
                'description': 'عرض البيانات فقط بدون تعديل',
                'is_system_role': False,
                'permissions': [
                    'عرض_المبيعات',
                    'عرض_المشتريات',
                    'عرض_العملاء',
                    'عرض_الموردين',
                    'عرض_المنتجات',
                    'عرض_المحاسبة',
                ]
            },
            'printing_manager': {
                'display_name': 'مسؤول طباعة',
                'description': 'إدارة طلبات الطباعة والتسعير وإعدادات الطباعة',
                'is_system_role': True,
                'permissions': [
                    'ادارة_التسعير',
                    'ادارة_الخدمات_المتخصصة',
                    'ادارة_الموردين',
                    'عرض_الموردين',
                    'عرض_المنتجات',
                    'عرض_العملاء',
                ]
            },
            'general_coordinator': {
                'display_name': 'منسق عام',
                'description': 'التنسيق بين الأقسام المختلفة ومتابعة سير العمل',
                'is_system_role': True,
                'permissions': [
                    'عرض_المبيعات',
                    'عرض_المشتريات',
                    'عرض_العملاء',
                    'عرض_الموردين',
                    'عرض_المنتجات',
                    'عرض_المحاسبة',
                    'عرض_تقارير_المبيعات',
                    'عرض_تقارير_المشتريات',
                    'عرض_تقارير_المخزون',
                    'ادارة_المبيعات',
                    'ادارة_المشتريات',
                    'ادارة_العملاء',
                    'ادارة_الموردين',
                ]
            },
        }

        roles_created = 0
        roles_updated = 0

        for role_name, role_config in roles_config.items():
            # إنشاء أو تحديث الدور
            role, created = Role.objects.get_or_create(
                name=role_name,
                defaults={
                    'display_name': role_config['display_name'],
                    'description': role_config['description'],
                    'is_system_role': role_config['is_system_role'],
                    'is_active': True,
                }
            )

            if created:
                roles_created += 1
                self.stdout.write(f"✅ تم إنشاء الدور: {role.display_name}")
            else:
                # تحديث المعلومات
                role.display_name = role_config['display_name']
                role.description = role_config['description']
                role.is_system_role = role_config['is_system_role']
                role.save()
                roles_updated += 1
                self.stdout.write(f"⚠️  تم تحديث الدور: {role.display_name}")

            # إضافة الصلاحيات المخصصة
            if role_config['permissions'] == 'all':
                # إضافة جميع الصلاحيات المخصصة فقط
                from users.models import User
                from django.contrib.contenttypes.models import ContentType
                content_type = ContentType.objects.get_for_model(User)
                custom_permissions = Permission.objects.filter(content_type=content_type)
                role.permissions.set(custom_permissions)
                self.stdout.write(f"   → تم إضافة جميع الصلاحيات المخصصة ({custom_permissions.count()} صلاحية)")
            else:
                # إضافة صلاحيات محددة
                permissions = []
                for perm_codename in role_config['permissions']:
                    try:
                        perm = Permission.objects.get(codename=perm_codename)
                        permissions.append(perm)
                    except Permission.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f"   ⚠️  الصلاحية غير موجودة: {perm_codename}")
                        )

                role.permissions.set(permissions)
                self.stdout.write(f"   → تم إضافة {len(permissions)} صلاحية مخصصة")

        # النتيجة النهائية
        self.stdout.write("\n" + "=" * 70)
        if roles_created > 0:
            self.stdout.write(
                self.style.SUCCESS(f"🎉 تم إنشاء {roles_created} دور جديد بنجاح!")
            )
        if roles_updated > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠️  تم تحديث {roles_updated} دور موجود")
            )

        # عرض ملخص الأدوار
        self.stdout.write("\n" + self.style.SUCCESS("📊 ملخص الأدوار المحدثة:"))
        for role in Role.objects.all().order_by('-is_system_role', 'display_name'):
            status = "🔒 نظام" if role.is_system_role else "✏️  مخصص"
            users_count = role.users.count()
            perms_count = role.permissions.count()
            self.stdout.write(
                f"  {status} | {role.display_name:25} | "
                f"{users_count:2} مستخدم | {perms_count:2} صلاحية"
            )
        
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✅ تم تحديث الأدوار بنجاح!"))
        self.stdout.write(self.style.SUCCESS("💡 الآن يمكنك استخدام الصلاحيات المخصصة المبسطة"))
        self.stdout.write("=" * 70)
