"""
Management Command لتنظيف JWT Tokens المنتهية الصلاحية
يجب تشغيله يومياً عبر cron job
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'تنظيف JWT Tokens المنتهية الصلاحية من قاعدة البيانات'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='عدد الأيام للاحتفاظ بالـ tokens المنتهية الصلاحية (افتراضي: 7)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض النتائج بدون حذف فعلي'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        
        # حساب التاريخ الحد
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(
            self.style.SUCCESS(f'🧹 بدء تنظيف JWT Tokens المنتهية الصلاحية قبل {cutoff_date}')
        )
        
        # العثور على الـ tokens المنتهية الصلاحية
        expired_outstanding = OutstandingToken.objects.filter(
            expires_at__lt=cutoff_date
        )
        
        expired_blacklisted = BlacklistedToken.objects.filter(
            token__expires_at__lt=cutoff_date
        )
        
        outstanding_count = expired_outstanding.count()
        blacklisted_count = expired_blacklisted.count()
        
        self.stdout.write(f'📊 تم العثور على:')
        self.stdout.write(f'   - {outstanding_count} outstanding tokens منتهية الصلاحية')
        self.stdout.write(f'   - {blacklisted_count} blacklisted tokens منتهية الصلاحية')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 Dry run mode - لن يتم حذف أي tokens')
            )
            return
        
        # حذف الـ tokens المنتهية الصلاحية
        try:
            # حذف blacklisted tokens أولاً (لأنها تعتمد على outstanding)
            deleted_blacklisted = expired_blacklisted.delete()[0]
            
            # حذف outstanding tokens
            deleted_outstanding = expired_outstanding.delete()[0]
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ تم حذف {deleted_blacklisted} blacklisted tokens و {deleted_outstanding} outstanding tokens'
                )
            )
            
            # تسجيل العملية
            logger.info(
                f'JWT Token cleanup completed: {deleted_blacklisted} blacklisted, '
                f'{deleted_outstanding} outstanding tokens deleted'
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في تنظيف الـ tokens: {str(e)}')
            )
            logger.error(f'JWT Token cleanup failed: {str(e)}')
            
        # إحصائيات ما بعد التنظيف
        remaining_outstanding = OutstandingToken.objects.count()
        remaining_blacklisted = BlacklistedToken.objects.count()
        
        self.stdout.write(f'📈 الإحصائيات النهائية:')
        self.stdout.write(f'   - {remaining_outstanding} outstanding tokens متبقية')
        self.stdout.write(f'   - {remaining_blacklisted} blacklisted tokens متبقية')
        
        self.stdout.write(
            self.style.SUCCESS('🎉 تم الانتهاء من تنظيف JWT Tokens بنجاح!')
        )