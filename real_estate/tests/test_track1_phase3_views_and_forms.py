# -*- coding: utf-8 -*-
"""
Pytest Test Suite for Track 1 - Phase 3 (Forms, Views & URLs)
فحص واجهات ونماذج ومسارات عقود مقاولي الباطن والمستخلصات التفصيلية
"""
from decimal import Decimal
from datetime import date, timedelta
import pytest
import io
import csv

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    ContractorContract,
    ContractorContractItem,
    ContractVariationOrder,
    ContractorProgressCertificate,
    ContractorCertificateItem,
    CertificatePaymentInstallmentSchedule,
)
from real_estate.forms.contractor_forms import (
    ContractorContractForm,
    ContractorContractItemForm,
    ContractorContractItemFormSet,
    ContractVariationOrderForm,
    ContractorProgressCertificateForm,
    AdvancePaymentDisbursementForm,
    RetentionReleaseForm,
    StornoReversalForm,
    CertificateExcelImportForm,
)
from supplier.models import Supplier
from financial.models import ChartOfAccounts, AccountType, EnterpriseApprovalRule
from financial.models.currency import Currency
from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware

User = get_user_model()


@pytest.fixture
def phase3_setup(db):
    """تجهيز البيانات الأساسية والمستخدمين والحسابات لاختبارات المرحلة الثالثة"""
    # تفعيل الموديول في الـ Middleware
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'التطوير العقاري', 'is_enabled': True}
    )
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_user(
        username="re_engineer_admin",
        password="Password123!",
        email="eng@mwheba.com",
        is_staff=True
    )
    # منح كافة صلاحيات العقارات
    for perm in Permission.objects.filter(content_type__app_label='real_estate'):
        user.user_permissions.add(perm)

    egp, _ = Currency.objects.get_or_create(code="EGP", defaults={'name': "Egyptian Pound", 'symbol': "EGP"})

    asset_type, _ = AccountType.objects.get_or_create(code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    liability_type, _ = AccountType.objects.get_or_create(code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'})

    accounts = {
        "12101": ("مشروعات تحت التنفيذ - أعمال مقاولات", asset_type),
        "11410": ("ضريبة القيمة المضافة - مدخلات", asset_type),
        "21310": ("تأمينات محتجزة للغير - حسن تنفيذ", liability_type),
        "21315": ("أمانات كسر مكعبات خرسانة معلقة", liability_type),
        "21345": ("أمانات نقابة المهندسين", liability_type),
        "21360": ("مخصص وأقساط وثيقة CAR", liability_type),
        "11350": ("دفعات مقدمة لمقاولي الباطن", asset_type),
        "21330": ("ضريبة الخصم والإضافة", liability_type),
        "21340": ("أمانات تأمينات اجتماعية مقاولات", liability_type),
        "42301": ("استرداد استهلاك مياه وإنارة الموقع", revenue_type),
        "42304": ("استرداد نفقات رفع رتش ومخلفات", revenue_type),
        "42302": ("إيرادات تشغيل أوناش ومعدات", revenue_type),
        "11355": ("سلف عمالة مقاولين نقدية", asset_type),
        "42303": ("استرداد نفقات طبية وحوادث أمن صناعي", revenue_type),
        "11201": ("مخزن المشروع - خامات منصرفة", asset_type),
        "42101": ("إيرادات غرامات تأخير وجودة", revenue_type),
        "42201": ("استرداد تكاليف إصلاح عيوب", revenue_type),
        "21110": ("مستحقات مقاولي الباطن", liability_type),
        "21350": ("أمانات حجوزات قضائية وتنفيذية", liability_type),
        "11121": ("حساب الضمان البنكي للمشروع Escrow", asset_type),
        "11111": ("الخزينة الرئيسية للمشروع", asset_type),
        "21210": ("أوراق الدفع - شيكات صادرة للمقاولين", liability_type),
    }
    for code, (name, a_type) in accounts.items():
        ChartOfAccounts.objects.get_or_create(
            code=code,
            defaults={'name': name, 'account_type': a_type, 'is_active': True, 'is_leaf': True}
        )

    EnterpriseApprovalRule.objects.create(
        module='REAL_ESTATE',
        rule_name='اعتماد مستخلصات المقاولين',
        min_amount=Decimal('0.00'),
        max_amount=Decimal('999999999.00'),
        approver_role='site_engineer',
        approval_level=1,
        is_active=True
    )

    project = RealEstateProject.objects.create(
        code="PRJ-VIEW-01",
        name="كمبوند الروضة السكني",
        project_type="RESIDENTIAL",
        status="UNDER_CONSTRUCTION",
        start_date=date(2026, 1, 1),
        expected_completion_date=date(2028, 12, 31),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="BLK-A",
        name="عمارة A",
        total_floors=6
    )
    contractor = Supplier.objects.create(
        name="شركة الأمل للمقاولات العامة",
        code="CON-AML-01",
        tax_number="123456789"
    )

    contract = ContractorContract.objects.create(
        contract_number="SUB-AML-2026",
        title="أعمال خرسانات وبناء عمارة A",
        project=project,
        block=block,
        contractor=contractor,
        contract_type=ContractorContract.ContractType.MEASURED_BOQ,
        tax_regime=ContractorContract.TaxRegime.TABLE_TAX_5,
        currency=egp,
        initial_contract_value=Decimal("1000000.00"),
        revised_contract_value=Decimal("1000000.00"),
        advance_payment_rate=Decimal("10.00"),
        advance_payment_amount=Decimal("100000.00"),
        advance_recovery_rate=Decimal("10.00"),
        retention_rate=Decimal("5.00"),
        site_utilities_deduction_rate=Decimal("0.50"),
        syndicate_stamp_rate=Decimal("0.450"),
        status=ContractorContract.ContractStatus.ACTIVE,
        created_by=user
    )

    item1 = ContractorContractItem.objects.create(
        contract=contract,
        item_code="CONC-01",
        description="خرسانة مسلحة للأسقف والأعمدة",
        unit="م3",
        contracted_quantity=Decimal("500.000"),
        unit_rate=Decimal("1500.00"),
        total_budget_amount=Decimal("750000.00")
    )
    item2 = ContractorContractItem.objects.create(
        contract=contract,
        item_code="BRICK-01",
        description="مباني طوب طفلي سمك 25 سم",
        unit="م2",
        contracted_quantity=Decimal("1000.000"),
        unit_rate=Decimal("250.00"),
        total_budget_amount=Decimal("250000.00")
    )

    client = Client()
    client.force_login(user)

    return {
        'user': user,
        'client': client,
        'currency': egp,
        'project': project,
        'block': block,
        'contractor': contractor,
        'contract': contract,
        'item1': item1,
        'item2': item2,
    }


# =========================================================================
# 1. اختبارات نماذج الإدخال (Forms Unit Tests)
# =========================================================================

def test_contractor_contract_form_validation(phase3_setup):
    """التحقق من صحة وقواعد نموذج إدخال عقد المقاولة"""
    setup = phase3_setup
    valid_data = {
        'contract_number': 'SUB-TEST-001',
        'title': 'أعمال تشطيبات داخلية',
        'project': setup['project'].id,
        'block': setup['block'].id,
        'contractor': setup['contractor'].id,
        'contract_type': ContractorContract.ContractType.MEASURED_BOQ,
        'start_date': date(2026, 2, 1),
        'completion_date': date(2026, 8, 31),
        'currency': setup['currency'].id,
        'initial_contract_value': Decimal('500000.00'),
        'advance_payment_rate': Decimal('10.00'),
        'advance_recovery_rate': Decimal('10.00'),
        'retention_rate': Decimal('5.00'),
        'retention_cap_amount': Decimal('25000.00'),
        'site_utilities_deduction_rate': Decimal('0.50'),
        'tax_regime': ContractorContract.TaxRegime.TABLE_TAX_5,
        'syndicate_stamp_rate': Decimal('0.450'),
        'is_assigned_to_bank': False,
        'is_garnished_by_court': False,
    }
    form = ContractorContractForm(data=valid_data)
    assert form.is_valid(), form.errors

    # فحص صمام التنازل البنكي (يلزم إدخال اسم البنك ورقم الـ IBAN)
    invalid_bank_data = valid_data.copy()
    invalid_bank_data['is_assigned_to_bank'] = True
    form_bank = ContractorContractForm(data=invalid_bank_data)
    assert not form_bank.is_valid()
    assert "التنازل البنكي" in str(form_bank.non_field_errors())

    # فحص صمام الحجز القضائي (يلزم تسجيل رقم الدعوى والمبلغ)
    invalid_garnished_data = valid_data.copy()
    invalid_garnished_data['is_garnished_by_court'] = True
    form_garnished = ContractorContractForm(data=invalid_garnished_data)
    assert not form_garnished.is_valid()
    assert "الحجز القضائي" in str(form_garnished.non_field_errors())

    # فحص صمام التواريخ (تاريخ النهاية قبل البداية)
    invalid_dates_data = valid_data.copy()
    invalid_dates_data['completion_date'] = date(2026, 1, 15)
    form_dates = ContractorContractForm(data=invalid_dates_data)
    assert not form_dates.is_valid()
    assert "تاريخ نهو الأعمال" in str(form_dates.non_field_errors())


def test_contractor_contract_items_formset_duplicate_code_guard(phase3_setup):
    """التحقق من صمام منع تكرار أكواد البنود في مقايسة العقد"""
    setup = phase3_setup
    contract = setup['contract']

    data = {
        'items-TOTAL_FORMS': '2',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-item_code': 'CONC-01',
        'items-0-description': 'بند أول',
        'items-0-unit': 'م3',
        'items-0-contracted_quantity': '100.000',
        'items-0-unit_rate': '1000.00',
        'items-1-item_code': 'CONC-01',  # كود مكرر
        'items-1-description': 'بند مكرر',
        'items-1-unit': 'م3',
        'items-1-contracted_quantity': '50.000',
        'items-1-unit_rate': '1000.00',
    }
    formset = ContractorContractItemFormSet(data=data, instance=contract)
    assert not formset.is_valid()
    assert "مكرر في مقايسة العقد" in str(formset.non_form_errors())


def test_contractor_certificate_form_validation(phase3_setup):
    """التحقق من نموذج المستخلص وصمام تواريخ الفترة"""
    setup = phase3_setup
    data = {
        'certificate_number': 'CERT-TEST-01',
        'sequence_order': 1,
        'certificate_type': ContractorProgressCertificate.CertificateType.STANDARD_PROGRESS,
        'contract': setup['contract'].id,
        'project': setup['project'].id,
        'contractor': setup['contractor'].id,
        'currency': setup['currency'].id,
        'period_start': date(2026, 3, 31),
        'period_end': date(2026, 3, 1),  # تاريخ النهاية قبل البداية
    }
    form = ContractorProgressCertificateForm(data=data)
    assert not form.is_valid()
    assert "تاريخ نهاية فترة المستخلص" in str(form.non_field_errors())


# =========================================================================
# 2. اختبارات واجهات عقود المقاولين (Contractor Contract Views)
# =========================================================================

def test_contractor_contract_list_view_and_ajax_search(phase3_setup):
    """التحقق من شاشة قائمة العقود واستجابة البحث الحركي AJAX"""
    setup = phase3_setup
    client = setup['client']

    # 1. طلب GET العادي
    url = reverse('real_estate:contractor_contract_list')
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'contracts' in resp.context
    assert resp.context['total_contracts'] >= 1
    assert resp.context['total_contract_value'] >= Decimal('1000000.00')

    # 2. طلب GET عبر AJAX للبحث الفوري
    ajax_resp = client.get(f"{url}?q=SUB-AML&ajax=1", HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert ajax_resp.status_code == 200
    data = ajax_resp.json()
    assert 'table_html' in data
    assert 'pagination_html' in data
    assert 'summary_html' in data
    assert data['total_count'] >= 1


def test_contractor_contract_detail_view(phase3_setup):
    """التحقق من استعراض تفاصيل العقد وبنوده وأوامر التغيير"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    url = reverse('real_estate:contractor_contract_detail', kwargs={'pk': contract.pk})
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context['contract'] == contract
    assert len(resp.context['items']) == 2
    assert 'advance_form' in resp.context
    assert 'vo_form' in resp.context


def test_contractor_contract_disburse_advance_post_action(phase3_setup):
    """التحقق من صرف الدفعة المقدمة عبر الـ View وتوليد القيد المحاسبي"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    url = reverse('real_estate:contractor_contract_disburse_advance', kwargs={'pk': contract.pk})
    post_data = {
        'amount': '100000.00',
        'escrow_account_code': '11121',
        'payment_date': '2026-02-01',
        'reference': 'CHK-ADV-01'
    }
    resp = client.post(url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 200
    json_data = resp.json()
    assert json_data['success'] is True
    contract.refresh_from_db()
    assert contract.advance_payment_disbursed == Decimal('100000.00')


def test_contractor_contract_variation_order_create_post_action(phase3_setup):
    """التحقق من إنشاء أمر تغيير وإعادة المعايرة لمعدل الاسترداد"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    url = reverse('real_estate:contractor_contract_variation_create', kwargs={'pk': contract.pk})
    post_data = {
        'order_number': 'VO-AML-01',
        'variation_type': ContractVariationOrder.VariationType.QUANTITY_INCREASE,
        'description': 'زيادة مكعبات الخرسانة لصب ميدات إضافية',
        'net_value_impact': '200000.00',
        'approved_additional_days': 15,
        'consultant_approval_ref': 'CONS-VO-01',
    }
    resp = client.post(url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 200
    assert resp.json()['success'] is True
    contract.refresh_from_db()
    assert contract.revised_contract_value == Decimal('1200000.00')


def test_api_contractor_contract_items_endpoint(phase3_setup):
    """التحقق من endpoint جلب بنود المقايسة المسعرة لتغذية شاشة المستخلص"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    url = reverse('real_estate:api_contractor_contract_items', kwargs={'contract_id': contract.pk})
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert data['contract_number'] == contract.contract_number
    assert len(data['items']) == 2
    assert data['items'][0]['item_code'] == 'CONC-01'


# =========================================================================
# 3. اختبارات واجهات مستخلصات المقاولين (Contractor Certificate Views)
# =========================================================================

def test_contractor_certificate_list_view_and_ajax_search(phase3_setup):
    """التحقق من شاشة قائمة المستخلصات واستجابة الـ AJAX مع الـ Totals"""
    setup = phase3_setup
    client = setup['client']

    url = reverse('real_estate:contractor_list')
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'certificates' in resp.context

    ajax_resp = client.get(f"{url}?ajax=1", HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert ajax_resp.status_code == 200
    data = ajax_resp.json()
    assert 'table_html' in data
    assert 'pagination_html' in data
    assert 'totals_html' in data


def test_contractor_certificate_create_post_view(phase3_setup):
    """التحقق من إنشاء مستخلص جديد بالبنود والتسلسل عبر الـ View"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    url = reverse('real_estate:contractor_create')
    post_data = {
        'certificate_number': 'CERT-AML-01',
        'sequence_order': 1,
        'certificate_type': ContractorProgressCertificate.CertificateType.STANDARD_PROGRESS,
        'contract': contract.id,
        'project': setup['project'].id,
        'contractor': setup['contractor'].id,
        'currency': setup['currency'].id,
        'period_start': '2026-03-01',
        'period_end': '2026-03-31',
        'gross_certified_work': '200000.00',
        'previous_certified_work': '0.00',
        'materials_on_site': '0.00',
        'retention_rate': '5.00',
        'advance_payment_recovery': '20000.00',
        'wht_rate': '1.00',
        'items-TOTAL_FORMS': '0',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
    }
    resp = client.post(url, data=post_data)
    assert resp.status_code == 302
    cert = ContractorProgressCertificate.objects.get(certificate_number='CERT-AML-01')
    assert cert.status == ContractorProgressCertificate.CertificateStatus.DRAFT
    assert cert.contract == contract
    assert cert.net_amount > Decimal('0.00')


def test_contractor_certificate_submit_and_post_gl_views(phase3_setup):
    """التحقق من دورة تقديم واعتماد وترحيل المستخلص عبر الـ Views"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-AML-SUBMIT",
        sequence_order=1,
        contract=contract,
        project=setup['project'],
        contractor=setup['contractor'],
        currency=setup['currency'],
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        gross_certified_work=Decimal("150000.00"),
        previous_certified_work=Decimal("0.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("15000.00"),
        wht_rate=Decimal("1.00"),
        created_by=setup['user']
    )

    # 1. تقديم للاعتماد
    submit_url = reverse('real_estate:contractor_submit', kwargs={'pk': cert.pk})
    submit_resp = client.post(submit_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert submit_resp.status_code == 200
    assert submit_resp.json()['success'] is True
    cert.refresh_from_db()
    assert cert.status == ContractorProgressCertificate.CertificateStatus.PENDING_APPROVAL
    assert len(cert.approval_snapshot_hash) == 64

    # محاكاة اكتمال دورة الاعتماد المؤسسي
    cert.approval_request.status = 'APPROVED'
    cert.approval_request.save()

    # 2. ترحيل القيد المحاسبي
    post_gl_url = reverse('real_estate:contractor_post_gl', kwargs={'pk': cert.pk})
    post_resp = client.post(post_gl_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert post_resp.status_code == 200
    assert post_resp.json()['success'] is True
    cert.refresh_from_db()
    assert cert.status == ContractorProgressCertificate.CertificateStatus.APPROVED
    assert cert.journal_entry is not None


def test_contractor_certificate_storno_reversal_view(phase3_setup):
    """التحقق من واجهة الإلغاء العكسي المعياري (Storno Reversal)"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-AML-REV",
        sequence_order=1,
        contract=contract,
        project=setup['project'],
        contractor=setup['contractor'],
        currency=setup['currency'],
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        gross_certified_work=Decimal("100000.00"),
        previous_certified_work=Decimal("0.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("10000.00"),
        wht_rate=Decimal("1.00"),
        created_by=setup['user']
    )
    # تقديم وترحيل القيد
    client.post(reverse('real_estate:contractor_submit', kwargs={'pk': cert.pk}))
    cert.refresh_from_db()
    cert.approval_request.status = 'APPROVED'
    cert.approval_request.save()
    client.post(reverse('real_estate:contractor_post_gl', kwargs={'pk': cert.pk}))

    # تنفيذ الاستورنو
    storno_url = reverse('real_estate:contractor_storno_reverse', kwargs={'pk': cert.pk})
    storno_resp = client.post(storno_url, data={'reversal_reason': 'خطأ في حصر كميات الخرسانة'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert storno_resp.status_code == 200
    assert storno_resp.json()['success'] is True
    cert.refresh_from_db()
    assert cert.status == ContractorProgressCertificate.CertificateStatus.CANCELLED
    assert cert.reversal_entry is not None


def test_contractor_certificate_excel_import_view(phase3_setup):
    """التحقق من واجهة استيراد ملف الحصر الهندسي (CSV/Excel)"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-AML-IMPORT",
        sequence_order=1,
        contract=contract,
        project=setup['project'],
        contractor=setup['contractor'],
        currency=setup['currency'],
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        gross_certified_work=Decimal("0.00"),
        previous_certified_work=Decimal("0.00"),
        created_by=setup['user']
    )

    # إنشاء ملف CSV افتراضي
    csv_content = (
        "item_code,description,unit,unit_rate,previous_quantity,current_quantity\n"
        "CONC-01,صب خرسانة مسلحة,م3,1500.00,0.00,100.00\n"
        "BRICK-01,مباني طوب مفرغ,م2,250.00,0.00,200.00\n"
    )
    csv_file = io.BytesIO(csv_content.encode('utf-8-sig'))
    csv_file.name = "survey_sheet.csv"

    url = reverse('real_estate:contractor_import_excel', kwargs={'pk': cert.pk})
    resp = client.post(url, data={'file': csv_file, 'replace_existing_items': 'on'})
    assert resp.status_code == 302
    cert.refresh_from_db()
    assert cert.items.count() == 2
    # 100 * 1500 + 200 * 250 = 150,000 + 50,000 = 200,000
    assert cert.current_period_work == Decimal("200000.00")
    assert cert.gross_certified_work == Decimal("200000.00")


def test_contractor_certificate_print_view_http200(phase3_setup):
    """التحقق من استجابة شاشة الطباعة الهندسية الرسمية"""
    setup = phase3_setup
    client = setup['client']
    contract = setup['contract']

    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-PRINT-01",
        sequence_order=1,
        contract=contract,
        project=setup['project'],
        contractor=setup['contractor'],
        currency=setup['currency'],
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        gross_certified_work=Decimal("50000.00"),
        previous_certified_work=Decimal("0.00"),
        created_by=setup['user']
    )

    url = reverse('real_estate:contractor_print', kwargs={'pk': cert.pk})
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context['cert'] == cert
    assert 'company_name' in resp.context
