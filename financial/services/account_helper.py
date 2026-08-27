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
    def get_cash_accounts():
        """الحصول على الحسابات النقدية والصناديق المفعلة والنهائية فقط"""
        if NEW_SYSTEM_AVAILABLE:
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
                pass
        return ChartOfAccounts.objects.none()

    @staticmethod
    def get_custody_accounts():
        """الحصول على حسابات العهد المؤقتة المفعلة والنهائية فقط للتسوية"""
        if NEW_SYSTEM_AVAILABLE:
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
                pass
        return ChartOfAccounts.objects.none()

    @staticmethod
    def get_bank_accounts():
        """الحصول على الحسابات البنكية والمحافظ المفعلة والنهائية فقط"""
        if NEW_SYSTEM_AVAILABLE:
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
                pass
        return ChartOfAccounts.objects.none()

    @staticmethod
    def get_cash_and_bank_accounts():
        """الحصول على جميع الحسابات النقدية والبنكية المفعلة والنهائية"""
        cash_qs = AccountHelperService.get_cash_accounts()
        bank_qs = AccountHelperService.get_bank_accounts()
        if NEW_SYSTEM_AVAILABLE:
            try:
                return (
                    ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
                    .filter(
                        models.Q(id__in=cash_qs.values_list('id', flat=True))
                        | models.Q(id__in=bank_qs.values_list('id', flat=True))
                    )
                    .order_by("code")
                )
            except Exception:
                pass
        return ChartOfAccounts.objects.none()

    @staticmethod
    def get_expense_and_settlement_accounts():
        """الحصول على الحسابات المتاحة لسداد وتسوية المصروفات والمشتريات (خزائن + بنوك + عهد)"""
        cash_qs = AccountHelperService.get_cash_accounts()
        bank_qs = AccountHelperService.get_bank_accounts()
        custody_qs = AccountHelperService.get_custody_accounts()
        if NEW_SYSTEM_AVAILABLE:
            try:
                return (
                    ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
                    .filter(
                        models.Q(id__in=cash_qs.values_list('id', flat=True))
                        | models.Q(id__in=bank_qs.values_list('id', flat=True))
                        | models.Q(id__in=custody_qs.values_list('id', flat=True))
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
    def get_default_cash_account():
        """الحصول على الحساب النقدي الافتراضي بسلسلة سقوط احترافي Fallback"""
        if not NEW_SYSTEM_AVAILABLE:
            return None

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
