# -*- coding: utf-8 -*-
"""
System Performance Optimization Command

Management command to optimize system performance using the unified services
and caching infrastructure.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from typing import Dict, Any
import logging

from core.services import ServiceFactory
from core.services.system_cache_service import SystemCacheService, BulkSystemCacheService
from core.utils.service_integration import ServiceIntegrationHelper

logger = logging.getLogger('core.management.optimize_performance')


class Command(BaseCommand):
    """
    Management command for system performance optimization.
    
    Features:
    - Warm system caches
    - Optimize database queries
    - Bulk operations for performance
    - Performance monitoring
    """
    
    help = 'Optimize system performance using unified services and caching'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--warm-caches',
            action='store_true',
            help='Warm system caches for better performance'
        )
        
        parser.add_argument(
            '--warm-user-caches',
            type=int,
            metavar='LIMIT',
            help='Warm user caches for most active users (specify limit)'
        )
        
        parser.add_argument(
            '--check-cache-health',
            action='store_true',
            help='Check cache system health'
        )
        
        parser.add_argument(
            '--optimize-queries',
            action='store_true',
            help='Run query optimization checks'
        )
        
        parser.add_argument(
            '--bulk-operations-test',
            type=int,
            metavar='BATCH_SIZE',
            help='Test bulk operations with specified batch size'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
    
    def handle(self, *args, **options):
        """Handle command execution."""
        self.verbosity = 2 if options['verbose'] else 1
        
        self.stdout.write(
            self.style.SUCCESS('🚀 بدء تحسين أداء النظام...')
        )
        
        results = {}
        
        # Warm system caches
        if options['warm_caches']:
            results['cache_warming'] = self._warm_system_caches()
        
        # Warm user caches
        if options['warm_user_caches']:
            results['user_cache_warming'] = self._warm_user_caches(options['warm_user_caches'])
        
        # Check cache health
        if options['check_cache_health']:
            results['cache_health'] = self._check_cache_health()
        
        # Query optimization checks
        if options['optimize_queries']:
            results['query_optimization'] = self._check_query_optimization()
        
        # Bulk operations test
        if options['bulk_operations_test']:
            results['bulk_operations'] = self._test_bulk_operations(options['bulk_operations_test'])
        
        # Display summary
        self._display_summary(results)
        
        self.stdout.write(
            self.style.SUCCESS('✅ تم تحسين أداء النظام بنجاح!')
        )
    
    def _warm_system_caches(self) -> Dict[str, Any]:
        """Warm system-wide caches."""
        self.stdout.write('📊 تسخين ذاكرة التخزين المؤقت للنظام...')
        
        try:
            cache_service = SystemCacheService()
            result = cache_service.execute('warm_system_stats')
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS('  ✓ تم تسخين إحصائيات النظام')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ فشل في تسخين إحصائيات النظام: {result.get("error", "Unknown error")}')
                )
            
            return result
            
        except Exception as e:
            error_msg = f'خطأ في تسخين ذاكرة التخزين المؤقت: {e}'
            self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
            return {'success': False, 'error': str(e)}
    
    def _warm_user_caches(self, limit: int) -> Dict[str, Any]:
        """Warm user caches for most active users."""
        self.stdout.write(f'👥 تسخين ذاكرة التخزين المؤقت للمستخدمين (الحد الأقصى: {limit})...')
        
        try:
            from users.models import User
            
            # Get most active users
            active_users = User.objects.filter(
                is_active=True,
                last_login__isnull=False
            ).order_by('-last_login')[:limit]
            
            user_ids = [user.id for user in active_users]
            
            if not user_ids:
                self.stdout.write(
                    self.style.WARNING('  ⚠ لا توجد مستخدمين نشطين للتسخين')
                )
                return {'success': True, 'message': 'No active users found'}
            
            result = ServiceIntegrationHelper.warm_user_caches(user_ids)
            
            success_count = len(result['success'])
            failed_count = len(result['failed'])
            
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ تم تسخين ذاكرة {success_count} مستخدم')
            )
            
            if failed_count > 0:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ فشل في تسخين ذاكرة {failed_count} مستخدم')
                )
            
            return result
            
        except Exception as e:
            error_msg = f'خطأ في تسخين ذاكرة المستخدمين: {e}'
            self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
            return {'success': False, 'error': str(e)}
    
    def _check_cache_health(self) -> Dict[str, Any]:
        """Check cache system health."""
        self.stdout.write('🏥 فحص صحة نظام التخزين المؤقت...')
        
        try:
            cache_service = SystemCacheService()
            health_stats = cache_service.execute('get_cache_health')
            
            status = health_stats.get('status', 'unknown')
            connectivity = health_stats.get('connectivity', 'unknown')
            
            if status == 'healthy' and connectivity == 'ok':
                self.stdout.write(
                    self.style.SUCCESS('  ✓ نظام التخزين المؤقت يعمل بشكل طبيعي')
                )
            elif status == 'warning':
                self.stdout.write(
                    self.style.WARNING('  ⚠ نظام التخزين المؤقت يعمل مع تحذيرات')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('  ✗ مشاكل في نظام التخزين المؤقت')
                )
            
            if self.verbosity >= 2:
                self.stdout.write(f'    Backend: {health_stats.get("cache_backend", "Unknown")}')
                if 'hit_rate' in health_stats:
                    self.stdout.write(f'    Hit Rate: {health_stats["hit_rate"]}%')
                if 'used_memory' in health_stats:
                    self.stdout.write(f'    Memory Used: {health_stats["used_memory"]}')
            
            return health_stats
            
        except Exception as e:
            error_msg = f'خطأ في فحص صحة النظام: {e}'
            self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
            return {'status': 'error', 'error': str(e)}
    
    def _check_query_optimization(self) -> Dict[str, Any]:
        """Check query optimization status."""
        self.stdout.write('🔍 فحص تحسين الاستعلامات...')
        
        try:
            # Test optimized user queries
            service = ServiceIntegrationHelper.get_user_management_service()
            
            # Time the optimized query
            import time
            start_time = time.time()
            
            users_with_stats = service.execute('get_users_with_stats')
            
            query_time = time.time() - start_time
            
            user_count = len(users_with_stats) if users_with_stats else 0
            
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ تم جلب {user_count} مستخدم في {query_time:.3f} ثانية')
            )
            
            # Performance thresholds
            if query_time < 0.5:
                performance_status = 'excellent'
                self.stdout.write(
                    self.style.SUCCESS('  ✓ أداء ممتاز للاستعلامات')
                )
            elif query_time < 1.0:
                performance_status = 'good'
                self.stdout.write(
                    self.style.SUCCESS('  ✓ أداء جيد للاستعلامات')
                )
            elif query_time < 2.0:
                performance_status = 'acceptable'
                self.stdout.write(
                    self.style.WARNING('  ⚠ أداء مقبول للاستعلامات')
                )
            else:
                performance_status = 'needs_improvement'
                self.stdout.write(
                    self.style.ERROR('  ✗ الاستعلامات تحتاج تحسين')
                )
            
            return {
                'query_time': query_time,
                'user_count': user_count,
                'performance_status': performance_status
            }
            
        except Exception as e:
            error_msg = f'خطأ في فحص تحسين الاستعلامات: {e}'
            self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
            return {'error': str(e)}
    
    def _test_bulk_operations(self, batch_size: int) -> Dict[str, Any]:
        """Test bulk operations performance."""
        self.stdout.write(f'📦 اختبار العمليات الجماعية (حجم الدفعة: {batch_size})...')
        
        try:
            from users.models import User
            
            # Get sample users for testing
            sample_users = User.objects.filter(is_active=True)[:batch_size * 2]
            user_ids = [user.id for user in sample_users]
            
            if len(user_ids) < batch_size:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ عدد المستخدمين المتاحين ({len(user_ids)}) أقل من حجم الدفعة المطلوب')
                )
                batch_size = len(user_ids)
            
            # Test bulk cache service
            bulk_cache_service = BulkSystemCacheService(batch_size=batch_size)
            
            import time
            start_time = time.time()
            
            # Process in batches
            batches = [user_ids[i:i + batch_size] for i in range(0, len(user_ids), batch_size)]
            total_processed = 0
            
            for batch in batches:
                result = bulk_cache_service.execute_bulk(batch, 'warm_user_caches')
                total_processed += len(result['success'])
            
            bulk_time = time.time() - start_time
            
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ تمت معالجة {total_processed} مستخدم في {bulk_time:.3f} ثانية')
            )
            
            # Calculate performance metrics
            items_per_second = total_processed / bulk_time if bulk_time > 0 else 0
            
            self.stdout.write(
                self.style.SUCCESS(f'  📈 معدل المعالجة: {items_per_second:.1f} عنصر/ثانية')
            )
            
            return {
                'batch_size': batch_size,
                'total_processed': total_processed,
                'processing_time': bulk_time,
                'items_per_second': items_per_second
            }
            
        except Exception as e:
            error_msg = f'خطأ في اختبار العمليات الجماعية: {e}'
            self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
            return {'error': str(e)}
    
    def _display_summary(self, results: Dict[str, Any]) -> None:
        """Display optimization summary."""
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('📋 ملخص تحسين الأداء'))
        self.stdout.write('='*50)
        
        for operation, result in results.items():
            if isinstance(result, dict) and not result.get('error'):
                if operation == 'cache_warming':
                    self.stdout.write(f'🔥 تسخين ذاكرة النظام: {"نجح" if result.get("success") else "فشل"}')
                
                elif operation == 'user_cache_warming':
                    success_count = len(result.get('success', []))
                    self.stdout.write(f'👥 تسخين ذاكرة المستخدمين: {success_count} مستخدم')
                
                elif operation == 'cache_health':
                    status = result.get('status', 'unknown')
                    self.stdout.write(f'🏥 صحة النظام: {status}')
                
                elif operation == 'query_optimization':
                    query_time = result.get('query_time', 0)
                    user_count = result.get('user_count', 0)
                    self.stdout.write(f'🔍 أداء الاستعلامات: {user_count} مستخدم في {query_time:.3f}s')
                
                elif operation == 'bulk_operations':
                    items_per_second = result.get('items_per_second', 0)
                    self.stdout.write(f'📦 العمليات الجماعية: {items_per_second:.1f} عنصر/ثانية')
            
            else:
                error = result.get('error', 'Unknown error') if isinstance(result, dict) else str(result)
                self.stdout.write(f'❌ {operation}: {error}')
        
        self.stdout.write('='*50)
        self.stdout.write(f'⏰ وقت التنفيذ: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')