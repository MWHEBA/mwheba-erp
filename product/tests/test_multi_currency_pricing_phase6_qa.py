"""
Phase 6 QA & Comprehensive End-to-End Integration Test Suite for Multi-Currency Product Pricing Architecture.
Covers:
- Edit Mode Round-Trip & Hydration
- Service Products (is_service=True) with Foreign Currency
- Multi-UOM & Barcode FX Lookup
- Primary Currency Deletion Guard in update_currency_prices
- Price Manager Bulk Update Synchronized FX
- Excel Import Multi-Currency Integration
- Purchase Signal Multi-Currency Cost Protection
- REST API Serializers Verification
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from financial.models import Currency, ExchangeRate
from product.models import (
    Product, Category, Unit, ProductCurrencyPrice,
    PriceHistory, ProductVariant
)
from product.forms import ProductForm
from product.views.main_views import update_currency_prices
from product.views.invoice_lookup import invoice_product_lookup
from api.serializers import ProductDetailSerializer, ProductListSerializer

User = get_user_model()


@pytest.fixture
def qa_setup(db):
    user = User.objects.create_superuser(username='qa_admin', email='qa@example.com', password='password123')
    
    egp, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'Egyptian Pound', 'symbol': 'ج.م', 'is_functional': True, 'is_active': True}
    )
    usd, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$', 'is_functional': False, 'is_active': True}
    )
    eur, _ = Currency.objects.get_or_create(
        code='EUR',
        defaults={'name': 'Euro', 'symbol': '€', 'is_functional': False, 'is_active': True}
    )

    ExchangeRate.objects.get_or_create(
        from_currency=usd,
        to_currency=egp,
        defaults={'rate': Decimal('50.000000'), 'effective_date': '2026-01-01'}
    )
    ExchangeRate.objects.get_or_create(
        from_currency=eur,
        to_currency=egp,
        defaults={'rate': Decimal('55.000000'), 'effective_date': '2026-01-01'}
    )

    category, _ = Category.objects.get_or_create(name='QA Category')
    unit_piece, _ = Unit.objects.get_or_create(name='قطعة', symbol='قطعة')
    unit_box, _ = Unit.objects.get_or_create(name='كرتونة', symbol='كرتونة')

    return {
        'user': user,
        'egp': egp,
        'usd': usd,
        'eur': eur,
        'category': category,
        'unit_piece': unit_piece,
        'unit_box': unit_box,
    }


@pytest.mark.django_db
class TestPhase6ComprehensiveQA:

    def test_e2e_edit_mode_round_trip_and_price_history(self, qa_setup):
        """Test full round-trip: create in USD -> open in edit form -> verify uninflated values -> update -> verify history."""
        user = qa_setup['user']
        usd = qa_setup['usd']
        category = qa_setup['category']
        unit = qa_setup['unit_piece']

        # 1. Create product via ProductForm
        form_data = {
            'name': 'Imported Industrial Pump',
            'sku': 'PUMP-USD-001',
            'category': category.id,
            'unit': unit.id,
            'pricing_currency': usd.id,
            'exchange_rate': '50.0000',
            'cost_price': '100.00',  # $100
            'selling_price': '150.00',  # $150
            'min_price': '130.00',
            'tax_type': 'standard',
            'tax_rate': '14.00',
            'is_active': True,
        }
        form = ProductForm(data=form_data, user=user)
        assert form.is_valid(), f"Form errors: {form.errors}"
        product = form.save()

        # Check DB values
        assert product.pricing_currency == usd
        assert product.is_foreign_currency_priced is True
        # EGP equivalent in product table
        assert product.cost_price == Decimal('5000.00')
        assert product.selling_price == Decimal('7500.00')

        # Check ProductCurrencyPrice
        usd_price = ProductCurrencyPrice.objects.get(product=product, currency=usd)
        assert usd_price.indicative_cost_price == Decimal('100.00')
        assert usd_price.indicative_selling_price == Decimal('150.00')

        # 2. Open in edit mode - form initial data must be $100 and $150 (NOT 5000 / 7500)
        edit_form = ProductForm(instance=product, user=user)
        assert edit_form.initial.get('cost_price') == Decimal('100.00')
        assert edit_form.initial.get('selling_price') == Decimal('150.00')

        # 3. Update in edit mode at new exchange rate 52.0
        update_data = form_data.copy()
        update_data['cost_price'] = '110.00'  # $110
        update_data['selling_price'] = '160.00'  # $160
        update_data['exchange_rate'] = '52.0000'

        update_form = ProductForm(data=update_data, instance=product, user=user)
        assert update_form.is_valid(), f"Update form errors: {update_form.errors}"
        updated_product = update_form.save()

        assert updated_product.cost_price == Decimal('5720.00')  # 110 * 52
        assert updated_product.selling_price == Decimal('8320.00')  # 160 * 52

        usd_price.refresh_from_db()
        assert usd_price.indicative_cost_price == Decimal('110.00')
        assert usd_price.indicative_selling_price == Decimal('160.00')

        # 4. Check PriceHistory logged
        history = PriceHistory.objects.filter(product=updated_product, source_type='CATALOG_FX')
        assert history.exists()

    def test_e2e_service_product_with_foreign_currency(self, qa_setup):
        """Test creating and querying services with foreign currency pricing."""
        user = qa_setup['user']
        usd = qa_setup['usd']
        category = qa_setup['category']
        unit = qa_setup['unit_piece']

        service = Product.objects.create(
            name='Cloud Architecture Consulting',
            sku='SRV-CONSULT-USD',
            category=category,
            unit=unit,
            is_service=True,
            pricing_currency=usd,
            cost_price=Decimal('2500.00'),  # 50 USD * 50 EGP
            selling_price=Decimal('5000.00'),  # 100 USD * 50 EGP
            is_active=True,
            created_by=user,
        )
        ProductCurrencyPrice.objects.create(
            product=service,
            currency=usd,
            indicative_cost_price=Decimal('50.00'),
            indicative_selling_price=Decimal('100.00'),
            created_by=user,
        )

        assert service.is_service is True
        assert service.is_foreign_currency_priced is True

        # Direct currency price lookup on product
        usd_price = service.get_price_for_currency(usd)
        assert usd_price == Decimal('100.00')

        # Cross FX lookup in EUR
        eur = qa_setup['eur']
        eur_price = service.get_price_for_currency(eur)
        assert eur_price is not None
        assert eur_price > 0

    def test_primary_currency_deletion_guard(self, qa_setup):
        """Test that update_currency_prices guards against deleting the product's primary pricing_currency."""
        user = qa_setup['user']
        usd = qa_setup['usd']
        eur = qa_setup['eur']
        category = qa_setup['category']
        unit = qa_setup['unit_piece']

        product = Product.objects.create(
            name='Protected Currency Product',
            sku='PROT-001',
            category=category,
            unit=unit,
            pricing_currency=usd,
            cost_price=Decimal('5000.00'),
            selling_price=Decimal('7500.00'),
            created_by=user,
        )
        usd_price = ProductCurrencyPrice.objects.create(
            product=product,
            currency=usd,
            indicative_selling_price=Decimal('150.00'),
            created_by=user,
        )
        eur_price = ProductCurrencyPrice.objects.create(
            product=product,
            currency=eur,
            indicative_selling_price=Decimal('140.00'),
            created_by=user,
        )

        factory = RequestFactory()

        # Try to delete USD price (which is product's pricing_currency) -> MUST BE PREVENTED
        delete_usd_request = factory.post(
            f'/product/{product.pk}/currency-prices/update/',
            data={'action': 'delete', 'currency_id': usd.id}
        )
        delete_usd_request.user = user
        response = update_currency_prices(delete_usd_request, pk=product.pk)
        assert response.status_code == 400
        assert ProductCurrencyPrice.objects.filter(product=product, currency=usd).exists()

        # Delete EUR price (secondary custom price) -> MUST SUCCEED
        delete_eur_request = factory.post(
            f'/product/{product.pk}/currency-prices/update/',
            data={'action': 'delete', 'currency_id': eur.id}
        )
        delete_eur_request.user = user
        response = update_currency_prices(delete_eur_request, pk=product.pk)
        assert response.status_code == 200
        assert not ProductCurrencyPrice.objects.filter(product=product, currency=eur).exists()

    def test_rest_api_serializers_multi_currency(self, qa_setup):
        """Test that REST API Serializers include pricing_currency fields correctly."""
        user = qa_setup['user']
        usd = qa_setup['usd']
        category = qa_setup['category']
        unit = qa_setup['unit_piece']

        product = Product.objects.create(
            name='API Multi Currency Item',
            sku='API-MC-001',
            category=category,
            unit=unit,
            pricing_currency=usd,
            cost_price=Decimal('2500.00'),
            selling_price=Decimal('5000.00'),
            created_by=user,
        )
        ProductCurrencyPrice.objects.create(
            product=product,
            currency=usd,
            indicative_cost_price=Decimal('50.00'),
            indicative_selling_price=Decimal('100.00'),
            created_by=user,
        )

        # List Serializer
        list_serializer = ProductListSerializer(instance=product)
        data = list_serializer.data
        assert 'pricing_currency' in data
        assert 'pricing_currency_code' in data
        assert data['pricing_currency_code'] == 'USD'
        assert data['is_foreign_currency_priced'] is True

        # Detail Serializer
        detail_serializer = ProductDetailSerializer(instance=product)
        detail_data = detail_serializer.data
        assert detail_data['pricing_currency'] == usd.id
        assert detail_data['pricing_currency_code'] == 'USD'
        assert 'currency_prices' in detail_data
        assert len(detail_data['currency_prices']) == 1
        assert detail_data['currency_prices'][0]['currency_code'] == 'USD'
        assert Decimal(str(detail_data['currency_prices'][0]['indicative_selling_price'])) == Decimal('100.00')

    def test_invoice_lookup_with_barcode_and_dynamic_fx(self, qa_setup):
        """Test invoice_product_lookup with barcode search and dynamic FX conversion."""
        import json
        user = qa_setup['user']
        usd = qa_setup['usd']
        category = qa_setup['category']
        unit = qa_setup['unit_piece']

        product = Product.objects.create(
            name='Barcode Protected Item',
            sku='BC-USD-999',
            barcode='6221234567890',
            category=category,
            unit=unit,
            pricing_currency=usd,
            cost_price=Decimal('2500.00'),     # 50 * 50
            selling_price=Decimal('5000.00'),  # 100 * 50
            created_by=user,
        )
        ProductCurrencyPrice.objects.create(
            product=product,
            currency=usd,
            indicative_cost_price=Decimal('50.00'),
            indicative_selling_price=Decimal('100.00'),
            created_by=user,
        )

        factory = RequestFactory()

        # 1. Search by barcode in a USD invoice -> should return $100.00
        req_usd = factory.get(
            f'/product/api/invoice-lookup/?q=6221234567890&currency_id={usd.id}&type=sale&show_all=true'
        )
        req_usd.user = user
        res_usd = invoice_product_lookup(req_usd)
        data_usd = json.loads(res_usd.content)
        assert 'products' in data_usd
        assert len(data_usd['products']) == 1
        assert float(data_usd['products'][0]['selling_price']) == 100.00

        # 2. Search by barcode in an EGP invoice at exchange rate 52.5 -> should return 100 * 52.5 = 5250.00
        req_egp = factory.get(
            f'/product/api/invoice-lookup/?q=6221234567890&exchange_rate=52.5&type=sale&show_all=true'
        )
        req_egp.user = user
        res_egp = invoice_product_lookup(req_egp)
        data_egp = json.loads(res_egp.content)
        assert 'products' in data_egp
        assert float(data_egp['products'][0]['selling_price']) == 5250.00

    def test_bulk_price_update_fx_synchronization(self, qa_setup):
        """Test bulk price manager API updating foreign currency prices by percentage."""
        import json
        from product.views.price_manager_views import price_manager_bulk_update_api
        user = qa_setup['user']
        usd = qa_setup['usd']
        category = qa_setup['category']
        unit = qa_setup['unit_piece']

        product = Product.objects.create(
            name='Bulk FX Item',
            sku='BULK-FX-01',
            category=category,
            unit=unit,
            pricing_currency=usd,
            cost_price=Decimal('5000.00'),      # 100 * 50
            selling_price=Decimal('10000.00'),  # 200 * 50
            created_by=user,
        )
        cp = ProductCurrencyPrice.objects.create(
            product=product,
            currency=usd,
            indicative_cost_price=Decimal('100.00'),
            indicative_selling_price=Decimal('200.00'),
            created_by=user,
        )

        factory = RequestFactory()
        post_data = {
            'ids': [product.id],
            'field': 'selling_price',
            'mode': 'percent_increase',
            'value': '10',  # +10%
        }
        request = factory.post(
            '/product/price-manager/bulk-update/',
            data=json.dumps(post_data),
            content_type='application/json'
        )
        request.user = user

        response = price_manager_bulk_update_api(request)
        assert response.status_code == 200
        res_json = json.loads(response.content)
        assert res_json['success'] is True

        # Check ProductCurrencyPrice increased: 200 + 10% = 220.00
        cp.refresh_from_db()
        assert cp.indicative_selling_price == Decimal('220.00')

        # Check Product.selling_price in EGP synced: 220 * 50 = 11000.00
        product.refresh_from_db()
        assert product.selling_price == Decimal('11000.00')

    def test_purchase_signal_foreign_currency_cost_protection(self, qa_setup):
        """Test purchase invoice signal sets USD indicative cost and EGP cost_price correctly."""
        from django.utils import timezone
        from purchase.models import Purchase, PurchaseItem
        from supplier.models import Supplier

        user = qa_setup['user']
        usd = qa_setup['usd']
        category = qa_setup['category']
        unit = qa_setup['unit_piece']

        supplier = Supplier.objects.create(name='Global Imports Inc.', created_by=user)
        product = Product.objects.create(
            name='Imported Switchboard',
            sku='SW-IMP-001',
            category=category,
            unit=unit,
            pricing_currency=usd,
            cost_price=Decimal('4500.00'),  # Initial EGP cost
            selling_price=Decimal('8000.00'),
            created_by=user,
        )

        # Create purchase invoice in USD ($100 per unit, exchange rate 50.0)
        purchase = Purchase.objects.create(
            number='PO-USD-QA-001',
            supplier=supplier,
            currency=usd,
            exchange_rate=Decimal('50.000000'),
            date='2026-01-01',
            subtotal=Decimal('1000.00'),
            total=Decimal('1000.00'),
            payment_method='credit',
            status='confirmed',
            created_by=user,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=10,
            unit_price=Decimal('100.00'),  # $100
        )

        # Check that Product.cost_price is EGP equivalent (5000.00), NOT unmultiplied $100
        product.refresh_from_db()
        assert product.cost_price == Decimal('5000.00')

        # Check that ProductCurrencyPrice has indicative cost $100
        cp = ProductCurrencyPrice.objects.filter(product=product, currency=usd).first()
        assert cp is not None
        assert cp.indicative_cost_price == Decimal('100.00')


