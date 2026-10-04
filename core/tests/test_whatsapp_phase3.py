# -*- coding: utf-8 -*-
"""
اختبارات شاملة للمرحلة الثالثة من منظومة WhatsApp Business Cloud API
MWHEBA ERP — WhatsApp Phase 3 Pytest Suite (HR, Payroll, Security, Governance & FX/Bank Dispatcher)
"""
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import reverse

from core.models import SystemSetting, WhatsAppMessageLog
from core.services.whatsapp_service import WhatsAppService
from core.services.document_dispatcher import DocumentDispatcher
from core.views.whatsapp_views import (
    whatsapp_prepare_send,
    whatsapp_send_document,
    whatsapp_document_status,
    whatsapp_partner_logs
)
from customer.models import Customer
from supplier.models import Supplier
from hr.models.employee import Employee
from hr.models.organization import Department, JobTitle
from hr.models.contract import Contract
from hr.models.payroll import Payroll
from hr.models.leave import Leave, LeaveType
from hr.models.permission import PermissionRequest, PermissionType
from hr.models.penalty_reward import PenaltyReward
from hr.models.employee_asset_custody import EmployeeAssetCustody
from financial.models.custody import EmployeeCustodyAdvance
from financial.models import ChartOfAccounts, Currency

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase3Dispatcher:
    """اختبارات موزع المستندات الموحد للرواتب والموارد البشرية والأمان والحوكمة"""

    def setup_method(self):
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestTokenPhase3", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "1000123456789", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="company_name",
            defaults={"value": "شركة موهبة للطباعة والتوريدات", "data_type": "string", "group": "general", "is_active": True}
        )

        from django.core.cache import cache
        cache.clear()
        WhatsAppService.reset_session()

        self.user = User.objects.create_user(username="test_hr_user", password="password123")
        self.dept = Department.objects.create(name_ar="إدارة تكنولوجيا المعلومات", code="IT-01")
        self.job = JobTitle.objects.create(code="JOB-01", title_ar="مهندس برمجيات", department=self.dept)
        self.employee = Employee.objects.create(
            name="أحمد محمود السيد",
            employee_number="EMP-0101",
            national_id="29001011234567",
            birth_date="1990-01-01",
            hire_date=timezone.now().date(),
            gender="male",
            marital_status="married",
            department=self.dept,
            job_title=self.job,
            mobile_phone="01099887766",
            user=self.user,
            created_by=self.user
        )

        self.contract = Contract.objects.create(
            employee=self.employee,
            contract_number="CNT-2026-001",
            contract_type="permanent",
            start_date=timezone.now().date(),
            basic_salary=Decimal("15000.00"),
            status="active",
            created_by=self.user
        )

    def test_payroll_dispatcher_info_and_pdf(self):
        """التحقق من قسيمة راتب الموظف الشهرية وتوليد الـ PDF"""
        payroll = Payroll.objects.create(
            employee=self.employee,
            contract=self.contract,
            month=timezone.now().date().replace(day=1),
            basic_salary=Decimal("15000.00"),
            allowances=Decimal("3000.00"),
            gross_salary=Decimal("18000.00"),
            net_salary=Decimal("16500.00"),
            status="approved",
            processed_by=self.user
        )

        info = DocumentDispatcher.get_document_info(payroll)
        assert info["doc_title"] == "قسيمة راتب"
        assert f"#{payroll.pk}" in info["doc_number"]
        assert info["partner"] == self.employee
        assert info["partner_type"] == "user"
        assert info["has_pdf"] is True
        assert "16,500.00" in info["financial_summary"]
        assert info["template_name"] == "document_send_ar"

        pdf_bytes, filename = DocumentDispatcher.render_document_pdf_bytes(payroll)
        assert pdf_bytes is not None
        assert filename.startswith("Payslip_")

    def test_employee_advance_dispatcher_info(self):
        """التحقق من سند سلفة / عهدة الموظف المالية"""
        from financial.models.chart_of_accounts import AccountType
        currency = Currency.objects.create(name="جنيه مصري", code="EGP", symbol="ج.م", is_functional=True)
        acc_type, _ = AccountType.objects.get_or_create(code="AST", defaults={"name": "أصول", "category": "asset", "nature": "debit"})
        acc = ChartOfAccounts.objects.create(name="عهد الموظفين", code="1205001", account_type=acc_type, currency=currency)
        
        adv = EmployeeCustodyAdvance.objects.create(
            employee=self.employee,
            user=self.user,
            source_treasury=acc,
            currency=currency,
            advance_number="ADV-2026-050",
            amount=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            purpose="سلفة نقدية طارئة"
        )

        info = DocumentDispatcher.get_document_info(adv)
        assert info["doc_title"] == "سند سلفة / عهدة مالية"
        assert info["doc_number"] == "ADV-2026-050"
        assert info["has_pdf"] is False
        assert info["template_name"] == "payment_receipt_ar"
        assert "5,000.00" in info["financial_summary"]

    def test_leave_request_dispatcher_info(self):
        """التحقق من إشعار الموافقة على طلب الإجازة"""
        ltype = LeaveType.objects.create(name_ar="إجازة اعتيادية", code="ANNUAL", max_days_per_year=21)
        leave = Leave.objects.create(
            employee=self.employee,
            leave_type=ltype,
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            days_count=4,
            reason="ظروف عائلية",
            status="approved"
        )

        info = DocumentDispatcher.get_document_info(leave)
        assert info["doc_title"] == "طلب إجازة"
        assert info["partner"] == self.employee
        assert info["template_name"] == "order_status_ar"
        assert "4 يوم" in info["status_display"]

    def test_permission_request_dispatcher_info(self):
        """التحقق من إشعار الموافقة على إذن الانصراف والمأمورية"""
        ptype = PermissionType.objects.create(name_ar="إذن شخصي", code="PERSONAL")
        perm = PermissionRequest.objects.create(
            employee=self.employee,
            permission_type=ptype,
            date=timezone.now().date(),
            start_time="14:00",
            end_time="16:00",
            duration_hours=Decimal("2.0"),
            reason="ظرف شخصي طارئ",
            status="approved"
        )

        info = DocumentDispatcher.get_document_info(perm)
        assert info["doc_title"] == "إذن انصراف / مأمورية"
        assert info["partner"] == self.employee
        assert info["template_name"] == "order_status_ar"

    def test_penalty_reward_dispatcher_info(self):
        """التحقق من إشعار المكافأة والجزاء الإداري"""
        pr = PenaltyReward.objects.create(
            employee=self.employee,
            category="reward",
            calculation_method="fixed",
            value=Decimal("1000.00"),
            reason="تميز استثنائي في إنجاز المشروع",
            month=timezone.now().date().replace(day=1),
            created_by=self.user
        )

        info = DocumentDispatcher.get_document_info(pr)
        assert info["doc_title"] == "قرار إداري"
        assert info["partner"] == self.employee
        assert info["template_name"] == "order_status_ar"

    def test_contract_dispatcher_info(self):
        """التحقق من إشعار تجديد العقد الوظيفي"""
        info = DocumentDispatcher.get_document_info(self.contract)
        assert info["doc_title"] == "عقد عمل"
        assert info["doc_number"] == "CNT-2026-001"
        assert info["partner"] == self.employee
        assert info["template_name"] == "order_status_ar"

    def test_asset_custody_dispatcher_info(self):
        """التحقق من إشعار تسليم واستلام عهدة الأصول"""
        custody = EmployeeAssetCustody.objects.create(
            custody_code="CUST-2026-001",
            employee=self.employee,
            item_name="Dell Precision 5570 Laptop",
            serial_number="SN-DELL-998877",
            status="active",
            delivered_date=timezone.now().date()
        )

        info = DocumentDispatcher.get_document_info(custody)
        assert info["doc_title"] == "عهدة أصول ومعدات"
        assert info["partner"] == self.employee
        assert info["template_name"] == "order_status_ar"

    def test_otp_auth_code_dispatcher_info(self):
        """التحقق من قالب رمز التحقق السري OTP"""
        class OTP:
            code = "849201"

        info = DocumentDispatcher.get_document_info(OTP())
        assert info["doc_title"] == "رمز التحقق OTP"
        assert info["template_name"] in ("otp_code", "otp_auth_code")
        assert info["otp_code"] == "849201"
        assert len(info["components"]) == 2
        assert info["components"][0]["parameters"][0]["text"] == "849201"

    def test_security_alert_dispatcher_info(self):
        """التحقق من تنبيهات أمان الحساب والدخول غير المعتاد"""
        class SecurityIncident:
            user = self.user

        info = DocumentDispatcher.get_document_info(SecurityIncident())
        assert info["doc_title"] == "تنبيه أمان الحساب"
        assert info["template_name"] == "order_status_ar"

    def test_backup_and_system_alert_dispatcher_info(self):
        """التحقق من إشعارات النسخ الاحتياطي وتنبيهات النظام"""
        class BackupRecord:
            file_name = "backup_2026_09_28.sql.gz"

        info = DocumentDispatcher.get_document_info(BackupRecord())
        assert info["doc_title"] == "النسخ الاحتياطي للنظام"
        assert info["doc_number"] == "backup_2026_09_28.sql.gz"
        assert info["template_name"] == "order_status_ar"


