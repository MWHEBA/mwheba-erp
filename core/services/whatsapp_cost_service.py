# -*- coding: utf-8 -*-
"""
محرك إدارة وتحليلات تكاليف محادثات واتساب (WhatsApp Cost & Analytics Ledger)
MWHEBA ERP — WhatsApp Meta Conversation Pricing & Cost Analytics Service
"""
import logging
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q
from ..models import WhatsAppMessageLog, WhatsAppAccount

logger = logging.getLogger('core.services.whatsapp_cost')


class WhatsAppCostService:
    """
    خدمة احتساب وتدقيق التكاليف التقديرية لمحادثات ورسائل Meta
    حسب فئات المحادثات الرسمية (Utility, Marketing, Service, Authentication)
    """

    # أسعار المحادثات التقديرية (بالدولار الأمريكي USD)
    DEFAULT_RATES_USD = {
        'UTILITY': Decimal('0.0050'),        # فواتير، سندات، إشعارات خدمة
        'MARKETING': Decimal('0.0380'),      # عروض ترويجية، حملات تسويقية
        'SERVICE': Decimal('0.0035'),        # ردود دعم فني مفتوحة بطلب العميل
        'AUTHENTICATION': Decimal('0.0150'), # رموز OTP والتحقق
        'UNKNOWN': Decimal('0.0050'),
    }

    # معامل التحويل التقديري للجنيه المصري EGP
    DEFAULT_USD_TO_EGP_RATE = Decimal('50.00')

    @classmethod
    def get_message_category(cls, msg: WhatsAppMessageLog) -> str:
        """تحديد فئة المحادثة / الرسالة"""
        if getattr(msg, 'pricing_category', None):
            return msg.pricing_category

        if msg.campaign:
            if msg.campaign.campaign_type == 'PROMOTIONAL':
                return 'MARKETING'
            return 'UTILITY'
        
        if msg.direction == 'INBOUND':
            return 'SERVICE'
            
        return 'UTILITY'

    @classmethod
    def calculate_estimated_cost(cls, msg: WhatsAppMessageLog, currency: str = 'USD') -> Decimal:
        """احتساب التكلفة التقديرية لرسالة مفردة"""
        category = cls.get_message_category(msg)
        rate_usd = cls.DEFAULT_RATES_USD.get(category, cls.DEFAULT_RATES_USD['UTILITY'])
        
        if currency.upper() == 'EGP':
            return (rate_usd * cls.DEFAULT_USD_TO_EGP_RATE).quantize(Decimal('0.0001'))
        return rate_usd.quantize(Decimal('0.0001'))

    @classmethod
    def get_cost_analytics_summary(cls, account_id: int = None, days: int = 30) -> dict:
        """
        توليد تقرير وملخص تحليلي شامل للتكاليف واستهلاك الرسائل
        خلال فترة محددة
        """
        since_date = timezone.now() - timedelta(days=days)
        qs = WhatsAppMessageLog.objects.filter(created_at__gte=since_date)

        if account_id:
            qs = qs.filter(account_id=account_id)

        total_messages = qs.count()
        outbound_count = qs.filter(direction__startswith='OUTBOUND').count()
        inbound_count = qs.filter(direction='INBOUND').count()
        delivered_count = qs.filter(status__in=['DELIVERED', 'READ']).count()
        failed_count = qs.filter(status='FAILED').count()

        # توزيع الفئات التقديري
        marketing_count = qs.filter(
            Q(pricing_category='MARKETING') | Q(campaign__campaign_type='PROMOTIONAL')
        ).count()
        utility_count = qs.filter(
            Q(pricing_category='UTILITY') |
            Q(campaign__campaign_type__in=['STATEMENT', 'COLLECTION_REMINDER', 'SERVICE_ANNOUNCEMENT'])
        ).count()
        service_count = max(0, total_messages - marketing_count - utility_count)

        # حساب التكاليف
        cost_marketing_usd = Decimal(marketing_count) * cls.DEFAULT_RATES_USD['MARKETING']
        cost_utility_usd = Decimal(utility_count) * cls.DEFAULT_RATES_USD['UTILITY']
        cost_service_usd = Decimal(service_count) * cls.DEFAULT_RATES_USD['SERVICE']
        total_cost_usd = (cost_marketing_usd + cost_utility_usd + cost_service_usd).quantize(Decimal('0.01'))
        total_cost_egp = (total_cost_usd * cls.DEFAULT_USD_TO_EGP_RATE).quantize(Decimal('0.01'))

        # تفصيل لكل حساب WABA
        accounts_breakdown = []
        accounts = WhatsAppAccount.objects.exclude(account_status='DISCONNECTED')
        for acc in accounts:
            acc_qs = qs.filter(account=acc)
            acc_total = acc_qs.count()
            if acc_total > 0:
                acc_sent = acc_qs.filter(direction__startswith='OUTBOUND').count()
                acc_cost_usd = (
                    Decimal(acc_qs.filter(pricing_category='MARKETING').count()) * cls.DEFAULT_RATES_USD['MARKETING'] +
                    Decimal(acc_qs.filter(pricing_category='UTILITY').count()) * cls.DEFAULT_RATES_USD['UTILITY'] +
                    Decimal(acc_qs.filter(pricing_category='SERVICE').count()) * cls.DEFAULT_RATES_USD['SERVICE']
                ).quantize(Decimal('0.01'))
                accounts_breakdown.append({
                    'account_id': acc.id,
                    'account_name': acc.name,
                    'phone_number': acc.display_phone_number,
                    'total_messages': acc_total,
                    'sent_messages': acc_sent,
                    'estimated_cost_usd': float(acc_cost_usd),
                    'estimated_cost_egp': float(acc_cost_usd * cls.DEFAULT_USD_TO_EGP_RATE),
                })

        return {
            'days': days,
            'total_messages': total_messages,
            'outbound_count': outbound_count,
            'inbound_count': inbound_count,
            'delivered_count': delivered_count,
            'failed_count': failed_count,
            'categories': {
                'utility': {
                    'count': utility_count,
                    'cost_usd': float(cost_utility_usd.quantize(Decimal('0.01'))),
                    'cost_egp': float((cost_utility_usd * cls.DEFAULT_USD_TO_EGP_RATE).quantize(Decimal('0.01'))),
                },
                'marketing': {
                    'count': marketing_count,
                    'cost_usd': float(cost_marketing_usd.quantize(Decimal('0.01'))),
                    'cost_egp': float((cost_marketing_usd * cls.DEFAULT_USD_TO_EGP_RATE).quantize(Decimal('0.01'))),
                },
                'service': {
                    'count': service_count,
                    'cost_usd': float(cost_service_usd.quantize(Decimal('0.01'))),
                    'cost_egp': float((cost_service_usd * cls.DEFAULT_USD_TO_EGP_RATE).quantize(Decimal('0.01'))),
                },
            },
            'total_cost_usd': float(total_cost_usd),
            'total_cost_egp': float(total_cost_egp),
            'accounts_breakdown': accounts_breakdown,
        }
