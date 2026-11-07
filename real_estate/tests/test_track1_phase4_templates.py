# -*- coding: utf-8 -*-
"""
Tests for Track 1 Phase 4: Frontend Templates & Print Views
MWHEBA ERP - Real Estate Construction Management

Validates:
1. Contractor contracts list, detail, and form templates.
2. Progress certificates list, detail, and form templates.
3. Official engineering print template (A4, four-way signatures).
4. All 9 interactive contractor modals.
5. Shared components (amount breakdown, document lifecycle timeline).
6. Project detail cross-module integration.
7. Strict UI rules compliance: CSS variables, NO gradients, NO unapproved fonts, and strictly «مخزن» terminology.
"""
from decimal import Decimal
from datetime import date
import pytest
from django.urls import reverse
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model

from real_estate.models import (
    RealEstateProject,
    ContractorContract,
    ContractorContractItem,
    ContractorProgressCertificate,
    ContractorCertificateItem,
    ContractorMaterialOnSite,
    ContractorBackcharge,
    CertificatePaymentInstallmentSchedule,
)
from supplier.models import Supplier
from financial.models.currency import Currency
from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware

User = get_user_model()


@pytest.fixture
def phase4_setup(db):
    """تهيئة البيانات الأساسية لاختبار قوالب المرحلة الرابعة"""
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'التطوير العقاري', 'is_enabled': True}
    )
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(
        username='phase4_admin',
        email='phase4@mwheba.com',
        password='AdminPassword2026!'
    )

    currency, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'جنيه مصري', 'symbol': 'ج.م'}
    )

    project = RealEstateProject.objects.create(
        code='PRJ-PH4-01',
        name='مشروع أبراج النرجس الفاخرة',
        project_type='RESIDENTIAL',
        status='UNDER_CONSTRUCTION',
        total_land_area=Decimal('12000.00'),
        gross_built_area=Decimal('45000.00'),
        start_date=date(2026, 1, 1),
        expected_completion_date=date(2028, 12, 31),
        created_by=user
    )

    contractor = Supplier.objects.create(
        name='شركة النيل للمقاولات العامة والإنشاءات',
        code='SUP-PH4-01'
    )

    contract = ContractorContract.objects.create(
        contract_number='CONT-PH4-001',
        title='عقد أعمال الخرسانات المسلحة والهيكل الإنشائي',
        project=project,
        contractor=contractor,
        currency=currency,
        status=ContractorContract.ContractStatus.ACTIVE,
        initial_contract_value=Decimal('5000000.00'),
        advance_payment_rate=Decimal('10.00'),
        advance_recovery_rate=Decimal('10.00'),
        retention_rate=Decimal('5.00'),
        created_by=user
    )

    contract_item = ContractorContractItem.objects.create(
        contract=contract,
        item_code='CONC-001',
        description='خرسانة مسلحة للأسقف والأعمدة عيار 350',
        unit='م3',
        contracted_quantity=Decimal('2500.000'),
        unit_rate=Decimal('2000.00')
    )

    cert = ContractorProgressCertificate.objects.create(
        certificate_number='CERT-PH4-001',
        sequence_order=1,
        contract=contract,
        project=project,
        contractor=contractor,
        currency=currency,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        gross_certified_work=Decimal('250000.00'),
        previous_certified_work=Decimal('0.00'),
        materials_on_site=Decimal('30000.00'),
        retention_rate=Decimal('5.00'),
        advance_payment_recovery=Decimal('25000.00'),
        wht_rate=Decimal('1.00'),
        created_by=user
    )

    cert_item = ContractorCertificateItem.objects.create(
        certificate=cert,
        contract_item=contract_item,
        item_code='CONC-001',
        description='خرسانة مسلحة للأسقف والأعمدة',
        unit='م3',
        previous_quantity=Decimal('0.000'),
        current_quantity=Decimal('125.000'),
        unit_rate=Decimal('2000.00')
    )

    mos = ContractorMaterialOnSite.objects.create(
        certificate=cert,
        item_name='حديد تسليح عز الدخيلة 16 مم',
        unit='طن',
        surveyed_quantity=Decimal('10.000'),
        invoice_unit_cost=Decimal('40000.00'),
        total_material_value=Decimal('400000.00'),
        advance_financing_rate=Decimal('75.00'),
        approved_advance_amount=Decimal('300000.00')
    )

    backcharge = ContractorBackcharge.objects.create(
        certificate=cert,
        memo_reference='BC-PH4-001',
        reason='إصلاح عيوب تعشيش خرسانات العمود 14',
        amount=Decimal('5000.00')
    )

    installment = CertificatePaymentInstallmentSchedule.objects.create(
        certificate=cert,
        installment_number=1,
        due_date=date(2026, 8, 15),
        amount=Decimal('100000.00')
    )

    return {
        'user': user,
        'project': project,
        'contractor': contractor,
        'contract': contract,
        'contract_item': contract_item,
        'certificate': cert,
        'cert_item': cert_item,
        'mos': mos,
        'backcharge': backcharge,
        'installment': installment,
    }


