# -*- coding: utf-8 -*-
"""
Tests for Wave 2 - Phase 6:
Contractor Progress Certificate Calculations, Enterprise Approval Rule Integration,
Multi-Level Approver Role Verification, Cryptographic Financial Mutation Lock,
Hard Payment Guard, and Accounting Gateway Accrual Posting.
"""
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from real_estate.models import (
    RealEstateProject,
    ContractorProgressCertificate,
)
from real_estate.services.contractor_service import (
    ContractorProgressService,
    MissingApprovalRuleError,
    MutationTamperError
)
from supplier.models import Supplier
from users.models import Role
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.approval import EnterpriseApprovalRule, EnterpriseApprovalRequest
from financial.services.approval_service import ApprovalService
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.fixture
def phase6_setup(db):
    user_admin = User.objects.create_superuser(
        username="admin_p6",
        email="admin_p6@example.com",
        password="password123"
    )

    # الأدوار الوظيفية
    role_engineer = Role.objects.create(name="site_engineer", display_name="مهندس الموقع")
    role_pm = Role.objects.create(name="project_manager", display_name="مدير المشروع")
    role_other = Role.objects.create(name="sales_agent", display_name="مسؤول مبيعات")

    user_engineer = User.objects.create_user(
        username="eng_karim",
        email="karim@example.com",
        password="password123",
        role=role_engineer
    )
    user_pm = User.objects.create_user(
        username="pm_hassan",
        email="hassan@example.com",
        password="password123",
        role=role_pm
    )
    user_unauthorized = User.objects.create_user(
        username="unauth_user",
        email="unauth@example.com",
        password="password123",
        role=role_other
    )

    # 1. شجرة الحسابات والعملات
    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )
    egp_currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )

    wip_account, _ = ChartOfAccounts.objects.get_or_create(
        code="12101",
        defaults={'name': "مشروعات تحت التنفيذ - عقارات", 'account_type': asset_type, 'is_active': True, 'is_leaf': True}
    )
    retention_account, _ = ChartOfAccounts.objects.get_or_create(
        code="21310",
        defaults={'name': "تأمين حسن تنفيذ مقاولي الباطن", 'account_type': liability_type, 'is_active': True, 'is_leaf': True}
    )
    payable_account, _ = ChartOfAccounts.objects.get_or_create(
        code="21110",
        defaults={'name': "مستحقات الموردين والمقاولين", 'account_type': liability_type, 'is_active': True, 'is_leaf': True}
    )
    wht_account, _ = ChartOfAccounts.objects.get_or_create(
        code="21330",
        defaults={'name': "ضريبة الخصم والإضافة", 'account_type': liability_type, 'is_active': True, 'is_leaf': True}
    )
    advance_account, _ = ChartOfAccounts.objects.get_or_create(
        code="11350",
        defaults={'name': "دفعات مقدمة لمقاولي الباطن", 'account_type': asset_type, 'is_active': True, 'is_leaf': True}
    )

    # 2. المشروع والمقاول
    project = RealEstateProject.objects.create(
        name="برج الصفا الإنشائي",
        code="PRJ-P6-BLD",
        project_type=RealEstateProject.ProjectType.COMMERCIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timezone.timedelta(days=365),
        created_by=user_admin
    )

    contractor = Supplier.objects.create(
        name="شركة الأهرام للهندسة والمقاولات",
        code="CON-001",
        entity_type="company",
        tax_number="TX-998877"
    )

    certificate = ContractorProgressCertificate.objects.create(
        certificate_number="PRG-2026-001",
        project=project,
        contractor=contractor,
        contract_reference="SUB-CNT-2026/01",
        period_start=timezone.localdate() - timezone.timedelta(days=30),
        period_end=timezone.localdate(),
        gross_certified_work=Decimal("500000.00"),
        previous_certified_work=Decimal("100000.00"),
        materials_on_site=Decimal("50000.00"),
        retention_rate=Decimal("5.00"),
        advance_payment_recovery=Decimal("40000.00"),
        wht_rate=Decimal("1.00"),
        penalty_deductions=Decimal("3500.00"),
        currency=egp_currency,
        created_by=user_admin
    )

    for acc in [wip_account, retention_account, payable_account, wht_account, advance_account]:
        acc.is_active = True
        acc.is_leaf = True
        acc.children.all().delete()
        acc.save()

    return {
        "user_admin": user_admin,
        "user_engineer": user_engineer,
        "user_pm": user_pm,
        "user_unauthorized": user_unauthorized,
        "project": project,
        "contractor": contractor,
        "certificate": certificate,
        "egp_currency": egp_currency,
        "accounts": {
            "wip": wip_account,
            "retention": retention_account,
            "payable": payable_account,
            "wht": wht_account,
            "advance": advance_account
        }
    }


