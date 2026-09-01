import pytest
from decimal import Decimal
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client

from customer.models import Customer
from supplier.models import Supplier
from financial.models import Currency
from printing_pricing.models.order import (
    PrintingOrder, ProofSignOff, OrderVendorAdvance,
    DieMouldCustody, QCSignoff, SupplementalRemake
)
from printing_pricing.models.calculations import OrderSummary
from printing_pricing.models.services import OrderService
from printing_pricing.services.procurement_bridge import ProcurementBridgeService
from printing_pricing.services.pdf_sanitizer_service import CustomerPDFSanitizerService
from printing_pricing.services.remake_service import SupplementalRemakeService
from printing_pricing.services.custody_service import DieMouldCustodyService
from printing_pricing.services.qc_service import QCSignoffService
from printing_pricing.services.stage_tracker_service import StageTrackerService

User = get_user_model()


@pytest.fixture
def test_setup(db):
    user = User.objects.create_user(username="procurement_tester", password="Password123!", is_staff=True)
    customer = Customer.objects.create(name="شركة الأهرام للتوزيع", phone="01012345678", tax_number="123-456-789")
    currency = Currency.objects.create(name="جنيه مصري", code="EGP", symbol="ج.م", is_functional=True)
    
    order = PrintingOrder.objects.create(
        order_number="PR260099",
        title="طباعة كتالوج سنوي 48 صفحة",
        customer=customer,
        currency=currency,
        quantity=5000,
        pages_count=48,
        order_type="BOOKS",
        created_by=user
    )

    # تجهيز ملخص تكلفة
    summary = OrderSummary.objects.create(
        order=order,
        material_cost=Decimal("8000.00"),
        printing_cost=Decimal("4000.00"),
        finishing_cost=Decimal("3500.00"),
        total_cost=Decimal("15500.00"),
        subtotal=Decimal("20000.00"),
        tax_amount=Decimal("2800.00"),
        discount_amount=Decimal("0.00"),
        profit_amount=Decimal("4500.00"),
        profit_margin_percentage=Decimal("22.50")
    )

    return {
        'user': user,
        'customer': customer,
        'order': order,
        'summary': summary,
        'client': Client()
    }


@pytest.mark.django_db
def test_po_gating_check(test_setup):
    order = test_setup['order']

    # 1. بدون بروفة معتمدة
    gating = ProcurementBridgeService.check_po_gating(order)
    assert gating['is_gated_ready'] is False
    assert "البروفة الرقمية لم يتم اعتمادها" in gating['issues'][0]

    # 2. إنشاء واعتماد البروفة
    ProofSignOff.objects.create(
        order=order,
        status=ProofSignOff.ProofStatus.APPROVED,
        approved_by_name="مدير المشتريات بالعميل"
    )
    gating_after_proof = ProcurementBridgeService.check_po_gating(order)
    assert gating_after_proof['is_gated_ready'] is True


@pytest.mark.django_db
def test_generate_vendor_purchase_orders_with_1pct_wht(test_setup):
    order = test_setup['order']
    user = test_setup['user']

    # إنشاء بروفة معتمدة
    ProofSignOff.objects.create(
        order=order,
        status=ProofSignOff.ProofStatus.APPROVED,
        approved_by_name="مدير المشتريات بالعميل"
    )

    pos = ProcurementBridgeService.generate_vendor_purchase_orders(order=order, gated=True, user=user)
    assert len(pos) >= 2  # أمر للمطبعة وأمر للتشطيبات وأمر للهدايا

    for po in pos:
        assert po.wht_active is True
        assert po.wht_rate == Decimal('1.00')
        # تحقق من خصم 1% بدقة
        expected_wht = (po.subtotal * Decimal('0.01')).quantize(Decimal('0.01'))
        assert po.wht_amount == expected_wht
        assert po.total == (po.subtotal - expected_wht)
        assert "شرط التسليم (SLA)" in po.notes
        assert "نموذج 41 ضرائب" in po.notes


