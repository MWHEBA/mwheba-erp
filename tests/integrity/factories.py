"""
Test Data Factory for System Integrity Testing

Factory methods for creating test data with proper relationships and expected outcomes.
"""

import factory
from factory.django import DjangoModelFactory
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

User = get_user_model()


class IntegrityTestDataFactory:
    """
    Factory for creating test data with proper relationships for integrity testing.
    """
    
    @staticmethod
    def create_test_user(username="test_user", is_superuser=False, is_staff=None):
        """Create a test user for integrity testing"""
        from django.utils import timezone
        
        # Generate unique username and email with timestamp
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S%f')
        unique_username = f"{username}_{timestamp}"
        unique_email = f"{username}_{timestamp}@test.com"
        
        # Default is_staff to is_superuser if not explicitly set
        if is_staff is None:
            is_staff = is_superuser
        
        return User.objects.create_user(
            username=unique_username,
            email=unique_email,
            password="test_password",
            is_superuser=is_superuser,
            is_staff=is_staff
        )
    
    @staticmethod
    def create_test_warehouse(name="Test Warehouse", code="TEST_WH"):
        """Create a test warehouse"""
        from product.models import Warehouse
        
        return Warehouse.objects.create(
            name=name,
            code=code,
            location="Test Location"
        )
    
    @staticmethod
    def create_test_product(name="Test Product", code="TEST_PROD", cost_price=100.00, created_by=None):
        """Create a test product with category and unit"""
        from product.models import Product, Category, Unit
        
        # Create or get category
        category, _ = Category.objects.get_or_create(
            name="Test Category",
            defaults={'code': 'TEST_CAT'}
        )
        
        # Create or get unit
        unit, _ = Unit.objects.get_or_create(
            name="Test Unit",
            defaults={'symbol': 'TU'}
        )
        
        # Create a user if not provided
        if created_by is None:
            # Create unique user for this product
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            created_by = IntegrityTestDataFactory.create_test_user(f"product_creator_{unique_id}")
        
        return Product.objects.create(
            name=name,
            sku=code,
            category=category,
            unit=unit,
            cost_price=Decimal(str(cost_price)),
            selling_price=Decimal(str(cost_price * 1.5)),
            created_by=created_by
        )
    
    @staticmethod
    def create_test_supplier(name="Test Supplier", code="TEST_SUP"):
        """Create a test supplier"""
        from supplier.models import Supplier
        
        return Supplier.objects.create(
            name=name,
            code=code,
            phone="123456789",
            email=f"{code.lower()}@test.com"
        )
    
    @staticmethod
    def create_test_customer(name="Test Customer", code="TEST_CUST"):
        """Create a test customer for sale operations"""
        from client.models import Customer
        
        return Customer.objects.create(
            name=name,
            code=code,
            phone="123456789",
            email=f"{code.lower()}@test.com"
        )
    
    @staticmethod
    def create_stock_with_constraints(product, warehouse, quantity=100, reserved_quantity=0):
        """Create stock with specific quantity constraints for testing"""
        from product.models import Stock
        
        stock, created = Stock.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={
                'quantity': Decimal(str(quantity)),
                'reserved_quantity': Decimal(str(reserved_quantity))
            }
        )
        
        if not created:
            stock.quantity = Decimal(str(quantity))
            stock.reserved_quantity = Decimal(str(reserved_quantity))
            stock.save()
        
        return stock
    
    @staticmethod
    def create_purchase_with_items(supplier, warehouse, user, items_count=3, with_stock=True):
        """Create complete purchase scenario with expected outcomes"""
        from purchase.models import Purchase, PurchaseItem
        
        # Calculate total first
        total_amount = Decimal('0.00')
        for i in range(items_count):
            quantity = Decimal('10')
            unit_price = Decimal('100') + (Decimal('10') * i)
            item_total = quantity * unit_price
            total_amount += item_total
        
        # Create purchase with calculated totals
        purchase = Purchase.objects.create(
            number=f"PUR-{timezone.now().strftime('%Y%m%d%H%M%S')}",
            date=date.today(),
            supplier=supplier,
            warehouse=warehouse,
            created_by=user,
            payment_method='cash',
            subtotal=total_amount,
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=total_amount
        )
        
        # Create items
        items = []
        
        for i in range(items_count):
            product = IntegrityTestDataFactory.create_test_product(
                name=f"Purchase Product {i+1}",
                code=f"PPUR_{i+1}_{purchase.id}",
                cost_price=100 + (i * 10)
            )
            
            if with_stock:
                IntegrityTestDataFactory.create_stock_with_constraints(
                    product=product,
                    warehouse=warehouse,
                    quantity=0,  # Start with zero stock
                    reserved_quantity=0
                )
            
            quantity = Decimal('10')
            unit_price = product.cost_price
            item_total = quantity * unit_price
            
            item = PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                discount=Decimal('0.00'),
                total=item_total
            )
            
            items.append(item)
        
        return {
            'purchase': purchase,
            'items': items,
            'expected_stock_movements': items_count,
            'expected_total': total_amount
        }
    
    # Sale methods removed - Sale module has been replaced with a generic product module
    
    @staticmethod
    def create_concurrent_scenario(operation_count=10, thread_count=5):
        """Create scenario for concurrent operation testing"""
        # Create shared resources
        user = IntegrityTestDataFactory.create_test_user("concurrent_user")
        warehouse = IntegrityTestDataFactory.create_test_warehouse("Concurrent WH", "CONC_WH")
        supplier = IntegrityTestDataFactory.create_test_supplier("Concurrent Supplier", "CONC_SUP")
        customer = IntegrityTestDataFactory.create_test_customer("Concurrent Customer", "CONC_CUST")
        
        # Create products for concurrent operations
        products = []
        for i in range(operation_count):
            product = IntegrityTestDataFactory.create_test_product(
                name=f"Concurrent Product {i+1}",
                code=f"CONC_PROD_{i+1}",
                cost_price=100
            )
            
            # Create initial stock with sufficient quantity for concurrent operations
            initial_quantity = thread_count * 100  # Ensure enough stock for all threads
            IntegrityTestDataFactory.create_stock_with_constraints(
                product=product,
                warehouse=warehouse,
                quantity=initial_quantity,
                reserved_quantity=0
            )
            
            products.append(product)
        
        # Create additional users for multi-user concurrency testing
        concurrent_users = []
        for i in range(thread_count):
            concurrent_user = IntegrityTestDataFactory.create_test_user(f"concurrent_user_{i}")
            concurrent_users.append(concurrent_user)
        
        return {
            'user': user,
            'warehouse': warehouse,
            'supplier': supplier,
            'parent': parent,
            'products': products,
            'concurrent_users': concurrent_users,
            'operation_count': operation_count,
            'thread_count': thread_count,
            'expected_operations': operation_count * thread_count
        }
    
    @staticmethod
    def create_constraint_violation_data():
        """Create data designed to violate specific constraints"""
        user = IntegrityTestDataFactory.create_test_user("constraint_user")
        warehouse = IntegrityTestDataFactory.create_test_warehouse("Constraint WH", "CONST_WH")
        product = IntegrityTestDataFactory.create_test_product("Constraint Product", "CONST_PROD")
        
        return {
            'user': user,
            'warehouse': warehouse,
            'product': product,
            'violation_scenarios': {
                'negative_stock': {
                    'quantity': -10,
                    'reserved_quantity': 0,
                    'expected_error': 'CHECK constraint failed: quantity >= 0'
                },
                'invalid_reserved': {
                    'quantity': 100,
                    'reserved_quantity': 150,  # Greater than available
                    'expected_error': 'CHECK constraint failed: reserved_quantity <= quantity'
                },
                'zero_quantity_with_reserved': {
                    'quantity': 0,
                    'reserved_quantity': 5,  # Reserved > available
                    'expected_error': 'CHECK constraint failed: reserved_quantity <= quantity'
                },
                'extreme_negative': {
                    'quantity': -999999,
                    'reserved_quantity': 0,
                    'expected_error': 'CHECK constraint failed: quantity >= 0'
                },
                'both_negative': {
                    'quantity': -10,
                    'reserved_quantity': -5,
                    'expected_error': 'CHECK constraint failed'
                }
            },
            'bulk_violation_data': [
                {'quantity': -1, 'reserved_quantity': 0},
                {'quantity': 50, 'reserved_quantity': 100},
                {'quantity': -5, 'reserved_quantity': 10},
                {'quantity': 0, 'reserved_quantity': 1}
            ]
        }
    
    @staticmethod
    def create_idempotency_test_data(operation_type="test_operation", key_suffix=None):
        """Create data for idempotency testing"""
        user = IntegrityTestDataFactory.create_test_user("idempotency_user")
        
        # Generate unique key if suffix not provided
        if key_suffix is None:
            key_suffix = timezone.now().strftime('%Y%m%d%H%M%S%f')
        
        return {
            'user': user,
            'operation_type': operation_type,
            'idempotency_key': f"test_key_{key_suffix}",
            'context_data': {
                'test_context': 'integrity_testing',
                'operation_id': f"op_{key_suffix}",
                'timestamp': timezone.now().isoformat(),
                'user_id': user.id
            },
            'result_data': {
                'test_result': 'success',
                'timestamp': timezone.now().isoformat(),
                'operation_id': 12345,
                'processed_items': 3,
                'total_amount': '1500.00'
            },
            'expected_outcomes': {
                'first_execution': 'create_new_record',
                'second_execution': 'return_existing_result',
                'concurrent_execution': 'single_winner_multiple_waiters'
            }
        }
    
    @staticmethod
    def create_purchase_scenario_with_expected_outcomes(items_count=3, scenario_type="standard"):
        """Create Purchase scenario with detailed expected outcomes"""
        user = IntegrityTestDataFactory.create_test_user("purchase_scenario_user")
        warehouse = IntegrityTestDataFactory.create_test_warehouse("Purchase WH", "PUR_WH")
        supplier = IntegrityTestDataFactory.create_test_supplier("Purchase Supplier", "PUR_SUP")
        
        # Create scenario based on type
        if scenario_type == "standard":
            purchase_data = IntegrityTestDataFactory.create_purchase_with_items(
                supplier=supplier,
                warehouse=warehouse,
                user=user,
                items_count=items_count,
                with_stock=True
            )
        elif scenario_type == "insufficient_stock":
            # Create products with insufficient stock for testing stock validation
            purchase_data = IntegrityTestDataFactory.create_purchase_with_items(
                supplier=supplier,
                warehouse=warehouse,
                user=user,
                items_count=items_count,
                with_stock=False  # No initial stock
            )
        elif scenario_type == "high_volume":
            # Create high-volume purchase for performance testing
            purchase_data = IntegrityTestDataFactory.create_purchase_with_items(
                supplier=supplier,
                warehouse=warehouse,
                user=user,
                items_count=items_count * 5,  # 5x more items
                with_stock=True
            )
        else:
            raise ValueError(f"Unknown scenario type: {scenario_type}")
        
        # Add expected outcomes
        purchase_data['expected_outcomes'] = {
            'stock_movements_count': items_count if scenario_type != "high_volume" else items_count * 5,
            'audit_trail_entries': 1,  # Purchase creation
            'idempotency_records': items_count if scenario_type != "high_volume" else items_count * 5,
            'governance_validations': ['user_permission', 'supplier_validation', 'warehouse_validation'],
            'signal_triggers': ['purchase_created', 'purchase_items_created', 'stock_movements_created']
        }
        
        return purchase_data
    
    # Sale scenario methods removed - Sale module has been replaced with a generic product module
    
    @staticmethod
    def cleanup_test_data():
        """Clean up all test data created by the factory"""
        from product.models import Stock, Product, Category, Unit, Warehouse
        from purchase.models import Purchase, PurchaseItem
        from supplier.models import Supplier
        from client.models import Customer
        from governance.models import IdempotencyRecord, AuditTrail
        
        # Clean up in reverse dependency order
        try:
            # Clean governance records
            IdempotencyRecord.objects.filter(
                operation_type__startswith='TEST_'
            ).delete()
            
            AuditTrail.objects.filter(
                source_service='IntegrityTestSuite'
            ).delete()
            
            # Clean business records
            PurchaseItem.objects.filter(
                purchase__number__startswith='PUR-'
            ).delete()
            
            Purchase.objects.filter(
                number__startswith='PUR-'
            ).delete()
            
            # Clean master data
            Stock.objects.filter(
                product__code__startswith=('TEST_', 'PPUR_', 'CONC_', 'CONST_')
            ).delete()
            
            Product.objects.filter(
                code__startswith=('TEST_', 'PPUR_', 'CONC_', 'CONST_')
            ).delete()
            
            Warehouse.objects.filter(
                code__startswith=('TEST_', 'CONC_', 'CONST_')
            ).delete()
            
            Supplier.objects.filter(
                code__startswith=('TEST_', 'CONC_', 'CONST_')
            ).delete()
            
            Customer.objects.filter(
                code__startswith=('TEST_', 'CONC_', 'CONST_')
            ).delete()
            
            # Clean test users
            User.objects.filter(
                username__in=[
                    'test_user', 'concurrent_user', 'constraint_user', 
                    'idempotency_user', 'integrity_test_user', 'admin_test_user'
                ]
            ).delete()
            
        except Exception as e:
            # Log but don't raise to avoid masking test failures
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error during test data cleanup: {e}")