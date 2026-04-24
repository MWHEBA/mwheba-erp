"""
Idempotency service for preventing duplicate operations.
Thread-safe implementation with proper database locking.
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from ..models import IdempotencyRecord, GovernanceContext
from ..exceptions import IdempotencyError, ConcurrencyError
from ..thread_safety import IdempotencyLock, monitor_operation

logger = logging.getLogger(__name__)


class IdempotencyService:
    """
    Service for managing idempotency across all governance operations.
    Ensures operations are not duplicated even under concurrent access.
    """
    
    @classmethod
    def check_and_record_operation(cls, operation_type: str, idempotency_key: str, 
                                 result_data: dict, user=None, expires_in_hours: int = 24):
        """
        Thread-safe method to check for existing operation or record new one.
        
        Args:
            operation_type: Type of operation (e.g., 'journal_entry', 'stock_movement')
            idempotency_key: Unique key for this operation
            result_data: Data to store as operation result
            user: User performing the operation (from context if not provided)
            expires_in_hours: Hours until idempotency record expires
            
        Returns:
            tuple: (is_duplicate, record, result_data)
                - is_duplicate: True if operation already exists
                - record: IdempotencyRecord instance
                - result_data: Result data (from existing record if duplicate)
        """
        # Get user from context if not provided
        if user is None:
            user = GovernanceContext.get_current_user()
            if user is None:
                raise IdempotencyError(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key,
                    context={'error': 'No user provided and none in context'}
                )
        
        # Use idempotency lock for thread safety
        with IdempotencyLock(operation_type, idempotency_key).acquire() as existing_record:
            if existing_record:
                # Operation already exists and is not expired
                logger.info(f"Duplicate operation detected: {operation_type}:{idempotency_key}")
                return True, existing_record, existing_record.result_data
            
            # Record new operation
            with monitor_operation(f"idempotency_{operation_type}"):
                is_duplicate, record = IdempotencyRecord.check_and_record(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key,
                    result_data=result_data,
                    user=user,
                    expires_in_hours=expires_in_hours
                )
                
                logger.info(f"Idempotency record created: {operation_type}:{idempotency_key}")
                return is_duplicate, record, result_data
    
    @classmethod
    def check_operation_exists(cls, operation_type: str, idempotency_key: str):
        """
        Check if operation already exists without creating new record.
        
        Returns:
            tuple: (exists, record, result_data)
        """
        try:
            record = IdempotencyRecord.objects.get(
                operation_type=operation_type,
                idempotency_key=idempotency_key
            )
            
            if record.is_expired():
                # Clean up expired record
                record.delete()
                return False, None, None
            
            return True, record, record.result_data
            
        except IdempotencyRecord.DoesNotExist:
            return False, None, None
    
    @classmethod
    def cleanup_expired_records(cls, batch_size: int = 1000, max_age_days: int = 30):
        """
        Clean up expired idempotency records with proper locking and batching.
        Should be run periodically as a maintenance task.
        
        Args:
            batch_size: Number of records to process in each batch
            max_age_days: Maximum age in days for records to keep (default 30 days)
            
        Returns:
            dict: Cleanup statistics including counts and any errors
        """
        from django.db import transaction
        from datetime import timedelta
        
        stats = {
            'total_deleted': 0,
            'batches_processed': 0,
            'errors': [],
            'start_time': timezone.now(),
            'end_time': None
        }
        
        try:
            with monitor_operation("idempotency_cleanup"):
                # Calculate cutoff dates
                now = timezone.now()
                expired_cutoff = now  # Records past their expires_at date
                old_cutoff = now - timedelta(days=max_age_days)  # Very old records
                
                # First pass: Delete clearly expired records
                expired_count = cls._cleanup_expired_batch(expired_cutoff, batch_size)
                stats['total_deleted'] += expired_count
                stats['batches_processed'] += 1
                
                # Second pass: Delete very old records regardless of expiry
                old_count = cls._cleanup_old_batch(old_cutoff, batch_size)
                stats['total_deleted'] += old_count
                stats['batches_processed'] += 1
                
                logger.info(f"Idempotency cleanup completed: {stats['total_deleted']} records deleted")
                
        except Exception as e:
            error_msg = f"Error during idempotency cleanup: {str(e)}"
            logger.error(error_msg)
            stats['errors'].append(error_msg)
        
        finally:
            stats['end_time'] = timezone.now()
            stats['duration'] = (stats['end_time'] - stats['start_time']).total_seconds()
        
        return stats
    
    @classmethod
    def _cleanup_expired_batch(cls, cutoff_time, batch_size):
        """Clean up records that have passed their expiry time"""
        from django.db import transaction
        
        deleted_count = 0
        
        with transaction.atomic():
            # Get expired records in batches to avoid long-running transactions
            expired_ids = list(
                IdempotencyRecord.objects.filter(
                    expires_at__lt=cutoff_time
                ).values_list('id', flat=True)[:batch_size]
            )
            
            if expired_ids:
                # Delete in smaller chunks to avoid lock contention
                chunk_size = min(100, len(expired_ids))
                for i in range(0, len(expired_ids), chunk_size):
                    chunk_ids = expired_ids[i:i + chunk_size]
                    deleted, _ = IdempotencyRecord.objects.filter(
                        id__in=chunk_ids
                    ).delete()
                    deleted_count += deleted
        
        return deleted_count
    
    @classmethod
    def _cleanup_old_batch(cls, cutoff_time, batch_size):
        """Clean up very old records regardless of expiry"""
        from django.db import transaction
        
        deleted_count = 0
        
        with transaction.atomic():
            # Get very old records
            old_ids = list(
                IdempotencyRecord.objects.filter(
                    created_at__lt=cutoff_time
                ).values_list('id', flat=True)[:batch_size]
            )
            
            if old_ids:
                # Delete in smaller chunks
                chunk_size = min(100, len(old_ids))
                for i in range(0, len(old_ids), chunk_size):
                    chunk_ids = old_ids[i:i + chunk_size]
                    deleted, _ = IdempotencyRecord.objects.filter(
                        id__in=chunk_ids
                    ).delete()
                    deleted_count += deleted
        
        return deleted_count
    
    @classmethod
    def generate_key(cls, *components):
        """
        Generate standardized idempotency key from components.
        
        Args:
            *components: Key components to join
            
        Returns:
            str: Formatted idempotency key
        """
        # Filter out None values and convert to strings
        clean_components = [str(c) for c in components if c is not None]
        return ':'.join(clean_components)
    
    @classmethod
    def generate_journal_entry_key(cls, source_module: str, source_model: str, 
                                 source_id: int, event_type: str = 'create'):
        """
        Generate standardized idempotency key for journal entries.
        
        Format: JE:{source_module}:{source_model}:{source_id}:{event_type}
        """
        return cls.generate_key('JE', source_module, source_model, source_id, event_type)
    
    @classmethod
    def generate_stock_movement_key(cls, product_id: int, movement_type: str, 
                                  reference_id: int = None, event_type: str = 'create'):
        """
        Generate standardized idempotency key for stock movements.
        
        Format: SM:{product_id}:{movement_type}:{reference_id}:{event_type}
        """
        return cls.generate_key('SM', product_id, movement_type, reference_id, event_type)
    
    @classmethod
    def generate_payment_key(cls, payment_type: str, source_id: int, 
                           amount: str, event_type: str = 'create'):
        """
        Generate standardized idempotency key for payments.
        
        Format: PAY:{payment_type}:{source_id}:{amount}:{event_type}
        """
        return cls.generate_key('PAY', payment_type, source_id, amount, event_type)
    
    @classmethod
    def generate_customer_payment_key(cls, customer_id: int, amount: str,
                                    payment_date: str, event_type: str = 'create'):
        """
        Generate standardized idempotency key for customer payments.
        
        Format: CP:{customer_id}:{amount}:{payment_date}:{event_type}
        """
        return cls.generate_key('CP', customer_id, amount, payment_date, event_type)
    
    @classmethod
    def generate_stock_adjustment_key(cls, product_id: int, warehouse_id: int, 
                                    adjustment_type: str, reference: str = None):
        """
        Generate standardized idempotency key for stock adjustments.
        
        Format: SA:{product_id}:{warehouse_id}:{adjustment_type}:{reference}
        """
        return cls.generate_key('SA', product_id, warehouse_id, adjustment_type, reference)
    
    @classmethod
    def generate_accounting_entry_key(cls, entry_type: str, source_module: str, 
                                    source_model: str, source_id: int, 
                                    amount: str = None):
        """
        Generate standardized idempotency key for accounting entries.
        
        Format: AE:{entry_type}:{source_module}:{source_model}:{source_id}:{amount}
        """
        return cls.generate_key('AE', entry_type, source_module, source_model, source_id, amount)
    
    # ============================================================================
    # PAYROLL-SPECIFIC IDEMPOTENCY KEY GENERATORS
    # ============================================================================
    
    @classmethod
    def generate_payroll_key(cls, employee_id: int, month: str, 
                           event_type: str = 'create'):
        """
        Generate standardized idempotency key for payroll operations.
        
        Format: PAYROLL:{employee_id}:{month}:{event_type}
        
        Args:
            employee_id: ID of the employee
            month: Month in YYYY-MM format
            event_type: Type of operation (create, calculate, approve, pay)
        """
        return cls.generate_key('PAYROLL', employee_id, month, event_type)
    
    @classmethod
    def generate_payroll_line_key(cls, payroll_id: int, component_code: str, 
                                event_type: str = 'create'):
        """
        Generate standardized idempotency key for payroll line operations.
        
        Format: PAYROLL_LINE:{payroll_id}:{component_code}:{event_type}
        """
        return cls.generate_key('PAYROLL_LINE', payroll_id, component_code, event_type)
    
    @classmethod
    def generate_payroll_payment_key(cls, payment_reference: str, 
                                   event_type: str = 'create'):
        """
        Generate standardized idempotency key for payroll payment operations.
        
        Format: PAYROLL_PAYMENT:{payment_reference}:{event_type}
        
        Args:
            payment_reference: Unique payment reference
            event_type: Type of operation (create, process, complete, cancel)
        """
        return cls.generate_key('PAYROLL_PAYMENT', payment_reference, event_type)
    
    @classmethod
    def generate_payroll_batch_key(cls, batch_id: str, month: str, 
                                 event_type: str = 'process'):
        """
        Generate standardized idempotency key for batch payroll operations.
        
        Format: PAYROLL_BATCH:{batch_id}:{month}:{event_type}
        
        Args:
            batch_id: Unique batch identifier
            month: Month in YYYY-MM format
            event_type: Type of operation (process, approve, pay)
        """
        return cls.generate_key('PAYROLL_BATCH', batch_id, month, event_type)
    
    @classmethod
    def generate_advance_key(cls, employee_id: int, amount: str, 
                           request_date: str, event_type: str = 'create'):
        """
        Generate standardized idempotency key for advance operations.
        
        Format: ADVANCE:{employee_id}:{amount}:{request_date}:{event_type}
        
        Args:
            employee_id: ID of the employee
            amount: Advance amount
            request_date: Request date in YYYY-MM-DD format
            event_type: Type of operation (create, approve, pay, deduct)
        """
        return cls.generate_key('ADVANCE', employee_id, amount, request_date, event_type)
    
    @classmethod
    def generate_advance_installment_key(cls, advance_id: int, month: str, 
                                       event_type: str = 'deduct'):
        """
        Generate standardized idempotency key for advance installment operations.
        
        Format: ADVANCE_INSTALLMENT:{advance_id}:{month}:{event_type}
        
        Args:
            advance_id: ID of the advance
            month: Month in YYYY-MM format
            event_type: Type of operation (deduct, reverse)
        """
        return cls.generate_key('ADVANCE_INSTALLMENT', advance_id, month, event_type)
    
    @classmethod
    def generate_payroll_journal_entry_key(cls, payroll_id: int, 
                                         event_type: str = 'create'):
        """
        Generate standardized idempotency key for payroll journal entries.
        
        Format: PAYROLL_JE:{payroll_id}:{event_type}
        
        Args:
            payroll_id: ID of the payroll
            event_type: Type of operation (create, reverse)
        """
        return cls.generate_key('PAYROLL_JE', payroll_id, event_type)
    
    @classmethod
    def generate_salary_component_key(cls, employee_id: int, component_code: str, 
                                    effective_date: str, event_type: str = 'create'):
        """
        Generate standardized idempotency key for salary component operations.
        
        Format: SALARY_COMPONENT:{employee_id}:{component_code}:{effective_date}:{event_type}
        
        Args:
            employee_id: ID of the employee
            component_code: Component code (e.g., BASIC_SALARY, ALLOWANCE)
            effective_date: Effective date in YYYY-MM-DD format
            event_type: Type of operation (create, update, terminate)
        """
        return cls.generate_key('SALARY_COMPONENT', employee_id, component_code, effective_date, event_type)
    
    @classmethod
    def get_operation_statistics(cls):
        """
        Get comprehensive statistics about idempotency operations.
        
        Returns:
            dict: Detailed statistics including counts, performance metrics, etc.
        """
        from django.db.models import Count, Q, Avg
        from datetime import timedelta
        
        stats = {}
        now = timezone.now()
        
        # Basic counts
        total_records = IdempotencyRecord.objects.count()
        stats['total_records'] = total_records
        
        if total_records == 0:
            return stats
        
        # Count by operation type
        operation_counts = IdempotencyRecord.objects.values('operation_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        stats['by_operation_type'] = {
            item['operation_type']: item['count'] 
            for item in operation_counts
        }
        
        # Count expired vs active
        stats['expired_count'] = IdempotencyRecord.objects.filter(
            expires_at__lt=now
        ).count()
        
        stats['active_count'] = IdempotencyRecord.objects.filter(
            expires_at__gte=now
        ).count()
        
        # Recent activity (last 24 hours)
        recent_cutoff = now - timedelta(hours=24)
        stats['recent_operations'] = IdempotencyRecord.objects.filter(
            created_at__gte=recent_cutoff
        ).count()
        
        # Weekly activity (last 7 days)
        week_cutoff = now - timedelta(days=7)
        stats['weekly_operations'] = IdempotencyRecord.objects.filter(
            created_at__gte=week_cutoff
        ).count()
        
        # Average record age (handle SQLite limitation)
        try:
            # For SQLite, we can't use Avg on datetime fields, so we'll calculate manually
            from django.db import connection
            
            if connection.vendor == 'sqlite':
                # Manual calculation for SQLite
                records = IdempotencyRecord.objects.values_list('created_at', flat=True)
                if records:
                    total_seconds = sum((now - record).total_seconds() for record in records)
                    avg_seconds = total_seconds / len(records)
                    stats['average_age_hours'] = avg_seconds / 3600
            else:
                # Use database aggregation for other databases
                avg_age = IdempotencyRecord.objects.aggregate(
                    avg_age=Avg('created_at')
                )['avg_age']
                
                if avg_age:
                    stats['average_age_hours'] = (now - avg_age).total_seconds() / 3600
        except Exception as e:
            logger.warning(f"Could not calculate average age: {e}")
            stats['average_age_hours'] = None
        
        # Records by user (top 10)
        user_counts = IdempotencyRecord.objects.values(
            'created_by__username'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        stats['top_users'] = {
            item['created_by__username'] or 'System': item['count']
            for item in user_counts
        }
        
        # Cleanup recommendations
        old_cutoff = now - timedelta(days=30)
        old_records_count = IdempotencyRecord.objects.filter(
            created_at__lt=old_cutoff
        ).count()
        
        stats['cleanup_recommendations'] = {
            'old_records_count': old_records_count,
            'should_cleanup': old_records_count > 1000,
            'estimated_cleanup_time': f"{old_records_count // 1000 + 1} minutes"
        }
        
        return stats
    
    @classmethod
    def get_health_status(cls):
        """
        Get health status of the idempotency system.
        
        Returns:
            dict: Health status with recommendations
        """
        stats = cls.get_operation_statistics()
        
        health = {
            'status': 'healthy',
            'issues': [],
            'recommendations': [],
            'metrics': {
                'total_records': stats.get('total_records', 0),
                'expired_ratio': 0,
                'recent_activity': stats.get('recent_operations', 0)
            }
        }
        
        total = stats.get('total_records', 0)
        expired = stats.get('expired_count', 0)
        
        if total > 0:
            expired_ratio = expired / total
            health['metrics']['expired_ratio'] = expired_ratio
            
            # Check for issues
            if expired_ratio > 0.5:
                health['status'] = 'warning'
                health['issues'].append('High ratio of expired records')
                health['recommendations'].append('Run cleanup_expired_records()')
            
            if total > 10000:
                health['status'] = 'warning'
                health['issues'].append('Large number of idempotency records')
                health['recommendations'].append('Consider more frequent cleanup')
            
            if stats.get('recent_operations', 0) == 0:
                health['issues'].append('No recent idempotency operations')
        
        return health