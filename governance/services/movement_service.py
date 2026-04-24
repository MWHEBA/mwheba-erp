"""
MovementService - Thread-Safe Central Service for Stock Movement Processing

This service is the single entry point for processing stock movements in the system.
It provides thread-safe operations, negative stock prevention, and integration with
the AccountingGateway for automatic journal entry creation.

Key Features:
- Thread-safe stock movement processing with proper locking
- Negative stock prevention with invariant enforcement
- Integration with IdempotencyService to prevent duplicate movements
- Automatic journal entry creation through AccountingGateway
- Audit trail creation for all stock operations
- Support for concurrent access with database-appropriate locking

Usage:
    service = MovementService()
    movement = service.process_movement(
        product_id=123,
        quantity_change=Decimal('10.00'),
        movement_type='in',
        source_reference='PO-001',
        idempotency_key='SM:product:StockMovement:123:create',
        user=request.user
    )
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

from django.db import transaction, connection
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.apps import apps

from ..models import IdempotencyRecord, AuditTrail, GovernanceContext, QuarantineRecord
from ..exceptions import (
    GovernanceError, AuthorityViolationError, ValidationError as GovValidationError,
    ConcurrencyError, IdempotencyError
)
from ..thread_safety import DatabaseLockManager, IdempotencyLock, monitor_operation
from .idempotency_service import IdempotencyService
from .audit_service import AuditService
from .authority_service import AuthorityService
from .accounting_gateway import AccountingGateway, create_stock_movement_entry
from .quarantine_service import QuarantineService

# Import product models
from product.models.stock_management import Stock, StockMovement

User = get_user_model()
logger = logging.getLogger(__name__)


class MovementType(Enum):
    """Enumeration of stock movement types"""
    IN = 'in'
    OUT = 'out'
    ADJUSTMENT = 'adjustment'
    TRANSFER = 'transfer'


class MovementService:
    """
    Thread-safe central service for all stock movement processing.
    
    This class enforces the single entry point pattern for stock movements,
    ensuring data integrity, negative stock prevention, and automatic
    accounting integration.
    """
    
    def __init__(self):
        """Initialize the MovementService with required services"""
        self.idempotency_service = IdempotencyService
        self.audit_service = AuditService
        self.authority_service = AuthorityService
        self.accounting_gateway = AccountingGateway()
        self.quarantine_service = QuarantineService
    
    def process_movement(
        self,
        product_id: int,
        quantity_change: Decimal,
        movement_type: str,
        source_reference: str,
        idempotency_key: str,
        user: User,
        unit_cost: Optional[Decimal] = None,
        document_number: Optional[str] = None,
        notes: str = '',
        movement_date: Optional[datetime] = None,
        warehouse_id: Optional[int] = None
    ) -> StockMovement:
        """
        Process stock movement with full validation and thread-safety.
        
        This is the main entry point for processing stock movements. It enforces
        all governance rules, prevents negative stock, and creates corresponding
        journal entries through the AccountingGateway.
        
        Args:
            product_id: ID of the product
            quantity_change: Quantity change (positive for in, negative for out)
            movement_type: Type of movement ('in', 'out', 'adjustment', 'transfer')
            source_reference: Reference to source document/transaction
            idempotency_key: Unique key to prevent duplicate operations
            user: User processing the movement
            unit_cost: Unit cost for the movement (required for 'in' movements)
            document_number: Document number for reference
            notes: Additional notes
            movement_date: Movement date (defaults to today)
            
        Returns:
            StockMovement: The created stock movement record
            
        Raises:
            AuthorityViolationError: If service lacks authority
            ValidationError: If validation fails
            IdempotencyError: If idempotency check fails
            ConcurrencyError: If concurrency conflict occurs
        """
        operation_start = timezone.now()
        
        try:
            with monitor_operation("movement_service_process_movement"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='MovementService',
                    operation='process_movement'
                )
                
                # Validate authority
                self._validate_authority()
                
                # Validate movement parameters
                self._validate_movement_parameters(
                    product_id, quantity_change, movement_type, unit_cost
                )
                
                # Check idempotency
                is_duplicate, existing_record, existing_data = self.idempotency_service.check_and_record_operation(
                    operation_type='stock_movement',
                    idempotency_key=idempotency_key,
                    result_data={},  # Will be updated after creation
                    user=user,
                    expires_in_hours=24
                )
                
                if is_duplicate:
                    logger.info(f"Duplicate stock movement detected: {idempotency_key}")
                    # Return existing stock movement
                    movement_id = existing_data.get('stock_movement_id')
                    if movement_id:
                        return StockMovement.objects.get(id=movement_id)
                    else:
                        raise IdempotencyError(
                            operation_type='stock_movement',
                            idempotency_key=idempotency_key,
                            context={'error': 'Existing record found but no stock movement ID'}
                        )
                
                # Process movement with thread-safe transaction
                stock_movement = self._process_movement_atomic(
                    product_id=product_id,
                    quantity_change=quantity_change,
                    movement_type=movement_type,
                    source_reference=source_reference,
                    idempotency_key=idempotency_key,
                    user=user,
                    unit_cost=unit_cost,
                    document_number=document_number,
                    notes=notes,
                    movement_date=movement_date,
                    warehouse_id=warehouse_id
                )
                
                # Update idempotency record with result
                existing_record.result_data = {
                    'stock_movement_id': stock_movement.id,
                    'product_id': product_id,
                    'quantity_change': str(quantity_change),
                    'movement_type': movement_type,
                    'new_stock_level': str(stock_movement.quantity_after),
                    'created_at': stock_movement.timestamp.isoformat()
                }
                existing_record.save()
                
                # Create audit trail
                self.audit_service.log_operation(
                    model_name='StockMovement',
                    object_id=stock_movement.id,
                    operation='CREATE',
                    user=user,
                    source_service='MovementService',
                    after_data={
                        'product_id': product_id,
                        'quantity_change': str(quantity_change),
                        'movement_type': movement_type,
                        'quantity_before': str(stock_movement.quantity_before),
                        'quantity_after': str(stock_movement.quantity_after),
                        'reference_number': source_reference
                    },
                    idempotency_key=idempotency_key,
                    operation_duration=(timezone.now() - operation_start).total_seconds()
                )
                
                logger.info(
                    f"Stock movement processed successfully: {stock_movement.id} "
                    f"for product {product_id}, quantity {quantity_change}"
                )
                
                return stock_movement
                
        except Exception as e:
            logger.error(
                f"Failed to process stock movement for product {product_id}: {str(e)}"
            )
            
            # Create audit trail for failure
            self.audit_service.log_operation(
                model_name='StockMovement',
                object_id=0,  # No movement created
                operation='CREATE_FAILED',
                user=user,
                source_service='MovementService',
                additional_context={
                    'error': str(e),
                    'product_id': product_id,
                    'quantity_change': str(quantity_change),
                    'movement_type': movement_type,
                    'idempotency_key': idempotency_key
                }
            )
            
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def _process_movement_atomic(
        self,
        product_id: int,
        quantity_change: Decimal,
        movement_type: str,
        source_reference: str,
        idempotency_key: str,
        user: User,
        unit_cost: Optional[Decimal],
        document_number: Optional[str],
        notes: str,
        movement_date: Optional[datetime],
        warehouse_id: Optional[int] = None
    ) -> StockMovement:
        """
        Process stock movement within atomic transaction with proper locking.
        
        This method handles the actual database operations with appropriate
        locking mechanisms for thread safety and negative stock prevention.
        
        Requirements 2.4, 2.7: Ensure atomic updates of stock and journal entries
        """
        with DatabaseLockManager.atomic_operation():
            # Get warehouse - use provided warehouse_id or fall back to default
            if warehouse_id:
                from product.models.stock_management import Warehouse
                try:
                    warehouse = Warehouse.objects.get(id=warehouse_id, is_active=True)
                except Warehouse.DoesNotExist:
                    warehouse = self._get_default_warehouse()
            else:
                warehouse = self._get_default_warehouse()
            
            # Get current stock with appropriate locking
            current_stock = self.get_current_stock(product_id, warehouse.id)
            
            # Validate stock operation (including negative stock check)
            self._validate_stock_operation(product_id, quantity_change, current_stock)
            
            # Calculate new stock level
            new_stock_level = current_stock + quantity_change
            
            # Get or create Stock record
            stock_record = self._get_or_create_stock_record(product_id, warehouse.id)
            
            # Create StockMovement record
            movement_date = movement_date or timezone.now()
            
            # Set unit cost - use provided unit_cost or get from product
            if unit_cost is None:
                # Get unit cost from product
                from product.models.product_core import Product
                try:
                    product = Product.objects.get(id=product_id)
                    unit_cost = product.cost_price or Decimal('0')
                except Product.DoesNotExist:
                    unit_cost = Decimal('0')
            
            # Determine document_type from source_reference
            document_type = self._determine_document_type(source_reference, movement_type)
            
            stock_movement = StockMovement(
                product_id=product_id,
                warehouse=warehouse,
                movement_type=movement_type,
                quantity=abs(quantity_change),  # Store absolute quantity
                unit_cost=unit_cost,
                quantity_before=int(current_stock),  # Convert to int for PositiveIntegerField
                quantity_after=int(new_stock_level),  # Convert to int for PositiveIntegerField
                timestamp=movement_date,
                reference_number=source_reference,
                document_number=document_number,
                document_type=document_type,
                notes=notes,
                idempotency_key=idempotency_key,
                created_by_service='MovementService',
                created_by=user
            )
            
            # Mark as service approved to avoid development warnings
            stock_movement.mark_as_service_approved()
            # Set flag to skip automatic journal entry creation in save()
            # because we'll create it explicitly below via _create_accounting_entry()
            stock_movement._skip_journal_entry = True
            # Set flag to skip stock quantity update in signal (StockOrchestratorService)
            # because we update stock_record directly below - prevents double update
            stock_movement._skip_update = True
            stock_movement.save()
            
            # Update Stock record
            stock_record.quantity = new_stock_level
            stock_record.last_movement_date = movement_date
            stock_record.last_movement_service = 'MovementService'
            stock_record.mark_as_service_approved()
            stock_record.save()
            
            # Create corresponding journal entry through AccountingGateway
            # This MUST happen within the same transaction to ensure atomicity (Requirement 2.4)
            journal_entry = None
            try:
                journal_entry = self._create_accounting_entry(stock_movement, user)
                stock_movement.journal_entry = journal_entry
                stock_movement.save(update_fields=['journal_entry'])
                
                logger.info(f"Journal entry created for stock movement: {journal_entry.number}")
                
            except Exception as e:
                logger.error(f"Failed to create journal entry for stock movement {stock_movement.id}: {str(e)}")
                # For critical stock-accounting integration, we should fail the entire operation
                # if journal entry creation fails (Requirement 2.7)
                self.quarantine_service.quarantine_data(
                    model_name='StockMovement',
                    object_id=stock_movement.id,
                    corruption_type='missing_journal_entry',
                    reason=f"Failed to create journal entry: {str(e)}",
                    original_data={
                        'stock_movement_id': stock_movement.id,
                        'product_id': product_id,
                        'quantity_change': str(quantity_change),
                        'error': str(e)
                    },
                    user=user
                )
                # Re-raise the exception to fail the entire transaction
                raise GovValidationError(
                message=f"Failed to create journal entry for stock movement: {str(e)}",
                context={
                        'stock_movement_id': stock_movement.id,
                        'product_id': product_id,
                        'error': str(e)
                    }
                )
            
            return stock_movement
    
    def _create_accounting_entry(self, stock_movement: StockMovement, user: User):
        """
        Create corresponding journal entry through AccountingGateway.
        
        This implements the critical stock-accounting integration workflow.
        """
        # Generate idempotency key for journal entry
        # Use the stock movement's idempotency key as part of the journal entry key
        # to ensure uniqueness while maintaining traceability
        je_idempotency_key = f"JE:SM:{stock_movement.id}:create"
        
        # Create journal entry using the convenience function
        return create_stock_movement_entry(
            stock_movement=stock_movement,
            user=user,
            idempotency_key=je_idempotency_key
        )
    
    def get_current_stock(self, product_id: int, warehouse_id: Optional[int] = None) -> Decimal:
        """
        Get current stock level with database-appropriate locking.
        
        Args:
            product_id: Product ID to get stock for
            warehouse_id: Warehouse ID (optional, uses default if not provided)
            
        Returns:
            Decimal: Current stock quantity
        """
        if warehouse_id is None:
            default_warehouse = self._get_default_warehouse()
            warehouse_id = default_warehouse.id
            
        with transaction.atomic():
            try:
                if connection.vendor == 'postgresql':
                    # Real row locking available
                    stock = Stock.objects.select_for_update().get(
                        product_id=product_id,
                        warehouse_id=warehouse_id
                    )
                else:
                    # SQLite: Best-effort with atomic block
                    stock = Stock.objects.get(
                        product_id=product_id,
                        warehouse_id=warehouse_id
                    )
                return Decimal(str(stock.quantity))
            except Stock.DoesNotExist:
                return Decimal('0')
    
    def _get_default_warehouse(self):
        """
        Get the default warehouse for stock movements.
        
        Returns:
            Warehouse: Default warehouse instance
        """
        from product.models.stock_management import Warehouse
        
        # Try to get the first active warehouse as default
        try:
            return Warehouse.objects.filter(is_active=True).first()
        except Warehouse.DoesNotExist:
            raise GovValidationError(
                message="No active warehouse found",
                context={}
            )
    
    def _get_or_create_stock_record(self, product_id: int, warehouse_id: Optional[int] = None) -> Stock:
        """
        Get or create Stock record for the product and warehouse.
        
        Args:
            product_id: Product ID
            warehouse_id: Warehouse ID (optional, uses default if not provided)
            
        Returns:
            Stock: Stock record
        """
        if warehouse_id is None:
            default_warehouse = self._get_default_warehouse()
            warehouse_id = default_warehouse.id
            
        try:
            if connection.vendor == 'postgresql':
                stock = Stock.objects.select_for_update().get(
                    product_id=product_id,
                    warehouse_id=warehouse_id
                )
            else:
                stock = Stock.objects.get(
                    product_id=product_id,
                    warehouse_id=warehouse_id
                )
        except Stock.DoesNotExist:
            # Create new stock record
            stock = Stock(
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=0,
                last_movement_date=timezone.now(),
                last_movement_service='MovementService'
            )
            stock.mark_as_service_approved()
            stock.save()
        
        return stock
    
    def _validate_authority(self) -> None:
        """
        Validate that MovementService has authority to process stock movements.
        
        Raises:
            AuthorityViolationError: If authority validation fails
        """
        # Check authority for Stock operations
        if not self.authority_service.validate_authority(
            service_name='MovementService',
            model_name='Stock',
            operation='UPDATE'
        ):
            raise AuthorityViolationError(
                message="MovementService lacks authority to update Stock records",
                error_code="AUTHORITY_VIOLATION",
                context={
                    'service': 'MovementService',
                    'model': 'Stock',
                    'operation': 'UPDATE'
                }
            )
        
        # Check authority for StockMovement operations
        if not self.authority_service.validate_authority(
            service_name='MovementService',
            model_name='StockMovement',
            operation='CREATE'
        ):
            raise AuthorityViolationError(
                message="MovementService lacks authority to create StockMovement records",
                error_code="AUTHORITY_VIOLATION",
                context={
                    'service': 'MovementService',
                    'model': 'StockMovement',
                    'operation': 'CREATE'
                }
            )
    
    def _validate_movement_parameters(
        self,
        product_id: int,
        quantity_change: Decimal,
        movement_type: str,
        unit_cost: Optional[Decimal]
    ) -> None:
        """
        Validate movement parameters.
        
        Args:
            product_id: Product ID
            quantity_change: Quantity change
            movement_type: Movement type
            unit_cost: Unit cost
            
        Raises:
            ValidationError: If validation fails
        """
        # Validate product exists
        from product.models.product_core import Product
        try:
            Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise GovValidationError(
                message=f"Product not found or inactive: {product_id}",
                context={'product_id': product_id}
            )
        
        # Validate movement type
        valid_types = [mt.value for mt in MovementType]
        if movement_type not in valid_types:
            raise GovValidationError(
                message=f"Invalid movement type: {movement_type}",
                context={
                    'movement_type': movement_type,
                    'valid_types': valid_types
                }
            )
        
        # Validate quantity change
        if quantity_change == 0:
            raise GovValidationError(
                message="Quantity change cannot be zero",
                context={'quantity_change': str(quantity_change)}
            )
        
        # Validate unit cost for inbound movements
        if movement_type == 'in' and (unit_cost is None or unit_cost <= 0):
            raise GovValidationError(
                message="Unit cost is required and must be positive for inbound movements",
                context={
                    'movement_type': movement_type,
                    'unit_cost': str(unit_cost) if unit_cost else None
                }
            )
    
    def _validate_stock_operation(
        self,
        product_id: int,
        quantity_change: Decimal,
        current_stock: Decimal
    ) -> None:
        """
        Validate stock operation with negative stock prevention.
        
        Args:
            product_id: Product ID
            quantity_change: Quantity change
            current_stock: Current stock level
            
        Raises:
            ValidationError: If operation would result in negative stock
        """
        new_stock_level = current_stock + quantity_change
        
        if new_stock_level < 0:
            # This is a critical violation - create audit trail and quarantine
            violation_data = {
                'product_id': product_id,
                'current_stock': str(current_stock),
                'quantity_change': str(quantity_change),
                'would_result_in': str(new_stock_level),
                'violation_type': 'negative_stock_attempt'
            }
            
            # Create audit trail for violation attempt
            self.audit_service.log_operation(
                model_name='Stock',
                object_id=product_id,
                operation='NEGATIVE_STOCK_VIOLATION',
                user=GovernanceContext.get_current_user(),
                source_service='MovementService',
                additional_context=violation_data
            )
            
            # Quarantine the violation attempt
            self.quarantine_service.quarantine_data(
                model_name='StockMovement',
                object_id=0,  # No movement created yet
                corruption_type='negative_stock_attempt',
                reason=f"Attempted to create negative stock: {current_stock} + {quantity_change} = {new_stock_level}",
                original_data=violation_data,
                user=GovernanceContext.get_current_user()
            )
            
            raise GovValidationError(
                message=f"Insufficient stock: current {current_stock}, requested {abs(quantity_change)}, would result in {new_stock_level}",
                context=violation_data
            )
    
    def validate_sufficient_stock(self, product_id: int, quantity: Decimal) -> bool:
        """
        Check if sufficient stock exists for outbound movement.
        
        Args:
            product_id: Product ID
            quantity: Required quantity (positive value)
            
        Returns:
            bool: True if sufficient stock exists
        """
        current_stock = self.get_current_stock(product_id)
        return current_stock >= quantity
    
    def _determine_document_type(self, source_reference: str, movement_type: str) -> str:
        """
        Determine document_type from source_reference pattern.
        
        Args:
            source_reference: Reference string (e.g., 'SALE_ITEM_32', 'PUR-INV-001')
            movement_type: Movement type ('in', 'out', etc.)
            
        Returns:
            str: Document type ('sale', 'purchase', 'sale_return', 'purchase_return', 'transfer', 'adjustment', 'other')
        """
        if not source_reference:
            return 'other'
        
        ref_upper = source_reference.upper()
        
        # Check for sale operations
        if 'SALE_ITEM_' in ref_upper or 'SALE_' in ref_upper or 'SAL-' in ref_upper:
            if 'RETURN' in ref_upper or 'CANCEL' in ref_upper:
                return 'sale_return'
            return 'sale'
        
        # Check for purchase operations
        if 'PURCHASE_ITEM_' in ref_upper or 'PURCHASE_' in ref_upper or 'PUR-' in ref_upper or 'PURCHASE-' in ref_upper:
            if 'RETURN' in ref_upper or 'CANCEL' in ref_upper:
                return 'purchase_return'
            return 'purchase'
        
        # Check for transfer operations
        if 'TRANSFER' in ref_upper:
            return 'transfer'
        
        # Check for adjustment/inventory operations
        if 'ADJUSTMENT' in ref_upper or 'INVENTORY' in ref_upper or 'STOCK_TAKE' in ref_upper:
            return 'adjustment'
        
        # Check for opening balance
        if 'OPENING' in ref_upper or 'INITIAL' in ref_upper:
            return 'opening'
        
        # Default based on movement_type
        if movement_type == 'adjustment':
            return 'adjustment'
        elif movement_type == 'transfer':
            return 'transfer'
        
        return 'other'
    
    def get_movement_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about stock movements processed through the service.
        
        Returns:
            Dict: Statistics including counts, amounts, and performance metrics
        """
        from django.db.models import Count, Sum, Avg
        
        stats = {}
        
        # Basic counts
        total_movements = StockMovement.objects.filter(
            created_by_service='MovementService'
        ).count()
        stats['total_movements'] = total_movements
        
        if total_movements == 0:
            return stats
        
        # Count by movement type
        type_counts = StockMovement.objects.filter(
            created_by_service='MovementService'
        ).values('movement_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        stats['by_type'] = {
            item['movement_type']: item['count']
            for item in type_counts
        }
        
        # Total value (calculated from quantity * unit_cost)
        from django.db.models import F
        total_value = StockMovement.objects.filter(
            created_by_service='MovementService'
        ).aggregate(
            total=Sum(F('quantity') * F('unit_cost'))
        )['total'] or Decimal('0')
        
        stats['total_value'] = str(total_value)
        
        # Recent activity (last 24 hours)
        recent_cutoff = timezone.now() - timedelta(hours=24)
        stats['recent_movements'] = StockMovement.objects.filter(
            created_by_service='MovementService',
            timestamp__gte=recent_cutoff
        ).count()
        
        # Negative stock violations
        violation_count = QuarantineRecord.objects.filter(
            corruption_type='negative_stock_attempt'
        ).count()
        stats['negative_stock_violations'] = violation_count
        
        return stats
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of the MovementService.
        
        Returns:
            Dict: Health status with recommendations
        """
        stats = self.get_movement_statistics()
        
        health = {
            'status': 'healthy',
            'issues': [],
            'recommendations': [],
            'metrics': {
                'total_movements': stats.get('total_movements', 0),
                'recent_activity': stats.get('recent_movements', 0),
                'negative_stock_violations': stats.get('negative_stock_violations', 0)
            }
        }
        
        # Check for issues
        if stats.get('recent_movements', 0) == 0:
            health['issues'].append('No recent stock movement activity')
        
        if stats.get('negative_stock_violations', 0) > 0:
            health['status'] = 'warning'
            health['issues'].append(f"{stats['negative_stock_violations']} negative stock violations detected")
            health['recommendations'].append('Review quarantined negative stock attempts')
        
        # Check idempotency service health
        idempotency_health = self.idempotency_service.get_health_status()
        if idempotency_health['status'] != 'healthy':
            health['status'] = 'warning'
            health['issues'].append('Idempotency service issues detected')
            health['recommendations'].extend(idempotency_health['recommendations'])
        
        return health