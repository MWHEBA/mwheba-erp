import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from product.models import Warehouse, Product, Category, Unit, BatchVoucher, BatchVoucherItem

User = get_user_model()


@pytest.mark.django_db
class TestBatchVoucherViews:
    def setup_method(self):
        self.user = User.objects.create_user(
            username='voucher_user',
            password='password123',
            is_staff=True
        )
        # Grant permissions
        perms = Permission.objects.filter(codename__in=[
            'view_batchvoucher', 'add_batchvoucher', 'change_batchvoucher',
            'delete_batchvoucher', 'approve_batchvoucher'
        ])
        self.user.user_permissions.add(*perms)

        self.category = Category.objects.create(name='General')
        self.unit = Unit.objects.create(name='Piece', symbol='pc')
        self.w1 = Warehouse.objects.create(name='المخزن الرئيسي', is_active=True)
        self.w2 = Warehouse.objects.create(name='مخزن الفرع', is_active=True)

        self.p1 = Product.objects.create(
            name='Test Product 1',
            sku='TP001',
            category=self.category,
            unit=self.unit,
            cost_price=100.0,
            selling_price=150.0,
            is_active=True,
            is_service=False,
            is_bundle=False,
            created_by=self.user
        )
        self.p2 = Product.objects.create(
            name='Test Product 2',
            sku='TP002',
            category=self.category,
            unit=self.unit,
            cost_price=50.0,
            selling_price=80.0,
            is_active=True,
            is_service=False,
            is_bundle=False,
            created_by=self.user
        )

    def test_batch_voucher_create_get(self, client):
        client.login(username='voucher_user', password='password123')
        url = reverse('product:batch_voucher_create')
        response = client.get(url)
        assert response.status_code == 200
        assert 'form' in response.context
        assert 'warehouses' in response.context
        assert b'id="batch-voucher-form"' in response.content

    def test_batch_voucher_create_post(self, client):
        client.login(username='voucher_user', password='password123')
        url = reverse('product:batch_voucher_create')
        post_data = {
            'voucher_type': 'transfer',
            'warehouse': self.w1.id,
            'target_warehouse': self.w2.id,
            'party_name': 'أحمد إبراهيم',
            'reference_document': 'DOC-2026-001',
            'notes': 'تحويل بضاعة للمخزن الفرعي',
            'product[]': [str(self.p1.id), str(self.p2.id)],
            'quantity[]': ['5', '10'],
            'unit_cost[]': ['100.0', '50.0'],
        }
        response = client.post(url, data=post_data, follow=True)
        assert response.status_code == 200
        voucher = BatchVoucher.objects.first()
        assert voucher is not None
        assert voucher.voucher_type == 'transfer'
        assert voucher.warehouse == self.w1
        assert voucher.target_warehouse == self.w2
        assert voucher.party_name == 'أحمد إبراهيم'
        assert voucher.reference_document == 'DOC-2026-001'
        assert voucher.total_items == 2
        assert voucher.total_quantity == 15
        assert voucher.total_value == 1000.00
        assert voucher.items.count() == 2

    def test_batch_voucher_detail_get(self, client):
        client.login(username='voucher_user', password='password123')
        voucher = BatchVoucher.objects.create(
            voucher_type='receipt',
            warehouse=self.w1,
            purpose_type='donation',
            party_name='المتبرع الكريم',
            created_by=self.user
        )
        BatchVoucherItem.objects.create(
            batch_voucher=voucher,
            product=self.p1,
            quantity=3,
            unit_cost=100.0,
            total_cost=300.0
        )
        voucher.calculate_totals()

        url = reverse('product:batch_voucher_detail', args=[voucher.pk])
        response = client.get(url)
        assert response.status_code == 200
        assert response.context['voucher'] == voucher

    def test_batch_voucher_update_post(self, client):
        client.login(username='voucher_user', password='password123')
        voucher = BatchVoucher.objects.create(
            voucher_type='receipt',
            warehouse=self.w1,
            purpose_type='donation',
            party_name='أحمد',
            created_by=self.user
        )
        BatchVoucherItem.objects.create(
            batch_voucher=voucher,
            product=self.p1,
            quantity=2,
            unit_cost=100.0,
            total_cost=200.0
        )
        voucher.calculate_totals()

        url = reverse('product:batch_voucher_update', args=[voucher.pk])
        update_data = {
            'voucher_type': 'receipt',
            'warehouse': self.w1.id,
            'purpose_type': 'inventory_gain',
            'party_name': 'أحمد إبراهيم المحدث',
            'reference_document': 'UPD-001',
            'notes': 'تعديل بنود الإذن',
            'product[]': [str(self.p1.id), str(self.p2.id)],
            'quantity[]': ['4', '6'],
            'unit_cost[]': ['100.0', '50.0'],
        }
        response = client.post(url, data=update_data, follow=True)
        assert response.status_code == 200
        voucher.refresh_from_db()
        assert voucher.party_name == 'أحمد إبراهيم المحدث'
        assert voucher.purpose_type == 'inventory_gain'
        assert voucher.total_items == 2
        assert voucher.total_quantity == 10
        assert voucher.total_value == 700.0

    def test_batch_voucher_transfer_validation(self, client):
        client.login(username='voucher_user', password='password123')
        url = reverse('product:batch_voucher_create')
        # Same source and target warehouse
        post_data = {
            'voucher_type': 'transfer',
            'warehouse': self.w1.id,
            'target_warehouse': self.w1.id,
            'product[]': [str(self.p1.id)],
            'quantity[]': ['5'],
            'unit_cost[]': ['100.0'],
        }
        response = client.post(url, data=post_data)
        assert response.status_code == 200
        assert 'target_warehouse' in response.context['form'].errors

    def test_batch_voucher_approve(self, client):
        client.login(username='voucher_user', password='password123')
        from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
        from financial.models.currency import Currency
        egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "Egyptian Pound", "symbol": "£"})
        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Assets", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REVENUE", defaults={"name": "Revenues", "category": "revenue"})

        ChartOfAccounts.objects.get_or_create(
            code='11310',
            defaults={'name': 'حساب المخزون', 'account_type': asset_type, 'currency': egp, 'is_active': True}
        )
        ChartOfAccounts.objects.get_or_create(
            code='49110',
            defaults={'name': 'أرباح تسوية جردية', 'account_type': revenue_type, 'currency': egp, 'is_active': True}
        )

        voucher = BatchVoucher.objects.create(
            voucher_type='receipt',
            warehouse=self.w1,
            purpose_type='inventory_gain',
            party_name='أمين المخزن',
            created_by=self.user
        )
        BatchVoucherItem.objects.create(
            batch_voucher=voucher,
            product=self.p1,
            quantity=5,
            unit_cost=100.0,
            total_cost=500.0
        )
        voucher.calculate_totals()

        url = reverse('product:batch_voucher_approve', args=[voucher.pk])
        response = client.post(url, follow=True)
        assert response.status_code == 200
        voucher.refresh_from_db()
        assert voucher.status == 'approved'
        assert voucher.approved_by == self.user

    def test_batch_voucher_delete(self, client):
        client.login(username='voucher_user', password='password123')
        voucher = BatchVoucher.objects.create(
            voucher_type='receipt',
            warehouse=self.w1,
            purpose_type='donation',
            created_by=self.user
        )
        url = reverse('product:batch_voucher_delete', args=[voucher.pk])
        response = client.post(url, follow=True)
        assert response.status_code == 200
        assert not BatchVoucher.objects.filter(pk=voucher.pk).exists()

    def test_get_product_cost_api(self, client):
        client.login(username='voucher_user', password='password123')
        url = reverse('product:get_product_cost')
        response = client.get(url, {'product_id': self.p1.id})
        assert response.status_code == 200
        data = response.json()
        assert data['unit_cost'] == 100.0
        assert data['product_name'] == 'Test Product 1'
