"""
SystemAutomationUserService - خدمة إدارة وتوفير مستخدم النظام للمهام المجدولة في الخلفية
يضمن وجود حساب معتمد للمهام الدورية مثل process_due_revenues و FX Revaluation
لتفادي استثناءات غياب الجلسة أو سقف الصلاحيات المالية في AccountingGateway
"""

import logging
from django.contrib.auth import get_user_model

logger = logging.getLogger("financial.system_automation_user")
User = get_user_model()


class SystemAutomationUserService:
    """
    خدمة مستخدم النظام الآلي (System Automation User Provider)
    """

    SYSTEM_USERNAME = "system_automation_engine"

    @classmethod
    def get_or_create_system_user(cls):
        """
        الحصول على أو إنشاء مستخدم النظام الآلي المعتمد
        """
        user, created = User.objects.get_or_create(
            username=cls.SYSTEM_USERNAME,
            defaults={
                "first_name": "System",
                "last_name": "Automation Engine",
                "email": "system.automation@mwheba.internal",
                "is_active": True,
                "is_staff": True,
                "is_superuser": True
            }
        )
        if created:
            user.set_unusable_password()
            user.save()
            logger.info(f"Created dedicated System Automation User: @{cls.SYSTEM_USERNAME}")

        return user
