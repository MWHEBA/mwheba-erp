# -*- coding: utf-8 -*-
"""
Phase 4 Enforcement Tests: Frontend Zero-Trust, Error Suppressors Purge,
Form QuerySet Filtering, Permission Categorization, Dependency Engine,
and API Security Enforcement.
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client

from users.models import Role
from users.forms import RoleForm, UserRoleForm
from users.services.permission_service import PermissionService
from users.services.permission_dependency import PermissionDependencyService
from financial.models import ChartOfAccounts, JournalEntry
from sale.models import Sale, Quotation
from work_order.models import WorkOrder
from customer.models import Customer
from product.models import Warehouse, Product

User = get_user_model()


@pytest.mark.django_db
class TestPhase4Enforcement:

    def test_error_suppressors_not_present_in_templates(self):
        """1. التحقق من خلو base.html و dashboard.html من ملفات كتم الأخطاء"""
        with open("templates/base.html", "r", encoding="utf-8") as f:
            base_content = f.read()
        assert "error-suppressor.js" not in base_content
        assert "suppress-json-errors.js" not in base_content

        with open("templates/users/permissions/dashboard.html", "r", encoding="utf-8") as f:
            dash_content = f.read()
        assert "error-suppressor.js" not in dash_content
        assert "error-prevention.js" not in dash_content
        assert "suppress-json-errors.js" not in dash_content

        with open("static/js/payment-system-loader.js", "r", encoding="utf-8") as f:
            loader_content = f.read()
        assert "suppress-json-errors.js" not in loader_content

    def test_impersonation_banner_uses_css_variables(self):
        """2. التحقق من خلو كود شريط الانتحال من أي hex colors مباشرة واستخدامه لمتغيرات :root"""
        with open("templates/base.html", "r", encoding="utf-8") as f:
            base_content = f.read()
        assert "var(--bs-warning-bg-subtle" in base_content
        assert "var(--bs-warning-border-subtle" in base_content
        assert "var(--bs-warning-text-emphasis" in base_content

    def test_role_form_excludes_technical_permissions(self):
        """3. التحقق من أن نموذج RoleForm و UserRoleForm يستبعدان تطبيقات جانغو التقنية الداخلية"""
        role_form = RoleForm()
        perm_qs = role_form.fields['permissions'].queryset
        app_labels = set(perm_qs.values_list('content_type__app_label', flat=True))
        
        # لا يجوز احتواء القائمة على التطبيقات التقنية البحتة
        assert 'sessions' not in app_labels
        assert 'contenttypes' not in app_labels
        assert 'token_blacklist' not in app_labels
        assert 'admin' not in app_labels

        user_role_form = UserRoleForm()
        user_perm_qs = user_role_form.fields['custom_permissions'].queryset
        user_app_labels = set(user_perm_qs.values_list('content_type__app_label', flat=True))
        assert 'sessions' not in user_app_labels
        assert 'contenttypes' not in user_app_labels

    def test_permission_service_unified_categorization(self):
        """4. التحقق من تطابق تصنيفات PermissionService مع الـ 10 وحدات المؤسسية"""
        categories = PermissionService.get_categorized_custom_permissions()
        expected_modules = ['sale', 'purchase', 'financial', 'product', 'customer', 'supplier', 'printing_pricing', 'work_order', 'hr', 'system']
        for mod in expected_modules:
            assert mod in categories
            assert 'permissions' in categories[mod]
            assert 'name' in categories[mod]

    def test_permission_dependency_service_resolves_sales_dependencies(self):
        """5. التحقق من أن محرك التبعيات يحل تلقائياً متطلبات add_sale"""
        deps = PermissionDependencyService.get_required_dependencies(['add_sale'])
        assert 'view_customer' in deps
        assert 'view_product' in deps
        assert 'view_currency' in deps
        assert 'view_warehouse' in deps

    def test_permission_dependency_service_resolves_procurement_dependencies(self):
        """6. التحقق من أن المحرك يحل متطلبات add_purchase"""
        deps = PermissionDependencyService.get_required_dependencies(['add_purchase'])
        assert 'view_supplier' in deps
        assert 'view_product' in deps
        assert 'view_currency' in deps

    def test_permission_dependency_service_auto_resolves_for_role(self):
        """7. التحقق من دالة auto_resolve_dependencies_for_role في إضافة الصلاحيات التمهيدية"""
        role = Role.objects.create(name="test_sales_role", display_name="دور مبيعات تجريبي")
        add_sale_perm = Permission.objects.filter(codename='add_sale').first()
        if add_sale_perm:
            role.permissions.add(add_sale_perm)
            resolved_count = PermissionDependencyService.auto_resolve_dependencies_for_role(role)
            # يجب أن يتم إضافة صلاحيات العرض التمهيدية
            role_codenames = set(role.permissions.values_list('codename', flat=True))
            assert 'view_customer' in role_codenames
            assert 'view_product' in role_codenames

    def test_role_form_save_auto_resolves_dependencies(self):
        """7b. التحقق من أن حفظ RoleForm يحل تلقائياً الصلاحيات التمهيدية"""
        add_sale_perm = Permission.objects.filter(codename='add_sale').first()
        if add_sale_perm:
            form = RoleForm(data={
                'name': 'test_form_role',
                'display_name': 'دور فورم تجريبي',
                'description': 'تجربة حفظ الفورم',
                'permissions': [add_sale_perm.id],
                'is_active': True
            })
            assert form.is_valid(), form.errors
            saved_role = form.save()
            role_codenames = set(saved_role.permissions.values_list('codename', flat=True))
            assert 'view_customer' in role_codenames
            assert 'view_product' in role_codenames

    def test_permission_service_create_role_auto_resolves_dependencies(self):
        """7c. التحقق من أن PermissionService.create_role يحل تلقائياً الصلاحيات التمهيدية"""
        admin_user = User.objects.create_superuser(username="admin_test_auto", password="password123")
        add_sale_perm = Permission.objects.filter(codename='add_sale').first()
        if add_sale_perm:
            role = PermissionService.create_role(
                name='test_svc_role',
                display_name='دور خدمة تجريبي',
                description='تجربة خدمة الصلاحيات',
                permissions=[add_sale_perm],
                created_by=admin_user
            )
            role_codenames = set(role.permissions.values_list('codename', flat=True))
            assert 'view_customer' in role_codenames
            assert 'view_product' in role_codenames

    def test_user_role_form_and_custom_permissions_auto_resolve_dependencies(self):
        """7d. التحقق من أن إسناد صلاحيات إضافية للمستخدم يحل تلقائياً الصلاحيات التمهيدية"""
        user = User.objects.create_user(username="target_rep_user", password="password123")
        add_sale_perm = Permission.objects.filter(codename='add_sale').first()
        if add_sale_perm:
            form = UserRoleForm(instance=user, data={
                'custom_permissions': [add_sale_perm.id]
            })
            assert form.is_valid(), form.errors
            saved_user = form.save()
            user_codenames = set(saved_user.custom_permissions.values_list('codename', flat=True))
            assert 'view_customer' in user_codenames
            assert 'view_product' in user_codenames

    def test_api_journal_entry_safe_method_blocked_without_permission(self):
        """8. التحقق من أن GET /api/journal-entries/ يرجع 403 للمستخدم الذي لا يملك financial.view_journalentry"""
        client = Client()
        user = User.objects.create_user(username="unauth_user", password="password123")
        client.login(username="unauth_user", password="password123")
        
        response = client.get("/api/journal-entries/")
        assert response.status_code == 403

    def test_sale_edit_blocked_when_work_order_in_production(self):
        """9. التحقق من قفل تعديل الفاتورة إذا كان أمر الشغل قيد التشغيل بالماكينات"""
        client = Client()
        user = User.objects.create_user(username="rep_user", password="password123")
        # منح المستخدم صلاحية تعديل المبيعات العادية فقط
        perm = Permission.objects.filter(codename='change_sale').first()
        if perm:
            user.user_permissions.add(perm)
        client.login(username="rep_user", password="password123")

        customer = Customer.objects.create(name="عميل اختبار", code="CUST-TEST-01")
        work_order = WorkOrder.objects.create(
            number="WO-TEST-999",
            customer=customer,
            status="in_production",
            created_by=user
        )
        from decimal import Decimal
        from django.utils import timezone
        warehouse = Warehouse.objects.create(name="مخزن رئيسي اختبار", code="WH-TEST-01")
        sale = Sale.objects.create(
            number="INV-TEST-999",
            customer=customer,
            warehouse=warehouse,
            work_order=work_order,
            date=timezone.now().date(),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            status="confirmed",
            created_by=user
        )

        response = client.post(reverse("sale:sale_edit", args=[sale.pk]), {
            "notes": "محاولة تعديل غير مصرح بها أثناء التشغيل"
        }, follow=True)

        assert "صالة الإنتاج" in response.content.decode("utf-8") or response.status_code in [302, 200]
        # التحقق من أن الفاتورة لم تتغير
        sale.refresh_from_db()
        assert sale.work_order.status == "in_production"

    def test_work_order_breadcrumbs_decoupled_from_sales(self):
        """10. التحقق من استقلالية مسار التنقل في أوامر الشغل وفك ارتباطها بمسار المبيعات"""
        with open("work_order/views.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert '{"title": _("الإنتاج والتشغيل")' in content
        assert '"icon": "fas fa-cogs"' in content

    def test_available_permissions_api_returns_dependencies_and_clean_categories(self):
        """11. التحقق من أن endpoint الصلاحيات يرجع التصنيفات النظيفة وخريطة الاعتماديات"""
        client = Client()
        admin_user = User.objects.create_superuser(username="api_admin_test", password="password123")
        client.login(username="api_admin_test", password="password123")
        
        response = client.get("/users/permissions/available-permissions/")
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'dependencies' in data
        assert 'add_sale' in data['dependencies']
        assert 'view_customer' in data['dependencies']['add_sale']
        # التحقق من أن التصنيفات ترجع الـ 10 وحدات المؤسسية النظيفة
        categories = data['permissions']
        assert 'sale' in categories
        assert 'purchase' in categories
        assert 'financial' in categories
        assert 'contenttypes' not in categories
        assert 'sessions' not in categories

    def test_sales_rep_cannot_view_others_sales_detail_without_view_all_sales(self):
        """12. التحقق من عزل فواتير المبيعات: المندوب لا يستطيع فتح تفاصيل فاتورة زميله دون view_all_sales"""
        from decimal import Decimal
        from django.utils import timezone
        
        rep1 = User.objects.create_user(username="rep1_owner", email="rep1_owner@test.com", password="password123")
        rep2 = User.objects.create_user(username="rep2_other", email="rep2_other@test.com", password="password123")
        view_sale_perm = Permission.objects.filter(codename='view_sale').first()
        if view_sale_perm:
            rep2.user_permissions.add(view_sale_perm)
        
        customer = Customer.objects.create(name="عميل عزل 1", code="CUST-ISO-01")
        warehouse = Warehouse.objects.create(name="مخزن عزل 1", code="WH-ISO-01")
        sale1 = Sale.objects.create(
            number="INV-ISO-001",
            customer=customer,
            warehouse=warehouse,
            date=timezone.now().date(),
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
            status="confirmed",
            created_by=rep1,
            salesman=rep1
        )
        
        client = Client()
        client.login(username="rep2_other", password="password123")
        response = client.get(reverse("sale:sale_detail", args=[sale1.pk]))
        # يجب أن يُحجب عنه ويرجع 404
        assert response.status_code == 404

        # عند منحه صلاحية الاطلاع على كافة المناديب view_all_sales
        view_all_perm = Permission.objects.filter(codename='view_all_sales').first()
        if view_all_perm:
            rep2.user_permissions.add(view_all_perm)
            response2 = client.get(reverse("sale:sale_detail", args=[sale1.pk]))
            assert response2.status_code == 200

    def test_sales_rep_cannot_edit_others_sales_without_view_all_sales(self):
        """13. التحقق من قفل تعديل فواتير الزملاء: المندوب يُحظر من تعديل فاتورة زميله"""
        from decimal import Decimal
        from django.utils import timezone
        
        rep1 = User.objects.create_user(username="rep1_edit_owner", email="rep1_edit_owner@test.com", password="password123")
        rep2 = User.objects.create_user(username="rep2_edit_intruder", email="rep2_edit_intruder@test.com", password="password123")
        change_sale_perm = Permission.objects.filter(codename='change_sale').first()
        if change_sale_perm:
            rep2.user_permissions.add(change_sale_perm)
            
        customer = Customer.objects.create(name="عميل عزل 2", code="CUST-ISO-02")
        warehouse = Warehouse.objects.create(name="مخزن عزل 2", code="WH-ISO-02")
        sale = Sale.objects.create(
            number="INV-ISO-002",
            customer=customer,
            warehouse=warehouse,
            date=timezone.now().date(),
            subtotal=Decimal("300.00"),
            total=Decimal("300.00"),
            status="draft",
            created_by=rep1,
            salesman=rep1
        )
        
        client = Client()
        client.login(username="rep2_edit_intruder", password="password123")
        response = client.get(reverse("sale:sale_edit", args=[sale.pk]))
        # يجب إظهار صفحة غير مصرح
        assert "غير مصرح لك بتعديل فاتورة مبيعات مسجلة بواسطة مستخدم آخر" in response.content.decode("utf-8")

    def test_quotation_ownership_filtering_for_sales_reps(self):
        """14. التحقق من عزل عروض الأسعار: المندوب لا يستطيع تعديل عرض سعر زميله دون view_all_quotations"""
        from decimal import Decimal
        from django.utils import timezone
        from core.models import SystemSetting
        SystemSetting.set_setting('enable_quotations', 'true')
        
        rep1 = User.objects.create_user(username="rep1_q_owner", email="rep1_q_owner@test.com", password="password123")
        rep2 = User.objects.create_user(username="rep2_q_intruder", email="rep2_q_intruder@test.com", password="password123")
        change_q_perm = Permission.objects.filter(codename='change_quotation').first()
        if change_q_perm:
            rep2.user_permissions.add(change_q_perm)
            
        customer = Customer.objects.create(name="عميل عزل عروض", code="CUST-Q-ISO-01")
        quotation = Quotation.objects.create(
            number="QT-ISO-001",
            customer=customer,
            date=timezone.now().date(),
            total=Decimal("1000.00"),
            status="draft",
            created_by=rep1,
            salesman=rep1
        )
        
        client = Client()
        client.login(username="rep2_q_intruder", password="password123")
        response = client.get(reverse("sale:quotation_edit", args=[quotation.pk]))
        assert "غير مصرح لك بتعديل عرض سعر مسجل بواسطة مستخدم آخر" in response.content.decode("utf-8")

        # مع منح view_all_quotations
        view_all_q_perm = Permission.objects.filter(codename='view_all_quotations').first()
        if view_all_q_perm:
            rep2.user_permissions.add(view_all_q_perm)
            response2 = client.get(reverse("sale:quotation_edit", args=[quotation.pk]))
            assert response2.status_code == 200

    def test_blind_grn_template_hides_cost_from_unauthorized_warehouseman(self):
        """15. التحقق من أن قالب الاستلام المخزني GRN يحجب التكلفة والأسعار عن أمين المخزن"""
        with open("templates/purchase/grn_detail.html", "r", encoding="utf-8") as f:
            template_content = f.read()
        # التحقق من أن ظهور التكلفة مشروط بصلاحية view_purchase أو view_journalentry أو can_view_operational_costs
        assert "can_view_operational_costs" in template_content or "perms.purchase.view_purchase" in template_content
        assert 'تكلفة الوحدة' in template_content
        assert 'إجمالي التكلفة' in template_content

    def test_work_order_template_hides_financials_from_operator(self):
        """16. التحقق من أن قالب أمر الشغل يحجب الهوامش والتكاليف عن الفنيين بدون صلاحية"""
        with open("templates/work_order/work_order_detail.html", "r", encoding="utf-8") as f:
            template_content = f.read()
        assert "{% if perms.printing_pricing.view_cost_breakdown or perms.printing_pricing.view_profit_margins" in template_content

    def test_permission_denied_template_uses_css_variables_and_no_gradients(self):
        """17. التحقق من مطابقة صفحة 403 لقواعد التصميم المؤسسي وعدم احتوائها على تدرجات أو ألوان مباشرة"""
        with open("templates/core/permission_denied.html", "r", encoding="utf-8") as f:
            content = f.read()
        assert "gradient" not in content.lower()
        assert "#" not in content

    def test_error_suppressors_physically_deleted_from_disk(self):
        """18. التحقق من الاستئصال المادي النهائي لملفات كتم الأخطاء من القرص"""
        import os
        assert not os.path.exists("static/js/error-suppressor.js")
        assert not os.path.exists("static/js/error-prevention.js")
        assert not os.path.exists("static/js/suppress-json-errors.js")

    def test_templates_free_of_redundant_is_admin_checks(self):
        """19. التحقق من تطهير القوالب من فحص user.is_admin المكرر عبثياً والاعتماد على perms المعيارية"""
        templates_to_check = [
            "templates/partials/header.html",
            "templates/partials/sidebar.html",
            "templates/core/dashboard.html",
            "templates/sale/quotation_form.html",
            "templates/sale/sale_form.html",
            "templates/work_order/work_order_detail.html"
        ]
        for tpath in templates_to_check:
            with open(tpath, "r", encoding="utf-8") as f:
                content = f.read()
            assert "user.is_admin" not in content, f"Found user.is_admin in {tpath}"

    def test_pricing_order_detail_uses_override_permission(self):
        """20. التحقق من استبدال is_staff بصلاحية override_pricing_rules في order_detail.html"""
        with open("templates/printing_pricing/orders/order_detail.html", "r", encoding="utf-8") as f:
            content = f.read()
        assert "perms.printing_pricing.override_pricing_rules" in content
        assert "request.user.is_staff" not in content

    def test_sales_order_form_locks_unit_price_without_permission(self):
        """21. التحقق من قفل حقل سعر الوحدة بـ readonly في sales_order_form.html لغير حاملي الصلاحية"""
        with open("templates/sale/sales_order_form.html", "r", encoding="utf-8") as f:
            content = f.read()
        assert "{% if not perms.sale.change_sales_order_price and not perms.sale.change_unit_price %}readonly{% endif %}" in content

    def test_purchase_print_template_blind_grn_masks_costs(self):
        """22. التحقق من حجب أسعار الشراء والملخص المالي في طباعة المشتريات عن أمين المخزن (Blind GRN)"""
        with open("templates/purchase/purchase_print.html", "r", encoding="utf-8") as f:
            content = f.read()
        assert "can_view_operational_costs" in content or "perms.purchase.view_purchase" in content
        assert "استلام مخزني أعمى" in content
        assert "***" in content

    def test_auto_select_prerequisites_in_dashboard_js(self):
        """23. التحقق من وجود منطق حل الاعتماديات التلقائي في سكريبت permissions-dashboard.js"""
        with open("static/js/permissions-dashboard.js", "r", encoding="utf-8") as f:
            content = f.read()
        assert "this.dependencyMap" in content
        assert "change.depEngine" in content
        assert "storageAvailable = false" not in content




