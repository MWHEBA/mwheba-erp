# -*- coding: utf-8 -*-
"""
Milestone Collection Bridge & Customer Installment Service
MWHEBA ERP — Track 3: Milestone Collection Bridge & Progress Notifications
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models import (
    RealEstateProject,
    PropertyContract,
    ProjectActivity,
    MilestoneInstallmentLink,
    MilestoneCollectionAlert,
)
from sale.models import InstallmentItem

logger = logging.getLogger(__name__)


class MilestoneCollectionBridgeService:
    """
    جسر ربط أقساط عقود البيع بمحطات الإنجاز الميدانية (Milestone Collection Bridge):
    - يربط القسط التعاقدي بنشاط WBS رئيسي محدد (Milestone).
    - يراقب وصول نسبة إنجاز المحطة إلى 100% ويطلق تنبيهات تحصيل مالية مؤتمتة.
    - يدير دورة حياة متابعة التحصيل (قيد المتابعة -> تم التواصل -> تم التحصيل / اعتراض).
    """

    @classmethod
    @transaction.atomic
    def link_installment_to_milestone(
        cls,
        contract: PropertyContract,
        installment_item: InstallmentItem,
        milestone_activity: ProjectActivity,
        notes: str = '',
        auto_trigger_if_completed: bool = True,
        user: Any = None,
    ) -> MilestoneInstallmentLink:
        """
        ربط قسط في خطة تقسيط العقد بمحطة إنجاز مع التحقق الصارم من الحوكمة.
        """
        if not milestone_activity.is_milestone:
            raise ValidationError(_("النشاط المحدد ليس محطة تسليم رئيسية (Milestone)."))

        if milestone_activity.project_id != contract.project_id:
            raise ValidationError(_("محطة الإنجاز المحددة تنتمي إلى مشروع مختلف عن مشروع العقد."))

        if not contract.installment_plan_id or contract.installment_plan_id != installment_item.plan_id:
            raise ValidationError(_("القسط المحدد لا ينتمي إلى خطة التقسيط المعتمدة لهذا العقد."))

        link, created = MilestoneInstallmentLink.objects.get_or_create(
            contract=contract,
            installment_item=installment_item,
            milestone_activity=milestone_activity,
            defaults={
                'notes': notes,
            }
        )

        if not created and notes and link.notes != notes:
            link.notes = notes
            link.save(update_fields=['notes', 'updated_at'])

        # إذا كانت المحطة منجزة بالفعل بنسبة 100%، يتم تفعيل الاستحقاق فوراً
        if auto_trigger_if_completed and milestone_activity.progress_percentage >= Decimal('100.00'):
            cls.check_and_trigger_milestone_collections(milestone_activity, user=user)
            link.refresh_from_db()

        return link

    @classmethod
    @transaction.atomic
    def check_and_trigger_milestone_collections(
        cls,
        milestone_activity: ProjectActivity,
        user: Any = None
    ) -> List[MilestoneCollectionAlert]:
        """
        فحص وتفعيل استحقاق أقساط المبيعات المربوطة بمحطة إنجاز بلغت 100%.
        ينشئ سجلات تنبيه التحصيل تلقائياً للروابط غير المفعلة.
        """
        if not milestone_activity.is_milestone:
            return []

        if milestone_activity.progress_percentage < Decimal('100.00'):
            return []

        # قفل الروابط غير المفعلة لمنع التكرار في حالات التزامن
        pending_links = list(
            MilestoneInstallmentLink.objects.select_for_update()
            .filter(milestone_activity=milestone_activity, is_triggered=False)
            .select_related('contract__customer', 'installment_item')
        )

        if not pending_links:
            return []

        now = timezone.now()
        created_alerts = []

        for link in pending_links:
            # التحقق من سريان العقد - إذا كان العقد موقوفاً أو غير سارٍ، يُرجأ التفعيل لحين عودة العقد للسريان
            if link.contract.status != PropertyContract.ContractStatus.ACTIVE:
                logger.info(
                    "Contract %s is not active (status=%s). Deferring milestone collection trigger.",
                    link.contract.contract_number,
                    link.contract.status
                )
                continue

            link.is_triggered = True
            link.triggered_at = now
            link.save(update_fields=['is_triggered', 'triggered_at', 'updated_at'])

            # تحديد المبلغ المستحق المطالب به من رصيد القسط القائم الفعلي فقط
            item = link.installment_item
            amount_due = max(Decimal('0.00'), item.remaining_balance)

            # إذا كان القسط مسدداً بالكامل مسبقاً (الرصيد القائم صفر)، لا يتم إصدار مطالبة تحصيل
            if amount_due <= Decimal('0.00'):
                logger.info(
                    "Installment #%s for contract %s is already settled (remaining_balance=0). Skipping collection alert.",
                    item.installment_number,
                    link.contract.contract_number
                )
                continue

            alert, created = MilestoneCollectionAlert.objects.get_or_create(
                milestone_link=link,
                contract=link.contract,
                milestone_activity=milestone_activity,
                defaults={
                    'customer': link.contract.customer,
                    'installment_amount': amount_due,
                    'due_date': item.due_date,
                    'status': MilestoneCollectionAlert.AlertStatus.PENDING,
                    'action_notes': f"تم تفعيل استحقاق القسط تلقائياً لإنجاز محطة: {milestone_activity.name} (100%)",
                }
            )
            created_alerts.append(alert)

            logger.info(
                "Milestone collection alert triggered: Contract=%s, Installment=#%s, Milestone=%s, Amount=%s",
                link.contract.contract_number,
                item.installment_number,
                milestone_activity.code,
                amount_due
            )

        return created_alerts

    @classmethod
    @transaction.atomic
    def evaluate_project_milestones_and_trigger(
        cls,
        project: RealEstateProject,
        user: Any = None
    ) -> List[MilestoneCollectionAlert]:
        """
        مسح شامل لكافة محطات الإنجاز التابعة للمشروع وتفعيل أي أقساط تستحق ولم تُفعّل بعد.
        """
        completed_milestones = project.wbs_activities.filter(
            is_milestone=True,
            progress_percentage__gte=Decimal('100.00')
        )

        all_alerts = []
        for ms in completed_milestones:
            alerts = cls.check_and_trigger_milestone_collections(ms, user=user)
            all_alerts.extend(alerts)

        return all_alerts

    @classmethod
    @transaction.atomic
    def update_alert_status(
        cls,
        alert_id: int,
        new_status: str,
        notes: str = '',
        user: Any = None
    ) -> MilestoneCollectionAlert:
        """
        تحديث حالة تنبيه التحصيل مع توثيق الإجراء والملاحظات.
        """
        if new_status not in MilestoneCollectionAlert.AlertStatus.values:
            raise ValidationError(_("حالة التنبيه المحددة غير صالحة."))

        alert = MilestoneCollectionAlert.objects.select_for_update().get(pk=alert_id)
        alert.status = new_status
        if notes:
            user_label = getattr(user, 'username', 'نظام') if user else 'نظام'
            prefix = f"[{timezone.now().strftime('%Y-%m-%d %H:%M')} - {user_label}]: "
            alert.action_notes = f"{alert.action_notes}\n{prefix}{notes}".strip()
        alert.save(update_fields=['status', 'action_notes', 'updated_at'])

        return alert

    @classmethod
    def get_contract_milestones_summary(cls, contract: PropertyContract) -> List[Dict[str, Any]]:
        """
        استخراج ملخص محطات الإنجاز المربوطة بأقساط عقد عقاري محدد.
        """
        links = contract.milestone_installment_links.select_related(
            'installment_item',
            'milestone_activity'
        ).prefetch_related('alerts').order_by('installment_item__installment_number')

        summary = []
        for link in links:
            latest_alert = link.alerts.first()
            summary.append({
                'link_id': link.id,
                'installment_id': link.installment_item_id,
                'installment_number': link.installment_item.installment_number,
                'due_date': link.installment_item.due_date,
                'amount': link.installment_item.total_amount,
                'milestone_id': link.milestone_activity_id,
                'milestone_code': link.milestone_activity.code,
                'milestone_name': link.milestone_activity.name,
                'milestone_progress': link.milestone_activity.progress_percentage,
                'is_triggered': link.is_triggered,
                'triggered_at': link.triggered_at,
                'alert_status': latest_alert.status if latest_alert else None,
                'alert_status_display': latest_alert.get_status_display() if latest_alert else None,
            })
        return summary