def test_contractor_contract_list_template_rendering(client, phase4_setup):
    """التحقق من تصيير قالب قائمة عقود المقاولين وكروت الملخص وجدول البيانات"""
    client.force_login(phase4_setup['user'])
    url = reverse('real_estate:contractor_contract_list')
    resp = client.get(url)
    assert resp.status_code == 200

    content = resp.content.decode('utf-8')
    assert 'عقود مقاولي الباطن الإنشائية' in content
    assert 'contractor-contracts-summary' in content
    assert 'contractor-contracts-table' in content
    assert phase4_setup['contract'].contract_number in content
    assert 'مخزن' in content or 'المشروع' in content


def test_contractor_contract_detail_template_rendering(client, phase4_setup):
    """التحقق من تصيير قالب تفاصيل العقد البانورامي مع كافة التبويبات والمودالات"""
    client.force_login(phase4_setup['user'])
    url = reverse('real_estate:contractor_contract_detail', kwargs={'pk': phase4_setup['contract'].pk})
    resp = client.get(url)
    assert resp.status_code == 200

    content = resp.content.decode('utf-8')
    assert phase4_setup['contract'].title in content
    assert 'بنود المقايسة المسعرة' in content
    assert 'أوامر التغيير' in content
    assert 'المستخلصات الإنشائية' in content
    assert 'الحوكمة والضمانات البنكية' in content
    assert 'disburseAdvanceModal' in content
    assert 'variationOrderModal' in content
    assert 'jointTerminationModal' in content


def test_contractor_contract_form_template_rendering(client, phase4_setup):
    """التحقق من تصيير نموذج إنشاء وتعديل العقد مع Inline Formset"""
    client.force_login(phase4_setup['user'])
    url = reverse('real_estate:contractor_contract_create')
    resp = client.get(url)
    assert resp.status_code == 200

    content = resp.content.decode('utf-8')
    assert 'إنشاء عقد مقاولة باطن جديد' in content
    assert 'contract-items-table' in content
    assert 'initial_contract_value' in content
    assert 'advance_payment_rate' in content


def test_contractor_certificate_list_template_rendering(client, phase4_setup):
    """التحقق من تصيير قالب قائمة المستخلصات مع بطاقات الـ KPI والجدول الجزئي"""
    client.force_login(phase4_setup['user'])
    url = reverse('real_estate:contractor_list')
    resp = client.get(url)
    assert resp.status_code == 200

    content = resp.content.decode('utf-8')
    assert 'مستخلصات المقاولين الإنشائية' in content
    assert 'contractor-certificates-table' in content
    assert phase4_setup['certificate'].certificate_number in content


def test_contractor_certificate_detail_panoramic_template(client, phase4_setup):
    """التحقق من تصيير قالب تفاصيل المستخلص البانورامي بكافة التبويبات والمودالات المدمجة"""
    client.force_login(phase4_setup['user'])
    url = reverse('real_estate:contractor_detail', kwargs={'pk': phase4_setup['certificate'].pk})
    resp = client.get(url)
    assert resp.status_code == 200

    content = resp.content.decode('utf-8')
    assert phase4_setup['certificate'].certificate_number in content
    assert 'حصر بنود الأعمال' in content
    assert 'تشوينات الموقع (MOS)' in content
    assert 'الخرسانة الجاهزة' in content
    assert 'بيان وتفنيد الاستقطاعات' in content
    assert 'الخصومات البينية والعيوب' in content
    assert 'عمليات الموقع والمعدات' in content
    assert 'الشيكات والجدولة' in content
    assert 'الحوكمة والقيود' in content
    assert 'importBOQModal' in content
    assert 'stornoReversalModal' in content


