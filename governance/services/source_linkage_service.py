"""
Source Linkage service for validating and managing journal entry source references.
Implements the SourceLinkage contract system with allowlist validation and thread-safe operations.
"""

import logging
from typing import Dict, Optional, Tuple, List
from django.apps import apps
from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import GovernanceContext, QuarantineRecord
from ..exceptions import ValidationError as GovernanceValidationError
from ..thread_safety import monitor_operation

logger = logging.getLogger(__name__)


class SourceLinkageService:
    """
    Service for managing source linkage validation and backfill operations.
    Ensures all journal entries have valid source references from allowlisted models.
    """
    
    # Allowlist of valid source models for journal entries
    ALLOWED_SOURCES = {
        'client.CustomerPayment',
        'purchase.PurchasePayment',
        'hr.PayrollPayment',
        'hr.Payroll',  # Added for POC testing - HR payroll records
        'product.StockMovement',
        'transportation.TransportationFee',
        'financial.FinancialTransaction',  # Added for TransactionService
        'financial.BankReconciliation',  # Added for BankReconciliationService
        'financial.PartnerTransaction',  # Added for partner transactions
        'courses.CourseEnrollment',  # Added for CourseAccountingService
        'qr_applications.QRApplication',  # Added for QR application payments
        'activities.ActivityExpense',  # Added for activity expense tracking
        'sale.Sale',  # Added for sale invoices
        'sale.SalePayment',  # Added for sale payments
        'sale.SaleReturn',  # Added for sale returns
        'purchase.Purchase',  # Added for purchase invoices
        'purchase.PurchaseReturn',  # Added for purchase returns
        # Note: 'financial.ManualAdjustment' will be added when the model is implemented
    }
    
    @classmethod
    def validate_linkage(cls, source_module: str, source_model: str, source_id: int) -> bool:
        """
        Validate that source reference points to existing record and is allowed.
        Thread-safe implementation with proper error handling.
        
        Args:
            source_module: Module name 
            source_model: Model name 
            source_id: ID of the source record
            
        Returns:
            bool: True if linkage is valid, False otherwise
        """
        with monitor_operation("source_linkage_validation"):
            try:
                source_key = f"{source_module}.{source_model}"
                
                # Check allowlist first
                if source_key not in cls.ALLOWED_SOURCES:
                    logger.warning(f"Invalid source model not in allowlist: {source_key}")
                    return False
                
                # Check if source record exists
                try:
                    model_class = apps.get_model(source_module, source_model)
                    return model_class.objects.filter(id=source_id).exists()
                except (LookupError, ValueError) as e:
                    logger.error(f"Error accessing model {source_key}: {e}")
                    return False
                    
            except Exception as e:
                logger.error(f"Unexpected error in source linkage validation: {e}", exc_info=True)
                return False
    
    @classmethod
    def create_linkage(cls, source_module: str, source_model: str, source_id: int) -> Dict[str, any]:
        """
        Create standardized source linkage data with validation.
        
        Args:
            source_module: Module name
            source_model: Model name
            source_id: ID of the source record
            
        Returns:
            dict: Standardized source linkage data
            
        Raises:
            GovernanceValidationError: If source reference is invalid
        """
        if not cls.validate_linkage(source_module, source_model, source_id):
            source_key = f"{source_module}.{source_model}"
            raise GovernanceValidationError(
                message=f"Invalid or disallowed source reference: {source_key}#{source_id}",
                field="source_linkage",
                value=source_key,
                context={
                    'source_module': source_module,
                    'source_model': source_model,
                    'source_id': source_id,
                    'allowed_sources': list(cls.ALLOWED_SOURCES)
                }
            )
        
        return {
            'source_module': source_module,
            'source_model': source_model,
            'source_id': source_id
        }
    
    @classmethod
    def get_source_object(cls, source_module: str, source_model: str, source_id: int):
        """
        Get the actual source object if it exists and is valid.
        
        Args:
            source_module: Module name
            source_model: Model name
            source_id: ID of the source record
            
        Returns:
            Model instance or None: The source object if valid, None otherwise
        """
        try:
            if not cls.validate_linkage(source_module, source_model, source_id):
                return None
            
            model_class = apps.get_model(source_module, source_model)
            return model_class.objects.get(id=source_id)
            
        except Exception as e:
            logger.error(f"Error retrieving source object: {e}")
            return None
    
    @classmethod
    def scan_orphaned_entries(cls, batch_size: int = 1000) -> List[Dict]:
        """
        Scan for journal entries with invalid or missing source linkage.
        Thread-safe implementation with batching.
        
        Args:
            batch_size: Number of entries to process in each batch
            
        Returns:
            list: List of orphaned entry information
        """
        from financial.models import JournalEntry
        
        orphaned_entries = []
        
        with monitor_operation("orphaned_entries_scan"):
            try:
                # Process entries in batches to avoid memory issues
                total_entries = JournalEntry.objects.count()
                processed = 0
                
                while processed < total_entries:
                    entries_batch = JournalEntry.objects.all()[processed:processed + batch_size]
                    
                    for entry in entries_batch:
                        # Check if entry has source linkage fields
                        if not all([entry.source_module, entry.source_model, entry.source_id]):
                            orphaned_entries.append({
                                'entry_id': entry.id,
                                'entry_number': entry.number,
                                'entry_date': entry.date,
                                'description': entry.description,
                                'issue': 'missing_source_fields',
                                'source_module': entry.source_module,
                                'source_model': entry.source_model,
                                'source_id': entry.source_id
                            })
                            continue
                        
                        # Check if source linkage is valid
                        if not cls.validate_linkage(entry.source_module, entry.source_model, entry.source_id):
                            orphaned_entries.append({
                                'entry_id': entry.id,
                                'entry_number': entry.number,
                                'entry_date': entry.date,
                                'description': entry.description,
                                'issue': 'invalid_source_linkage',
                                'source_module': entry.source_module,
                                'source_model': entry.source_model,
                                'source_id': entry.source_id
                            })
                    
                    processed += len(entries_batch)
                    
                    # Log progress
                    if processed % (batch_size * 10) == 0:
                        logger.info(f"Processed {processed}/{total_entries} journal entries for orphan detection")
                
                logger.info(f"Orphaned entries scan completed. Found {len(orphaned_entries)} orphaned entries")
                return orphaned_entries
                
            except Exception as e:
                logger.error(f"Error during orphaned entries scan: {e}", exc_info=True)
                raise
    
    @classmethod
    def backfill_source_linkage(cls, entry_id: int, source_module: str, source_model: str, 
                              source_id: int, user=None, dry_run: bool = False) -> Tuple[bool, str, Dict]:
        """
        Backfill source linkage for a specific journal entry.
        Thread-safe implementation with validation and audit trail.
        
        Args:
            entry_id: ID of the journal entry to backfill
            source_module: Module name for the source
            source_model: Model name for the source
            source_id: ID of the source record
            user: User performing the backfill (from context if not provided)
            dry_run: If True, validate but don't actually update
            
        Returns:
            tuple: (success, message, details)
        """
        from financial.models import JournalEntry
        from .audit_service import AuditService
        
        # Get user from context if not provided
        if user is None:
            user = GovernanceContext.get_current_user()
        
        with monitor_operation("source_linkage_backfill"):
            try:
                # Validate the new source linkage
                linkage_data = cls.create_linkage(source_module, source_model, source_id)
                
                with transaction.atomic():
                    # Get the journal entry
                    try:
                        entry = JournalEntry.objects.select_for_update().get(id=entry_id)
                    except JournalEntry.DoesNotExist:
                        return False, f"Journal entry with ID {entry_id} not found", {}
                    
                    # Store original data for audit
                    original_data = {
                        'source_module': entry.source_module,
                        'source_model': entry.source_model,
                        'source_id': entry.source_id
                    }
                    
                    if dry_run:
                        return True, "Dry run successful - source linkage is valid", {
                            'entry_number': entry.number,
                            'original_linkage': original_data,
                            'new_linkage': linkage_data
                        }
                    
                    # Update the source linkage
                    entry.source_module = source_module
                    entry.source_model = source_model
                    entry.source_id = source_id
                    entry.save(update_fields=['source_module', 'source_model', 'source_id'])
                    
                    # Create audit trail
                    if user:
                        AuditService.log_operation(
                            model_name='JournalEntry',
                            object_id=entry.id,
                            operation='UPDATE',
                            source_service='SourceLinkageService',
                            user=user,
                            before_data=original_data,
                            after_data=linkage_data,
                            operation_type='source_linkage_backfill'
                        )
                    
                    logger.info(f"Source linkage backfilled for entry {entry.number}: {source_module}.{source_model}#{source_id}")
                    
                    return True, "Source linkage backfilled successfully", {
                        'entry_number': entry.number,
                        'original_linkage': original_data,
                        'new_linkage': linkage_data
                    }
                    
            except GovernanceValidationError as e:
                return False, f"Validation error: {e.message}", {'error': str(e)}
            except Exception as e:
                logger.error(f"Error during source linkage backfill: {e}", exc_info=True)
                return False, f"Unexpected error: {str(e)}", {'error': str(e)}
    
    @classmethod
    def quarantine_orphaned_entry(cls, entry_id: int, reason: str, user=None) -> bool:
        """
        Quarantine an orphaned journal entry that cannot be backfilled.
        
        Args:
            entry_id: ID of the journal entry to quarantine
            reason: Reason for quarantine
            user: User performing the quarantine
            
        Returns:
            bool: True if successfully quarantined
        """
        from financial.models import JournalEntry
        
        # Get user from context if not provided
        if user is None:
            user = GovernanceContext.get_current_user()
            if user is None:
                logger.error("No user provided for quarantine operation")
                return False
        
        try:
            with transaction.atomic():
                entry = JournalEntry.objects.get(id=entry_id)
                
                # Create quarantine record
                quarantine_record = QuarantineRecord.objects.create(
                    model_name='JournalEntry',
                    object_id=entry.id,
                    corruption_type='ORPHANED_ENTRY',
                    original_data={
                        'number': entry.number,
                        'date': str(entry.date),
                        'description': entry.description,
                        'source_module': entry.source_module,
                        'source_model': entry.source_model,
                        'source_id': entry.source_id,
                        'total_debit': str(entry.total_debit),
                        'total_credit': str(entry.total_credit)
                    },
                    quarantine_reason=reason,
                    quarantined_by=user
                )
                
                logger.warning(f"Journal entry {entry.number} quarantined: {reason}")
                return True
                
        except Exception as e:
            logger.error(f"Error quarantining orphaned entry: {e}", exc_info=True)
            return False
    
    @classmethod
    def get_backfill_statistics(cls) -> Dict[str, any]:
        """
        Get statistics about source linkage and backfill operations.
        
        Returns:
            dict: Statistics including orphaned entries count, backfill success rate, etc.
        """
        from financial.models import JournalEntry
        from django.db.models import Q, Count
        
        stats = {}
        
        try:
            # Total journal entries
            stats['total_entries'] = JournalEntry.objects.count()
            
            # Entries with complete source linkage
            complete_linkage = JournalEntry.objects.filter(
                source_module__isnull=False,
                source_model__isnull=False,
                source_id__isnull=False
            ).exclude(
                Q(source_module='') | Q(source_model='') | Q(source_id__isnull=True)
            )
            stats['complete_linkage_count'] = complete_linkage.count()
            
            # Entries with missing source linkage
            stats['missing_linkage_count'] = stats['total_entries'] - stats['complete_linkage_count']
            
            # Percentage of complete linkage
            if stats['total_entries'] > 0:
                stats['linkage_completion_percentage'] = (
                    stats['complete_linkage_count'] / stats['total_entries']
                ) * 100
            else:
                stats['linkage_completion_percentage'] = 0
            
            # Count by source model
            source_counts = complete_linkage.values('source_module', 'source_model').annotate(
                count=Count('id')
            ).order_by('-count')
            
            stats['entries_by_source'] = {
                f"{item['source_module']}.{item['source_model']}": item['count']
                for item in source_counts
            }
            
            # Quarantined orphaned entries
            stats['quarantined_orphans'] = QuarantineRecord.objects.filter(
                model_name='JournalEntry',
                corruption_type='ORPHANED_ENTRY',
                status='QUARANTINED'
            ).count()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error generating backfill statistics: {e}", exc_info=True)
            return {'error': str(e)}
    
    @classmethod
    def validate_allowlist_models(cls) -> List[str]:
        """
        Validate that all models in the allowlist exist and are accessible.
        
        Returns:
            list: List of validation errors, empty if all models are valid
        """
        errors = []
        
        for source_key in cls.ALLOWED_SOURCES:
            try:
                module_name, model_name = source_key.split('.')
                model_class = apps.get_model(module_name, model_name)
                
                # Try to access the model's meta to ensure it's properly loaded
                _ = model_class._meta.verbose_name
                
            except (ValueError, LookupError) as e:
                errors.append(f"Invalid allowlist entry '{source_key}': {e}")
            except Exception as e:
                errors.append(f"Error validating allowlist entry '{source_key}': {e}")
        
        if errors:
            logger.error(f"Allowlist validation failed: {errors}")
        else:
            logger.info("Allowlist validation passed - all models are accessible")
        
        return errors
    
    @classmethod
    def get_source_model_info(cls, source_module: str, source_model: str) -> Optional[Dict]:
        """
        Get information about a source model.
        
        Args:
            source_module: Module name
            source_model: Model name
            
        Returns:
            dict or None: Model information if valid, None otherwise
        """
        try:
            source_key = f"{source_module}.{source_model}"
            
            if source_key not in cls.ALLOWED_SOURCES:
                return None
            
            model_class = apps.get_model(source_module, source_model)
            
            return {
                'source_key': source_key,
                'model_name': model_class.__name__,
                'verbose_name': str(model_class._meta.verbose_name),
                'app_label': model_class._meta.app_label,
                'table_name': model_class._meta.db_table,
                'is_allowlisted': True,
                'record_count': model_class.objects.count()
            }
            
        except Exception as e:
            logger.error(f"Error getting source model info: {e}")
            return None