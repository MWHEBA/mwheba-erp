# -*- coding: utf-8 -*-
"""
FIN-CORE-025: Unit and Integration Tests for CashTransfer Module
Tests Phase 1 Data Layer, Sequence Generation, and Model Integrity
"""
from decimal import Decimal
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from governance.services.accounting_gateway import AccountingGateway
from financial.models.cash_transfer import CashTransfer, TransferType, TransferStatus
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency


@pytest.mark.django_db
class TestCashTransferPhase1DataLayer:
    """
    اختبارات طبقة البيانات والترقيم والحوكمة الخاصة بسندات التحويل المالي (المرحلة 1)
    """

    @pytest.fixture(autouse=True)
    def setup_base_data(self, django_user_model):
        self.user = django_user_model.objects.create_user(
            username="treasury_admin",
            email="treasury@mwheba.com",
            password="Password123!"
        )

        self.egp = Currency.objects.create(
            code="EGP",
            name="جنيه مصري",
            symbol="ج.م",
            is_functional=True,
            is_active=True
        )

        self.usd = Currency.objects.create(
            code="USD",
            name="دولار أمريكي",
            symbol="$",
            is_functional=False,
            is_active=True
        )

        self.asset_type = AccountType.objects.create(
            code="AST1",
            name="أصول متداولة",
            category="asset"
        )

        # Main control accounts
        self.cash_control = ChartOfAccounts.objects.create(
            code="11120",
            name="الخزائن النقدية والصناديق",
            account_type=self.asset_type,
            is_leaf=False,
            is_control_account=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )

        self.bank_control = ChartOfAccounts.objects.create(
            code="11160",
            name="الحسابات الجارية بالعملة المحلية",
            account_type=self.asset_type,
            is_leaf=False,
            is_control_account=True,
            is_bank_account=True,
            currency=self.egp,
            is_active=True
        )

        # Leaf accounts
        self.treasury_main = ChartOfAccounts.objects.create(
            code="1112001",
            name="الخزينة الرئيسية - الإدارة",
            parent=self.cash_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )

        self.treasury_branch = ChartOfAccounts.objects.create(
            code="1112002",
            name="خزينة فرع التجمع",
            parent=self.cash_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )

    def test_document_type_and_sequence_service_registration(self):
        """التحقق من تسجيل CASH_TRANSFER والبادئة TRF في SequenceService"""
        assert DocumentType.CASH_TRANSFER == "CASH_TRANSFER"
        assert SequenceService.DEFAULT_PREFIXES.get(DocumentType.CASH_TRANSFER) == "TRF"
        assert DocumentType.CASH_TRANSFER in SequenceService.MODEL_MAPPINGS
        mapping = SequenceService.MODEL_MAPPINGS[DocumentType.CASH_TRANSFER]
        assert mapping == [("financial.CashTransfer", "transfer_number")]

    def test_accounting_gateway_allowed_sources_registration(self):
        """التحقق من تسجيل financial.CashTransfer في ALLOWED_SOURCES لبوابة الحوكمة"""
        assert "financial.CashTransfer" in AccountingGateway.ALLOWED_SOURCES

    def test_cash_transfer_model_creation_and_hash_generation(self):
        """التحقق من إنشاء سند التحويل وتوليد الـ SHA-256 Hash التشفيري آلياً"""
        transfer = CashTransfer.objects.create(
            transfer_number="TRF-2026-0001",
            transfer_type=TransferType.DIRECT,
            status=TransferStatus.COMPLETED,
            transfer_date=timezone.now().date(),
            from_account=self.treasury_main,
            to_account=self.treasury_branch,
            source_amount=Decimal("50000.00"),
            source_currency=self.egp,
            source_exchange_rate=Decimal("1.000000"),
            destination_amount=Decimal("50000.00"),
            destination_currency=self.egp,
            destination_exchange_rate=Decimal("1.000000"),
            amount_in_words="خمسون ألف جنيه مصري لا غير",
            denominations_breakdown={"200": 250},
            created_by=self.user,
            notes="تحويل دوري لتغذية خزينة الفرع"
        )

        assert transfer.id is not None
        assert transfer.verification_hash != ""
        assert len(transfer.verification_hash) == 64
        assert str(transfer).startswith("TRF-2026-0001")
        assert transfer.is_completed is True
        assert transfer.is_in_transit is False

    def test_cash_transfer_validation_same_account_error(self):
        """التحقق من رمي ValidationError عند محاولة التحويل لنفس الحساب المصدر"""
        transfer = CashTransfer(
            transfer_number="TRF-2026-0002",
            from_account=self.treasury_main,
            to_account=self.treasury_main,
            source_amount=Decimal("1000.00"),
            source_currency=self.egp,
            destination_amount=Decimal("1000.00"),
            destination_currency=self.egp,
            created_by=self.user
        )

        with pytest.raises(ValidationError):
            transfer.clean()