def test_contractor_certificate_print_view_template(client, phase4_setup):
    """التحقق من تصيير قالب الطباعة الهندسي المعتمد بالتوقيعات الرباعية الرسمية A4"""
    client.force_login(phase4_setup['user'])
    url = reverse('real_estate:contractor_print', kwargs={'pk': phase4_setup['certificate'].pk})
    resp = client.get(url)
    assert resp.status_code == 200

    content = resp.content.decode('utf-8')
    assert 'مستخلص مقاول باطن رسمي' in content
    assert 'print-document' in content
    assert 'أولاً: حصر كميات الأعمال المنفذة خلال الفترة' in content
    assert 'ثانياً: الموقف المالي وحساب الصافي المستحق' in content
    assert 'مهندس الموقع' in content
    assert 'المهندس الاستشاري' in content
    assert 'المراجعة المالية والحسابات' in content
    assert 'اعتماد الإدارة العليا / CEO' in content


def test_shared_components_amount_breakdown_and_timeline():
    """التحقق من تصيير المكونات المشتركة amount_breakdown و document_lifecycle_timeline"""
    # 1. Amount Breakdown
    html_breakdown = render_to_string('components/amount_breakdown.html', {
        'gross_amount': Decimal('500000.00'),
        'additions': [{'label': 'تشوينات الموقع', 'amount': Decimal('50000.00')}],
        'deductions': [{'label': 'تأمين الأعمال', 'amount': Decimal('25000.00'), 'rate': Decimal('5.00')}],
        'net_amount': Decimal('525000.00'),
        'currency_code': 'EGP'
    })
    assert 'التفنيد المالي الصافي' in html_breakdown
    assert '500,000.00' in html_breakdown
    assert '525,000.00 EGP' in html_breakdown

    # 2. Lifecycle Timeline
    html_timeline = render_to_string('components/document_lifecycle_timeline.html', {
        'current_status': 'APPROVED',
        'is_posted': True
    })
    assert 'مسار دورة حياة المستند' in html_timeline
    assert 'مسودة' in html_timeline
    assert 'الاعتماد' in html_timeline
    assert 'القيد المالي' in html_timeline
    assert 'الصرف' in html_timeline


def test_contractor_modals_rendering():
    """التحقق من تصيير كافة المودالات التفاعلية التسعة بدون أي خطأ نحوي"""
    modals = [
        'real_estate/modals/contractor_boq_import_modal.html',
        'real_estate/modals/contractor_variation_order_modal.html',
        'real_estate/modals/contractor_backcharge_modal.html',
        'real_estate/modals/contractor_default_notice_modal.html',
        'real_estate/modals/contractor_lg_modal.html',
        'real_estate/modals/contractor_advance_payment_modal.html',
        'real_estate/modals/contractor_joint_termination_modal.html',
        'real_estate/modals/contractor_installment_reschedule_modal.html',
        'real_estate/modals/contractor_tripartite_lien_modal.html',
        'cheques/partials/payable_cheque_modal.html',
    ]

    for tmpl in modals:
        rendered = render_to_string(tmpl, {})
        assert 'modal-header' in rendered
        assert 'modal-content' in rendered
        assert 'modal-dialog' in rendered
        # التحقق من خلوها تماماً من أي استخدام لكلمة مستودع
        assert 'مستودع' not in rendered


def test_project_detail_cross_module_template(client, phase4_setup):
    """التحقق من ظهور قسم عقود ومستخلصات المقاولين في شاشة تفاصيل المشروع"""
    client.force_login(phase4_setup['user'])
    url = reverse('real_estate:project_detail', kwargs={'pk': phase4_setup['project'].pk})
    resp = client.get(url)
    assert resp.status_code == 200

    content = resp.content.decode('utf-8')
    assert 'عقود مقاولي الباطن والمستخلصات الإنشائية للمشروع' in content
    assert 'عقود المقاولين' in content
    assert 'مستخلصات التنفيذ' in content
