import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from financial.models import (
    TaxCode,
    TaxJurisdiction,
    TaxRule,
    TaxExemptionCertificate,
    TaxDeterminationAudit,
    TaxEvent,
    TaxCalculationLine,
    ChartOfAccounts,
    AccountType,
    AccountingPeriod,
    JournalEntry,
)
from client.models import Customer
from supplier.models import Supplier
from financial.services.tax_service import TaxDeterminationService
from financial.services.vat_settlement_service import VATSettlementService

User = get_user_model()


@pytest.mark.django_db
class TestTaxSettlementAndReports:
    """
    اختبارات المحرك الضريبي المتقدم، التسوية الشهرية لضريبة القيمة المضافة، نموذج 10، ونموذج 41
    """

    @pytest.fixture
    def setup_tax_environment(self):
        user, _ = User.objects.get_or_create(username="tax_admin", defaults={"email": "tax@mwheba.com"})
        today = timezone.now().date()

        # Accounting Period
        period, _ = AccountingPeriod.objects.get_or_create(
            name=f"TaxPeriod_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )

        asset_type = AccountType.objects.filter(category="ASSET").first() or AccountType.objects.create(code="ASSET_TEST", name="Assets", category="ASSET")
        liab_type = AccountType.objects.filter(category="LIABILITY").first() or AccountType.objects.create(code="LIAB_TEST", name="Liabilities", category="LIABILITY")

        ChartOfAccounts.objects.get_or_create(code="11010", defaults={"name": "AR Account", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11050", defaults={"name": "Input VAT Recoverable", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="22010", defaults={"name": "Output VAT Payable", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="21310", defaults={"name": "Tax Authority Payable", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11550", defaults={"name": "Tax Credit Carryforward", "account_type": asset_type, "is_active": True})

        customer = Customer.objects.create(name="Egyptian Trading Co", code="CUST-EG-001")
        supplier = Supplier.objects.create(name="Delta Supplies", code="SUPP-EG-001", tax_number="123-456-789")

        # Seed presets
        TaxDeterminationService.seed_egyptian_tax_presets()

        return user, customer, supplier, today

    def test_seed_egyptian_tax_presets(self, setup_tax_environment):
        """التحقق من توليد الأكواد المصرية القياسية بنجاح (14%، جدول 5%، سعر صفر، معفى، خصم 1%، 3%، 5%)"""
        assert TaxCode.objects.filter(code="VAT14").exists()
        assert TaxCode.objects.filter(code="VAT14_IN").exists()
        assert TaxCode.objects.filter(code="TABLE_05").exists()
        assert TaxCode.objects.filter(code="ZERO_RATED").exists()
        assert TaxCode.objects.filter(code="EXEMPT").exists()
        assert TaxCode.objects.filter(code="WHT_01").exists()
        assert TaxCode.objects.filter(code="WHT_03").exists()
        assert TaxCode.objects.filter(code="WHT_05").exists()

    def test_line_by_line_multi_tax_and_inclusive_pricing(self, setup_tax_environment):
        """التحقق من حساب ضرائب متعددة على مستوى البنود مع الأسعار الشاملة وغير الشاملة"""
        user, customer, supplier, today = setup_tax_environment

        lines = [
            {"line_id": 1, "amount": Decimal("1000.00"), "tax_code": "VAT14", "is_tax_inclusive": False},
            {"line_id": 2, "amount": Decimal("114.00"), "tax_code": "VAT14", "is_tax_inclusive": True}, # 114 inclusive = 100 base + 14 tax
            {"line_id": 3, "amount": Decimal("500.00"), "tax_code": "EXEMPT"},
        ]

        res = TaxDeterminationService.calculate_tax(
            document_type="SalesInvoice",
            document_id=101,
            customer=customer,
            lines=lines
        )

        assert res.subtotal == Decimal("1600.00") # 1000 + 100 + 500
        assert res.tax_amount == Decimal("154.00") # 140 + 14 + 0
        assert res.total_amount == Decimal("1754.00")
        assert len(res.line_decisions) == 3
        assert res.line_decisions[1]["tax_amount"] == "14.00"
        assert res.line_decisions[2]["tax_amount"] == "0.00"

    def test_exemption_quota_tracking(self, setup_tax_environment):
        """التحقق من تتبع السقف المالي لشهادة الإعفاء الضريبي"""
        user, customer, supplier, today = setup_tax_environment
        vat_code = TaxCode.objects.get(code="VAT14")

        cert = TaxExemptionCertificate.objects.create(
            customer=customer,
            certificate_number="CERT-QUOTA-100",
            tax_code=vat_code,
            valid_from=today - timedelta(days=5),
            valid_to=today + timedelta(days=30),
            max_quota_amount=Decimal("10000.00"),
            utilized_amount=Decimal("8000.00"),
            exemption_reason="Diplomatic Exemption",
            status="ACTIVE"
        )

        # Invoice within quota: 1500 <= 2000 remaining
        lines = [{"line_id": 1, "amount": Decimal("1500.00")}]
        audit = TaxDeterminationService.apply_tax_posting("SalesInvoice", 201, "INV-QUOTA-201", customer=customer, lines=lines, user=user)
        assert audit.tax_amount == Decimal("0.00")

        cert.refresh_from_db()
        assert cert.utilized_amount == Decimal("9500.00")

    def test_monthly_vat_settlement_posting(self, setup_tax_environment):
        """التحقق من تجميع إقرار القيمة المضافة وتوليد قيد المقاصة والتسوية الشهرية"""
        user, customer, supplier, today = setup_tax_environment

        # 1. Post Sales Invoice with Output VAT: 10,000 * 14% = 1,400
        sales_lines = [{"line_id": 1, "amount": Decimal("10000.00"), "tax_code": "VAT14"}]
        TaxDeterminationService.apply_tax_posting("SalesInvoice", 301, "INV-301", customer=customer, lines=sales_lines, user=user)

        # 2. Post Purchase Invoice with Input VAT: 6,000 * 14% = 840
        pur_lines = [{"line_id": 1, "amount": Decimal("6000.00"), "tax_code": "VAT14_IN"}]
        TaxDeterminationService.apply_tax_posting("PurchaseInvoice", 302, "BILL-302", supplier=supplier, lines=pur_lines, user=user)

        start_date = today.replace(day=1)
        end_date = today.replace(day=28)

        # 3. Calculate Monthly Summary
        summary = VATSettlementService.get_monthly_tax_summary(start_date, end_date)
        assert summary["output_tax_total"] == Decimal("1400.00")
        assert summary["input_tax_total"] == Decimal("840.00")
        assert summary["net_vat_due"] == Decimal("560.00")
        assert summary["is_payable"] is True
        assert summary["net_payable_amount"] == Decimal("560.00")

        # 4. Post Monthly VAT Settlement Journal Entry
        entry = VATSettlementService.post_monthly_vat_settlement(start_date, end_date, user=user)
        assert entry is not None
        assert entry.lines.count() == 3 # Debit Output VAT, Credit Input VAT, Credit Tax Authority
        assert entry.total_debit == Decimal("1400.00")
        assert entry.total_credit == Decimal("1400.00")

    def test_tax_code_is_default_and_single_source_of_truth(self, setup_tax_environment):
        """التحقق من حوكمة is_default وربطها الحي مع SystemSetting.get_setting"""
        from core.models import SystemSetting

        vat14 = TaxCode.objects.get(code="VAT14")
        assert vat14.is_default is True
        assert SystemSetting.get_setting("default_tax_rate") == 14.0

        # Create a new default VAT 15%
        vat15 = TaxCode.objects.create(
            code="VAT15",
            name="VAT 15%",
            tax_type="VAT",
            rate=Decimal("15.0000"),
            is_default=True
        )

        vat14.refresh_from_db()
        assert vat14.is_default is False
        assert vat15.is_default is True
        assert SystemSetting.get_setting("default_tax_rate") == 15.0

        # Verify WHT default does not affect VAT default
        wht01 = TaxCode.objects.get(code="WHT_01")
        assert wht01.is_default is True
        assert vat15.is_default is True

    def test_tax_rule_auto_code_generation(self, setup_tax_environment):
        """التحقق من التوليد التلقائي لكود القاعدة الضريبية عند تركه فارغاً"""
        vat14 = TaxCode.objects.get(code="VAT14")
        rule = TaxRule.objects.create(
            name="General Services Rule",
            tax_code=vat14,
            priority=10
        )
        assert rule.code is not None
        assert rule.code.startswith("RUL-")
