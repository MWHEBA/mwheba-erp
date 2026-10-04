# -*- coding: utf-8 -*-
"""
مصفوفة الاختبارات الآلية الشاملة للمرحلة السادسة (Phase 6: Cost Ledger, SLA Health, Simulator & Meta Compliance)
MWHEBA ERP — WhatsApp Phase 6 Pytest Matrix
"""
import json
import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from core.models import WhatsAppAccount, WhatsAppMessageLog, WhatsAppCampaign
from core.services.whatsapp_cost_service import WhatsAppCostService
from core.services.whatsapp_metrics_service import WhatsAppMetricsService
from core.services.whatsapp_simulator_service import WhatsAppSimulatorService

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase6CostAndReview:
    """مصفوفة الاختبارات الشاملة للمرحلة السادسة"""

    def setup_method(self):
        WhatsAppAccount.objects.all().delete()
        WhatsAppMessageLog.objects.all().delete()
        WhatsAppCampaign.objects.all().delete()

        self.user = User.objects.create_superuser(
            username="cfo_whatsapp_admin_p6",
            email="cfo_p6@mwheba.co.uk",
            password="StrongPassword2026!"
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.account = WhatsAppAccount.objects.create(
            name="فرع القاهرة الرئيسي",
            phone_number_id="1010101010",
            waba_id="2020202020",
            display_phone_number="+201012345678",
            is_default=True,
            account_status='CONNECTED'
        )

    def test_cost_service_calculations_and_categories(self):
        """1. اختبار احتساب التكاليف وفئات المحادثات (Utility, Marketing, Service)"""
        # رسالة فاتورة (Utility)
        msg_utility = WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone="201011112222",
            direction="OUTBOUND_ERP",
            pricing_category="UTILITY",
            document_reference_text="INV-100",
            status="DELIVERED"
        )
        cat_u = WhatsAppCostService.get_message_category(msg_utility)
        assert cat_u == 'UTILITY'
        cost_u_usd = WhatsAppCostService.calculate_estimated_cost(msg_utility, currency='USD')
        assert cost_u_usd == Decimal('0.0050')

        # رسالة حملة ترويجية (Marketing)
        campaign = WhatsAppCampaign.objects.create(
            name="عروض الصيف",
            account=self.account,
            campaign_type="PROMOTIONAL",
            template_name="summer_offer"
        )
        msg_marketing = WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone="201011113333",
            direction="OUTBOUND_ERP",
            pricing_category="MARKETING",
            campaign=campaign,
            status="DELIVERED"
        )
        cat_m = WhatsAppCostService.get_message_category(msg_marketing)
        assert cat_m == 'MARKETING'
        cost_m_egp = WhatsAppCostService.calculate_estimated_cost(msg_marketing, currency='EGP')
        assert cost_m_egp == Decimal('1.9000')

        # فحص الملخص التحليلي (Cost Summary)
        summary = WhatsAppCostService.get_cost_analytics_summary(days=30)
        assert summary['total_messages'] == 2
        assert summary['categories']['utility']['count'] >= 1
        assert summary['categories']['marketing']['count'] >= 1
        assert summary['total_cost_usd'] > 0

    def test_metrics_service_sla_recording_and_stats(self):
        """2. اختبار تسجيل زمن الاستجابة وحساب مؤشرات الـ SLA (<20ms)"""
        # تسجيل قراءات أزمنة استجابة
        WhatsAppMetricsService.record_ingress_latency(2.5)
        WhatsAppMetricsService.record_ingress_latency(5.1)
        WhatsAppMetricsService.record_ingress_latency(12.0)
        WhatsAppMetricsService.record_ingress_latency(18.2)
        WhatsAppMetricsService.record_ingress_latency(4.0)

        sla = WhatsAppMetricsService.get_sla_metrics()
        assert sla['total_requests'] >= 5
        assert sla['avg_latency_ms'] < 20.0
        assert sla['sla_compliance_rate'] == 100.0
        assert sla['status'] == 'HEALTHY'

    def test_simulator_service_invoice_generation_and_dispatch(self):
        """3. اختبار محاكي إرسال الفواتير لفيديو اعتماد Meta"""
        pdf_bytes = WhatsAppSimulatorService.generate_demo_invoice_pdf("INV-DEMO-2026", "Test Customer", 500.0)
        assert pdf_bytes.startswith(b"%PDF")

        res = WhatsAppSimulatorService.send_simulator_test_invoice(
            recipient_phone="201012345678",
            account_id=self.account.id,
            invoice_number="INV-DEMO-2026"
        )
        assert res['success'] is True
        assert 'INV-DEMO-2026' in res.get('message', '') or 'wamid' in res.get('message_id', '')

    def test_phase6_apis(self):
        """4. اختبار مسارات الـ API لمقاييس الـ SLA وتحليلات التكلفة والمحاكي"""
        # SLA API
        res_sla = self.client.get(reverse('core:whatsapp_sla_metrics'))
        assert res_sla.status_code == 200
        data_sla = json.loads(res_sla.content)
        assert data_sla['success'] is True
        assert 'metrics' in data_sla

        # Cost Analytics API
        res_cost = self.client.get(reverse('core:whatsapp_cost_analytics'))
        assert res_cost.status_code == 200
        data_cost = json.loads(res_cost.content)
        assert data_cost['success'] is True
        assert 'summary' in data_cost

        # Simulator Dispatch API
        res_sim = self.client.post(
            reverse('core:whatsapp_simulator_dispatch'),
            data=json.dumps({'recipient_phone': '201099887766', 'invoice_number': 'INV-TEST-001'}),
            content_type='application/json'
        )
        assert res_sim.status_code == 200
        data_sim = json.loads(res_sim.content)
        assert data_sim['success'] is True

    def test_meta_compliance_pages_and_data_deletion_callback(self):
        """5. اختبار صفحات الامتثال ومسار حذف البيانات المعتمد لـ Meta للزوار والمراجعين بدون تسجيل دخول (Public Access)"""
        anon_client = Client()

        # Privacy Policy Page (Public)
        res_priv = anon_client.get(reverse('core:whatsapp_privacy_policy'))
        assert res_priv.status_code == 200
        assert "خصوصية" in res_priv.content.decode('utf-8')
        assert "Privacy Policy" in res_priv.content.decode('utf-8')

        # Terms of Service Page (Public)
        res_terms = anon_client.get(reverse('core:whatsapp_terms'))
        assert res_terms.status_code == 200
        assert "شروط" in res_terms.content.decode('utf-8')
        assert "Terms of Service" in res_terms.content.decode('utf-8')

        # Meta Data Deletion Callback (Public POST)
        res_del = anon_client.post(
            reverse('core:whatsapp_data_deletion_callback'),
            data={'signed_request': 'mock_signed_request_payload'}
        )
        assert res_del.status_code == 200
        data_del = json.loads(res_del.content)
        assert 'confirmation_code' in data_del
        assert 'url' in data_del

        # Confirmation Status Page (Public)
        res_status = anon_client.get(reverse('core:whatsapp_data_deletion_status', kwargs={'confirmation_code': data_del['confirmation_code']}))
        assert res_status.status_code == 200
        assert data_del['confirmation_code'] in res_status.content.decode('utf-8')
