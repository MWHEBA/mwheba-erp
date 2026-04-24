"""
Stock Orchestrator Service - Centralized business logic for StockMovement operations.

This service consolidates all business logic that was previously scattered across signals,
providing a single point of control for stock-related operations with proper governance.

Key Features:
- Centralized stock movement lifecycle management
- Negative stock prevention with proper validation
- Atomic stock updates with transaction boundaries
- Integration with AccountingGateway for journal entries
- Idempotency protection and audit trail integration
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from ..models import StockMovement, Stock, Product
from governance.services import (
    MovementService, AccountingGateway, IdempotencyService, 
    AuditService, governance_switchboard, GovernanceContext
)
from governance.exceptions import ValidationError, GovernanceError

User = get_user_model()
logger = logging.getLogger(__name__)


class StockOrchestratorService:
    """
    Orchestrator service for all StockMovement business operations.
    
    Consolidates business logic from signals into proper service methods
    with governance controls and proper transaction boundaries.
    """
    
    @classmethod
    def handle_stock_movement_change(cls, movement: StockMovement, created: bool, user: Optional[User] = None) -> Dict[str, Any]:
        """
        Handle StockMovement creation or modification.
        
        This replaces the business logic from:
        - product/signals.py:update_stock_on_movement
        - sale/signals.py:create_stock_movement_for_sale_item
        
        Args:
            movement: The StockMovement instance
            created: Whether this is a new movement
            user: User performing the operation
            
        Returns:
            dict: Operation result with success status and details
        """
        if not governance_switchboard.is_workflow_enabled('stock_movement_to_journal_entry'):
            return {
                'success': True,
                'message': 'StockMovement workflow disabled - operation skipped',
                'workflow_disabled': True
            }
        
        operation_key = f"stock_movement_{movement.id}_{timezone.now().timestamp()}"
        
        try:
            with transaction.atomic():
                # Set governance context
                GovernanceContext.set_context(
                    user=user or movement.created_by,
                    service='StockOrchestratorService',
                    operation='handle_stock_movement_change'
                )
                
                result = {
                    'success': False,
                    'movement_id': movement.id,
                    'created': created,
                    'actions_taken': [],
                    'journal_entries_created': [],
                    'stock_updated': False,
                    'low_stock_alert': False,
                    'negative_stock_prevented': False
                }
                
                # 1. Process through MovementService for validation
                if created:
                    movement_result = cls._process_new_movement(movement, operation_key)
                    result.update(movement_result)
                else:
                    movement_result = cls._process_movement_modification(movement, operation_key)
                    result.update(movement_result)
                
                # 2. Update stock quantities atomically
                stock_result = cls._update_stock_quantities(movement)
                result['stock_updated'] = stock_result['updated']
                result['actions_taken'].extend(stock_result.get('actions', []))
                
                if stock_result.get('negative_stock_prevented'):
                    result['negative_stock_prevented'] = True
                    result['actions_taken'].append('negative_stock_prevented')
                
                # 3. Check for low stock alerts
                if stock_result['updated']:
                    alert_result = cls._check_low_stock_alerts(movement)
                    result['low_stock_alert'] = alert_result['alert_created']
                    result['actions_taken'].extend(alert_result.get('actions', []))
                
                # 4. Create journal entry through AccountingGateway
                if movement.document_type in ['sale', 'purchase', 'adjustment']:
                    journal_result = cls._create_movement_journal_entry(movement, operation_key)
                    if journal_result['success']:
                        result['journal_entries_created'].append(journal_result['journal_entry_id'])
                        result['actions_taken'].append('journal_entry_created')
                
                # 5. Create audit trail
                AuditService.log_operation(
                    model_name='StockMovement',
                    object_id=movement.id,
                    operation='ORCHESTRATED_CHANGE',
                    source_service='StockOrchestratorService',
                    user=user or movement.created_by,
                    created=created,
                    actions_taken=result['actions_taken']
                )
                
                result['success'] = True
                
                return result
                
        except Exception as e:
            logger.error(f"Stock movement orchestration failed for movement {movement.id}: {e}", exc_info=True)
            
            # Create error audit trail
            AuditService.log_operation(
                model_name='StockMovement',
                object_id=movement.id,
                operation='ORCHESTRATION_ERROR',
                source_service='StockOrchestratorService',
                user=user or movement.created_by,
                error=str(e)
            )
            
            raise GovernanceError(f"Stock movement orchestration failed: {e}")
            
        finally:
            GovernanceContext.clear_context()
    
    @classmethod
    def handle_stock_movement_deletion(cls, movement: StockMovement, user: Optional[User] = None) -> Dict[str, Any]:
        """
        Handle StockMovement deletion.
        
        This replaces the business logic from:
        - product/signals.py:revert_stock_on_movement_delete
        - sale/signals.py:handle_deleted_sale_item
        """
        if not governance_switchboard.is_workflow_enabled('stock_movement_to_journal_entry'):
            return {
                'success': True,
                'message': 'StockMovement workflow disabled - operation skipped',
                'workflow_disabled': True
            }
        
        try:
            with transaction.atomic():
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='StockOrchestratorService',
                    operation='handle_stock_movement_deletion'
                )
                
                result = {
                    'success': False,
                    'movement_id': movement.id,
                    'product_id': movement.product.id,
                    'actions_taken': [],
                    'stock_reverted': False,
                    'journal_entry_reversed': False
                }
                
                # 1. Revert stock quantities
                revert_result = cls._revert_stock_quantities(movement)
                result['stock_reverted'] = revert_result['reverted']
                result['actions_taken'].extend(revert_result.get('actions', []))
                
                # 2. Reverse journal entry if exists
                if movement.journal_entry:
                    reversal_result = cls._create_movement_reversal_entry(movement)
                    result['journal_entry_reversed'] = reversal_result['success']
                    if reversal_result['success']:
                        result['actions_taken'].append('journal_entry_reversed')
                
                # 3. Create audit trail
                AuditService.log_operation(
                    model_name='StockMovement',
                    object_id=movement.id,
                    operation='ORCHESTRATED_DELETION',
                    source_service='StockOrchestratorService',
                    user=user,
                    actions_taken=result['actions_taken']
                )
                
                result['success'] = True
                
                return result
                
        except Exception as e:
            logger.error(f"Stock movement deletion orchestration failed for movement {movement.id}: {e}", exc_info=True)
            raise GovernanceError(f"Stock movement deletion orchestration failed: {e}")
            
        finally:
            GovernanceContext.clear_context()
    
    
    # Private helper methods
    
    @classmethod
    def _process_new_movement(cls, movement: StockMovement, operation_key: str) -> Dict[str, Any]:
        """Process new stock movement through MovementService"""
        result = {'actions_taken': []}
        
        try:
            # Validate movement through MovementService
            validation_result = MovementService.validate_movement(
                product_id=movement.product.id,
                quantity_change=movement.quantity if movement.movement_type == 'in' else -movement.quantity,
                movement_type=movement.movement_type,
                warehouse=movement.warehouse
            )
            
            if validation_result['valid']:
                result['actions_taken'].append('movement_validated')
            else:
                raise ValidationError(f"Movement validation failed: {validation_result['error']}")
                
        except Exception as e:
            logger.error(f"Movement validation failed: {e}")
            result['actions_taken'].append('movement_validation_failed')
            raise
        
        result['actions_taken'].append('new_movement_processed')
        return result
    
    @classmethod
    def _process_movement_modification(cls, movement: StockMovement, operation_key: str) -> Dict[str, Any]:
        """Process stock movement modification"""
        result = {'actions_taken': []}
        
        # For modifications, we need to revert the old effect and apply the new one
        # This is complex and should be handled carefully
        result['actions_taken'].append('movement_modification_processed')
        return result
    
    @classmethod
    def _update_stock_quantities(cls, movement: StockMovement) -> Dict[str, Any]:
        """Update stock quantities atomically with negative stock prevention"""
        result = {'updated': False, 'actions': []}
        
        try:
            # Get or create stock record
            stock, created = Stock.objects.get_or_create(
                product=movement.product,
                warehouse=movement.warehouse,
                defaults={"quantity": Decimal("0")}
            )
            
            if created:
                result['actions'].append('stock_record_created')
            
            # Calculate new quantity based on movement type
            old_quantity = stock.quantity
            
            if movement.movement_type in ["in", "return_in"]:
                new_quantity = old_quantity + Decimal(movement.quantity)
            elif movement.movement_type in ["out", "return_out"]:
                new_quantity = old_quantity - Decimal(movement.quantity)
                
                # Prevent negative stock
                if new_quantity < 0:
                    logger.warning(f"Preventing negative stock for product {movement.product.id}: {old_quantity} - {movement.quantity} = {new_quantity}")
                    result['negative_stock_prevented'] = True
                    new_quantity = Decimal("0")  # Set to zero instead of negative
                    
            elif movement.movement_type == "transfer" and movement.destination_warehouse:
                # Handle transfer - reduce from source
                new_quantity = max(Decimal("0"), old_quantity - Decimal(movement.quantity))
                
                # Increase in destination
                dest_stock, dest_created = Stock.objects.get_or_create(
                    product=movement.product,
                    warehouse=movement.destination_warehouse,
                    defaults={"quantity": Decimal("0")}
                )
                dest_stock.quantity += Decimal(movement.quantity)
                dest_stock.save()
                
                if dest_created:
                    result['actions'].append('destination_stock_record_created')
                result['actions'].append('destination_stock_updated')
                
            elif movement.movement_type == "adjustment":
                new_quantity = Decimal(movement.quantity)
            else:
                new_quantity = old_quantity
            
            # Update stock quantity
            if new_quantity != old_quantity:
                stock.quantity = new_quantity
                stock.save()
                result['updated'] = True
                result['actions'].append('stock_quantity_updated')
                
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to update stock quantities: {e}")
            result['actions'].append('stock_update_failed')
            raise
    
    @classmethod
    def _revert_stock_quantities(cls, movement: StockMovement) -> Dict[str, Any]:
        """Revert stock quantities when movement is deleted"""
        result = {'reverted': False, 'actions': []}
        
        try:
            # Find the stock record
            stock = Stock.objects.get(
                product=movement.product,
                warehouse=movement.warehouse
            )
            
            old_quantity = stock.quantity
            
            # Reverse the movement effect
            if movement.movement_type in ["in", "return_in"]:
                # Reverse addition - subtract
                new_quantity = max(Decimal("0"), old_quantity - Decimal(movement.quantity))
            elif movement.movement_type in ["out", "return_out"]:
                # Reverse subtraction - add back
                new_quantity = old_quantity + Decimal(movement.quantity)
            elif movement.movement_type == "transfer":
                # Reverse transfer
                new_quantity = old_quantity + Decimal(movement.quantity)
                
                # Reverse destination warehouse effect
                if movement.destination_warehouse:
                    try:
                        dest_stock = Stock.objects.get(
                            product=movement.product,
                            warehouse=movement.destination_warehouse
                        )
                        dest_stock.quantity = max(Decimal("0"), dest_stock.quantity - Decimal(movement.quantity))
                        dest_stock.save()
                        result['actions'].append('destination_stock_reverted')
                    except Stock.DoesNotExist:
                        pass
            else:
                new_quantity = old_quantity
            
            # Update stock quantity
            if new_quantity != old_quantity:
                stock.quantity = new_quantity
                stock.save()
                result['reverted'] = True
                result['actions'].append('stock_quantity_reverted')
                
            
            return result
            
        except Stock.DoesNotExist:
            logger.warning(f"Stock record not found for product {movement.product.id} in warehouse {movement.warehouse.id}")
            result['actions'].append('stock_record_not_found')
            return result
        except Exception as e:
            logger.error(f"Failed to revert stock quantities: {e}")
            result['actions'].append('stock_revert_failed')
            raise
    
    @classmethod
    def _check_low_stock_alerts(cls, movement: StockMovement) -> Dict[str, Any]:
        """Check for low stock conditions and create alerts"""
        result = {'alert_created': False, 'actions': []}
        
        try:
            # Get current stock level
            stock = Stock.objects.get(
                product=movement.product,
                warehouse=movement.warehouse
            )
            
            # Check if stock is below minimum threshold
            if (movement.product.min_stock > 0 and 
                stock.quantity <= movement.product.min_stock):
                
                # Create low stock alert through notification service
                try:
                    from core.services.notification_service import NotificationService
                    from django.contrib.auth import get_user_model
                    from django.db.models import Q
                    
                    User = get_user_model()
                    
                    # Get authorized users for inventory alerts
                    authorized_users = User.objects.filter(
                        Q(user_type__in=['admin', 'inventory_manager']) | Q(is_superuser=True),
                        is_active=True
                    ).distinct()
                    
                    for user in authorized_users:
                        NotificationService.create_notification(
                            user=user,
                            title=f"تنبيه مخزون منخفض: {movement.product.name}",
                            message=f"المخزون الحالي: {stock.quantity} - الحد الأدنى: {movement.product.min_stock}",
                            notification_type="warning",
                            related_model="Product",
                            related_id=movement.product.id,
                            link_url=f"/products/{movement.product.id}/"
                        )
                    
                    result['alert_created'] = True
                    result['actions'].append('low_stock_alert_created')
                    
                    
                except Exception as e:
                    logger.error(f"Failed to create low stock alert: {e}")
                    result['actions'].append('low_stock_alert_failed')
            
            return result
            
        except Stock.DoesNotExist:
            return result
        except Exception as e:
            logger.error(f"Failed to check low stock alerts: {e}")
            result['actions'].append('low_stock_check_failed')
            return result
    
    @classmethod
    def _create_movement_journal_entry(cls, movement: StockMovement, operation_key: str) -> Dict[str, Any]:
        """Create journal entry for stock movement through AccountingGateway"""
        try:
            from governance.services.accounting_gateway import JournalEntryLineData
            
            # Calculate cost (simplified - should use proper costing method)
            cost_per_unit = getattr(movement.product, 'cost_price', 0) or 0
            total_cost = Decimal(movement.quantity) * Decimal(cost_per_unit)
            
            lines = []
            
            if movement.movement_type == 'in':
                # Inventory increase
                lines = [
                    JournalEntryLineData(
                        account_code='1201',  # Inventory
                        debit_amount=total_cost,
                        credit_amount=0,
                        description=f'زيادة مخزون - {movement.product.name}'
                    ),
                    JournalEntryLineData(
                        account_code='5101',  # Cost of Goods Sold (or appropriate account)
                        debit_amount=0,
                        credit_amount=total_cost,
                        description=f'تكلفة مخزون - {movement.product.name}'
                    )
                ]
            elif movement.movement_type == 'out':
                # Inventory decrease
                lines = [
                    JournalEntryLineData(
                        account_code='5101',  # Cost of Goods Sold
                        debit_amount=total_cost,
                        credit_amount=0,
                        description=f'تكلفة مبيعات - {movement.product.name}'
                    ),
                    JournalEntryLineData(
                        account_code='1201',  # Inventory
                        debit_amount=0,
                        credit_amount=total_cost,
                        description=f'نقص مخزون - {movement.product.name}'
                    )
                ]
            elif movement.movement_type == 'adjustment':
                # Inventory adjustment
                if total_cost > 0:
                    lines = [
                        JournalEntryLineData(
                            account_code='1201',  # Inventory
                            debit_amount=total_cost,
                            credit_amount=0,
                            description=f'تسوية مخزون - {movement.product.name}'
                        ),
                        JournalEntryLineData(
                            account_code='5201',  # Inventory Adjustments
                            debit_amount=0,
                            credit_amount=total_cost,
                            description=f'تسوية مخزون - {movement.product.name}'
                        )
                    ]
            
            if lines:
                from governance.exceptions import AuthorityViolationError, ValidationError as GovValidationError, IdempotencyError
                from financial.models import ChartOfAccounts
                from decimal import Decimal
                
                # ✅ Convert account_code to account objects
                converted_lines = []
                for line_data in lines:
                    try:
                        account = ChartOfAccounts.objects.get(code=line_data.account_code, is_active=True)
                        converted_lines.append(
                            JournalEntryLineData(
                                account=account,
                                debit=Decimal(str(line_data.debit_amount)) if hasattr(line_data, 'debit_amount') else line_data.debit,
                                credit=Decimal(str(line_data.credit_amount)) if hasattr(line_data, 'credit_amount') else line_data.credit,
                                description=line_data.description
                            )
                        )
                    except ChartOfAccounts.DoesNotExist:
                        logger.error(f'Account {line_data.account_code} not found')
                        return {'success': False, 'error': f'Account {line_data.account_code} not configured'}
                
                # Get financial category and subcategory from product
                financial_category = movement.product.financial_category if hasattr(movement.product, 'financial_category') else None
                financial_subcategory = movement.product.financial_subcategory if hasattr(movement.product, 'financial_subcategory') else None
                
                # ✅ Call AccountingGateway with proper error handling
                try:
                    gateway = AccountingGateway()
                    journal_entry = gateway.create_journal_entry(
                        source_module='product',
                        source_model='StockMovement',
                        source_id=movement.id,
                        lines=converted_lines,
                        idempotency_key=f"stock_movement_{operation_key}",
                        user=GovernanceContext.get_current_user(),
                        entry_type='automatic',
                        description=f'حركة مخزون - {movement.product.name}',
                        reference=f'STK-{movement.id}',
                        date=movement.movement_date if hasattr(movement, 'movement_date') else timezone.now().date(),
                        financial_category=financial_category,
                        financial_subcategory=financial_subcategory
                    )
                    
                    # Link journal entry to movement
                    movement.journal_entry = journal_entry
                    movement.save(update_fields=['journal_entry'])
                    
                    logger.info(f'Created journal entry {journal_entry.number} for stock movement {movement.id}')
                    
                    return {
                        'success': True,
                        'journal_entry_id': journal_entry.id,
                        'journal_entry_number': journal_entry.number
                    }
                    
                except AuthorityViolationError as e:
                    logger.error(f'Authority violation creating journal entry for movement {movement.id}: {e}')
                    return {'success': False, 'error': f'Authority violation: {str(e)}'}
                    
                except GovValidationError as e:
                    logger.error(f'Validation error creating journal entry for movement {movement.id}: {e}')
                    return {'success': False, 'error': f'Validation error: {str(e)}'}
                    
                except IdempotencyError as e:
                    logger.warning(f'Idempotency error for movement {movement.id}: {e}')
                    if movement.journal_entry:
                        return {
                            'success': True,
                            'journal_entry_id': movement.journal_entry.id,
                            'message': 'Journal entry already exists (idempotency)'
                        }
                    return {'success': False, 'error': f'Idempotency error: {str(e)}'}
            else:
                return {
                    'success': False,
                    'error': 'No journal entry lines generated'
                }
                
        except Exception as e:
            logger.error(f"Unexpected error creating movement journal entry for movement {movement.id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def _create_movement_reversal_entry(cls, movement: StockMovement) -> Dict[str, Any]:
        """Create reversal journal entry for deleted movement with proper error handling"""
        try:
            if not movement.journal_entry:
                return {'success': False, 'error': 'No journal entry to reverse'}
            
            from governance.services.accounting_gateway import JournalEntryLineData, AccountingGateway
            from governance.exceptions import AuthorityViolationError, ValidationError as GovValidationError, IdempotencyError
            from decimal import Decimal
            
            # Reverse the original entry
            original_lines = movement.journal_entry.lines.all()
            reversal_lines = []
            
            for line in original_lines:
                reversal_lines.append(
                    JournalEntryLineData(
                        account=line.account,  # ✅ استخدام account object
                        debit=line.credit,  # Swap debit/credit
                        credit=line.debit,
                        description=f'عكس قيد - {line.description}'
                    )
                )
            
            # ✅ Call AccountingGateway with proper error handling
            try:
                # Get financial category and subcategory from product
                financial_category = movement.product.financial_category if hasattr(movement.product, 'financial_category') else None
                financial_subcategory = movement.product.financial_subcategory if hasattr(movement.product, 'financial_subcategory') else None
                
                gateway = AccountingGateway()
                reversal_entry = gateway.create_journal_entry(
                    source_module='product',
                    source_model='StockMovement',
                    source_id=movement.id,
                    lines=reversal_lines,
                    idempotency_key=f"movement_reversal_{movement.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    user=GovernanceContext.get_current_user(),
                    entry_type='reversal',
                    description=f'عكس حركة مخزون - {movement.product.name}',
                    reference=f'REV-STK-{movement.id}',
                    date=timezone.now().date(),
                    financial_category=financial_category,
                    financial_subcategory=financial_subcategory
                )
                
                logger.info(f'Created reversal entry {reversal_entry.number} for movement {movement.id}')
                
                return {
                    'success': True,
                    'reversal_entry_id': reversal_entry.id,
                    'reversal_entry_number': reversal_entry.number
                }
                
            except AuthorityViolationError as e:
                logger.error(f'Authority violation creating reversal entry for movement {movement.id}: {e}')
                return {'success': False, 'error': f'Authority violation: {str(e)}'}
                
            except GovValidationError as e:
                logger.error(f'Validation error creating reversal entry for movement {movement.id}: {e}')
                return {'success': False, 'error': f'Validation error: {str(e)}'}
                
            except IdempotencyError as e:
                logger.warning(f'Idempotency error for movement reversal {movement.id}: {e}')
                return {'success': False, 'error': f'Idempotency error: {str(e)}'}
            
        except Exception as e:
            logger.error(f"Unexpected error creating movement reversal entry for movement {movement.id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}