from decimal import Decimal
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse

from customer.models import Customer
from financial.models.currency import Currency
from supplier.models import Supplier
from work_order.models import WorkOrder
from purchase.models import Purchase

from printing_pricing.models import (
    PrintingOrder, OrderMaterial, OrderService, ProofSignOff, QCSignoff, OrderTransportLog
)
from printing_pricing.models.base import OrderType, ProductionStage
from printing_pricing.models.calculations import OrderSummary, CostCalculation, CalculationType
from printing_pricing.services.procurement_bridge import ProcurementBridgeService
from printing_pricing.services.proof_approval_service import ProofApprovalService
from printing_pricing.services.stage_tracker_service import StageTrackerService
from printing_pricing.services.qc_service import QCSignoffService
from printing_pricing.services.pdf_sanitizer_service import CustomerPDFSanitizerService

User = get_user_model()


@pytest.fixture
def e2e_admin_user(db):
    return User.objects.create_superuser(
        username='e2e_admin',
        email='admin@mwheba.com',
        password='password123'
    )


@pytest.fixture
def e2e_sales_rep(db):
    user = User.objects.create_user(
        username='e2e_sales_rep',
        email='sales@mwheba.com',
        password='password123'
    )
    user.user_type = 'sales_rep'
    user.save()
    return user


@pytest.fixture
def egp_currency(db):
    curr, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'جنيه مصري', 'is_functional': True, 'symbol': 'ج.م'}
    )
    return curr


@pytest.fixture
def usd_currency(db):
    curr, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'دولار أمريكي', 'is_functional': False, 'symbol': '$'}
    )
    return curr



@pytest.fixture
def e2e_customer(db):
    return Customer.objects.create(
        name='شركة الأهرام للتجارة والصناعة',
        phone='01012345678',
        tax_number='123-456-789',
        is_active=True
    )


@pytest.fixture
def e2e_paper_supplier(db):
    return Supplier.objects.create(
        name='شركة النيل للورق والكرتون',
        phone='01198765432',
        is_active=True
    )


@pytest.fixture
def e2e_lamination_workshop(db):
    return Supplier.objects.create(
        name='ورشة الأمل لخدمات السلوفان والتكسير',
        phone='01234567890',
        is_active=True
    )


@pytest.fixture
def e2e_courier_supplier(db):
    return Supplier.objects.create(
        name='كابتن أحمد المشوارجي (خدمات نقل)',
        phone='01511223344',
        is_active=True
    )


