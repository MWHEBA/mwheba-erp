"""
أمر لتبسيط أرقام القيود المحاسبية الموجودة
تحويل من FEE-111-20260103130915 إلى FEE-0001
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from financial.models.journal_entry import JournalEntry


class Command(BaseCommand):
    help = 'تبسيط أرقام القيود المحاسبية الموجودة'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض التغييرات المطلوبة دون تطبيقها',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=200,
            help='عدد القيود المراد معالجتها (افتراضي: 200)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        
        self.stdout.write(
            self.style.SUCCESS('🔧 بدء تبسيط أرقام القيود المحاسبية...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️ وضع المعاينة - لن يتم حفظ التغييرات')
            )

        # جلب جميع القيود التي تحتاج تبسيط
        entries = JournalEntry.objects.all().order_by('id')[:limit]

        if not entries.exists():
            self.stdout.write(
                self.style.WARNING('لا توجد قيود تحتاج تبسيط')
            )
            return

        # تجميع القيود حسب البادئة
        prefixes = {}
        for entry in entries:
            if '-' in entry.number:
                prefix = entry.number.split('-')[0]
                if prefix not in prefixes:
                    prefixes[prefix] = []
                prefixes[prefix].append(entry)

        updated_count = 0
        errors_count = 0

        # معالجة كل بادئة على حدة
        for prefix, prefix_entries in prefixes.items():
            self.stdout.write(f"\n📋 معالجة البادئة: {prefix} ({len(prefix_entries)} قيد)")
            
            # ترتيب القيود حسب ID للحفاظ على التسلسل
            prefix_entries.sort(key=lambda x: x.id)
            
            for index, entry in enumerate(prefix_entries, 1):
                try:
                    with transaction.atomic():
                        old_number = entry.number
                        new_number = f"{prefix}-{index:04d}"
                        
                        # التحقق من عدم وجود رقم مكرر
                        if JournalEntry.objects.filter(number=new_number).exclude(id=entry.id).exists():
                            # إذا كان الرقم موجود، استخدم رقم أعلى
                            max_existing = JournalEntry.objects.filter(
                                number__startswith=f"{prefix}-"
                            ).exclude(id=entry.id).count()
                            new_number = f"{prefix}-{max_existing + index:04d}"
                        
                        if old_number != new_number:
                            if not dry_run:
                                entry.number = new_number
                                entry.save(update_fields=['number'])
                            
                            updated_count += 1
                            self.stdout.write(
                                f"  ✅ {old_number} → {new_number}"
                            )
                        
                except Exception as e:
                    errors_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"  ❌ خطأ في القيد {entry.number}: {str(e)}")
                    )

        # عرض النتائج
        self.stdout.write(
            self.style.SUCCESS(f'\n📊 النتائج:')
        )
        self.stdout.write(f"✅ تم تبسيط: {updated_count} قيد")
        if errors_count > 0:
            self.stdout.write(
                self.style.ERROR(f"❌ أخطاء: {errors_count} قيد")
            )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('\n⚠️ لتطبيق التغييرات، قم بتشغيل الأمر بدون --dry-run')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('\n🎉 تم تبسيط أرقام القيود بنجاح!')
            )
            
        # عرض ملخص البادئات
        self.stdout.write(f'\n📋 ملخص البادئات:')
        for prefix, prefix_entries in prefixes.items():
            self.stdout.write(f"  {prefix}: {len(prefix_entries)} قيد")