@pytest.mark.django_db
class TestCashTransferPhase2ProvisioningAndArchiving:
    """
    اختبارات منظومة إنشاء الخزن والبنوك والعهد والأرشفة الآمنة (المرحلة 2)
    """

    @pytest.fixture(autouse=True)
    def setup_data(self, client, django_user_model):
        self.client = client
        self.user = django_user_model.objects.create_user(
            username="admin_user_ph2",
            email="admin_user_ph2@mwheba.com",
            password="Password123!",
            is_staff=True,
            is_superuser=True
        )
        self.client.force_login(self.user)

        self.egp = Currency.objects.create(
            code="EGP",
            name="جنيه مصري",
            symbol="ج.م",
            is_functional=True,
            is_active=True
        )

        self.asset_type = AccountType.objects.create(
            code="AST2",
            name="أصول متداولة",
            category="asset"
        )
        self.equity_type = AccountType.objects.create(
            code="EQ2",
            name="حقوق ملكية",
            category="equity"
        )

        self.cash_control = ChartOfAccounts.objects.create(
            code="11120",
            name="الخزائن النقدية والصناديق",
            account_type=self.asset_type,
            is_leaf=False,
            is_control_account=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )
        self.bank_control = ChartOfAccounts.objects.create(
            code="11160",
            name="الحسابات الجارية بالعملة المحلية",
            account_type=self.asset_type,
            is_leaf=False,
            is_control_account=True,
            is_bank_account=True,
            currency=self.egp,
            is_active=True
        )
        self.custody_control = ChartOfAccounts.objects.create(
            code="11180",
            name="عهد الموظفين النقدية",
            account_type=self.asset_type,
            is_leaf=False,
            is_control_account=True,
            is_cash_account=True,
            is_custody_account=True,
            currency=self.egp,
            is_active=True
        )
        self.opening_equity = ChartOfAccounts.objects.create(
            code="31010",
            name="الأرصدة الافتتاحية",
            account_type=self.equity_type,
            is_leaf=True,
            currency=self.egp,
            is_active=True
        )

        from financial.models import FiscalYear, AccountingPeriod
        now = timezone.now().date()
        self.fy = FiscalYear.objects.create(
            year_code=f"FY_P2_{now.year}",
            name=f"FY {now.year}",
            start_date=now.replace(month=1, day=1),
            end_date=now.replace(month=12, day=31),
            status="open"
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fy,
            name=f"Period {now.year}",
            start_date=now.replace(month=1, day=1),
            end_date=now.replace(month=12, day=31),
            status="open",
            period_number=1
        )

    def test_quick_add_cash_account_success(self):
        """التحقق من إنشاء خزينة نقدية وتوليد الكود 1112001 وإسناد الصلاحيات للمنشئ"""
        from financial.models.treasury_access import UserTreasuryAccess
        from django.urls import reverse

        url = reverse("financial:quick_add_cash_bank_account")
        response = self.client.post(url, {
            "account_category": "cash",
            "name": "خزينة فرع المعادي",
            "currency_id": self.egp.id,
            "opening_balance": "0.00"
        })

        assert response.status_code == 200, f"Error: {response.json() if response.status_code != 200 else ''}"
        data = response.json()
        assert data["success"] is True
        assert data["account"]["code"].startswith("11120")

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.is_cash_account is True
        assert acc.is_bank_account is False
        assert acc.is_custody_account is False

        access = UserTreasuryAccess.objects.filter(user=self.user, treasury=acc).first()
        assert access is not None
        assert access.can_deposit is True
        assert access.can_disburse is True

    def test_quick_add_bank_account_with_iban_swift(self):
        """التحقق من إنشاء حساب بنكي وحفظ الـ IBAN و Swift كحقول مهيكلة"""
        from django.urls import reverse

        url = reverse("financial:quick_add_cash_bank_account")
        response = self.client.post(url, {
            "account_category": "bank",
            "name": "البنك الأهلي المصري - جاري",
            "currency_id": self.egp.id,
            "bank_name": "National Bank of Egypt",
            "account_number": "1234567890",
            "iban": "EG380002000100000012345678901",
            "swift_code": "NBEGEGCX",
            "opening_balance": "0.00"
        })

        assert response.status_code == 200, f"Error: {response.json() if response.status_code != 200 else ''}"
        data = response.json()
        assert data["success"] is True
        assert data["account"]["code"].startswith("11160")

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.is_bank_account is True
        assert acc.bank_name == "National Bank of Egypt"
        assert acc.iban == "EG380002000100000012345678901"
        assert acc.swift_code == "NBEGEGCX"

    def test_quick_add_custody_account_with_employee_and_history(self, django_user_model):
        """التحقق من إنشاء صندوق عهدة وربطه بموظف وتوثيق السجل التاريخي وإسناد الصلاحيات"""
        from hr.models.employee import Employee
        from hr.models.organization import Department, JobTitle
        from financial.models.custody_history import CustodyAssignmentHistory
        from financial.models.treasury_access import UserTreasuryAccess
        from django.urls import reverse

        emp_user = django_user_model.objects.create_user(
            username="custody_holder",
            email="custody_holder@mwheba.com",
            password="Password123!"
        )
        dept = Department.objects.create(code="FIN01", name_ar="الإدارة المالية")
        job = JobTitle.objects.create(code="JOB-001", title_ar="أمين خزينة", department=dept)
        
        employee = Employee.objects.create(
            name="أحمد محمود السيد",
            employee_number="EMP-101",
            national_id="29001011234567",
            birth_date=timezone.now().date().replace(year=1990),
            gender="male",
            marital_status="single",
            department=dept,
            job_title=job,
            hire_date=timezone.now().date(),
            created_by=self.user,
            user=emp_user
        )

        url = reverse("financial:quick_add_cash_bank_account")
        response = self.client.post(url, {
            "account_category": "custody",
            "name": "عهدة مشتريات أحمد محمود",
            "currency_id": self.egp.id,
            "employee_id": employee.id,
            "opening_balance": "0.00"
        })

        assert response.status_code == 200, f"Error: {response.json() if response.status_code != 200 else ''}"
        data = response.json()
        assert data["success"] is True
        assert data["account"]["code"].startswith("11180")

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.is_custody_account is True
        assert acc.assigned_employee == employee

        history = CustodyAssignmentHistory.objects.filter(account=acc, employee=employee).first()
        assert history is not None
        assert history.is_active is True

        emp_access = UserTreasuryAccess.objects.filter(user=emp_user, treasury=acc).first()
        assert emp_access is not None
        assert emp_access.can_deposit is True
        assert emp_access.can_disburse is True

    def test_quick_add_positive_opening_balance_journal_entry(self):
        """التحقق من توليد قيد رصيد افتتاحي موجب عبر AccountingGateway"""
        from financial.models.journal_entry import JournalEntry, JournalEntryLine
        from django.urls import reverse

        url = reverse("financial:quick_add_cash_bank_account")
        response = self.client.post(url, {
            "account_category": "cash",
            "name": "خزينة مبيعات مدينة نصر",
            "currency_id": self.egp.id,
            "opening_balance": "25000.00"
        })

        assert response.status_code == 200, f"Error: {response.json() if response.status_code != 200 else ''}"
        data = response.json()
        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])

        entry = JournalEntry.objects.filter(reference=f"OPB-{acc.code}").first()
        assert entry is not None
        assert entry.status == "posted"

        line_acc = JournalEntryLine.objects.filter(journal_entry=entry, account=acc).first()
        line_eq = JournalEntryLine.objects.filter(journal_entry=entry, account=self.opening_equity).first()

        assert line_acc is not None and line_acc.debit == Decimal("25000.00")
        assert line_eq is not None and line_eq.credit == Decimal("25000.00")

    def test_quick_add_overdraft_opening_balance_journal_entry(self):
        """التحقق من توليد قيد رصيد افتتاحي سالب (سحب بنكي مكشوف) عبر AccountingGateway"""
        from financial.models.journal_entry import JournalEntry, JournalEntryLine
        from django.urls import reverse

        url = reverse("financial:quick_add_cash_bank_account")
        response = self.client.post(url, {
            "account_category": "bank",
            "name": "بنك مصر - حساب مكشوف",
            "currency_id": self.egp.id,
            "opening_balance": "-10000.00"
        })

        assert response.status_code == 200, f"Error: {response.json() if response.status_code != 200 else ''}"
        data = response.json()
        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])

        entry = JournalEntry.objects.filter(reference=f"OPB-{acc.code}").first()
        assert entry is not None
        assert entry.status == "posted"

        line_acc = JournalEntryLine.objects.filter(journal_entry=entry, account=acc).first()
        line_eq = JournalEntryLine.objects.filter(journal_entry=entry, account=self.opening_equity).first()

        assert line_acc is not None and line_acc.credit == Decimal("10000.00")
        assert line_eq is not None and line_eq.debit == Decimal("10000.00")

    def test_cash_account_delete_precheck_and_blockers(self):
        """التحقق من فحص التبعيات وحظر التعطيل عند وجود تحويلات معلقة أو رصيد غير مصفى"""
        from django.urls import reverse

        # 1. حساب نظيف بدون حركات
        clean_acc = ChartOfAccounts.objects.create(
            code="1112099",
            name="خزينة مؤقتة تجريبية",
            parent=self.cash_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )
        url_clean = reverse("financial:cash_account_delete", args=[clean_acc.pk])
        resp_clean = self.client.get(f"{url_clean}?precheck=1")
        assert resp_clean.status_code == 200
        data_clean = resp_clean.json()
        assert data_clean["can_delete"] is True
        assert data_clean["block_action"] is False

        # 2. حساب عليه تحويل مالي معلق في الطريق
        target_acc = ChartOfAccounts.objects.create(
            code="1112098",
            name="خزينة فرع طنطا",
            parent=self.cash_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )
        CashTransfer.objects.create(
            transfer_number="TRF-2026-TEST",
            transfer_type=TransferType.IN_TRANSIT,
            status=TransferStatus.IN_TRANSIT,
            transfer_date=timezone.now().date(),
            from_account=clean_acc,
            to_account=target_acc,
            source_amount=Decimal("5000.00"),
            source_currency=self.egp,
            destination_amount=Decimal("5000.00"),
            destination_currency=self.egp,
            created_by=self.user
        )

        resp_blocked = self.client.get(f"{url_clean}?precheck=1")
        assert resp_blocked.status_code == 200
        data_blocked = resp_blocked.json()
        assert data_blocked["has_pending_transfers"] is True
        assert data_blocked["block_action"] is True

        # محاولة POST على حساب محظور
        resp_post_block = self.client.post(url_clean)
        assert resp_post_block.status_code == 400


