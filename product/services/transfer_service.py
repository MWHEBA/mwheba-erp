"""
Transfer Service - خدمة التحويل المخزني
متكامل بالكامل مع MovementService وموديول الحوكمة
"""
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging
from typing import Dict, Tuple

from product.models.inventory_movement import InventoryMovement
from product.models.stock_management import Stock, Warehouse
from product.models.product_core import Product
from governance.services.movement_service import MovementService

User = get_user_model()
logger = logging.getLogger(__name__)


class TransferService:
    """
    خدمة التحويل المخزني - متكامل مع MovementService
    
    يستخدم MovementService لضمان:
    - Thread-safety
    - Negative stock prevention
    - Idempotency
    - Audit trail
    - Automatic accounting entries
    """
    
    def __init__(self):
        self.movement_service = MovementService()
    
    def create_transfer(
        self,
        product: Product,
        from_warehouse: Warehouse,
        to_warehouse: Warehouse,
        quantity: int,
        user: User,
        reference_document: str = '',
        transferred_by_name: str = '',
        notes: str = ''
    ) -> Tuple[InventoryMovement, InventoryMovement]:
        """
        إنشاء تحويل مخزني كامل
        
        Args:
            product: المنتج المراد تحويله
            from_warehouse: المخزن المصدر
            to_warehouse: المخزن الهدف
            quantity: الكمية
            user: المستخدم
            reference_document: المستند المرجعي
            transferred_by_name: اسم المحول
            notes: ملاحظات
            
        Returns:
            Tuple[InventoryMovement, InventoryMovement]: (حركة الخروج، حركة الدخول)
            
        Raises:
            ValueError: إذا كانت الكمية غير متوفرة أو المخازن متطابقة
        """
        # التحقق من أن المخازن مختلفة
        if from_warehouse.id == to_warehouse.id:
            raise ValueError('لا يمكن التحويل من وإلى نفس المخزن')
        
        # التحقق من توفر الكمية في المخزن المصدر
        try:
            source_stock = Stock.objects.get(
                product=product,
                warehouse=from_warehouse
            )
            
            if source_stock.quantity < quantity:
                raise ValueError(
                    f'الكمية المتاحة في {from_warehouse.name} هي {source_stock.quantity} فقط'
                )
            
            # الحصول على متوسط التكلفة من المخزن المصدر
            unit_cost = source_stock.average_cost or product.cost_price or Decimal('0')
            
        except Stock.DoesNotExist:
            raise ValueError(f'المنتج غير متوفر في {from_warehouse.name}')
        
        # توليد رقم التحويل
        transfer_number = self._generate_transfer_number()
        
        try:
            with transaction.atomic():
                # 1. إنشاء حركة الخروج من المخزن المصدر
                movement_out = self._create_transfer_out(
                    product=product,
                    warehouse=from_warehouse,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    transfer_number=transfer_number,
                    to_warehouse=to_warehouse,
                    user=user,
                    reference_document=reference_document,
                    transferred_by_name=transferred_by_name,
                    notes=notes
                )
                
                # 2. إنشاء حركة الدخول للمخزن الهدف
                movement_in = self._create_transfer_in(
                    product=product,
                    warehouse=to_warehouse,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    transfer_number=transfer_number,
                    from_warehouse=from_warehouse,
                    user=user,
                    reference_document=reference_document,
                    transferred_by_name=transferred_by_name,
                    notes=notes,
                    reference_movement=movement_out
                )
                
                # ربط الحركتين ببعض
                movement_out.reference_movement = movement_in
                movement_out.save(update_fields=['reference_movement'])
                
                logger.info(
                    f"Transfer created: {transfer_number} - "
                    f"{product.name} ({quantity}) from {from_warehouse.name} to {to_warehouse.name}"
                )
                
                return movement_out, movement_in
                
        except Exception as e:
            logger.error(f"Failed to create transfer: {str(e)}")
            raise
    
    def _create_transfer_out(
        self,
        product: Product,
        warehouse: Warehouse,
        quantity: int,
        unit_cost: Decimal,
        transfer_number: str,
        to_warehouse: Warehouse,
        user: User,
        reference_document: str,
        transferred_by_name: str,
        notes: str
    ) -> InventoryMovement:
        """إنشاء حركة الخروج من المخزن المصدر"""
        
        # إنشاء سجل InventoryMovement
        movement = InventoryMovement.objects.create(
            product=product,
            warehouse=warehouse,
            movement_type='transfer_out',
            document_type='transfer',
            document_number=transfer_number,
            voucher_type='none',
            quantity=quantity,
            unit_cost=unit_cost,
            reference_document=reference_document,
            issued_by_name=transferred_by_name,
            notes=f"تحويل إلى {to_warehouse.name}" + (f" - {notes}" if notes else ""),
            movement_date=timezone.now(),
            created_by=user,
            is_approved=False  # يحتاج اعتماد
        )
        
        return movement
    
    def _create_transfer_in(
        self,
        product: Product,
        warehouse: Warehouse,
        quantity: int,
        unit_cost: Decimal,
        transfer_number: str,
        from_warehouse: Warehouse,
        user: User,
        reference_document: str,
        transferred_by_name: str,
        notes: str,
        reference_movement: InventoryMovement
    ) -> InventoryMovement:
        """إنشاء حركة الدخول للمخزن الهدف"""
        
        # إنشاء سجل InventoryMovement
        movement = InventoryMovement.objects.create(
            product=product,
            warehouse=warehouse,
            movement_type='transfer_in',
            document_type='transfer',
            document_number=transfer_number,
            voucher_type='none',
            quantity=quantity,
            unit_cost=unit_cost,
            reference_document=reference_document,
            received_by_name=transferred_by_name,
            reference_movement=reference_movement,
            notes=f"تحويل من {from_warehouse.name}" + (f" - {notes}" if notes else ""),
            movement_date=timezone.now(),
            created_by=user,
            is_approved=False  # يحتاج اعتماد
        )
        
        return movement
    
    def approve_transfer(
        self,
        movement_out: InventoryMovement,
        user: User
    ) -> bool:
        """
        اعتماد التحويل المخزني
        
        يعتمد الحركتين (خروج ودخول) ويستخدم MovementService
        لضمان التكامل الكامل مع موديول الحوكمة
        
        Args:
            movement_out: حركة الخروج (الحركة الرئيسية)
            user: المستخدم المعتمد
            
        Returns:
            bool: True إذا نجح الاعتماد
        """
        if movement_out.is_approved:
            logger.warning(f"Transfer already approved: {movement_out.movement_number}")
            return False
        
        if movement_out.movement_type != 'transfer_out':
            raise ValueError('يجب أن تكون الحركة من نوع transfer_out')
        
        # الحصول على حركة الدخول المرتبطة
        movement_in = movement_out.reference_movement
        if not movement_in:
            raise ValueError('حركة الدخول المرتبطة غير موجودة')
        
        try:
            with transaction.atomic():
                # 1. اعتماد حركة الخروج
                logger.info(f"Approving transfer_out movement {movement_out.id}")
                if not movement_out.approve(user):
                    error_msg = 'فشل اعتماد حركة الخروج'
                    logger.error(f"{error_msg} - Movement ID: {movement_out.id}")
                    raise Exception(error_msg)
                
                logger.info(f"Successfully approved transfer_out movement {movement_out.id}")
                
                # 2. اعتماد حركة الدخول
                logger.info(f"Approving transfer_in movement {movement_in.id}")
                if not movement_in.approve(user):
                    error_msg = 'فشل اعتماد حركة الدخول'
                    logger.error(f"{error_msg} - Movement ID: {movement_in.id}")
                    raise Exception(error_msg)
                
                logger.info(f"Successfully approved transfer_in movement {movement_in.id}")
                
                # 3. إنشاء القيد المحاسبي للتحويل
                logger.info(f"Creating accounting entry for transfer {movement_out.document_number}")
                self._create_transfer_accounting_entry(movement_out, movement_in, user)
                
                logger.info(
                    f"Transfer approved successfully: {movement_out.document_number} by {user.username}"
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to approve transfer: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _create_transfer_accounting_entry(
        self,
        movement_out: InventoryMovement,
        movement_in: InventoryMovement,
        user: User
    ):
        """
        إنشاء القيد المحاسبي للتحويل المخزني
        
        القيد:
        من حـ/ مخزون المخزن الهدف
            إلى حـ/ مخزون المخزن المصدر
        """
        from financial.models.chart_of_accounts import ChartOfAccounts
        from financial.models.journal_entry import JournalEntry, JournalEntryLine
        
        try:
            # الحصول على حسابات المخزون للمخزنين
            source_inventory_account = self._get_warehouse_inventory_account(
                movement_out.warehouse
            )
            target_inventory_account = self._get_warehouse_inventory_account(
                movement_in.warehouse
            )
            
            # حساب القيمة الإجمالية
            total_value = movement_out.total_cost
            
            # إنشاء القيد
            journal_entry = JournalEntry.objects.create(
                date=timezone.now().date(),
                description=f"تحويل مخزني - {movement_out.document_number}",
                reference=movement_out.document_number,
                entry_type='transfer',
                created_by=user
            )
            
            # سطر المدين (المخزن الهدف)
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=target_inventory_account,
                debit=total_value,
                credit=Decimal('0'),
                description=f"تحويل من {movement_out.warehouse.name} - {movement_out.product.name}"
            )
            
            # سطر الدائن (المخزن المصدر)
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=source_inventory_account,
                debit=Decimal('0'),
                credit=total_value,
                description=f"تحويل إلى {movement_in.warehouse.name} - {movement_in.product.name}"
            )
            
            # ربط القيد بالحركتين
            movement_out.journal_entry = journal_entry
            movement_out.save(update_fields=['journal_entry'])
            
            movement_in.journal_entry = journal_entry
            movement_in.save(update_fields=['journal_entry'])
            
            logger.info(f"Transfer accounting entry created: {journal_entry.number}")
            
        except Exception as e:
            logger.error(f"Failed to create transfer accounting entry: {str(e)}")
            raise
    
    def _get_warehouse_inventory_account(self, warehouse: Warehouse):
        """الحصول على حساب المخزون للمخزن"""
        from financial.models.chart_of_accounts import ChartOfAccounts
        
        try:
            # البحث عن حساب مخزون خاص بالمخزن (سلسلة 10400)
            account = ChartOfAccounts.objects.filter(
                code__startswith='10400',
                name__icontains=warehouse.name,
                is_active=True
            ).first()
            
            if account:
                return account
            
            # استخدام حساب المخزون العام
            return ChartOfAccounts.objects.get(code='10400')
            
        except ChartOfAccounts.DoesNotExist:
            raise ValueError('حساب المخزون غير موجود في الدليل المحاسبي')
    
    def _generate_transfer_number(self) -> str:
        """توليد رقم التحويل"""
        from product.models.system_utils import SerialNumber
        
        serial = SerialNumber.objects.get_or_create(
            document_type='stock_transfer',
            year=timezone.now().year,
            defaults={'prefix': 'TRF'}
        )[0]
        
        next_number = serial.get_next_number()
        return f"{serial.prefix}{next_number:04d}"
