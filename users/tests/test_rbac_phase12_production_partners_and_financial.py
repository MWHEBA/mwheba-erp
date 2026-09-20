# -*- coding: utf-8 -*-
import pytest
import json
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from users.models import Role
from product.models.stock_management import Warehouse
from product.models import Product, Category, Unit
from customer.models import Customer
from core.models import SystemModule
from printing_pricing.models import PrintingOrder
from financial.models import ChartOfAccounts, AccountType, JournalEntry

User = get_user_model()


@pytest.fixture
def base_user(db):
    return User.objects.create_user(
        username="test_employee",
        email="emp@example.com",
        password="Password123!"
    )


@pytest.fixture
def financial_manager_user(db):
    fm_role, _ = Role.objects.get_or_create(name="financial_manager", defaults={"display_name": "مدير مالي"})
    user = User.objects.create_user(
        username="fm_user",
        email="fm@example.com",
        password="Password123!",
        role=fm_role
    )
    return user


@pytest.mark.django_db
class TestPackage1ProductionPrintingPressGovernance:
    """اختبارات حوكمة أوامر العمل وتكلفة المطبعة"""

    def test_printing_order_approval_blocks_self_approval_for_creator(self, client, base_user):
        customer = Customer.objects.create(name="عميل اختبار 1")
        change_perm = Permission.objects.get(codename="change_printingorder", content_type__app_label="printing_pricing")
        base_user.user_permissions.add(change_perm)

        order = PrintingOrder.objects.create(
            customer=customer,
            title="طلب اختبار 1",
            order_type="book",
            quantity=500,
            created_by=base_user
        )

        client.force_login(base_user)
        url = reverse("printing_pricing:approve_order", kwargs={"pk": order.pk})
        response = client.post(url)
        assert response.status_code == 403

    def test_printing_order_cost_masking_for_non_financial_users(self, client, base_user):
        customer = Customer.objects.create(name="عميل اختبار 2")
        view_perm = Permission.objects.get(codename="view_printingorder", content_type__app_label="printing_pricing")
        base_user.user_permissions.add(view_perm)

        order = PrintingOrder.objects.create(
            customer=customer,
            title="طلب اختبار 2",
            order_type="book",
            quantity=1000,
            created_by=base_user,
            final_price=Decimal("1000.00")
        )

        client.force_login(base_user)
        url = reverse("printing_pricing:calculate_cost", kwargs={"pk": order.pk})
        response = client.post(url)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["estimated_cost"] == 0.0
        assert data["profit_margin"] == 0.0
        assert data["profit_amount"] == 0.0
        assert data["can_view_financials"] is False


@pytest.mark.django_db
class TestPackage2PriceManagerAndMovementScoping:
    """اختبارات مدير الأسعار وحوكمة حركات المخازن"""

    def test_price_manager_requires_view_permission(self, client, base_user):
        client.force_login(base_user)
        url = reverse("product:price_manager")
        response = client.get(url)
        assert response.status_code == 403

        # منح صلاحية العرض
        view_perm = Permission.objects.get(codename="view_product", content_type__app_label="product")
        base_user.user_permissions.add(view_perm)
        response = client.get(url)
        assert response.status_code == 200

    def test_price_manager_update_requires_change_permission(self, client, base_user):
        cat = Category.objects.create(name="تصنيف 1")
        unit = Unit.objects.create(name="قطعة", symbol="قطعة")
        prod = Product.objects.create(
            name="منتج اختبار",
            sku="SKU-P1",
            category=cat,
            unit=unit,
            created_by=base_user,
            selling_price=Decimal("10.00"),
            cost_price=Decimal("5.00")
        )

        client.force_login(base_user)
        url = reverse("product:price_manager_update")
        payload = json.dumps({"id": prod.id, "field": "selling_price", "value": "15.00"})
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 403

        # منح صلاحية التعديل
        change_perm = Permission.objects.get(codename="change_product", content_type__app_label="product")
        base_user.user_permissions.add(change_perm)
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200
        prod.refresh_from_db()
        assert prod.selling_price == Decimal("15.00")

    def test_batch_voucher_approve_warehouse_scoping(self, client, base_user):
        """التحقق من عزل اعتماد الإذن الجماعي وحظر الاعتماد لمخزن غير مسند مع الرد بـ 403 AJAX"""
        from product.models import BatchVoucher, Warehouse
        w1 = Warehouse.objects.create(name="مخزن رئيسي مصرح", manager=base_user)
        w2 = Warehouse.objects.create(name="مخزن فرعي محظور")

        voucher = BatchVoucher.objects.create(
            voucher_number="BV-TEST-001",
            voucher_type="receipt",
            warehouse=w2,
            created_by=base_user,
            status="draft"
        )

        approve_perm = Permission.objects.get(codename="approve_batchvoucher", content_type__app_label="product")
        base_user.user_permissions.add(approve_perm)
        client.force_login(base_user)

        url = reverse("product:batch_voucher_approve", kwargs={"pk": voucher.pk})
        # استدعاء أياكس
        response = client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert response.status_code == 403
        data = response.json()
        assert data["success"] is False
        assert "غير مسند" in data["error"]


