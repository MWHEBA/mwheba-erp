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
            payment_method_code: Account code (e.g., '10100', '10200')
            
        Returns:
            Account type ('cash', 'bank') or None
            
        Example:
            >>> PaymentMethodService.get_account_type('10100')
            'cash'
            >>> PaymentMethodService.get_account_type('10200')
            'bank'
        """
        account = cls.get_account_from_code(payment_method_code)
        return account.account_type if account else None
    
    @classmethod
    def is_cash_payment(cls, payment_method_code: str) -> bool:
        """
        Check if payment method is cash.
        
        Args:
            payment_method_code: Account code
            
        Returns:
            True if cash payment, False otherwise
            
        Example:
            >>> PaymentMethodService.is_cash_payment('10100')
            True
            >>> PaymentMethodService.is_cash_payment('10200')
            False
        """
        account_type = cls.get_account_type(payment_method_code)
        return account_type == 'cash'
    
    @classmethod
    def is_bank_payment(cls, payment_method_code: str) -> bool:
        """
        Check if payment method is bank.
        
        Args:
            payment_method_code: Account code
            
        Returns:
            True if bank payment, False otherwise
        """
        account_type = cls.get_account_type(payment_method_code)
        return account_type == 'bank'
    
    @classmethod
    def is_non_cash_payment(cls, payment_method_code: str) -> bool:
        """
        Check if payment method is non-cash (bank, check, card, etc.).
        
        Args:
            payment_method_code: Account code
            
        Returns:
            True if non-cash payment, False otherwise
        """
        return not cls.is_cash_payment(payment_method_code)
    
    @classmethod
    def get_payment_method_display(cls, payment_method_code: str) -> str:
        """
        Get display name for payment method.
        
        Args:
            payment_method_code: Account code
            
        Returns:
            Display name (e.g., "نقدي", "تحويل بنكي")
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
        
        Args:
            payment_method_code: Account code
            
        Returns:
            FontAwesome icon class
        """
        account_type = cls.get_account_type(payment_method_code)
        
        if account_type == 'cash':
            return 'fas fa-money-bill-wave'
        elif account_type == 'bank':
            return 'fas fa-university'
        else:
            return 'fas fa-credit-card'
    
    @classmethod
    def validate_payment_method(cls, payment_method_code: str) -> Tuple[bool, Optional[str]]:
        """
        Validate payment method code.
        
        Args:
            payment_method_code: Account code to validate
            
        Returns:
            Tuple of (is_valid, error_message)
            
        Example:
            >>> is_valid, error = PaymentMethodService.validate_payment_method('10100')
            >>> if not is_valid:
            ...     raise ValidationError(error)
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
        if account.account_type not in ['cash', 'bank']:
            return False, _(
                f"الحساب {account.name} ({account.code}) ليس حساب نقدية أو بنك"
            )
        
        return True, None
    
    @classmethod
    def get_default_cash_account(cls):
        """Get default cash account (10100)"""
        from financial.models import ChartOfAccounts
        return ChartOfAccounts.objects.filter(
            code='10100',
            is_active=True
        ).first()
    
    @classmethod
    def get_default_bank_account(cls):
        """Get default bank account (10200)"""
        from financial.models import ChartOfAccounts
        return ChartOfAccounts.objects.filter(
            code='10200',
            is_active=True
        ).first()
    
    @classmethod
    def clear_cache(cls, payment_method_code: str = None):
        """
        Clear cached payment account data.
        
        Args:
            payment_method_code: Specific code to clear, or None to clear all
        """
        if payment_method_code:
            cache_key = f"payment_account_{payment_method_code}"
            cache.delete(cache_key)
        else:
            # Clear all payment account caches
            # This is a simple implementation - in production you might want
            # to use cache key patterns
            from financial.models import ChartOfAccounts
            for account in ChartOfAccounts.objects.filter(
                account_type__code__in=['cash', 'bank']
            ):
                cache_key = f"payment_account_{account.code}"
                cache.delete(cache_key)
