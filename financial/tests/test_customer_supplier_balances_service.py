# -*- coding: utf-8 -*-
"""
Unit Tests for CustomerSupplierBalancesService
اختبارات خدمة تقارير أعمار الديون وأرصدة العملاء والموردين وتصدير الإكسيل.
"""
from decimal import Decimal
from datetime import date
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model

from financial.services.customer_supplier_balances_service import CustomerSupplierBalancesService
from customer.models import Customer
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class CustomerSupplierBalancesServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test_balances_user", password="password")
        self.service = CustomerSupplierBalancesService(as_of_date=date.today())

    def test_generate_customer_balances_empty(self):
        """اختبار تقرير أرصدة العملاء بدون بيانات"""
        report = self.service.generate_customer_balances_report()
        self.assertIn("accounts", report)
        self.assertIn("due_periods", report)
        self.assertIn("summary", report)
        self.assertEqual(report["summary"]["total_balance"], Decimal("0"))

    def test_generate_supplier_balances_empty(self):
        """اختبار تقرير أرصدة الموردين بدون بيانات"""
        report = self.service.generate_supplier_balances_report()
        self.assertIn("accounts", report)
        self.assertIn("due_periods", report)
        self.assertIn("summary", report)
        self.assertEqual(report["summary"]["total_balance"], Decimal("0"))

    def test_export_to_excel_structure(self):
        """اختبار تصدير التقرير إلى Excel"""
        report_data = {
            "accounts": [
                {
                    "account_code": "11210001",
                    "account_name": "شركة العالمية",
                    "current": Decimal("5000.00"),
                    "days_1_30": Decimal("2000.00"),
                    "days_31_60": Decimal("0.00"),
                    "days_61_90": Decimal("0.00"),
                    "over_90": Decimal("0.00"),
                    "total_balance": Decimal("7000.00"),
                }
            ],
            "due_periods": {
                "current": {"amount": Decimal("5000.00")},
                "days_1_30": {"amount": Decimal("2000.00")},
                "days_31_60": {"amount": Decimal("0.00")},
                "days_61_90": {"amount": Decimal("0.00")},
                "over_90": {"amount": Decimal("0.00")},
            },
            "summary": {"total_balance": Decimal("7000.00")},
        }

        excel_bytes = self.service.export_to_excel(report_data, report_type="ar")
        self.assertIsInstance(excel_bytes, bytes)
        self.assertTrue(len(excel_bytes) > 0)
