# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from customer.models import Customer, CustomerCreditProfile
from financial.models import Currency, ChartOfAccounts
from sale.models import (
    Sale,
    SalePayment,
    DeliveryNote,
    SalesOrder,
    InstallmentPlan,
    InstallmentItem,
    InstallmentSettlement,
    InstallmentRescheduleLog,
    InstallmentOperationAudit,
    CollectionRadarSnapshot,
)
from cheques.models import Cheque, ChequeType, ChequeStatus, ChequePurpose, ChequeInvoiceAllocation, AllocationStatus

User = get_user_model()


@pytest.mark.django_db
class TestInstallmentsSchemaAndModels:
    @pytest.fixture
    def setup_data(self):
        user = User.objects.create_user(username="test_admin", password="password123")
        currency, _ = Currency.objects.get_or_create(
            code="EGP", defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True}
        )
        customer = Customer.objects.create(
            name="شركة التغليف الحديثة",
            code="CUST-9901",
            credit_limit=Decimal("50000.00"),
            installment_credit_limit=Decimal("150000.00"),
            default_currency=currency,
        )
        credit_profile, _ = CustomerCreditProfile.objects.get_or_create(
            customer=customer,
            defaults={
                "credit_limit": Decimal("50000.00"),
                "installment_credit_limit": Decimal("150000.00"),
            },
        )
        return {
            "user": user,
            "currency": currency,
            "customer": customer,
            "credit_profile": credit_profile,
        }

    def test_customer_installment_credit_limit(self, setup_data):
        customer = setup_data["customer"]
        profile = setup_data["credit_profile"]
        assert customer.installment_credit_limit == Decimal("150000.00")
        assert profile.installment_credit_limit == Decimal("150000.00")

    def test_sale_installment_fields_and_contract_total(self, setup_data):
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-9001",
            customer=customer,
            created_by=user,
            currency=currency,
            date=timezone.now().date(),
            subtotal=Decimal("10000.00"),
            total=Decimal("10000.00"),
            is_installment_sale=True,
            markup_amount=Decimal("1200.00"),
            markup_rate=Decimal("12.000"),
            contract_total=Decimal("11200.00"),
            contract_total_functional=Decimal("11200.00"),
        )

        assert sale.is_installment_sale is True
        assert sale.contract_total == Decimal("11200.00")
        assert sale.amount_due == Decimal("11200.00")
        assert sale.is_fully_paid is False

    def test_installment_plan_and_items_lifecycle(self, setup_data):
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-9002",
            customer=customer,
            created_by=user,
            currency=currency,
            date=timezone.now().date(),
            subtotal=Decimal("10000.00"),
            total=Decimal("10000.00"),
            is_installment_sale=True,
            markup_amount=Decimal("1000.00"),
            contract_total=Decimal("11000.00"),
            contract_total_functional=Decimal("11000.00"),
        )

        plan = InstallmentPlan.objects.create(
            sale=sale,
            customer=customer,
            plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
            total_principal=Decimal("10000.00"),
            markup_rate=Decimal("10.000"),
            total_markup=Decimal("1000.00"),
            total_amount=Decimal("11000.00"),
            down_payment=Decimal("1000.00"),
            number_of_installments=2,
            start_date=timezone.now().date(),
            status=InstallmentPlan.PlanStatus.ACTIVE,
            created_by=user,
        )

        item1 = InstallmentItem.objects.create(
            plan=plan,
            installment_number=1,
            due_date=timezone.now().date(),
            principal_amount=Decimal("4500.00"),
            interest_amount=Decimal("500.00"),
            total_amount=Decimal("5000.00"),
        )
        item2 = InstallmentItem.objects.create(
            plan=plan,
            installment_number=2,
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            principal_amount=Decimal("4500.00"),
            interest_amount=Decimal("500.00"),
            total_amount=Decimal("5000.00"),
        )

        # فحص الحسابات الدقيقة للرصيد
        assert item1.remaining_principal == Decimal("4500.00")
        assert item1.remaining_interest == Decimal("500.00")
        assert item1.unearned_interest_balance == Decimal("500.00")
        assert item1.remaining_balance == Decimal("5000.00")

        # محاكاة سداد جزئي
        item1.paid_principal = Decimal("2000.00")
        item1.paid_interest = Decimal("200.00")
        item1.paid_amount = Decimal("2200.00")
        item1.save()

        assert item1.remaining_principal == Decimal("2500.00")
        assert item1.remaining_interest == Decimal("300.00")
        assert item1.remaining_balance == Decimal("2800.00")

    def test_installment_settlement_impact_on_sale_amount_due(self, setup_data):
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-9003",
            customer=customer,
            created_by=user,
            currency=currency,
            date=timezone.now().date(),
            subtotal=Decimal("10000.00"),
            total=Decimal("10000.00"),
            is_installment_sale=True,
            contract_total=Decimal("11000.00"),
        )

        plan = InstallmentPlan.objects.create(
            sale=sale,
            customer=customer,
            total_principal=Decimal("10000.00"),
            total_amount=Decimal("11000.00"),
            number_of_installments=1,
            start_date=timezone.now().date(),
            created_by=user,
        )

        item = InstallmentItem.objects.create(
            plan=plan,
            installment_number=1,
            due_date=timezone.now().date(),
            principal_amount=Decimal("10000.00"),
            interest_amount=Decimal("1000.00"),
            total_amount=Decimal("11000.00"),
        )

        assert sale.amount_due == Decimal("11000.00")

        # تسوية خصم تعجيل سداد تمويلي
        settlement = InstallmentSettlement.objects.create(
            sale=sale,
            plan=plan,
            installment_item=item,
            settlement_type=InstallmentSettlement.SettlementType.EARLY_SETTLEMENT_DISCOUNT,
            status=InstallmentSettlement.SettlementStatus.POSTED,
            affects_invoice_due=True,
            amount=Decimal("500.00"),
            created_by=user,
        )

        assert sale.amount_settled == Decimal("500.00")
        assert sale.amount_due == Decimal("10500.00")

        # تسوية تشغيلية لا تؤثر على رصيد الفاتورة (إسقاط غرامة تأخير)
        penalty_waiver = InstallmentSettlement.objects.create(
            sale=sale,
            plan=plan,
            installment_item=item,
            settlement_type=InstallmentSettlement.SettlementType.PENALTY_WAIVER,
            status=InstallmentSettlement.SettlementStatus.POSTED,
            affects_invoice_due=False,
            amount=Decimal("150.00"),
            created_by=user,
        )

        assert sale.amount_settled == Decimal("500.00")  # لم يتغير
        assert sale.amount_due == Decimal("10500.00")

        # عكس التسوية
        settlement.is_reversed = True
        settlement.status = InstallmentSettlement.SettlementStatus.REVERSED
        settlement.save()

        assert sale.amount_settled == Decimal("0.00")
        assert sale.amount_due == Decimal("11000.00")

    def test_cheque_allocation_properties_and_shared_cheque(self, setup_data):
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        cheque = Cheque.objects.create(
            voucher_number="CHQ-V-901",
            cheque_type=ChequeType.RECEIVABLE,
            cheque_number="998877",
            amount=Decimal("10000.00"),
            remaining_amount=Decimal("10000.00"),
            currency=currency,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=60),
            drawer_bank_name="CIB",
            drawer_name="شركة التغليف",
            payee_name="موهبة",
            customer=customer,
            status=ChequeStatus.IN_PORTFOLIO,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
        )

        sale1 = Sale.objects.create(
            number="INV-2026-9004", customer=customer, created_by=user,
            currency=currency, date=timezone.now().date(), subtotal=Decimal("6000.00"), total=Decimal("6000.00"),
        )
        sale2 = Sale.objects.create(
            number="INV-2026-9005", customer=customer, created_by=user,
            currency=currency, date=timezone.now().date(), subtotal=Decimal("4000.00"), total=Decimal("4000.00"),
        )

        assert cheque.total_allocated_amount == Decimal("0.00")
        assert cheque.unallocated_amount == Decimal("10000.00")
        assert cheque.is_shared_or_multi_allocated is False

        # تخصيص على الفاتورة الأولى
        alloc1 = ChequeInvoiceAllocation.objects.create(
            cheque=cheque,
            sale=sale1,
            allocated_amount=Decimal("4000.00"),
            allocated_amount_functional=Decimal("4000.00"),
            allocation_status=AllocationStatus.APPLIED,
            allocation_date=timezone.now().date(),
        )

        assert cheque.total_allocated_amount == Decimal("4000.00")
        assert cheque.unallocated_amount == Decimal("6000.00")
        assert cheque.is_shared_or_multi_allocated is False

        # تخصيص على الفاتورة الثانية (أصبح مشتركاً)
        alloc2 = ChequeInvoiceAllocation.objects.create(
            cheque=cheque,
            sale=sale2,
            allocated_amount=Decimal("3000.00"),
            allocated_amount_functional=Decimal("3000.00"),
            allocation_status=AllocationStatus.APPLIED,
            allocation_date=timezone.now().date(),
        )

        assert cheque.total_allocated_amount == Decimal("7000.00")
        assert cheque.unallocated_amount == Decimal("3000.00")
        assert cheque.is_shared_or_multi_allocated is True

        # تخصيص دفعة مقدمة
        cheque.prepaid_allocated_amount = Decimal("2000.00")
        cheque.save()

        assert cheque.total_allocated_amount == Decimal("9000.00")
        assert cheque.unallocated_amount == Decimal("1000.00")

    def test_delivery_note_pilot_run_and_authorization(self, setup_data):
        from product.models.stock_management import Warehouse
        customer = setup_data["customer"]
        user = setup_data["user"]
        wh, _ = Warehouse.objects.get_or_create(name="المخزن الرئيسي", defaults={"code": "WH-MAIN-99"})
        so = SalesOrder.objects.create(
            order_number="SO-2026-901",
            order_date=timezone.now().date(),
            customer=customer,
            warehouse=wh,
            total_amount=Decimal("50000.00"),
            created_by=user,
        )

        dn = DeliveryNote.objects.create(
            delivery_number="DN-2026-901",
            sales_order=so,
            customer=customer,
            warehouse=wh,
            delivery_date=timezone.now().date(),
            driver_name="محمد السائق",
            truck_plate_number="أ ب ج 1234",
            is_pilot_run=True,
            created_by=user,
        )

        assert dn.is_pilot_run is True
        assert dn.driver_name == "محمد السائق"

    def test_sale_payment_installment_and_governance_fields(self, setup_data):
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-9006",
            customer=customer,
            created_by=user,
            currency=currency,
            date=timezone.now().date(),
            subtotal=Decimal("20000.00"),
            total=Decimal("20000.00"),
            is_installment_sale=True,
            contract_total=Decimal("22000.00"),
        )
        plan = InstallmentPlan.objects.create(
            sale=sale, customer=customer, total_principal=Decimal("20000.00"),
            total_amount=Decimal("22000.00"), number_of_installments=2,
            start_date=timezone.now().date(), created_by=user,
        )
        item = InstallmentItem.objects.create(
            plan=plan, installment_number=1, due_date=timezone.now().date(),
            principal_amount=Decimal("10000.00"), interest_amount=Decimal("1000.00"),
            total_amount=Decimal("11000.00"),
        )

        payment = SalePayment.objects.create(
            sale=sale,
            installment_item=item,
            amount=Decimal("11000.00"),
            payment_date=timezone.now().date(),
            payment_method="cash",
            batch_id="BATCH-CMP-9001",
            third_party_payer_name="شركة الشروق للتغليف (شركة شقيقة)",
            instapay_reference="INSTA-REF-778899",
            created_by=user,
            status="posted",
        )

        assert payment.installment_item == item
        assert payment.batch_id == "BATCH-CMP-9001"
        assert payment.third_party_payer_name == "شركة الشروق للتغليف (شركة شقيقة)"
        assert payment.instapay_reference == "INSTA-REF-778899"

    def test_reschedule_log_and_operation_audit(self, setup_data):
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-9007", customer=customer, created_by=user,
            currency=currency, date=timezone.now().date(),
            subtotal=Decimal("10000.00"), total=Decimal("10000.00"),
        )
        plan = InstallmentPlan.objects.create(
            sale=sale, customer=customer, total_principal=Decimal("10000.00"),
            total_amount=Decimal("10000.00"), number_of_installments=1,
            start_date=timezone.now().date(), created_by=user,
        )
        item = InstallmentItem.objects.create(
            plan=plan, installment_number=1, due_date=timezone.now().date(),
            principal_amount=Decimal("10000.00"), total_amount=Decimal("10000.00"),
        )

        reschedule = InstallmentRescheduleLog.objects.create(
            installment=item,
            old_due_date=timezone.now().date(),
            new_due_date=timezone.now().date() + timezone.timedelta(days=30),
            penalty_action="MAINTAINED",
            reason="طلب العميل ترحيل القسط لظروف السيولة",
            collateral_renewed=True,
            approved_by=user,
        )
        assert reschedule.collateral_renewed is True
        assert reschedule.new_due_date == timezone.now().date() + timezone.timedelta(days=30)

        audit = InstallmentOperationAudit.objects.create(
            idempotency_key="IDEMP-AUDIT-901",
            plan=plan,
            action="RESCHEDULE",
            payload={"old_date": str(timezone.now().date()), "status": "OK"},
        )
        assert audit.action == "RESCHEDULE"

    def test_collection_radar_snapshot(self, setup_data):
        snapshot = CollectionRadarSnapshot.objects.create(
            snapshot_date=timezone.now().date(),
            total_uncovered_overdue=Decimal("50000.00"),
            total_cheques_under_collection=Decimal("120000.00"),
            total_due_today=Decimal("15000.00"),
            expected_cashflow_30d=Decimal("250000.00"),
            metrics_payload={"overdue_count": 5, "cheques_count": 12},
        )
        assert snapshot.total_uncovered_overdue == Decimal("50000.00")
        assert snapshot.metrics_payload["overdue_count"] == 5

    def test_customer_balance_signals_with_installment_sale(self, setup_data):
        from sale.signals import recalculate_customer_balance
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        # إنشاء فاتورة تقسيط بمبلغ تعاقدي يشمل الفوائد
        sale = Sale.objects.create(
            number="INV-2026-9008",
            customer=customer,
            created_by=user,
            currency=currency,
            date=timezone.now().date(),
            subtotal=Decimal("20000.00"),
            total=Decimal("20000.00"),
            total_functional=Decimal("20000.00"),
            is_installment_sale=True,
            markup_amount=Decimal("3000.00"),
            contract_total=Decimal("23000.00"),
            contract_total_functional=Decimal("23000.00"),
            status="confirmed",
        )

        recalculate_customer_balance(customer)
        customer.refresh_from_db()
        # يجب أن ينعكس المبلغ التعاقدي الشامل للتقسيط (23000) في رصيد العميل وليس فقط أصل الفاتورة (20000)
        assert customer.balance == Decimal("23000.00")
