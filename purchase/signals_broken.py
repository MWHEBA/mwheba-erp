from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import PurchaseItem, PurchasePayment, Purchase, PurchaseReturn
from product.models import StockMovement


@receiver(post_save, sender=PurchaseItem)
def create_stock_movement_for_purchase_item(sender, instance, created, **kwargs):
    """
    إنشاء حركة مخزون عند إنشاء بند فاتورة مشتريات
    """
    if created and instance.purchase.status == 'confirmed':
        # التحقق من عدم وجود حركة مخزون مسبقاً لتجنب الازدواجية
        existing_movement = StockMovement.objects.filter(
            product=instance.product,
            warehouse=instance.purchase.warehouse,
            document_type='purchase',
            document_number=instance.purchase.number,
            reference_number=f"PURCHASE-{instance.purchase.number}-ITEM-{instance.id}"
        ).exists()
        
        if not existing_movement:
            with transaction.atomic():
                # إنشاء حركة مخزون للوارد
                StockMovement.objects.create(
                    product=instance.product,
                    warehouse=instance.purchase.warehouse,
                    movement_type='in',
                    quantity=instance.quantity,
                    document_type='purchase',
                    document_number=instance.purchase.number,
                    reference_number=f"PURCHASE-{instance.purchase.number}-ITEM-{instance.id}",
                    notes=f"مشتريات - فاتورة رقم {instance.purchase.number}",
                    created_by=instance.purchase.created_by
                )
    
    if created:
        # تحديث سعر الشراء للمنتج إذا تغير
        product = instance.product
        if product.cost_price != instance.unit_price:
            product.cost_price = instance.unit_price
            product.save(update_fields=['cost_price'])


@receiver(post_delete, sender=PurchaseItem)
def handle_deleted_purchase_item(sender, instance, **kwargs):
    """
    إلغاء حركة المخزون عند حذف بند فاتورة الشراء
    يمكن تنفيذ منطق أكثر تعقيدًا حسب متطلبات العمل
    """
    # يمكن إضافة منطق لإنشاء حركة مخزون معاكسة (صادر)
    pass


@receiver(post_save, sender=PurchasePayment)
def update_payment_status_on_payment(sender, instance, created, **kwargs):
    """
    تحديث حالة الدفع عند تسجيل دفعة
    """
    if created:
        instance.purchase.update_payment_status()
        
        # تحديث رصيد المورد
        supplier = instance.purchase.supplier
        if supplier:
            supplier.balance -= instance.amount
            supplier.save(update_fields=['balance'])


@receiver(post_save, sender=Purchase)
def update_supplier_balance_on_purchase(sender, instance, created, **kwargs):
    """
    تحديث رصيد المورد عند إنشاء فاتورة مشتريات
    """
    if created:
        supplier = instance.supplier
        if supplier:
            # إذا كانت الفاتورة آجلة، أضف كامل المبلغ إلى رصيد المورد
            if instance.payment_method == 'credit':
                supplier.balance += instance.total
                supplier.save(update_fields=['balance'])
            # إذا كانت الفاتورة نقدية وغير مدفوعة بالكامل، أضف المبلغ المتبقي إلى رصيد المورد
            elif instance.payment_method == 'cash' and instance.payment_status != 'paid':
                # المبلغ المستحق = الإجمالي - المبلغ المدفوع
                amount_due = instance.total - instance.amount_paid
                if amount_due > 0:
                    supplier.balance += amount_due
                    supplier.save(update_fields=['balance'])


@receiver(post_save, sender=Purchase)
def update_supplier_balance_on_purchase_update(sender, instance, created, **kwargs):
    """
    تحديث رصيد المورد عند تعديل فاتورة مشتريات موجودة
    """
    # نتعامل فقط مع التعديلات وليس مع الإنشاء الجديد
    if not created:
        # نحتاج للتأكد من أن هناك فعلاً تغييرات في القيم المالية أو طريقة الدفع
        # الحل بسيط هنا هو تحديث حالة الدفع للفاتورة، والتي ستقوم بالتعامل مع تحديث الرصيد عند اللزوم
        instance.update_payment_status()


