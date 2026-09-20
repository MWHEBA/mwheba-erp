# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from users.models import Role
from users.services.data_scoping_service import DataScopingService
from users.services.permission_dependency import PermissionDependencyService
from users.services.permission_service import PermissionService
from product.models.stock_management import Warehouse
from product.forms import TransferVoucherForm
from customer.models import Customer
from sale.models import Sale, CreditNote
from sale.models.quotation import Quotation
from sale.models.sales_models import SalesOrder, DeliveryNote

User = get_user_model()


@pytest.fixture
def sales_rep_user(db):
    user = User.objects.create_user(
        username="rep_ahmed",
        email="ahmed@example.com",
        password="Password123!",
        first_name="Ahmed",
        last_name="Sales"
    )
    # منحه صلاحية مبيعات عادية بدون view_all_sales
    view_sale_perm = Permission.objects.get(codename="view_sale", content_type__app_label="sale")
    user.user_permissions.add(view_sale_perm)
    return user


@pytest.fixture
def sales_rep_other(db):
    user = User.objects.create_user(
        username="rep_mahmoud",
        email="mahmoud@example.com",
        password="Password123!",
        first_name="Mahmoud",
        last_name="Sales"
    )
    view_sale_perm = Permission.objects.get(codename="view_sale", content_type__app_label="sale")
    user.user_permissions.add(view_sale_perm)
    return user


@pytest.fixture
def accountant_user(db):
    accountant_role, _ = Role.objects.get_or_create(name="accountant", defaults={"display_name": "محاسب"})
    user = User.objects.create_user(
        username="acc_mohamed",
        email="mohamed@example.com",
        password="Password123!",
        first_name="Mohamed",
        last_name="Accountant",
        role=accountant_role
    )
    view_sale_perm = Permission.objects.get(codename="view_sale", content_type__app_label="sale")
    user.user_permissions.add(view_sale_perm)
    return user


@pytest.fixture
def warehouse_keeper_user(db):
    user = User.objects.create_user(
        username="wh_keeper_ali",
        email="ali@example.com",
        password="Password123!",
        first_name="Ali",
        last_name="Keeper"
    )
    return user


@pytest.fixture
def sample_customer(db):
    return Customer.objects.create(
        name="شركة الأهرام للتجارة",
        code="CUST-001",
        is_active=True
    )


@pytest.fixture
def sample_warehouses(db, warehouse_keeper_user):
    wh_cairo = Warehouse.objects.create(
        name="مخزن القاهرة الرئيسي",
        code="WH-CAI-01",
        manager=warehouse_keeper_user,
        is_active=True
    )
    wh_alex = Warehouse.objects.create(
        name="مخزن الإسكندرية",
        code="WH-ALX-01",
        is_active=True
    )
    return wh_cairo, wh_alex