@pytest.mark.django_db
def test_match_supplier_bill_and_settle_advances(test_setup):
    order = test_setup['order']
    supplier = Supplier.objects.create(name="مطبعة السلام الحديثة", is_active=True)

    # تسجيل عربون مورد
    OrderVendorAdvance.objects.create(
        order=order,
        supplier=supplier,
        amount=Decimal("1500.00"),
        is_settled=False
    )

    bill_res = ProcurementBridgeService.match_supplier_bill(
        order=order,
        supplier=supplier,
        bill_amount=Decimal("5000.00")
    )

    assert bill_res['bill_amount'] == Decimal("5000.00")
    assert bill_res['advance_deducted'] == Decimal("1500.00")
    assert bill_res['wht_deducted_1pct'] == Decimal("50.00")
    assert bill_res['net_cash_payable'] == Decimal("3450.00")  # 5000 - 1500 - 50
    assert bill_res['settled_advances_count'] == 1


@pytest.mark.django_db
def test_wht_certificate_generation(test_setup):
    supplier = Supplier.objects.create(name="ورشة الألوان المتحدة", tax_number="333-444-555", is_active=True)
    order = test_setup['order']
    ProofSignOff.objects.create(order=order, status=ProofSignOff.ProofStatus.APPROVED)

    # توليد أوامر شراء
    ProcurementBridgeService.generate_vendor_purchase_orders(order=order, gated=False)

    cert_data = ProcurementBridgeService.generate_wht_certificate_data(
        supplier=supplier,
        year=timezone.now().year,
        quarter=1
    )
    assert cert_data['supplier_name'] == supplier.name
    assert 'total_wht_deducted' in cert_data


@pytest.mark.django_db
def test_customer_pdf_sanitizer_service(test_setup):
    order = test_setup['order']
    context = CustomerPDFSanitizerService.sanitize_order_context(order)

    # تحقق من نظافة السياق وعدم وجود أي تكاليف داخلية أو أسماء ورش
    assert context['order_number'] == order.order_number
    assert context['customer_name'] == order.customer.name
    assert len(context['items']) >= 1
    assert "RGB" in context['terms_and_conditions'][3]
    assert "6 أشهر" in context['terms_and_conditions'][4]

    # اختبار رسالة الواتساب
    wa_msg = CustomerPDFSanitizerService.generate_whatsapp_quote_message(order)
    assert order.order_number in wa_msg
    assert "يسعدنا تقديم عرض السعر" in wa_msg


@pytest.mark.django_db
def test_supplemental_remake_service(test_setup):
    order = test_setup['order']
    supplier = Supplier.objects.create(name="ورشة التكسير المعيبة")

    remake = SupplementalRemakeService.create_remake_order(
        order=order,
        defective_quantity=300,
        fault_party=SupplementalRemake.FaultParty.VENDOR_FAULT,
        responsible_supplier=supplier,
        estimated_copq=Decimal("750.00"),
        reason="تلف في خطوط التكسير والريجة"
    )

    assert remake.remake_number.startswith("RMK-")
    assert remake.defective_quantity == 300
    assert remake.estimated_copq == Decimal("750.00")

    copq_total = SupplementalRemakeService.get_order_total_copq(order)
    assert copq_total == Decimal("750.00")


@pytest.mark.django_db
def test_die_mould_custody_service(test_setup):
    order = test_setup['order']
    customer = test_setup['customer']
    workshop = Supplier.objects.create(name="ورشة الفورمات المركزية")

    mould = DieMouldCustodyService.register_mould(
        code="DIE-FLDR-A4",
        name="فورمة فولدر A4 بجيبين",
        mould_type=DieMouldCustody.MouldType.DIE_CUT,
        customer=customer,
        workshop=workshop,
        storage_location="الرف 3 - القسم B"
    )

    assert mould.code == "DIE-FLDR-A4"
    assert mould.hit_count == 0
    assert mould.status == DieMouldCustody.MouldStatus.ACTIVE

    # سحب 21,000 ضربة لفحص تحويل الحالة لصيانة تلقائياً
    updated_mould = DieMouldCustodyService.record_usage(mould, order, 21000)
    assert updated_mould.hit_count == 21000
    assert updated_mould.status == DieMouldCustody.MouldStatus.MAINTENANCE


