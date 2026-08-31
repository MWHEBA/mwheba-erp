# -*- coding: utf-8 -*-
"""
Unit Tests for SubledgerAccountService
اختبارات شاملة للمحرك المركزي الموحد لحسابات الأستاذ المساعد للعملاء والموردين.
"""
from decimal import Decimal
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.services.subledger_account_service import SubledgerAccountService
from customer.models import Customer
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class SubledgerAccountServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test_subledger_user", password="password")
        
        # إنشاء أنواع الحسابات الأساسية
        self.asset_type, _ = AccountType.objects.get_or_create(
            code="ASSET", defaults={"name": "أصول", "category": "asset", "nature": "debit"}
        )
        self.liability_type, _ = AccountType.objects.get_or_create(
            code="LIABILITY", defaults={"name": "خصوم", "category": "liability", "nature": "credit"}
        )

        # إنشاء الحسابات الرقابية الحاكمة
        self.customer_control, _ = ChartOfAccounts.objects.get_or_create(
            code="11210",
            defaults={
                "name": "العملاء",
                "account_type": self.asset_type,
                "level": 3,
                "is_control_account": True,
                "is_leaf": False,
                "is_active": True,
            }
        )
        self.supplier_control, _ = ChartOfAccounts.objects.get_or_create(
            code="21110",
            defaults={
                "name": "الموردون",
                "account_type": self.liability_type,
                "level": 3,
                "is_control_account": True,
                "is_leaf": False,
                "is_active": True,
            }
        )

    def test_create_customer_account_sequential_codes(self):
        """اختبار إنشاء حساب أستاذ مساعد لعميل مع توليد كود ثماني متسلسل"""
        cust1 = Customer.objects.create(name="شركة الأمل للتجارة", code="CUST-001", created_by=self.user)
        account1 = SubledgerAccountService.create_customer_account(cust1, user=self.user)

        self.assertIsNotNone(account1)
        self.assertTrue(account1.code.startswith("11210"))
        self.assertEqual(len(account1.code), 8)
        self.assertEqual(account1.parent, self.customer_control)
        self.assertEqual(account1.account_type.category, "asset")
        self.assertEqual(account1.account_type.nature, "debit")
        self.assertEqual(account1.account_type, self.asset_type)

        cust2 = Customer.objects.create(name="مؤسسة النور للتوريدات", code="CUST-002", created_by=self.user)
        account2 = SubledgerAccountService.create_customer_account(cust2, user=self.user)

        self.assertIsNotNone(account2)
        self.assertTrue(int(account2.code) > int(account1.code))

    def test_create_supplier_account_sequential_codes(self):
        """اختبار إنشاء حساب أستاذ مساعد لمورد مع توليد كود ثماني متسلسل"""
        supp1 = Supplier.objects.create(name="شركة الإخلاص للمقاولات", code="SUPP-001", created_by=self.user)
        account1 = SubledgerAccountService.create_supplier_account(supp1, user=self.user)

        self.assertIsNotNone(account1)
        self.assertTrue(account1.code.startswith("21110"))
        self.assertEqual(len(account1.code), 8)
        self.assertEqual(account1.parent, self.supplier_control)
        self.assertEqual(account1.account_type.category, "liability")
        self.assertEqual(account1.account_type.nature, "credit")
        self.assertEqual(account1.account_type, self.liability_type)

    def test_get_or_create_returns_existing_account(self):
        """اختبار أن get_or_create يعيد نفس الحساب ولا يكرره"""
        cust = Customer.objects.create(name="شركة القدس الدولية", code="CUST-003", created_by=self.user)
        account1 = SubledgerAccountService.get_or_create_customer_account(cust, user=self.user)
        account2 = SubledgerAccountService.get_or_create_customer_account(cust, user=self.user)

        self.assertEqual(account1.pk, account2.pk)
        self.assertEqual(account1.code, account2.code)

    def test_sync_entity_to_account(self):
        """اختبار مزامنة تعديل اسم العميل مع حسابه المحاسبي"""
        cust = Customer.objects.create(name="الاسم القديم للعميل", code="CUST-004", created_by=self.user)
        account = SubledgerAccountService.create_customer_account(cust, user=self.user)
        self.assertEqual(account.name, "الاسم القديم للعميل")

        cust.name = "الاسم الجديد المحدث"
        cust.save()
        SubledgerAccountService.sync_entity_to_account(cust)

        account.refresh_from_db()
        self.assertEqual(account.name, "الاسم الجديد المحدث")

    def test_handle_entity_deletion_deactivates_account(self):
        """اختبار تعطيل الحساب المحاسبي بأمان عند حذف الكيان"""
        cust = Customer.objects.create(name="عميل تحت الحذف", code="CUST-005", created_by=self.user)
        account = SubledgerAccountService.create_customer_account(cust, user=self.user)
        self.assertTrue(account.is_active)

        SubledgerAccountService.handle_entity_deletion(cust)
        account.refresh_from_db()
        self.assertFalse(account.is_active)
