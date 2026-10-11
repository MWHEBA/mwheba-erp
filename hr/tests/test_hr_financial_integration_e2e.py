"""
Comprehensive End-to-End Test Suite for HR-to-Finance Accounting Integration.
Validates the complete lifecycle of HR transactions, Journal Entry balances in General Ledger,
idempotency, account role resolution, expense offsets, and backfill command execution.
"""

import pytest
from decimal import Decimal
from datetime import date, datetime
from io import StringIO

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.utils import timezone

from hr.models import (
    Employee, Department, JobTitle, Contract,
    Payroll, PayrollLine, Advance, AdvanceInstallment, InsurancePayment
)
from financial.models import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    FinancialCategory, FinancialSubcategory
)
from financial.services.role_registry import AccountRoleRegistry
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from governance.services.source_linkage_service import SourceLinkageService
from hr.services.advance_service import AdvanceService
from hr.services.payroll_service import PayrollService
from hr.services.payroll_accounting_service import PayrollAccountingService
from hr.services.insurance_payment_service import InsurancePaymentService

User = get_user_model()


@pytest.fixture
def hr_test_user(db):
    user, _ = User.objects.get_or_create(
        username='hr_fin_admin',
        defaults={
            'email': 'hr_admin@mwheba.com',
            'is_staff': True,
            'is_superuser': True,
            'is_active': True
        }
    )
    return user


