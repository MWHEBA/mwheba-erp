# financial/management/commands/create_audit_trail_test_data.py
"""
أمر لإنشاء بيانات وهمية لاختبار سجل التدقيق
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta
import random

from financial.models import AuditTrail, JournalEntry

User = get_user_model()


class Command(BaseCommand):
    help = 'إنشاء بيانات وهمية لاختبار سجل التدقيق'

    def add_arguments(self, parser):
        parser.add_argument(
            '--entries',
            type=int,
            default=50,
            help='عدد السجلات المراد إنشاؤها (افتراضي: 50)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        entries_count = options['entries']
        
        self.stdout.write(self.style.SUCCESS('🚀 بدء إنشاء بيانات سجل التدقيق...'))
        
        # الحصول على مستخدمين
        users = list(User.objects.all()[:5])  # أول 5 مستخدمين
        if not users:
            self.stdout.write(self.style.ERROR('❌ لا يوجد مستخدمين في النظام'))
            return
        
        # الحصول على بعض القيود للربط
        journal_entries = list(JournalEntry.objects.all()[:20])
        
        # إنشاء سجلات التدقيق
        created = self._create_audit_entries(users, journal_entries, entries_count)
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ تم إنشاء {created} سجل تدقيق بنجاح!'
        ))
    
    def _create_audit_entries(self, users, journal_entries, count):
        """إنشاء سجلات التدقيق"""
        
        actions = ['create', 'update', 'delete', 'post', 'unpost', 'sync']
        entity_types = ['sale_payment', 'purchase_payment', 'journal_entry', 'cash_movement', 'sale', 'purchase']
        
        descriptions = {
            'create': [
                'إنشاء قيد محاسبي جديد',
                'إنشاء دفعة مبيعات',
                'إنشاء دفعة مشتريات',
                'إنشاء حركة خزينة',
            ],
            'update': [
                'تحديث بيانات القيد',
                'تعديل مبلغ الدفعة',
                'تحديث طريقة الدفع',
                'تعديل تاريخ العملية',
            ],
            'delete': [
                'حذف قيد محاسبي',
                'حذف دفعة',
                'حذف حركة خزينة',
            ],
            'post': [
                'ترحيل قيد محاسبي',
                'ترحيل دفعة للحسابات',
                'اعتماد العملية',
            ],
            'unpost': [
                'إلغاء ترحيل قيد',
                'إلغاء ترحيل دفعة',
                'إلغاء الاعتماد',
            ],
            'sync': [
                'ربط مالي تلقائي',
                'مزامنة مع النظام المالي',
                'تحديث الحسابات',
            ],
        }
        
        created = 0
        today = timezone.now()
        
        for i in range(count):
            # تاريخ عشوائي في آخر 30 يوم
            days_ago = random.randint(0, 30)
            timestamp = today - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            
            # اختيار عشوائي
            action = random.choice(actions)
            entity_type = random.choice(entity_types)
            user = random.choice(users)
            
            # وصف العملية
            description = random.choice(descriptions.get(action, ['عملية على النظام']))
            
            # بيانات إضافية
            entity_id = random.randint(1, 1000)
            entity_name = f"{entity_type} #{entity_id}"
            
            # قيم قديمة وجديدة (للتحديثات)
            old_values = None
            new_values = None
            if action == 'update':
                old_values = {
                    'amount': random.randint(1000, 50000),
                    'status': random.choice(['draft', 'pending']),
                    'date': (today - timedelta(days=days_ago+1)).strftime('%Y-%m-%d'),
                }
                new_values = {
                    'amount': random.randint(1000, 50000),
                    'status': random.choice(['posted', 'approved']),
                    'date': (today - timedelta(days=days_ago)).strftime('%Y-%m-%d'),
                }
            
            # معلومات إضافية
            metadata = {
                'module': 'financial',
                'ip_address': f'192.168.1.{random.randint(1, 255)}',
                'browser': random.choice(['Chrome', 'Firefox', 'Safari', 'Edge']),
            }
            
            # إنشاء السجل
            try:
                AuditTrail.objects.create(
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_name=entity_name,
                    user=user,
                    timestamp=timestamp,
                    description=description,
                    old_values=old_values,
                    new_values=new_values,
                    metadata=metadata,
                    status='success',
                )
                created += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️ فشل إنشاء سجل: {e}'))
        
        return created
