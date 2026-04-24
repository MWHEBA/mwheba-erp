"""
✅ PHASE 7: Simplified Health Check Endpoints
Essential health checks for production monitoring
"""
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
import time
import logging

logger = logging.getLogger(__name__)

def health_check(request):
    """
    ✅ SIMPLIFIED: Basic health check endpoint
    Returns 200 if system is healthy, 503 if not
    """
    health_status = {
        'status': 'healthy',
        'timestamp': time.time(),
        'checks': {}
    }
    
    overall_healthy = True
    
    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        health_status['checks']['database'] = {'status': 'healthy'}
    except Exception as e:
        health_status['checks']['database'] = {'status': 'unhealthy', 'error': str(e)}
        overall_healthy = False
        logger.error(f"Database health check failed: {e}")
    
    # Cache check (optional - don't fail if cache is down)
    try:
        cache_key = 'health_check_test'
        cache.set(cache_key, 'test_value', 10)
        cached_value = cache.get(cache_key)
        
        if cached_value == 'test_value':
            health_status['checks']['cache'] = {'status': 'healthy'}
        else:
            health_status['checks']['cache'] = {'status': 'degraded'}
    except Exception as e:
        health_status['checks']['cache'] = {'status': 'degraded', 'error': str(e)}
        logger.warning(f"Cache health check failed: {e}")
    
    # Backup system check (optional - don't fail if backup is down)
    try:
        from core.services.backup_service import BackupService
        backup_service = BackupService()
        
        # Check if backup directory exists and is writable
        if backup_service.backup_dir.exists() and backup_service.backup_dir.is_dir():
            health_status['checks']['backup'] = {'status': 'healthy'}
        else:
            health_status['checks']['backup'] = {'status': 'degraded', 'error': 'Backup directory not accessible'}
    except Exception as e:
        health_status['checks']['backup'] = {'status': 'degraded', 'error': str(e)}
        logger.warning(f"Backup health check failed: {e}")
    
    # Set overall status
    if not overall_healthy:
        health_status['status'] = 'unhealthy'
        return JsonResponse(health_status, status=503)
    
    return JsonResponse(health_status, status=200)


def readiness_check(request):
    """
    ✅ SIMPLIFIED: Basic readiness check for deployment
    Returns 200 if system is ready to serve traffic
    """
    readiness_status = {
        'status': 'ready',
        'timestamp': time.time(),
        'checks': {}
    }
    
    overall_ready = True
    
    # Database migrations check
    try:
        from django.db.migrations.executor import MigrationExecutor
        from django.db import connections
        
        executor = MigrationExecutor(connections['default'])
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        
        if plan:
            readiness_status['checks']['migrations'] = {
                'status': 'not_ready', 
                'error': f'{len(plan)} pending migrations'
            }
            overall_ready = False
        else:
            readiness_status['checks']['migrations'] = {'status': 'ready'}
            
    except Exception as e:
        readiness_status['checks']['migrations'] = {'status': 'error', 'error': str(e)}
        overall_ready = False
        logger.error(f"Migration check failed: {e}")
    
    # Set overall status
    if not overall_ready:
        readiness_status['status'] = 'not_ready'
        return JsonResponse(readiness_status, status=503)
    
    return JsonResponse(readiness_status, status=200)