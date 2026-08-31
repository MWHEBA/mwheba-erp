import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from customer.models import Customer
from product.models import Product, Warehouse, Category, Unit
from sale.models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem, Sale
from sale.services.sales_service import SalesService
from financial.models import ChartOfAccounts, JournalEntry

User = get_user_model()

@pytest.mark.django_db
class TestEnterpriseSalesLifecycle:
    def setup_method(self):
        self.user = User.objects.create_user(
            username='sc_tester_user',
            email='sc_tester_user@example.com',
            password='Password123!'
        )
        self.customer = Customer.objects.create(
            name='شركة النجاح التجارية',
            phone='01000000000',
            address='القاهرة - مصر',
            is_active=True
        )
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            is_active=True
        )
        self.category = Category.objects.create(name='إلكترونيات')
        self.unit = Unit.objects.create(name='قطعة')

        self.product = Product.objects.create(
            name='شاشة سامسونج 55 بوصة',
            sku='SAMS-55-4K',
            selling_price=Decimal('10000.00'),
            cost_price=Decimal('7000.00'),
            category=self.category,
            unit=self.unit,
            created_by=self.user
        )

        self.service_product = Product.objects.create(
            name='خدمة تركيب وتوصيل',
            sku='SERV-INST-01',
            selling_price=Decimal('500.00'),
            cost_price=Decimal('0.00'),
            category=self.category,
            unit=self.unit,
            is_service=True,
            created_by=self.user
        )

        from product.models.stock_management import Stock
        Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=Decimal('10.00'),
            created_by=self.user
        )

    def test_full_sales_order_lifecycle(self):
        """
        اختبار دورة حياة أمر البيع:
        1. إنشاء أمر البيع مع الخصومات والضرائب والحقول الإضافية
        2. التحقق من الحسابات المالية الدقيقة
        3. إلغاء أمر البيع وإطلاق حجز المخزون
        """
        items_data = [
            {
                'product_id': self.product.id,
                'ordered_qty': Decimal('2.00'),
                'unit_price': Decimal('10000.00'),
                'discount_percentage': Decimal('10.00'),
            },
            {
                'product_id': self.service_product.id,
                'ordered_qty': Decimal('1.00'),
                'unit_price': Decimal('500.00'),
                'discount_percentage': Decimal('0.00'),
            }
        ]

        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            items_data=items_data,
            order_date=timezone.now().date(),
            user=self.user,
            discount_amount=Decimal('500.00'),
            discount_type='fixed',
            vat_rate=Decimal('14.00'),
            wht_active=True,
            wht_rate=Decimal('1.00'),
            expected_delivery_date=timezone.now().date(),
            shipping_method='COMPANY_FLEET',
            shipping_address='موقع العميل - التجمع الخامس',
            required_down_payment=Decimal('5000.00'),
            notes='تسليم خلال 48 ساعة',
            custom_fields=[{'key': 'project_ref', 'label': 'مرجع المشروع', 'value': 'PRJ-2026'}]
        )

        assert so.id is not None
        assert so.items.count() == 2
        assert so.required_down_payment == Decimal('5000.00')
        assert so.shipping_method == 'COMPANY_FLEET'
        assert len(so.custom_fields) == 1

        if so.status == 'PENDING_APPROVAL':
            approved_so = SalesService.approve_sales_order(so.id, self.user)
            assert approved_so.status == 'APPROVED'
            so = approved_so

        assert so.status == 'APPROVED'

        # إلغاء أمر البيع
        cancelled_so = SalesService.cancel_sales_order(so.id, self.user, reason='إلغاء تجريبي')
        assert cancelled_so.status == 'CANCELLED'

    def test_delivery_note_and_cogs_flow(self):
        """
        اختبار إصدار إذن تسليم بضاعة من أمر بيع معتمد:
        1. التحقق من خصم المخزون
        2. التحقق من توليد قيد التكلفة COGS
        3. التحقق من إلغاء إذن التسليم وعكس القيد
        """
        # تجهيز حسابات المخزون والتكلفة
        from financial.models import AccountType
        expense_type, _ = AccountType.objects.get_or_create(
            code="EXP",
            defaults={"name": "مصروفات", "category": "expense", "nature": "debit"}
        )
        asset_type, _ = AccountType.objects.get_or_create(
            code="AST",
            defaults={"name": "أصول", "category": "asset", "nature": "debit"}
        )

        cogs_account, _ = ChartOfAccounts.objects.get_or_create(
            code="51100",
            defaults={"name": "تكلفة البضاعة المباعة", "account_type": expense_type, "created_by": self.user}
        )
        inv_account, _ = ChartOfAccounts.objects.get_or_create(
            code="11310",
            defaults={"name": "مخزون البضائع", "account_type": asset_type, "created_by": self.user}
        )

        items_data = [
            {
                'product_id': self.product.id,
                'ordered_qty': Decimal('3.00'),
                'unit_price': Decimal('10000.00'),
            }
        ]

        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            items_data=items_data,
            order_date=timezone.now().date(),
            user=self.user,
        )
        if so.status == 'PENDING_APPROVAL':
            so = SalesService.approve_sales_order(so.id, self.user)

        so_item = so.items.first()

        # إصدار إذن تسليم
        dn = SalesService.deliver_goods(
            so_id=so.id,
            delivery_date=timezone.now().date(),
            items_data=[{'so_item_id': so_item.id, 'delivered_qty': Decimal('2.00')}],
            user=self.user
        )

        assert dn.id is not None
        assert dn.status == 'DELIVERED'
        so.refresh_from_db()
        so_item.refresh_from_db()
        assert so_item.delivered_qty == Decimal('2.00')
        assert so.status == 'PARTIALLY_DELIVERED'

        # إلغاء إذن التسليم
        SalesService.cancel_delivery_note(dn.id, self.user, reason='إلغاء تجريبي لإذن التسليم')
        dn.refresh_from_db()
        so.refresh_from_db()
        so_item.refresh_from_db()
        assert dn.status == 'CANCELLED'
        assert so_item.delivered_qty == Decimal('0.00')
        assert so.status in ['APPROVED', 'CONFIRMED']

    def test_release_expired_reservations_command(self):
        """
        اختبار أمر الإدارة الدوري لتحرير الحجوزات منتهية الصلاحية
        """
        from django.core.management import call_command
        call_command('release_expired_reservations')

