# -*- coding: utf-8 -*-
"""
مهام الأتمتة الخلفية المجدولة للقطاع العقاري (Celery Background Automation Tasks)
MWHEBA ERP — Real Estate Wave 6 (Phase 6.3: Nightly Booking Sweeper & Pre-Due / Legal Escalation Radar)
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from django.utils import timezone

logger = logging.getLogger('real_estate.tasks')

try:
    from celery import shared_task
except ImportError:
    def shared_task(*args, **kwargs):
        def decorator(func):
            def wrapper(*a, **kw):
                return func(*a, **kw)
            wrapper.delay = wrapper
            return wrapper
        if len(args) == 1 and callable(args[0]):
            return decorator(args[0])
        return decorator


def _is_real_estate_module_enabled() -> bool:
    """
    حارس التحقق من تفعيل موديول العقارات قبل تشغيل أي مهمة خلفية
    """
    try:
        from core.models import SystemModule
        mod = SystemModule.objects.filter(code='real_estate').first()
        if mod is not None:
            return bool(mod.is_enabled)
        return True
    except Exception:
        return True


@shared_task(name='real_estate.tasks.sweep_expired_unit_bookings_task', bind=True, max_retries=3, acks_late=True)
def sweep_expired_unit_bookings_task(self, as_of_date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    مهمة مكنسة الحجوزات الليلية التلقائية (Nightly Booking Sweeper):
    - تلغي الحجوزات المنتهية مهلتها دون تحويلها إلى عقد بيع.
    - تعيد طرح الوحدات المحجوزة للبيع (AVAILABLE) مع الحراسة التزامنية المزدوجة.
    """
    if not _is_real_estate_module_enabled():
        logger.info("⏭️ تم تخطي مكنسة الحجوزات العقارية: موديول العقارات غير مفعل.")
        return {
            'success': True,
            'skipped': True,
            'reason': 'real_estate_module_disabled',
            'released_count': 0,
        }

    from real_estate.services.booking_sweep_service import UnitBookingSweepService

    try:
        if as_of_date_str:
            target_date = datetime.strptime(as_of_date_str, '%Y-%m-%d').date()
        else:
            target_date = timezone.localdate()

        released_count = UnitBookingSweepService.sweep_expired_bookings(as_of_date=target_date)
        return {
            'success': True,
            'skipped': False,
            'as_of_date': target_date.isoformat(),
            'released_count': released_count,
        }
    except Exception as exc:
        logger.exception(f"خطأ في مهمة كنس الحجوزات العقارية: {exc}")
        if hasattr(self, 'retry') and getattr(self.request, 'retries', 0) < self.max_retries:
            raise self.retry(exc=exc, countdown=120)
        return {
            'success': False,
            'error': str(exc),
            'released_count': 0,
        }


@shared_task(name='real_estate.tasks.dispatch_installment_escalation_radar_task', bind=True, max_retries=3, acks_late=True)
def dispatch_installment_escalation_radar_task(
    self,
    as_of_date_str: Optional[str] = None,
    stages_filter: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    مهمة رادار التنبيهات المسبقة للأقساط والتصعيد القانوني التلقائي:
    - ترسل تنبيهات الاستحقاق المسبقة (T-7 / T-3) عبر قوالب Meta WhatsApp المعتمدة.
    - تحتسب غرامات التأخير التعاقدية اليومية للأقساط المتأخرة وتصدر الإنذارات القانونية دون تكرار.
    """
    if not _is_real_estate_module_enabled():
        logger.info("⏭️ تم تخطي رادار تنبيهات الأقساط العقارية: موديول العقارات غير مفعل.")
        return {
            'success': True,
            'skipped': True,
            'reason': 'real_estate_module_disabled',
            'processed_count': 0,
        }

    from real_estate.services.legal_escalation_service import LegalEscalationPipeline

    try:
        if as_of_date_str:
            target_date = datetime.strptime(as_of_date_str, '%Y-%m-%d').date()
        else:
            target_date = timezone.localdate()

        summary = LegalEscalationPipeline.run_daily_escalation_sweep(
            as_of_date=target_date,
            stages_filter=stages_filter
        )
        return {
            'success': True,
            'skipped': False,
            **summary,
        }
    except Exception as exc:
        logger.exception(f"خطأ في مهمة رادار الأقساط والتصعيد القانوني: {exc}")
        if hasattr(self, 'retry') and getattr(self.request, 'retries', 0) < self.max_retries:
            raise self.retry(exc=exc, countdown=180)
        return {
            'success': False,
            'error': str(exc),
            'processed_count': 0,
        }
