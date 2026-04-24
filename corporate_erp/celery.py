"""
Celery configuration for corporate_erp project.
"""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')

app = Celery('corporate_erp')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery configuration
app.conf.update(
    # Task routing
    task_routes={
        'client.tasks.send_payment_notification': {'queue': 'notifications'},
        'client.tasks.generate_payment_report': {'queue': 'reports'},
        'financial.tasks.process_accounting_integration': {'queue': 'accounting'},
        'financial.tasks.bulk_process_settlements': {'queue': 'bulk_processing'},
    },
    
    # Task serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Africa/Cairo',
    enable_utc=True,
    
    # Task execution
    task_always_eager=False,
    task_eager_propagates=True,
    task_ignore_result=False,
    task_store_eager_result=True,
    
    # Task retry configuration
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Worker configuration
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    
    # Result backend
    result_backend='redis://localhost:6379/1' if not settings.DEBUG else 'cache+memcache://127.0.0.1:11211/',
    result_expires=3600,  # 1 hour
    
    # Broker configuration
    broker_url='redis://localhost:6379/0' if not settings.DEBUG else 'memory://',
    broker_transport_options={'visibility_timeout': 3600},
    
    # Beat schedule for periodic tasks
    beat_schedule={
        # Financial settlement tasks
        'retry-failed-settlements': {
            'task': 'financial.tasks.retry_failed_settlements',
            'schedule': 300.0,
        },
        'cleanup-old-audit-logs': {
            'task': 'financial.tasks.cleanup_old_audit_logs',
            'schedule': 86400.0,
        },
        'generate-daily-settlement-report': {
            'task': 'financial.tasks.generate_daily_settlement_report',
            'schedule': 3600.0,
        },
        
        # HR Biometric tasks
        'process-biometric-logs': {
            'task': 'hr.tasks.process_biometric_logs_task',
            'schedule': 300.0,  # Every 5 minutes - معالجة البصمات كل 5 دقائق
        },
        'cleanup-old-biometric-logs': {
            'task': 'hr.tasks.cleanup_old_biometric_logs',
            'schedule': 604800.0,  # Weekly - حذف السجلات القديمة أسبوعياً
            'kwargs': {'months': 6}
        },
    },
)

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery configuration"""
    print(f'Request: {self.request!r}')