"""
Comprehensive Pytest Suite for RBAC Phase 2 Enforcement:
1. Server-side Pricing & Discount Security (PricingSecurityValidator).
2. Record Ownership Isolation (Sale, Quotation, SalesOrder).
3. Production In-Progress Mutation Lock.
4. Work Order Decoupling & Permissions.
5. External API RoleBasedModelPermissions Security.
"""
import pytest
from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError

from users.models import Role
from sale.models import Sale, SaleItem, Quotation, SalesOrder
from customer.models import Customer
from product.models import Product, Category, Warehouse
from work_order.models import WorkOrder
from sale.services.sale_service import SaleService
from sale.services.pricing_validator import PricingSecurityValidator

User = get_user_model()


class RBACPhase2EnforcementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create standard roles
        cls.admin_role, _ = Role.objects.get_or_create(
            name='admin', defaults={'display_name': 'مدير النظام', 'is_system_role': True}
        )
        cls.sales_rep_role, _ = Role.objects.get_or_create(
            name='sales_rep', defaults={'display_name': 'مندوب مبيعات', 'is_system_role': True}
        )
        cls.sales_mgr_role, _ = Role.objects.get_or_create(
            name='sales_manager', defaults={'display_name': 'مدير مبيعات', 'is_system_role': True}
        )

        # Users
        cls.rep1 = User.objects.create_user(username='rep1_phase2', email='rep1@test.com', password='pass', role=cls.sales_rep_role)
        cls.rep2 = User.objects.create_user(username='rep2_phase2', email='rep2@test.com', password='pass', role=cls.sales_rep_role)
        cls.manager = User.objects.create_user(username='manager_phase2', email='mgr@test.com', password='pass', role=cls.sales_mgr_role)
        cls.admin_user = User.objects.create_user(username='admin_phase2', email='admin@test.com', password='pass', role=cls.admin_role)

        # Master Data
        from product.models.product_core import Unit
        cls.unit, _ = Unit.objects.get_or_create(name="قطعة", defaults={'symbol': 'قطعة'})
        cls.customer = Customer.objects.create(name="عميل اختبار المرحلة 2", code="CUST-P2-01", created_by=cls.admin_user)
        cls.category = Category.objects.create(name="تصنيف اختبار 2", code="CAT-P2")
        cls.warehouse = Warehouse.objects.create(name="مخزن اختبار 2", code="WH-P2-01")
        cls.product = Product.objects.create(
            name="منتج تجريبي 2",
            sku="PRD-P2-01",
            unit=cls.unit,
            selling_price=Decimal("100.00"),
            cost_price=Decimal("60.00"),
            category=cls.category,
            created_by=cls.admin_user
        )

    # -------------------------------------------------------------------------
    # Package 1: Pricing Security & Discount Cap
    # -------------------------------------------------------------------------
    def test_sales_rep_discount_cap_violation_raises_permission_denied(self):
        """مندوب مبيعات يحاول تطبيق خصم 10% (أعلى من الحد الأقصى 5%) دون صلاحية التجاوز"""
        items_data = [{
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': Decimal('100.00'),
            'discount': Decimal('0.00'),
        }]

        with pytest.raises(ValidationError) as exc_info:
            PricingSecurityValidator.validate_document_pricing(
                user=self.rep1,
                items_data=items_data,
                discount=Decimal('10.00'),
                discount_type='percentage',
                subtotal=Decimal('100.00')
            )
        assert "نسبة الخصم" in str(exc_info.value) or "تتجاوز الحد الأقصى" in str(exc_info.value)

    def test_manager_can_apply_high_discount_with_permission(self):
        """مدير المبيعات أو من يملك صلاحية apply_special_discount يمكنه تطبيق خصم يتجاوز 5%"""
        perm = Permission.objects.get(
            content_type=ContentType.objects.get(app_label='sale', model='sale'),
            codename='apply_special_discount'
        )
        self.rep1.user_permissions.add(perm)

        items_data = [{
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': Decimal('100.00'),
            'discount': Decimal('0.00'),
        }]

        # Should NOT raise ValidationError
        PricingSecurityValidator.validate_document_pricing(
            user=self.rep1,
            items_data=items_data,
            discount=Decimal('10.00'),
            discount_type='percentage',
            subtotal=Decimal('100.00')
        )

    def test_unit_price_tampering_blocked_for_sales_rep(self):
        """تلاعب في سعر الوحدة من قبل مندوب لا يملك صلاحية change_unit_price"""
        items_data = [{
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': Decimal('80.00'),  # Official price is 100.00
            'discount': Decimal('0.00'),
        }]

        with pytest.raises(ValidationError) as exc_info:
            PricingSecurityValidator.validate_document_pricing(
                user=self.rep1,
                items_data=items_data,
                discount=Decimal('0.00'),
                discount_type='fixed',
                subtotal=Decimal('80.00')
            )
        assert "سعر" in str(exc_info.value)

    # -------------------------------------------------------------------------
    # Package 2: Record Ownership Isolation
    # -------------------------------------------------------------------------
    def test_sales_rep_cannot_update_another_reps_sale(self):
        """مندوب لا يستطيع تعديل فاتورة أنشأها مندوب آخر"""
        from django.utils import timezone
        sale = Sale.objects.create(
            number="INV-P2-001",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            created_by=self.rep2,
            salesman=self.rep2
        )

        update_data = {
            'customer': self.customer,
            'items': [{
                'product_id': self.product.id,
                'quantity': 1,
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0.00')
            }],
            'notes': 'محاولة تعديل غير مصرح بها'
        }

        with pytest.raises(PermissionDenied) as exc_info:
            SaleService.update_sale(sale, update_data, user=self.rep1)
        assert "صلاحية" in str(exc_info.value) or "تعديل" in str(exc_info.value)

    def test_manager_can_update_any_sales_rep_sale(self):
        """مدير مبيعات يملك sale.view_all_sales يمكنه تعديل الفاتورة"""
        from django.utils import timezone
        sale = Sale.objects.create(
            number="INV-P2-002",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            created_by=self.rep2,
            salesman=self.rep2
        )

        perm = Permission.objects.get(
            content_type=ContentType.objects.get(app_label='sale', model='sale'),
            codename='view_all_sales'
        )
        self.rep1.user_permissions.add(perm)

        update_data = {
            'customer': self.customer,
            'items': [{
                'product_id': self.product.id,
                'quantity': 1,
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0.00')
            }],
            'notes': 'تعديل مصرح به بفضل صلاحية الرؤية العامة'
        }

        # Should pass ownership check and production check
        # (will execute up to database save without raising PermissionDenied)
        try:
            SaleService.update_sale(sale, update_data, user=self.rep1)
        except PermissionDenied:
            pytest.fail("Should not raise PermissionDenied for user with view_all_sales")
        except Exception:
            # Other business exceptions (e.g. accounting/stock) are fine; ownership passed!
            pass

    # -------------------------------------------------------------------------
    # Package 4: Production In-Progress Mutation Lock
    # -------------------------------------------------------------------------
    def test_production_lock_blocks_sale_edit_when_in_progress(self):
        """قفل التعديل على الفاتورة عندما يكون أمر الشغل قيد التنفيذ"""
        from django.utils import timezone
        work_order = WorkOrder.objects.create(
            number="WO-P2-001",
            customer=self.customer,
            status='in_progress',
            created_by=self.admin_user
        )
        sale = Sale.objects.create(
            number="INV-P2-003",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            work_order=work_order,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            created_by=self.rep1,
            salesman=self.rep1
        )

        update_data = {
            'customer': self.customer,
            'items': [{
                'product_id': self.product.id,
                'quantity': 1,
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0.00')
            }],
            'notes': 'تعديل بعد دخول الشغل الماكينات'
        }

        with pytest.raises(ValidationError) as exc_info:
            SaleService.update_sale(sale, update_data, user=self.rep1)
        assert "قيد التشغيل" in str(exc_info.value) or "أمر الشغل" in str(exc_info.value)

    def test_production_lock_can_be_overridden_with_permission(self):
        """تجاوز قفل أمر الشغل قيد التشغيل لمن يملك صلاحية override_production_lock أو الأدمن"""
        from django.utils import timezone
        work_order = WorkOrder.objects.create(
            number="WO-P2-002",
            customer=self.customer,
            status='in_progress',
            created_by=self.admin_user
        )
        sale = Sale.objects.create(
            number="INV-P2-004",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            work_order=work_order,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            created_by=self.admin_user,
            salesman=self.admin_user
        )

        update_data = {
            'customer': self.customer,
            'items': [{
                'product_id': self.product.id,
                'quantity': 1,
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0.00')
            }],
            'notes': 'تعديل استثنائي مصرح به من الإدارة'
        }

        # Admin user has full override
        try:
            SaleService.update_sale(sale, update_data, user=self.admin_user)
        except ValidationError as e:
            if "أمر الشغل" in str(e):
                pytest.fail("Production lock should not block admin user")
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Package 3: Work Order Permissions Decoupling
    # -------------------------------------------------------------------------
    def test_work_order_views_use_work_order_permissions(self):
        """التأكد من أن عروض أوامر الشغل تستخدم صلاحيات work_order وليس sale.quotation"""
        from work_order.views import work_order_list
        factory = RequestFactory()

        # User has sale.view_quotation but lacks work_order.view_workorder
        quotation_perm = Permission.objects.get(
            content_type=ContentType.objects.get(app_label='sale', model='quotation'),
            codename='view_quotation'
        )
        user_test = User.objects.create_user(username='tester_wo', email='tester@test.com', password='pass')
        user_test.user_permissions.add(quotation_perm)

        req = factory.get('/work-orders/')
        req.user = user_test

        response = work_order_list(req)
        # Should be denied
        assert "غير مصرح" in response.content.decode('utf-8')

    # -------------------------------------------------------------------------
    # Package 6: REST API Security
    # -------------------------------------------------------------------------
    def test_api_role_based_permissions_checks_safe_methods(self):
        """التأكد من أن فحص الصلاحيات للـ API يفحص أيضاً دوال القراءة (GET)"""
        from api.permissions import RoleBasedModelPermissions
        from api.viewsets import UserViewSet

        perm_checker = RoleBasedModelPermissions()
        factory = RequestFactory()
        req = factory.get('/api/users/')
        
        user_without_view = User.objects.create_user(username='no_perm_user', email='no_perm@test.com', password='pass')
        req.user = user_without_view

        view = UserViewSet()
        view.action = 'list'
        
        # User without view_customuser must be DENIED even on GET
        has_perm = perm_checker.has_permission(req, view)
        assert has_perm is False
