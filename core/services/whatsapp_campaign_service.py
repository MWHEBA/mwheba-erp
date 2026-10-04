# -*- coding: utf-8 -*-
"""
خدمة إدارة وتنفيذ الحملات والإشعارات الجماعية عبر WhatsApp Business Cloud API
MWHEBA ERP — WhatsApp Campaign & Throttling Service (Phase 5)
"""
import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..models import WhatsAppAccount, WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppMessageLog
from .whatsapp_service import WhatsAppService
from customer.models import Customer
from supplier.models import Supplier

logger = logging.getLogger('core.services.whatsapp.campaign')


class WhatsAppCampaignService:
    """
    محرك إدارة وتنفيذ الحملات الجماعية مع خنق التدفق (Rate Throttling)
    ودرع حماية تقييم الجودة (Quality Score Shield) وصندوق الصادر المؤجل
    """

    @classmethod
    def populate_recipients(cls, campaign: WhatsAppCampaign) -> int:
        """
        تعبئة وتوليد قائمة مستلمي الحملة بناءً على نوع الجمهور المستهدف
        """
        existing_phones = set(campaign.recipients.values_list('recipient_phone', flat=True))
        new_recipients = []

        if campaign.audience_type in ('ALL_CUSTOMERS', 'CUSTOMERS_WITH_BALANCE', 'CUSTOMER_TIER'):
            cust_qs = Customer.objects.all()

            if campaign.audience_type == 'CUSTOMERS_WITH_BALANCE':
                # العملاء ذوو الأرصدة المدينة
                if hasattr(Customer, 'balance'):
                    cust_qs = cust_qs.filter(balance__gt=Decimal('0.00'))
            elif campaign.audience_type == 'CUSTOMER_TIER' and campaign.customer_tier:
                cust_qs = cust_qs.filter(tier=campaign.customer_tier)

            for cust in cust_qs:
                phone = cust.phone_primary or cust.phone or getattr(cust, 'mobile_phone', '')
                norm_phone = WhatsAppService.normalize_phone(phone, partner=cust)
                if not norm_phone or norm_phone in existing_phones:
                    continue

                existing_phones.add(norm_phone)
                is_opt_out = getattr(cust, 'whatsapp_opt_out', False)
                is_land = WhatsAppService.is_landline(phone)

                status = 'PENDING'
                error_msg = ''
                if is_opt_out:
                    status = 'SKIPPED'
                    error_msg = 'تم التخطي: العميل قام بإلغاء الاشتراك (Opt-Out)'
                elif is_land:
                    status = 'SKIPPED'
                    error_msg = 'تم التخطي: رقم هاتف أرضي'

                new_recipients.append(WhatsAppCampaignRecipient(
                    campaign=campaign,
                    customer=cust,
                    recipient_phone=norm_phone,
                    recipient_name=cust.name,
                    status=status,
                    error_message=error_msg
                ))

        elif campaign.audience_type == 'ALL_SUPPLIERS':
            supp_qs = Supplier.objects.all()
            for supp in supp_qs:
                phone = getattr(supp, 'phone', '') or getattr(supp, 'secondary_phone', '')
                norm_phone = WhatsAppService.normalize_phone(phone, partner=supp)
                if not norm_phone or norm_phone in existing_phones:
                    continue

                existing_phones.add(norm_phone)
                is_opt_out = getattr(supp, 'whatsapp_opt_out', False)
                is_land = WhatsAppService.is_landline(phone)

                status = 'PENDING'
                error_msg = ''
                if is_opt_out:
                    status = 'SKIPPED'
                    error_msg = 'تم التخطي: المورد قام بإلغاء الاشتراك (Opt-Out)'
                elif is_land:
                    status = 'SKIPPED'
                    error_msg = 'تم التخطي: رقم هاتف أرضي'

                new_recipients.append(WhatsAppCampaignRecipient(
                    campaign=campaign,
                    supplier=supp,
                    recipient_phone=norm_phone,
                    recipient_name=supp.name,
                    status=status,
                    error_message=error_msg
                ))

        if new_recipients:
            WhatsAppCampaignRecipient.objects.bulk_create(new_recipients, batch_size=500)

        # تحديث إجمالي المستلمين
        total = campaign.recipients.count()
        skipped = campaign.recipients.filter(status='SKIPPED').count()
        campaign.total_recipients = total
        campaign.skipped_count = skipped
        campaign.save(update_fields=['total_recipients', 'skipped_count'])
        return total

    @classmethod
    def launch_campaign(cls, campaign_id: int, triggered_by: Any = None) -> Dict[str, Any]:
        """
        إطلاق وتنفيذ الحملة مع فحص درع حماية الجودة (Quality Score Shield)
        """
        campaign = WhatsAppCampaign.objects.filter(pk=campaign_id).first()
        if not campaign:
            return {"success": False, "error": "الحملة غير موجودة"}

        account = campaign.account or WhatsAppAccount.objects.filter(is_default=True).first()

        # 1. درع حماية تقييم الجودة (Quality Score Shield - Standard 127)
        if account:
            if account.quality_rating == 'RED' or account.account_status == 'FLAGGED':
                if campaign.campaign_type == 'PROMOTIONAL':
                    campaign.status = 'FROZEN_QUALITY'
                    campaign.save(update_fields=['status'])
                    logger.warning(f"🛑 تم تجميد الحملة #{campaign.id} لحماية جودة الرقم {account.display_phone_number}")
                    return {
                        "success": False,
                        "frozen": True,
                        "error": "تم تجميد الحملة الترويجية تلقائياً لحماية تقييم جودة الرقم (Quality Score Shield) لهبوط تقييم الحساب إلى RED أو FLAGGED."
                    }

        # 2. تعبئة المستلمين إذا لم تكن معبأة
        if campaign.total_recipients == 0:
            cls.populate_recipients(campaign)

        if campaign.total_recipients == 0:
            return {"success": False, "error": "لا يوجد مستلمون مؤهلون لهذه الحملة"}

        campaign.status = 'RUNNING'
        campaign.started_at = timezone.now()
        campaign.save(update_fields=['status', 'started_at'])

        # 3. تشغيل مهمة Celery المجدولة مع خنق التدفق Throttling
        from core.tasks.whatsapp_tasks import execute_whatsapp_campaign_task
        try:
            execute_whatsapp_campaign_task.delay(campaign.id)
        except Exception as queue_err:
            logger.warning(f"WhatsApp Campaign Celery Broker unavailable ({queue_err}) -> معالجة متزامنة فورية")
            cls.execute_campaign_sync(campaign.id)

        return {
            "success": True,
            "message": "تم إطلاق الحملة وجاري الإرسال المجدول بنجاح 🚀",
            "total_recipients": campaign.total_recipients
        }

    @classmethod
    def execute_campaign_sync(cls, campaign_id: int):
        """
        التنفيذ المتزامن للحملة (Fallback & Pytest Execution)
        """
        campaign = WhatsAppCampaign.objects.filter(pk=campaign_id).first()
        if not campaign or campaign.status != 'RUNNING':
            return

        recipients = campaign.recipients.filter(status='PENDING')
        for rec in recipients:
            cls.send_single_recipient(rec.id)

        # فحص اكتمال الحملة
        cls.check_and_finalize_campaign(campaign.id)

    @classmethod
    def send_single_recipient(cls, recipient_id: int) -> Dict[str, Any]:
        """
        إرسال رسالة فردية لمستلم داخل الحملة وتحديث العدادات
        """
        rec = WhatsAppCampaignRecipient.objects.select_related('campaign', 'customer', 'supplier').filter(pk=recipient_id).first()
        if not rec or rec.status != 'PENDING':
            return {"success": False, "error": "المستلم غير صالح أو تم إرساله مسبقاً"}

        campaign = rec.campaign
        account = campaign.account or WhatsAppAccount.objects.filter(is_default=True).first()
        partner = rec.customer or rec.supplier

        # بناء معاملات القالب
        site_name = "موهبة ERP"
        try:
            from core.models import SystemSetting
            site_name = SystemSetting.get_site_name()
        except Exception:
            pass

        balance_str = "0.00 ج.م"
        if rec.customer and hasattr(rec.customer, 'balance'):
            balance_str = f"{rec.customer.balance:,.2f} ج.م"

        components = [{
            "type": "body",
            "parameters": [
                {"type": "text", "text": rec.recipient_name or "عميلنا العزيز"},
                {"type": "text", "text": campaign.name[:40]},
                {"type": "text", "text": balance_str},
                {"type": "text", "text": site_name[:40]},
            ]
        }]

        res = WhatsAppService.send_template_message(
            phone=rec.recipient_phone,
            template_name=campaign.template_name,
            language_code=campaign.language_code,
            components=components,
            partner=partner,
            account=account,
            created_by=campaign.created_by,
            is_automatic=True
        )

        now = timezone.now()
        if res.get("success"):
            rec.status = 'SENT'
            rec.sent_at = now
            if res.get("log_id"):
                rec.message_log_id = res["log_id"]
                WhatsAppMessageLog.objects.filter(id=res["log_id"]).update(campaign=campaign)
            rec.save(update_fields=['status', 'sent_at', 'message_log_id'])

            WhatsAppCampaign.objects.filter(pk=campaign.pk).update(sent_count=F('sent_count') + 1)
            logger.info(f"✅ تم إرسال رسالة الحملة #{campaign.id} للمستلم {rec.recipient_phone}")
            return {"success": True, "message_id": res.get("message_id")}
        else:
            rec.status = 'FAILED'
            rec.error_message = str(res.get("error", "فشل الإرسال"))
            rec.save(update_fields=['status', 'error_message'])

            WhatsAppCampaign.objects.filter(pk=campaign.pk).update(failed_count=F('failed_count') + 1)
            logger.error(f"❌ فشل إرسال رسالة الحملة #{campaign.id} للمستلم {rec.recipient_phone}: {rec.error_message}")
            return {"success": False, "error": rec.error_message}

    @classmethod
    def check_and_finalize_campaign(cls, campaign_id: int):
        """
        التحقق من انتهاء كافة مستلمي الحملة وتحديث الحالة إلى COMPLETED
        """
        campaign = WhatsAppCampaign.objects.filter(pk=campaign_id).first()
        if not campaign:
            return

        remaining = campaign.recipients.filter(status='PENDING').count()
        if remaining == 0:
            campaign.status = 'COMPLETED'
            campaign.completed_at = timezone.now()
            campaign.save(update_fields=['status', 'completed_at'])
            logger.info(f"🎉 اكتملت الحملة #{campaign.id} ({campaign.name}) بنجاح!")
