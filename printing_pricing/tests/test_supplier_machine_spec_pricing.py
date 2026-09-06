import pytest
from decimal import Decimal
from django.urls import reverse
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from printing_pricing.services import PrintingCalculationEngine
from printing_pricing.views.api_views import GetPressesAPIView
from supplier.models import Supplier, SupplierService, ServiceType

User = get_user_model()

@pytest.mark.django_db
class TestSupplierMachineSpecPricing:
    """
    اختبارات معمارية عدم إظهار أو احتساب أي أسعار إلا بناءً على مواصفات ماكينة المورد
    (أوفست وديجيتال وزنكات)
    """

    def setup_method(self):
        self.user = User.objects.create_user(username='test_user_spec', password='password123')
        self.rf = RequestFactory()

        # إنشاء أنواع الخدمات
        self.st_offset, _ = ServiceType.objects.get_or_create(code='offset_printing', defaults={'name': 'طباعة أوفست'})
        self.st_digital, _ = ServiceType.objects.get_or_create(code='digital_printing', defaults={'name': 'طباعة ديجيتال'})
        self.st_ctp, _ = ServiceType.objects.get_or_create(code='ctp_plates', defaults={'name': 'زنكات CTP'})

        # إنشاء مورد تجريبي
        self.supplier = Supplier.objects.create(name='مطبعة المورد المعتمد', is_active=True)

        # إضافة ماكينة أوفست بمواصفات وأسعار حقيقية خاصة بالمورد
        self.offset_svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.st_offset,
            name='ماكينة هايدلبرج SM 74 نصف فرخ',
            base_price=Decimal('55.00'),  # سعر التراج المعتمد لهذا المورد
            minimum_charge=Decimal('180.00'),
            set_price=Decimal('220.00'),
            set_included_tirages=1,
            is_active=True,
            attributes={'sheet_size': '50x70', 'max_colors': 4}
        )

        # إضافة خدمة زنك CTP خاصة بالمورد
        self.ctp_svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.st_ctp,
            name='زنكات CTP مقاس 50×70 سم',
            base_price=Decimal('42.00'),  # سعر الزنكة الواحدة لهذا المورد
            set_price=Decimal('168.00'),
            is_active=True,
            attributes={'plate_size': 'زنك نصف فرخ'}
        )

        # إضافة ماكينة ديجيتال خاصة بالمورد
        self.digital_svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.st_digital,
            name='ماكينة زيروكس Versant ليزر',
            base_price=Decimal('3.25'),
            is_active=True,
            attributes={'price_per_page_color': 3.25, 'price_per_page_bw': 0.90}
        )

    def test_no_price_calculated_when_form_fields_empty(self):
        """
        التحقق من أن الفورم عندما يرسل قيم فارغة (لم يختر المستخدم ماكينة مورد بعد)
        لا يتم احتساب أي سعر افتراضي للأوفست أو الزنكات أو الديجيتال
        """
        payload = {
            'quantity': 1000,
            'width': 21.0,
            'height': 29.7,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'cover_printing_type': 'offset',
            'cover_press_machine': '',
            'press_rate': '',
            'cover_ctp_supplier': '',
            'plate_price': '',
            'digital_sheet_price': '',
        }
        res = PrintingCalculationEngine.calculate(payload)
        assert res['success'] is True
        # تكلفة الطباعة الأوفست وتكلفة الزنكات يجب أن تكون 0.00
        assert res['printing']['applied_press_cost'] == 0.0
        assert res['printing']['rate_per_1000'] == 0.0
        assert res['plates']['total_cost'] == 0.0
        assert res['plates']['unit_price'] == 0.0

    def test_pricing_calculated_strictly_from_selected_supplier_machine(self):
        """
        التحقق من احتساب تكلفة الأوفست والزنكات بناءً على مواصفات وأسعار ماكينة المورد المختار
        """
        payload = {
            'quantity': 1000,
            'width': 21.0,
            'height': 29.7,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'cover_printing_type': 'offset',
            'cover_press_machine': f'offset_{self.offset_svc.id}',
            'press_rate': '55.00',
            'cover_ctp_supplier': str(self.supplier.id),
            'plate_price': '42.00',
        }
        res = PrintingCalculationEngine.calculate(payload)
        assert res['success'] is True
        # يجب احتساب سعر التراج الخاص بماكينة المورد 55.00
        assert res['printing']['rate_per_1000'] == 55.0
        assert res['printing']['applied_press_cost'] >= 55.0
        # يجب احتساب سعر زنكات المورد 42.00
        assert res['plates']['unit_price'] == 42.0
        assert res['plates']['total_cost'] == float(Decimal('42.00') * 4)

    def test_digital_pricing_strictly_from_supplier_machine(self):
        """
        التحقق من احتساب الديجيتال بناءً على ماكينة المورد المختار
        """
        # بدون سعر -> 0.00
        payload_empty = {
            'quantity': 100,
            'width': 21.0,
            'height': 29.7,
            'cover_printing_type': 'digital',
            'cover_digital_machine': '',
            'digital_sheet_price': '',
        }
        res_empty = PrintingCalculationEngine.calculate(payload_empty)
        assert res_empty['printing']['total_cost'] == 0.0
        assert res_empty['printing']['click_rate'] == 0.0

        # مع سعر ماكينة المورد
        payload_selected = {
            'quantity': 100,
            'width': 21.0,
            'height': 29.7,
            'cover_printing_type': 'digital',
            'cover_digital_machine': f'digital_{self.digital_svc.id}',
            'digital_sheet_price': '3.25',
        }
        res_selected = PrintingCalculationEngine.calculate(payload_selected)
        assert res_selected['printing']['click_rate'] == 3.25
        assert res_selected['printing']['total_cost'] > 0.0

    def test_get_presses_api_returns_supplier_machines_with_normalized_specs(self):
        """
        التحقق من أن API الماكينات يرجع ماكينات المورد بمواصفاتها ومقاساتها القياسية وأسعارها الحقيقية
        """
        view = GetPressesAPIView.as_view()

        # فحص ماكينات الأوفست
        req_offset = self.rf.get(f'/printing-pricing/api/presses/?supplier_id={self.supplier.id}&order_type=offset')
        req_offset.user = self.user
        res_offset = view(req_offset)
        data_offset = res_offset.content.decode('utf-8')
        assert str(self.offset_svc.id) in data_offset
        assert '50x70' in data_offset
        assert '55.0' in data_offset

        # فحص زنكات CTP
        req_ctp = self.rf.get(f'/printing-pricing/api/presses/?supplier_id={self.supplier.id}&order_type=ctp')
        req_ctp.user = self.user
        res_ctp = view(req_ctp)
        data_ctp = res_ctp.content.decode('utf-8')
        assert str(self.ctp_svc.id) in data_ctp
        assert '42.0' in data_ctp
        assert 'standard_bed_size' in data_ctp