@pytest.mark.django_db
class TestDataScopingService:
    """اختبارات خدمة عزل وتحديد نطاق البيانات (DataScopingService)"""

    def test_sales_scoping_for_salesman(self, sales_rep_user, sales_rep_other, sample_customer, sample_warehouses):
        wh, _ = sample_warehouses
        # فاتورة خاصة بالمندوب أحمد
        sale_ahmed = Sale.objects.create(
            number="INV-2026-0001",
            customer=sample_customer,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            salesman=sales_rep_user,
            created_by=sales_rep_user
        )
        # فاتورة خاصة بالمندوب محمود
        sale_mahmoud = Sale.objects.create(
            number="INV-2026-0002",
            customer=sample_customer,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("2500.00"),
            total=Decimal("2500.00"),
            salesman=sales_rep_other,
            created_by=sales_rep_other
        )

        # فحص عزل المندوب أحمد
        scoped_ahmed = DataScopingService.get_scoped_sales(sales_rep_user)
        assert sale_ahmed in scoped_ahmed
        assert sale_mahmoud not in scoped_ahmed

        # فحص عزل المندوب محمود
        scoped_mahmoud = DataScopingService.get_scoped_sales(sales_rep_other)
        assert sale_mahmoud in scoped_mahmoud
        assert sale_ahmed not in scoped_mahmoud

    def test_sales_scoping_exemptions_for_accountant(self, accountant_user, sales_rep_user, sales_rep_other, sample_customer, sample_warehouses):
        wh, _ = sample_warehouses
        sale1 = Sale.objects.create(
            number="INV-2026-0010",
            customer=sample_customer,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
            salesman=sales_rep_user,
            created_by=sales_rep_user
        )
        sale2 = Sale.objects.create(
            number="INV-2026-0011",
            customer=sample_customer,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("2000.00"),
            total=Decimal("2000.00"),
            salesman=sales_rep_other,
            created_by=sales_rep_other
        )

        # المحاسب يرى كلاهما بدون عمى محاسبي
        scoped_acc = DataScopingService.get_scoped_sales(accountant_user)
        assert sale1 in scoped_acc
        assert sale2 in scoped_acc

    def test_quotations_and_orders_scoping(self, sales_rep_user, sales_rep_other, sample_customer, sample_warehouses):
        wh, _ = sample_warehouses
        q1 = Quotation.objects.create(
            number="QUO-001",
            customer=sample_customer,
            salesman=sales_rep_user,
            created_by=sales_rep_user,
            total=Decimal("500.00")
        )
        q2 = Quotation.objects.create(
            number="QUO-002",
            customer=sample_customer,
            salesman=sales_rep_other,
            created_by=sales_rep_other,
            total=Decimal("800.00")
        )

        scoped_q = DataScopingService.get_scoped_quotations(sales_rep_user)
        assert q1 in scoped_q
        assert q2 not in scoped_q

        so1 = SalesOrder.objects.create(
            order_number="SO-001",
            customer=sample_customer,
            warehouse=wh,
            order_date=timezone.now().date(),
            salesman=sales_rep_user,
            created_by=sales_rep_user
        )
        so2 = SalesOrder.objects.create(
            order_number="SO-002",
            customer=sample_customer,
            warehouse=wh,
            order_date=timezone.now().date(),
            salesman=sales_rep_other,
            created_by=sales_rep_other
        )

        scoped_so = DataScopingService.get_scoped_sales_orders(sales_rep_user)
        assert so1 in scoped_so
        assert so2 not in scoped_so

    def test_managed_warehouses_scoping(self, warehouse_keeper_user, sales_rep_user, sample_warehouses):
        wh_cairo, wh_alex = sample_warehouses

        # أمين المخزن يرى المخزن المسند له فقط
        keeper_whs = DataScopingService.get_managed_warehouses(warehouse_keeper_user)
        assert wh_cairo in keeper_whs
        assert wh_alex not in keeper_whs

        # مستخدم بدون إدارة مخازن يرى قائمة فارغة
        rep_whs = DataScopingService.get_managed_warehouses(sales_rep_user)
        assert rep_whs.count() == 0

        # فحص نموذج إذن التحويل المخزني
        form = TransferVoucherForm(user=warehouse_keeper_user)
        from_wh_qs = form.fields['from_warehouse'].queryset
        assert wh_cairo in from_wh_qs
        assert wh_alex not in from_wh_qs

    def test_credit_notes_scoping(self, sales_rep_user, sales_rep_other, sample_customer, sample_warehouses):
        wh, _ = sample_warehouses
        sale_ahmed = Sale.objects.create(
            number="INV-2026-0030",
            customer=sample_customer,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("3000.00"),
            total=Decimal("3000.00"),
            salesman=sales_rep_user,
            created_by=sales_rep_user
        )
        cn_ahmed = CreditNote.objects.create(
            credit_note_number="CN-001",
            customer=sample_customer,
            sale=sale_ahmed,
            total_amount=Decimal("300.00"),
            created_by=sales_rep_user
        )

        sale_mahmoud = Sale.objects.create(
            number="INV-2026-0031",
            customer=sample_customer,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("4000.00"),
            total=Decimal("4000.00"),
            salesman=sales_rep_other,
            created_by=sales_rep_other
        )
        cn_mahmoud = CreditNote.objects.create(
            credit_note_number="CN-002",
            customer=sample_customer,
            sale=sale_mahmoud,
            total_amount=Decimal("400.00"),
            created_by=sales_rep_other
        )

        scoped_cn = DataScopingService.get_scoped_credit_notes(sales_rep_user)
        assert cn_ahmed in scoped_cn
        assert cn_mahmoud not in scoped_cn


