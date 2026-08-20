import logging
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from financial.services.partner_subledger_service import PartnerSubledgerService
from financial.services.partner_balance_service import PartnerBalanceService

logger = logging.getLogger(__name__)


class PaymentManagementService:
    """
    خدمة إدارة وحوكمة دورة حياة المدفوعات (Payment Management & Governance Service)
    - حظر التعديل أو الحذف المباشر في الفترات المالية المغلقة
    - عكس القيود المحاسبية عبر AccountingGateway
    - استعادة الأستاذ المساعد وأعمار الديون
    - تطبيق التعديل التفاضلي لرصيد الشريك
    - تصفير كسور الأقساط التراكمية (Penny Auto-Clear)
    """

    @classmethod
    def delete_payment(cls, payment, user=None):
        """
        حذف دفعة محوكم ومؤمن بالكامل
        """
        if not payment:
            return False

        with transaction.atomic():
            # 1. التحقق من صلاحيات المستخدم (RBAC Guard)
            if user and not (user.is_superuser or user.is_staff or user.has_perm("financial.delete_payment") or user.has_perm("sale.delete_salepayment") or user.has_perm("purchase.delete_purchasepayment")):
                raise ValidationError(_("ليس لديك الصلاحية الكافية لحذف هذه الدفعة المالية."))

            # 2. التحقق من حظر الفترات المالية المغلقة
            pmt_date = getattr(payment, "payment_date", None)
            if pmt_date:
                from financial.models import AccountingPeriod
                period = AccountingPeriod.objects.filter(
                    start_date__lte=pmt_date,
                    end_date__gte=pmt_date
                ).first()
                if period and period.status == "closed":
                    raise ValidationError(_("لا يمكن حذف الدفعة لأنها تقع في فترة مالية مغلقة. يرجى استخدام قيد تسوية عكسي."))

            # 3. تحديد الفاتورة والشريك
            sale = getattr(payment, "sale", None)
            purchase = getattr(payment, "purchase", None)

            partner_type = "customer" if sale else ("supplier" if purchase else None)
            partner = sale.customer if sale else (purchase.supplier if purchase else None)

            # 3. عكس أو حذف القيد المحاسبي المرتبط
            if payment.financial_transaction:
                try:
                    from financial.services.accounting_gateway import AccountingGateway
                    AccountingGateway.reverse_journal_entry(
                        journal_entry_id=payment.financial_transaction.id,
                        user=user,
                        reason=f"إلغاء دفعة #{payment.id}"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ لم يتم عكس القيد المحاسبي عبر Gateway، سيتم فك الارتباط: {e}")

            # 4. حساب المعادل الدفتري المستعاد
            rate = Decimal("1.000000")
            if sale:
                rate = Decimal(str(getattr(sale, "exchange_rate", "1.000000") or "1.000000"))
            elif purchase:
                rate = Decimal(str(getattr(purchase, "exchange_rate", "1.000000") or "1.000000"))

            settled = getattr(payment, "amount_settled_invoice_currency", payment.amount) or payment.amount

            # 5. حذف سجل الدفعة
            payment_id = payment.id
            payment.delete()

            # 6. استعادة رصيد الشريك تفاضلياً
            if partner and partner_type:
                PartnerBalanceService.apply_settlement_delta(
                    partner_type=partner_type,
                    partner_id=partner.id,
                    settled_invoice_amount=settled,
                    invoice_rate=rate,
                    is_addition=True
                )

            # 7. تحديث الأستاذ المساعد وأعمار الديون
            if sale:
                PartnerSubledgerService.record_sale_invoice(sale, user)
                sale.update_payment_status()
            elif purchase:
                PartnerSubledgerService.record_purchase_bill(purchase, user)
                purchase.update_payment_status()

            logger.info(f"✅ تم حذف الدفعة #{payment_id} وعكس أثرها المحاسبي بنجاح")
            return True
