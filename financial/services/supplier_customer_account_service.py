"""
خدمة إدارة حسابات الموردين والعملاء في دليل الحسابات
"""
import logging
from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class SupplierCustomerAccountService:
    """
    خدمة مركزية لإدارة ربط الموردين والعملاء بدليل الحسابات
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

        try:
            with transaction.atomic():
                # البحث عن الحساب الرئيسي للموردين
                payables_type = AccountType.objects.filter(code="PAYABLES").first()
                if not payables_type:
                    raise ValueError("نوع حساب PAYABLES غير موجود")

                parent_account = ChartOfAccounts.objects.filter(
                    account_type=payables_type, is_active=True
                ).first()

                if not parent_account:
                    # إنشاء الحساب الرئيسي إذا لم يكن موجوداً
                    parent_account = ChartOfAccounts.objects.create(
                        code="21010",
                        name="الموردون",
                        account_type=payables_type,
                        is_active=True,
                        is_leaf=False,
                        is_control_account=True,
                        created_by=user,
                    )

                # توليد كود فريد للحساب الفرعي
                code = f"2101{supplier.id:03d}"  # مثال: 21010001

                # التحقق من عدم وجود الكود
                if ChartOfAccounts.objects.filter(code=code).exists():
                    # إذا كان موجوداً، نستخدم timestamp
                    import time

                    code = f"2101{int(time.time()) % 1000:03d}"

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

                logger.info(
                    f"تم إنشاء حساب محاسبي {account.code} للمورد {supplier.name}"
                )
                return account

        except Exception as e:
            logger.error(f"فشل إنشاء حساب للمورد {supplier.name}: {e}")
            raise

    @staticmethod
    def create_customer_account(customer, user=None):
        """
        إنشاء حساب محاسبي للعميل

        Args:
            customer: كائن العميل
            user: المستخدم الذي ينشئ الحساب (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي المنشأ
        """
        from financial.models import ChartOfAccounts, AccountType

        try:
            with transaction.atomic():
                # البحث عن الحساب الرئيسي للعملاء
                receivables_type = AccountType.objects.filter(
                    code="RECEIVABLES"
                ).first()
                if not receivables_type:
                    raise ValueError("نوع حساب RECEIVABLES غير موجود")

                parent_account = ChartOfAccounts.objects.filter(
                    account_type=receivables_type, parent__isnull=True, is_active=True
                ).first()

                if not parent_account:
                    # إنشاء الحساب الرئيسي إذا لم يكن موجوداً
                    parent_account = ChartOfAccounts.objects.create(
                        code="11030",
                        name="العملاء",
                        account_type=receivables_type,
                        is_active=True,
                        is_leaf=False,
                        is_control_account=True,
                        created_by=user,
                    )

                # توليد كود فريد للحساب الفرعي
                code = f"1103{customer.id:03d}"  # مثال: 11030001

                # التحقق من عدم وجود الكود
                if ChartOfAccounts.objects.filter(code=code).exists():
                    # إذا كان موجوداً، نستخدم timestamp
                    import time

                    code = f"1103{int(time.time()) % 1000:03d}"

                # حساب الرصيد الافتتاحي من القيود المرحلة فقط
                from sale.models import Sale, SalePayment

                # إجمالي فواتير المبيعات المرحلة
                total_sales = (
                    Sale.objects.filter(
                        customer=customer,
                        journal_entry__isnull=False,
                        journal_entry__status="posted",
                    ).aggregate(total=Sum("total"))["total"]
                    or 0
                )

                # إجمالي المدفوعات المرحلة
                total_payments = (
                    SalePayment.objects.filter(
                        sale__customer=customer,
                        sale__journal_entry__isnull=False,
                        sale__journal_entry__status="posted",
                    ).aggregate(total=Sum("amount"))["total"]
                    or 0
                )

                opening_balance = total_sales - total_payments

                # إنشاء الحساب الفرعي
                account = ChartOfAccounts.objects.create(
                    code=code,
                    name=f"عميل - {customer.name}",
                    parent=parent_account,
                    account_type=receivables_type,
                    is_active=True,
                    is_leaf=True,
                    opening_balance=opening_balance,
                    description=f"حساب العميل: {customer.name} (كود: {customer.code})",
                    created_by=user,
                )

                # ربط الحساب بالعميل
                customer.financial_account = account
                customer.save(update_fields=["financial_account"])

                logger.info(
                    f"تم إنشاء حساب محاسبي {account.code} للعميل {customer.name}"
                )
                return account

        except Exception as e:
            logger.error(f"فشل إنشاء حساب للعميل {customer.name}: {e}")
            raise

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
        return SupplierCustomerAccountService.create_supplier_account(supplier, user)

    @staticmethod
    def get_or_create_customer_account(customer, user=None):
        """
        الحصول على الحساب المحاسبي للعميل أو إنشاؤه إذا لم يكن موجوداً

        Args:
            customer: كائن العميل
            user: المستخدم (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي
        """
        if customer.financial_account:
            return customer.financial_account
        return SupplierCustomerAccountService.create_customer_account(customer, user)

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