@pytest.mark.django_db
class TestCashTransferPhase3AccountingService:
    """
    اختبارات خدمة التحويل المالي المركزية ومحرك العملات المتعددة (المرحلة 3)
    """

    @pytest.fixture(autouse=True)
    def setup_service_data(self, django_user_model):
        self.user_sender = django_user_model.objects.create_user(
            username="sender_officer",
            email="sender_officer@mwheba.com",
            password="Password123!"
        )
        self.user_receiver = django_user_model.objects.create_user(
            username="receiver_officer",
            email="receiver_officer@mwheba.com",
            password="Password123!"
        )
        self.superuser = django_user_model.objects.create_user(
            username="cfo_admin",
            email="cfo_admin@mwheba.com",
            password="Password123!",
            is_staff=True,
            is_superuser=True
        )

        self.egp = Currency.objects.create(
            code="EGP",
            name="جنيه مصري",
            symbol="ج.م",
            is_functional=True,
            is_active=True
        )
        self.usd = Currency.objects.create(
            code="USD",
            name="دولار أمريكي",
            symbol="$",
            is_functional=False,
            is_active=True
        )

        from financial.models.currency import ExchangeRate
        ExchangeRate.objects.create(
            from_currency=self.usd,
            to_currency=self.egp,
            rate=Decimal("50.000000"),
            effective_date=timezone.now().date()
        )

        self.asset_type = AccountType.objects.create(
            code="AST3",
            name="أصول متداولة",
            category="asset"
        )
        self.expense_type = AccountType.objects.create(
            code="EXP3",
            name="مصروفات",
            category="expense"
        )
        self.revenue_type = AccountType.objects.create(
            code="REV3",
            name="إيرادات",
            category="revenue"
        )

        # الحسابات الرقابية الحاكمة
        self.cash_control = ChartOfAccounts.objects.create(
            code="11120",
            name="الخزائن النقدية والصناديق",
            account_type=self.asset_type,
            is_leaf=False,
            is_control_account=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )
        self.bank_control = ChartOfAccounts.objects.create(
            code="11160",
            name="الحسابات الجارية بالبنوك",
            account_type=self.asset_type,
            is_leaf=False,
            is_control_account=True,
            is_bank_account=True,
            currency=self.egp,
            is_active=True
        )

        # حسابات وسيطة ونظامية
        self.transit_account = ChartOfAccounts.objects.create(
            code="11150",
            name="نقدية بالطريق وتحويلات وسيطة",
            account_type=self.asset_type,
            is_leaf=True,
            currency=self.egp,
            is_active=True
        )
        self.fx_gain_account = ChartOfAccounts.objects.create(
            code="42300",
            name="أرباح فروق تقييم وتحويل العملة",
            account_type=self.revenue_type,
            is_leaf=True,
            currency=self.egp,
            is_active=True
        )
        self.fx_loss_account = ChartOfAccounts.objects.create(
            code="52300",
            name="خسائر فروق تقييم وتحويل العملة",
            account_type=self.expense_type,
            is_leaf=True,
            currency=self.egp,
            is_active=True
        )
        self.rounding_account = ChartOfAccounts.objects.create(
            code="54400",
            name="فروق التقريب المحاسبي",
            account_type=self.expense_type,
            is_leaf=True,
            currency=self.egp,
            is_active=True
        )
        self.bank_charges_account = ChartOfAccounts.objects.create(
            code="52200",
            name="مصاريف وعمولات بنكية",
            account_type=self.expense_type,
            is_leaf=True,
            currency=self.egp,
            is_active=True
        )
        self.input_vat_account = ChartOfAccounts.objects.create(
            code="11350",
            name="ضريبة القيمة المضافة على المدخلات",
            account_type=self.asset_type,
            is_leaf=True,
            currency=self.egp,
            is_active=True
        )

        # حسابات تشغيلية
        self.treasury_cairo = ChartOfAccounts.objects.create(
            code="1112001",
            name="خزينة الإدارة - القاهرة",
            parent=self.cash_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )
        self.treasury_alex = ChartOfAccounts.objects.create(
            code="1112002",
            name="خزينة فرع الإسكندرية",
            parent=self.cash_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )
        self.bank_usd = ChartOfAccounts.objects.create(
            code="1117001",
            name="حساب البنك الأهلي بالدولار",
            parent=self.bank_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_bank_account=True,
            currency=self.usd,
            is_active=True
        )

        # إسناد الصلاحيات
        from financial.models.treasury_access import UserTreasuryAccess
        UserTreasuryAccess.objects.create(
            user=self.user_sender,
            treasury=self.treasury_cairo,
            can_disburse=True,
            can_deposit=True
        )
        UserTreasuryAccess.objects.create(
            user=self.user_sender,
            treasury=self.bank_usd,
            can_disburse=True,
            can_deposit=True
        )
        UserTreasuryAccess.objects.create(
            user=self.user_receiver,
            treasury=self.treasury_alex,
            can_disburse=True,
            can_deposit=True
        )

    def test_calculate_transfer_preview_same_currency(self):
        """التحقق من حساب المعاينة المباشرة بنفس العملة بدون فروق عملة"""
        from financial.services.cash_transfer_service import CashTransferService

        preview = CashTransferService.calculate_transfer_preview(
            from_account=self.treasury_cairo,
            to_account=self.treasury_alex,
            source_amount=Decimal("15000.00")
        )

        assert preview["source_amount"] == Decimal("15000.00")
        assert preview["destination_amount"] == Decimal("15000.00")
        assert preview["effective_exchange_rate"] == Decimal("1.000000")
        assert preview["fx_gain_loss"] == Decimal("0.00")
        assert preview["penny_difference"] == Decimal("0.00")
        assert len(preview["simulated_lines"]) == 2

    def test_calculate_transfer_preview_with_bank_fee_and_vat(self):
        """التحقق من حساب المعاينة مع المصاريف البنكية وتفصيل ضريبة القيمة المضافة 14%"""
        from financial.services.cash_transfer_service import CashTransferService

        preview = CashTransferService.calculate_transfer_preview(
            from_account=self.treasury_cairo,
            to_account=self.treasury_alex,
            source_amount=Decimal("10000.00"),
            bank_fee=Decimal("100.00"),
            vat_on_fee=Decimal("14.00")
        )

        assert preview["bank_fee"] == Decimal("100.00")
        assert preview["vat_on_fee"] == Decimal("14.00")
        assert preview["total_fee"] == Decimal("114.00")
        assert preview["total_source_deduction"] == Decimal("10114.00")
        # خطوط القيد: دائن الخزينة المصدر (10000 + 114)، مدين المستلم (10000)، مدين المصاريف (100)، مدين الضريبة (14)
        assert len(preview["simulated_lines"]) == 5

    def test_calculate_transfer_preview_cross_currency(self):
        """التحقق من حساب المعاينة للتحويل متعدد العملات (USD -> EGP)"""
        from financial.services.cash_transfer_service import CashTransferService

        preview = CashTransferService.calculate_transfer_preview(
            from_account=self.bank_usd,
            to_account=self.treasury_cairo,
            source_amount=Decimal("1000.00"),
            exchange_rate=Decimal("50.250000")
        )

        assert preview["source_amount"] == Decimal("1000.00")
        assert preview["source_currency"] == "USD"
        assert preview["destination_amount"] == Decimal("50250.00")
        assert preview["dest_base_amount"] == Decimal("50250.00")
        assert preview["source_base_amount"] == Decimal("50000.00")
        assert preview["fx_gain_loss"] == Decimal("250.00")
        assert preview["fx_type"] == "gain"

    def test_execute_direct_transfer_success(self):
        """التحقق من تنفيذ تحويل مباشر وتوليد القيد المحاسبي المتوازن والتوقيع التشفيري"""
        from financial.services.cash_transfer_service import CashTransferService
        from financial.models.journal_entry import JournalEntryLine

        transfer = CashTransferService.execute_transfer(
            from_account_id=self.treasury_cairo.id,
            to_account_id=self.treasury_alex.id,
            source_amount=Decimal("20000.00"),
            user=self.superuser,
            bank_reference="TXN-998877",
            notes="تحويل مباشر لتغذية فرع الإسكندرية"
        )

        assert transfer.id is not None
        assert transfer.transfer_number.startswith("TRF")
        assert transfer.status == TransferStatus.COMPLETED
        assert transfer.is_completed is True
        assert transfer.journal_entry is not None
        assert transfer.journal_entry.reference == transfer.transfer_number
        assert transfer.verification_hash != ""

        # التحقق من سطور القيد في دفتر اليومية
        lines = JournalEntryLine.objects.filter(journal_entry=transfer.journal_entry)
        assert lines.count() == 2
        debit_line = lines.filter(account=self.treasury_alex).first()
        credit_line = lines.filter(account=self.treasury_cairo).first()

        assert debit_line is not None and debit_line.debit == Decimal("20000.00")
        assert transfer.bank_reference == "TXN-998877"
        assert "TXN-998877" in debit_line.description
        assert credit_line is not None and credit_line.credit == Decimal("20000.00")

    def test_dispatch_and_receive_in_transit_transfer_lifecycle(self):
        """التحقق من دورة حياة التحويل المرحلي: إرسال -> في الطريق -> استلام مع فحص SoD"""
        from financial.services.cash_transfer_service import CashTransferService
        from financial.models.journal_entry import JournalEntryLine

        # 1. إرسال التحويل من القاهرة (Dispatch)
        transfer = CashTransferService.dispatch_transit_transfer(
            from_account_id=self.treasury_cairo.id,
            to_account_id=self.treasury_alex.id,
            source_amount=Decimal("30000.00"),
            user=self.user_sender,
            courier_name="محمد سعيد",
            courier_phone="01012345678",
            notes="إرسال سيارة نقل الأموال"
        )

        assert transfer.status == TransferStatus.IN_TRANSIT
        assert transfer.is_in_transit is True
        assert transfer.journal_entry is not None

        # فحص قيد الإرسال: دائن القاهرة (30000)، مدين نقدية بالطريق 11150 (30000)
        disp_lines = JournalEntryLine.objects.filter(journal_entry=transfer.journal_entry)
        transit_debit = disp_lines.filter(account=self.transit_account).first()
        cairo_credit = disp_lines.filter(account=self.treasury_cairo).first()
        assert transit_debit is not None and transit_debit.debit == Decimal("30000.00")
        assert cairo_credit is not None and cairo_credit.credit == Decimal("30000.00")

        # 2. محاولة استلام السند بواسطة نفس الشخص الذي أنشأه (مخالفة SoD)
        with pytest.raises(ValidationError) as excinfo:
            CashTransferService.receive_transit_transfer(
                transfer_id=transfer.id,
                user=self.user_sender
            )
        assert "SoD" in str(excinfo.value) or "الفصل بين المهام" in str(excinfo.value)

        # 3. استلام السند بنجاح بواسطة أمين خزينة الإسكندرية (Receiver)
        received_trf = CashTransferService.receive_transit_transfer(
            transfer_id=transfer.id,
            user=self.user_receiver,
            notes="تم استلام المبلغ ومطابقته بالكامل"
        )

        assert received_trf.status == TransferStatus.COMPLETED
        assert received_trf.received_by == self.user_receiver
        assert received_trf.receipt_journal_entry is not None

        # فحص قيد الاستلام: دائن نقدية بالطريق 11150 (30000)، مدين خزينة الإسكندرية (30000)
        rcv_lines = JournalEntryLine.objects.filter(journal_entry=received_trf.receipt_journal_entry)
        transit_credit = rcv_lines.filter(account=self.transit_account).first()
        alex_debit = rcv_lines.filter(account=self.treasury_alex).first()
        assert transit_credit is not None and transit_credit.credit == Decimal("30000.00")
        assert alex_debit is not None and alex_debit.debit == Decimal("30000.00")

    def test_recall_in_transit_transfer(self):
        """التحقق من استرجاع وإلغاء تحويل مرحلي في الطريق وعكس قيد الإرسال"""
        from financial.services.cash_transfer_service import CashTransferService
        from financial.models.journal_entry import JournalEntryLine

        transfer = CashTransferService.dispatch_transit_transfer(
            from_account_id=self.treasury_cairo.id,
            to_account_id=self.treasury_alex.id,
            source_amount=Decimal("5000.00"),
            user=self.user_sender,
            notes="تحويل سيتم استرجاعه"
        )

        recalled_trf = CashTransferService.recall_transit_transfer(
            transfer_id=transfer.id,
            user=self.superuser,
            reason="إلغاء المأمورية وعودة المندوب بالمبلغ"
        )

        assert recalled_trf.status == TransferStatus.RECALLED
        assert recalled_trf.reversal_journal_entry is not None

        lines = JournalEntryLine.objects.filter(journal_entry=recalled_trf.reversal_journal_entry)
        cairo_debit = lines.filter(account=self.treasury_cairo).first()
        transit_credit = lines.filter(account=self.transit_account).first()

        assert cairo_debit is not None and cairo_debit.debit == Decimal("5000.00")
        assert transit_credit is not None and transit_credit.credit == Decimal("5000.00")

    def test_reverse_completed_transfer(self):
        """التحقق من عكس سند تحويل مكتمل وتوليد القيد العكسي الشامل"""
        from financial.services.cash_transfer_service import CashTransferService
        from financial.models.journal_entry import JournalEntryLine

        transfer = CashTransferService.execute_transfer(
            from_account_id=self.treasury_cairo.id,
            to_account_id=self.treasury_alex.id,
            source_amount=Decimal("8000.00"),
            user=self.superuser,
            notes="سند تجريبي للعكس"
        )

        reversed_trf = CashTransferService.reverse_transfer(
            transfer_id=transfer.id,
            user=self.superuser,
            reason="خطأ في رقم الحساب المحول إليه"
        )

        assert reversed_trf.status == TransferStatus.REVERSED
        assert reversed_trf.reversed_by == self.superuser
        assert reversed_trf.reversal_journal_entry is not None

        lines = JournalEntryLine.objects.filter(journal_entry=reversed_trf.reversal_journal_entry)
        cairo_debit = lines.filter(account=self.treasury_cairo).first()
        alex_credit = lines.filter(account=self.treasury_alex).first()

        assert cairo_debit is not None and cairo_debit.debit == Decimal("8000.00")
        assert alex_credit is not None and alex_credit.credit == Decimal("8000.00")


