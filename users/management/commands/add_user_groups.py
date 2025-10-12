from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from users.models import User

class Command(BaseCommand):
    help = 'إضافة المستخدمين إلى المجموعات المناسبة'

    def handle(self, *args, **options):
        # تعيين المجموعات
        try:
            admin_group = Group.objects.get(name='المدراء')
            accountant_group = Group.objects.get(name='المحاسبون')
            inventory_group = Group.objects.get(name='مدراء المخزون')
            sales_group = Group.objects.get(name='مندوبي المبيعات')
            
            # إضافة المستخدمين إلى المجموعات
            # المدير
            try:
                admin_user = User.objects.get(username='admin')
                admin_user.groups.add(admin_group)
                self.stdout.write(self.style.SUCCESS(f'تم إضافة {admin_user.username} إلى مجموعة {admin_group.name}'))
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING('المستخدم admin غير موجود'))
            
            # المحاسب
            try:
                accountant_user = User.objects.get(username='accountant')
                accountant_user.groups.add(accountant_group)
                self.stdout.write(self.style.SUCCESS(f'تم إضافة {accountant_user.username} إلى مجموعة {accountant_group.name}'))
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING('المستخدم accountant غير موجود'))
            
            # مدير المخزون
            try:
                inventory_user = User.objects.get(username='inventory')
                inventory_user.groups.add(inventory_group)
                self.stdout.write(self.style.SUCCESS(f'تم إضافة {inventory_user.username} إلى مجموعة {inventory_group.name}'))
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING('المستخدم inventory غير موجود'))
            
            # مندوبي المبيعات
            for sales_username in ['sales1', 'sales2']:
                try:
                    sales_user = User.objects.get(username=sales_username)
                    sales_user.groups.add(sales_group)
                    self.stdout.write(self.style.SUCCESS(f'تم إضافة {sales_user.username} إلى مجموعة {sales_group.name}'))
                except User.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'المستخدم {sales_username} غير موجود'))
            
            self.stdout.write(self.style.SUCCESS('تمت إضافة جميع المستخدمين إلى المجموعات بنجاح'))
            
        except Group.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f'خطأ: {e}')) 