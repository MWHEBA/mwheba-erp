from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import SaleItem, SalePayment, Sale, SaleReturn
from product.models import StockMovement


@receiver(post_save, sender=SaleItem)
def create_stock_movement_for_sale_item(sender, instance, created, **kwargs):
    """
    إنشاء حركة مخزون عند إنشاء بند فاتورة مبيعات
    """
    if created and instance.sale.status == 'confirmed':
        # التحقق من عدم وجود حركة مخزون مسبقاً لتجنب الازدواجية
        existing_movement = StockMovement.objects.filter(
            product=instance.product,
            warehouse=instance.sale.warehouse,
            document_type='sale',
            document_number=instance.sale.number,
            reference_number=f"SALE-{instance.sale.number}-ITEM-{instance.id}"
        ).exists()
        
        if not existing_movement:
            with transaction.atomic():
                # إنشاء حركة مخزون للصادر
                StockMovement.objects.create(
                    product=instance.product,
                    warehouse=instance.sale.warehouse,
                    movement_type='out',
                    quantity=instance.quantity,
                    document_type='sale',
                    document_number=instance.sale.number,
                    reference_number=f"SALE-{instance.sale.number}-ITEM-{instance.id}",
                    notes=f"مبيعات - فاتورة رقم {instance.sale.number}",
                    created_by=instance.sale.created_by
                )


@receiver(post_delete, sender=SaleItem)
def handle_deleted_sale_item(sender, instance, **kwargs):
    """
    إلغاء حركة المخزون عند حذف بند الفاتورة
    """
    try:
        # البحث عن حركة المخزون المرتبطة وحذفها
        related_movement = StockMovement.objects.filter(
            product=instance.product,
            warehouse=instance.sale.warehouse,
            document_type='sale',
            document_number=instance.sale.number,
            reference_number=f"SALE-{instance.sale.number}-ITEM-{instance.id}"
        ).first()
        
        if related_movement:
            with transaction.atomic():
                # إنشاء حركة مخزون معاكسة (إرجاع المخزون)
                StockMovement.objects.create(
                    product=instance.product,
                    warehouse=instance.sale.warehouse,
                    movement_type='in',
                    quantity=related_movement.quantity,
                    document_type='sale_return',
                    document_number=instance.sale.number,
                    reference_number=f"SALE-CANCEL-{instance.sale.number}-ITEM-{instance.id}",
                    notes=f"إلغاء بند مبيعات - فاتورة رقم {instance.sale.number}",
                    created_by=instance.sale.created_by
                )
                
                # حذف الحركة الأصلية
                related_movement.delete()
                
    except Exception as e:
        # تسجيل الخطأ دون إيقاف العملية
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في معالجة حذف بند المبيعات: {str(e)}")


@receiver(post_save, sender=SalePayment)
def update_payment_status_on_payment(sender, instance, created, **kwargs):
    """
    تحديث حالة الدفع عند تسجيل دفعة
    """
    if created:
        instance.sale.update_payment_status()
        
        # تحديث رصيد العميل
        customer = instance.sale.customer
        if customer:
            customer.balance -= instance.amount
            customer.save(update_fields=['balance'])


@receiver(post_save, sender=Sale)
def update_customer_balance_on_sale(sender, instance, created, **kwargs):
    """
    تحديث رصيد العميل عند إنشاء فاتورة مبيعات
    """
    if created and instance.payment_method == 'credit':
        customer = instance.customer
        if customer:
            customer.balance += instance.total
            customer.save(update_fields=['balance'])


