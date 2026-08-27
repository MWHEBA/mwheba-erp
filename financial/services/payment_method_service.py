"""
Payment Method Service
======================

Centralized service for handling payment method operations.
Provides utilities to work with payment methods as account codes.

Critical Issue #1: Payment Method Inconsistency - Solution
"""

from typing import Optional, Tuple
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class PaymentMethodService:
    """
    Service for handling payment method operations.
    
    This service provides utilities to:
    - Get account type from payment method code
    - Validate payment methods
    - Get payment method display names
    - Check if payment is cash/non-cash
    """
    
    # Cache timeout (1 hour)
    CACHE_TIMEOUT = 3600
    
    @classmethod
    def get_account_from_code(cls, payment_method_code: str):
        """
        Get ChartOfAccounts instance from payment method code.
        
        Args:
            payment_method_code: Account code (e.g., '10100', '10200')
            
        Returns:
            ChartOfAccounts instance or None
        """
        if not payment_method_code:
            return None
        
        # Check cache first
        cache_key = f"payment_account_{payment_method_code}"
        account = cache.get(cache_key)
        
        if account is None:
            from financial.models import ChartOfAccounts
            try:
                account = ChartOfAccounts.objects.get(
                    code=payment_method_code,
                    is_active=True
                )
                cache.set(cache_key, account, cls.CACHE_TIMEOUT)
            except ChartOfAccounts.DoesNotExist:
                return None
        
        return account
    
    @classmethod
    def get_account_type(cls, payment_method_code: str) -> Optional[str]:
        """
        Get account type from payment method code.
        
        Args:
            payment_method_code: Account code (e.g., '10100', '11160')
            
        Returns:
            Account type ('cash', 'bank') or None
        """
        account = cls.get_account_from_code(payment_method_code)
        if not account:
            return None
        if account.is_cash_account or (account.account_type and account.account_type.code.lower() == 'cash'):
            return 'cash'
        if account.is_bank_account or (account.account_type and account.account_type.code.lower() == 'bank'):
            return 'bank'
        if account.code.startswith('1145') or account.code.startswith('1051') or (account.account_type and account.account_type.code.upper() == 'OTHER_DEBIT') or 'عهدة' in account.name:
            return 'custody'
        name = account.name
        if any(k in name for k in ['نقدي', 'صندوق', 'خزينة']):
            return 'cash'
        if any(k in name for k in ['بنك', 'مصرف', 'جارية']):
            return 'bank'
        return 'cash' if getattr(account, 'is_leaf', False) else None
    
    @classmethod
    def is_cash_payment(cls, payment_method_code: str) -> bool:
        """
        Check if payment method is cash.
        """
        account_type = cls.get_account_type(payment_method_code)
        return account_type == 'cash'
    
    @classmethod
    def is_bank_payment(cls, payment_method_code: str) -> bool:
        """
        Check if payment method is bank.
        """
        account_type = cls.get_account_type(payment_method_code)
        return account_type == 'bank'
    
    @classmethod
    def is_non_cash_payment(cls, payment_method_code: str) -> bool:
        """
        Check if payment method is non-cash (bank, check, card, custody, etc.).
        """
        return not cls.is_cash_payment(payment_method_code)
    
    @classmethod
    def get_payment_method_display(cls, payment_method_code: str) -> str:
        """
        Get display name for payment method.
        """
        account = cls.get_account_from_code(payment_method_code)
        if account:
            return account.name
        
        # Fallback for unknown codes
        return payment_method_code
    
    @classmethod
    def get_payment_method_icon(cls, payment_method_code: str) -> str:
        """
        Get FontAwesome icon for payment method.
        """
        account_type = cls.get_account_type(payment_method_code)
        
        if account_type == 'cash':
            return 'fas fa-money-bill-wave'
        elif account_type == 'bank':
            return 'fas fa-university'
        elif account_type == 'custody':
            return 'fas fa-user-tag'
        else:
            return 'fas fa-credit-card'
    
    @classmethod
    def validate_payment_method(cls, payment_method_code: str) -> Tuple[bool, Optional[str]]:
        """
        Validate payment method code.
        """
        if not payment_method_code:
            return False, _("طريقة الدفع مطلوبة")
        
        # Check if it's a legacy value
        if payment_method_code in ['cash', 'bank_transfer', 'check', 'card', 'online']:
            return False, _(
                "payment_method يجب أن يكون رمز حساب محاسبي (مثل '10100')، "
                "وليس قيمة قديمة"
            )
        
        # Check if account exists
        account = cls.get_account_from_code(payment_method_code)
        if not account:
            return False, _(f"رمز الحساب غير صحيح أو غير نشط: {payment_method_code}")
        
        # Check if account is cash or bank type
        is_cash_or_bank = (
            getattr(account, 'is_cash_account', False)
            or getattr(account, 'is_bank_account', False)
            or (account.account_type and account.account_type.code.lower() in ['cash', 'bank'])
            or any(k in account.name for k in ['نقدي', 'صندوق', 'خزينة', 'عهدة', 'بنك', 'مصرف', 'جارية'])
        )
        if not is_cash_or_bank:
            return False, _(
                f"الحساب {account.name} ({account.code}) ليس حساب نقدية أو بنك"
            )
        
        return True, None
    
    @classmethod
    def get_default_cash_account(cls):
        """Get default cash account"""
        from financial.services.account_helper import AccountHelperService
        return AccountHelperService.get_default_cash_account()
    
    @classmethod
    def get_default_bank_account(cls):
        """Get default bank account (11160 / 10200)"""
        from financial.services.role_registry import AccountRoleRegistry
        from financial.models import ChartOfAccounts
        try:
            def_code = AccountRoleRegistry.resolve_role_code("DEFAULT_BANK_ACCOUNT")
            if def_code:
                acc = ChartOfAccounts.objects.filter(code=def_code, is_active=True, is_leaf=True).first()
                if acc:
                    return acc
        except Exception:
            pass
        return ChartOfAccounts.objects.filter(
            code__in=['11160', '10200'],
            is_active=True
        ).first()
    
    @classmethod
    def clear_cache(cls, payment_method_code: str = None):
        """
        Clear cached payment account data.
        """
        if payment_method_code:
            cache_key = f"payment_account_{payment_method_code}"
            cache.delete(cache_key)
        else:
            from financial.services.account_helper import AccountHelperService
            for account in AccountHelperService.get_cash_and_bank_accounts():
                cache_key = f"payment_account_{account.code}"
                cache.delete(cache_key)
