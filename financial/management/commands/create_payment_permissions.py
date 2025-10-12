"""
أمر Django لإنشاء صلاحيات تعديل الدفعات
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from financial.models.journal_entry import JournalEntry


class Command(BaseCommand):
    help = 'إنشاء صلاحيات تعديل الدفعات'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('بدء إنشاء صلاحيات تعديل الدفعات...'))
        
        try:
            # الحصول على content type للقيود المحاسبية
            journal_entry_ct = ContentType.objects.get_for_model(JournalEntry)
            
            # إنشاء الصلاحيات
            permissions_created = 0
            
            # صلاحية تعديل الدفعات المرحّلة
            perm, created = Permission.objects.get_or_create(
                codename='can_edit_posted_payments',
                name='يمكن تعديل الدفعات المرحّلة',
                content_type=journal_entry_ct,
            )
            if created:
                permissions_created += 1
                self.stdout.write(f'✅ تم إنشاء صلاحية: {perm.name}')
            else:
                self.stdout.write(f'⚠️  الصلاحية موجودة مسبقاً: {perm.name}')
            
            # صلاحية إلغاء ترحيل الدفعات
            perm, created = Permission.objects.get_or_create(
                codename='can_unpost_payments',
                name='يمكن إلغاء ترحيل الدفعات',
                content_type=journal_entry_ct,
            )
            if created:
                permissions_created += 1
                self.stdout.write(f'✅ تم إنشاء صلاحية: {perm.name}')
            else:
                self.stdout.write(f'⚠️  الصلاحية موجودة مسبقاً: {perm.name}')
            
            # صلاحية حذف القيود المرحلة (موجودة مسبقاً)
            perm, created = Permission.objects.get_or_create(
                codename='force_delete_posted_entry',
                name='يمكن حذف القيود المرحلة',
                content_type=journal_entry_ct,
            )
            if created:
                permissions_created += 1
                self.stdout.write(f'✅ تم إنشاء صلاحية: {perm.name}')
            else:
                self.stdout.write(f'⚠️  الصلاحية موجودة مسبقاً: {perm.name}')
            
            # النتيجة النهائية
            if permissions_created > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'🎉 تم إنشاء {permissions_created} صلاحية جديدة بنجاح!')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('جميع الصلاحيات موجودة مسبقاً')
                )
            
            # إرشادات للمستخدم
            self.stdout.write('\n' + '='*50)
            self.stdout.write(self.style.SUCCESS('📋 إرشادات الاستخدام:'))
            self.stdout.write('1. اذهب إلى لوحة الإدارة Django')
            self.stdout.write('2. اختر المستخدمين أو المجموعات')
            self.stdout.write('3. أضف الصلاحيات التالية حسب الحاجة:')
            self.stdout.write('   - يمكن تعديل الدفعات المرحّلة')
            self.stdout.write('   - يمكن إلغاء ترحيل الدفعات')
            self.stdout.write('   - يمكن حذف القيود المرحلة (للمدير فقط)')
            self.stdout.write('='*50)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في إنشاء الصلاحيات: {str(e)}')
            )
            raise e
