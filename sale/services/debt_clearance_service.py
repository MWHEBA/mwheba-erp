# -*- coding: utf-8 -*-
"""
FIN-SAL-INS-006: DebtClearanceCertificateService
محرك إصدار شهادات المخالصة المالية الرسمية وإبراء الذمة للعملاء (I-Score Clearance)
شروط وقواعد الحوكمة الصارمة:
1. تصفير كامل رصيد العميل دفترياً (Customer.balance <= 0) وانعدام أي أقساط معلقة أو متأخرة.
2. مرور 5 أيام عمل مصرفية على الأقل على تحصيل آخر شيك بنكي لتفادي مخاطر الارتداد المتأخر.
3. تسليم واسترداد كافة شيكات الضمان المسلمة للعميل (RETURNED_TO_DRAWER).
"""
import uuid
from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, List
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from customer.models import Customer
from sale.models.installments import InstallmentItem, InstallmentCashStatus
from cheques.models.cheque import Cheque


class DebtClearanceCertificateService:
    """
    حوكمة وإصدار شهادة المخالصة وإبراء الذمة الرسمية للعملاء
    """

    MIN_BANK_CLEARING_BUSINESS_DAYS = 5

    @classmethod
    def verify_clearance_eligibility(cls, customer: Customer) -> Dict[str, Any]:
        """
        فحص استيفاء العميل لشروط استخراج المخالصة الرسمية
        """
        if not customer:
            raise ValidationError(_("يجب تحديد العميل المراد فحص مخالصته."))

        blocking_reasons: List[str] = []
        now_date = timezone.localdate()

        # 1. فحص رصيد العميل المالي القائم
        current_balance = getattr(customer, 'balance', Decimal("0.00")) or Decimal("0.00")
        if current_balance > Decimal("0.00"):
            blocking_reasons.append(
                f"العميل مدين برصيد تجاري قائم قدره {current_balance:,.2f} ج.م."
            )

        # 2. فحص الأقساط المجدولة غير المسددة
        unsettled_items = InstallmentItem.objects.filter(
            plan__sale__customer=customer
        ).exclude(
            cash_status__in=[InstallmentCashStatus.COLLECTED, InstallmentCashStatus.WAIVED]
        )
        if unsettled_items.exists():
            count = unsettled_items.count()
            blocking_reasons.append(
                f"يوجد عدد {count} قسط غير مسدد أو معلق لنزاع تشغيل/قضائي."
            )

        # 3. فحص مرور 5 أيام مصرفية على آخر شيك محصل
        customer_cheques = Cheque.objects.filter(
            customer=customer,
            cheque_type="RECEIVABLE"
        )
        last_collected_cheque = customer_cheques.filter(
            status="COLLECTED"
        ).order_by("-collection_date", "-cleared_at", "-id").first()

        last_cleared_date = None
        if last_collected_cheque:
            last_cleared_date = (
                getattr(last_collected_cheque, 'collection_date', None) or
                (last_collected_cheque.cleared_at.date() if getattr(last_collected_cheque, 'cleared_at', None) else None) or
                last_collected_cheque.due_date
            )
            if last_cleared_date:
                # 5 أيام عمل تقابل تقريباً 7 أيام تقويمية استيعاباً لعطلة نهاية الأسبوع
                min_days_required = 7
                days_since_cleared = (now_date - last_cleared_date).days
                if days_since_cleared < min_days_required:
                    blocking_reasons.append(
                        f"لم يمر 5 أيام عمل مصرفية على تمام مقاصة آخر شيك محصل #{last_collected_cheque.cheque_number} "
                        f"(تم التحصيل في {last_cleared_date}، مضى {days_since_cleared} يوماً فقط - المطلوب {min_days_required} أيام على الأقل منعاً لمخاطر الارتداد العكسي)."
                    )

        # 4. فحص استرداد شيكات الضمان المسلمة
        from cheques.models import ChequePurpose, ChequeStatus
        unreturned_collateral = customer_cheques.filter(
            models.Q(purpose=ChequePurpose.SECURITY_GUARANTEE) | models.Q(secured_installment_plans__isnull=False)
        ).exclude(
            status__in=[ChequeStatus.RETURNED_TO_DRAWER, ChequeStatus.CANCELLED]
        ).distinct()
        if unreturned_collateral.exists():
            cheque_nums = ", ".join(unreturned_collateral.values_list('cheque_number', flat=True)[:3])
            blocking_reasons.append(
                f"توجد شيكات ضمان محتجزة بالخزينة لم يتم إثبات تسليمها للعميل بمحضر استلام رسمي (الشيكات: {cheque_nums})."
            )

        is_eligible = len(blocking_reasons) == 0

        return {
            "eligible": is_eligible,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "current_balance": current_balance,
            "blocking_reasons": blocking_reasons,
            "last_cleared_date": last_cleared_date,
        }

    @classmethod
    def issue_clearance_certificate(
        cls,
        customer: Customer,
        issued_by=None,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        إصدار وثيقة المخالصة المالية وإبراء الذمة الرسمية بعد التحقق التام
        """
        check_result = cls.verify_clearance_eligibility(customer)
        if not check_result["eligible"]:
            reasons_str = " | ".join(check_result["blocking_reasons"])
            raise ValidationError(
                _(f"لا يمكن استخراج شهادة المخالصة للعميل {customer.name} للأسباب التالية: {reasons_str}")
            )

        cert_ref = f"CERT-CLR-{customer.id}-{uuid.uuid4().hex[:8].upper()}"
        issue_date = timezone.localdate()

        certificate_data = {
            "certificate_number": cert_ref,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "tax_number": getattr(customer, 'tax_number', '') or '-',
            "commercial_register": getattr(customer, 'commercial_register', '') or '-',
            "issue_date": issue_date,
            "issued_by": getattr(issued_by, 'get_full_name', lambda: str(issued_by))() if issued_by else "النظام الآلي",
            "notes": notes or _("مخالصة مالية نهائية تفيد براءة ذمة العميل من كافة الالتزامات والأقساط والشيكات المرتبطة."),
            "verified_zero_balance": True,
        }

        return certificate_data
