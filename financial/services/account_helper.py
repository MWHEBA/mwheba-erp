"""
خدمة مساعدة للتعامل مع الحسابات في النظام
توفر واجهة موحدة للوصول للحسابات النقدية والبنكية مع الحوكمة والسرية التامة للمستخدمين
"""

from typing import Optional, Union
from django.db import models
from django.core.exceptions import ObjectDoesNotExist

try:
    from ..models.chart_of_accounts import ChartOfAccounts, AccountType
    NEW_SYSTEM_AVAILABLE = True
except ImportError:
    NEW_SYSTEM_AVAILABLE = False

Account = None


class AccountHelperService:
    """خدمة مساعدة للتعامل مع الحسابات"""

    @staticmethod
    def get_cash_accounts(user=None, action: str = "any"):
        """
        الحصول على الحسابات النقدية والصناديق المفعلة والنهائية
        إذا تم تمرير user: يتم تطبيق حوكمة وسرية الخزن المتاحة له بحسب نوع العملية (deposit/disburse/any)
        """
        if not NEW_SYSTEM_AVAILABLE:
            return ChartOfAccounts.objects.none()

        if user is not None:
            from financial.services.treasury_security_service import TreasurySecurityService
            qs = TreasurySecurityService.get_user_accessible_treasuries(user, action=action)
            return qs.filter(
                models.Q(is_cash_account=True)
                | models.Q(account_type__code__iexact="cash")
                | models.Q(account_type__name__icontains="نقدي")
                | models.Q(account_type__name__icontains="صندوق")
                | models.Q(account_type__name__icontains="خزينة")
            ).order_by("code")

        try:
            return (
                ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
                .filter(
                    models.Q(is_cash_account=True)
                    | models.Q(account_type__code__iexact="cash")
                    | models.Q(account_type__name__icontains="نقدي")
                    | models.Q(account_type__name__icontains="صندوق")
                    | models.Q(account_type__name__icontains="خزينة")
                )
                .order_by("code")
            )
        except Exception:
            return ChartOfAccounts.objects.none()

    @staticmethod
    def get_custody_accounts(user=None):
        """
        الحصول على حسابات العهد المؤقتة المفعلة والنهائية فقط للتسوية
        إذا تم تمرير user: يتم حصر العهد على العهد المسندة له شخصياً
        """
        if not NEW_SYSTEM_AVAILABLE:
            return ChartOfAccounts.objects.none()

        if user is not None:
            from financial.services.treasury_security_service import TreasurySecurityService
            qs = TreasurySecurityService.get_user_accessible_treasuries(user, action="any")
            return qs.filter(
                models.Q(code__startswith="1145")
                | models.Q(code__startswith="1051")
                | models.Q(account_type__code__iexact="OTHER_DEBIT")
                | models.Q(account_type__name__icontains="عهدة")
            ).order_by("code")

        try:
            return (
                ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
                .filter(
                    models.Q(code__startswith="1145")
                    | models.Q(code__startswith="1051")
                    | models.Q(account_type__code__iexact="OTHER_DEBIT")
                    | models.Q(account_type__name__icontains="عهدة")
                )
                .order_by("code")
            )
        except Exception:
            return ChartOfAccounts.objects.none()

    @staticmethod
    def get_bank_accounts(user=None, action: str = "any"):
        """
        الحصول على الحسابات البنكية والمحافظ المفعلة والنهائية
        إذا تم تمرير user: يتم حصر الحسابات على المصرح له بها
        """
        if not NEW_SYSTEM_AVAILABLE:
            return ChartOfAccounts.objects.none()

        if user is not None:
            from financial.services.treasury_security_service import TreasurySecurityService
            qs = TreasurySecurityService.get_user_accessible_treasuries(user, action=action)
            return qs.filter(
                models.Q(is_bank_account=True)
                | models.Q(account_type__code__iexact="bank")
                | models.Q(account_type__name__icontains="بنك")
                | models.Q(account_type__name__icontains="مصرف")
            ).order_by("code")

        try:
            return (
                ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
                .filter(
                    models.Q(is_bank_account=True)
                    | models.Q(account_type__code__iexact="bank")
                    | models.Q(account_type__name__icontains="بنك")
                    | models.Q(account_type__name__icontains="مصرف")
                )
                .order_by("code")
            )
        except Exception:
            return ChartOfAccounts.objects.none()

    @staticmethod
    def get_cash_and_bank_accounts(user=None, action: str = "any"):
        """الحصول على جميع الحسابات النقدية والبنكية المفعلة والنهائية"""
        cash_qs = AccountHelperService.get_cash_accounts(user=user, action=action)
        bank_qs = AccountHelperService.get_bank_accounts(user=user, action=action)
        if NEW_SYSTEM_AVAILABLE:
            try:
                return (
                    ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
                    .filter(
                        models.Q(id__in=cash_qs.values_list("id", flat=True))
                        | models.Q(id__in=bank_qs.values_list("id", flat=True))
                    )
                    .order_by("code")
                )
            except Exception:
                pass
        return ChartOfAccounts.objects.none()

    @staticmethod
    def get_expense_and_settlement_accounts(user=None):
        """الحصول على الحسابات المتاحة لسداد وتسوية المصروفات والمشتريات (خزائن + بنوك + عهد)"""
        cash_qs = AccountHelperService.get_cash_accounts(user=user, action="disburse")
        bank_qs = AccountHelperService.get_bank_accounts(user=user, action="disburse")
        custody_qs = AccountHelperService.get_custody_accounts(user=user)
        if NEW_SYSTEM_AVAILABLE:
            try:
                return (
                    ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
                    .filter(
                        models.Q(id__in=cash_qs.values_list("id", flat=True))
                        | models.Q(id__in=bank_qs.values_list("id", flat=True))
                        | models.Q(id__in=custody_qs.values_list("id", flat=True))
                    )
                    .order_by("code")
                )
            except Exception:
                pass
        return ChartOfAccounts.objects.none()

    @staticmethod
    def get_all_active_accounts():
        """الحصول على جميع الحسابات النشطة والنهائية"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True, is_leaf=True
                ).order_by("code")
            except Exception:
                pass
        return ChartOfAccounts.objects.none()

    @staticmethod
    def get_accounts_by_category(category):
        """الحصول على الحسابات حسب التصنيف"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True, is_leaf=True, account_type__category=category
                ).order_by("code")
            except Exception:
                pass
        return ChartOfAccounts.objects.none()

    @staticmethod
    def find_account_by_name(name_contains):
        """البحث عن حساب بالاسم"""
        if NEW_SYSTEM_AVAILABLE:
            try:
                return ChartOfAccounts.objects.filter(
                    is_active=True, is_leaf=True, name__icontains=name_contains
                ).first()
            except Exception:
                pass
        return None

    @staticmethod
    def get_default_cash_account(user=None, action: str = "deposit"):
        """الحصول على الحساب النقدي الافتراضي للمستخدم أو للنظام بسلسلة سقوط احترافي Fallback"""
        if not NEW_SYSTEM_AVAILABLE:
            return None

        if user is not None:
            from financial.services.treasury_security_service import TreasurySecurityService
            def_trsy = TreasurySecurityService.get_user_default_treasury(user, action=action)
            if def_trsy:
                return def_trsy

        # 1. محاولة جلب الحساب المربوط بديناميكية الأدوار
        try:
            from financial.services.role_registry import AccountRoleRegistry
            def_code = AccountRoleRegistry.resolve_role_code("DEFAULT_CASH_DRAWER")
            if def_code:
                acc = ChartOfAccounts.objects.filter(code=def_code, is_active=True, is_leaf=True).first()
                if acc:
                    return acc
        except Exception:
            pass

        # 2. كود 10100 الافتراضي
        acc = ChartOfAccounts.objects.filter(code="10100", is_active=True, is_leaf=True).first()
        if acc:
            return acc

        # 3. البحث عن حساب باسم "خزينة" أو "صندوق"
        account = AccountHelperService.find_account_by_name("خزينة") or AccountHelperService.find_account_by_name("صندوق")
        if account:
            return account

        # 4. أول حساب نقدي فاعل
        cash_accounts = AccountHelperService.get_cash_accounts()
        if cash_accounts.exists():
            return cash_accounts.first()

        # 5. أول حساب بنكي أو نقدي متاح
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
        if hasattr(account, "get_balance"):
            return account.get_balance()
        elif hasattr(account, "balance"):
            return account.balance
        return 0

    @staticmethod
    def get_account_display_name(account):
        """الحصول على اسم الحساب للعرض"""
        if hasattr(account, "code") and account.code:
            return f"{account.code} - {account.name}"
        return account.name
