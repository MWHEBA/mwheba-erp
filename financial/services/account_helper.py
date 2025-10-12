"""
خدمة مساعدة للتعامل مع الحسابات في النظام الجديد والقديم

هذه الخدمة توفر واجهة موحدة للوصول للحسابات
مع إمكانية التراجع للنظام القديم في حالة الحاجة
"""

from django.db import models
from django.core.exceptions import ObjectDoesNotExist

try:
    from ..models.chart_of_accounts import ChartOfAccounts, AccountType
    NEW_SYSTEM_AVAILABLE = True
except ImportError:
    NEW_SYSTEM_AVAILABLE = False

# النظام القديم لم يعد متاحاً - استخدام النظام الجديد فقط
Account = None


class AccountHelperService:
    """خدمة مساعدة للتعامل مع الحسابات"""
    
    @staticmethod
    def get_cash_and_bank_accounts():
        """الحصول على الحسابات النقدية والبنكية"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True,
                    is_leaf=True
                ).filter(
                    models.Q(is_cash_account=True) | 
                    models.Q(is_bank_account=True) |
                    models.Q(account_type__name__icontains='نقدي') |
                    models.Q(account_type__name__icontains='بنك') |
                    models.Q(account_type__name__icontains='صندوق')
                ).order_by('code')
            except Exception:
                pass
        
        # التراجع للنظام القديم غير متاح
        return ChartOfAccounts.objects.none()
    
    @staticmethod
    def get_all_active_accounts():
        """الحصول على جميع الحسابات النشطة"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True,
                    is_leaf=True
                ).order_by('code')
            except Exception:
                pass
        
        # التراجع للنظام القديم غير متاح
        return ChartOfAccounts.objects.none()
    
    @staticmethod
    def get_accounts_by_category(category):
        """الحصول على الحسابات حسب التصنيف"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True,
                    is_leaf=True,
                    account_type__category=category
                ).order_by('code')
            except Exception:
                pass
        
        # التراجع للنظام القديم غير متاح
        return ChartOfAccounts.objects.none()
    
    @staticmethod
    def get_bank_accounts():
        """الحصول على الحسابات البنكية فقط"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True,
                    is_leaf=True,
                    is_bank_account=True
                ).order_by('code')
            except Exception:
                pass
        
        # التراجع للنظام القديم غير متاح
        return ChartOfAccounts.objects.none()
    
    @staticmethod
    def get_cash_accounts():
        """الحصول على الحسابات النقدية فقط"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True,
                    is_leaf=True,
                    is_cash_account=True
                ).order_by('code')
            except Exception:
                pass
        
        # التراجع للنظام القديم غير متاح
        return ChartOfAccounts.objects.none()
    
    @staticmethod
    def find_account_by_name(name_contains):
        """البحث عن حساب بالاسم"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True,
                    is_leaf=True,
                    name__icontains=name_contains
                ).first()
            except Exception:
                pass
        
        # التراجع للنظام القديم غير متاح
        return None
    
    @staticmethod
    def get_default_cash_account():
        """الحصول على الحساب النقدي الافتراضي"""
        # البحث عن حساب الخزينة أولاً
        account = AccountHelperService.find_account_by_name('خزينة')
        if account:
            return account
        
        # البحث عن أي حساب نقدي
        cash_accounts = AccountHelperService.get_cash_accounts()
        if cash_accounts.exists():
            return cash_accounts.first()
        
        # البحث عن أي حساب نقدي أو بنكي
        cash_bank_accounts = AccountHelperService.get_cash_and_bank_accounts()
        if cash_bank_accounts.exists():
            return cash_bank_accounts.first()
        
        return None
    
    @staticmethod
    def is_new_system_available():
        """التحقق من توفر النظام الجديد"""
        return NEW_SYSTEM_AVAILABLE
    
    @staticmethod
    def get_account_balance(account):
        """الحصول على رصيد الحساب"""
        if hasattr(account, 'get_balance'):
            return account.get_balance()
        elif hasattr(account, 'balance'):
            return account.balance
        return 0
    
    @staticmethod
    def get_account_display_name(account):
        """الحصول على اسم الحساب للعرض"""
        if hasattr(account, 'code') and account.code:
            return f"{account.code} - {account.name}"
        return account.name
