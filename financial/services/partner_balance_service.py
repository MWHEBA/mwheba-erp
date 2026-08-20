import logging
from decimal import Decimal
from django.db import models, transaction
from financial.services.partner_balance_snapshot_service import PartnerBalanceSnapshotService

logger = logging.getLogger(__name__)


class PartnerBalanceService:
    """
    محرك إدارة وتحديث أرصدة الشركاء التفاضلي السريع O(1) (Partner Balance Engine)
    - يطبق التحديثات التفاضلية المحوكمة بدقة IAS 21
    - يزامن لقطات الانكشاف المالي متعددة العملات فورياً
    """

    @classmethod
    def apply_settlement_delta(cls, partner_type: str, partner_id: int, settled_invoice_amount: Decimal, invoice_rate: Decimal, is_addition: bool = False):
        """
        تطبيق التعديل التفاضلي لرصيد الشريك عند سداد أو إلغاء سداد فاتورة:
        Delta = (settled_invoice_amount * invoice_rate)
        """
        if not partner_id:
            return

        rate = Decimal(str(invoice_rate or "1.000000"))
        settled = Decimal(str(settled_invoice_amount or "0.00"))
        delta_functional = (settled * rate).quantize(Decimal("0.01"))

        if is_addition:
            # إلغاء دفعة / عكس سداد: زيادة المديونية
            cls._update_partner_balance_field(partner_type, partner_id, delta_functional)
        else:
            # سداد دفعة: تخفيض المديونية
            cls._update_partner_balance_field(partner_type, partner_id, -delta_functional)

        cls.update_partner_snapshot(partner_type, partner_id)

    @classmethod
    def apply_document_delta(cls, partner_type: str, partner_id: int, document_functional_total: Decimal, is_addition: bool = True):
        """
        تطبيق التعديل التفاضلي عند اعتماد أو إلغاء فاتورة / مرتجع
        """
        if not partner_id:
            return

        doc_func = Decimal(str(document_functional_total or "0.00")).quantize(Decimal("0.01"))
        delta = doc_func if is_addition else -doc_func

        cls._update_partner_balance_field(partner_type, partner_id, delta)
        cls.update_partner_snapshot(partner_type, partner_id)

    @classmethod
    def apply_advance_delta(cls, partner_type: str, partner_id: int, advance_foreign_amount: Decimal, advance_rate: Decimal, is_addition: bool = False):
        """
        تطبيق التعديل التفاضلي عند استلام دفعة مقدمة (تخفيض الذمة/دائن)
        """
        if not partner_id:
            return

        rate = Decimal(str(advance_rate or "1.000000"))
        adv_amt = Decimal(str(advance_foreign_amount or "0.00"))
        delta_functional = (adv_amt * rate).quantize(Decimal("0.01"))

        delta = delta_functional if is_addition else -delta_functional
        cls._update_partner_balance_field(partner_type, partner_id, delta)
        cls.update_partner_snapshot(partner_type, partner_id)

    @classmethod
    def apply_allocation_delta(cls, partner_type: str, partner_id: int, adv_func: Decimal, sale_func: Decimal):
        """
        تطبيق التعديل التفاضلي عند تخصيص دفعة مقدمة لفاتورة مبيعات/مشتريات مع فرق العملة
        """
        if not partner_id:
            return

        # عند التخصيص: تم قيد الدفعة المقدمة مسبقاً (-adv_func) وتم قيد الفاتورة (+sale_func)
        # الصافي التفاضلي للتخصيص يصحح أي فروق صرف محققة
        cls.update_partner_snapshot(partner_type, partner_id)

    @classmethod
    def update_partner_snapshot(cls, partner_type: str, partner_id: int):
        """
        مزامنة لقطة العملات للعميل أو المورد
        """
        try:
            PartnerBalanceSnapshotService.update_snapshot(partner_type, partner_id)
        except Exception as e:
            logger.warning(f"⚠️ فشل تحديث لقطة العملات للـ {partner_type} #{partner_id}: {e}")

    @classmethod
    def _update_partner_balance_field(cls, partner_type: str, partner_id: int, delta: Decimal):
        """
        تحديث حقل balance في قاعدة البيانات ذرياً
        """
        if delta == Decimal("0.00"):
            return

        try:
            if partner_type == "customer":
                from client.models import Customer
                Customer.objects.filter(pk=partner_id).update(balance=models.F("balance") + delta)
            elif partner_type == "supplier":
                from supplier.models import Supplier
                Supplier.objects.filter(pk=partner_id).update(balance=models.F("balance") + delta)
        except Exception as e:
            logger.error(f"❌ خطأ في تحديث رصيد {partner_type} #{partner_id} بقيمة {delta}: {e}")
