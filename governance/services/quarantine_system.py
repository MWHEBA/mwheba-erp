"""
QuarantineSystem - Comprehensive Thread-Safe Quarantine Management

This system implements Task 16 of the code governance system - a comprehensive
quarantine system for isolating suspicious data with thread-safe operations,
management capabilities, and resolution tools.

Key Features:
- Thread-safe quarantine storage and management
- Suspicious data isolation mechanisms
- Comprehensive quarantine reporting
- Resolution tools with audit trails
- Integration with RepairService and existing QuarantineService
- Batch operations for efficiency
- Advanced search and filtering capabilities
"""

import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from decimal import Decimal
from datetime import timedelta, datetime
from django.db import transaction, connection
from django.apps import apps
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Avg, Max, Min
from django.core.paginator import Paginator

from ..models import QuarantineRecord, AuditTrail, GovernanceContext
from ..thread_safety import (
    monitor_operation, DatabaseLockManager, ThreadSafeOperationMixin,
    retry_on_concurrency_error
)
from ..exceptions import QuarantineError, ConcurrencyError, ValidationError as GovValidationError
from .quarantine_service import QuarantineService
from .audit_service import AuditService

User = get_user_model()
logger = logging.getLogger(__name__)


class QuarantineStorage:
    """
    Thread-safe storage manager for quarantine operations.
    Handles concurrent access to quarantine records with proper locking.
    """
    
    @staticmethod
    @retry_on_concurrency_error(max_retries=3)
    def store_quarantine_record(model_name: str, object_id: int, corruption_type: str,
                               reason: str, original_data: dict, user, **context) -> QuarantineRecord:
        """
        Thread-safe storage of quarantine record.
        
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
        with monitor_operation("store_quarantine_record"):
            with DatabaseLockManager.atomic_operation():
                # Check for existing quarantine with proper locking
                existing_queryset = QuarantineRecord.objects.filter(
                    model_name=model_name,
                    object_id=object_id,
                    corruption_type=corruption_type,
                    status__in=['QUARANTINED', 'UNDER_REVIEW']
                )
                
                existing_queryset = DatabaseLockManager.select_for_update_if_supported(
                    existing_queryset
                )
                
                existing = existing_queryset.first()
                if existing:
                    logger.info(f"Quarantine record already exists: {existing.id}")
                    return existing
                
                # Create new quarantine record
                quarantine_record = QuarantineRecord.objects.create(
                    model_name=model_name,
                    object_id=object_id,
                    corruption_type=corruption_type,
                    original_data=original_data,
                    quarantine_reason=reason,
                    quarantined_by=user,
                    status='QUARANTINED'
                )
                
                logger.info(f"Quarantine record created: {quarantine_record.id}")
                return quarantine_record
    
    @staticmethod
    @retry_on_concurrency_error(max_retries=3)
    def update_quarantine_status(quarantine_id: int, new_status: str, 
                                user, notes: str = "") -> QuarantineRecord:
        """
        Thread-safe update of quarantine record status.
        
        Args:
            quarantine_id: ID of the quarantine record
            new_status: New status to set
            user: User making the update
            notes: Optional notes about the update
            
        Returns:
            QuarantineRecord: Updated quarantine record
        """
        with monitor_operation("update_quarantine_status"):
            with DatabaseLockManager.atomic_operation():
                # Get record with lock
                quarantine_record = DatabaseLockManager.get_with_lock(
                    QuarantineRecord, id=quarantine_id
                )
                
                old_status = quarantine_record.status
                quarantine_record.status = new_status
                
                if new_status == 'RESOLVED':
                    quarantine_record.resolved_at = timezone.now()
                    quarantine_record.resolved_by = user
                    quarantine_record.resolution_notes = notes
                
                quarantine_record.save()
                
                # Create audit trail
                AuditService.log_operation(
                    model_name='QuarantineRecord',
                    object_id=quarantine_record.id,
                    operation='UPDATE',
                    source_service='QuarantineSystem',
                    user=user,
                    before_data={'status': old_status},
                    after_data={'status': new_status, 'notes': notes}
                )
                
                logger.info(f"Quarantine status updated: {quarantine_id} {old_status} -> {new_status}")
                return quarantine_record
    
    @staticmethod
    def batch_store_quarantine_records(quarantine_data: List[Dict], user) -> List[QuarantineRecord]:
        """
        Thread-safe batch storage of multiple quarantine records.
        
        Args:
            quarantine_data: List of quarantine data dictionaries
            user: User initiating the batch operation
            
        Returns:
            List[QuarantineRecord]: Created quarantine records
        """
        created_records = []
        
        with monitor_operation("batch_store_quarantine"):
            for data in quarantine_data:
                try:
                    record = QuarantineStorage.store_quarantine_record(
                        model_name=data['model_name'],
                        object_id=data['object_id'],
                        corruption_type=data['corruption_type'],
                        reason=data['reason'],
                        original_data=data['original_data'],
                        user=user,
                        **data.get('context', {})
                    )
                    created_records.append(record)
                except Exception as e:
                    logger.error(f"Failed to store quarantine record: {e}")
                    # Continue with other records
                    continue
        
        logger.info(f"Batch quarantine completed: {len(created_records)}/{len(quarantine_data)} records created")
        return created_records


class QuarantineManager(ThreadSafeOperationMixin):
    """
    Comprehensive quarantine management with thread-safe operations.
    Provides advanced search, filtering, and batch operations.
    """
    
    def __init__(self):
        self.storage = QuarantineStorage()
    
    @monitor_operation("search_quarantine_records")
    def search_quarantine_records(self, filters: Dict = None, page: int = 1, 
                                 page_size: int = 50) -> Dict:
        """
        Advanced search and filtering of quarantine records.
        
        Args:
            filters: Dictionary of search filters
            page: Page number for pagination
            page_size: Number of records per page
            
        Returns:
            Dict: Search results with pagination info
        """
        with self.thread_safe_operation("search_quarantine"):
            queryset = QuarantineRecord.objects.all()
            
            # Apply filters
            if filters:
                if 'model_name' in filters:
                    queryset = queryset.filter(model_name=filters['model_name'])
                
                if 'corruption_type' in filters:
                    queryset = queryset.filter(corruption_type=filters['corruption_type'])
                
                if 'status' in filters:
                    if isinstance(filters['status'], list):
                        queryset = queryset.filter(status__in=filters['status'])
                    else:
                        queryset = queryset.filter(status=filters['status'])
                
                if 'quarantined_by' in filters:
                    queryset = queryset.filter(quarantined_by=filters['quarantined_by'])
                
                if 'date_from' in filters:
                    queryset = queryset.filter(quarantined_at__gte=filters['date_from'])
                
                if 'date_to' in filters:
                    queryset = queryset.filter(quarantined_at__lte=filters['date_to'])
                
                if 'search_text' in filters:
                    search_text = filters['search_text']
                    queryset = queryset.filter(
                        Q(quarantine_reason__icontains=search_text) |
                        Q(resolution_notes__icontains=search_text)
                    )
            
            # Order by most recent first
            queryset = queryset.order_by('-quarantined_at')
            
            # Paginate results
            paginator = Paginator(queryset, page_size)
            page_obj = paginator.get_page(page)
            
            return {
                'records': list(page_obj.object_list),
                'pagination': {
                    'current_page': page,
                    'total_pages': paginator.num_pages,
                    'total_records': paginator.count,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous(),
                    'page_size': page_size
                }
            }
    
    @monitor_operation("get_quarantine_statistics")
    def get_quarantine_statistics(self, date_from: datetime = None, 
                                 date_to: datetime = None) -> Dict:
        """
        Get comprehensive quarantine statistics.
        
        Args:
            date_from: Start date for statistics
            date_to: End date for statistics
            
        Returns:
            Dict: Comprehensive statistics
        """
        with self.thread_safe_operation("quarantine_statistics"):
            queryset = QuarantineRecord.objects.all()
            
            # Apply date filters
            if date_from:
                queryset = queryset.filter(quarantined_at__gte=date_from)
            if date_to:
                queryset = queryset.filter(quarantined_at__lte=date_to)
            
            # Basic counts
            total_quarantined = queryset.count()
            
            # Status breakdown
            status_counts = queryset.values('status').annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Corruption type breakdown
            corruption_counts = queryset.values('corruption_type').annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Model breakdown
            model_counts = queryset.values('model_name').annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Time-based statistics
            recent_24h = queryset.filter(
                quarantined_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
            
            recent_7d = queryset.filter(
                quarantined_at__gte=timezone.now() - timedelta(days=7)
            ).count()
            
            # Resolution statistics
            resolved_count = queryset.filter(status='RESOLVED').count()
            resolution_rate = (resolved_count / total_quarantined * 100) if total_quarantined > 0 else 0
            
            # Average resolution time for resolved records
            resolved_records = queryset.filter(
                status='RESOLVED',
                resolved_at__isnull=False
            )
            
            avg_resolution_time = None
            if resolved_records.exists():
                resolution_times = []
                for record in resolved_records:
                    if record.resolved_at and record.quarantined_at:
                        delta = record.resolved_at - record.quarantined_at
                        resolution_times.append(delta.total_seconds())
                
                if resolution_times:
                    avg_resolution_time = sum(resolution_times) / len(resolution_times)
            
            return {
                'summary': {
                    'total_quarantined': total_quarantined,
                    'recent_24h': recent_24h,
                    'recent_7d': recent_7d,
                    'resolved_count': resolved_count,
                    'resolution_rate': round(resolution_rate, 2),
                    'avg_resolution_time_seconds': avg_resolution_time
                },
                'by_status': {item['status']: item['count'] for item in status_counts},
                'by_corruption_type': {item['corruption_type']: item['count'] for item in corruption_counts},
                'by_model': {item['model_name']: item['count'] for item in model_counts},
                'date_range': {
                    'from': date_from.isoformat() if date_from else None,
                    'to': date_to.isoformat() if date_to else None
                }
            }
    
    @monitor_operation("batch_update_quarantine")
    def batch_update_quarantine_status(self, quarantine_ids: List[int], 
                                      new_status: str, user, notes: str = "") -> Dict:
        """
        Batch update multiple quarantine records.
        
        Args:
            quarantine_ids: List of quarantine record IDs
            new_status: New status to set
            user: User making the updates
            notes: Optional notes about the updates
            
        Returns:
            Dict: Results of batch update operation
        """
        results = {
            'updated': [],
            'failed': [],
            'total_requested': len(quarantine_ids)
        }
        
        with self.thread_safe_operation("batch_update"):
            for quarantine_id in quarantine_ids:
                try:
                    updated_record = QuarantineStorage.update_quarantine_status(
                        quarantine_id=quarantine_id,
                        new_status=new_status,
                        user=user,
                        notes=notes
                    )
                    results['updated'].append({
                        'id': updated_record.id,
                        'model_name': updated_record.model_name,
                        'object_id': updated_record.object_id,
                        'new_status': new_status
                    })
                except Exception as e:
                    logger.error(f"Failed to update quarantine {quarantine_id}: {e}")
                    results['failed'].append({
                        'id': quarantine_id,
                        'error': str(e)
                    })
        
        logger.info(f"Batch update completed: {len(results['updated'])}/{len(quarantine_ids)} updated")
        return results
    
    @monitor_operation("get_quarantine_trends")
    def get_quarantine_trends(self, days: int = 30) -> Dict:
        """
        Get quarantine trends over time.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict: Trend analysis data
        """
        with self.thread_safe_operation("quarantine_trends"):
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)
            
            # Daily quarantine counts
            from django.db.models import Count
            from django.db.models.functions import TruncDate
            
            daily_counts = QuarantineRecord.objects.filter(
                quarantined_at__gte=start_date,
                quarantined_at__lte=end_date
            ).annotate(
                date=TruncDate('quarantined_at')
            ).values('date').annotate(
                count=Count('id')
            ).order_by('date')
            
            # Corruption type trends
            corruption_trends = {}
            for corruption_type in QuarantineRecord.objects.values_list('corruption_type', flat=True).distinct():
                trend_data = QuarantineRecord.objects.filter(
                    corruption_type=corruption_type,
                    quarantined_at__gte=start_date,
                    quarantined_at__lte=end_date
                ).annotate(
                    date=TruncDate('quarantined_at')
                ).values('date').annotate(
                    count=Count('id')
                ).order_by('date')
                
                corruption_trends[corruption_type] = list(trend_data)
            
            return {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': days
                },
                'daily_counts': list(daily_counts),
                'corruption_type_trends': corruption_trends
            }


class QuarantineReporter:
    """
    Comprehensive reporting tools for quarantine system.
    Generates detailed reports for analysis and decision making.
    """
    
    def __init__(self):
        self.manager = QuarantineManager()
    
    @monitor_operation("generate_quarantine_report")
    def generate_comprehensive_report(self, report_type: str = 'full', 
                                    filters: Dict = None) -> Dict:
        """
        Generate comprehensive quarantine report.
        
        Args:
            report_type: Type of report ('full', 'summary', 'trends')
            filters: Optional filters for the report
            
        Returns:
            Dict: Comprehensive report data
        """
        report = {
            'report_type': report_type,
            'generated_at': timezone.now().isoformat(),
            'filters_applied': filters or {},
            'data': {}
        }
        
        if report_type in ['full', 'summary']:
            # Get statistics
            stats = self.manager.get_quarantine_statistics()
            report['data']['statistics'] = stats
            
            # Get recent quarantines
            recent_search = self.manager.search_quarantine_records(
                filters={'date_from': timezone.now() - timedelta(days=7)},
                page_size=100
            )
            report['data']['recent_quarantines'] = {
                'count': len(recent_search['records']),
                'records': [self._serialize_quarantine_record(r) for r in recent_search['records'][:10]]
            }
        
        if report_type in ['full', 'trends']:
            # Get trends
            trends = self.manager.get_quarantine_trends(days=30)
            report['data']['trends'] = trends
        
        if report_type == 'full':
            # Get detailed breakdown by corruption type
            corruption_details = {}
            for corruption_type in QuarantineRecord.objects.values_list('corruption_type', flat=True).distinct():
                type_records = self.manager.search_quarantine_records(
                    filters={'corruption_type': corruption_type},
                    page_size=10
                )
                corruption_details[corruption_type] = {
                    'total_count': type_records['pagination']['total_records'],
                    'sample_records': [self._serialize_quarantine_record(r) for r in type_records['records']]
                }
            
            report['data']['corruption_type_details'] = corruption_details
            
            # Get resolution analysis
            report['data']['resolution_analysis'] = self._analyze_resolution_patterns()
        
        return report
    
    def _serialize_quarantine_record(self, record: QuarantineRecord) -> Dict:
        """Serialize quarantine record for reporting"""
        return {
            'id': record.id,
            'model_name': record.model_name,
            'object_id': record.object_id,
            'corruption_type': record.corruption_type,
            'status': record.status,
            'quarantined_at': record.quarantined_at.isoformat(),
            'quarantined_by': record.quarantined_by.username if record.quarantined_by else None,
            'resolved_at': record.resolved_at.isoformat() if record.resolved_at else None,
            'resolved_by': record.resolved_by.username if record.resolved_by else None,
            'reason_summary': record.quarantine_reason[:100] + '...' if len(record.quarantine_reason) > 100 else record.quarantine_reason
        }
    
    def _analyze_resolution_patterns(self) -> Dict:
        """Analyze resolution patterns for insights"""
        resolved_records = QuarantineRecord.objects.filter(status='RESOLVED')
        
        if not resolved_records.exists():
            return {'message': 'No resolved records for analysis'}
        
        # Resolution time analysis
        resolution_times = []
        for record in resolved_records:
            if record.resolved_at and record.quarantined_at:
                delta = record.resolved_at - record.quarantined_at
                resolution_times.append(delta.total_seconds())
        
        analysis = {}
        if resolution_times:
            analysis['resolution_time_stats'] = {
                'avg_seconds': sum(resolution_times) / len(resolution_times),
                'min_seconds': min(resolution_times),
                'max_seconds': max(resolution_times),
                'total_analyzed': len(resolution_times)
            }
        
        # Resolution by corruption type
        resolution_by_type = resolved_records.values('corruption_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        analysis['resolution_by_corruption_type'] = {
            item['corruption_type']: item['count'] 
            for item in resolution_by_type
        }
        
        return analysis


class QuarantineSystem(ThreadSafeOperationMixin):
    """
    Comprehensive QuarantineSystem implementation for Task 16.
    
    Provides thread-safe quarantine storage, management capabilities,
    reporting tools, and integration with RepairService.
    """
    
    def __init__(self):
        self.storage = QuarantineStorage()
        self.manager = QuarantineManager()
        self.reporter = QuarantineReporter()
        self.service = QuarantineService()  # Existing service for compatibility
    
    # Core quarantine operations
    
    @monitor_operation("quarantine_data")
    def quarantine_data(self, model_name: str, object_id: int, corruption_type: str,
                       reason: str, original_data: dict, user=None, **context) -> QuarantineRecord:
        """
        Quarantine suspicious or corrupted data with comprehensive logging.
        
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
        
        with self.thread_safe_operation("quarantine_data"):
            # Store quarantine record
            quarantine_record = self.storage.store_quarantine_record(
                model_name=model_name,
                object_id=object_id,
                corruption_type=corruption_type,
                reason=reason,
                original_data=original_data,
                user=user,
                **context
            )
            
            # Create comprehensive audit trail
            AuditService.log_operation(
                model_name='QuarantineRecord',
                object_id=quarantine_record.id,
                operation='CREATE',
                source_service='QuarantineSystem',
                user=user,
                after_data={
                    'quarantined_model': model_name,
                    'quarantined_object_id': object_id,
                    'corruption_type': corruption_type,
                    'quarantine_id': quarantine_record.id
                },
                **context
            )
            
            logger.info(f"Data quarantined by QuarantineSystem: {quarantine_record}")
            return quarantine_record
    
    @monitor_operation("resolve_quarantine")
    def resolve_quarantine(self, quarantine_id: int, resolution_notes: str, 
                          user=None, **context) -> QuarantineRecord:
        """
        Resolve a quarantine record with comprehensive audit trail.
        
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
        
        with self.thread_safe_operation("resolve_quarantine"):
            # Update quarantine status
            quarantine_record = self.storage.update_quarantine_status(
                quarantine_id=quarantine_id,
                new_status='RESOLVED',
                user=user,
                notes=resolution_notes
            )
            
            logger.info(f"Quarantine resolved by QuarantineSystem: {quarantine_record}")
            return quarantine_record
    
    # Batch operations
    
    def batch_quarantine_data(self, quarantine_data_list: List[Dict], user=None) -> Dict:
        """
        Batch quarantine multiple data items.
        
        Args:
            quarantine_data_list: List of quarantine data dictionaries
            user: User initiating the batch operation
            
        Returns:
            Dict: Results of batch operation
        """
        with self.thread_safe_operation("batch_quarantine"):
            created_records = self.storage.batch_store_quarantine_records(
                quarantine_data=quarantine_data_list,
                user=user
            )
            
            return {
                'success': True,
                'created_count': len(created_records),
                'requested_count': len(quarantine_data_list),
                'quarantine_ids': [r.id for r in created_records]
            }
    
    def batch_resolve_quarantine(self, quarantine_ids: List[int], 
                                resolution_notes: str, user=None) -> Dict:
        """
        Batch resolve multiple quarantine records.
        
        Args:
            quarantine_ids: List of quarantine record IDs
            resolution_notes: Notes about the resolution
            user: User resolving the quarantines
            
        Returns:
            Dict: Results of batch resolution
        """
        return self.manager.batch_update_quarantine_status(
            quarantine_ids=quarantine_ids,
            new_status='RESOLVED',
            user=user,
            notes=resolution_notes
        )
    
    # Search and reporting
    
    def search_quarantine_records(self, filters: Dict = None, page: int = 1, 
                                 page_size: int = 50) -> Dict:
        """
        Search quarantine records with advanced filtering.
        
        Args:
            filters: Dictionary of search filters
            page: Page number for pagination
            page_size: Number of records per page
            
        Returns:
            Dict: Search results with pagination info
        """
        return self.manager.search_quarantine_records(
            filters=filters,
            page=page,
            page_size=page_size
        )
    
    def get_quarantine_statistics(self, date_from: datetime = None, 
                                 date_to: datetime = None) -> Dict:
        """
        Get comprehensive quarantine statistics.
        
        Args:
            date_from: Start date for statistics
            date_to: End date for statistics
            
        Returns:
            Dict: Comprehensive statistics
        """
        return self.manager.get_quarantine_statistics(
            date_from=date_from,
            date_to=date_to
        )
    
    def generate_quarantine_report(self, report_type: str = 'full', 
                                  filters: Dict = None) -> Dict:
        """
        Generate comprehensive quarantine report.
        
        Args:
            report_type: Type of report ('full', 'summary', 'trends')
            filters: Optional filters for the report
            
        Returns:
            Dict: Comprehensive report data
        """
        return self.reporter.generate_comprehensive_report(
            report_type=report_type,
            filters=filters
        )
    
    # Integration with RepairService
    
    def quarantine_from_corruption_report(self, corruption_report, user=None) -> Dict:
        """
        Quarantine data based on corruption report from RepairService.
        
        Args:
            corruption_report: CorruptionReport from RepairService
            user: User initiating quarantine
            
        Returns:
            Dict: Results of quarantine operation
        """
        quarantine_data_list = []
        
        # Convert corruption report to quarantine data
        for corruption_type, data in corruption_report.corruption_types.items():
            confidence = data['confidence']
            issues = data['issues']
            
            # Only quarantine low confidence issues automatically
            if confidence == 'LOW':
                for issue in issues:
                    model_name = self._get_model_name_for_corruption(corruption_type)
                    object_id = self._get_object_id_from_issue(issue)
                    
                    quarantine_data_list.append({
                        'model_name': model_name,
                        'object_id': object_id,
                        'corruption_type': corruption_type,
                        'reason': f"Low confidence corruption detected: {confidence}",
                        'original_data': issue,
                        'context': {
                            'source': 'RepairService',
                            'confidence': confidence,
                            'corruption_scan': True
                        }
                    })
        
        if quarantine_data_list:
            return self.batch_quarantine_data(quarantine_data_list, user)
        else:
            return {
                'success': True,
                'created_count': 0,
                'requested_count': 0,
                'message': 'No low confidence issues to quarantine'
            }
    
    # Utility methods
    
    def _get_model_name_for_corruption(self, corruption_type: str) -> str:
        """Get model name for corruption type"""
        mapping = {
            'ORPHANED_JOURNAL_ENTRIES': 'JournalEntry',
            'NEGATIVE_STOCK': 'Stock',
            'MULTIPLE_ACTIVE_ACADEMIC_YEARS': 'AcademicYear',
            'UNBALANCED_JOURNAL_ENTRIES': 'JournalEntry'
        }
        return mapping.get(corruption_type, 'Unknown')
    
    def _get_object_id_from_issue(self, issue: Dict) -> int:
        """Extract object ID from issue data"""
        # Try common ID field names
        for field in ['entry_id', 'stock_id', 'year_id', 'id']:
            if field in issue:
                return issue[field]
        return 0  # Fallback
    
    # Health check and monitoring
    
    @monitor_operation("quarantine_health_check")
    def health_check(self) -> Dict:
        """
        Perform health check on quarantine system.
        
        Returns:
            Dict: Health check results
        """
        health_status = {
            'status': 'healthy',
            'checks': {},
            'timestamp': timezone.now().isoformat()
        }
        
        try:
            # Check database connectivity
            total_records = QuarantineRecord.objects.count()
            health_status['checks']['database_connectivity'] = {
                'status': 'ok',
                'total_records': total_records
            }
        except Exception as e:
            health_status['status'] = 'unhealthy'
            health_status['checks']['database_connectivity'] = {
                'status': 'error',
                'error': str(e)
            }
        
        try:
            # Check for stuck quarantines (over 30 days old)
            stuck_count = QuarantineRecord.objects.filter(
                status='QUARANTINED',
                quarantined_at__lt=timezone.now() - timedelta(days=30)
            ).count()
            
            health_status['checks']['stuck_quarantines'] = {
                'status': 'warning' if stuck_count > 0 else 'ok',
                'stuck_count': stuck_count
            }
        except Exception as e:
            health_status['checks']['stuck_quarantines'] = {
                'status': 'error',
                'error': str(e)
            }
        
        try:
            # Check recent activity
            recent_count = QuarantineRecord.objects.filter(
                quarantined_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
            
            health_status['checks']['recent_activity'] = {
                'status': 'ok',
                'recent_24h_count': recent_count
            }
        except Exception as e:
            health_status['checks']['recent_activity'] = {
                'status': 'error',
                'error': str(e)
            }
        
        return health_status


# Global QuarantineSystem instance
quarantine_system = QuarantineSystem()