@receiver(post_save, sender=Sale)
def create_financial_transaction_for_sale(sender, instance, created, **kwargs):
    """
    إنشاء معاملة مالية عند إنشاء فاتورة مبيعات جديدة
    """
    if created and instance.payment_status == 'paid':
        try:
            # استيراد النماذج المالية من الملف الأساسي مباشرة
            import financial.models as financial_models
            Transaction = financial_models.Transaction
            TransactionLine = financial_models.TransactionLine
            Account = financial_models.Account
            
            # إيجاد حساب الإيراد من المبيعات (تم تعطيل الإنشاء التلقائي)
            sales_account = Account.objects.filter(code='INC002').first()
            if not sales_account:
                # يجب إنشاء الحساب يدوياً في النظام الجديد
                return
            
            # إيجاد حساب العملاء (تم تعطيل الإنشاء التلقائي)
            customers_account = Account.objects.filter(code='AR001').first()
            if not customers_account:
                # يجب إنشاء الحساب يدوياً في النظام الجديد
                return
            
            # إيجاد حساب الصندوق (تم تعطيل الإنشاء التلقائي)
            cash_account = Account.objects.filter(code='CASH001').first()
            if not cash_account:
                # يجب إنشاء الحساب يدوياً في النظام الجديد
                return
            
            with transaction.atomic():
                # إنشاء معاملة مالية للفاتورة
                financial_trans = Transaction.objects.create(
                    account=sales_account,
                    transaction_type='income',
                    amount=instance.total,
                    date=instance.date,
                    description=f'فاتورة مبيعات رقم {instance.number} - {instance.customer.name}',
                    reference_number=instance.number,
                    created_by=instance.created_by
                )
                
                # إذا كانت الفاتورة مدفوعة نقدًا
                if instance.payment_method == 'cash' and instance.payment_status == 'paid':
                    # مدين: الصندوق
                    TransactionLine.objects.create(
                        transaction=financial_trans,
                        account=cash_account,
                        debit=instance.total,
                        credit=0,
                        description=f'مبيعات نقدية - فاتورة رقم {instance.number}'
                    )
                else:
                    # مدين: حساب العملاء (ذمم مدينة)
                    TransactionLine.objects.create(
                        transaction=financial_trans,
                        account=customers_account,
                        debit=instance.total,
                        credit=0,
                        description=f'مبيعات آجلة - فاتورة رقم {instance.number}'
                    )
                
                # دائن: حساب إيرادات المبيعات
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=sales_account,
                    debit=0,
                    credit=instance.total,
                    description=f'إيراد مبيعات - فاتورة رقم {instance.number}'
                )
                
                # تحديث أرصدة الحسابات
                if instance.payment_method == 'cash' and instance.payment_status == 'paid':
                    cash_account.update_balance(instance.total, 'add')
                else:
                    customers_account.update_balance(instance.total, 'add')
                    
                sales_account.update_balance(instance.total, 'add')
                
        except Exception as e:
            # تسجيل الخطأ بدلاً من إيقاف العملية
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating financial transaction for sale {instance.number}: {str(e)}")


