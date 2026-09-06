import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from supplier.models import Supplier, SupplierType, ServiceType, SupplierService, ServicePriceTier
from financial.models.currency import Currency, ExchangeRate
from printing_pricing.models import PaperType, PaperSize, PaperOrigin, PrintingMachine, MachineDimension
from printing_pricing.services.bulk_price_updater import BulkPriceUpdaterService
from core.models import SystemModule

User = get_user_model()

@pytest.mark.django_db
class TestServicePricingMatrix:

    @pytest.fixture(autouse=True)
    def setup_data(self):
        SystemModule.objects.update_or_create(code='printing_pricing', defaults={'is_enabled': True})
        self.user = User.objects.create_superuser(
            username='admin_test',
            email='admin@test.com',
            password='password123'
        )
        self.sup_type, _ = SupplierType.objects.get_or_create(code='paper_sup', defaults={'name': 'مورد ورق'})
        self.currency_egp, _ = Currency.objects.get_or_create(code='EGP', defaults={'name': 'جنيه مصري', 'is_functional': True})
        self.currency_usd, _ = Currency.objects.get_or_create(code='USD', defaults={'name': 'دولار أمريكي', 'is_functional': False})

        # Exchange rate: 1 USD = 50 EGP
        ExchangeRate.objects.update_or_create(
            from_currency=self.currency_usd,
            to_currency=self.currency_egp,
            defaults={'rate': Decimal('50.000000')}
        )

        self.supplier_a, _ = Supplier.objects.get_or_create(
            code='SUP-A',
            defaults={
                'name': 'مورد أ للورق',
                'primary_type': self.sup_type,
                'is_preferred': True
            }
        )
        self.supplier_b, _ = Supplier.objects.get_or_create(
            code='SUP-B',
            defaults={
                'name': 'مورد ب للورق',
                'primary_type': self.sup_type,
                'is_preferred': False
            }
        )

        self.service_type_paper, _ = ServiceType.objects.get_or_create(
            code='paper',
            defaults={'name': 'خامات الورق', 'category': 'paper'}
        )
        self.service_type_press, _ = ServiceType.objects.get_or_create(
            code='offset_printing',
            defaults={'name': 'طباعة أوفست', 'category': 'machines'}
        )

        self.paper_type, _ = PaperType.objects.get_or_create(name='كوشيه فاخر')
        self.paper_size, _ = PaperSize.objects.get_or_create(name='70x100', defaults={'width': Decimal('70.00'), 'height': Decimal('100.00')})
        self.paper_origin, _ = PaperOrigin.objects.get_or_create(name='فنلندي')

        # خدمة ورق لمورد أ: طن بـ 50,000 ج.م
        self.service_a = SupplierService.objects.create(
            supplier=self.supplier_a,
            service_type=self.service_type_paper,
            name='كوشيه 150 جرام 70x100',
            pricing_formula='PER_TON',
            price_per_ton=Decimal('50000.00'),
            paper_type_ref=self.paper_type,
            paper_size=self.paper_size,
            paper_origin=self.paper_origin,
            gsm=150,
            currency=self.currency_egp
        )

        # خدمة ورق لمورد ب: طن بـ 48,000 ج.م (أرخص)
        self.service_b = SupplierService.objects.create(
            supplier=self.supplier_b,
            service_type=self.service_type_paper,
            name='كوشيه 150 جرام 70x100',
            pricing_formula='PER_TON',
            price_per_ton=Decimal('48000.00'),
            paper_type_ref=self.paper_type,
            paper_size=self.paper_size,
            paper_origin=self.paper_origin,
            gsm=150,
            currency=self.currency_egp
        )

        # شريحة كميات لمورد ب
        self.tier_b = ServicePriceTier.objects.create(
            service=self.service_b,
            min_quantity=5000,
            price_per_unit=Decimal('4.50')
        )

    def test_bulk_price_updater_handles_ton_price_and_tiers(self):
        """التحقق من أن التحديث المجمع يحدث سعر الطن وشرائح الكميات التابعة بالتوازي"""
        res = BulkPriceUpdaterService.bulk_update_supplier_services(
            service_ids=[self.service_b.id],
            percentage_change=Decimal('10.0'), # +10%
            user=self.user
        )
        assert res['success'] is True
        self.service_b.refresh_from_db()
        self.tier_b.refresh_from_db()

        # 48,000 * 1.10 = 52,800
        assert self.service_b.price_per_ton == Decimal('52800.00')
        # 4.50 * 1.10 = 4.95
        assert self.tier_b.price_per_unit == Decimal('4.95')

    def test_pricing_matrix_view_access_and_best_price(self, client):
        """التحقق من أن الصفحة تفتح بسلاسة وتميز المورد الأرخص بشارة الأفضل سعراً"""
        client.force_login(self.user)
        url = reverse('supplier:service_pricing_matrix')
        response = client.get(url, {'tab': 'paper'})
        assert response.status_code == 200
        assert 'أسعار الخدمات' in response.content.decode('utf-8')

        # خدمة ب هي الأرخص في السوق
        services = list(response.context['services'])
        b_service = next(s for s in services if s.id == self.service_b.id)
        a_service = next(s for s in services if s.id == self.service_a.id)

        assert b_service.is_best_price is True
        assert a_service.is_best_price is False

    def test_quick_price_update_api(self, client):
        """التحقق من أن التعديل السريع يعيد السطر المحدث row_html ويحدث سعر الفرخ"""
        client.force_login(self.user)
        url = reverse('supplier:service_price_quick_update', kwargs={'pk': self.service_a.id})
        response = client.post(
            url,
            data={'field': 'price_per_ton', 'value': '60000.00'},
            content_type='application/json'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'row_html' in data

        self.service_a.refresh_from_db()
        assert self.service_a.price_per_ton == Decimal('60000.00')

    def test_toggle_preferred_supplier(self, client):
        """التحقق من تبديل حالة المورد المعتمد بنقرة واحدة"""
        client.force_login(self.user)
        url = reverse('supplier:toggle_preferred_supplier', kwargs={'pk': self.service_b.id})
        response = client.post(url, content_type='application/json')
        assert response.status_code == 200
        assert response.json()['is_preferred'] is True

        self.supplier_b.refresh_from_db()
        assert self.supplier_b.is_preferred is True

    def test_export_excel(self, client):
        """التحقق من تصدير التقرير كـ CSV/Excel نظيف"""
        client.force_login(self.user)
        url = reverse('supplier:service_pricing_matrix') + '?tab=paper&export=excel'
        response = client.get(url)
        assert response.status_code == 200
        assert 'attachment; filename=' in response.headers.get('Content-Disposition', '')

    def test_smart_numeric_search_for_gsm_and_specs(self, client):
        """التحقق من أن محرك البحث الذكي يتعرف تلقائياً على رقم الجراماج والمقاس والمنشأ"""
        client.force_login(self.user)
        url = reverse('supplier:service_pricing_matrix')

        # 1. بحث بالجراماج "150"
        res_gsm = client.get(url, {'tab': 'paper', 'q': '150'})
        assert res_gsm.status_code == 200
        services = list(res_gsm.context['services'])
        assert len(services) == 2
        assert all(s.gsm == 150 for s in services)

        # 2. بحث برقم غير موجود "400"
        res_none = client.get(url, {'tab': 'paper', 'q': '400'})
        assert len(list(res_none.context['services'])) == 0

        # 3. بحث بالمقاس "70x100"
        res_size = client.get(url, {'tab': 'paper', 'q': '70x100'})
        assert len(list(res_size.context['services'])) == 2

        # 4. بحث بالمنشأ "فنلندي"
        res_origin = client.get(url, {'tab': 'paper', 'q': 'فنلندي'})
        assert len(list(res_origin.context['services'])) == 2

    def test_specialized_paper_filters(self, client):
        """التحقق من فلاتر الورق التخصصية (خامة، جراماج، مقاس، منشأ)"""
        client.force_login(self.user)
        url = reverse('supplier:service_pricing_matrix')

        res = client.get(url, {
            'tab': 'paper',
            'paper_type_ref': str(self.paper_type.id),
            'gsm': '150',
            'paper_size': str(self.paper_size.id),
            'paper_origin': str(self.paper_origin.id)
        })
        assert res.status_code == 200
        services = list(res.context['services'])
        assert len(services) == 2

    def test_global_market_best_price_preserved_under_single_supplier_filter(self, client):
        """التحقق من أن شارة الأفضل سعراً لا تضلل عند فلترة مورد فردي"""
        client.force_login(self.user)
        url = reverse('supplier:service_pricing_matrix')

        # 1. فلترة المورد الأرخص B
        res_b = client.get(url, {'tab': 'paper', 'supplier': str(self.supplier_b.id)})
        assert res_b.status_code == 200
        services_b = list(res_b.context['services'])
        assert len(services_b) == 1
        assert services_b[0].is_best_price is True

        # 2. فلترة المورد الأغلى A
        res_a = client.get(url, {'tab': 'paper', 'supplier': str(self.supplier_a.id)})
        assert res_a.status_code == 200
        services_a = list(res_a.context['services'])
        assert len(services_a) == 1
        assert services_a[0].is_best_price is False

    def test_ajax_response_returns_table_wrapper_html(self, client):
        """التحقق من أن رد الـ AJAX يعيد table_wrapper_html لتحديث الجدول بدون فقدان الفوكس"""
        client.force_login(self.user)
        url = reverse('supplier:service_pricing_matrix') + '?tab=paper&ajax=1'
        response = client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'table_html' in data
        assert 'table_wrapper_html' in data
        assert 'pagination_html' in data
        assert 'summary_html' in data
        assert 'paper-matrix-table' in data['table_wrapper_html']

    def test_paper_spec_options_strictly_limited_to_actual_services(self, client):
        """التحقق من أن خيارات فلاتر الورق (الخامات، الجرامات، المقاسات، المناشئ، التجار) لا تجلب إلا الموجود فعلياً"""
        # إنشاء بيانات عامة غير مستخدمة في أي خدمة
        unused_type = PaperType.objects.create(name='خامة غير مستخدمة', sort_order=99, is_active=True)
        unused_size = PaperSize.objects.create(name='مقاس غير مستخدم', width=Decimal('50.00'), height=Decimal('70.00'), sort_order=99, is_active=True)
        unused_origin = PaperOrigin.objects.create(name='منشأ غير مستخدم', sort_order=99, is_active=True)
        unused_supplier = Supplier.objects.create(code='UNUSED-SUP', name='مورد بدون ورق', is_active=True)

        client.force_login(self.user)
        url = reverse('supplier:service_pricing_matrix') + '?tab=paper'
        res = client.get(url)
        assert res.status_code == 200

        paper_types = res.context['paper_types']
        paper_sizes = res.context['paper_sizes']
        paper_origins = res.context['paper_origins']
        available_gsms = res.context['available_gsms']
        suppliers = res.context['suppliers']

        # التأكد من أن غير المستخدم لا يظهر نهائياً
        assert unused_type not in paper_types
        assert unused_size not in paper_sizes
        assert unused_origin not in paper_origins
        assert unused_supplier not in suppliers
        assert 999 not in available_gsms

        # التأكد من أن الأصناف الموجودة فعلياً فقط هي التي تظهر
        assert self.paper_type in paper_types
        assert self.paper_size in paper_sizes
        assert self.paper_origin in paper_origins
        assert 150 in available_gsms
        assert self.supplier_a in suppliers

    def test_faceted_cascading_filters_reflect_table_state(self, client):
        """التحقق من أن الفلاتر ديناميكية وتقتصر فقط على ما هو موجود في الجدول عند تصفية خامة معينة"""
        # إضافة خامة ثانية (دوبلكس) يبيعها مورد ثالث فقط
        supplier_c = Supplier.objects.create(code='SUP-C', name='مورد ج للكرتون', primary_type=self.sup_type, is_active=True)
        type_duplex = PaperType.objects.create(name='دوبلكس رمادي', sort_order=10, is_active=True)
        origin_egypt = PaperOrigin.objects.create(name='مصري', sort_order=10, is_active=True)
        SupplierService.objects.create(
            supplier=supplier_c,
            service_type=self.service_type_paper,
            name='دوبلكس 300 جرام',
            pricing_formula='PER_TON',
            price_per_ton=Decimal('35000.00'),
            paper_type_ref=type_duplex,
            paper_size=self.paper_size,
            paper_origin=origin_egypt,
            gsm=300,
            currency=self.currency_egp
        )

        client.force_login(self.user)
        # فلترة خامة الدوبلكس فقط
        url = reverse('supplier:service_pricing_matrix') + f'?tab=paper&paper_type_ref={type_duplex.id}&ajax=1'
        res = client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        data = res.json()
        assert 'filters_data' in data
        fd = data['filters_data']

        # 1. الموردين المتاحين للدوبلكس يجب أن يكون مورد ج فقط
        sup_ids = [s['id'] for s in fd['suppliers']]
        assert supplier_c.id in sup_ids
        assert self.supplier_a.id not in sup_ids
        assert self.supplier_b.id not in sup_ids

        # 2. الجرامات المتاحة يجب أن تكون 300 فقط (يختفي 150)
        gsm_ids = [g['id'] for g in fd['gsms']]
        assert 300 in gsm_ids
        assert 150 not in gsm_ids

        # 3. المناشئ المتاحة يجب أن تكون مصري فقط (يختفي فنلندي)
        origin_ids = [o['id'] for o in fd['paper_origins']]
        assert origin_egypt.id in origin_ids
        assert self.paper_origin.id not in origin_ids