@pytest.mark.django_db
class TestPermissionDependenciesAndLifecycle:
    """اختبارات محرك تبعيات الصلاحيات ودورة الحياة المحوكمة"""

    def test_quotation_and_sales_order_transition_dependencies(self):
        # فحص متطلبات تحويل عرض السعر لأمر بيع
        deps_convert_order = PermissionDependencyService.get_required_dependencies(["sale.convert_to_order"])
        assert "sale.view_quotation" in deps_convert_order
        assert "sale.add_salesorder" in deps_convert_order

        # فحص متطلبات تحويل عرض السعر لفاتورة
        deps_convert_sale = PermissionDependencyService.get_required_dependencies(["sale.convert_quotation"])
        assert "sale.view_quotation" in deps_convert_sale
        assert "sale.add_sale" in deps_convert_sale

        # فحص متطلبات اعتماد أمر البيع
        deps_approve_so = PermissionDependencyService.get_required_dependencies(["sale.approve_sales_order"])
        assert "sale.view_salesorder" in deps_approve_so

        # فحص متطلبات إصدار إذن التسليم
        deps_delivery = PermissionDependencyService.get_required_dependencies(["sale.add_deliverynote"])
        assert "sale.view_salesorder" in deps_delivery

        # فحص متطلبات إصدار الإشعار الدائن
        deps_cn = PermissionDependencyService.get_required_dependencies(["sale.add_creditnote"])
        assert "sale.view_creditnote" in deps_cn
        assert "sale.view_sale" in deps_cn

    def test_auto_resolve_dependencies_for_role(self):
        # إنشاء دور تجريبي وإضافة صلاحية تحويل لأمر بيع
        role = Role.objects.create(name="test_transition_role", display_name="دور تحويل تجريبي")
        perm_transition = Permission.objects.get(codename="convert_to_order", content_type__app_label="sale")
        role.permissions.add(perm_transition)

        # حل التبعيات آلياً للدور
        added_count = PermissionDependencyService.auto_resolve_dependencies_for_role(role)
        assert added_count > 0

        # التأكد من إضافة صلاحيات الرؤية والإضافة المطلوبة
        role_codenames = set(role.permissions.values_list("codename", flat=True))
        assert "view_quotation" in role_codenames
        assert "add_salesorder" in role_codenames


@pytest.mark.django_db
class TestRoleCompareAndExportServices:
    """اختبارات خدمات ومسارات مقارنة وتصدير الأدوار"""

    def test_compare_roles_structure(self):
        # إنشاء دورين تجريبيين
        role1 = Role.objects.create(name="test_sales_role", display_name="مندوب تجريبي")
        role2 = Role.objects.create(name="test_supervisor_role", display_name="مشرف تجريبي")

        perm_view = Permission.objects.get(codename="view_sale", content_type__app_label="sale")
        perm_add = Permission.objects.get(codename="add_sale", content_type__app_label="sale")
        perm_delete = Permission.objects.get(codename="delete_sale", content_type__app_label="sale")

        role1.permissions.add(perm_view, perm_add)
        role2.permissions.add(perm_view, perm_add, perm_delete)

        comparison = PermissionService.compare_roles(role1, role2)

        # التحقق من البنية
        assert "role1" in comparison
        assert "role2" in comparison
        assert "comparison" in comparison
        assert "permissions" in comparison

        # التحقق من أن permissions مقسمة كقاموس app_label وليس قائمة خام
        assert isinstance(comparison["permissions"]["common"], dict)
        assert "sale" in comparison["permissions"]["common"]
        assert comparison["comparison"]["common_count"] == 2
        assert comparison["comparison"]["role2_only_count"] == 1

    def test_export_roles_payload(self):
        roles_export = PermissionService.export_role_configuration()
        assert "roles" in roles_export
        assert "export_timestamp" in roles_export
        assert isinstance(roles_export["roles"], list)