@receiver(post_save, sender=SalePayment)
def create_financial_transaction_for_payment(sender, instance, created, **kwargs):
    """
    إنشاء معاملة مالية عند استلام دفعة من فاتورة مبيعات
    """
    print(f"SalePayment signal called: created={created}, has_transaction={instance.financial_transaction is not None}")
    
    if created and not instance.financial_transaction:
        try:
            print(f"Creating financial transaction for sale payment: {instance.id}")
            
            # استيراد النماذج المالية من الملف الأساسي مباشرة
            import financial.models as financial_models
            Transaction = financial_models.Transaction
            TransactionLine = financial_models.TransactionLine
            Account = financial_models.Account
            
            # إيجاد حساب العملاء (تم تعطيل الإنشاء التلقائي)
            customers_account = Account.objects.filter(code='AR001').first()
            if not customers_account:
                print("تحذير: حساب العملاء غير موجود - يجب إنشاؤه في النظام الجديد")
                return
            print(f"Customers account: {customers_account.id} - {customers_account.name}")
            
            # تحديد الحساب الذي سيتم الإيداع فيه بناءً على طريقة الدفع
            if instance.payment_method == 'cash':
                payment_account, _ = Account.objects.get_or_create(
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
                payment_account, _ = Account.objects.get_or_create(
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
                payment_account, _ = Account.objects.get_or_create(
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
                    account=payment_account,
                    transaction_type='income',
                    amount=instance.amount,
                    date=instance.payment_date,
                    description=f'دفعة من فاتورة رقم {instance.sale.number} - {instance.sale.customer.name}',
                    reference_number=instance.reference_number,
                    created_by=instance.created_by
                )
                print(f"Created transaction: {financial_trans.id} - {financial_trans.amount}")
                
                # مدين: حساب الصندوق/البنك
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=payment_account,
                    debit=instance.amount,
                    credit=0,
                    description=f'استلام دفعة - فاتورة رقم {instance.sale.number}'
                )
                
                # دائن: حساب العملاء
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=customers_account,
                    debit=0,
                    credit=instance.amount,
                    description=f'تسديد دفعة - فاتورة رقم {instance.sale.number}'
                )
                
                # تحديث أرصدة الحسابات
                payment_account.update_balance(instance.amount, 'add')
                customers_account.update_balance(instance.amount, 'subtract')
                
                # ربط المعاملة المالية بالدفعة
                instance.financial_transaction = financial_trans
                instance.save(update_fields=['financial_transaction'])
                print(f"Successfully linked transaction {financial_trans.id} to payment {instance.id}")
                
        except Exception as e:
            # تسجيل الخطأ بدلاً من إيقاف العملية
            import logging
            logger = logging.getLogger(__name__)
            print(f"ERROR creating financial transaction: {str(e)}")
            logger.error(f"Error creating financial transaction for sale payment {instance.id}: {str(e)}")


@receiver(post_save, sender=SaleReturn)
def create_financial_transaction_for_return(sender, instance, **kwargs):
    """
    إنشاء معاملة مالية عند تأكيد مرتجع مبيعات
    """
    if instance.status == 'confirmed':
        try:
            # استيراد النماذج المالية من الملف الأساسي مباشرة
            import financial.models as financial_models
            Transaction = financial_models.Transaction
            TransactionLine = financial_models.TransactionLine
            Account = financial_models.Account
            
            # إيجاد حسابات المبيعات والعملاء والصندوق
            sales_account = Account.objects.filter(code='INC002').first()
            customers_account = Account.objects.filter(code='AR001').first()
            cash_account = Account.objects.filter(code='CASH001').first()
            
            if not sales_account or not customers_account or not cash_account:
                raise Exception("لم يتم العثور على الحسابات اللازمة")
            
            with transaction.atomic():
                # إنشاء معاملة مالية للمرتجع
                financial_trans = Transaction.objects.create(
                    account=sales_account,
                    transaction_type='expense',
                    amount=instance.total,
                    date=instance.date,
                    description=f'مرتجع مبيعات رقم {instance.number} - فاتورة رقم {instance.sale.number}',
                    reference_number=instance.number,
                    created_by=instance.created_by
                )
                
                # مدين: حساب إيرادات المبيعات (تخفيض الإيرادات)
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=sales_account,
                    debit=instance.total,
                    credit=0,
                    description=f'مرتجع مبيعات - فاتورة رقم {instance.sale.number}'
                )
                
                # دائن: حساب العملاء أو الصندوق (حسب طريقة الدفع الأصلية)
                if instance.sale.payment_method == 'cash' and instance.sale.payment_status == 'paid':
                    account_to_credit = cash_account
                else:
                    account_to_credit = customers_account
                
                TransactionLine.objects.create(
                    transaction=financial_trans,
                    account=account_to_credit,
                    debit=0,
                    credit=instance.total,
                    description=f'مرتجع مبيعات - فاتورة رقم {instance.sale.number}'
                )
                
                # تحديث أرصدة الحسابات
                sales_account.update_balance(instance.total, 'subtract')
                
                if account_to_credit == cash_account:
                    cash_account.update_balance(instance.total, 'subtract')
                else:
                    customers_account.update_balance(instance.total, 'subtract')
                
        except Exception as e:
            # تسجيل الخطأ بدلاً من إيقاف العملية
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating financial transaction for return {instance.number}: {str(e)}") 