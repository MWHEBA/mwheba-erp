from django.test import TestCase
from django.contrib.auth import get_user_model
from sale.models import CustomFieldDefinition, Sale, Quotation
from sale.services.sale_service import SaleService
from client.models import Customer
from product.models import Warehouse, Product, Unit, Category

User = get_user_model()


class CustomFieldsTestCase(TestCase):
    def setUp(self):
        from financial.models import ChartOfAccounts, AccountType, AccountingPeriod
        from datetime import date
        AccountingPeriod.objects.get_or_create(
            name='سنة 2026',
            defaults={'start_date': date(2026, 1, 1), 'end_date': date(2026, 12, 31), 'status': 'open'}
        )
        rev_type, _ = AccountType.objects.get_or_create(code='REV', defaults={'name': 'إيرادات', 'category': 'revenue'})
        asset_type, _ = AccountType.objects.get_or_create(code='AST', defaults={'name': 'أصول متداولة', 'category': 'asset'})
        exp_type, _ = AccountType.objects.get_or_create(code='EXP', defaults={'name': 'مصروفات', 'category': 'expense'})
        ChartOfAccounts.objects.get_or_create(code='40100', defaults={'name': 'إيرادات المبيعات', 'account_type': rev_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='10100', defaults={'name': 'الخزينة العامة', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='50100', defaults={'name': 'تكلفة المبيعات', 'account_type': exp_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='50300', defaults={'name': 'مصروفات أخرى', 'account_type': exp_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='10400', defaults={'name': 'المخزون', 'account_type': asset_type, 'is_active': True})

        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123'
        )
        self.customer = Customer.objects.create(name='عميل تجريبي', created_by=self.user)
        self.unit = Unit.objects.create(name='قطعة', symbol='قطعة')
        self.category = Category.objects.create(name='عام')
        self.warehouse = Warehouse.objects.create(name='المخزن الرئيسي')
        self.product = Product.objects.create(
            name='منتج تجريبي',
            unit=self.unit,
            category=self.category,
            cost_price=50,
            selling_price=100,
            created_by=self.user
        )
        from product.models import Stock
        Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=100
        )

        self.field_po = CustomFieldDefinition.objects.create(
            name='رقم أمر الشراء',
            key='po_number',
            module='sale',
            field_type='text',
            show_on_print=True,
            show_on_thermal=True,
            is_active=True
        )
        self.field_delivery = CustomFieldDefinition.objects.create(
            name='تاريخ التسليم المتوقع',
            key='delivery_date',
            module='sale',
            field_type='date',
            show_on_print=True,
            show_on_thermal=False,
            is_active=True
        )

    def test_custom_field_key_auto_generation(self):
        field = CustomFieldDefinition.objects.create(
            name='ملاحظات خاصة بالسائق',
            module='sale',
            field_type='text'
        )
        self.assertTrue(field.key.startswith('cf_') or field.key == 'po_number' or len(field.key) > 0)

    def test_parse_custom_fields_defensive(self):
        raw_json = '[{"key": "po_number", "name": "رقم أمر الشراء", "value": "PO-12345", "show_on_print": true}]'
        parsed = SaleService.parse_custom_fields(raw_json)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]['key'], 'po_number')
        self.assertEqual(parsed[0]['value'], 'PO-12345')

        # Invalid JSON fallback
        bad_parsed = SaleService.parse_custom_fields('invalid-json')
        self.assertEqual(bad_parsed, [])

    def test_smart_merge_custom_fields(self):
        existing = [{'key': 'po_number', 'name': 'رقم أمر الشراء', 'value': 'PO-999', 'show_on_print': True}]
        merged = SaleService.smart_merge_custom_fields('sale', existing)
        self.assertEqual(len(merged), 2)
        mapped = {item['key']: item['value'] for item in merged}
        self.assertEqual(mapped['po_number'], 'PO-999')
        self.assertEqual(mapped['delivery_date'], '')

    def test_sale_creation_with_custom_fields(self):
        from django.utils import timezone
        sale_data = {
            'date': timezone.now().date(),
            'customer_id': self.customer.id,
            'warehouse_id': self.warehouse.id,
            'payment_method': 'cash',
            'items': [
                {
                    'product_id': self.product.id,
                    'quantity': 2,
                    'unit_price': 100,
                    'discount': 0
                }
            ],
            'custom_fields': [
                {'key': 'po_number', 'name': 'رقم أمر الشراء', 'value': 'PO-5555', 'show_on_print': True, 'show_on_thermal': True}
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=self.user)
        self.assertIsNotNone(sale.pk)
        self.assertEqual(len(sale.custom_fields), 1)
        self.assertEqual(sale.custom_fields[0]['value'], 'PO-5555')

    def test_show_in_header_custom_field(self):
        header_field = CustomFieldDefinition.objects.create(
            name='الرقم الإشاري الخارجي',
            key='ext_ref',
            module='sale',
            field_type='text',
            show_in_header=True,
            is_active=True
        )
        merged = SaleService.smart_merge_custom_fields('sale', [])
        ref_field = next((f for f in merged if f['key'] == 'ext_ref'), None)
        self.assertIsNotNone(ref_field)
        self.assertTrue(ref_field.get('show_in_header'))
