import json
import pytest
from decimal import Decimal
from django.urls import reverse
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from supplier.models import Supplier, SupplierService, ServiceType
from financial.models import Currency
from printing_pricing.views.api_views import GetPaperSuppliersAPIView
from printing_pricing.views.order_views import (
    get_active_offset_suppliers,
    get_active_digital_suppliers,
    get_active_ctp_suppliers,
    get_active_paper_suppliers,
    OrderCreateView
)

User = get_user_model()

@pytest.mark.django_db
class TestPreferredSuppliersAndZeroPricing:
    """
    اختبارات معمارية الموردين المعتمدين وتصفير الأسعار الهاردكود
    """

    def setup_method(self):
        self.user = User.objects.create_user(username='test_pref_user', password='password123')
        self.rf = RequestFactory()

        # العملة
        self.currency, _ = Currency.objects.get_or_create(code='EGP', defaults={'name': 'جنيه مصري', 'symbol': 'ج.م', 'is_functional': True})

        # أنواع الخدمات
        self.st_paper, _ = ServiceType.objects.get_or_create(code='paper', defaults={'name': 'ورق'})
        self.st_offset, _ = ServiceType.objects.get_or_create(code='offset_printing', defaults={'name': 'أوفست'})
        self.st_digital, _ = ServiceType.objects.get_or_create(code='digital_printing', defaults={'name': 'ديجيتال'})
        self.st_ctp, _ = ServiceType.objects.get_or_create(code='ctp_plates', defaults={'name': 'زنكات CTP'})

        # إنشاء موردين: عادي ومعتمد
        self.supp_normal = Supplier.objects.create(name='مورد عادي', is_active=True, is_preferred=False)
        self.supp_pref = Supplier.objects.create(name='مورد معتمد', is_active=True, is_preferred=True)

        # إضافة خدمات للموردين
        for s in [self.supp_normal, self.supp_pref]:
            SupplierService.objects.create(supplier=s, service_type=self.st_paper, name='خامة ورق', base_price=Decimal('10.00'), is_active=True)
            SupplierService.objects.create(supplier=s, service_type=self.st_offset, name='ماكينة أوفست', base_price=Decimal('50.00'), is_active=True)
            SupplierService.objects.create(supplier=s, service_type=self.st_digital, name='ماكينة ديجيتال', base_price=Decimal('3.00'), is_active=True)
            SupplierService.objects.create(supplier=s, service_type=self.st_ctp, name='زنكات CTP', base_price=Decimal('40.00'), is_active=True)

    def test_paper_suppliers_api_returns_preferred_first(self):
        """التحقق من أن API موردي الورق يفرز المعتمد أولاً ويرجع حقل is_preferred"""
        view = GetPaperSuppliersAPIView.as_view()
        req = self.rf.get('/printing-pricing/api/paper-suppliers/')
        req.user = self.user
        res = view(req)
        assert res.status_code == 200
        data = json.loads(res.content)
        assert data['success'] is True
        suppliers = data['suppliers']
        assert len(suppliers) >= 2
        # المورد المعتمد يجب أن يتصدر
        assert suppliers[0]['id'] == self.supp_pref.id
        assert suppliers[0]['is_preferred'] is True
        assert suppliers[1]['id'] == self.supp_normal.id
        assert suppliers[1]['is_preferred'] is False

    def test_active_suppliers_querysets_order_preferred_first(self):
        """التحقق من أن دوال جلب الموردين في الباك إند ترتب المعتمد أولاً"""
        paper_qs = list(get_active_paper_suppliers())
        assert paper_qs[0].id == self.supp_pref.id
        assert paper_qs[0].is_preferred is True

        offset_qs = list(get_active_offset_suppliers())
        assert offset_qs[0].id == self.supp_pref.id
        assert offset_qs[0].is_preferred is True

        digital_qs = list(get_active_digital_suppliers())
        assert digital_qs[0].id == self.supp_pref.id
        assert digital_qs[0].is_preferred is True

        ctp_qs = list(get_active_ctp_suppliers())
        assert ctp_qs[0].id == self.supp_pref.id
        assert ctp_qs[0].is_preferred is True

    def test_step2_template_renders_preferred_badge_and_attribute(self):
        """التحقق من ظهور شارة (مورد معتمد) و data-preferred="true" في القالب"""
        offset_suppliers = get_active_offset_suppliers()
        paper_suppliers = get_active_paper_suppliers()
        rendered = render_to_string(
            'printing_pricing/orders/partials/step2_cover_or_main.html',
            {
                'offset_suppliers': offset_suppliers,
                'paper_suppliers': paper_suppliers,
                'currency_symbol': 'ج.م',
                'functional_currency': self.currency,
            }
        )
        assert 'data-preferred="true"' in rendered
        assert 'مورد معتمد' in rendered
        assert 'btn_apply_preferred_suppliers' in rendered

    def test_zero_hardcoded_prices_in_step2_and_step3(self):
        """التحقق من خلو القوالب من أي أسعار أو Fallbacks هاردكود قديمة"""
        rendered_step2 = render_to_string(
            'printing_pricing/orders/partials/step2_cover_or_main.html',
            {
                'currency_symbol': 'ج.م',
                'functional_currency': self.currency,
            }
        )
        # التأكد من تصفير أسعار الفرخ والسلوفان والبانر في الـ HTML
        assert 'placeholder="3.50"' not in rendered_step2
        assert 'placeholder="0.40"' not in rendered_step2
        assert 'value="50.00"' not in rendered_step2
        assert 'placeholder="0.00"' in rendered_step2

        rendered_step3 = render_to_string(
            'printing_pricing/orders/partials/step3_inner_pages.html',
            {
                'currency_symbol': 'ج.م',
                'functional_currency': self.currency,
            }
        )
        assert 'placeholder="2.40"' not in rendered_step3
        assert 'value="2.40"' not in rendered_step3
