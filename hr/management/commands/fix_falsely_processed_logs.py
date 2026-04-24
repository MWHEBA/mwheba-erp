"""
إصلاح سجلات البصمة المعلمة كـ "معالجة" بدون سجل حضور فعلي.

السجلات المتضررة هي: is_processed=True AND attendance=None
سببها: الكود القديم كان يعلم السجلات الفاشلة كـ "معالجة" لتجنب إعادة المعالجة.

الحل: إعادة تعيين is_processed=False عليها لتدخل في المعالجة التالية.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from hr.models import BiometricLog


class Command(BaseCommand):
    help = 'إصلاح سجلات البصمة المعلمة كمعالجة بدون سجل حضور فعلي'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض العدد فقط بدون تعديل'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # السجلات المتضررة: معلمة كـ "معالجة" لكن مش مربوطة بـ attendance
        affected = BiometricLog.objects.filter(
            is_processed=True,
            attendance__isnull=True,
            employee__isnull=False  # مربوطة بموظف - يعني كان المفروض يتعمل لها attendance
        )

        count = affected.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('لا توجد سجلات متضررة.'))
            return

        self.stdout.write(
            f'سجلات معلمة كـ "معالجة" بدون attendance: {count}'
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('dry-run: لم يتم التعديل.'))
            return

        with transaction.atomic():
            updated = affected.update(
                is_processed=False,
                processed_at=None
            )

        self.stdout.write(self.style.SUCCESS(
            f'تم إعادة تعيين {updated} سجل - ستُعالج في المرة القادمة.'
        ))
