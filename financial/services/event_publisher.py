import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
from django.db import transaction

logger = logging.getLogger(__name__)


class ClosingEventPublisher(ABC):
    """
    واجهة مجرّدة لإرسال وإطلاق أحداث الإغلاق المحاسبي (Event Publisher Interface)
    تسمح بفصل كود الإغلاق الرئيسي عن آلية معالجة الأحداث والمهام الخلفية.
    """
    @abstractmethod
    def publish_fiscal_year_closed(self, closing_run_id: int, payload: Dict[str, Any]) -> bool:
        """إطلاق حدث اكتمال إغلاق السنة المالية"""
        pass

    @abstractmethod
    def publish_period_closed(self, period_id: int, payload: Dict[str, Any]) -> bool:
        """إطلاق حدث إغلاق فترة محاسبية"""
        pass


class SyncEventPublisher(ClosingEventPublisher):
    """
    مُنفذ أحداث تزامني (Synchronous Event Publisher) للمرحلة Phase 1A.
    يضمن عدم تشغيل أي حدث إطلاق إلا بعد نجاح الترحيل النهائي لقاعدة البيانات (transaction.on_commit).
    """

    def publish_fiscal_year_closed(self, closing_run_id: int, payload: Dict[str, Any]) -> bool:
        def _on_commit_handler():
            logger.info(f"📢 [FiscalYearClosedEvent] تم تأكيد إغلاق السنة المالية للتشغيل #{closing_run_id}")
            # يمكن في المرحلة Phase 1B/3 توجيه هذه النقطة لاستدعاء الخدمة أو إرسال الإشعار

        transaction.on_commit(_on_commit_handler)
        return True

    def publish_period_closed(self, period_id: int, payload: Dict[str, Any]) -> bool:
        def _on_commit_handler():
            logger.info(f"📢 [PeriodClosedEvent] تم تأكيد إغلاق الفترة المحاسبية #{period_id}")

        transaction.on_commit(_on_commit_handler)
        return True
