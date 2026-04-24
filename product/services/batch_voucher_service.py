"""
خدمة الأذون الجماعية (Batch Voucher Service)
تدير منطق الأعمال للأذون الجماعية
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from product.models import BatchVoucher, BatchVoucherItem, InventoryMovement, Product, Warehouse
from governance.services import AccountingGateway, JournalEntryLineData
from financial.models import ChartOfAccounts


class BatchVoucherService:
    """خدمة إدارة الأذون الجماعية"""
    
    @transaction.atomic
    def create_batch_voucher(self, voucher_type, warehouse_id, user, **kwargs):
        """
        إنشاء إذن جماعي جديد
        
        Args:
            voucher_type: نوع الإذن (receipt/issue/transfer)
            warehouse_id: معرف المخزن
            user: المستخدم المنشئ
            **kwargs: بيانات إضافية (target_warehouse_id, purpose_type, party_name, etc.)
        
        Returns:
            BatchVoucher: الإذن المنشأ
        """
        warehouse = Warehouse.objects.get(id=warehouse_id)
        
        voucher_data = {
            'voucher_type': voucher_type,
            'warehouse': warehouse,
            'created_by': user,
            'status': 'draft',
        }
        
        # إضافة البيانات الإضافية
        if voucher_type == 'transfer':
            target_warehouse_id = kwargs.get('target_warehouse_id')
            if not target_warehouse_id:
                raise ValueError('المخزن الهدف مطلوب لأذون التحويل')
            voucher_data['target_warehouse'] = Warehouse.objects.get(id=target_warehouse_id)
        else:
            voucher_data['purpose_type'] = kwargs.get('purpose_type')
        
        voucher_data['notes'] = kwargs.get('notes', '')
        
        voucher = BatchVoucher.objects.create(**voucher_data)
        return voucher
    
    @transaction.atomic
    def add_item_to_batch(self, batch_voucher, product_id, quantity, unit_cost=None):
        """
        إضافة منتج للإذن الجماعي
        
        Args:
            batch_voucher: الإذن الجماعي
            product_id: معرف المنتج
            quantity: الكمية
            unit_cost: تكلفة الوحدة (اختياري - يتم حسابها تلقائياً)
        
        Returns:
            BatchVoucherItem: البند المضاف
        """
        if not batch_voucher.can_edit():
            raise ValueError('لا يمكن تعديل إذن معتمد. يمكن تعديل الأذون في حالة "مسودة" فقط.')
        
        product = Product.objects.get(id=product_id)
        
        # حساب التكلفة تلقائياً إذا لم تُحدد
        if unit_cost is None:
            unit_cost = product.cost_price or Decimal('0.00')
        
        # التحقق من عدم تكرار المنتج
        if batch_voucher.items.filter(product=product).exists():
            raise ValueError(f'المنتج "{product.name}" موجود مسبقاً في الإذن. لا يمكن إضافة نفس المنتج مرتين.')
        
        item = BatchVoucherItem.objects.create(
            batch_voucher=batch_voucher,
            product=product,
            quantity=quantity,
            unit_cost=unit_cost
        )
        
        return item
    
    @transaction.atomic
    def remove_item_from_batch(self, batch_voucher, product_id):
        """
        حذف منتج من الإذن الجماعي
        
        Args:
            batch_voucher: الإذن الجماعي
            product_id: معرف المنتج
        """
        if not batch_voucher.can_edit():
            raise ValueError('لا يمكن تعديل إذن معتمد. يمكن تعديل الأذون في حالة "مسودة" فقط.')
        
        item = batch_voucher.items.filter(product_id=product_id).first()
        if item:
            item.delete()
    
    @transaction.atomic
    def update_batch_voucher(self, batch_voucher, user, **kwargs):
        """
        تحديث بيانات الإذن الجماعي
        
        Args:
            batch_voucher: الإذن الجماعي
            user: المستخدم المعدل
            **kwargs: البيانات المراد تحديثها
        """
        if not batch_voucher.can_edit():
            raise ValueError('لا يمكن تعديل إذن معتمد. يمكن تعديل الأذون في حالة "مسودة" فقط.')
        
        # تحديث الحقول المسموحة
        allowed_fields = ['purpose_type', 'notes', 'status']
        for field in allowed_fields:
            if field in kwargs:
                setattr(batch_voucher, field, kwargs[field])
        
        batch_voucher.updated_by = user
        batch_voucher.save()
        
        return batch_voucher
    
    def _validate_approval(self, batch_voucher):
        """
        التحقق من إمكانية اعتماد الإذن
        
        Args:
            batch_voucher: الإذن الجماعي
        
        Raises:
            ValueError: إذا كان الإذن غير صالح للاعتماد
        """
        if not batch_voucher.can_approve():
            raise ValueError('لا يمكن اعتماد هذا الإذن. الإذن يجب أن يكون في حالة "مسودة" وغير معتمد مسبقاً.')
        
        if not batch_voucher.items.exists():
            raise ValueError('لا يمكن اعتماد إذن فارغ. يرجى إضافة منتج واحد على الأقل.')
        
        # للصرف والتحويل: التحقق من توفر الكمية
        if batch_voucher.voucher_type in ['issue', 'transfer']:
            from product.models import Stock
            
            insufficient_items = []
            for item in batch_voucher.items.all():
                stock = Stock.objects.filter(
                    product=item.product,
                    warehouse=batch_voucher.warehouse
                ).first()
                
                available = stock.quantity if stock else 0
                
                if available < item.quantity:
                    insufficient_items.append(
                        f'• {item.product.name}: الكمية المتاحة ({available}) أقل من المطلوبة ({item.quantity})'
                    )
            
            if insufficient_items:
                error_msg = 'لا يمكن اعتماد الإذن بسبب نقص الكميات التالية:\n\n' + '\n'.join(insufficient_items)
                error_msg += '\n\nيرجى تعديل الكميات أو اختيار مخزن آخر.'
                raise ValueError(error_msg)
    
    def _create_inventory_movements(self, batch_voucher, user):
        """
        إنشاء حركات المخزون لجميع بنود الإذن
        
        Args:
            batch_voucher: الإذن الجماعي
            user: المستخدم المعتمد
        """
        movement_type_map = {
            'receipt': 'in',
            'issue': 'out',
            'transfer': 'transfer_out',
        }
        
        # توليد أرقام الحركات مسبقاً لتجنب race condition
        from product.models.system_utils import SerialNumber
        
        serial, created = SerialNumber.objects.get_or_create(
            document_type="inventory_movement",
            year=batch_voucher.voucher_date.year,
            defaults={"prefix": "INV", "last_number": 0},
        )
        
        # إذا كان SerialNumber جديد، نتحقق من آخر رقم موجود في الـ database
        if created or serial.last_number == 0:
            last_movement = InventoryMovement.objects.filter(
                movement_number__startswith=serial.prefix
            ).order_by('-movement_number').first()
            
            if last_movement:
                try:
                    last_num = int(last_movement.movement_number.replace(serial.prefix, ''))
                    if last_num > serial.last_number:
                        serial.last_number = last_num
                        serial.save()
                except ValueError:
                    pass
        
        for item in batch_voucher.items.all():
            # توليد رقم الحركة مسبقاً
            movement_number = serial.get_next_number()
            movement_number_str = f"{serial.prefix}{movement_number:04d}"
            
            # إنشاء الحركة الأساسية
            movement = InventoryMovement.objects.create(
                movement_number=movement_number_str,
                product=item.product,
                warehouse=batch_voucher.warehouse,
                movement_type=movement_type_map[batch_voucher.voucher_type],
                document_type='batch_voucher',
                document_number=batch_voucher.voucher_number,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
                voucher_type=batch_voucher.voucher_type,
                purpose_type=batch_voucher.purpose_type,
                notes=f'إذن جماعي: {batch_voucher.voucher_number}',
                movement_date=batch_voucher.voucher_date,
                created_by=user,
                batch_voucher=batch_voucher
            )
            
            # اعتماد الحركة
            if not movement.approve(user):
                raise ValueError(f'فشل اعتماد حركة المنتج {item.product.name}')
            
            # ربط الحركة بالبند
            item.inventory_movement = movement
            item.save(update_fields=['inventory_movement'])
            
            # للتحويل: إنشاء حركة الدخول للمخزن الهدف
            if batch_voucher.voucher_type == 'transfer':
                movement_in_number = serial.get_next_number()
                movement_in_number_str = f"{serial.prefix}{movement_in_number:04d}"
                
                movement_in = InventoryMovement.objects.create(
                    movement_number=movement_in_number_str,
                    product=item.product,
                    warehouse=batch_voucher.target_warehouse,
                    movement_type='transfer_in',
                    document_type='batch_voucher',
                    document_number=batch_voucher.voucher_number,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    reference_movement=movement,
                    notes=f'إذن جماعي: {batch_voucher.voucher_number} - من {batch_voucher.warehouse.name}',
                    movement_date=batch_voucher.voucher_date,
                    created_by=user,
                    batch_voucher=batch_voucher
                )
                
                if not movement_in.approve(user):
                    raise ValueError(f'فشل اعتماد حركة الدخول للمنتج {item.product.name}')
    
    def _create_batch_accounting_entry(self, batch_voucher, user):
        """
        إنشاء قيد محاسبي موحد لجميع بنود الإذن
        
        Args:
            batch_voucher: الإذن الجماعي
            user: المستخدم المعتمد
        """
        # حساب المخزون الرئيسي
        try:
            inventory_account = ChartOfAccounts.objects.get(code='10400')
        except ChartOfAccounts.DoesNotExist:
            raise ValueError('حساب المخزون (10400) غير موجود')
        
        # الحساب المقابل
        if batch_voucher.voucher_type == 'transfer':
            # للتحويل: لا يوجد قيد محاسبي (حركة داخلية)
            return None
        
        # الحصول على الحساب المقابل حسب الغرض
        from product.services.voucher_accounting_service import get_contra_account
        contra_account = get_contra_account(batch_voucher.purpose_type)
        
        # إعداد بيانات القيد
        gateway = AccountingGateway()
        
        if batch_voucher.voucher_type == 'receipt':
            # إذن استلام: مدين المخزون / دائن الحساب المقابل
            lines = [
                JournalEntryLineData(
                    account_code=inventory_account.code,
                    debit=batch_voucher.total_value,
                    credit=Decimal('0.00'),
                    description=f'إذن استلام جماعي - {batch_voucher.total_items} صنف'
                ),
                JournalEntryLineData(
                    account_code=contra_account.code,
                    debit=Decimal('0.00'),
                    credit=batch_voucher.total_value,
                    description=f'{batch_voucher.get_purpose_type_display()}'
                )
            ]
        else:  # issue
            # إذن صرف: مدين الحساب المقابل / دائن المخزون
            lines = [
                JournalEntryLineData(
                    account_code=contra_account.code,
                    debit=batch_voucher.total_value,
                    credit=Decimal('0.00'),
                    description=f'{batch_voucher.get_purpose_type_display()}'
                ),
                JournalEntryLineData(
                    account_code=inventory_account.code,
                    debit=Decimal('0.00'),
                    credit=batch_voucher.total_value,
                    description=f'إذن صرف جماعي - {batch_voucher.total_items} صنف'
                )
            ]
        
        entry = gateway.create_journal_entry(
            source_module='product',
            source_model='BatchVoucher',
            source_id=batch_voucher.id,
            lines=lines,
            idempotency_key=f'JE:product:BatchVoucher:{batch_voucher.id}',
            user=user,
            date=batch_voucher.voucher_date.date() if hasattr(batch_voucher.voucher_date, 'date') else batch_voucher.voucher_date,
            description=f'{batch_voucher.get_voucher_type_display()} - {batch_voucher.voucher_number}',
            reference=batch_voucher.voucher_number,
            entry_type='inventory',
            auto_post=True
        )
        
        # ربط القيد بالإذن
        batch_voucher.journal_entry = entry
        batch_voucher.save(update_fields=['journal_entry'])
        
        return entry
    
    @transaction.atomic
    def approve_batch_voucher(self, batch_voucher, user):
        """
        اعتماد الإذن الجماعي
        يتم تنفيذ جميع العمليات في transaction واحد (All or Nothing)
        
        Args:
            batch_voucher: الإذن الجماعي
            user: المستخدم المعتمد
        
        Returns:
            bool: True إذا تم الاعتماد بنجاح
        
        Raises:
            ValueError: في حالة فشل الاعتماد
        """
        try:
            # 1. التحقق من صحة الإذن
            self._validate_approval(batch_voucher)
            
            # 2. إنشاء حركات المخزون واعتمادها
            self._create_inventory_movements(batch_voucher, user)
            
            # 3. إنشاء القيد المحاسبي الموحد
            if batch_voucher.voucher_type != 'transfer':
                self._create_batch_accounting_entry(batch_voucher, user)
            
            # 4. تحديث حالة الإذن
            batch_voucher.status = 'approved'
            batch_voucher.approved_by = user
            batch_voucher.approval_date = timezone.now()
            batch_voucher.save()
            
            return True
            
        except Exception as e:
            # في حالة الفشل، سيتم rollback تلقائياً بسبب transaction.atomic
            raise ValueError(f'فشل اعتماد الإذن: {str(e)}')
    
    @transaction.atomic
    def delete_batch_voucher(self, batch_voucher):
        """
        حذف إذن جماعي (draft فقط)
        
        Args:
            batch_voucher: الإذن الجماعي
        """
        if not batch_voucher.can_delete():
            raise ValueError('لا يمكن حذف إذن معتمد')
        
        batch_voucher.delete()
