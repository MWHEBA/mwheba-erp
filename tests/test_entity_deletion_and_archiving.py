import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import Client
from customer.models import Customer
from customer.services.customer_service import CustomerService
from supplier.models import Supplier
from supplier.services.supplier_service import SupplierService
from financial.models import ChartOfAccounts, AccountType
from product.models import Warehouse
from sale.models import Sale
from purchase.models import Purchase

User = get_user_model()

@pytest.mark.django_db
class TestEntityDeletionAndArchiving:

    @pytest.fixture(autouse=True)
    def setup_base(self):
        self.user, _ = User.objects.get_or_create(username="test_admin", defaults={"email": "admin@test.com"})
        self.warehouse, _ = Warehouse.objects.get_or_create(
            name="مخزن رئيسي تجريبي",
            defaults={"code": "WH-MAIN-TEST", "is_active": True}
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_new_customer_hard_delete_and_chart_of_accounts_cleanup(self):
        """
        اختبار العميل الجديد الخالي من الحركات:
        يجب أن يُحذف نهائياً وتُطهر شجرة الحسابات من حسابه المالي التابع.
        """
        customer = Customer.objects.create(
            name="عميل تجريبي جديد",
            code="CUST_NEW_001",
            created_by=self.user
        )
        account_id = customer.financial_account_id
        assert account_id is not None
        assert ChartOfAccounts.objects.filter(id=account_id).exists()

        # فحص إمكانية الحذف
        can_delete, summary, exposure = CustomerService.can_delete_customer(customer)
        assert can_delete is True
        assert len(summary) == 0

        # تنفيذ الحذف
        res = CustomerService.delete_or_archive_customer(customer, user=self.user)
        assert res['success'] is True
        assert res['action'] == 'deleted'

        # التحقق من المسح التام وتطهير الدليل المحاسبي
        assert not Customer.objects.filter(code="CUST_NEW_001").exists()
        assert not ChartOfAccounts.objects.filter(id=account_id).exists()

    def test_customer_with_sales_soft_archives_and_reactivates(self):
        """
        اختبار العميل المرتبط بفاتورة مبيعات:
        يجب أن يتم تحويله إلى أرشفة وتعطيل (Soft Archive) وحماية فواتيره وقيوده،
        مع إمكانية إعادة تنشيطه لاحقاً.
        """
        customer = Customer.objects.create(
            name="عميل لديه فواتير",
            code="CUST_ACTIVE_002",
            created_by=self.user
        )
        account_id = customer.financial_account_id
        
        # إنشاء فاتورة مبيعات للعميل
        sale = Sale.objects.create(
            customer=customer,
            warehouse=self.warehouse,
            number="INV-TEST-001",
            date=timezone.now().date(),
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            created_by=self.user
        )

        # فحص إمكانية الحذف
        can_delete, summary, exposure = CustomerService.can_delete_customer(customer)
        assert can_delete is False
        assert any(item['label'] == 'فواتير مبيعات' and item['count'] == 1 for item in summary)

        # محاولة الحذف -> يجب أن يتحول إلى أرشفة وتعطيل
        res = CustomerService.delete_or_archive_customer(customer, user=self.user)
        assert res['success'] is True
        assert res['action'] == 'archived'

        # التحقق من بقاء العميل وحسابه في قاعدة البيانات مع تعطلهم
        customer.refresh_from_db()
        assert customer.is_active is False
        if customer.financial_account:
            assert customer.financial_account.is_active is False

        # التأكد من بقاء الفاتورة دون أي تلف
        assert Sale.objects.filter(number="INV-TEST-001").exists()

        # إعادة التنشيط
        reactivate_res = CustomerService.reactivate_customer(customer, user=self.user)
        assert reactivate_res['success'] is True
        assert reactivate_res['action'] == 'reactivated'

        customer.refresh_from_db()
        assert customer.is_active is True
        if customer.financial_account:
            assert customer.financial_account.is_active is True

    def test_new_supplier_hard_delete_and_chart_of_accounts_cleanup(self):
        """
        اختبار المورد الجديد الخالي من الحركات:
        يجب حذفه نهائياً وتطهير حسابه المالي من شجرة الحسابات.
        """
        supplier = Supplier.objects.create(
            name="مورد تجريبي جديد",
            code="SUPP_NEW_001",
            created_by=self.user
        )
        account_id = supplier.financial_account_id
        if account_id:
            assert ChartOfAccounts.objects.filter(id=account_id).exists()

        # فحص إمكانية الحذف
        can_delete, summary, exposure = SupplierService.can_delete_supplier(supplier)
        assert can_delete is True

        # تنفيذ الحذف
        res = SupplierService.delete_supplier(supplier, user=self.user)
        assert res['success'] is True
        assert res['action'] == 'deleted'

        # التحقق من المسح التام
        assert not Supplier.objects.filter(code="SUPP_NEW_001").exists()
        if account_id:
            assert not ChartOfAccounts.objects.filter(id=account_id).exists()

    def test_supplier_with_purchases_soft_archives_and_reactivates(self):
        """
        اختبار المورد المرتبط بفواتير مشتريات:
        يجب أن يتم أرشفته وتعطيله للحفاظ على القيود المحاسبية وتاريخ المعاملات.
        """
        supplier = Supplier.objects.create(
            name="مورد لديه مشتريات",
            code="SUPP_ACTIVE_002",
            created_by=self.user
        )
        
        # إنشاء فاتورة مشتريات للمورد
        Purchase.objects.create(
            supplier=supplier,
            warehouse=self.warehouse,
            number="PURCH-TEST-001",
            date=timezone.now().date(),
            subtotal=Decimal("3000.00"),
            total=Decimal("3000.00"),
            created_by=self.user
        )

        can_delete, summary, exposure = SupplierService.can_delete_supplier(supplier)
        assert can_delete is False
        assert any(item['label'] == 'فواتير مشتريات' for item in summary)

        # تنفيذ الحذف -> أرشفة
        res = SupplierService.delete_supplier(supplier, user=self.user)
        assert res['success'] is True
        assert res['action'] == 'archived'

        supplier.refresh_from_db()
        assert supplier.is_active is False

        # إعادة التنشيط
        reactivate_res = SupplierService.reactivate_supplier(supplier, user=self.user)
        assert reactivate_res['success'] is True
        supplier.refresh_from_db()
        assert supplier.is_active is True

    def test_ajax_precheck_endpoints_return_200_json(self):
        """
        اختبار استجابة الـ AJAX Pre-check لكلا من العملاء والموردين بدون أخطاء 500
        """
        customer = Customer.objects.create(
            name="عميل لفحص الـ AJAX",
            code="CUST_AJAX_001",
            created_by=self.user
        )
        supplier = Supplier.objects.create(
            name="مورد لفحص الـ AJAX",
            code="SUPP_AJAX_001",
            created_by=self.user
        )

        # 1. فحص العميل
        cust_resp = self.client.get(f"/customers/{customer.id}/delete/?precheck=1", HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert cust_resp.status_code == 200
        cust_json = cust_resp.json()
        assert cust_json['success'] is True
        assert cust_json['can_delete'] is True

        # 2. فحص المورد
        supp_resp = self.client.get(f"/suppliers/{supplier.id}/delete/?precheck=1", HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert supp_resp.status_code == 200
        supp_json = supp_resp.json()
        assert supp_json['success'] is True
        assert supp_json['can_delete'] is True

    def test_product_deactivation_and_reactivation_and_detail_headers(self):
        """
        اختبار تفاعل أزرار الهيدر مع المنتج المعطل وإعادة تنشيطه:
        - عند تعطيل المنتج تختفي أزرار التعديل والحذف ويظهر زر إعادة التنشيط والعودة للأرشيف
        - اختبار endpoint إعادة التنشيط (product_reactivate)
        """
        from product.models import Product, Category, Unit
        category, _ = Category.objects.get_or_create(name="تصنيف تجريبي", defaults={"description": "وصف"})
        unit, _ = Unit.objects.get_or_create(name="قطعة", defaults={"symbol": "PCS"})
        
        product = Product.objects.create(
            name="منتج تجريبي للاختبار",
            sku="PRD-REACT-001",
            category=category,
            unit=unit,
            selling_price=Decimal("100.00"),
            cost_price=Decimal("80.00"),
            is_active=True,
            created_by=self.user
        )

        # 1. فحص المنتج النشط
        resp_active = self.client.get(f"/products/{product.pk}/")
        assert resp_active.status_code == 200
        assert "تعديل" in resp_active.content.decode('utf-8')
        assert "حذف" in resp_active.content.decode('utf-8')

        # 2. تعطيل المنتج
        product.is_active = False
        product.save(update_fields=["is_active"])

        # 3. فحص صفحة تفاصيل المنتج المعطل
        resp_inactive = self.client.get(f"/products/{product.pk}/")
        assert resp_inactive.status_code == 200
        content = resp_inactive.content.decode('utf-8')
        assert "تفعيل المنتج" in content or "إعادة التنشيط" in content
        assert "العودة للأرشيف" in content
        assert "معطل / مؤرشف" in content

        # 4. إعادة تنشيط المنتج عبر endpoint
        resp_reactivate = self.client.post(f"/products/{product.pk}/reactivate/")
        assert resp_reactivate.status_code == 302
        
        product.refresh_from_db()
        assert product.is_active is True

    def test_account_detail_header_and_deletion(self):
        """
        اختبار وجود زر الحذف في صفحة تفاصيل الحساب وإمكانية حذفه نهائياً إذا خلا من الحركات
        """
        account_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "مصروفات", "nature": "debit"})
        account = ChartOfAccounts.objects.create(
            name="حساب مؤقت للاختبار",
            code="999901",
            account_type=account_type,
            is_active=True
        )

        resp = self.client.get(f"/financial/accounts/{account.pk}/")
        assert resp.status_code == 200
        assert "حذف" in resp.content.decode('utf-8')

        # حذف الحساب
        del_resp = self.client.post(f"/financial/accounts/{account.pk}/delete/")
        assert del_resp.status_code == 302
        assert not ChartOfAccounts.objects.filter(pk=account.pk).exists()

    def test_cost_center_detail_header_and_deletion(self):
        """
        اختبار وجود زر الحذف في صفحة تفاصيل مركز التكلفة وإمكانية حذفه
        """
        from financial.models import CostCenter
        cost_center = CostCenter.objects.create(
            name="مركز تكلفة تجريبي للحذف",
            code="CC-DEL-001",
            is_active=True
        )

        resp = self.client.get(f"/financial/cost-centers/{cost_center.pk}/")
        assert resp.status_code == 200
        assert "حذف" in resp.content.decode('utf-8')

        # حذف مركز التكلفة
        del_resp = self.client.post(f"/financial/cost-centers/{cost_center.pk}/delete/")
        assert del_resp.status_code == 302
        assert not CostCenter.objects.filter(pk=cost_center.pk).exists()

    def test_warehouse_detail_header_and_deletion(self):
        """
        اختبار وجود زر الحذف في صفحة تفاصيل المخزن وإمكانية حذفه نهائياً إذا خلا من البضائع والحركات
        """
        from product.models import Warehouse
        warehouse = Warehouse.objects.create(
            name="مخزن تجريبي للحذف",
            code="WH9999",
            is_active=True
        )

        resp = self.client.get(f"/products/warehouses/{warehouse.pk}/")
        assert resp.status_code == 200
        assert "حذف" in resp.content.decode('utf-8')

        # حذف المخزن
        del_resp = self.client.post(f"/products/warehouses/{warehouse.pk}/delete/")
        assert del_resp.status_code == 302
        assert not Warehouse.objects.filter(pk=warehouse.pk).exists()
