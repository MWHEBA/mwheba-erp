"""
Transaction Service
خدمة المعاملات المالية
"""
from decimal import Decimal
from django.db import transaction
from typing import Optional


class TransactionService:
    """خدمة إنشاء القيود المحاسبية للمعاملات المالية"""
    
    @staticmethod
    @transaction.atomic
    def create_transaction_entry(financial_transaction, user=None):
        """
        إنشاء قيد محاسبي لمعاملة مالية عبر AccountingGateway
        
        Args:
            financial_transaction: Transaction instance
            user: User creating the entry
            
        Returns:
            JournalEntry or None
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            from governance.services import AccountingGateway, JournalEntryLineData
            from financial.models import ChartOfAccounts
            
            # تحديد المستخدم
            if user is None:
                user = financial_transaction.created_by
            
            logger.debug(f"Creating entry for transaction {financial_transaction.id}, type={financial_transaction.transaction_type}")
            
            # إنشاء القيد
            gateway = AccountingGateway()
            lines = []
            
            if financial_transaction.transaction_type == "income":
                # إيراد: مدين الحساب المستلم / دائن حساب الإيرادات
                revenue_account = financial_transaction._get_revenue_account()
                if not revenue_account:
                    logger.error("Revenue account not found")
                    return None
                
                logger.debug(f"Revenue account: {revenue_account.code}")
                
                lines = [
                    JournalEntryLineData(
                        account_code=financial_transaction.account.code,
                        debit=financial_transaction.amount,
                        credit=Decimal('0'),
                        description=financial_transaction.title
                    ),
                    JournalEntryLineData(
                        account_code=revenue_account.code,
                        debit=Decimal('0'),
                        credit=financial_transaction.amount,
                        description=financial_transaction.title
                    )
                ]
                
            elif financial_transaction.transaction_type == "expense":
                # مصروف: مدين حساب المصروفات / دائن الحساب الدافع
                expense_account = financial_transaction._get_expense_account()
                if not expense_account:
                    logger.error("Expense account not found")
                    return None
                
                logger.debug(f"Expense account: {expense_account.code}")
                
                lines = [
                    JournalEntryLineData(
                        account_code=expense_account.code,
                        debit=financial_transaction.amount,
                        credit=Decimal('0'),
                        description=financial_transaction.title
                    ),
                    JournalEntryLineData(
                        account_code=financial_transaction.account.code,
                        debit=Decimal('0'),
                        credit=financial_transaction.amount,
                        description=financial_transaction.title
                    )
                ]
            else:
                logger.error(f"Unknown transaction type: {financial_transaction.transaction_type}")
                return None
            
            logger.debug(f"Creating journal entry with {len(lines)} lines")
            
            entry = gateway.create_journal_entry(
                source_module='financial',
                source_model='FinancialTransaction',
                source_id=financial_transaction.id,
                lines=lines,
                idempotency_key=f'JE:financial:FinancialTransaction:{financial_transaction.id}:create',
                user=user,
                date=financial_transaction.date,
                description=f"{financial_transaction.get_transaction_type_display()} - {financial_transaction.title}",
                reference=financial_transaction.reference_number or f"TXN-{financial_transaction.id}",
                entry_type='automatic'
            )
            
            if entry:
                pass
            else:
                logger.error("Gateway returned None")
            
            return entry
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد المعاملة المالية: {e}", exc_info=True)
            return None
