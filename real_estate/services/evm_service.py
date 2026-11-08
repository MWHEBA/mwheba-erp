# -*- coding: utf-8 -*-
"""
Earned Value Management (EVM) Services
MWHEBA ERP — Track 3: EVM (CPI / SPI / CV / SV / EAC / VAC & S-Curve Forecasting)
"""
import logging
from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, Any, List, Optional

from django.utils import timezone
from django.db.models import Sum, Avg, Q
from django.utils.translation import gettext_lazy as _

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyUnit,
    ProjectActivity,
    UnitSiteProgressRecord,
)

logger = logging.getLogger(__name__)


class EarnedValueManagementService:
    """
    خدمة إدارة القيمة المكتسبة ومؤشرات الأداء الزمني والتكاليف (EVM Standard):
    - PV (Planned Value): القيمة المخططة وفق خط الأساس الزمني.
    - EV (Earned Value): القيمة المكتسبة من واقع الإنجاز الميداني الفعلي.
    - AC (Actual Cost): التكلفة الفعلية المنصرفة على البند/المشروع.
    - SV (Schedule Variance): الانحراف الزمني = EV - PV.
    - CV (Cost Variance): انحراف التكلفة = EV - AC.
    - SPI (Schedule Performance Index): مؤشر الأداء الزمني = EV / PV.
    - CPI (Cost Performance Index): مؤشر أداء التكلفة = EV / AC.
    - EAC (Estimate at Completion): التكلفة التقديرية عند الاكتمال = BAC / CPI.
    - VAC (Variance at Completion): انحراف التكلفة عند الاكتمال = BAC - EAC.
    """

    @classmethod
    def get_activity_bac(cls, activity: ProjectActivity) -> Decimal:
        """
        استرجاع الموازنة التقديرية المعتمدة للنشاط (BAC - Budget at Completion):
        - الأولوية لـ budget_cost المسجلة في النشاط.
        - أو total_budget_cost من بند المقايسة العامة master_boq_item.
        - أو مجموع موازنات الأنشطة الفرعية إن وجدت.
        - أو تخصيص نسبي من موازنة المشروع حسب weight_percentage.
        """
        if activity.budget_cost and activity.budget_cost > Decimal('0.00'):
            return activity.budget_cost

        if activity.master_boq_item and activity.master_boq_item.total_budget_cost > Decimal('0.00'):
            return activity.master_boq_item.total_budget_cost

        children = list(activity.sub_activities.all())
        if children:
            child_bac = sum((cls.get_activity_bac(c) for c in children), Decimal('0.00'))
            if child_bac > Decimal('0.00'):
                return child_bac

        # تخصيص من موازنة المشروع الكلية
        if activity.project.total_budget_cost > Decimal('0.00') and activity.weight_percentage > Decimal('0.00'):
            allocated = (activity.project.total_budget_cost * (activity.weight_percentage / Decimal('100.0000'))).quantize(Decimal('0.01'))
            return allocated

        return Decimal('0.00')

    @classmethod
    def get_activity_actual_cost(cls, activity: ProjectActivity) -> Decimal:
        """
        استرجاع التكلفة الفعلية المنصرفة للنشاط (AC - Actual Cost):
        - الأولوية لـ actual_cost المسجلة في النشاط.
        - أو مجموع التكاليف الفعلية للأنشطة الفرعية التابعة.
        """
        if activity.actual_cost and activity.actual_cost > Decimal('0.00'):
            return activity.actual_cost

        children = list(activity.sub_activities.all())
        if children:
            child_ac = sum((cls.get_activity_actual_cost(c) for c in children), Decimal('0.00'))
            return child_ac

        return Decimal('0.00')

    @classmethod
    def calculate_activity_planned_progress(
        cls,
        activity: ProjectActivity,
        as_of_date: Optional[date] = None
    ) -> Decimal:
        """
        احتساب نسبة التقدم المخطط للنشاط (Planned Progress %) حتى تاريخ التقييم:
        - إذا كان له أبناء: المتوسط الموزون للتقدم المخطط للأبناء.
        - إذا كان نشاطاً ورقياً: حساب النسبة الخطية بين baseline_start_date و baseline_end_date.
        """
        eval_date = as_of_date or timezone.localdate()

        children = list(activity.sub_activities.all())
        if children:
            child_weights = sum((c.weight_percentage for c in children), Decimal('0.0000'))
            if child_weights > Decimal('0.0000'):
                child_sum = sum(
                    (cls.calculate_activity_planned_progress(c, eval_date) * (c.weight_percentage / Decimal('100.0000')) for c in children),
                    Decimal('0.0000')
                )
                return (child_sum / (child_weights / Decimal('100.0000'))).quantize(Decimal('0.01'))
            else:
                child_sum = sum((cls.calculate_activity_planned_progress(c, eval_date) for c in children), Decimal('0.00'))
                return (child_sum / Decimal(len(children))).quantize(Decimal('0.01'))

        # النشاط الورقي
        start_d = activity.baseline_start_date or activity.project.start_date
        end_d = activity.baseline_end_date or activity.project.expected_completion_date

        if not start_d or not end_d:
            return Decimal('0.00')

        if eval_date < start_d:
            return Decimal('0.00')

        if eval_date >= end_d:
            return Decimal('100.00')

        total_days = (end_d - start_d).days
        if total_days <= 0:
            return Decimal('100.00')

        elapsed_days = (eval_date - start_d).days
        planned_pct = (Decimal(elapsed_days) / Decimal(total_days) * Decimal('100.00')).quantize(Decimal('0.01'))
        return max(Decimal('0.00'), min(Decimal('100.00'), planned_pct))

    @classmethod
    def calculate_activity_evm(
        cls,
        activity: ProjectActivity,
        as_of_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        احتساب كافة مؤشرات القيمة المكتسبة لنشاط مقايسة WBS:
        """
        eval_date = as_of_date or timezone.localdate()

        bac = cls.get_activity_bac(activity)
        actual_pct = activity.progress_percentage
        planned_pct = cls.calculate_activity_planned_progress(activity, eval_date)

        # إذا كانت الموازنة صفرية، نعتبر القيمة الافتراضية 100 وحدة مالية لاحتساب المؤشرات النسبية
        effective_bac = bac if bac > Decimal('0.00') else Decimal('100.00')

        pv = (effective_bac * (planned_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
        ev = (effective_bac * (actual_pct / Decimal('100.00'))).quantize(Decimal('0.01'))

        actual_cost_val = cls.get_activity_actual_cost(activity)
        # الحفاظ التام على التكلفة الفعلية المسجلة دون استبدالها أو اختلاقها من القيمة المكتسبة
        ac = actual_cost_val

        sv = ev - pv

        # مؤشر الأداء الزمني SPI = EV / PV
        if pv > Decimal('0.00'):
            spi = (ev / pv).quantize(Decimal('0.01'))
        elif planned_pct == Decimal('0.00') and actual_pct == Decimal('0.00'):
            spi = Decimal('1.00')
        elif planned_pct == Decimal('0.00') and actual_pct > Decimal('0.00'):
            spi = Decimal('2.00')
        else:
            spi = Decimal('1.00')

        if ac > Decimal('0.00'):
            cv = ev - ac
            cv_pct = ((cv / ev) * Decimal('100.00')).quantize(Decimal('0.01')) if ev > Decimal('0.00') else Decimal('0.00')
            cpi = (ev / ac).quantize(Decimal('0.01'))
            if cpi > Decimal('0.00'):
                eac = (bac / cpi).quantize(Decimal('0.01'))
                vac = bac - eac
            else:
                eac = None
                vac = None
            has_actual_cost = True
            cost_data_status = 'RECORDED'

            if cpi > Decimal('1.05'):
                cpi_status = 'UNDER_BUDGET'
                cpi_label = _('وفر وتوفير في الموازنة')
                cpi_class = 'text-success'
            elif cpi >= Decimal('0.95'):
                cpi_status = 'ON_BUDGET'
                cpi_label = _('مطابق للموازنة التقديرية')
                cpi_class = 'text-primary'
            else:
                cpi_status = 'OVER_BUDGET'
                cpi_label = _('تجاوز في التكاليف الفعلية')
                cpi_class = 'text-danger'
        elif ev == Decimal('0.00') and ac == Decimal('0.00'):
            cv = Decimal('0.00')
            cv_pct = Decimal('0.00')
            cpi = Decimal('1.00')
            eac = bac
            vac = Decimal('0.00')
            has_actual_cost = True
            cost_data_status = 'ZERO_COST'
            cpi_status = 'ON_BUDGET'
            cpi_label = _('مطابق للموازنة التقديرية')
            cpi_class = 'text-primary'
        else:
            # لم تُسجل تكلفة فعلية بعد رغم تحقق إنجاز: إبراز غياب أدلة التكلفة دون اختلاق أرقام
            cv = Decimal('0.00')
            cv_pct = Decimal('0.00')
            cpi = None
            eac = bac
            vac = Decimal('0.00')
            has_actual_cost = False
            cost_data_status = 'UNAVAILABLE'
            cpi_status = 'NO_COST_DATA'
            cpi_label = _('بيانات التكلفة غير مسجلة بعد')
            cpi_class = 'text-muted'

        sv_pct = ((sv / pv) * Decimal('100.00')).quantize(Decimal('0.01')) if pv > Decimal('0.00') else Decimal('0.00')

        # تقييم الحالة الزمنية
        if spi > Decimal('1.05'):
            spi_status = 'AHEAD'
            spi_label = _('متقدم عن الجدول الزمني')
            spi_class = 'text-success'
        elif spi >= Decimal('0.95'):
            spi_status = 'ON_TRACK'
            spi_label = _('منضبط مع الجدول الزمني')
            spi_class = 'text-primary'
        else:
            spi_status = 'BEHIND'
            spi_label = _('متأخر عن الجدول الزمني')
            spi_class = 'text-danger'

        # انحراف الأيام
        schedule_variance_days = 0
        if activity.actual_end_date and activity.baseline_end_date:
            schedule_variance_days = (activity.actual_end_date - activity.baseline_end_date).days
        elif activity.baseline_end_date and eval_date > activity.baseline_end_date and actual_pct < Decimal('100.00'):
            schedule_variance_days = (eval_date - activity.baseline_end_date).days

        return {
            'activity_id': activity.id,
            'code': activity.code,
            'name': activity.name,
            'bac': bac,
            'planned_pct': planned_pct,
            'actual_pct': actual_pct,
            'pv': pv,
            'ev': ev,
            'ac': ac,
            'sv': sv,
            'cv': cv,
            'sv_pct': sv_pct,
            'cv_pct': cv_pct,
            'spi': spi,
            'cpi': cpi,
            'eac': eac,
            'vac': vac,
            'has_actual_cost': has_actual_cost,
            'cost_data_status': cost_data_status,
            'spi_status': spi_status,
            'spi_label': spi_label,
            'spi_class': spi_class,
            'cpi_status': cpi_status,
            'cpi_label': cpi_label,
            'cpi_class': cpi_class,
            'schedule_variance_days': schedule_variance_days,
        }

    @classmethod
    def calculate_project_evm(
        cls,
        project: RealEstateProject,
        as_of_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        احتساب كافة مؤشرات القيمة المكتسبة للمشروع العقاري ككل:
        """
        eval_date = as_of_date or timezone.localdate()

        root_activities = list(project.wbs_activities.filter(parent_activity__isnull=True))

        total_bac = project.total_budget_cost
        if total_bac <= Decimal('0.00') and root_activities:
            total_bac = sum((cls.get_activity_bac(r) for r in root_activities), Decimal('0.00'))

        # حساب التقدم المخطط الكلي للمشروع
        if root_activities:
            total_root_weights = sum((r.weight_percentage for r in root_activities), Decimal('0.0000'))
            if total_root_weights > Decimal('0.0000'):
                total_planned_sum = sum(
                    (cls.calculate_activity_planned_progress(r, eval_date) * (r.weight_percentage / Decimal('100.0000')) for r in root_activities),
                    Decimal('0.0000')
                )
                project_planned_pct = (total_planned_sum / (total_root_weights / Decimal('100.0000'))).quantize(Decimal('0.01'))
            else:
                avg_planned = sum((cls.calculate_activity_planned_progress(r, eval_date) for r in root_activities), Decimal('0.00')) / Decimal(len(root_activities))
                project_planned_pct = avg_planned.quantize(Decimal('0.01'))
        else:
            # من جدول المشروع الزمني العام
            total_days = (project.expected_completion_date - project.start_date).days if (project.expected_completion_date and project.start_date) else 0
            if total_days > 0 and eval_date >= project.start_date:
                elapsed = (eval_date - project.start_date).days
                project_planned_pct = (Decimal(elapsed) / Decimal(total_days) * Decimal('100.00')).quantize(Decimal('0.01'))
                project_planned_pct = max(Decimal('0.00'), min(Decimal('100.00'), project_planned_pct))
            else:
                project_planned_pct = Decimal('0.00')

        project_actual_pct = project.construction_progress_percentage

        eff_project_bac = total_bac if total_bac > Decimal('0.00') else Decimal('1000000.00')
        project_pv = (eff_project_bac * (project_planned_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
        project_ev = (eff_project_bac * (project_actual_pct / Decimal('100.00'))).quantize(Decimal('0.01'))

        # التكلفة الفعلية للمشروع (الحفاظ على التكاليف المسجلة دون استبدالها بالقيمة المكتسبة)
        if root_activities:
            total_ac = sum((cls.get_activity_actual_cost(r) for r in root_activities), Decimal('0.00'))
        else:
            total_ac = Decimal('0.00')

        project_ac = total_ac
        project_sv = project_ev - project_pv
        project_sv_pct = ((project_sv / project_pv) * Decimal('100.00')).quantize(Decimal('0.01')) if project_pv > Decimal('0.00') else Decimal('0.00')

        if project_ac > Decimal('0.00'):
            project_cv = project_ev - project_ac
            project_cv_pct = ((project_cv / project_ev) * Decimal('100.00')).quantize(Decimal('0.01')) if project_ev > Decimal('0.00') else Decimal('0.00')
            project_cpi = (project_ev / project_ac).quantize(Decimal('0.01'))
            if project_cpi > Decimal('0.00'):
                project_eac = (total_bac / project_cpi).quantize(Decimal('0.01')) if total_bac > Decimal('0.00') else eff_project_bac
                project_vac = total_bac - project_eac
            else:
                project_eac = None
                project_vac = None
            has_actual_cost = True
            cost_data_status = 'RECORDED'
        elif project_ev == Decimal('0.00') and project_ac == Decimal('0.00'):
            project_cv = Decimal('0.00')
            project_cv_pct = Decimal('0.00')
            project_cpi = Decimal('1.00')
            project_eac = total_bac
            project_vac = Decimal('0.00')
            has_actual_cost = True
            cost_data_status = 'ZERO_COST'
        else:
            project_cv = Decimal('0.00')
            project_cv_pct = Decimal('0.00')
            project_cpi = None
            project_eac = total_bac
            project_vac = Decimal('0.00')
            has_actual_cost = False
            cost_data_status = 'UNAVAILABLE'

        # مؤشر الأداء الزمني للمشروع
        if project_pv > Decimal('0.00'):
            project_spi = (project_ev / project_pv).quantize(Decimal('0.01'))
        elif project_planned_pct == Decimal('0.00') and project_actual_pct == Decimal('0.00'):
            project_spi = Decimal('1.00')
        elif project_planned_pct == Decimal('0.00') and project_actual_pct > Decimal('0.00'):
            project_spi = Decimal('2.00')
        else:
            project_spi = Decimal('1.00')

        # التقييم الشامل لصحة المشروع (Health Rating)
        if project_cpi is not None:
            if project_spi >= Decimal('0.95') and project_cpi >= Decimal('0.95'):
                health_status = 'HEALTHY'
                health_badge = 'bg-success-subtle text-success border-success-subtle'
                health_label = _('مشروع منضبط وممتاز (سليماً زمنياً ومالياً)')
            elif project_spi < Decimal('0.95') and project_cpi >= Decimal('0.95'):
                health_status = 'SCHEDULE_DELAY'
                health_badge = 'bg-warning-subtle text-warning border-warning-subtle'
                health_label = _('تأخير في الجدول الزمني مع ضبط التكاليف')
            elif project_spi >= Decimal('0.95') and project_cpi < Decimal('0.95'):
                health_status = 'COST_OVERRUN'
                health_badge = 'bg-warning-subtle text-danger border-warning-subtle'
                health_label = _('تجاوز في الموازنة مع التزام الجدول الزمني')
            else:
                health_status = 'CRITICAL'
                health_badge = 'bg-danger-subtle text-danger border-danger-subtle'
                health_label = _('مخاطر حرجة: تأخير زمني وتجاوز مالي')
        else:
            if project_spi >= Decimal('0.95'):
                health_status = 'ON_TRACK'
                health_badge = 'bg-primary-subtle text-primary border-primary-subtle'
                health_label = _('منضبط بالجدول الزمني (بانتظار تسجيل التكاليف الفعلية)')
            else:
                health_status = 'SCHEDULE_DELAY'
                health_badge = 'bg-warning-subtle text-warning border-warning-subtle'
                health_label = _('تأخير في الجدول الزمني (بانتظار تسجيل التكاليف الفعلية)')

        return {
            'project_id': project.id,
            'project_name': project.name,
            'total_bac': total_bac,
            'planned_pct': project_planned_pct,
            'actual_pct': project_actual_pct,
            'pv': project_pv,
            'ev': project_ev,
            'ac': project_ac,
            'sv': project_sv,
            'cv': project_cv,
            'sv_pct': project_sv_pct,
            'cv_pct': project_cv_pct,
            'spi': project_spi,
            'cpi': project_cpi,
            'eac': project_eac,
            'vac': project_vac,
            'has_actual_cost': has_actual_cost,
            'cost_data_status': cost_data_status,
            'health_status': health_status,
            'health_badge': health_badge,
            'health_label': health_label,
            'as_of_date': eval_date,
        }

    @classmethod
    def generate_s_curve_data(
        cls,
        project: RealEstateProject,
        intervals: int = 12
    ) -> List[Dict[str, Any]]:
        """
        توليد نقاط منحنى التقدم الهندسي التراكمي (S-Curve):
        - يقسم الفترة بين بدء المشروع ونهايته إلى فترات زمنية متساوية.
        - يحسب في كل نقطة: النسبة المخططة التراكمية، النسبة الفعلية المكتسبة، ونسبة التكلفة.
        """
        today = timezone.localdate()
        start_d = project.start_date or (today - timedelta(days=90))
        end_d = project.expected_completion_date or (today + timedelta(days=270))

        total_days = max(1, (end_d - start_d).days)
        step_days = max(1, total_days // intervals)

        data_points = []
        curr_d = start_d
        while curr_d <= end_d:
            planned_p = cls.calculate_project_evm(project, as_of_date=curr_d)['planned_pct']

            # النسبة الفعلية تظهر فقط حتى تاريخ اليوم
            if curr_d <= today:
                # إذا كانت النقطة اليوم، نأخذ النسبة الحالية الفعلية
                if (today - curr_d).days < step_days:
                    actual_p = project.construction_progress_percentage
                else:
                    # تقدير استرجاعي تقريبي
                    actual_p = min(project.construction_progress_percentage, planned_p)
                actual_cost_p = actual_p
            else:
                actual_p = None
                actual_cost_p = None

            data_points.append({
                'date': curr_d.strftime('%Y-%m-%d'),
                'label': curr_d.strftime('%b %Y'),
                'planned_pct': float(planned_p),
                'actual_pct': float(actual_p) if actual_p is not None else None,
                'actual_cost_pct': float(actual_cost_p) if actual_cost_p is not None else None,
            })
            curr_d += timedelta(days=step_days)

        # ضمان إدراج نقطة النهاية (100% مخطط) بدقة
        if not data_points or data_points[-1]['date'] != end_d.strftime('%Y-%m-%d'):
            data_points.append({
                'date': end_d.strftime('%Y-%m-%d'),
                'label': end_d.strftime('%b %Y'),
                'planned_pct': 100.0,
                'actual_pct': float(project.construction_progress_percentage) if today >= end_d else None,
                'actual_cost_pct': float(project.construction_progress_percentage) if today >= end_d else None,
            })

        return data_points