@receiver(post_save, sender=Purchase)
def create_financial_transaction_for_purchase(sender, instance, created, **kwargs):
    """
    إنشاء معاملة مالية عند إنشاء فاتورة مشتريات جديدة
    """
    if created and instance.payment_status == 'paid':
        try:
            # استيراد النماذج المالية من الملف الأساسي مباشرة
            import financial.models as financial_models
            Transaction = financial_models.Transaction
            TransactionLine = financial_models.TransactionLine
            Account = financial_models.Account
            
            # إيجاد أو إنشاء حساب المصروفات (المشتريات)
            purchases_account, _ = # تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
        # Account.objects.get_or_create(
                code='EXP001',
                defaults={
                    'name': 'مشتريات',
                    'account_type': 'expense',
                    'is_active': True,
                    'created_by': instance.created_by
                }
            )
            
            # إيجاد أو إنشاء حساب الموردين (ذمم دائنة)
            suppliers_account, _ = # تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
        # Account.objects.get_or_create(
                code='AP001',
                defaults={
                    'name': 'حسابات الموردين',
                    'account_type': 'liability',
                    'is_active': True,
                    'created_by': instance.created_by
                }
            )
            
            # إيجاد أو إنشاء حساب الصندوق
            cash_account, _ = # تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
        # Account.objects.get_or_create(
                code='CASH001',
                defaults={
                    'name': 'الصندوق',
                    'account_type': 'asset',
                    'type': 'cash',
                    'is_active': True,
                    'created_by': instance.created_by
                }
            )
            
            with transaction.atomic():
                # إنشاء معاملة مالية للفاتورة
                financial_trans = Transaction.objects.create(
                    account=purchases_account,
                    transaction_type='expense',
                    amount=instance.total,
                    date=instance.date,
                    description=f'فاتورة مشتريات رقم {instance.number} - {instance.supplier.name}',
                    reference_number=instance.number,
                    created_by=instance.created_by
                )
                
                # مدين: حساب المشتريات
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=purchases_account,
                    debit=instance.total,
                    credit=0,
                    description=f'مشتريات - فاتورة رقم {instance.number}'
                )
                
                # دائن: حساب الموردين أو الصندوق (حسب طريقة الدفع)
                if instance.payment_method == 'cash' and instance.payment_status == 'paid':
                    # دائن: الصندوق
                    TransactionLine.objects.create(
                        transaction=financial_trans,
                        account=cash_account,
                        debit=0,
                        credit=instance.total,
                        description=f'دفع نقدي - فاتورة رقم {instance.number}'
                    )
                    
                    # تحديث رصيد الصندوق
                    cash_account.update_balance(instance.total, 'subtract')
                else:
                    # دائن: حساب الموردين (ذمم دائنة)
                    TransactionLine.objects.create(
                        transaction=financial_trans,
                        account=suppliers_account,
                        debit=0,
                        credit=instance.total,
                        description=f'مشتريات آجلة - فاتورة رقم {instance.number}'
                    )
                    
                    # تحديث رصيد حساب الموردين
                    suppliers_account.update_balance(instance.total, 'add')
                
                # تحديث رصيد حساب المشتريات
                purchases_account.update_balance(instance.total, 'add')
                
        except Exception as e:
            # تسجيل الخطأ بدلاً من إيقاف العملية
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating financial transaction for purchase {instance.number}: {str(e)}")


@receiver(post_save, sender=PurchasePayment)
def create_financial_transaction_for_purchase_payment(sender, instance, created, **kwargs):
    """
    إنشاء معاملة مالية عند دفع فاتورة مشتريات
    """
    print(f"PurchasePayment signal called: created={created}, has_transaction={instance.financial_transaction is not None}")
    
    if created and not instance.financial_transaction:
        try:
            print(f"Creating financial transaction for purchase payment: {instance.id}")
            
            # استيراد النماذج المالية من الملف الأساسي مباشرة
            import financial.models as financial_models
            Transaction = financial_models.Transaction
            TransactionLine = financial_models.TransactionLine
            Account = financial_models.Account
            
            # إيجاد أو إنشاء حساب الموردين
            suppliers_account, _ = # تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
        # Account.objects.get_or_create(
                code='AP001',
                defaults={
                    'name': 'حسابات الموردين',
                    'account_type': 'liability',
                    'is_active': True,
                    'created_by': instance.created_by
                }
            )
            print(f"Suppliers account: {suppliers_account.id} - {suppliers_account.name}")
            
            # تحديد الحساب الذي سيتم السحب منه بناءً على طريقة الدفع
            if instance.payment_method == 'cash':
                payment_account, _ = # تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
        # Account.objects.get_or_create(
                    code='CASH001',
                    defaults={
                        'name': 'الصندوق',
                        'account_type': 'asset',
                        'type': 'cash',
                        'is_active': True,
                        'created_by': instance.created_by
                    }
                )
            elif instance.payment_method == 'bank_transfer':
                payment_account, _ = # تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
        # Account.objects.get_or_create(
                    code='BANK001',
                    defaults={
                        'name': 'البنك',
                        'account_type': 'asset',
                        'type': 'bank',
                        'is_active': True,
                        'created_by': instance.created_by
                    }
                )
            else:
                # افتراضي إذا كانت طريقة دفع أخرى
                payment_account, _ = # تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
        # Account.objects.get_or_create(
                    code='CASH001',
                    defaults={
                        'name': 'الصندوق',
                        'account_type': 'asset',
                        'type': 'cash',
                        'is_active': True,
                        'created_by': instance.created_by
                    }
                )
            print(f"Payment account: {payment_account.id} - {payment_account.name}")
            
            with transaction.atomic():
                # إنشاء معاملة مالية للدفعة
                financial_trans = Transaction.objects.create(
                    account=suppliers_account,
                    transaction_type='expense',
                    amount=instance.amount,
                    date=instance.payment_date,
                    description=f'دفعة لفاتورة رقم {instance.purchase.number} - {instance.purchase.supplier.name}',
                    reference_number=instance.reference_number,
                    created_by=instance.created_by
                )
                print(f"Created transaction: {financial_trans.id} - {financial_trans.amount}")
                
                # مدين: حساب الموردين
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=suppliers_account,
                    debit=instance.amount,
                    credit=0,
                    description=f'تسديد مستحقات - فاتورة رقم {instance.purchase.number}'
                )
                
                # دائن: حساب الصندوق/البنك
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=payment_account,
                    debit=0,
                    credit=instance.amount,
                    description=f'دفع مستحقات - فاتورة رقم {instance.purchase.number}'
                )
                
                # تحديث أرصدة الحسابات
                suppliers_account.update_balance(instance.amount, 'subtract')
                payment_account.update_balance(instance.amount, 'subtract')
                
                # ربط المعاملة المالية بالدفعة
                instance.financial_transaction = financial_trans
                instance.save(update_fields=['financial_transaction'])
                print(f"Successfully linked transaction {financial_trans.id} to payment {instance.id}")
                
        except Exception as e:
            # تسجيل الخطأ بدلاً من إيقاف العملية
            import logging
            logger = logging.getLogger(__name__)
            print(f"ERROR creating financial transaction: {str(e)}")
            logger.error(f"Error creating financial transaction for purchase payment {instance.id}: {str(e)}")


