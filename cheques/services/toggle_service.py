# -*- coding: utf-8 -*-
"""
FIN-CHQ-TOGGLE: Cheque Module Feature Toggle & Draining Mode Service
خدمة حوكمة تفعيل وتعطيل موديول الشيكات مع دعم وضع التصفية التدريجي (Draining Mode)
"""
import logging
from typing import Dict, Any, List
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from cheques.models import Cheque, ChequePurpose, ChequeStatus

logger = logging.getLogger(__name__)


class ChequeToggleService:
    """
    حوكمة تشغيل وتعطيل موديول الشيكات:
    1. التحقق من حالة الموديول (Enabled / Disabled)
    2. فحص الشيكات النشطة لمنع التعطيل الفوري في حالة وجود دورة مستندية قائمة
    3. إدارة وضع التصفية التدريجي (Draining Mode) لمنع أي إصدارات جديدة مع إتاحة التحصيل/الصرف القائم
    """

    DRAINING_SETTING_KEY = "cheques_draining_mode"

    ACTIVE_STATUSES = [
        ChequeStatus.IN_PORTFOLIO,
        ChequeStatus.UNDER_COLLECTION,
        ChequeStatus.PARTIALLY_COLLECTED,
        ChequeStatus.BOUNCED,
        ChequeStatus.ENDORSED_BOUNCED,
        ChequeStatus.LEGAL_ACTION,
        ChequeStatus.ISSUED,
    ]

    @classmethod
    def is_enabled(cls) -> bool:
        """هل موديول الشيكات مفعل في النظام"""
        try:
            from core.models import SystemModule
            mod = SystemModule.objects.filter(code='cheques').first()
            if mod is not None:
                return mod.is_enabled
            return True
        except Exception:
            return True

    @classmethod
    def is_draining(cls) -> bool:
        """هل موديول الشيكات في وضع التصفية التدريجية (Draining Mode)"""
        try:
            from core.models import SystemSetting
            return SystemSetting.get_bool(cls.DRAINING_SETTING_KEY, default=False)
        except Exception:
            return False

    @classmethod
    def get_active_cheques_count(cls) -> int:
        """
        حساب عدد الشيكات النشطة التي تمنع تعطيل الموديول:
        - شيكات قيد التداول (في الحافظة، برسم التحصيل، محصلة جزئياً، صادرة، مرتدة، قضائية)
        - شيكات ضمان لم يتم إرجاعها للساحب بعد
        """
        try:
            return Cheque.objects.filter(
                Q(status__in=cls.ACTIVE_STATUSES) |
                (
                    Q(purpose=ChequePurpose.SECURITY_GUARANTEE) &
                    ~Q(status__in=[ChequeStatus.RETURNED_TO_DRAWER, ChequeStatus.CANCELLED, ChequeStatus.DRAFT])
                )
            ).count()
        except Exception as e:
            logger.warning(f"Error querying active cheques count: {e}")
            return 0

    @classmethod
    def can_disable_module(cls) -> bool:
        """
        هل يمكن تعطيل الموديول حالياً:
        فقط إذا كان خط الأنابيب التشغيلي خالياً تماماً (عدد الشيكات النشطة = 0)
        """
        return cls.get_active_cheques_count() == 0

    @classmethod
    def can_create_new_cheques(cls) -> bool:
        """
        هل يُسمح بإنشاء شيكات جديدة:
        - الموديول يجب أن يكون مفعلاً
        - الموديول يجب ألا يكون في وضع التصفية (Draining Mode)
        """
        if not cls.is_enabled():
            return False
        if cls.is_draining():
            return False
        return True

    @classmethod
    def set_draining_mode(cls, enabled: bool) -> None:
        """تفعيل أو إلغاء وضع التصفية"""
        from core.models import SystemSetting
        SystemSetting.set_setting(
            key=cls.DRAINING_SETTING_KEY,
            value="true" if enabled else "false",
            group="cheques",
            data_type="boolean",
            description="وضع التصفية لمنظومة الشيكات (Draining Mode)"
        )
        logger.info(f"Cheque module draining mode set to: {enabled}")

    @classmethod
    def request_disable(cls, user=None) -> Dict[str, Any]:
        """
        طلب رسمي لتعطيل موديول الشيكات:
        - إذا لم تكن هناك أي شيكات نشطة: يتم التعطيل الكامل فوراً.
        - إذا كانت هناك شيكات نشطة: يتم تفعيل وضع التصفية (Draining Mode) ومنع إضافة شيكات جديدة.
        """
        active_count = cls.get_active_cheques_count()
        if active_count == 0:
            from core.models import SystemModule
            SystemModule.objects.filter(code='cheques').update(is_enabled=False)
            cls.set_draining_mode(False)
            return {
                "success": True,
                "draining": False,
                "active_count": 0,
                "message": _("تم تعطيل منظومة الشيكات بنجاح لعدم وجود أي شيكات نشطة.")
            }
        else:
            cls.set_draining_mode(True)
            return {
                "success": False,
                "draining": True,
                "active_count": active_count,
                "message": _(f"لا يمكن تعطيل المنظومة لوجود {active_count} شيك نشط. تم تفعيل وضع التصفية (Draining Mode) لحين اكتمال تسوية الشيكات.")
            }
