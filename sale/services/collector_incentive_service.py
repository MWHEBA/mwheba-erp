# -*- coding: utf-8 -*-
"""
FIN-SAL-INS-005: CollectorIncentiveService
محرك حوافز التحصيل المتدرجة المتناقصة للمحصلين ومسؤولي المبيعات
- بونص التسريع المبكر (+0.5%) عند التحصيل قبل تاريخ الاستحقاق بـ 5 أيام فأكثر
- نسبة 100% من الحافز الأساسي عند التحصيل في الميعاد أو خلال فترة السماح
- تناقص الحافز بنسبة 20% أسبوعياً عند التأخير بعد فترة السماح
"""
from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, Optional
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from sale.models.installments import InstallmentItem


class CollectorIncentiveService:
    """
    حساب عمولات وحوافز التحصيل الميداني والمكتبي وفق مبدأ الجدارة وسرعة التدفق النقدي
    """

    DEFAULT_BASE_RATE = Decimal("0.02")  # 2% عمولة أساسية
    EARLY_ACCELERATION_BONUS = Decimal("0.005")  # +0.5% بونص تسريع مبكر (>= 5 أيام)
    WEEKLY_DECAY_RATE = Decimal("0.20")  # تناقص 20% أسبوعياً للتأخير

    @classmethod
    def calculate_incentive(
        cls,
        installment_item: InstallmentItem,
        payment_date: Optional[timezone.datetime.date] = None,
        base_rate: Optional[Decimal] = None,
        collected_amount: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        احتساب حافز التحصيل لقسط محدد:
        - installment_item: القسط المحصل
        - payment_date: تاريخ التحصيل الفعلي (الافتراضي: اليوم)
        - base_rate: النسبة الأساسية للحافز (الافتراضي: 2%)
        - collected_amount: المبلغ المحصل الفعلي (الافتراضي: paid_principal أو principal_amount)
        """
        if not installment_item:
            raise ValidationError(_("يجب تحديد القسط المراد حساب حافز تحصيله."))

        pay_date = payment_date or installment_item.paid_date or timezone.localdate()
        base = base_rate if base_rate is not None else cls.DEFAULT_BASE_RATE

        # المبلغ المعتمد لاحتساب العمولة (أصل الدين المحصل فقط مستبعداً منه الفوائد والغرامات)
        amount = collected_amount if collected_amount is not None else (
            installment_item.paid_principal if installment_item.paid_principal > Decimal("0.00")
            else installment_item.principal_amount
        )

        due_date = installment_item.due_date
        grace_days = installment_item.grace_period_days or 0
        grace_end_date = due_date + timedelta(days=grace_days)

        early_bonus_applied = False
        weeks_overdue = 0
        decay_factor = Decimal("1.00")
        effective_rate = base

        # 1. حالة التسريع المبكر (قبل الاستحقاق بـ 5 أيام على الأقل)
        if pay_date <= (due_date - timedelta(days=5)):
            early_bonus_applied = True
            effective_rate = base + cls.EARLY_ACCELERATION_BONUS

        # 2. حالة التحصيل في الميعاد أو خلال فترة السماح
        elif pay_date <= grace_end_date:
            effective_rate = base

        # 3. حالة التأخير بعد فترة السماح (تناقص الحافز 20% أسبوعياً)
        else:
            days_late = (pay_date - grace_end_date).days
            # احتساب عدد الأسابيع (كل 7 أيام أو جزء منها يعتبر أسبوعاً)
            weeks_overdue = (days_late + 6) // 7
            decay = cls.WEEKLY_DECAY_RATE * Decimal(str(weeks_overdue))
            decay_factor = max(Decimal("0.00"), Decimal("1.00") - decay)
            effective_rate = (base * decay_factor).quantize(Decimal("0.0001"))

        incentive_amount = (amount * effective_rate).quantize(Decimal("0.01"))

        return {
            "installment_id": installment_item.id,
            "installment_number": installment_item.installment_number,
            "due_date": due_date,
            "payment_date": pay_date,
            "base_amount": amount,
            "base_rate": base,
            "effective_rate": effective_rate,
            "early_bonus_applied": early_bonus_applied,
            "weeks_overdue": weeks_overdue,
            "decay_factor": decay_factor,
            "incentive_amount": incentive_amount,
        }
