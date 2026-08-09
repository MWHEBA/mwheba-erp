# -*- coding: utf-8 -*-
"""
Document Currency Guard Service
خدمة الحراسة والحماية المركزية لقوانين تغيير عملات المستندات بالفواتير وعروض الأسعار
"""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class DocumentCurrencyGuardService:
    """
    خدمة موحدة للتحقق من سلامة وصلاحية تغيير عملة المستند بناءً على حالة المستند وجودة البنود
    """

    @classmethod
    def validate_currency_change(cls, document, new_currency_id):
        """
        التحقق من إمكانية تغيير عملة المستند
        
        Matrix:
        - Draft بدون بنود: مسموح.
        - Draft مع بنود: محظور حتى مسح كافة البنود.
        - Confirmed / Posted / Sent / Accepted: محظور تماماً.
        """
        if not document or not document.pk:
            return True

        if not new_currency_id:
            return True

        current_currency_id = document.currency_id
        if str(current_currency_id) == str(new_currency_id):
            return True

        status = getattr(document, "status", "draft")

        # حالة المستندات المؤكدة أو المرحلة
        if status in ["confirmed", "posted", "sent", "accepted", "completed", "cancelled"]:
            raise ValidationError(
                _("محظور حوكمياً: لا يمكن تغيير عملة المستند في حالة ({})").format(status)
            )

        # حالة المسودة (Draft): فحص البنود
        has_items = False
        if hasattr(document, "items"):
            has_items = document.items.exists()

        if has_items:
            raise ValidationError(
                _("لا يمكن تغيير عملة المستند أثناء وجود بنود مضافة بالجدول. يرجى مسح كافة البنود أولاً لتمكين تغيير العملة.")
            )

        return True
