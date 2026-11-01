# -*- coding: utf-8 -*-
"""
ProjectArchivingService - محرك أرشفة المشروعات العقارية المكتملة والحفظ البارد بدون فقدان البيانات
(Wave 3 Phase 14 - Non-Destructive Project Cold Archiving & Restoration)
"""

import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models.project import RealEstateProject
from real_estate.models.unit import PropertyUnit

logger = logging.getLogger(__name__)


class ProjectArchivingService:
    """
    خدمة أرشفة المشروعات العقارية المكتملة وعزلها عن الاستعلامات التشغيلية اليومية:
    - ضمان الحفظ البارد دون أي حذف فيزيائي للبيانات (Zero Data Loss)
    - استثناء كامل لكافة بيانات القطاع العقاري من روتينات الحذف الآلي (DataRetentionService)
    - إمكانية استعادة وتنشيط أي مشروع مؤرشف في أي وقت بكامل تفاصيله التاريخية
    """

    @classmethod
    def archive_project(
        cls,
        project: RealEstateProject,
        user,
        reason: str = ""
    ) -> RealEstateProject:
        """
        أرشفة المشروع العقاري بعد اكتماله وتسليم وحداته
        """
        if project.is_archived:
            raise ValidationError(_("المشروع مؤرشف بالفعل مسبقاً."))

        # التحقق من أن المشروع ليس في مرحلة التخطيط أو تحت الإنشاء النشط
        if project.status in [
            RealEstateProject.ProjectStatus.PLANNING,
            RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION
        ]:
            raise ValidationError(
                _("لا يمكن أرشفة مشروع لا يزال في مرحلة التخطيط أو تحت الإنشاء النشط (الحالة: %(status)s).") % {
                    'status': project.get_status_display()
                }
            )

        with transaction.atomic():
            project.is_archived = True
            project.save(update_fields=['is_archived', 'updated_at'])

            logger.info(f"Real estate project {project.code} ({project.name}) archived by {user.username}. Reason: {reason}")
            return project

    @classmethod
    def restore_project(
        cls,
        project: RealEstateProject,
        user
    ) -> RealEstateProject:
        """
        استعادة المشروع العقاري المؤرشف وإعادته للاستعلامات والعمليات النشطة
        """
        if not project.is_archived:
            raise ValidationError(_("المشروع غير مؤرشف."))

        with transaction.atomic():
            project.is_archived = False
            project.save(update_fields=['is_archived', 'updated_at'])

            logger.info(f"Real estate project {project.code} ({project.name}) restored from cold archive by {user.username}.")
            return project
