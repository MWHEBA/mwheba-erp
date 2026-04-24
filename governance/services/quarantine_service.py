"""
Quarantine service for isolating suspicious or corrupted data.
Provides safe isolation and resolution mechanisms.
"""

import logging
from django.db import transaction
from django.utils import timezone
from ..models import QuarantineRecord, GovernanceContext
from ..thread_safety import monitor_operation
from ..exceptions import QuarantineError

logger = logging.getLogger(__name__)


class QuarantineService:
    """
    Service for managing data quarantine operations.
    Isolates suspicious data and provides resolution mechanisms.
    """
    
    @classmethod
    def quarantine_data(cls, model_name: str, object_id: int, corruption_type: str,
                       reason: str, original_data: dict, user=None, **context):
        """
        Quarantine suspicious or corrupted data.
        
        Args:
            model_name: Name of the model containing corrupted data
            object_id: ID of the corrupted object
            corruption_type: Type of corruption detected
            reason: Detailed reason for quarantine
            original_data: Original data before quarantine
            user: User or system that initiated quarantine
            **context: Additional context information
            
        Returns:
            QuarantineRecord: Created quarantine record
        """
        # Get user from context if not provided
        if user is None:
            user = GovernanceContext.get_current_user()
            if user is None:
                raise QuarantineError(
                    model=model_name,
                    object_id=object_id,
                    corruption_type=corruption_type,
                    context={'error': 'No user provided for quarantine operation'}
                )
        
        with monitor_operation("quarantine_data"):
            try:
                with transaction.atomic():
                    # Check if already quarantined
                    existing = QuarantineRecord.objects.filter(
                        model_name=model_name,
                        object_id=object_id,
                        corruption_type=corruption_type,
                        status__in=['QUARANTINED', 'UNDER_REVIEW']
                    ).first()
                    
                    if existing:
                        logger.warning(f"Data already quarantined: {model_name}#{object_id}")
                        return existing
                    
                    # Create quarantine record
                    quarantine_record = QuarantineRecord.objects.create(
                        model_name=model_name,
                        object_id=object_id,
                        corruption_type=corruption_type,
                        original_data=original_data,
                        quarantine_reason=reason,
                        quarantined_by=user,
                        status='QUARANTINED'
                    )
                    
                    # Log the quarantine action
                    from .audit_service import AuditService
                    AuditService.log_operation(
                        model_name='QuarantineRecord',
                        object_id=quarantine_record.id,
                        operation='CREATE',
                        source_service='QuarantineService',
                        user=user,
                        after_data={
                            'quarantined_model': model_name,
                            'quarantined_object_id': object_id,
                            'corruption_type': corruption_type
                        },
                        **context
                    )
                    
                    logger.info(f"Data quarantined: {quarantine_record}")
                    return quarantine_record
                    
            except Exception as e:
                logger.error(f"Failed to quarantine data: {e}", exc_info=True)
                raise QuarantineError(
                    model=model_name,
                    object_id=object_id,
                    corruption_type=corruption_type,
                    context={'error': str(e)}
                )
    
    @classmethod
    def resolve_quarantine(cls, quarantine_id: int, resolution_notes: str, 
                          user=None, **context):
        """
        Resolve a quarantine record.
        
        Args:
            quarantine_id: ID of the quarantine record
            resolution_notes: Notes about the resolution
            user: User resolving the quarantine
            **context: Additional context
            
        Returns:
            QuarantineRecord: Updated quarantine record
        """
        # Get user from context if not provided
        if user is None:
            user = GovernanceContext.get_current_user()
            if user is None:
                raise QuarantineError(
                    model='QuarantineRecord',
                    object_id=quarantine_id,
                    corruption_type='RESOLUTION',
                    context={'error': 'No user provided for resolution'}
                )
        
        with monitor_operation("resolve_quarantine"):
            try:
                with transaction.atomic():
                    quarantine_record = QuarantineRecord.objects.select_for_update().get(
                        id=quarantine_id
                    )
                    
                    if quarantine_record.status == 'RESOLVED':
                        logger.warning(f"Quarantine already resolved: {quarantine_id}")
                        return quarantine_record
                    
                    # Resolve the quarantine
                    quarantine_record.resolve(user, resolution_notes)
                    
                    logger.info(f"Quarantine resolved: {quarantine_record}")
                    return quarantine_record
                    
            except QuarantineRecord.DoesNotExist:
                raise QuarantineError(
                    model='QuarantineRecord',
                    object_id=quarantine_id,
                    corruption_type='NOT_FOUND',
                    context={'error': 'Quarantine record not found'}
                )
            except Exception as e:
                logger.error(f"Failed to resolve quarantine: {e}", exc_info=True)
                raise QuarantineError(
                    model='QuarantineRecord',
                    object_id=quarantine_id,
                    corruption_type='RESOLUTION_FAILED',
                    context={'error': str(e)}
                )
    
    @classmethod
    def mark_under_review(cls, quarantine_id: int, user=None):
        """
        Mark quarantine record as under review.
        
        Args:
            quarantine_id: ID of the quarantine record
            user: User marking for review
        """
        with monitor_operation("quarantine_review"):
            try:
                with transaction.atomic():
                    quarantine_record = QuarantineRecord.objects.select_for_update().get(
                        id=quarantine_id
                    )
                    
                    quarantine_record.status = 'UNDER_REVIEW'
                    quarantine_record.save()
                    
                    # Log the status change
                    from .audit_service import AuditService
                    AuditService.log_operation(
                        model_name='QuarantineRecord',
                        object_id=quarantine_record.id,
                        operation='UPDATE',
                        source_service='QuarantineService',
                        user=user,
                        before_data={'status': 'QUARANTINED'},
                        after_data={'status': 'UNDER_REVIEW'}
                    )
                    
                    logger.info(f"Quarantine marked for review: {quarantine_record}")
                    return quarantine_record
                    
            except QuarantineRecord.DoesNotExist:
                raise QuarantineError(
                    model='QuarantineRecord',
                    object_id=quarantine_id,
                    corruption_type='NOT_FOUND'
                )
    
    @classmethod
    def get_quarantined_objects(cls, model_name: str = None, corruption_type: str = None,
                              status: str = None, limit: int = 100):
        """
        Get quarantined objects with optional filtering.
        
        Args:
            model_name: Filter by model name
            corruption_type: Filter by corruption type
            status: Filter by status
            limit: Maximum number of records
            
        Returns:
            QuerySet: Quarantine records matching criteria
        """
        queryset = QuarantineRecord.objects.all()
        
        if model_name:
            queryset = queryset.filter(model_name=model_name)
        
        if corruption_type:
            queryset = queryset.filter(corruption_type=corruption_type)
        
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset.order_by('-quarantined_at')[:limit]
    
    @classmethod
    def get_corruption_summary(cls):
        """
        Get summary of corruption types and counts.
        
        Returns:
            dict: Summary of quarantined data
        """
        from django.db.models import Count
        
        summary = {}
        
        # Count by corruption type
        corruption_counts = QuarantineRecord.objects.values('corruption_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        summary['by_corruption_type'] = {
            item['corruption_type']: item['count'] 
            for item in corruption_counts
        }
        
        # Count by model
        model_counts = QuarantineRecord.objects.values('model_name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        summary['by_model'] = {
            item['model_name']: item['count'] 
            for item in model_counts
        }
        
        # Count by status
        status_counts = QuarantineRecord.objects.values('status').annotate(
            count=Count('id')
        )
        
        summary['by_status'] = {
            item['status']: item['count'] 
            for item in status_counts
        }
        
        summary['total_quarantined'] = QuarantineRecord.objects.count()
        
        # Recent quarantines (last 24 hours)
        recent_cutoff = timezone.now() - timezone.timedelta(hours=24)
        summary['recent_quarantines'] = QuarantineRecord.objects.filter(
            quarantined_at__gte=recent_cutoff
        ).count()
        
        return summary
    
    @classmethod
    def check_object_quarantined(cls, model_name: str, object_id: int):
        """
        Check if an object is currently quarantined.
        
        Args:
            model_name: Name of the model
            object_id: ID of the object
            
        Returns:
            tuple: (is_quarantined, quarantine_records)
        """
        quarantine_records = QuarantineRecord.objects.filter(
            model_name=model_name,
            object_id=object_id,
            status__in=['QUARANTINED', 'UNDER_REVIEW']
        )
        
        return quarantine_records.exists(), list(quarantine_records)
    
    @classmethod
    def quarantine_orphaned_journal_entry(cls, entry_id: int, user=None):
        """
        Quarantine an orphaned journal entry.
        
        Args:
            entry_id: ID of the journal entry
            user: User initiating quarantine
        """
        return cls.quarantine_data(
            model_name='JournalEntry',
            object_id=entry_id,
            corruption_type='ORPHANED_ENTRY',
            reason='Journal entry has invalid or missing source linkage',
            original_data={'entry_id': entry_id},
            user=user
        )
    
    @classmethod
    def quarantine_negative_stock(cls, stock_id: int, current_quantity: float, user=None):
        """
        Quarantine negative stock record.
        
        Args:
            stock_id: ID of the stock record
            current_quantity: Current negative quantity
            user: User initiating quarantine
        """
        return cls.quarantine_data(
            model_name='Stock',
            object_id=stock_id,
            corruption_type='NEGATIVE_STOCK',
            reason=f'Stock quantity is negative: {current_quantity}',
            original_data={'stock_id': stock_id, 'quantity': current_quantity},
            user=user
        )
    
    @classmethod
    def quarantine_unbalanced_entry(cls, entry_id: int, debit_total: float, 
                                   credit_total: float, user=None):
        """
        Quarantine unbalanced journal entry.
        
        Args:
            entry_id: ID of the journal entry
            debit_total: Total debit amount
            credit_total: Total credit amount
            user: User initiating quarantine
        """
        return cls.quarantine_data(
            model_name='JournalEntry',
            object_id=entry_id,
            corruption_type='UNBALANCED_ENTRY',
            reason=f'Journal entry is unbalanced: debits={debit_total}, credits={credit_total}',
            original_data={
                'entry_id': entry_id,
                'debit_total': debit_total,
                'credit_total': credit_total
            },
            user=user
        )