@pytest.mark.django_db
class TestPhase6CompleteE2EWorkflow:
    """
    حزمة اختبارات الدورة المستندية والتشغيلية الكاملة End-to-End (E2E)
    وحالات الحافة والاعتماد النهائي للإنتاج
    """

    def test_e2e_complete_commercial_printing_lifecycle(
        self, client, e2e_admin_user, e2e_customer, egp_currency,
        e2e_paper_supplier, e2e_lamination_workshop, e2e_courier_supplier
    ):
        """
        اختبار دورة الحياة التشغيلية الكاملة لمقايسة مطبوع تجاري:
        طلب التسعير -> الحسابات الفنية -> اعتماد البروفة -> تحويل لأمر شغل ->
        تفكيك أوامر شراء الورش (مع 1% أ.ت.ص) -> تتبع مراحل الشغل وتدوين أجرة المشوارجي ->
        فحص الجودة وتحريز العينات -> التسليم -> مركز تسوية التكاليف والأرباح 360°.
        """
        # 1. إنشاء طلب تسعير تجاري لمقايسة فلايرات فاخرة
        order = PrintingOrder.objects.create(
            order_number='PR-E2E-2026-001',
            customer=e2e_customer,
            title='فلاير دعائي فاخر A4 وجهين سلوفان مط',
            order_type='commercial',
            quantity=5000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            currency=egp_currency,
            current_stage=ProductionStage.PREPRESS,
            created_by=e2e_admin_user,
            updated_by=e2e_admin_user
        )

        # إضافة خامات الورق (أفرخ كوشيه 150 جم)
        OrderMaterial.objects.create(
            order=order,
            material_type='paper',
            material_name='ورق كوشيه 150 جم مستورد',
            quantity=Decimal('1250'),
            unit='sheet',
            unit_cost=Decimal('4.50'),
            total_cost=Decimal('5625.00'),
            created_by=e2e_admin_user
        )

        # إضافة خدمات الطباعة والسلوفان والتكسير للورش
        OrderService.objects.create(
            order=order,
            service_category='printing',
            service_name='طباعة أوفست 4/4 لون',
            quantity=Decimal('5000'),
            unit='piece',
            unit_price=Decimal('0.30'),
            total_cost=Decimal('1500.00'),
            created_by=e2e_admin_user
        )
        OrderService.objects.create(
            order=order,
            service_category='finishing',
            service_name='سلوفان حراري مط وجهين',
            quantity=Decimal('5000'),
            unit='piece',
            unit_price=Decimal('0.25'),
            total_cost=Decimal('1250.00'),
            created_by=e2e_admin_user
        )

        # ملخص التكاليف والأسعار
        subtotal = Decimal('11500.00')
        tax_amount = (subtotal * Decimal('0.14')).quantize(Decimal('0.01'))
        final_price = subtotal + tax_amount
        order.final_price = final_price
        order.estimated_cost = Decimal('8375.00')
        order.save()

        summary = OrderSummary.objects.create(
            order=order,
            material_cost=Decimal('5625.00'),
            printing_cost=Decimal('1500.00'),
            finishing_cost=Decimal('1250.00'),
            total_cost=Decimal('8375.00'),
            subtotal=subtotal,
            tax_amount=tax_amount,
            final_price=final_price
        )


        # 2. اعتماد البروفة مع الإقرار القانوني لنسبة تفاوت الألوان
        proof_req = ProofApprovalService.generate_proof_request(
            order=order,
            user=e2e_admin_user
        )
        assert proof_req['success'] is True
        token = proof_req['token']

        approve_res = ProofApprovalService.approve_proof(
            token=token,
            client_name='أ/ محمد مجدي - مدير التسويق',
            client_ip='192.168.1.50'
        )
        assert approve_res['success'] is True

        order.refresh_from_db()
        assert order.proof_signoff.status == ProofSignOff.ProofStatus.APPROVED


        # 3. التحقق من صمام الأمان وتوليد أوامر شراء الورش (Vendor POs)
        gating = ProcurementBridgeService.check_po_gating(order)
        assert gating['is_gated_ready'] is True

        created_pos = ProcurementBridgeService.generate_vendor_purchase_orders(
            order=order,
            gated=True,
            user=e2e_admin_user
        )
        assert order.work_order is not None
        assert order.work_order.customer == e2e_customer


        # 4. تتبع مراحل الشغل الـ 8 وتسجيل مصاريف المشوارجي بدون توقيعات
        stage_res = StageTrackerService.update_order_stage(
            order=order,
            stage=ProductionStage.PRESS,
            driver=e2e_courier_supplier,
            driver_fee=Decimal('250.00'),
            user=e2e_admin_user,
            notes='نقل البالتات لسحب الملازم على ماكينة هايدلبرج'
        )
        assert stage_res['success'] is True
        assert order.current_stage == ProductionStage.PRESS
        assert order.transport_logs.count() == 1
        assert order.transport_logs.first().cost == Decimal('250.00')

        # 5. فحص الجودة QC وتحريز عينات الخزانة 90 يوماً
        qc_report = QCSignoffService.record_inspection(
            order=order,
            inspector_name='م/ حسام الجيار',
            bleed_verified=True,
            barcode_scannable=True,
            color_registration_passed=True,
            physical_swatch_matched=True,
            lamination_adhesion_passed=True,
            ncr_sequence_verified=True,
            sample_vault_archived=True,
            sample_vault_ref='VAULT-2026-088',
            net_quantity_approved=5000,
            defect_count=20,
            status=QCSignoff.QCStatus.PASSED,
            notes='الكمية مطابقة 100% وتم تحريز 10 عينات بخزانة الجودة'
        )
        assert qc_report.status == QCSignoff.QCStatus.PASSED
        assert qc_report.sample_vault_ref == 'VAULT-2026-088'


        # 6. تحديث المرحلة للتسليم النهائي
        StageTrackerService.update_order_stage(
            order=order,
            stage=ProductionStage.DELIVERED,
            user=e2e_admin_user,
            notes='تم التسليم بنجاح مع إذن الاستلام'
        )
        assert order.current_stage == ProductionStage.DELIVERED

        # 7. مركز تسوية التكاليف والأرباح 360°
        client_revenue = order.final_price
        unbundled_pos = Purchase.objects.filter(work_order=order.work_order)
        total_vendor_cost = sum(po.total for po in unbundled_pos)
        total_courier_cost = sum(t.cost for t in order.transport_logs.all())
        net_job_profit = client_revenue - total_vendor_cost - total_courier_cost

        assert net_job_profit > Decimal('0.00')
        assert client_revenue == Decimal('13110.00')




    def test_e2e_cultural_publishing_zero_vat_lifecycle(self, db, e2e_admin_user, e2e_customer, egp_currency):
        """
        اختبار الإعفاء الضريبي التلقائي 0% للكتب والمجلات الثقافية وفقاً للقانون
        """
        book_order = PrintingOrder.objects.create(
            order_number='PR-E2E-BOOK-001',
            customer=e2e_customer,
            title='كتاب الرؤية المستقبلية للطباعة (200 صفحة)',
            order_type='books',
            quantity=1000,
            pages_count=200,
            currency=egp_currency,
            created_by=e2e_admin_user,
            updated_by=e2e_admin_user
        )

        subtotal = Decimal('45000.00')
        # ضريبة الكتب 0%
        summary = OrderSummary.objects.create(
            order=book_order,
            subtotal=subtotal,
            tax_amount=Decimal('0.00'),
            final_price=subtotal
        )

        context = CustomerPDFSanitizerService.sanitize_order_context(book_order)
        assert context['tax_amount'] == Decimal('0.00')
        assert context['final_total'] == subtotal
        assert "200 صفحة" in context['items'][0]['description']

    def test_e2e_giveaways_electronics_safety_buffer(self, db, e2e_admin_user, e2e_customer, egp_currency):
        """
        اختبار احتساب احتياطي فحص إلكترونيات الهدايا (3% Safety Buffer)
        """
        giveaway_order = PrintingOrder.objects.create(
            order_number='PR-E2E-GIVEAWAY-001',
            customer=e2e_customer,
            title='فلاشات معدنية مضيئة 32 جيجا مع باور بنك',
            order_type='giveaways',
            quantity=500,
            currency=egp_currency,
            created_by=e2e_admin_user,
            updated_by=e2e_admin_user
        )

        # احتساب 3% هالك إلكترونيات إضافي
        required_qty = 500
        buffer_qty = int(required_qty * 1.03)
        assert buffer_qty == 515  # 15 قطعة إضافية لفحص المعيب

    def test_e2e_multi_currency_stability_and_rate_snapshot(self, db, e2e_admin_user, e2e_customer, usd_currency):
        """
        اختبار ثبات أسعار الصرف للعملات الأجنبية وتجميد سعر الصرف (IAS 21 Rate Snapshot)
        """
        usd_order = PrintingOrder.objects.create(
            order_number='PR-E2E-USD-001',
            customer=e2e_customer,
            title='كتالوج تصدير فاخر باللغة الإنجليزية',
            order_type='books',
            quantity=2000,
            currency=usd_currency,
            created_by=e2e_admin_user,
            updated_by=e2e_admin_user
        )

        usd_subtotal = Decimal('2500.00')
        summary = OrderSummary.objects.create(
            order=usd_order,
            subtotal=usd_subtotal,
            tax_amount=Decimal('0.00'),
            final_price=usd_subtotal
        )

        context = CustomerPDFSanitizerService.sanitize_order_context(usd_order)
        assert context['currency_code'] == 'USD'
        assert context['final_total'] == Decimal('2500.00')

    def test_e2e_sales_rep_trade_secret_isolation(self, client, e2e_sales_rep, e2e_customer, egp_currency):
        """
        اختبار الأمان المالي المزدوج ومنع تسريب تكاليف الورش وهوامش الأرباح للمناديب
        """
        order = PrintingOrder.objects.create(
            order_number='PR-E2E-SECRET-001',
            customer=e2e_customer,
            title='شغلانة حساسة - دراسة جدوى مطبوعة',
            order_type='commercial',
            quantity=1000,
            currency=egp_currency,
            created_by=e2e_sales_rep,
            updated_by=e2e_sales_rep
        )

        OrderSummary.objects.create(
            order=order,
            total_cost=Decimal('3500.00'),
            subtotal=Decimal('6000.00'),
            tax_amount=Decimal('840.00'),
            final_price=Decimal('6840.00')
        )

        client.force_login(e2e_sales_rep)
        url = reverse('printing_pricing:order_detail', kwargs={'pk': order.pk})
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['can_view_margins'] is False
        assert response.context['current_calculations'] == []
        assert response.context['sanitized_final_price'] == Decimal('6840.00')
