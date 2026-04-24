"""
Management command to run performance optimizations
✅ PHASE 3: Performance optimization command
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings
from django.core.cache import cache
from django.db import connection
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run comprehensive performance optimizations'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-indexes',
            action='store_true',
            help='Skip database index creation'
        )
        parser.add_argument(
            '--skip-cache',
            action='store_true',
            help='Skip cache warming'
        )
        parser.add_argument(
            '--skip-cleanup',
            action='store_true',
            help='Skip cleanup operations'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting Performance Optimization')
        )
        
        start_time = time.time()
        
        # 1. Database optimizations
        if not options['skip_indexes']:
            self.optimize_database(dry_run)
        
        # 2. Cache optimizations
        if not options['skip_cache']:
            self.optimize_cache(dry_run)
        
        # 3. Cleanup operations
        if not options['skip_cleanup']:
            self.cleanup_operations(dry_run)
        
        # 4. Performance analysis
        self.analyze_performance()
        
        total_time = time.time() - start_time
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Performance optimization completed in {total_time:.2f} seconds'
            )
        )
    
    def optimize_database(self, dry_run=False):
        """Run database optimizations"""
        self.stdout.write('📊 Optimizing database...')
        
        # Add database indexes
        try:
            call_command('add_database_indexes', dry_run=dry_run, verbosity=0)
            self.stdout.write(
                self.style.SUCCESS('  ✅ Database indexes optimized')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Database index optimization failed: {e}')
            )
        
        # Analyze database statistics
        if not dry_run:
            self.analyze_database_stats()
    
    def optimize_cache(self, dry_run=False):
        """Run cache optimizations"""
        self.stdout.write('🗄️  Optimizing cache...')
        
        if dry_run:
            self.stdout.write('  Would warm up cache with common queries')
            return
        
        try:
            # Warm up cache with common queries
            self.warm_cache()
            
            # Clear old cache entries
            self.clear_old_cache()
            
            self.stdout.write(
                self.style.SUCCESS('  ✅ Cache optimized')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Cache optimization failed: {e}')
            )
    
    def cleanup_operations(self, dry_run=False):
        """Run cleanup operations"""
        self.stdout.write('🧹 Running cleanup operations...')
        
        if dry_run:
            self.stdout.write('  Would clean up old files and cache entries')
            return
        
        try:
            # Clean up old media files
            from core.utils.static_optimization import MediaFileManager
            
            media_root = getattr(settings, 'MEDIA_ROOT', None)
            if media_root:
                cleanup_result = MediaFileManager.cleanup_old_files(media_root, days_old=90)
                if cleanup_result['success']:
                    self.stdout.write(
                        f"  ✅ Cleaned {cleanup_result['deleted_count']} old media files"
                    )
            
            # Run async cleanup task
            from core.tasks.async_operations import cleanup_old_cache_entries
            cleanup_old_cache_entries.delay()
            
            self.stdout.write(
                self.style.SUCCESS('  ✅ Cleanup operations completed')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Cleanup operations failed: {e}')
            )
    
    def warm_cache(self):
        """Warm up cache with common queries"""
        try:
            # Import here to avoid circular imports
            from core.utils.performance_cache import (
                get_active_customers_count,
                get_pending_payments_summary,
                get_dashboard_statistics
            )
            
            # Warm up common cached queries
            get_active_customers_count()
            get_pending_payments_summary()
            get_dashboard_statistics()
            
            self.stdout.write('  ✅ Cache warmed up with common queries')
            
        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
    
    def clear_old_cache(self):
        """Clear old cache entries"""
        try:
            # Clear pagination cache
            from core.utils.pagination_optimizer import clear_pagination_cache
            clear_pagination_cache()
            
            # Clear performance stats older than 1 hour
            from core.middleware.performance_monitoring import clear_performance_stats
            clear_performance_stats()
            
            self.stdout.write('  ✅ Old cache entries cleared')
            
        except Exception as e:
            logger.error(f"Cache clearing failed: {e}")
    
    def analyze_database_stats(self):
        """Analyze database performance statistics"""
        try:
            with connection.cursor() as cursor:
                # Get database engine
                db_engine = settings.DATABASES['default']['ENGINE']
                
                if 'mysql' in db_engine:
                    # MySQL specific statistics
                    cursor.execute("SHOW STATUS LIKE 'Queries'")
                    queries = cursor.fetchone()
                    
                    cursor.execute("SHOW STATUS LIKE 'Uptime'")
                    uptime = cursor.fetchone()
                    
                    if queries and uptime:
                        qps = int(queries[1]) / int(uptime[1])
                        self.stdout.write(f'  📈 Database QPS: {qps:.2f}')
                
                elif 'sqlite' in db_engine:
                    # SQLite specific statistics
                    cursor.execute("PRAGMA cache_size")
                    cache_size = cursor.fetchone()
                    
                    if cache_size:
                        self.stdout.write(f'  📈 SQLite cache size: {cache_size[0]} pages')
                
        except Exception as e:
            logger.error(f"Database stats analysis failed: {e}")
    
    def analyze_performance(self):
        """Analyze current performance metrics"""
        self.stdout.write('📈 Analyzing performance metrics...')
        
        try:
            # Get performance statistics
            from core.middleware.performance_monitoring import get_performance_stats
            stats = get_performance_stats()
            
            if 'request_stats' in stats and stats['request_stats']:
                request_stats = stats['request_stats']
                
                self.stdout.write(f"  📊 Total requests: {request_stats.get('total_requests', 0)}")
                self.stdout.write(f"  ⏱️  Average response time: {request_stats.get('avg_response_time', 0):.3f}s")
                self.stdout.write(f"  🗃️  Average queries per request: {request_stats.get('avg_queries_per_request', 0):.1f}")
                self.stdout.write(f"  🐌 Slow requests: {request_stats.get('slow_requests', 0)}")
                self.stdout.write(f"  ❌ Error requests: {request_stats.get('error_requests', 0)}")
            
            # Get cache statistics
            if 'cache_stats' in stats and stats['cache_stats']:
                cache_stats = stats['cache_stats']
                total_cache_requests = cache_stats.get('hits', 0) + cache_stats.get('misses', 0)
                
                if total_cache_requests > 0:
                    hit_rate = (cache_stats.get('hits', 0) / total_cache_requests) * 100
                    self.stdout.write(f"  🎯 Cache hit rate: {hit_rate:.1f}%")
                    self.stdout.write(f"  💾 Cache memory usage: {cache_stats.get('memory_usage', 'Unknown')}")
            
            # Get database connection info
            db_queries_count = len(connection.queries)
            self.stdout.write(f"  🔗 Database queries in this session: {db_queries_count}")
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'  ⚠️  Performance analysis failed: {e}')
            )
    
    def get_optimization_recommendations(self):
        """Get performance optimization recommendations"""
        recommendations = []
        
        try:
            # Check cache configuration
            if not getattr(settings, 'REDIS_URL', None):
                recommendations.append(
                    "Consider setting up Redis for better caching performance"
                )
            
            # Check database configuration
            db_engine = settings.DATABASES['default']['ENGINE']
            if 'sqlite' in db_engine and not settings.DEBUG:
                recommendations.append(
                    "Consider using PostgreSQL or MySQL for production instead of SQLite"
                )
            
            # Check static files configuration
            if settings.DEBUG:
                recommendations.append(
                    "Ensure DEBUG=False in production for better static file serving"
                )
            
            # Check middleware configuration
            middleware = settings.MIDDLEWARE
            if 'core.middleware.performance_monitoring.PerformanceMonitoringMiddleware' not in middleware:
                recommendations.append(
                    "Add PerformanceMonitoringMiddleware for better monitoring"
                )
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            return []