@pytest.mark.django_db
class TestWhatsAppPhase3API:
    """اختبارات الواجهات البرمجية للمرحلة 3 (Prepare Send & Send Document للرواتب)"""

    def setup_method(self):
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestTokenPhase3API", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "1000123456789", "data_type": "string", "group": "whatsapp", "is_active": True}
        )

        from django.core.cache import cache
        cache.clear()
        WhatsAppService.reset_session()

        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(username="api_hr_user", password="password123", email="hr@mwheba.test")
        self.dept = Department.objects.create(name_ar="إدارة الموارد البشرية", code="HR-01")
        self.job = JobTitle.objects.create(code="JOB-02", title_ar="أخصائي موارد بشرية", department=self.dept)
        self.employee = Employee.objects.create(
            name="سارة خالد إبراهيم",
            employee_number="EMP-0202",
            national_id="29501011234568",
            birth_date="1995-01-01",
            hire_date=timezone.now().date(),
            gender="female",
            marital_status="single",
            department=self.dept,
            job_title=self.job,
            mobile_phone="01122334455",
            user=self.user,
            created_by=self.user
        )

        self.contract = Contract.objects.create(
            employee=self.employee,
            contract_number="CNT-2026-002",
            contract_type="permanent",
            start_date=timezone.now().date(),
            basic_salary=Decimal("12000.00"),
            status="active",
            created_by=self.user
        )

        self.payroll = Payroll.objects.create(
            employee=self.employee,
            contract=self.contract,
            month=timezone.now().date().replace(day=1),
            basic_salary=Decimal("12000.00"),
            allowances=Decimal("2000.00"),
            gross_salary=Decimal("14000.00"),
            net_salary=Decimal("13000.00"),
            status="approved",
            processed_by=self.user
        )

    def test_prepare_send_payroll_api(self):
        """التحقق من endpoint تجهيز إرسال قسيمة الراتب"""
        ct = ContentType.objects.get_for_model(Payroll)
        url = f"{reverse('core:whatsapp_prepare_send')}?content_type_id={ct.id}&object_id={self.payroll.id}&partner_id={self.employee.id}&partner_type=user"

        request = self.factory.get(url)
        request.user = self.user

        response = whatsapp_prepare_send(request)
        assert response.status_code == 200

        data = json.loads(response.content.decode("utf-8"))
        assert data["success"] is True
        assert data["doc_title"] == "قسيمة راتب"
        assert data["partner_name"] == "سارة خالد إبراهيم"
        assert "13,000.00" in data["financial_summary"]
        assert len(data["phone_options"]) >= 1

    @patch("core.services.whatsapp_service.WhatsAppService.send_template_message")
    @patch("core.services.document_dispatcher.DocumentDispatcher.render_document_pdf_bytes")
    def test_send_payroll_document_api(self, mock_pdf, mock_send):
        """التحقق من endpoint إرسال قسيمة الراتب للموظف بنجاح"""
        mock_pdf.return_value = (b"%PDF-1.4 mock binary content", "Payslip_1.pdf")
        mock_send.return_value = {
            "success": True,
            "message_id": "wamid.HBgLMjAxMTAxMjM0NTY3FQIAERgSMzAyRUYwODk3",
            "log_id": 999
        }

        ct = ContentType.objects.get_for_model(Payroll)
        payload = {
            "content_type_id": ct.id,
            "object_id": self.payroll.id,
            "recipient_phone": "01122334455",
            "template_name": "document_send_ar",
            "partner_id": self.employee.id,
            "partner_type": "user",
            "custom_components": json.dumps([
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "سارة خالد إبراهيم"},
                        {"type": "text", "text": "قسيمة راتب #1"},
                        {"type": "text", "text": "صافي الراتب: 13,000.00 ج.م"},
                        {"type": "text", "text": "مؤسسة موهبة"}
                    ]
                }
            ])
        }

        request = self.factory.post(
            reverse("core:whatsapp_send_document"),
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.user
        request._dont_enforce_csrf_checks = True

        response = whatsapp_send_document(request)
        assert response.status_code == 200
        data = json.loads(response.content.decode("utf-8"))
        assert data["success"] is True
        assert "wamid." in data["message_id"]

    def test_prepare_send_multi_waba_accounts_and_window_status(self):
        """التحقق من إرجاع قائمة الحسابات النشطة ومؤشر نافذة الـ 24 ساعة"""
        from core.models import WhatsAppAccount
        WhatsAppAccount.objects.all().delete()
        acc1 = WhatsAppAccount.objects.create(
            name="الفرع الرئيسي",
            phone_number_id="1111111111",
            waba_id="WABA-1",
            display_phone_number="+201011111111",
            is_default=True,
            is_coexistence=True
        )
        acc2 = WhatsAppAccount.objects.create(
            name="فرع الإسكندرية",
            phone_number_id="2222222222",
            waba_id="WABA-2",
            display_phone_number="+201022222222",
            is_default=False,
            is_coexistence=False
        )

        ct = ContentType.objects.get_for_model(Payroll)
        url = f"{reverse('core:whatsapp_prepare_send')}?content_type_id={ct.id}&object_id={self.payroll.id}&partner_id={self.employee.id}&partner_type=user"

        request = self.factory.get(url)
        request.user = self.user

        response = whatsapp_prepare_send(request)
        assert response.status_code == 200
        data = json.loads(response.content.decode("utf-8"))
        assert data["success"] is True
        assert len(data["accounts"]) == 2
        assert data["accounts"][0]["name"] == "الفرع الرئيسي"
        assert data["accounts"][0]["is_default"] is True
        assert data["accounts"][1]["name"] == "فرع الإسكندرية"

    @patch("core.services.whatsapp_service.WhatsAppService.send_template_message")
    @patch("core.services.document_dispatcher.DocumentDispatcher.render_document_pdf_bytes")
    def test_send_payroll_with_specific_account(self, mock_pdf, mock_send):
        """التحقق من إرسال مستند مع تحديد account_id مخصص"""
        from core.models import WhatsAppAccount
        WhatsAppAccount.objects.all().delete()
        acc = WhatsAppAccount.objects.create(
            name="فرع المعادي",
            phone_number_id="3333333333",
            waba_id="WABA-3",
            display_phone_number="+201033333333",
            is_default=True
        )

        mock_pdf.return_value = (b"%PDF-1.4 mock", "Payslip_1.pdf")
        mock_send.return_value = {"success": True, "message_id": "wamid.SPECIFIC_ACCOUNT_MSG", "log_id": 101}

        ct = ContentType.objects.get_for_model(Payroll)
        payload = {
            "content_type_id": ct.id,
            "object_id": self.payroll.id,
            "recipient_phone": "01099887766",
            "account_id": acc.id
        }

        request = self.factory.post(
            reverse("core:whatsapp_send_document"),
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.user
        request._dont_enforce_csrf_checks = True

        response = whatsapp_send_document(request)
        assert response.status_code == 200
        data = json.loads(response.content.decode("utf-8"))
        assert data["success"] is True
        assert data["message_id"] == "wamid.SPECIFIC_ACCOUNT_MSG"

    @patch("core.services.whatsapp_service.WhatsAppService.get_session")
    def test_test_connection_api_updates_account(self, mock_get_session):
        """التحقق من تحديث بيانات الحساب الحية عند فحص الاتصال بـ Meta"""
        from core.models import WhatsAppAccount
        from core.views.whatsapp_views import whatsapp_test_connection_api
        WhatsAppAccount.objects.all().delete()
        acc = WhatsAppAccount.objects.create(
            name="حساب الاختبار",
            phone_number_id="4444444444",
            waba_id="WABA-4",
            display_phone_number="+201044444444",
            is_default=True
        )
        acc.access_token = "EAATestToken123"
        acc.save()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "display_phone_number": "+20 104 444 4444",
            "verified_name": "MWHEBA OFFICIAL STORE",
            "quality_rating": "GREEN",
            "status": "CONNECTED",
            "messaging_limit_tier": "TIER_1K",
            "name_status": "APPROVED",
        }
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_get_session.return_value = mock_session

        payload = {"account_id": acc.id}
        request = self.factory.post(
            reverse("core:whatsapp_test_connection"),
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.user

        response = whatsapp_test_connection_api(request)
        assert response.status_code == 200
        data = json.loads(response.content.decode("utf-8"))
        assert data["success"] is True
        assert data["verified_name"] == "MWHEBA OFFICIAL STORE"

        # التحقق من حفظ البيانات المحدثة في قاعدة البيانات
        acc.refresh_from_db()
        assert acc.verified_name == "MWHEBA OFFICIAL STORE"
        assert acc.quality_rating == "GREEN"
        assert acc.account_status == "CONNECTED"

