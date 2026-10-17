# -*- coding: utf-8 -*-
"""
FIN-CORE-026: Comprehensive Unit and Integration Tests for Smart Treasury, Bank & Custody Account Provisioning
اختبارات شاملة ومحوكمة لتأسيس الخزن والحسابات البنكية وصناديق العهد
"""
from decimal import Decimal
import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models import AccountingPeriod
from financial.models.treasury_access import UserTreasuryAccess, TreasuryAccessAuditLog
from financial.models.custody_history import CustodyAssignmentHistory
from users.models import Role
from hr.models.employee import Employee
from hr.models.work_location import WorkLocation


@pytest.mark.django_db
class TestTreasuryProvisioningSuite:
    """
    مجموعة اختبارات التحقق من تأسيس الحسابات المالية (خزن، بنوك، عهد)
    """

    @pytest.fixture(autouse=True)
    def setup_data(self, django_user_model):
        self.admin_user = django_user_model.objects.create_superuser(
            username="admin_treasury",
            email="admin@mwheba.com",
            password="AdminPassword123!"
        )

        self.regular_user = django_user_model.objects.create_user(
            username="regular_user",
            email="regular@mwheba.com",
            password="UserPassword123!"
        )

        self.emp_user = django_user_model.objects.create_user(
            username="emp_custody_user",
            email="emp@mwheba.com",
            password="EmpPassword123!"
        )

        from hr.models.organization import Department, JobTitle
        self.dept = Department.objects.create(code="FIN01", name_ar="الإدارة المالية")
        self.job = JobTitle.objects.create(code="JOB-001", title_ar="أمين خزينة", department=self.dept)

        self.employee = Employee.objects.create(
            name="أحمد محمود المحاسب",
            employee_number="EMP-1001",
            national_id="29001011234567",
            birth_date=timezone.now().date().replace(year=1990),
            gender="male",
            marital_status="single",
            department=self.dept,
            job_title=self.job,
            hire_date=timezone.now().date(),
            created_by=self.admin_user,
            user=self.emp_user,
            status="active"
        )

        self.work_location = WorkLocation.objects.create(
            name_ar="فرع التجمع الخامس",
            latitude=Decimal("30.0123456"),
            longitude=Decimal("31.0123456"),
            is_active=True
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
            code="AST_CURR",
            name="أصول متداولة",
            category="asset"
        )

        self.equity_type = AccountType.objects.create(
            code="EQUITY",
            name="حقوق ملكية",
            category="equity"
        )

        # Control parent accounts
        self.cash_parent = ChartOfAccounts.objects.create(
            code="11120",
            name="نقدية بالصندوق والخزائن",
            account_type=self.asset_type,
            is_leaf=False,
            is_active=True
        )

        self.bank_egp_parent = ChartOfAccounts.objects.create(
            code="11160",
            name="حسابات جارية بالبنوك - محلي",
            account_type=self.asset_type,
            is_leaf=False,
            is_active=True
        )

        self.bank_foreign_parent = ChartOfAccounts.objects.create(
            code="11170",
            name="حسابات جارية بالبنوك - عملات أجنبية",
            account_type=self.asset_type,
            is_leaf=False,
            is_active=True
        )

        self.custody_parent = ChartOfAccounts.objects.create(
            code="11180",
            name="عهد نقدية مستديمة ومؤقتة",
            account_type=self.asset_type,
            is_leaf=False,
            is_active=True
        )

        self.equity_opb = ChartOfAccounts.objects.create(
            code="31010",
            name="الأرصدة الافتتاحية",
            account_type=self.equity_type,
            is_leaf=True,
            is_active=True
        )

        from financial.models import FiscalYear, AccountingPeriod
        now = timezone.now().date()
        self.fy = FiscalYear.objects.create(
            year_code=f"FY{now.year}",
            name=str(now.year),
            start_date=now.replace(month=1, day=1),
            end_date=now.replace(month=12, day=31),
            status="open"
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fy,
            name=f"فترة {now.year}",
            start_date=now.replace(month=1, day=1),
            end_date=now.replace(month=12, day=31),
            status="open",
            period_number=1
        )

        self.url = reverse("financial:quick_add_cash_bank_account")

    def test_permission_denied_for_unauthorized_user(self, client):
        """فحص منع المستخدم غير المصرح له وإرجاع 403 Forbidden"""
        client.force_login(self.regular_user)
        response = client.post(self.url, {
            "account_category": "cash",
            "name": "خزينة تجريبية",
            "opening_balance": "0.00"
        })
        assert response.status_code == 403
        data = response.json()
        assert data["success"] is False
        assert "غير مصرح" in data["error"]

    def test_create_cash_treasury_fast_path(self, client):
        """إنشاء خزينة نقدية مسار فائق السرعة برصيد صفري وربط الفرع والسقف"""
        client.force_login(self.admin_user)
        response = client.post(self.url, {
            "account_category": "cash",
            "name": "خزينة مبيعات التجمع",
            "work_location_id": self.work_location.id,
            "max_holding_limit": "50000.00",
            "minimum_balance": "1000.00",
            "opening_balance": "0.00",
            "currency_id": self.egp.id
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.parent == self.cash_parent
        assert acc.code.startswith("11120")
        assert acc.is_cash_account is True
        assert acc.work_location == self.work_location
        assert acc.max_holding_limit == Decimal("50000.00")
        assert acc.minimum_balance == Decimal("1000.00")
        
        # Check automatic UserTreasuryAccess
        access = UserTreasuryAccess.objects.filter(user=self.admin_user, treasury=acc).first()
        assert access is not None
        assert access.can_deposit is True
        assert access.can_disburse is True

    def test_create_domestic_bank_account(self, client):
        """إنشاء حساب بنكي محلي والتأكد من التوجيه لـ 11160 وتفعيل is_reconcilable"""
        client.force_login(self.admin_user)
        response = client.post(self.url, {
            "account_category": "bank",
            "name": "بنك مصر - حساب جاري",
            "bank_name": "بنك مصر",
            "account_number": "1020304050",
            "iban": "EG1020304050607080",
            "swift_code": "BMISEGCX",
            "currency_id": self.egp.id,
            "opening_balance": "0.00"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.parent == self.bank_egp_parent
        assert acc.code.startswith("11160")
        assert acc.is_bank_account is True
        assert acc.is_reconcilable is True
        assert acc.bank_name == "بنك مصر"
        assert acc.account_number == "1020304050"

    def test_create_foreign_currency_bank_account_with_opening_balance(self, client):
        """إنشاء حساب بنكي أجنبي بالدولار وتوليد القيد الافتتاحي"""
        client.force_login(self.admin_user)
        response = client.post(self.url, {
            "account_category": "bank",
            "name": "CIB - حساب دولار أمريكي",
            "bank_name": "CIB",
            "account_number": "9988776655",
            "currency_id": self.usd.id,
            "opening_balance": "1000.00",
            "exchange_rate": "50.000000",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d")
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.parent == self.bank_foreign_parent
        assert acc.code.startswith("11170")
        assert acc.currency == self.usd
        assert acc.opening_balance == Decimal("1000.00")

    def test_create_custody_account_with_history(self, client):
        """إنشاء صندوق عهدة لموظف والتأكد من التوجيه لـ 11180 وتوثيق السجل التاريخي"""
        client.force_login(self.admin_user)
        response = client.post(self.url, {
            "account_category": "custody",
            "name": "عهدة مشتريات أحمد محمود",
            "employee_id": self.employee.id,
            "custody_type": "permanent",
            "currency_id": self.egp.id,
            "opening_balance": "5000.00",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d")
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.parent == self.custody_parent
        assert acc.code.startswith("11180")
        assert acc.is_custody_account is True
        assert acc.assigned_employee == self.employee

        # Check CustodyAssignmentHistory
        history = CustodyAssignmentHistory.objects.filter(account=acc, employee=self.employee).first()
        assert history is not None
        assert history.opening_balance_on_handover == Decimal("5000.00")
        assert history.is_active is True

        # Check UserTreasuryAccess granted to employee's user
        emp_access = UserTreasuryAccess.objects.filter(user=self.emp_user, treasury=acc).first()
        assert emp_access is not None

    def test_duplicate_bank_account_rejection(self, client):
        """رفض تكرار رقم الحساب البنكي لنفس البنك"""
        client.force_login(self.admin_user)
        # إنشاء أول حساب
        client.post(self.url, {
            "account_category": "bank",
            "name": "بنك القاهرة 1",
            "bank_name": "بنك القاهرة",
            "account_number": "11223344",
            "currency_id": self.egp.id,
            "opening_balance": "0.00"
        })

        # محاولة إنشاء حساب مكرر
        response = client.post(self.url, {
            "account_category": "bank",
            "name": "بنك القاهرة 2",
            "bank_name": "بنك القاهرة",
            "account_number": "11223344",
            "currency_id": self.egp.id,
            "opening_balance": "0.00"
        })
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "مسجل مسبقاً" in data["error"]

    def test_duplicate_cash_account_name_rejection(self, client):
        """رفض تكرار اسم الخزنة النقدية"""
        client.force_login(self.admin_user)
        # إنشاء أول خزينة
        res1 = client.post(self.url, {
            "account_category": "cash",
            "name": "خزينة الفرع الرئيسي",
            "work_location_id": self.work_location.id,
            "opening_balance": "0.00",
            "currency_id": self.egp.id
        })
        assert res1.status_code == 200
        assert res1.json()["success"] is True

        # محاولة إنشاء خزينة بنفس الاسم
        res2 = client.post(self.url, {
            "account_category": "cash",
            "name": "خزينة الفرع الرئيسي",
            "work_location_id": self.work_location.id,
            "opening_balance": "0.00",
            "currency_id": self.egp.id
        })
        assert res2.status_code == 400
        data2 = res2.json()
        assert data2["success"] is False
        assert "يوجد خزينة مسجلة مسبقاً بنفس الاسم" in data2["error"]

    def test_cash_account_edit_duplicate_name_rejection(self, client):
        """رفض تعديل اسم الخزينة إلى اسم خزينة أخرى موجودة بالفعل"""
        client.force_login(self.admin_user)
        # إنشاء خزينة أولى
        res1 = client.post(self.url, {
            "account_category": "cash",
            "name": "خزينة رقم 1",
            "opening_balance": "0.00",
            "currency_id": self.egp.id
        })
        # إنشاء خزينة ثانية
        res2 = client.post(self.url, {
            "account_category": "cash",
            "name": "خزينة رقم 2",
            "opening_balance": "0.00",
            "currency_id": self.egp.id
        })
        acc2_id = res2.json()["account"]["id"]

        # محاولة تعديل اسم الخزينة الثانية ليصبح "خزينة رقم 1"
        edit_url = reverse("financial:cash_account_edit", args=[acc2_id])
        edit_resp = client.post(edit_url, {
            "name": "خزينة رقم 1",
            "account_type_choice": "cash",
            "is_active": "on"
        }, follow=True)
        
        # التأكد من عدم تغيير الاسم
        acc2 = ChartOfAccounts.objects.get(pk=acc2_id)
        assert acc2.name == "خزينة رقم 2"

    def test_cash_account_creation_with_opening_balance_auto_resolves_equity(self, client):
        """التحقق من إنشاء خزينة برصيد افتتاحي وحل حساب الأرصدة الافتتاحية تلقائياً"""
        client.force_login(self.admin_user)
        # حذف حساب الأرصدة الافتتاحية إن وجد لاختبار الحل التلقائي الجذري
        ChartOfAccounts.objects.filter(code="31010").delete()

        res = client.post(self.url, {
            "account_category": "cash",
            "name": "خزينة المبيعات الجديدة",
            "work_location_id": self.work_location.id,
            "opening_balance": "100000.00",
            "opening_balance_date": "2026-10-08",
            "currency_id": self.egp.id
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

        # التحقق من إنشاء الحساب والقيد الافتتاحي المقابل
        new_acc = ChartOfAccounts.objects.get(name="خزينة المبيعات الجديدة")
        assert new_acc.code in data["message"]
        assert new_acc.opening_balance == Decimal("100000.00")
        assert ChartOfAccounts.objects.filter(code="31010").exists()

    def test_custody_creation_by_non_superuser_financial_manager(self, client, django_user_model):
        """التحقق من إنشاء عهدة بواسطة مدير مالي غير superuser والتأكد من قلب is_leaf للأب وإسناد الصلاحيات وعدم رصد TAMPER_ATTEMPT"""
        parent_11130, _ = ChartOfAccounts.objects.get_or_create(
            code="11130",
            defaults={
                "name": "عهد نقدية مستديمة ومؤقتة",
                "account_type": self.asset_type,
                "is_leaf": True,
                "is_active": True,
            }
        )
        parent_11130.is_leaf = True
        parent_11130.save()

        fin_mgr = django_user_model.objects.create_user(
            username="fin_mgr_user",
            email="fm_user@mwheba.com",
            password="FMPassword123!"
        )
        role, _ = Role.objects.get_or_create(name="financial_manager")
        fin_mgr.role = role
        fin_mgr.save()

        client.force_login(fin_mgr)
        response = client.post(self.url, {
            "account_category": "custody",
            "name": "عهدة المشتريات الخارجية - تجربة المدير المالي",
            "employee_id": self.employee.id,
            "custody_type": "permanent",
            "currency_id": self.egp.id,
            "opening_balance": "200000.00",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d"),
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.code.startswith("11130")
        assert acc.opening_balance == Decimal("200000.00")
        assert acc.is_custody_account is True

        # التأكد من قلب حساب الأب لـ is_leaf=False
        parent_11130.refresh_from_db()
        assert parent_11130.is_leaf is False

        # التأكد من إنشاء صلاحيات للمنشئ (المدير المالي) وللموظف المسؤول
        mgr_access = UserTreasuryAccess.objects.filter(user=fin_mgr, treasury=acc).first()
        assert mgr_access is not None
        assert mgr_access.can_deposit is True
        assert mgr_access.can_disburse is True

        emp_access = UserTreasuryAccess.objects.filter(user=self.emp_user, treasury=acc).first()
        assert emp_access is not None
        assert emp_access.employee == self.employee

        # التأكد من عدم تسجيل أي محاولة اختراق وهمية في سجل الرقابة
        assert not TreasuryAccessAuditLog.objects.filter(treasury=acc, action="TAMPER_ATTEMPT").exists()

    def test_custody_creation_by_accountant_with_add_perm(self, client, django_user_model):
        """التحقق من إنشاء عهدة بواسطة محاسب يحمل صلاحية add_chartofaccounts"""
        accountant = django_user_model.objects.create_user(
            username="accountant_ops",
            email="acct_ops@mwheba.com",
            password="AcctPassword123!"
        )
        perm_add_coa = Permission.objects.get(codename="add_chartofaccounts")
        accountant.user_permissions.add(perm_add_coa)

        client.force_login(accountant)
        response = client.post(self.url, {
            "account_category": "custody",
            "name": "عهدة صيانة الفرع - محاسب",
            "employee_id": self.employee.id,
            "custody_type": "permanent",
            "currency_id": self.egp.id,
            "opening_balance": "50000.00",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d"),
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.opening_balance == Decimal("50000.00")
        assert UserTreasuryAccess.objects.filter(user=accountant, treasury=acc).exists()

    def test_custody_creation_with_no_user_employee(self, client):
        """التحقق من إنشاء عهدة لموظف غير مرتبط بحساب مستخدم نظام دون حدوث أخطاء"""
        emp_no_user = Employee.objects.create(
            name="سائق مندوب بدون حساب",
            employee_number="EMP-9999",
            national_id="29001019999999",
            birth_date=timezone.now().date().replace(year=1995),
            gender="male",
            marital_status="single",
            department=self.dept,
            job_title=self.job,
            hire_date=timezone.now().date(),
            created_by=self.admin_user,
            user=None,
            status="active"
        )

        client.force_login(self.admin_user)
        response = client.post(self.url, {
            "account_category": "custody",
            "name": "عهدة وقود السيارات",
            "employee_id": emp_no_user.id,
            "custody_type": "temporary",
            "currency_id": self.egp.id,
            "opening_balance": "10000.00",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d"),
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        acc = ChartOfAccounts.objects.get(pk=data["account"]["id"])
        assert acc.assigned_employee == emp_no_user

        # التحقق من توثيق سجل التسليم للموظف
        history = CustodyAssignmentHistory.objects.filter(account=acc, employee=emp_no_user).first()
        assert history is not None
        assert history.opening_balance_on_handover == Decimal("10000.00")

        # التحقق من منح الصلاحية لمنشئ الحساب دون انهيار النظام بسبب user=None
        assert UserTreasuryAccess.objects.filter(user=self.admin_user, treasury=acc).exists()

    def test_custody_negative_opening_balance_rejection(self, client):
        """التحقق من رفض فتح عهدة برصيد افتتاحي سالب مع إرجاع 400"""
        client.force_login(self.admin_user)
        response = client.post(self.url, {
            "account_category": "custody",
            "name": "عهدة غير قانونية برصيد سالب",
            "employee_id": self.employee.id,
            "custody_type": "permanent",
            "currency_id": self.egp.id,
            "opening_balance": "-25000.00",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d"),
        })
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "سالب" in data["error"]

    def test_custom_exchange_rate_invalid_rejection(self, client):
        """التحقق من رفض سعر الصرف الصفري أو السالب لحسابات العملات الأجنبية"""
        client.force_login(self.admin_user)
        
        # اختبار سعر صرف صفري
        res_zero = client.post(self.url, {
            "account_category": "bank",
            "name": "بنك أجنبي بسعر صرف صفري",
            "bank_name": "HSBC",
            "account_number": "5544332211",
            "currency_id": self.usd.id,
            "opening_balance": "1000.00",
            "exchange_rate": "0",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d"),
        })
        assert res_zero.status_code == 400
        assert res_zero.json()["success"] is False
        assert "\u0633\u0639\u0631 \u0627\u0644\u0635\u0631\u0641" in res_zero.json()["error"]

        # اختبار سعر صرف سالب
        res_neg = client.post(self.url, {
            "account_category": "bank",
            "name": "بنك أجنبي بسعر صرف سالب",
            "bank_name": "HSBC",
            "account_number": "5544332212",
            "currency_id": self.usd.id,
            "opening_balance": "1000.00",
            "exchange_rate": "-50.00",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d"),
        })
        assert res_neg.status_code == 400
        assert res_neg.json()["success"] is False
        assert "\u0633\u0639\u0631 \u0627\u0644\u0635\u0631\u0641" in res_neg.json()["error"]

    def test_atomic_rollback_on_failure_leaves_no_ghost_account(self, client, monkeypatch):
        """التحقق من التراجع الذري للعملية وعدم ترك حساب شبحي يتيم عند فشل إنشاء القيد الافتتاحي"""
        from django.core.exceptions import ValidationError
        from governance.services.accounting_gateway import AccountingGateway

        def mock_create_journal_entry(*args, **kwargs):
            raise ValidationError("فشل متعمد لمحاكاة خطأ أثناء توليد القيد الافتتاحي")

        monkeypatch.setattr(AccountingGateway, "create_journal_entry", mock_create_journal_entry)

        client.force_login(self.admin_user)
        response = client.post(self.url, {
            "account_category": "custody",
            "name": "عهدة ستفشل عمداً",
            "employee_id": self.employee.id,
            "custody_type": "permanent",
            "currency_id": self.egp.id,
            "opening_balance": "75000.00",
            "opening_balance_date": timezone.now().date().strftime("%Y-%m-%d"),
        })
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "فشل متعمد" in data["error"]

        # التأكد من التراجع التام وعدم وجود الحساب في قاعدة البيانات نهائياً
        assert not ChartOfAccounts.objects.filter(name="عهدة ستفشل عمداً").exists()