@receiver(post_save, sender=PurchaseReturn)
def create_financial_transaction_for_purchase_return(sender, instance, **kwargs):
    """
    إنشاء معاملة مالية عند تأكيد مرتجع مشتريات
    """
    if instance.status == 'confirmed':
        try:
            # استيراد النماذج المالية من الملف الأساسي مباشرة
            import financial.models as financial_models
            Transaction = financial_models.Transaction
            TransactionLine = financial_models.TransactionLine
            Account = financial_models.Account
            
            # إيجاد حسابات المشتريات والموردين والصندوق
            purchases_account = Account.objects.filter(code='EXP001').first()
            suppliers_account = Account.objects.filter(code='AP001').first()
            cash_account = Account.objects.filter(code='CASH001').first()
            
            if not purchases_account or not suppliers_account or not cash_account:
                raise Exception("لم يتم العثور على الحسابات اللازمة")
            
            with transaction.atomic():
                # إنشاء معاملة مالية للمرتجع
                financial_trans = Transaction.objects.create(
                    account=purchases_account,
                    transaction_type='income',
                    amount=instance.total,
                    date=instance.date,
                    description=f'مرتجع مشتريات رقم {instance.number} - فاتورة رقم {instance.purchase.number}',
                    reference_number=instance.number,
                    created_by=instance.created_by
                )
                
                # مدين: حساب الموردين أو الصندوق (حسب طريقة الدفع الأصلية)
                if instance.purchase.payment_method == 'cash' and instance.purchase.payment_status == 'paid':
                    # مدين: الصندوق (استرداد المبلغ نقدا)
                    TransactionLine.objects.create(
                        transaction=financial_trans,
                        account=cash_account,
                        debit=instance.total,
                        credit=0,
                        description=f'استرداد نقدي - مرتجع مشتريات رقم {instance.number}'
                    )
                    cash_account.update_balance(instance.total, 'add')
                else:
                    # مدين: حساب الموردين (تخفيض المستحق عليهم)
                    TransactionLine.objects.create(
                        transaction=financial_trans,
                        account=suppliers_account,
                        debit=instance.total,
                        credit=0,
                        description=f'استرداد - مرتجع مشتريات رقم {instance.number}'
                    )
                    suppliers_account.update_balance(instance.total, 'subtract')
                
                # دائن: حساب المشتريات (تخفيض المشتريات)
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=purchases_account,
                    debit=0,
                    credit=instance.total,
                    description=f'مرتجع مشتريات - فاتورة رقم {instance.purchase.number}'
                )
                
                # تحديث رصيد حساب المشتريات
                purchases_account.update_balance(instance.total, 'subtract')
                
        except Exception as e:
            # تسجيل الخطأ بدلاً من إيقاف العملية
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating financial transaction for purchase return {instance.number}: {str(e)}")


@receiver(post_delete, sender=Purchase)
def update_supplier_balance_on_purchase_delete(sender, instance, **kwargs):
    """
    تحديث رصيد المورد عند حذف فاتورة مشتريات
    """
    supplier = instance.supplier
    if supplier:
        # إذا كانت الفاتورة آجلة، قم بخصم كامل المبلغ من رصيد المورد
        if instance.payment_method == 'credit':
            supplier.balance -= instance.total
            supplier.save(update_fields=['balance'])
        # إذا كانت الفاتورة نقدية وغير مدفوعة بالكامل، قم بخصم المبلغ المتبقي من رصيد المورد
        elif instance.payment_method == 'cash' and instance.payment_status != 'paid':
            # المبلغ المستحق = الإجمالي - المبلغ المدفوع
            amount_due = instance.total - instance.amount_paid
            if amount_due > 0:
                supplier.balance -= amount_due
                supplier.save(update_fields=['balance']) 