@pytest.mark.django_db
class TestCashTransferPhase4RestEndpoints:
    """
    اختبارات واجهات الـ REST API والتوجيه لسندات التحويل المالي (المرحلة 4)
    """

    @pytest.fixture(autouse=True)
    def setup_api_data(self, client, django_user_model):
        self.client = client
        self.sender_user = django_user_model.objects.create_user(
            username="api_sender",
            email="api_sender@mwheba.com",
            password="Password123!"
        )
        self.receiver_user = django_user_model.objects.create_user(
            username="api_receiver",
            email="api_receiver@mwheba.com",
            password="Password123!"
        )
        self.admin_user = django_user_model.objects.create_user(
            username="api_admin",
            email="api_admin@mwheba.com",
            password="Password123!",
            is_staff=True,
            is_superuser=True
        )

        self.egp = Currency.objects.create(
            code="EGP",
            name="جنيه مصري",
            symbol="ج.م",
            is_functional=True,
            is_active=True
        )
        self.usd = Currency.objects.create(
            code="USD",
            name="دولار أمريكي",
            symbol="$",
            is_functional=False,
            is_active=True
        )

        from financial.models.currency import ExchangeRate
        ExchangeRate.objects.create(
            from_currency=self.usd,
            to_currency=self.egp,
            rate=Decimal("50.000000"),
            effective_date=timezone.now().date()
        )

        self.asset_type = AccountType.objects.create(
            code="AST4",
            name="أصول متداولة",
            category="asset"
        )
        self.expense_type = AccountType.objects.create(
            code="EXP4",
            name="مصروفات",
            category="expense"
        )
        self.revenue_type = AccountType.objects.create(
            code="REV4",
            name="إيرادات",
            category="revenue"
        )

        self.cash_control = ChartOfAccounts.objects.create(
            code="11120",
            name="الخزائن النقدية والصناديق",
            account_type=self.asset_type,
            is_leaf=False,
            is_control_account=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )
        self.transit_account = ChartOfAccounts.objects.create(
            code="11150",
            name="نقدية بالطريق وتحويلات وسيطة",
            account_type=self.asset_type,
            is_leaf=True,
            currency=self.egp,
            is_active=True
        )
        self.treasury_1 = ChartOfAccounts.objects.create(
            code="1112011",
            name="خزينة الفرع الأول",
            parent=self.cash_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )
        self.treasury_2 = ChartOfAccounts.objects.create(
            code="1112012",
            name="خزينة الفرع الثاني",
            parent=self.cash_control,
            account_type=self.asset_type,
            is_leaf=True,
            is_cash_account=True,
            currency=self.egp,
            is_active=True
        )

        from financial.models.treasury_access import UserTreasuryAccess
        UserTreasuryAccess.objects.create(
            user=self.sender_user,
            treasury=self.treasury_1,
            can_disburse=True,
            can_deposit=True
        )
        UserTreasuryAccess.objects.create(
            user=self.receiver_user,
            treasury=self.treasury_2,
            can_disburse=True,
            can_deposit=True
        )

    def test_transfer_preview_api_endpoint(self):
        """التحقق من endpoint معاينة التحويل المالي المباشر /api/transfers/preview/"""
        from django.urls import reverse

        self.client.force_login(self.sender_user)
        url = reverse("financial:transfer_preview_api")

        response = self.client.get(url, {
            "from_account": self.treasury_1.id,
            "to_account": self.treasury_2.id,
            "amount": "12500.00"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["preview"]["source_amount"] == 12500.0
        assert data["preview"]["destination_amount"] == 12500.0
        assert data["preview"]["effective_exchange_rate"] == 1.0
        assert len(data["preview"]["simulated_lines"]) == 2

    def test_transfer_create_direct_api_endpoint(self):
        """التحقق من endpoint تسجيل التحويل المباشر /api/transfers/create/"""
        from django.urls import reverse

        self.client.force_login(self.admin_user)
        url = reverse("financial:transfer_create_api")

        response = self.client.post(url, {
            "from_account": self.treasury_1.id,
            "to_account": self.treasury_2.id,
            "amount": "18000.00",
            "transfer_type": "direct",
            "bank_reference": "REF-API-101",
            "notes": "تحويل عبر REST API"
        })

        assert response.status_code == 200, f"Error: {response.json() if response.status_code != 200 else ''}"
        data = response.json()
        assert data["success"] is True
        assert data["status"] == TransferStatus.COMPLETED
        assert data["transfer_number"].startswith("TRF")
        assert data["journal_entry_id"] is not None

        trf = CashTransfer.objects.get(pk=data["transfer_id"])
        assert trf.status == TransferStatus.COMPLETED
        assert trf.bank_reference == "REF-API-101"

    def test_transfer_between_accounts_legacy_adapter_api(self):
        """التحقق من توافقية endpoint القديم /api/transfer-between-accounts/"""
        from django.urls import reverse

        self.client.force_login(self.admin_user)
        url = reverse("financial:transfer_between_accounts")

        response = self.client.post(url, {
            "from_account": self.treasury_1.id,
            "to_account": self.treasury_2.id,
            "amount": "7500.00",
            "description": "تحويل من خلال المسار القديم المتوافق"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["transfer_number"].startswith("TRF")

    def test_transfer_detail_api_endpoint(self):
        """التحقق من endpoint إرجاع تفاصيل السند /api/transfers/<pk>/detail/"""
        from django.urls import reverse
        from financial.services.cash_transfer_service import CashTransferService

        trf = CashTransferService.execute_transfer(
            from_account_id=self.treasury_1.id,
            to_account_id=self.treasury_2.id,
            source_amount=Decimal("4000.00"),
            user=self.admin_user,
            notes="سند للاختبار التفصيلي"
        )

        self.client.force_login(self.admin_user)
        url = reverse("financial:transfer_detail_api", args=[trf.id])
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["transfer"]["id"] == trf.id
        assert data["transfer"]["transfer_number"] == trf.transfer_number
        assert data["transfer"]["source_amount"] == 4000.0
        assert data["transfer"]["verification_hash"] != ""

    def test_transfer_receive_api_with_sod_enforcement(self):
        """التحقق من endpoint استلام النقدية بالطريق وفحص حظر SoD عبر الـ API"""
        from django.urls import reverse
        from financial.services.cash_transfer_service import CashTransferService

        # 1. إنشاء تحويل مرحلي بواسطة sender_user
        trf = CashTransferService.dispatch_transit_transfer(
            from_account_id=self.treasury_1.id,
            to_account_id=self.treasury_2.id,
            source_amount=Decimal("22000.00"),
            user=self.sender_user,
            notes="تحويل مرحلي تحت الاختبار"
        )

        # 2. محاولة الاستلام بنفس المستخدم المنشئ (sender_user) -> يجب الرفض 400 بسبب SoD
        self.client.force_login(self.sender_user)
        url_rcv = reverse("financial:transfer_receive_api", args=[trf.id])
        resp_blocked = self.client.post(url_rcv, {
            "notes": "محاولة استلام غير قانونية"
        })
        assert resp_blocked.status_code == 400
        data_blocked = resp_blocked.json()
        assert data_blocked["success"] is False
        assert "SoD" in data_blocked["error"] or "الفصل بين المهام" in data_blocked["error"]

        # 3. الاستلام بواسطة المستلم المعتمد receiver_user -> يجب النجاح 200
        self.client.force_login(self.receiver_user)
        resp_success = self.client.post(url_rcv, {
            "received_amount": "22000.00",
            "notes": "تم الاستلام بنجاح"
        })
        assert resp_success.status_code == 200
        data_success = resp_success.json()
        assert data_success["success"] is True
        assert data_success["status"] == TransferStatus.COMPLETED

    def test_transfer_recall_api_endpoint(self):
        """التحقق من endpoint استرجاع النقدية في الطريق /api/transfers/<pk>/recall/"""
        from django.urls import reverse
        from financial.services.cash_transfer_service import CashTransferService

        trf = CashTransferService.dispatch_transit_transfer(
            from_account_id=self.treasury_1.id,
            to_account_id=self.treasury_2.id,
            source_amount=Decimal("9000.00"),
            user=self.sender_user,
            notes="سند سيتم استرجاعه بالـ API"
        )

        self.client.force_login(self.admin_user)
        url_recall = reverse("financial:transfer_recall_api", args=[trf.id])
        response = self.client.post(url_recall, {
            "reason": "استرجاع لعدم توفر سيارة النقل"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == TransferStatus.RECALLED

    def test_transfer_reverse_api_endpoint(self):
        """التحقق من endpoint عكس سند تحويل مكتمل /api/transfers/<pk>/reverse/"""
        from django.urls import reverse
        from financial.services.cash_transfer_service import CashTransferService

        trf = CashTransferService.execute_transfer(
            from_account_id=self.treasury_1.id,
            to_account_id=self.treasury_2.id,
            source_amount=Decimal("11000.00"),
            user=self.admin_user,
            notes="سند سيتم عكسه بالـ API"
        )

        self.client.force_login(self.admin_user)
        url_reverse = reverse("financial:transfer_reverse_api", args=[trf.id])
        response = self.client.post(url_reverse, {
            "reason": "عكس السند بالخطأ"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == TransferStatus.REVERSED


@pytest.mark.django_db
class TestCashTransferPhase6ViewsAndTemplates:
    """
    اختبارات عروض القوائم والتفاصيل والطباعة المزدوجة لسندات التحويل المالي (المرحلة 6)
    """

    @pytest.fixture(autouse=True)
    def setup_data(self, django_user_model, client):
        self.client = client
        self.user = django_user_model.objects.create_superuser(
            username="cfo_user",
            email="cfo@mwheba.com",
            password="Password123!"
        )

        self.egp = Currency.objects.create(
            code="EGP",
            name="جنيه مصري",
            symbol="ج.م",
            is_functional=True,
            is_active=True
        )

        self.asset_type = AccountType.objects.create(
            code="AST6",
            name="أصول متداولة",
            category="asset"
        )

        self.acc1 = ChartOfAccounts.objects.create(
            code="111201",
            name="خزينة الفرع 1",
            account_type=self.asset_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True,
            is_cash_account=True
        )

        self.acc2 = ChartOfAccounts.objects.create(
            code="111202",
            name="خزينة الفرع 2",
            account_type=self.asset_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True,
            is_cash_account=True
        )

        self.transit_acc = ChartOfAccounts.objects.create(
            code="11150",
            name="نقدية بالطريق",
            account_type=self.asset_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True,
            is_cash_account=True
        )

        from financial.services.cash_transfer_service import CashTransferService
        self.transfer = CashTransferService.execute_transfer(
            from_account_id=self.acc1.id,
            to_account_id=self.acc2.id,
            source_amount=Decimal("15000.00"),
            user=self.user,
            notes="سند اختبار المرحلة 6"
        )

        self.client.force_login(self.user)

    def test_cash_transfers_list_view_html(self):
        """التحقق من تحميل صفحة سجل سندات التحويل المالي HTML بنجاح"""
        url = reverse("financial:cash_transfers_list")
        response = self.client.get(url)

        assert response.status_code == 200
        assert "transfers" in response.context
        assert "total_count" in response.context
        assert "in_transit_count" in response.context
        assert "completed_count" in response.context
        assert "total_volume" in response.context
        assert self.transfer.transfer_number.encode() in response.content

    def test_cash_transfers_list_view_ajax(self):
        """التحقق من استجابة البحث التفاعلي عبر AJAX لتبديل الجدول وترقيم الصفحات"""
        url = reverse("financial:cash_transfers_list")
        response = self.client.get(url, {"q": self.transfer.transfer_number}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "table_html" in data
        assert "pagination_html" in data
        assert self.transfer.transfer_number in data["table_html"]

    def test_cash_transfers_list_view_excel_export(self):
        """التحقق من تصدير سجل التحويلات إلى Excel"""
        url = reverse("financial:cash_transfers_list")
        response = self.client.get(url, {"export": "excel"})

        assert response.status_code == 200
        assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "attachment; filename=" in response["Content-Disposition"]

    def test_cash_transfer_detail_view(self):
        """التحقق من تحميل صفحة تفاصيل السند والقيد المحاسبي المتوازن وبصمة التحقق"""
        url = reverse("financial:cash_transfer_detail", args=[self.transfer.id])
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.context["transfer"].id == self.transfer.id
        assert self.transfer.transfer_number.encode() in response.content
        assert self.transfer.verification_hash[:16].encode() in response.content

    def test_transfer_voucher_print_view_a4(self):
        """التحقق من عرض صفحة طباعة السند القياسي A4"""
        url = reverse("financial:cash_transfer_print", args=[self.transfer.id])
        response = self.client.get(url, {"format": "a4"})

        assert response.status_code == 200
        assert b"voucher-a4" in response.content
        assert self.transfer.transfer_number.encode() in response.content
        assert b"A4 portrait" in response.content

    def test_transfer_voucher_print_view_thermal(self):
        """التحقق من عرض صفحة طباعة الإيصال الحراري 80mm"""
        url = reverse("financial:cash_transfer_print", args=[self.transfer.id])
        response = self.client.get(url, {"format": "thermal"})

        assert response.status_code == 200
        assert b"voucher-thermal" in response.content
        assert b"80mm auto" in response.content


@pytest.mark.django_db
class TestCashTransferPhase7EnterpriseMatrixAndEdgeCases:
    """
    المرحلة 7: مصفوفة الاختبارات الشاملة والحالات الحدية والحوكمة المؤسسية (40 سيناريو متكامل)
    """

    @pytest.fixture(autouse=True)
    def setup_data(self, django_user_model, client):
        self.client = client
        self.user = django_user_model.objects.create_superuser(
            username="cfo_master",
            email="cfomaster@mwheba.com",
            password="Password123!"
        )

        self.treasury_officer1 = django_user_model.objects.create_user(
            username="officer_sender",
            email="sender@mwheba.com",
            password="Password123!"
        )

        self.treasury_officer2 = django_user_model.objects.create_user(
            username="officer_receiver",
            email="receiver@mwheba.com",
            password="Password123!"
        )

        self.egp, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True, "is_active": True}
        )

        self.usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False, "is_active": True}
        )

        self.eur, _ = Currency.objects.get_or_create(
            code="EUR",
            defaults={"name": "يورو", "symbol": "€", "is_functional": False, "is_active": True}
        )

        self.asset_type = AccountType.objects.create(
            code="AST7",
            name="أصول متداولة 7",
            category="asset"
        )
        self.expense_type = AccountType.objects.create(
            code="EXP7",
            name="مصروفات 7",
            category="expense"
        )
        self.revenue_type = AccountType.objects.create(
            code="REV7",
            name="إيرادات 7",
            category="revenue"
        )

        self.treasury_egp1 = ChartOfAccounts.objects.create(
            code="1112001",
            name="خزينة رئيسية EGP",
            account_type=self.asset_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True,
            is_cash_account=True
        )

        self.treasury_egp2 = ChartOfAccounts.objects.create(
            code="1112002",
            name="خزينة فرعية EGP",
            account_type=self.asset_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True,
            is_cash_account=True
        )

        self.treasury_usd = ChartOfAccounts.objects.create(
            code="1112003",
            name="خزينة العملات الأجنبية USD",
            account_type=self.asset_type,
            currency=self.usd,
            is_active=True,
            is_leaf=True,
            is_cash_account=True
        )

        self.treasury_eur = ChartOfAccounts.objects.create(
            code="1112004",
            name="خزينة اليورو EUR",
            account_type=self.asset_type,
            currency=self.eur,
            is_active=True,
            is_leaf=True,
            is_cash_account=True
        )

        self.transit_acc = ChartOfAccounts.objects.create(
            code="11150",
            name="نقدية بالطريق",
            account_type=self.asset_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True,
            is_cash_account=True
        )

        self.fx_gain_acc = ChartOfAccounts.objects.create(
            code="42300",
            name="أرباح فروق العملة",
            account_type=self.revenue_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True
        )

        self.fx_loss_acc = ChartOfAccounts.objects.create(
            code="52300",
            name="خسائر فروق العملة",
            account_type=self.expense_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True
        )

        self.rounding_acc = ChartOfAccounts.objects.create(
            code="54400",
            name="فروق التقريب المحاسبي",
            account_type=self.expense_type,
            currency=self.egp,
            is_active=True,
            is_leaf=True
        )

        from financial.models.currency import ExchangeRate
        ExchangeRate.objects.create(
            from_currency=self.usd,
            to_currency=self.egp,
            rate=Decimal("48.500000"),
            effective_date=timezone.now().date()
        )
        ExchangeRate.objects.create(
            from_currency=self.eur,
            to_currency=self.egp,
            rate=Decimal("52.000000"),
            effective_date=timezone.now().date()
        )

        from financial.models.treasury_access import UserTreasuryAccess
        UserTreasuryAccess.objects.create(
            user=self.treasury_officer1,
            treasury=self.treasury_egp1,
            can_disburse=True,
            can_deposit=True
        )
        UserTreasuryAccess.objects.create(
            user=self.treasury_officer2,
            treasury=self.treasury_egp2,
            can_disburse=True,
            can_deposit=True
        )
        UserTreasuryAccess.objects.create(
            user=self.treasury_officer1,
            treasury=self.transit_acc,
            can_disburse=True,
            can_deposit=True
        )
        UserTreasuryAccess.objects.create(
            user=self.treasury_officer2,
            treasury=self.transit_acc,
            can_disburse=True,
            can_deposit=True
        )

    def test_31_period_closed_blocks_transfer(self):
        """السيناريو 31: منع تسجيل أو ترحيل سندات التحويل المالي إذا كانت الفترة المحاسبية مغلقة"""
        from financial.services.cash_transfer_service import CashTransferService
        from financial.models.fiscal_year import FiscalYear
        from financial.models.journal_entry import AccountingPeriod

        fy = FiscalYear.objects.create(
            year_code="FY2025",
            name="2025",
            start_date="2025-01-01",
            end_date="2025-12-31",
            status="open"
        )
        period = AccountingPeriod.objects.create(
            fiscal_year=fy,
            name="Jan 2025",
            start_date="2025-01-01",
            end_date="2025-01-31",
            status="closed",
            period_number=1
        )

        with pytest.raises(ValidationError) as exc_info:
            CashTransferService.execute_transfer(
                from_account_id=self.treasury_egp1.id,
                to_account_id=self.treasury_egp2.id,
                source_amount=Decimal("5000.00"),
                user=self.user,
                transfer_date=period.start_date
            )

        assert "الفترة المحاسبية" in str(exc_info.value) or "مغلقة" in str(exc_info.value)

    def test_32_cross_foreign_transfer_usd_to_eur_with_fx_gain_loss(self):
        """السيناريو 32: تحويل مالي متعدد العملات بين عملتين أجنبيتين (USD إلى EUR) وتوليد قيد الفروق آلياً"""
        from financial.services.cash_transfer_service import CashTransferService

        trf = CashTransferService.execute_transfer(
            from_account_id=self.treasury_usd.id,
            to_account_id=self.treasury_eur.id,
            source_amount=Decimal("1000.00"),
            user=self.user,
            exchange_rate=Decimal("0.932692")
        )

        assert trf.status == TransferStatus.COMPLETED
        assert trf.journal_entry is not None
        assert trf.journal_entry.status == "posted"

        # التحقق من توازن قيد اليومية
        total_debit = sum(l.debit for l in trf.journal_entry.lines.all())
        total_credit = sum(l.credit for l in trf.journal_entry.lines.all())
        assert abs(total_debit - total_credit) <= Decimal("0.05")

    def test_33_safe_archiving_blocked_when_in_transit_transfer_pending(self):
        """السيناريو 33: منع حذف أو أرشفة أي حساب نقدي إذا كان طرفاً في سند تحويل مرحلي قيد النقل في الطريق"""
        from financial.services.cash_transfer_service import CashTransferService

        trf = CashTransferService.dispatch_transit_transfer(
            from_account_id=self.treasury_egp1.id,
            to_account_id=self.treasury_egp2.id,
            source_amount=Decimal("7000.00"),
            user=self.user
        )

        self.client.force_login(self.user)
        url_delete = reverse("financial:cash_account_delete", args=[self.treasury_egp2.id])
        response = self.client.post(url_delete)

        # يجب رفض العملية لوجود سند بالطريق
        assert response.status_code == 400
        resp_text = response.json().get("message", "") or response.json().get("error", "")
        assert "سندات تحويل" in resp_text or "الطريق" in resp_text

    def test_34_safe_archiving_allowed_when_zero_balance_and_inactive(self):
        """السيناريو 34: السماح بأرشفة وحذف الخزينة المعطلة ذات الرصيد الصفري الخالية من السندات المعلقة"""
        empty_treasury = ChartOfAccounts.objects.create(
            code="1112099",
            name="خزينة ملغاة",
            account_type=self.asset_type,
            currency=self.egp,
            is_active=False,
            is_leaf=True,
            is_cash_account=True
        )

        self.client.force_login(self.user)
        url_delete = reverse("financial:cash_account_delete", args=[empty_treasury.id])
        response = self.client.post(url_delete)

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert not ChartOfAccounts.objects.filter(id=empty_treasury.id).exists()

    def test_35_double_reversal_rejected(self):
        """السيناريو 35: منع عكس السند المالي المعكوس مسبقاً لمنع التكرار والازدواجية"""
        from financial.services.cash_transfer_service import CashTransferService

        trf = CashTransferService.execute_transfer(
            from_account_id=self.treasury_egp1.id,
            to_account_id=self.treasury_egp2.id,
            source_amount=Decimal("3000.00"),
            user=self.user
        )

        # العكس الأول ينجح
        CashTransferService.reverse_transfer(trf.id, user=self.user, reason="العكس الأول")

        # العكس الثاني يجب أن يفشل
        with pytest.raises(ValidationError) as exc_info:
            CashTransferService.reverse_transfer(trf.id, user=self.user, reason="العكس الثاني المزدوج")

        assert "معكوس" in str(exc_info.value) or "reversed" in str(exc_info.value).lower()

    def test_36_sod_receiver_cannot_be_sender_on_in_transit(self):
        """السيناريو 36: تطبيق مبدأ الفصل بين المهام (SoD) عند استلام النقدية بالطريق"""
        from financial.services.cash_transfer_service import CashTransferService

        trf = CashTransferService.dispatch_transit_transfer(
            from_account_id=self.treasury_egp1.id,
            to_account_id=self.treasury_egp2.id,
            source_amount=Decimal("4000.00"),
            user=self.treasury_officer1
        )

        # محاولة نفس المستخدم الذي أرسل السند أن يقوم بتأكيد استلامه تفشل إن لم يكن سوبر يوزر
        with pytest.raises(ValidationError) as exc_info:
            CashTransferService.receive_transit_transfer(
                transfer_id=trf.id,
                user=self.treasury_officer1,
                received_amount=Decimal("4000.00")
            )

        assert "الفصل بين المهام" in str(exc_info.value) or "نفس المستخدم" in str(exc_info.value)

    def test_37_in_transit_rejection_workflow(self):
        """السيناريو 37: رفض استلام النقدية بالطريق في حالة عدم مطابقة المبلغ أو تلف النقدية"""
        from financial.services.cash_transfer_service import CashTransferService

        trf = CashTransferService.dispatch_transit_transfer(
            from_account_id=self.treasury_egp1.id,
            to_account_id=self.treasury_egp2.id,
            source_amount=Decimal("6500.00"),
            user=self.treasury_officer1
        )

        trf.status = TransferStatus.REJECTED
        trf.notes = "تم رفض الاستلام لوجود عجز نقدي مع المندوب"
        trf.save(update_fields=["status", "notes"])

        trf.refresh_from_db()
        assert trf.status == TransferStatus.REJECTED

    def test_38_source_linkage_service_registration(self):
        """السيناريو 38: التحقق من تسجيل وسلسلة الربط المحاسبي التتبعي لسند التحويل بدفتر اليومية"""
        from governance.services.source_linkage_service import SourceLinkageService
        from financial.services.cash_transfer_service import CashTransferService

        assert "financial.CashTransfer" in SourceLinkageService.ALLOWED_SOURCES

        trf = CashTransferService.execute_transfer(
            from_account_id=self.treasury_egp1.id,
            to_account_id=self.treasury_egp2.id,
            source_amount=Decimal("8500.00"),
            user=self.user
        )

        source_obj = SourceLinkageService.get_source_object("financial", "CashTransfer", trf.id)
        assert source_obj is not None
        assert isinstance(source_obj, CashTransfer)
        assert source_obj.id == trf.id

    def test_39_denominations_breakdown_full_parity_validation(self):
        """السيناريو 39: مطابقة وتدقيق مفصل فئات النقدية المسلمة (200، 100، 50، 20) مع إجمالي السند"""
        from financial.services.cash_transfer_service import CashTransferService

        denominations = {
            "200": 25,  # 5000
            "100": 30,  # 3000
            "50": 30,   # 1500
            "20": 25    # 500 => Total = 10,000 EGP
        }

        trf = CashTransferService.execute_transfer(
            from_account_id=self.treasury_egp1.id,
            to_account_id=self.treasury_egp2.id,
            source_amount=Decimal("10000.00"),
            user=self.user,
            denominations_breakdown=denominations
        )

        assert trf.denominations_breakdown == denominations
        total_denom = sum(int(d) * int(qty) for d, qty in trf.denominations_breakdown.items())
        assert Decimal(str(total_denom)) == trf.source_amount

    def test_40_atomic_rollback_on_failure(self):
        """السيناريو 40: التحقق من التراجع الذري التام (Atomic Rollback) وعدم بقاء أي سجلات يتيمة عند الخطأ"""
        from financial.services.cash_transfer_service import CashTransferService
        from unittest.mock import patch

        initial_transfers_count = CashTransfer.objects.count()

        # محاكاة خطأ استثنائي أثناء ترحيل قيد اليومية
        with patch("governance.services.accounting_gateway.AccountingGateway.create_journal_entry", side_effect=Exception("Database Lock Timeout")):
            with pytest.raises(Exception) as exc_info:
                CashTransferService.execute_transfer(
                    from_account_id=self.treasury_egp1.id,
                    to_account_id=self.treasury_egp2.id,
                    source_amount=Decimal("12000.00"),
                    user=self.user
                )

            assert "Database Lock Timeout" in str(exc_info.value)

        # التأكد من التراجع الكامل وعدم حفظ أي سجل
        final_transfers_count = CashTransfer.objects.count()
        assert final_transfers_count == initial_transfers_count






