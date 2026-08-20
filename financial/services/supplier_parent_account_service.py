"""
خدمة إدارة حسابات الموردين والعملاء في دليل الحسابات
"""
import logging
from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class SupplierParentAccountService:
    """
    خدمة مركزية لإدارة ربط الموردين وأولياء الأمور بدليل الحسابات
    """

    @staticmethod
    def create_supplier_account(supplier, user=None):
        """
        إنشاء حساب محاسبي للمورد

        Args:
            supplier: كائن المورد
            user: المستخدم الذي ينشئ الحساب (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي المنشأ
        """
        from financial.models import ChartOfAccounts, AccountType

        from financial.services.role_registry import AccountRoleRegistry

        try:
            with transaction.atomic():
                parent_account = AccountRoleRegistry.get_account_by_role("SUPPLIER_PAYABLE_CONTROL")
                if not parent_account:
                    parent_account = ChartOfAccounts.objects.filter(code="21110", is_active=True).first()

                if not parent_account:
                    raise ValueError("حساب رقابة الموردين (21110) غير موجود في دليل الحسابات")

                payables_type = parent_account.account_type
                prefix = parent_account.code[:4]

                # البحث عن آخر كود مستخدم تحت حساب الموردين
                last_sub = ChartOfAccounts.objects.filter(
                    parent=parent_account,
                    code__startswith=prefix
                ).exclude(code=parent_account.code).order_by("-code").first()

                if last_sub:
                    try:
                        seq = int(last_sub.code[len(prefix):]) + 1
                    except ValueError:
                        seq = 1
                else:
                    seq = 1

                code = f"{prefix}{seq:04d}"
                while ChartOfAccounts.objects.filter(code=code).exists():
                    seq += 1
                    code = f"{prefix}{seq:04d}"

                # حساب الرصيد الافتتاحي من القيود المرحلة فقط
                from purchase.models import Purchase, PurchasePayment
                # إجمالي فواتير الشراء المرحلة
                total_purchases = (
                    Purchase.objects.filter(
                        supplier=supplier,
                        journal_entry__isnull=False,
                        journal_entry__status="posted",
                    ).aggregate(total=Sum("total"))["total"]
                    or 0
                )

                # إجمالي المدفوعات المرحلة
                total_payments = (
                    PurchasePayment.objects.filter(
                        purchase__supplier=supplier,
                        purchase__journal_entry__isnull=False,
                        purchase__journal_entry__status="posted",
                    ).aggregate(total=Sum("amount"))["total"]
                    or 0
                )

                opening_balance = total_purchases - total_payments

                # إنشاء الحساب الفرعي
                account = ChartOfAccounts.objects.create(
                    code=code,
                    name=f"مورد - {supplier.name}",
                    parent=parent_account,
                    account_type=payables_type,
                    is_active=True,
                    is_leaf=True,
                    opening_balance=opening_balance,
                    description=f"حساب المورد: {supplier.name} (كود: {supplier.code})",
                    created_by=user,
                )

                # ربط الحساب بالمورد
                supplier.financial_account = account
                supplier.save(update_fields=["financial_account"])

                return account

        except Exception as e:
            logger.error(f"فشل إنشاء حساب للمورد {supplier.name}: {e}")
            raise

    @staticmethod
    def create_customer_account(customer, user=None):
        """
        إنشاء حساب محاسبي للعميل (بديل create_parent_account)

        Args:
            customer: كائن العميل (client.Customer)
            user: المستخدم الذي ينشئ الحساب (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي المنشأ
        """
        from financial.models import ChartOfAccounts, AccountType
        from financial.services.role_registry import AccountRoleRegistry
        from decimal import Decimal

        try:
            with transaction.atomic():
                parent_account = AccountRoleRegistry.get_account_by_role("CUSTOMER_RECEIVABLE_CONTROL")
                if not parent_account:
                    parent_account = ChartOfAccounts.objects.filter(code="11210", is_active=True).first()

                if not parent_account:
                    raise ValueError("حساب رقابة العملاء (11210) غير موجود في دليل الحسابات")

                receivables_type = parent_account.account_type
                prefix = parent_account.code[:4]

                last_sub = ChartOfAccounts.objects.filter(
                    parent=parent_account,
                    code__startswith=prefix
                ).exclude(code=parent_account.code).order_by("-code").first()

                if last_sub:
                    try:
                        seq = int(last_sub.code[len(prefix):]) + 1
                    except ValueError:
                        seq = 1
                else:
                    seq = 1

                code = f"{prefix}{seq:04d}"
                while ChartOfAccounts.objects.filter(code=code).exists():
                    seq += 1
                    code = f"{prefix}{seq:04d}"

                account = ChartOfAccounts.objects.create(
                    code=code,
                    name=f"عميل - {customer.name if hasattr(customer, 'name') else customer}",
                    parent=parent_account,
                    account_type=receivables_type,
                    is_active=True,
                    is_leaf=True,
                    opening_balance=Decimal('0'),
                    description=f"حساب العميل: {customer}",
                    created_by=user,
                )

                customer.financial_account = account
                customer.save(update_fields=["financial_account"])

                return account

        except Exception as e:
            logger.error(f"فشل إنشاء حساب للعميل {customer}: {e}")
            raise

    # Alias للتوافق مع الكود القديم
    create_parent_account = create_customer_account

    @staticmethod
    def get_or_create_supplier_account(supplier, user=None):
        """
        الحصول على الحساب المحاسبي للمورد أو إنشاؤه إذا لم يكن موجوداً

        Args:
            supplier: كائن المورد
            user: المستخدم (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي
        """
        if supplier.financial_account:
            return supplier.financial_account
        return SupplierParentAccountService.create_supplier_account(supplier, user)

    @staticmethod
    def get_or_create_customer_account(customer, user=None):
        """
        الحصول على الحساب المحاسبي للعميل أو إنشاؤه إذا لم يكن موجوداً
        """
        if customer.financial_account:
            return customer.financial_account
        return SupplierParentAccountService.create_customer_account(customer, user)

    # Alias للتوافق مع الكود القديم
    @staticmethod
    def get_or_create_parent_account(parent, user=None):
        if parent.financial_account:
            return parent.financial_account
        return SupplierParentAccountService.create_customer_account(parent, user)

    @staticmethod
    def sync_balance(entity):
        """
        مزامنة الرصيد بين المورد/العميل والحساب المحاسبي

        Args:
            entity: المورد أو العميل
        """
        if not entity.financial_account:
            return

        try:
            # تحديث الرصيد في الحساب المحاسبي
            current_balance = entity.financial_account.get_balance()
            actual_balance = entity.actual_balance

            if current_balance != actual_balance:
                logger.warning(
                    f"تباين في الرصيد: {entity.__class__.__name__} {entity.name} - "
                    f"الحساب المحاسبي: {current_balance}, الرصيد الفعلي: {actual_balance}"
                )
        except Exception as e:
            logger.error(f"فشل مزامنة الرصيد لـ {entity.name}: {e}")