@pytest.mark.django_db
def test_qc_signoff_service(test_setup):
    order = test_setup['order']

    qc = QCSignoffService.record_inspection(
        order=order,
        inspector_name="مهندس أحمد عبد الله",
        bleed_verified=True,
        barcode_scannable=True,
        color_registration_passed=True,
        physical_swatch_matched=True,
        lamination_adhesion_passed=True,
        ncr_sequence_verified=True,
        sample_vault_archived=True,
        net_quantity_approved=4980,
        defect_count=20,
        status=QCSignoff.QCStatus.PASSED,
        notes="تم الفحص والتحريز بنجاح"
    )

    assert qc.status == QCSignoff.QCStatus.PASSED
    assert qc.bleed_verified is True
    assert qc.sample_vault_ref.startswith("VLT-")
    assert qc.net_quantity_approved == 4980


@pytest.mark.django_db
def test_document_views_rendering(test_setup):
    client = test_setup['client']
    user = test_setup['user']
    order = test_setup['order']
    client.force_login(user)

    # 1. أمر التشغيل المجمع للمطبعة
    resp1 = client.get(reverse('printing_pricing:consolidated_job_sheet', kwargs={'pk': order.pk}))
    assert resp1.status_code == 200
    assert "أمر تشغيل مطبعة مجمع" in resp1.content.decode('utf-8')

    # 2. أمر التشغيل الخارجي للورشة
    resp2 = client.get(reverse('printing_pricing:outsourced_job_sheet', kwargs={'pk': order.pk}))
    assert resp2.status_code == 200
    assert "أمر تشغيل ورشة تشطيبات خارجية" in resp2.content.decode('utf-8')

    # 3. إذن التسليم
    resp3 = client.get(reverse('printing_pricing:delivery_note', kwargs={'pk': order.pk}))
    assert resp3.status_code == 200
    assert "إذن تسليم بضاعة رسمي" in resp3.content.decode('utf-8')

    # 4. استيكرات الكراتين
    resp4 = client.get(reverse('printing_pricing:carton_labels', kwargs={'pk': order.pk}))
    assert resp4.status_code == 200
    assert "كرتونة" in resp4.content.decode('utf-8')

    # 5. الملخص التنفيذي
    resp5 = client.get(reverse('printing_pricing:executive_summary', kwargs={'pk': order.pk}))
    assert resp5.status_code == 200
    assert "ملخص التفاوض وهوامش الربح التنفيذي" in resp5.content.decode('utf-8')


@pytest.mark.django_db
def test_stage_tracker_and_courier_fee(test_setup):
    order = test_setup['order']
    user = test_setup['user']
    workshop = Supplier.objects.create(name="مطبعة السلام للأوفست", is_active=True)
    courier = Supplier.objects.create(name="محمد العربي - مندوب نقل", is_active=True)

    from printing_pricing.services.stage_tracker_service import StageTrackerService
    from printing_pricing.models.base import ProductionStage

    res = StageTrackerService.update_order_stage(
        order=order,
        stage=ProductionStage.LAMINATION,
        workshop=workshop,
        driver=courier,
        driver_fee=Decimal("150.00"),
        notes="نقل أفرخ الكوشيه من المطبعة إلى ورشة السلوفان",
        user=user
    )

    assert res['success'] is True
    assert res['current_stage'] == ProductionStage.LAMINATION
    assert res['workshop_name'] == "مطبعة السلام للأوفست"
    assert res['driver_po_number'] is not None
    assert res['from_location'] is not None
    assert res['to_location'] == "مطبعة السلام للأوفست"

    # التحقق من تسجيل سجل حركة النقل (OrderTransportLog)
    from printing_pricing.models.order import OrderTransportLog
    log = OrderTransportLog.objects.get(id=res['transport_log_id'])
    assert log.transporter == courier
    assert log.cost == Decimal("150.00")
    assert log.to_location == "مطبعة السلام للأوفست"

    # التحقق من تسجيل قيد الفاتورة للمندوب كمورد
    from purchase.models import Purchase
    driver_po = Purchase.objects.get(number=res['driver_po_number'])
    assert driver_po.supplier == courier
    assert driver_po.subtotal == Decimal("150.00")
    assert driver_po.is_service is True
    assert "أجرة نقل ومشوار" in driver_po.notes