@pytest.mark.django_db
class TestPackage3BusinessPartnersGovernance:
    """اختبارات حوكمة العملاء والموردين والحد الائتماني وأعمار الديون"""

    def test_supplier_aging_api_requires_view_permission(self, client, base_user):
        from supplier.models import Supplier
        supplier = Supplier.objects.create(name="مورد اختبار")

        client.force_login(base_user)
        url = reverse("supplier:supplier_aging_api", kwargs={"pk": supplier.pk})
        response = client.get(url)
        assert response.status_code == 403

        view_perm = Permission.objects.get(codename="view_supplier", content_type__app_label="supplier")
        base_user.user_permissions.add(view_perm)
        response = client.get(url)
        assert response.status_code == 200

    def test_price_tier_add_requires_change_supplier_permission(self, client, base_user):
        SystemModule.objects.update_or_create(code="printing_pricing", defaults={"is_enabled": True})
        from supplier.models import Supplier, SupplierService, ServiceType
        supplier = Supplier.objects.create(name="مورد تجربة")
        st, _ = ServiceType.objects.get_or_create(code="coating", defaults={"name": "سلفنة"})
        service = SupplierService.objects.create(supplier=supplier, service_type=st, name="سلفنة مطفي")

        client.force_login(base_user)
        url = reverse("supplier:price_tier_add", kwargs={"pk": supplier.pk, "service_pk": service.pk})
        response = client.get(url)
        assert response.status_code == 403

        change_perm = Permission.objects.get(codename="change_supplier", content_type__app_label="supplier")
        base_user.user_permissions.add(change_perm)
        response = client.get(url)
        assert response.status_code == 200

    def test_customer_form_credit_limit_backend_tamper_protection(self, base_user):
        """حماية الحد الائتماني من التلاعب البرمجي في النموذج لمستخدم غير مصرح"""
        from customer.models import Customer
        from customer.forms import CustomerForm
        customer = Customer.objects.create(name="عميل اختبار", code="CUST0099", credit_limit=Decimal("500.00"))

        # محاولة مستخدم عادي إرسال سقف ائتماني 99999 عبر البوست المباشر
        form_data = {
            "name": "عميل اختبار معدل",
            "code": customer.code,
            "credit_limit": "99999.00",
            "credit_status": "ACTIVE",
            "risk_category": "LOW",
        }
        form = CustomerForm(data=form_data, instance=customer, user=base_user)
        assert form.is_valid(), form.errors
        # تحقق أن سقف الائتمان تم إرجاعه للقيمة الأصلية 500.00 ولم يتم التلاعب به
        assert form.cleaned_data["credit_limit"] == Decimal("500.00")
        assert form.cleaned_data["credit_status"] == "ACTIVE"
        assert form.cleaned_data["risk_category"] == "LOW"


@pytest.mark.django_db
class TestPackage4FinancialTreasuryGovernance:
    """اختبارات دليل الحسابات، التحويل المالي وإلغاء ترحيل القيود"""

    def test_transfer_between_accounts_requires_permission(self, client, base_user):
        client.force_login(base_user)
        url = reverse("financial:transfer_between_accounts")
        response = client.post(url, data={})
        assert response.status_code == 403

        add_perm = Permission.objects.get(codename="add_journalentry", content_type__app_label="financial")
        base_user.user_permissions.add(add_perm)
        response = client.post(url, data={})
        # يجب ألا يكون 403 بعد إعطاء الصلاحية (سيعطي 400 لنقص البيانات في الطلب)
        assert response.status_code == 400

    def test_chart_of_accounts_create_requires_permission(self, client, base_user):
        client.force_login(base_user)
        url = reverse("financial:chart_of_accounts_create")
        response = client.get(url)
        assert response.status_code == 403

        add_perm = Permission.objects.get(codename="add_chartofaccounts", content_type__app_label="financial")
        base_user.user_permissions.add(add_perm)
        response = client.get(url)
        assert response.status_code == 200

    def test_journal_entries_unpost_governance(self, client, base_user, financial_manager_user):
        from financial.models import AccountingPeriod, FiscalYear
        fy = FiscalYear.objects.create(
            year_code="FY-TEST-01",
            name="سنة 2026",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            status="open"
        )
        period = AccountingPeriod.objects.create(
            fiscal_year=fy,
            period_number=1,
            name="فترة تجربة",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            status="open"
        )
        entry = JournalEntry.objects.create(
            date=timezone.now().date(),
            reference="JE-UNPOST-001",
            accounting_period=period,
            status="posted"
        )

        client.force_login(base_user)
        url = reverse("financial:journal_entries_unpost", kwargs={"pk": entry.pk})
        # المستخدم العادي بدون change_journalentry يمنع 403 من require_permission
        response = client.post(url)
        assert response.status_code == 403

        # منح المستخدم change_journalentry لكنه ليس مديراً مالياً
        change_perm = Permission.objects.get(codename="change_journalentry", content_type__app_label="financial")
        base_user.user_permissions.add(change_perm)
        response = client.post(url)
        assert response.status_code == 403
        data = response.json()
        assert "محصور حصرياً بالمدير المالي" in data.get("message", "")

        # المدير المالي يملك الصلاحية
        financial_manager_user.user_permissions.add(change_perm)
        client.force_login(financial_manager_user)
        response = client.post(url, data={"reason": "تصحيح قيد"}, content_type="application/json")
        # يعود بنجاح
        assert response.status_code in [200, 400]
