"""
إشارات ربط المخزون بالمحاسبة - Governed Signals (Phase 3.2)
Stock-Accounting Integration Signals - Low-Risk Signal Processing

Migration Status: Phase 3.2 - Low-Risk Signal Processing ✅
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
from datetime import date
import logging

from governance.signal_integration import governed_signal_handler, side_effect_handler
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext

from .models import StockMovement
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import (
    JournalEntry,
    JournalEntryLine,
    AccountingPeriod,
)
from financial.services.journal_service import JournalEntryService

logger = logging.getLogger(__name__)


# Import the correct service
from product.services.stock_accounting_service import StockAccountingService


@side_effect_handler(
    "stock_accounting_entry_creation",
    "Create accounting journal entry for stock movements"
)
@receiver(post_save, sender=StockMovement)
def create_accounting_entry_for_stock_movement(sender, instance, created, **kwargs):
    """
    إنشاء قيد محاسبي عند إنشاء حركة مخزون
    Governed side effect handler: Creates accounting journal entry for stock movements
    
    ⚠️ ملاحظة: تم تعطيل القيود المحاسبية للمشتريات - يتم إنشاؤها عبر AccountingIntegrationService
    """
    if not created or getattr(instance, "_skip_accounting", False):
        return
    
    # ✅ تخطي المشتريات - يتم إنشاء القيود عبر AccountingIntegrationService
    if instance.document_type == "purchase":
        logger.debug(f"Skipping accounting entry for purchase stock movement {instance.reference_number} - handled by AccountingIntegrationService")
        return
        
    # تجنب إنشاء قيود محاسبية متكررة
    if hasattr(instance, "journal_entry") and instance.journal_entry:
        logger.debug(f"Journal entry already exists for stock movement {instance.id}")
        return

    try:
        with transaction.atomic():
            journal_entry = StockAccountingService.create_stock_movement_entry(
                instance,
                user=instance.created_by
            )
            if journal_entry:
                # Audit journal entry creation
                AuditService.create_audit_record(
                    model_name='StockMovement',
                    object_id=instance.id,
                    operation='ACCOUNTING_JOURNAL_ENTRY_CREATED',
                    user=GovernanceContext.get_current_user(),
                    source_service='StockAccountingSignals',
                    additional_context={
                        'journal_entry_id': journal_entry.id,
                        'reference_number': instance.reference_number,
                        'movement_type': instance.movement_type,
                        'product_name': instance.product.name,
                        'amount': str(instance.quantity * instance.product.cost_price) if hasattr(instance.product, 'cost_price') else 'N/A'
                    }
                )
                
            else:
                logger.warning(f"Failed to create journal entry for stock movement {instance.reference_number}")

    except Exception as e:
        logger.error(f"Error creating accounting journal entry for stock movement {instance.reference_number}: {e}")
        
        # Audit error
        AuditService.create_audit_record(
            model_name='StockMovement',
            object_id=instance.id,
            operation='ACCOUNTING_JOURNAL_ENTRY_ERROR',
            user=GovernanceContext.get_current_user(),
            source_service='StockAccountingSignals',
            additional_context={
                'error': str(e),
                'reference_number': instance.reference_number,
                'movement_type': instance.movement_type
            }
        )


@side_effect_handler(
    "stock_accounting_entry_deletion",
    "Delete accounting journal entry when stock movement is deleted"
)
@receiver(post_delete, sender=StockMovement)
def delete_accounting_entry_for_stock_movement(sender, instance, **kwargs):
    """
    حذف القيد المحاسبي عند حذف حركة المخزون
    Governed side effect handler: Deletes accounting journal entry when stock movement is deleted
    """
    try:
        if hasattr(instance, "journal_entry") and instance.journal_entry:
            journal_entry = instance.journal_entry
            journal_entry_id = journal_entry.id
            journal_entry.delete()
            
            # Audit journal entry deletion
            AuditService.create_audit_record(
                model_name='StockMovement',
                object_id=instance.id,
                operation='ACCOUNTING_JOURNAL_ENTRY_DELETED',
                user=GovernanceContext.get_current_user(),
                source_service='StockAccountingSignals',
                additional_context={
                    'deleted_journal_entry_id': journal_entry_id,
                    'reference_number': instance.reference_number,
                    'movement_type': instance.movement_type,
                    'product_name': instance.product.name
                }
            )
            

    except Exception as e:
        logger.error(f"Error deleting accounting journal entry for stock movement {instance.reference_number}: {e}")
        
        # Audit error
        AuditService.create_audit_record(
            model_name='StockMovement',
            object_id=instance.id,
            operation='ACCOUNTING_JOURNAL_DELETION_ERROR',
            user=GovernanceContext.get_current_user(),
            source_service='StockAccountingSignals',
            additional_context={
                'error': str(e),
                'reference_number': instance.reference_number
            }
        )
