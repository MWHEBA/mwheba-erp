# -*- coding: utf-8 -*-
"""
محرك مقاييس كفاءة وسرعة استجابة الـ Webhook Ingress ومراقبة الـ SLA
MWHEBA ERP — WhatsApp Webhook SLA & Ingress Health Metrics Service
"""
import time
import logging
from django.core.cache import cache

logger = logging.getLogger('core.services.whatsapp_metrics')

LATENCY_CACHE_KEY = "whatsapp_ingress_latencies"
METRICS_CACHE_KEY = "whatsapp_ingress_sla_metrics"
CACHE_EXPIRY = 86400  # 24 ساعة


class WhatsAppMetricsService:
    """
    خدمة قياس ومراقبة كفاءة طبقة الاستقبال (Webhook Ingress <20ms SLA)
    وحساب معدلات الاستجابة والتوافر اللحظي
    """

    @classmethod
    def record_ingress_latency(cls, latency_ms: float):
        """تسجيل زمن استجابة طلب Webhook لحظي"""
        try:
            latencies = cache.get(LATENCY_CACHE_KEY, [])
            latencies.append(round(float(latency_ms), 2))
            # الاحتفاظ بآخر 1000 قراءة فقط لترشيد استهلاك الذاكرة
            if len(latencies) > 1000:
                latencies = latencies[-1000:]
            cache.set(LATENCY_CACHE_KEY, latencies, timeout=CACHE_EXPIRY)
        except Exception as e:
            logger.warning(f"Error recording ingress latency: {e}")

    @classmethod
    def get_sla_metrics(cls) -> dict:
        """
        استرجاع مؤشرات الأداء الحية للـ Webhook Ingress
        - متوسط زمن الاستجابة (Average Latency)
        - أقصى زمن استجابة (Peak Latency)
        - نسبة الامتثال لمعيار SLA (< 20ms)
        - نسبة التوافر والنجاح
        """
        latencies = cache.get(LATENCY_CACHE_KEY, [])
        if not latencies:
            return {
                'total_requests': 0,
                'avg_latency_ms': 0.0,
                'min_latency_ms': 0.0,
                'max_latency_ms': 0.0,
                'p95_latency_ms': 0.0,
                'sla_compliance_rate': 100.0,
                'sla_target_ms': 20.0,
                'status': 'HEALTHY',
                'status_display': 'ممتاز (<20ms SLA)',
            }

        total_reqs = len(latencies)
        avg_lat = round(sum(latencies) / total_reqs, 2)
        min_lat = min(latencies)
        max_lat = max(latencies)
        
        # حساب الـ P95
        sorted_lat = sorted(latencies)
        p95_index = int(total_reqs * 0.95)
        p95_lat = sorted_lat[min(p95_index, total_reqs - 1)]

        # نسبة الطلبات التي استجابت في أقل من 20 مللي ثانية
        under_sla_count = sum(1 for l in latencies if l <= 20.0)
        sla_rate = round((under_sla_count / total_reqs) * 100.0, 1)

        status = 'HEALTHY'
        status_display = 'ممتاز (ممتثل لمعيار <20ms)'
        if avg_lat > 50.0 or sla_rate < 80.0:
            status = 'CRITICAL'
            status_display = 'تأخير مرتفع (>50ms)'
        elif avg_lat > 20.0 or sla_rate < 95.0:
            status = 'WARNING'
            status_display = 'تحذير بطء نسبي (>20ms)'

        return {
            'total_requests': total_reqs,
            'avg_latency_ms': avg_lat,
            'min_latency_ms': min_lat,
            'max_latency_ms': max_lat,
            'p95_latency_ms': p95_lat,
            'sla_compliance_rate': sla_rate,
            'sla_target_ms': 20.0,
            'status': status,
            'status_display': status_display,
        }
