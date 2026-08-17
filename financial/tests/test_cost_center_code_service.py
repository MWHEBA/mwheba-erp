# -*- coding: utf-8 -*-
import pytest
from django.urls import reverse
from django.core.exceptions import ValidationError
from financial.models import CostCenter, JournalEntry, JournalEntryLine, ChartOfAccounts, AccountType
from financial.services.cost_center_code_service import CostCenterCodeService


@pytest.mark.django_db
class TestCostCenterCodeService:

    def test_root_code_generation_sequential(self):
        """اختبار توليد أكواد المراكز الرئيسية بالعشرات 10, 20, 30"""
        cc1 = CostCenter.objects.create(name="المركز الرئيسي 1")
        assert cc1.code == "10"

        cc2 = CostCenter.objects.create(name="المركز الرئيسي 2")
        assert cc2.code == "20"

        cc3 = CostCenter.objects.create(name="المركز الرئيسي 3")
        assert cc3.code == "30"

    def test_child_code_generation_under_numeric_parent(self):
        """اختبار توليد كود الأبناء تحت مركز رئيسي رقمي 10 -> 1001, 1002"""
        parent = CostCenter.objects.create(name="قطاع المشروعات")  # code = 10
        assert parent.code == "10"

        child1 = CostCenter.objects.create(name="مشروع القاهرة", parent=parent)
        assert child1.code == "1001"

        child2 = CostCenter.objects.create(name="مشروع الإسكندرية", parent=parent)
        assert child2.code == "1002"

        # حفيد من المستوى الثالث
        grandchild = CostCenter.objects.create(name="موقع التجمع", parent=child1)
        assert grandchild.code == "100101"

    def test_child_code_generation_under_alphanumeric_parent(self):
        """اختبار توليد كود الأبناء تحت مركز ذي كود نصي أو بادئة"""
        parent = CostCenter.objects.create(code="CC-HQ", name="المقر العام")

        child1 = CostCenter.objects.create(name="قسم الموارد البشرية", parent=parent)
        assert child1.code == "CC-HQ-01"

        child2 = CostCenter.objects.create(name="قسم تكنولوجيا المعلومات", parent=parent)
        assert child2.code == "CC-HQ-02"

    def test_sanitize_code_behavior(self):
        """اختبار تنظيف وتوحيد الأحرف والمسافات في الكود"""
        assert CostCenterCodeService.sanitize_code("  cc-test-01  ") == "CC-TEST-01"
        assert CostCenterCodeService.sanitize_code(None) == ""

        # عند الإنشاء مع مسافات
        cc = CostCenter.objects.create(code="  1050  ", name="مركز مخصص")
        assert cc.code == "1050"

    def test_suggest_cost_center_code_api(self, client, admin_user):
        """اختبار استدعاء الـ API لاقتراح الكود"""
        client.force_login(admin_user)
        root = CostCenter.objects.create(name="مركز رئيسي")  # 10

        # بدون parent_id -> كود رئيسي تالٍ (20)
        url = reverse('financial:cost_center_suggest_code')
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['suggested_code'] == "20"

        # مع parent_id -> كود ابن تالٍ (1001)
        response_child = client.get(f"{url}?parent_id={root.id}")
        assert response_child.status_code == 200
        data_child = response_child.json()
        assert data_child['success'] is True
        assert data_child['suggested_code'] == "1001"

    def test_code_immutability_guard_with_posted_transactions(self):
        """اختبار حظر تعديل كود مركز التكلفة لو كان مرتبطاً بقيود مرحلة"""
        cc = CostCenter.objects.create(name="مركز العمليات")  # 10

        # إنشاء قيد مرحل مرتبط بمركز التكلفة
        acc_type, _ = AccountType.objects.get_or_create(
            code="EXP",
            defaults={"name": "مصروفات", "category": "expense", "nature": "debit"}
        )
        account, _ = ChartOfAccounts.objects.get_or_create(
            code="50001",
            defaults={"name": "مصروفات عمومية", "account_type": acc_type}
        )

        je = JournalEntry.objects.create(
            number="JV-TEST-001",
            status="posted",
            entry_type="manual"
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=account,
            cost_center=cc,
            debit=100.00,
            credit=0.00
        )

        # محاولة تعديل الكود
        cc.code = "9999"
        with pytest.raises(ValidationError) as excinfo:
            cc.clean()
        assert "لا يمكن تعديل كود مركز التكلفة" in str(excinfo.value)