@pytest.mark.django_db
class TestRBACPhase11HardeningAndIDOR:
    """اختبارات سد ثغرات الـ IDOR والـ BOLA وعزل المستودعات الصارم"""

    def test_sale_duplicate_blocks_other_salesman_invoice(self, client, sales_rep_user, sales_rep_other, sample_customer, sample_warehouses):
        # منح صلاحية إضافة وعرض المبيعات للمندوب الآخر
        perm_view = Permission.objects.get(codename="view_sale", content_type__app_label="sale")
        perm_add = Permission.objects.get(codename="add_sale", content_type__app_label="sale")
        sales_rep_other.user_permissions.add(perm_view, perm_add)

        # إنشاء فاتورة للمندوب الأول
        sale_rep1 = Sale.objects.create(
            number="INV-REP1-001",
            customer=sample_customer,
            warehouse=sample_warehouses[0],
            salesman=sales_rep_user,
            created_by=sales_rep_user,
            date=timezone.now().date(),
            subtotal=Decimal("100.00"),
            total=Decimal("114.00")
        )

        # تسجيل دخول المندوب الآخر ومحاولة نسخ الفاتورة
        client.force_login(sales_rep_other)
        response = client.get(reverse("sale:sale_duplicate", kwargs={"pk": sale_rep1.pk}))
        assert response.status_code == 404

    def test_sale_add_payment_blocks_other_salesman_invoice(self, client, sales_rep_user, sales_rep_other, sample_customer, sample_warehouses):
        perm_view = Permission.objects.get(codename="view_sale", content_type__app_label="sale")
        sales_rep_other.user_permissions.add(perm_view)

        sale_rep1 = Sale.objects.create(
            number="INV-REP1-002",
            customer=sample_customer,
            warehouse=sample_warehouses[0],
            salesman=sales_rep_user,
            created_by=sales_rep_user,
            date=timezone.now().date(),
            subtotal=Decimal("200.00"),
            total=Decimal("228.00")
        )

        client.force_login(sales_rep_other)
        response = client.get(reverse("sale:sale_add_payment", kwargs={"pk": sale_rep1.pk}))
        assert response.status_code == 404

    def test_quotation_convert_blocks_unauthorized_warehouse(self, client, sales_rep_user, sample_customer, sample_warehouses):
        from product.models.stock_management import Warehouse
        # تعيين المندوب كأمين لمخزن القاهرة فقط
        wh_allowed = sample_warehouses[0]
        wh_allowed.manager = sales_rep_user
        wh_allowed.save()

        # إنشاء مخزن غير مصرح به للمندوب
        unauthorized_wh = Warehouse.objects.create(name="مخزن سري محظور", code="SEC-WH-999", is_active=True)

        from core.models import SystemSetting
        SystemSetting.set_setting('enable_quotations', 'true')

        perm_convert = Permission.objects.get(codename="convert_quotation", content_type__app_label="sale")
        perm_view = Permission.objects.get(codename="view_quotation", content_type__app_label="sale")
        sales_rep_user.user_permissions.add(perm_convert, perm_view)

        quote = Quotation.objects.create(
            number="QT-2026-999",
            customer=sample_customer,
            salesman=sales_rep_user,
            created_by=sales_rep_user,
            date=timezone.now().date(),
            subtotal=Decimal("500.00"),
            total=Decimal("570.00")
        )

        client.force_login(sales_rep_user)
        # إرسال طلب تحويل بمخزن غير مصرح به
        response = client.post(
            reverse("sale:quotation_convert_to_sale", kwargs={"pk": quote.pk}),
            {"warehouse": unauthorized_wh.id},
            follow=False
        )
        assert response.status_code == 302
        assert response.url == reverse("sale:quotation_detail", kwargs={"pk": quote.pk})
        quote.refresh_from_db()
        assert quote.converted_to_sale is None