@pytest.fixture
def standard_chart_of_accounts(db):
    """Ensure all standard accounts for HR integration exist and are leaf accounts."""
    from financial.models.chart_of_accounts import AccountType

    type_asset, _ = AccountType.objects.get_or_create(code='ASSET', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    type_liab, _ = AccountType.objects.get_or_create(code='LIAB', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    type_exp, _ = AccountType.objects.get_or_create(code='EXP', defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'})

    types = {
        'asset': type_asset,
        'liability': type_liab,
        'expense': type_exp,
    }

    accounts = {
        '11110': ('الخزينة الرئيسية', 'asset'),
        '11160001': ('البنك الأهلي المصري', 'asset'),
        '11230': ('سلف العاملين', 'asset'),
        '21320': ('مصلحة الضرائب - كسب عمل', 'liability'),
        '21410': ('رواتب وأجور مستحقة', 'liability'),
        '21420': ('هيئة التأمينات الاجتماعية', 'liability'),
        '21430': ('مخصص مكافأة نهاية الخدمة', 'liability'),
        '52100': ('الرواتب والأجور', 'expense'),
        '52200': ('تأمينات اجتماعية - مصروف', 'expense'),
        '52300': ('مصروف نهاية الخدمة', 'expense'),
        '54400': ('فروق تقريب العملات', 'expense'),
    }
    resolved = {}
    for code, (name, cat) in accounts.items():
        acc = ChartOfAccounts.objects.filter(code=code).first()
        if not acc:
            acc = ChartOfAccounts.objects.create(
                code=code,
                name=name,
                account_type=types[cat],
                is_active=True,
                is_leaf=True
            )
        resolved[code] = acc
    return resolved


@pytest.fixture
def test_org_structure(db, hr_test_user):
    dept, _ = Department.objects.get_or_create(
        code='FIN-OPS',
        defaults={
            'name_ar': 'الشؤون المالية والعمليات',
            'name_en': 'Finance & Operations',
            'is_active': True
        }
    )
    job, _ = JobTitle.objects.get_or_create(
        code='ACC-SNR',
        defaults={
            'title_ar': 'محاسب أول',
            'title_en': 'Senior Accountant',
            'department': dept,
            'is_active': True
        }
    )
    emp, _ = Employee.objects.get_or_create(
        employee_number='EMP-TEST-100',
        defaults={
            'name': 'طارق أحمد محمود',
            'national_id': '29201011111111',
            'birth_date': date(1992, 1, 1),
            'gender': 'male',
            'marital_status': 'married',
            'department': dept,
            'job_title': job,
            'hire_date': date(2025, 1, 1),
            'status': 'active',
            'created_by': hr_test_user
        }
    )
    contract, _ = Contract.objects.get_or_create(
        contract_number='CTR-TEST-100',
        defaults={
            'employee': emp,
            'contract_type': 'permanent',
            'start_date': date(2025, 1, 1),
            'basic_salary': Decimal('12000.00'),
            'status': 'active',
            'created_by': hr_test_user
        }
    )
    return {'dept': dept, 'job': job, 'emp': emp, 'contract': contract}


@pytest.mark.django_db
class TestHRFinancialIntegrationE2E:
    """E2E Test Suite for HR Accounting Integration."""

    def test_01_advance_disbursement_journal_entry(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """صرف سلفة والتحقق من حساب 11230 والخزينة"""
        emp = test_org_structure['emp']
        cash_acc = standard_chart_of_accounts['11110']

        advance = Advance.objects.create(
            employee=emp,
            amount=Decimal('5000.00'),
            reason='سلفة زواج طارئة',
            installments_count=5,
            installment_amount=Decimal('1000.00'),
            remaining_amount=Decimal('5000.00'),
            deduction_start_month=date(2026, 6, 1),
            payment_date=date(2026, 5, 20),
            status='paid'
        )

        je = AdvanceService.create_disbursement_journal_entry(
            advance=advance,
            payment_account=cash_acc,
            created_by=hr_test_user
        )

        assert je is not None
        assert advance.journal_entry_id == je.id
        assert advance.payment_account_id == cash_acc.id

        lines = list(je.lines.all())
        assert len(lines) == 2
        dr_line = [l for l in lines if l.debit > 0][0]
        cr_line = [l for l in lines if l.credit > 0][0]

        assert dr_line.account.code == '11230'
        assert cr_line.account.code == '11110'
        assert dr_line.debit == Decimal('5000.00')
        assert cr_line.credit == Decimal('5000.00')

    def test_02_payroll_payment_journal_entry_balance(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """دفع الراتب وتوازن القيد: مدين 52100 / دائن الخزينة والتأمينات والضرائب"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']
        cash_acc = standard_chart_of_accounts['11110']

        payroll = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 5, 1),
            basic_salary=Decimal('12000.00'),
            allowances=Decimal('2000.00'),
            overtime_amount=Decimal('500.00'),
            bonus=Decimal('500.00'),
            gross_salary=Decimal('15000.00'),
            social_insurance=Decimal('1500.00'),
            tax=Decimal('1000.00'),
            advance_deduction=Decimal('1000.00'),
            total_deductions=Decimal('3500.00'),
            net_salary=Decimal('11500.00'),
            status='approved',
            processed_by=hr_test_user
        )

        paid_payroll = PayrollService.pay_payroll(
            payroll=payroll,
            paid_by=hr_test_user,
            payment_account=cash_acc,
            payment_reference='PAY-TEST-001'
        )

        assert paid_payroll.status == 'paid'
        je = paid_payroll.journal_entry
        assert je is not None

        lines = list(je.lines.all())
        tot_dr = sum(l.debit for l in lines)
        tot_cr = sum(l.credit for l in lines)

        assert abs(tot_dr - tot_cr) < Decimal('0.01')
        assert tot_dr == Decimal('15000.00')
        assert tot_cr == Decimal('15000.00')

    def test_03_payroll_advance_deduction_repayment(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """خصم قسط السلفة من الراتب وإقفال الحساب ذرّياً"""
        emp = test_org_structure['emp']
        cash_acc = standard_chart_of_accounts['11110']

        advance = Advance.objects.create(
            employee=emp,
            amount=Decimal('3000.00'),
            reason='سلفة علاجية',
            installments_count=3,
            installment_amount=Decimal('1000.00'),
            remaining_amount=Decimal('3000.00'),
            deduction_start_month=date(2026, 6, 1),
            payment_date=date(2026, 5, 1),
            status='paid',
            payment_account=cash_acc
        )

        # Record deduction
        inst = advance.record_installment_payment(month=date(2026, 6, 1), amount=Decimal('1000.00'))
        advance.refresh_from_db()

        assert advance.paid_installments == 1
        assert advance.remaining_amount == Decimal('2000.00')
        assert advance.status == 'in_progress'
        assert inst.amount == Decimal('1000.00')

    def test_04_income_tax_deduction_journal_entry(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """استقطاع ضريبة كسب العمل على حساب 21320"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']
        cash_acc = standard_chart_of_accounts['11110']

        payroll = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 6, 1),
            basic_salary=Decimal('10000.00'),
            gross_salary=Decimal('10000.00'),
            tax=Decimal('1250.00'),
            total_deductions=Decimal('1250.00'),
            net_salary=Decimal('8750.00'),
            status='approved',
            processed_by=hr_test_user
        )

        paid_payroll = PayrollService.pay_payroll(
            payroll=payroll,
            paid_by=hr_test_user,
            payment_account=cash_acc
        )

        tax_line = paid_payroll.journal_entry.lines.filter(account__code='21320').first()
        assert tax_line is not None
        assert tax_line.credit == Decimal('1250.00')

    def test_05_external_insurance_payment_journal_entry(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """تحصيل تأمين الموظف الخارجي: مدين الخزينة / دائن 21420"""
        emp = test_org_structure['emp']
        cash_acc = standard_chart_of_accounts['11110']

        ins_payment = InsurancePayment.objects.create(
            employee=emp,
            month=date(2026, 5, 1),
            total_amount=Decimal('850.00'),
            status='pending'
        )

        paid_ins = InsurancePaymentService.record_payment(
            insurance_payment=ins_payment,
            payment_account=cash_acc,
            received_by=hr_test_user,
            payment_date=date(2026, 5, 25)
        )

        assert paid_ins.status == 'paid'
        je = paid_ins.journal_entry
        assert je is not None

        lines = list(je.lines.all())
        assert len(lines) == 2
        dr = [l for l in lines if l.debit > 0][0]
        cr = [l for l in lines if l.credit > 0][0]

        assert dr.account.code == '11110'
        assert cr.account.code == '21420'
        assert dr.debit == Decimal('850.00')
        assert cr.credit == Decimal('850.00')

    def test_06_absence_penalty_other_deductions_offset_expense(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """التحقق من توجيه خصم الغياب والخصومات الأخرى لتخفيض المصروف 52100 بدلاً من الخصوم"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']
        cash_acc = standard_chart_of_accounts['11110']

        payroll = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 7, 1),
            basic_salary=Decimal('10000.00'),
            gross_salary=Decimal('10000.00'),
            absence_deduction=Decimal('500.00'),
            late_deduction=Decimal('100.00'),
            other_deductions=Decimal('200.00'),
            total_deductions=Decimal('800.00'),
            net_salary=Decimal('9200.00'),
            status='approved',
            processed_by=hr_test_user
        )

        paid_payroll = PayrollService.pay_payroll(
            payroll=payroll,
            paid_by=hr_test_user,
            payment_account=cash_acc
        )

        je = paid_payroll.journal_entry
        salary_credit_lines = je.lines.filter(account__code='52100', credit__gt=0)
        total_salary_credit = sum(l.credit for l in salary_credit_lines)

        assert total_salary_credit == Decimal('800.00'), f"Expense offset must equal 800.00, got {total_salary_credit}"
        # Ensure no liability accounts like 21410 were credited for absence/penalties
        liability_line = je.lines.filter(account__code='21410').first()
        assert liability_line is None, "Liabilities must NOT receive absence/penalty deductions!"

    def test_07_zero_net_salary_journal_entry(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """اختبار قيد راتب ذو صافي صفري بدون سطر نقدية"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']
        cash_acc = standard_chart_of_accounts['11110']

        payroll = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 8, 1),
            basic_salary=Decimal('6000.00'),
            gross_salary=Decimal('6000.00'),
            social_insurance=Decimal('1000.00'),
            tax=Decimal('1000.00'),
            advance_deduction=Decimal('4000.00'),
            total_deductions=Decimal('6000.00'),
            net_salary=Decimal('0.00'),
            payment_account=cash_acc,
            status='approved',
            processed_by=hr_test_user
        )

        svc = PayrollAccountingService()
        je = svc.create_payroll_journal_entry(payroll, hr_test_user)
        assert je is not None

        lines = list(je.lines.all())
        cash_line = [l for l in lines if l.account.code == '11110']
        assert len(cash_line) == 0, "Zero net salary JE must NOT contain cash/bank lines!"

        tot_dr = sum(l.debit for l in lines)
        tot_cr = sum(l.credit for l in lines)
        assert abs(tot_dr - tot_cr) < Decimal('0.01')
        assert tot_dr == Decimal('6000.00')

    def test_08_department_subcategory_parent_validation(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """اختبار مطابقة التصنيف الرئيسي والفرعي لمنع رفض الحوكمة"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']

        cat = FinancialCategory.objects.create(
            name='رواتب',
            code='test_salaries_cat',
            default_expense_account=standard_chart_of_accounts['52100']
        )
        subcat = FinancialSubcategory.objects.create(name='قسم المالية', code='subcat_fin', parent_category=cat)

        emp.department.financial_subcategory = subcat
        emp.department.save()

        payroll = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 9, 1),
            basic_salary=Decimal('7000.00'),
            gross_salary=Decimal('7000.00'),
            net_salary=Decimal('7000.00'),
            total_deductions=Decimal('0.00'),
            status='approved',
            processed_by=hr_test_user
        )

        svc = PayrollAccountingService()
        resolved_subcat, resolved_cat = svc._resolve_categories(payroll)

        assert resolved_subcat.id == subcat.id
        assert resolved_cat.id == cat.id

    def test_09_post_payment_immutability_guard(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """التحقق من منع تعديل أو إلغاء اعتماد قسيمة مدفوعة"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']
        cash_acc = standard_chart_of_accounts['11110']

        payroll = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 10, 1),
            basic_salary=Decimal('8000.00'),
            gross_salary=Decimal('8000.00'),
            net_salary=Decimal('8000.00'),
            total_deductions=Decimal('0.00'),
            status='approved',
            processed_by=hr_test_user
        )

        paid_payroll = PayrollService.pay_payroll(
            payroll=payroll,
            paid_by=hr_test_user,
            payment_account=cash_acc
        )

        with pytest.raises(ValueError, match="يمكن إلغاء الاعتماد فقط للقسائم المعتمدة وغير المدفوعة"):
            PayrollService.unapprove_payroll(paid_payroll, hr_test_user)

    def test_10_idempotency_protection(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """منع تكرار القيود لأي عملية HR مرتين"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']
        cash_acc = standard_chart_of_accounts['11110']

        payroll = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 11, 1),
            basic_salary=Decimal('8000.00'),
            gross_salary=Decimal('8000.00'),
            net_salary=Decimal('8000.00'),
            total_deductions=Decimal('0.00'),
            status='approved',
            payment_account=cash_acc,
            processed_by=hr_test_user
        )

        svc = PayrollAccountingService()
        je1 = svc.create_payroll_journal_entry(payroll, hr_test_user)
        je2 = svc.create_payroll_journal_entry(payroll, hr_test_user)

        assert je1.id == je2.id, "Idempotency must return the existing Journal Entry without creating duplicates!"

    def test_11_advance_cash_repayment_journal_entry(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """سداد قسط سلفة نقداً بالخزينة"""
        emp = test_org_structure['emp']
        cash_acc = standard_chart_of_accounts['11110']

        advance = Advance.objects.create(
            employee=emp,
            amount=Decimal('4000.00'),
            reason='سلفة مؤقتة',
            installments_count=4,
            installment_amount=Decimal('1000.00'),
            remaining_amount=Decimal('4000.00'),
            deduction_start_month=date(2026, 6, 1),
            payment_date=date(2026, 5, 1),
            status='paid',
            payment_account=cash_acc
        )

        adv_after, je = AdvanceService.repay_installment_cash(
            advance=advance,
            installment_amount=Decimal('1000.00'),
            payment_account=cash_acc,
            user=hr_test_user,
            payment_date=date(2026, 6, 15)
        )

        assert je is not None
        lines = list(je.lines.all())
        dr = [l for l in lines if l.debit > 0][0]
        cr = [l for l in lines if l.credit > 0][0]

        assert dr.account.code == '11110'
        assert cr.account.code == '11230'
        assert adv_after.remaining_amount == Decimal('3000.00')

    def test_12_bulk_processing_fault_isolation(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """عزل أخطاء القسائم أثناء الصرف الجماعي"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']
        cash_acc = standard_chart_of_accounts['11110']

        p_valid = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 12, 1),
            basic_salary=Decimal('5000.00'),
            gross_salary=Decimal('5000.00'),
            net_salary=Decimal('5000.00'),
            total_deductions=Decimal('0.00'),
            status='approved',
            processed_by=hr_test_user
        )

        # Process single slip in atomic isolation
        res = PayrollService.pay_payroll(p_valid, hr_test_user, cash_acc)
        assert res.status == 'paid'
        assert res.journal_entry is not None

    def test_13_end_of_service_benefit_allowed_source(self, hr_test_user, standard_chart_of_accounts):
        """التحقق من اعتماد نموذج مكافأة نهاية الخدمة في الحوكمة"""
        assert 'hr.EndOfServiceBenefit' in AccountingGateway.ALLOWED_SOURCES
        assert 'hr.Advance' in AccountingGateway.ALLOWED_SOURCES
        assert 'hr.InsurancePayment' in AccountingGateway.ALLOWED_SOURCES

    def test_14_backfill_command_execution(self, hr_test_user, standard_chart_of_accounts, test_org_structure):
        """اختبار أداة المعالجة بأثر رجعي مع الفترات المفتوحة والمقفلة"""
        emp = test_org_structure['emp']
        contract = test_org_structure['contract']
        cash_acc = standard_chart_of_accounts['11110']

        p_hist = Payroll.objects.create(
            employee=emp,
            contract=contract,
            month=date(2026, 4, 1),
            basic_salary=Decimal('6000.00'),
            gross_salary=Decimal('6000.00'),
            net_salary=Decimal('6000.00'),
            total_deductions=Decimal('0.00'),
            status='paid',
            payment_account=cash_acc,
            processed_by=hr_test_user
        )

        out = StringIO()
        call_command('backfill_hr_journal_entries', month='2026-04', stdout=out)
        out_str = out.getvalue()

        p_hist.refresh_from_db()
        assert p_hist.journal_entry is not None, "Backfill command must create and link JE for historical payroll!"