@pytest.mark.django_db
def test_contractor_progress_certificate_deterministic_calculations(phase6_setup):
    """
    اختبار حسابات المستخلص المعيارية:
    current_period_work = 500,000 - 100,000 = 400,000
    base_for_retention = 400,000 + 50,000 = 450,000
    retention_amount (5%) = 22,500
    wht_amount (1%) = 4,000
    net_amount = 400,000 + 50,000 - 22,500 - 40,000 - 4,000 - 3,500 = 380,000
    """
    cert = phase6_setup["certificate"]
    cert.compute_amounts()
    cert.save()

    assert cert.current_period_work == Decimal("400000.00")
    assert cert.retention_amount == Decimal("22500.00")
    assert cert.wht_amount == Decimal("4000.00")
    assert cert.net_amount == Decimal("380000.00")


@pytest.mark.django_db
def test_submit_for_approval_missing_rule_fallback(phase6_setup):
    """
    اختبار الفشل الصريح عند غياب قاعدة اعتماد مطابقة في EnterpriseApprovalRule
    """
    cert = phase6_setup["certificate"]
    user = phase6_setup["user_admin"]

    # التأكد من عدم وجود قواعد مسبقة لموديول REAL_ESTATE
    EnterpriseApprovalRule.objects.filter(module='REAL_ESTATE').delete()

    with pytest.raises(MissingApprovalRuleError) as exc:
        ContractorProgressService.submit_certificate_for_approval(cert, user=user)

    assert "لا توجد قاعدة اعتماد مالي مطابقة لمستخلص المقاول" in str(exc.value)


@pytest.mark.django_db
def test_submit_for_approval_creates_request_and_audit_hash(phase6_setup):
    """
    اختبار تقديم المستخلص للاعتماد المؤسسي وتثبيت البصمة الرقمية المشفرة
    """
    cert = phase6_setup["certificate"]
    user = phase6_setup["user_admin"]

    # إنشاء قاعدة اعتماد للمستخلصات
    EnterpriseApprovalRule.objects.create(
        module='REAL_ESTATE',
        rule_name="اعتماد مستخلصات حتى 500 ألف",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("500000.00"),
        approver_role="site_engineer",
        approval_level=1,
        is_active=True
    )

    submitted_cert = ContractorProgressService.submit_certificate_for_approval(cert, user=user)

    assert submitted_cert.status == ContractorProgressCertificate.CertificateStatus.PENDING_APPROVAL
    assert submitted_cert.approval_request is not None
    assert submitted_cert.approval_request.status == "PENDING"
    assert submitted_cert.approval_snapshot_hash != ""
    assert submitted_cert.approval_snapshot_hash == submitted_cert.compute_financial_hash()


@pytest.mark.django_db
def test_multi_level_approver_role_enforcement(phase6_setup):
    """
    اختبار التحقق الصارم من دور المعتمد (Approver Role Verification):
    - الخطوة 1 تتطلب site_engineer
    - الخطوة 2 تتطلب project_manager
    أي مستخدم لا يحمل الدور المحدد يُرفض اعتماده بـ FinancialCoreError
    """
    cert = phase6_setup["certificate"]
    user_admin = phase6_setup["user_admin"]
    user_eng = phase6_setup["user_engineer"]
    user_pm = phase6_setup["user_pm"]
    user_unauth = phase6_setup["user_unauthorized"]

    # إنشاء قاعدتين لمستويين متتابعين
    EnterpriseApprovalRule.objects.create(
        module='REAL_ESTATE',
        rule_name="المستوى الأول: مهندس الموقع",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("1000000.00"),
        approver_role="site_engineer",
        approval_level=1,
        is_active=True
    )
    EnterpriseApprovalRule.objects.create(
        module='REAL_ESTATE',
        rule_name="المستوى الثاني: مدير المشروع",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("1000000.00"),
        approver_role="project_manager",
        approval_level=2,
        is_active=True
    )

    cert = ContractorProgressService.submit_certificate_for_approval(cert, user=user_admin)
    req = cert.approval_request
    assert req.steps.count() == 2

    # 1. محاولة اعتماد الخطوة 1 بواسطة مستخدم غير مخول (sales_agent)
    with pytest.raises(FinancialCoreError) as exc:
        ApprovalService.approve_request(req.id, user=user_unauth, comments="محاولة اعتماد غير مصرح بها")
    assert "لا يحمل الدور المطلوب 'site_engineer'" in str(exc.value)

    # 2. اعتماد الخطوة 1 بنجاح بواسطة مهندس الموقع
    ApprovalService.approve_request(req.id, user=user_eng, comments="تمت مراجعة الكميات والأعمال المنفذة بالموقع")
    req.refresh_from_db()
    assert req.status == "PENDING"  # ما زال معلقاً لوجود الخطوة 2

    step1 = req.steps.get(sequence=1)
    assert step1.status == "APPROVED"
    assert step1.action_by == user_eng

    # 3. محاولة اعتماد الخطوة 2 بواسطة مهندس الموقع مجدداً (ليس project_manager)
    with pytest.raises(FinancialCoreError) as exc2:
        ApprovalService.approve_request(req.id, user=user_eng, comments="محاولة اعتماد خطوة الإدارة")
    assert "لا يحمل الدور المطلوب 'project_manager'" in str(exc2.value)

    # 4. اعتماد الخطوة 2 بنجاح بواسطة مدير المشروع
    ApprovalService.approve_request(req.id, user=user_pm, comments="معتمد نهائياً للصرف")
    req.refresh_from_db()
    assert req.status == "APPROVED"
    assert req.approved_by == user_pm


