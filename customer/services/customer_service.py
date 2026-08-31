"""
CustomerService - Unified Service for Customer Operations

This service provides a centralized interface for all customer-related operations
with full governance compliance using AccountingGateway.

Key Features:
- Customer creation and management
- Automatic financial account creation through AccountingGateway
- Balance calculations and statements
- Thread-safe operations with proper validation
- Full audit trail integration

Usage:
    service = CustomerService()
    customer = service.create_customer(
        name="Customer Name",
        code="CUST001",
        user=request.user
    )
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from ..models import Customer
from financial.models import ChartOfAccounts
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext

User = get_user_model()
logger = logging.getLogger(__name__)


class CustomerService:
    """
    Unified service for customer operations with governance compliance.
    """
    
    def __init__(self):
        """Initialize the CustomerService with required services"""
        self.accounting_gateway = AccountingGateway()
        self.audit_service = AuditService
    
    def create_customer(
        self,
        name: str,
        code: str,
        user: User,
        phone: str = '',
        phone_primary: str = '',
        phone_secondary: str = '',
        email: str = '',
        address: str = '',
        country: str = 'مصر',
        city: str = '',
        company_name: str = '',
        contact_person: str = '',
        customer_type: str = 'individual',
        is_vip: bool = False,
        national_id: str = '',
        commercial_registry: str = '',
        credit_limit: Decimal = Decimal('0'),
        tax_number: str = '',
        default_currency=None,
        contact_frequency: str = '',
        last_contact_date=None,
        notes: str = '',
        is_active: bool = True,
        **extra_fields
    ) -> Customer:
        """
        Create a new customer with full identity, CRM, and credit profile support.
        
        Financial account creation is handled automatically by the post_save signal.
        """
        operation_start = timezone.now()
        
        try:
            with transaction.atomic():
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='CustomerService',
                    operation='create_customer'
                )
                
                # Validate customer code uniqueness
                if Customer.objects.filter(code=code).exists():
                    raise ValidationError(f"Customer code '{code}' already exists")
                
                # Create customer (signal will create financial account automatically)
                customer = Customer.objects.create(
                    name=name,
                    code=code,
                    phone=phone,
                    phone_secondary=phone_secondary,
                    email=email,
                    address=address,
                    country=country,
                    city=city,
                    company_name=company_name,
                    contact_person=contact_person,
                    customer_type=customer_type,
                    is_vip=is_vip,
                    national_id=national_id,
                    commercial_registry=commercial_registry,
                    credit_limit=credit_limit,
                    tax_number=tax_number,
                    default_currency=default_currency,
                    contact_frequency=contact_frequency,
                    last_contact_date=last_contact_date,
                    notes=notes,
                    is_active=is_active,
                    **extra_fields
                )
                
                # Create default credit profile
                from customer.models import CustomerCreditProfile
                default_payment_term = extra_fields.get('default_payment_term')
                grace_period_days = extra_fields.get('grace_period_days', 0)
                credit_status = extra_fields.get('credit_status', 'ACTIVE')
                risk_category = extra_fields.get('risk_category', 'LOW')
                next_review_date = extra_fields.get('next_review_date')
                curr_code = customer.default_currency.code if customer.default_currency else "EGP"
                
                CustomerCreditProfile.objects.get_or_create(
                    customer=customer,
                    defaults={
                        "credit_limit": customer.credit_limit or Decimal("0.00"),
                        "currency": curr_code,
                        "default_payment_term": default_payment_term,
                        "grace_period_days": grace_period_days,
                        "credit_status": credit_status,
                        "risk_category": risk_category,
                        "next_review_date": next_review_date,
                        "approved_by": user,
                        "approval_date": timezone.now().date(),
                    }
                )

                # Refresh to get the financial_account created by signal
                customer.refresh_from_db()
                
                # Create audit trail
                self.audit_service.log_operation(
                    model_name='Customer',
                    object_id=customer.id,
                    operation='CREATE',
                    user=user,
                    source_service='CustomerService',
                    after_data={
                        'name': customer.name,
                        'code': customer.code,
                        'customer_type': customer.customer_type,
                        'financial_account_code': customer.financial_account.code if customer.financial_account else None
                    },
                    operation_duration=(timezone.now() - operation_start).total_seconds()
                )
                
                logger.info(f"Customer created successfully: {customer.code} - {customer.name}")
                
                return customer
                
        except Exception as e:
            logger.error(f"Failed to create customer: {str(e)}")
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    @staticmethod
    @transaction.atomic
    def create_financial_account_for_customer(
        customer: Customer,
        user: User = None
    ) -> ChartOfAccounts:
        """
        Create financial account for customer using proper account structure.
        
        This method creates a sub-account under the main Customers account (10300)
        following the proper chart of accounts hierarchy.
        
        Uses idempotency to prevent duplicate account creation.
        
        Args:
            customer: Customer instance
            user: User creating the account
            
        Returns:
            ChartOfAccounts: The created financial account
            
        Raises:
            ValidationError: If account creation fails
        """
        from governance.services.idempotency_service import IdempotencyService
        
        # Generate idempotency key for this operation
        idempotency_key = IdempotencyService.generate_key(
            'CUSTOMER_ACCOUNT',
            customer.id,
            customer.code
        )
        
        # Check if account already created
        exists, record, result_data = IdempotencyService.check_operation_exists(
            operation_type='create_customer_account',
            idempotency_key=idempotency_key
        )
        
        if exists and result_data:
            # Account already created, return existing account
            account_id = result_data.get('account_id')
            if account_id:
                try:
                    account = ChartOfAccounts.objects.get(id=account_id)
                    logger.info(
                        f"✅ Idempotency: Returning existing account {account.code} "
                        f"for customer {customer.code}"
                    )
                    return account
                except ChartOfAccounts.DoesNotExist:
                    # Account was deleted, continue to create new one
                    logger.warning(
                        f"⚠️ Idempotency record exists but account {account_id} not found. "
                        f"Creating new account."
                    )
        
        try:
            from financial.services.subledger_account_service import SubledgerAccountService
            account = SubledgerAccountService.create_customer_account(customer, user=user)

            if not account:
                raise ValueError(f"تعذر إنشاء حساب محاسبي للعميل {customer.name}")

            # Record idempotency to prevent future duplicates
            IdempotencyService.check_and_record_operation(
                operation_type='create_customer_account',
                idempotency_key=idempotency_key,
                result_data={
                    'account_id': account.id,
                    'account_code': account.code,
                    'customer_id': customer.id,
                    'customer_code': customer.code
                },
                user=user,
                expires_in_hours=720  # 30 days
            )

            logger.info(
                f"✅ Financial account created for customer {customer.code}: "
                f"{account.code} - {account.name}"
            )

            return account
            
        except Exception as e:
            logger.error(
                f"Failed to create financial account for customer {customer.code}: {str(e)}"
            )
            raise ValidationError(f"Failed to create financial account: {str(e)}")
    
    def update_customer(
        self,
        customer: Customer,
        user: User,
        **update_fields
    ) -> Customer:
        """
        Update customer information.
        
        Args:
            customer: Customer instance to update
            user: User performing the update
            **update_fields: Fields to update
            
        Returns:
            Customer: Updated customer instance
        """
        operation_start = timezone.now()
        
        try:
            # Set governance context
            GovernanceContext.set_context(
                user=user,
                service='CustomerService',
                operation='update_customer'
            )
            
            # Store old values for audit
            old_values = {
                field: getattr(customer, field)
                for field in update_fields.keys()
                if hasattr(customer, field)
            }
            
            # Update fields
            for field, value in update_fields.items():
                if hasattr(customer, field):
                    setattr(customer, field, value)
            
            customer.save()
            
            # Create audit trail
            self.audit_service.log_operation(
                model_name='Customer',
                object_id=customer.id,
                operation='UPDATE',
                user=user,
                source_service='CustomerService',
                before_data=old_values,
                after_data=update_fields,
                operation_duration=(timezone.now() - operation_start).total_seconds()
            )
            
            logger.info(f"Customer updated successfully: {customer.code}")
            
            return customer
            
        except Exception as e:
            logger.error(f"Failed to update customer {customer.code}: {str(e)}")
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def calculate_balance(self, customer: Customer) -> Decimal:
        """
        Calculate customer's actual balance from sales and payments.
        
        Args:
            customer: Customer instance
            
        Returns:
            Decimal: Actual balance (positive = customer owes us)
        """
        # Total sales in functional currency
        sales_qs = customer.sales.exclude(status='cancelled')
        total_sales = sum(
            (getattr(s, 'total_functional', None) or (s.total * (getattr(s, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')))).quantize(Decimal('0.01'))
            for s in sales_qs
        ) if sales_qs.exists() else Decimal('0.00')
        
        # Total payments on sales in functional currency
        from sale.models import SalePayment
        payments_qs = SalePayment.objects.filter(sale__customer=customer, status='posted').select_related('sale')
        total_payments = Decimal('0.00')
        for p in payments_qs:
            rate = getattr(p.sale, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')
            settled = getattr(p, 'amount_settled_invoice_currency', p.amount) or p.amount
            func_amt = (Decimal(str(settled)) * Decimal(str(rate))).quantize(Decimal('0.01'))
            total_payments += func_amt
        
        # Balance = Sales - Payments
        return (total_sales - total_payments).quantize(Decimal('0.01'))
    
    def get_customer_statement(
        self,
        customer: Customer,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get customer statement with all transactions.
        
        Args:
            customer: Customer instance
            start_date: Start date for statement (optional)
            end_date: End date for statement (optional)
            
        Returns:
            List of transaction dictionaries with running balance
        """
        from sale.models import SalePayment
        
        transactions = []
        
        # Get sales
        sales_query = customer.sales.all()
        if start_date:
            sales_query = sales_query.filter(date__gte=start_date)
        if end_date:
            sales_query = sales_query.filter(date__lte=end_date)
        
        for sale in sales_query:
            transactions.append({
                'date': sale.created_at,
                'type': 'sale',
                'reference': sale.number,
                'description': f'Sale Invoice {sale.number}',
                'debit': sale.total,
                'credit': Decimal('0'),
                'balance': Decimal('0')  # Will be calculated
            })
        
        # Get payments
        payments_query = SalePayment.objects.filter(
            sale__customer=customer,
            status='posted'
        )
        if start_date:
            payments_query = payments_query.filter(payment_date__gte=start_date)
        if end_date:
            payments_query = payments_query.filter(payment_date__lte=end_date)
        
        for payment in payments_query:
            transactions.append({
                'date': payment.created_at,
                'type': 'payment',
                'reference': payment.reference_number or f'PAY-{payment.id}',
                'description': f'Payment on {payment.sale.number}',
                'debit': Decimal('0'),
                'credit': payment.amount,
                'balance': Decimal('0')  # Will be calculated
            })
        
        # Sort by date
        transactions.sort(key=lambda x: x['date'])
        
        # Calculate running balance
        running_balance = Decimal('0')
        for transaction in transactions:
            running_balance += transaction['debit'] - transaction['credit']
            transaction['balance'] = running_balance
        
        return transactions
    
    def get_customer_statistics(self, customer: Customer) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a customer.
        
        Args:
            customer: Customer instance
            
        Returns:
            Dictionary with customer statistics
        """
        from sale.models import SalePayment
        
        # Sales statistics in functional currency
        sales_qs = customer.sales.exclude(status='cancelled')
        sales_count = sales_qs.count()
        total_sales = sum(
            (getattr(s, 'total_functional', None) or (s.total * (getattr(s, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')))).quantize(Decimal('0.01'))
            for s in sales_qs
        ) if sales_count > 0 else Decimal('0.00')
        
        # Payment statistics in functional currency
        payments_qs = SalePayment.objects.filter(sale__customer=customer, status='posted').select_related('sale')
        payments_count = payments_qs.count()
        total_payments = Decimal('0.00')
        for p in payments_qs:
            rate = getattr(p.sale, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')
            settled = getattr(p, 'amount_settled_invoice_currency', p.amount) or p.amount
            func_amt = (Decimal(str(settled)) * Decimal(str(rate))).quantize(Decimal('0.01'))
            total_payments += func_amt
        
        # Calculate balance
        actual_balance = self.calculate_balance(customer)
        
        # Available credit
        available_credit = customer.credit_limit - actual_balance if customer.credit_limit else Decimal('0')
        
        return {
            'total_sales': total_sales,
            'sales_count': sales_count,
            'total_payments': total_payments,
            'payments_count': payments_count,
            'actual_balance': actual_balance,
            'credit_limit': customer.credit_limit,
            'available_credit': available_credit,
            'is_over_limit': actual_balance > customer.credit_limit if customer.credit_limit else False
        }

    @staticmethod
    def can_delete_customer(customer: Customer) -> tuple:
        """
        فحص شامل لمصفوفة المعاملات السيادية للعميل.
        إرجاع: (can_delete_permanently: bool, transactions_summary_list: list, exposure_dict: dict)
        """
        from sale.models import SalePayment
        transactions_summary = []
        
        # 1. فواتير المبيعات
        sales_count = customer.sales.count() if hasattr(customer, 'sales') else 0
        if sales_count > 0:
            transactions_summary.append({'label': 'فواتير مبيعات', 'count': sales_count, 'icon': 'fas fa-file-invoice-dollar'})
            
        # 2. عروض الأسعار
        quotations_count = customer.quotations.count() if hasattr(customer, 'quotations') else 0
        if quotations_count > 0:
            transactions_summary.append({'label': 'عروض أسعار', 'count': quotations_count, 'icon': 'fas fa-file-alt'})
            
        # 3. المقبوضات وسندات الدفع
        payments_count = (customer.payments.count() if hasattr(customer, 'payments') else 0) + SalePayment.objects.filter(sale__customer=customer).count()
        if payments_count > 0:
            transactions_summary.append({'label': 'سندات دفع ومقبوضات', 'count': payments_count, 'icon': 'fas fa-money-bill-wave'})
            
        # 4. الأستاذ المساعد للعملاء
        subledger_count = customer.subledger_transactions.count() if hasattr(customer, 'subledger_transactions') else 0
        if subledger_count > 0:
            transactions_summary.append({'label': 'حركات أستاذ مساعد', 'count': subledger_count, 'icon': 'fas fa-book'})
            
        # 5. الإشعارات الدائنة
        cn_count = customer.credit_notes.count() if hasattr(customer, 'credit_notes') else 0
        if cn_count > 0:
            transactions_summary.append({'label': 'إشعارات دائنة', 'count': cn_count, 'icon': 'fas fa-undo'})
            
        # 6. مرتجعات المبيعات
        returns_count = 0
        if hasattr(customer, 'sales_returns'):
            returns_count += customer.sales_returns.count()
        try:
            from sale.models import SalesReturnHeader
            returns_count += SalesReturnHeader.objects.filter(customer=customer).count()
        except Exception:
            pass
        if returns_count > 0:
            transactions_summary.append({'label': 'مرتجعات مبيعات', 'count': returns_count, 'icon': 'fas fa-exchange-alt'})

        # 7. أوامر البيع وأذون التسليم
        try:
            from sale.models import SalesOrder, DeliveryNote
            so_count = SalesOrder.objects.filter(customer=customer).count()
            if so_count > 0:
                transactions_summary.append({'label': 'أوامر بيع', 'count': so_count, 'icon': 'fas fa-shopping-cart'})
            dn_count = DeliveryNote.objects.filter(customer=customer).count()
            if dn_count > 0:
                transactions_summary.append({'label': 'أذون تسليم', 'count': dn_count, 'icon': 'fas fa-truck-loading'})
        except Exception:
            pass

        # 8. أوامر الشغل
        try:
            from work_order.models import WorkOrder
            wo_count = WorkOrder.objects.filter(customer=customer).count()
            if wo_count > 0:
                transactions_summary.append({'label': 'أوامر شغل', 'count': wo_count, 'icon': 'fas fa-tasks'})
        except Exception:
            pass
            
        # 9. قيود اليومية المرتبطة بالحساب المالي
        journal_lines_count = 0
        if customer.financial_account:
            from financial.models.journal_entry import JournalEntryLine
            journal_lines_count = JournalEntryLine.objects.filter(account=customer.financial_account).count()
            if journal_lines_count > 0:
                transactions_summary.append({'label': 'قيود يومية محاسبية', 'count': journal_lines_count, 'icon': 'fas fa-calculator'})
                
        # 10. الأرصدة الافتتاحية
        try:
            from financial.models import OpeningBalanceLine
            opening_count = OpeningBalanceLine.objects.filter(customer=customer).count()
            if opening_count > 0:
                transactions_summary.append({'label': 'أرصدة افتتاحية', 'count': opening_count, 'icon': 'fas fa-balance-scale'})
        except Exception:
            pass

        # 11. تسويات وتخصيصات الدفع
        try:
            from financial.models import PaymentAllocation
            pa_count = PaymentAllocation.objects.filter(customer=customer).count()
            if pa_count > 0:
                transactions_summary.append({'label': 'تسويات وتخصيصات دفع', 'count': pa_count, 'icon': 'fas fa-receipt'})
        except Exception:
            pass

        # 12. طلبات التسعير
        try:
            from printing_pricing.models import PricingOrder
            po_count = PricingOrder.objects.filter(customer=customer).count()
            if po_count > 0:
                transactions_summary.append({'label': 'طلبات تسعير', 'count': po_count, 'icon': 'fas fa-tags'})
        except Exception:
            pass

        # فحص المزامنة الخارجية مع دفترة
        daftra_id = getattr(customer, 'daftra_id', None)
        if daftra_id:
            transactions_summary.append({'label': 'ارتباط مزامنة دفترة', 'count': 1, 'icon': 'fas fa-sync'})

        total_transactions = sum(item['count'] for item in transactions_summary)
        can_delete = (total_transactions == 0)

        # حساب الالتزامات المالية
        has_debt = (customer.balance != Decimal('0.00'))
        available_prepaid = customer.available_prepaid_balance

        exposure_dict = {
            'has_debt': has_debt,
            'balance': customer.balance,
            'available_prepaid': available_prepaid,
        }

        return can_delete, transactions_summary, exposure_dict

    @staticmethod
    @transaction.atomic
    def delete_or_archive_customer(customer: Customer, user=None) -> dict:
        """
        حذف نهائي للعميل الجديد الفارغ أو أرشفة وتعطيل ذكي للعميل المرتبط بمعاملات
        مع حماية التزامن وقفل الصفوف.
        """
        # قفل صف العميل لمنع تضارب التزامن أثناء اتخاذ القرار
        locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
        can_delete, summary, exposure = CustomerService.can_delete_customer(locked_customer)

        customer_name = locked_customer.name
        customer_code = locked_customer.code

        if can_delete:
            # 1. حذف نهائي وتطهير الحساب المالي التابع
            financial_account = locked_customer.financial_account
            locked_customer.delete()
            
            if financial_account:
                try:
                    from financial.models import ChartOfAccounts, JournalEntryLine
                    acc = ChartOfAccounts.objects.filter(id=financial_account.id).first()
                    if acc and not JournalEntryLine.objects.filter(account=acc).exists() and not acc.children.exists():
                        acc.delete()
                        logger.info(f"✅ تم تطهير الحساب المالي الفرعي {acc.code} للعميل المحذوف {customer_name}")
                except Exception as e:
                    logger.warning(f"فشل حذف الحساب المالي بعد حذف العميل: {e}")

            logger.info(f"✅ تم حذف العميل {customer_name} ({customer_code}) نهائياً من قاعدة البيانات")
            return {
                'success': True,
                'action': 'deleted',
                'message': f"تم حذف العميل '{customer_name}' وتطهير الحساب المالي التابع له بنجاح."
            }
        else:
            # 2. أرشفة وتعطيل ذكي
            locked_customer.is_active = False
            locked_customer.save(update_fields=['is_active'])

            if locked_customer.financial_account:
                try:
                    locked_customer.financial_account.is_active = False
                    locked_customer.financial_account.save(update_fields=['is_active'])
                except Exception as e:
                    logger.warning(f"فشل تعطيل الحساب المالي للعميل المؤرشف: {e}")

            logger.info(f"📦 تمت أرشفة وتعطيل العميل {customer_name} ({customer_code}) بنجاح لوجود سجلات مرتبطة")
            return {
                'success': True,
                'action': 'archived',
                'message': f"تمت أرشفة وتعطيل العميل '{customer_name}' وحسابه المالي بنجاح لمنع التعامل معه، ويمكنك مراجعته عبر فلتر 'المعطلين'."
            }

    @staticmethod
    @transaction.atomic
    def reactivate_customer(customer: Customer, user=None) -> dict:
        """
        إعادة تنشيط عميل مؤرشف وحسابه المالي التابع
        """
        locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
        locked_customer.is_active = True
        locked_customer.save(update_fields=['is_active'])

        if locked_customer.financial_account:
            try:
                locked_customer.financial_account.is_active = True
                locked_customer.financial_account.save(update_fields=['is_active'])
            except Exception as e:
                logger.warning(f"فشل إعادة تنشيط الحساب المالي للعميل: {e}")

        logger.info(f"🔄 تمت إعادة تنشيط العميل {locked_customer.name} ({locked_customer.code}) وحسابه المالي بنجاح")
        return {
            'success': True,
            'action': 'reactivated',
            'message': f"تمت إعادة تنشيط العميل '{locked_customer.name}' وحسابه المالي بنجاح."
        }