@pytest.mark.django_db
def test_cryptographic_financial_mutation_tamper_detection(phase6_setup):
    """
    اختبار القفل التشفيري ضد التلاعب (Cryptographic Financial Mutation Lock):
    إذا تم تعديل مبالغ المستخلص بعد اعتماده، يتم إلغاء الاعتماد فوراً وتوجيه إنذار أمني
    """
    cert = phase6_setup["certificate"]
    user_admin = phase6_setup["user_admin"]
    user_eng = phase6_setup["user_engineer"]

    EnterpriseApprovalRule.objects.create(
        module='REAL_ESTATE',
        rule_name="اعتماد مستخلصات",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("1000000.00"),
        approver_role="site_engineer",
        approval_level=1,
        is_active=True
    )

    cert = ContractorProgressService.submit_certificate_for_approval(cert, user=user_admin)
    ApprovalService.approve_request(cert.approval_request.id, user=user_eng, comments="معتمد")
    cert.approval_request.refresh_from_db()
    assert cert.approval_request.status == "APPROVED"

    # تلاعب مالي: محاولة زيادة صافي المبلغ بعد الاعتماد
    cert.materials_on_site = Decimal("150000.00")  # زيادة 100 ألف
    cert.compute_amounts()
    cert.save()

    # محاولة إصدار القيد المحاسبي ستكشف كسر البصمة التشفيرية
    with pytest.raises(MutationTamperError) as exc:
        ContractorProgressService.verify_and_post_certificate(cert, user=user_admin)

    assert "تم اكتشاف تعديل في الأرقام المالية للمستخلص بعد الاعتماد" in str(exc.value)

    cert.refresh_from_db()
    assert cert.status == ContractorProgressCertificate.CertificateStatus.DRAFT
    assert cert.approval_request.status == "CANCELLED"


@pytest.mark.django_db
def test_hard_payment_guard_blocks_unapproved_posting(phase6_setup):
    """
    اختبار الحارس المالي الصارم: حظر إصدار القيد المحاسبي لمستخلص غير معتمد
    """
    cert = phase6_setup["certificate"]
    user_admin = phase6_setup["user_admin"]

    # المستخلص في حالة DRAFT
    with pytest.raises(ValidationError) as exc:
        ContractorProgressService.verify_and_post_certificate(cert, user=user_admin)

    assert "المستخلص لم يستوفِ دورة الاعتمادات المالية المطلوبة" in str(exc.value)


@pytest.mark.django_db
def test_verified_posting_generates_balanced_journal_entry(phase6_setup):
    """
    اختبار الترحيل المالي المحوكم بعد استيفاء الاعتمادات:
    Dr: WIP Construction Cost (12101) [450,000]
    Cr: Retentions Payable (21310) [22,500]
    Cr: Advance Recovery (11350) [40,000]
    Cr: WHT Payable (21330) [4,000]
    Cr: Supplier Payable (21110) [380,000 + 3,500 penalty = 383,500]
    """
    cert = phase6_setup["certificate"]
    user_admin = phase6_setup["user_admin"]
    user_eng = phase6_setup["user_engineer"]

    # إزالة الغرامات لتبسيط مطابقة القيد المالي المباشر
    cert.penalty_deductions = Decimal("0.00")
    cert.compute_amounts()
    cert.save()

    EnterpriseApprovalRule.objects.create(
        module='REAL_ESTATE',
        rule_name="اعتماد مستخلصات",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("1000000.00"),
        approver_role="site_engineer",
        approval_level=1,
        is_active=True
    )

    cert = ContractorProgressService.submit_certificate_for_approval(cert, user=user_admin)
    ApprovalService.approve_request(cert.approval_request.id, user=user_eng, comments="معتمد نهائياً")

    journal_entry = ContractorProgressService.verify_and_post_certificate(cert, user=user_admin)

    assert journal_entry is not None
    assert journal_entry.status.lower() == 'posted'
    cert.refresh_from_db()
    assert cert.status == ContractorProgressCertificate.CertificateStatus.APPROVED
    assert cert.journal_entry == journal_entry

    lines = list(journal_entry.lines.all())
    total_debit = sum(l.debit for l in lines)
    total_credit = sum(l.credit for l in lines)

    # القيد متوازن تماماً
    assert total_debit == total_credit
    assert total_debit == Decimal("450000.00")

    # فحص تفاصيل الحسابات
    wip_line = [l for l in lines if l.account.code == "12101"][0]
    retention_line = [l for l in lines if l.account.code == "21310"][0]
    advance_line = [l for l in lines if l.account.code == "11350"][0]
    wht_line = [l for l in lines if l.account.code == "21330"][0]
    payable_line = [l for l in lines if l.account.code == "21110"][0]

    assert wip_line.debit == Decimal("450000.00")
    assert retention_line.credit == Decimal("22500.00")
    assert advance_line.credit == Decimal("40000.00")
    assert wht_line.credit == Decimal("4000.00")
    assert payable_line.credit == Decimal("383500.00")
