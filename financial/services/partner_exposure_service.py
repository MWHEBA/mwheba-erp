import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db.models import Sum, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class PartnerExposureDTO:
    """
    Data Transfer Object (DTO) يمثل انكشاف الشريك المالي بالعملة الواحدة
    """
    def __init__(
        self,
        partner_id: int,
        partner_type: str,
        currency: str,
        debit: Decimal,
        credit: Decimal,
        net_balance: Decimal,
        functional_net_balance: Decimal,
        nature: str, # PAYABLE / RECEIVABLE / ZERO
        raw_balance: Decimal
    ):
        self.partner_id = partner_id
        self.partner_type = partner_type
        self.currency = currency
        self.debit = debit
        self.credit = credit
        self.net_balance = net_balance
        self.functional_net_balance = functional_net_balance
        self.nature = nature
        self.raw_balance = raw_balance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "partner_id": self.partner_id,
            "partner_type": self.partner_type,
            "currency": self.currency,
            "debit": float(self.debit),
            "credit": float(self.credit),
            "net_balance": float(self.net_balance),
            "functional_net_balance": float(self.functional_net_balance),
            "nature": self.nature,
            "raw_balance": float(self.raw_balance),
        }


class BusinessPartnerExposureDTO(PartnerExposureDTO):
    """Alias for BusinessPartnerExposureDTO"""
    pass


class BusinessPartnerExposureService:
    """
    الخدمة المعتمدة لحساب وتجميع الانكشافات المالية لشركاء الأعمال التجاريين (الموردين والعملاء) لكل عملة
    Enterprise Multi-Currency Business Partner Subledger & Exposure Engine (IAS 21 Compliant)
    """

    @classmethod
    def get_open_balances(
        cls,
        partner_type: str,
        partner_ids: List[int],
        include_children: bool = False,
        as_of_date: Optional[Any] = None
    ) -> Dict[int, List[PartnerExposureDTO]]:
        """
        جلب الانكشافات المالية المفتوحة المجمعة لجميع الشركاء المحددين دفعة واحدة (Bulk Aggregation - No N+1 Queries)
        :param partner_type: 'supplier' أو 'customer'
        :param partner_ids: قائمة معرقات الشركاء
        :param include_children: تجميع الفروع والمؤسسات التابعة للمورد القابض
        :return: قاموس يربط partner_id بقائمة من PartnerExposureDTO
        """
        if not partner_ids:
            return {}

        results: Dict[int, List[PartnerExposureDTO]] = {pid: [] for pid in partner_ids}

        # تحديد النماذج المناسبة
        if partner_type == "supplier":
            from supplier.models import Supplier, SupplierTransaction
            from purchase.models import Purchase
            partners_map = {s.id: s for s in Supplier.objects.filter(id__in=partner_ids).select_related('default_currency')}
            partner_currency_map: Dict[int, Dict[str, Dict[str, Decimal]]] = {}

            # تجميع فواتير المشتريات غير المسددة بالكامل لكل عملة
            purchases = Purchase.objects.filter(
                supplier_id__in=partner_ids
            ).exclude(payment_status="paid").select_related("currency")

            purchase_numbers = set()
            for p in purchases:
                purchase_numbers.add(p.number)
                pid = p.supplier_id
                curr = p.currency.code if p.currency else "EGP"
                due = p.amount_due if hasattr(p, "amount_due") and p.amount_due > Decimal("0.00") else (p.total - (p.amount_paid or Decimal("0.00")))
                if due <= Decimal("0.00"):
                    continue
                rate = p.exchange_rate or Decimal("1.000000")
                open_func = (due * rate).quantize(Decimal("0.01"))

                if pid not in partner_currency_map:
                    partner_currency_map[pid] = {}
                if curr not in partner_currency_map[pid]:
                    partner_currency_map[pid][curr] = {"foreign": Decimal("0.00"), "functional": Decimal("0.00")}

                partner_currency_map[pid][curr]["foreign"] += due
                partner_currency_map[pid][curr]["functional"] += open_func

            # تجميع المعاملات المفتوحة المعتمدة من SupplierTransaction غير المرتبطة بفواتير مشتريات لمنع الازدواجية
            txns_qs = SupplierTransaction.objects.filter(
                supplier_id__in=partner_ids,
                open_amount__gt=Decimal("0.00")
            ).exclude(transaction_number__in=purchase_numbers).values("supplier_id", "currency").annotate(
                total_open_foreign=Sum("open_amount_foreign"),
                total_open_functional=Sum("open_amount_functional")
            )
            for item in txns_qs:
                pid = item["supplier_id"]
                curr = item["currency"] or "EGP"
                open_foreign = item["total_open_foreign"] or Decimal("0.00")
                open_func = item["total_open_functional"] or Decimal("0.00")

                if pid not in partner_currency_map:
                    partner_currency_map[pid] = {}
                if curr not in partner_currency_map[pid]:
                    partner_currency_map[pid][curr] = {"foreign": Decimal("0.00"), "functional": Decimal("0.00")}

                partner_currency_map[pid][curr]["foreign"] += open_foreign
                partner_currency_map[pid][curr]["functional"] += open_func

            # تجميع النتائج لجميع الموردين المطلوبة
            for pid in partner_ids:
                supplier = partners_map.get(pid)
                curr_data = partner_currency_map.get(pid, {})

                if curr_data:
                    for curr, val in curr_data.items():
                        open_foreign = val["foreign"]
                        open_func = val["functional"]
                        val_to_use = open_foreign if (open_foreign > Decimal("0.00") or curr != "EGP") else open_func
                        if val_to_use > Decimal("0.00") or open_func > Decimal("0.00"):
                            dto = PartnerExposureDTO(
                                partner_id=pid,
                                partner_type="supplier",
                                currency=curr,
                                debit=Decimal("0.00"),
                                credit=val_to_use,
                                net_balance=val_to_use,
                                functional_net_balance=open_func if open_func > Decimal("0.00") else val_to_use,
                                nature="PAYABLE",
                                raw_balance=-val_to_use
                            )
                            results[pid].append(dto)

                # Fallback آمن للموردين الذين لا يملكون سجلات مفتوحة مفصلة ويملكون رصيداً في balance
                if not results[pid] and supplier:
                    supplier_balance = supplier.balance or Decimal("0.00")
                    if supplier_balance != Decimal("0.00"):
                        default_curr_code = supplier.default_currency.code if supplier.default_currency else "EGP"
                        nature = "PAYABLE" if supplier_balance > Decimal("0.00") else "RECEIVABLE"
                        abs_balance = abs(supplier_balance)
                        dto = PartnerExposureDTO(
                            partner_id=pid,
                            partner_type="supplier",
                            currency=default_curr_code,
                            debit=Decimal("0.00") if nature == "PAYABLE" else abs_balance,
                            credit=abs_balance if nature == "PAYABLE" else Decimal("0.00"),
                            net_balance=abs_balance,
                            functional_net_balance=abs_balance,
                            nature=nature,
                            raw_balance=-supplier_balance if nature == "PAYABLE" else supplier_balance
                        )
                        results[pid].append(dto)

        elif partner_type == "customer":
            from customer.models import Customer, CustomerTransaction
            from sale.models import Sale
            customers_map = {c.id: c for c in Customer.objects.filter(id__in=partner_ids).select_related('default_currency')}
            partner_currency_map: Dict[int, Dict[str, Dict[str, Decimal]]] = {}

            # تجميع فواتير المبيعات غير المسددة بالكامل لكل عملة
            sales = Sale.objects.filter(
                customer_id__in=partner_ids
            ).exclude(payment_status="paid").select_related("currency")

            sale_numbers = set()
            for s in sales:
                sale_numbers.add(s.number)
                pid = s.customer_id
                curr = s.currency.code if s.currency else "EGP"
                due = s.amount_due if hasattr(s, "amount_due") and s.amount_due > Decimal("0.00") else (s.total - (s.amount_paid or Decimal("0.00")))
                if due <= Decimal("0.00"):
                    continue
                rate = s.exchange_rate or Decimal("1.000000")
                open_func = (due * rate).quantize(Decimal("0.01"))

                if pid not in partner_currency_map:
                    partner_currency_map[pid] = {}
                if curr not in partner_currency_map[pid]:
                    partner_currency_map[pid][curr] = {"foreign": Decimal("0.00"), "functional": Decimal("0.00")}

                partner_currency_map[pid][curr]["foreign"] += due
                partner_currency_map[pid][curr]["functional"] += open_func

            # تجميع المعاملات المفتوحة المعتمدة من CustomerTransaction غير المرتبطة بفواتير مبيعات لمنع الازدواجية
            txns_qs = CustomerTransaction.objects.filter(
                customer_id__in=partner_ids,
                open_amount__gt=Decimal("0.00")
            ).exclude(transaction_number__in=sale_numbers).values("customer_id", "currency").annotate(
                total_open_foreign=Sum("open_amount_foreign"),
                total_open_functional=Sum("open_amount_functional")
            )
            for item in txns_qs:
                pid = item["customer_id"]
                curr = item["currency"] or "EGP"
                open_foreign = item["total_open_foreign"] or Decimal("0.00")
                open_func = item["total_open_functional"] or Decimal("0.00")

                if pid not in partner_currency_map:
                    partner_currency_map[pid] = {}
                if curr not in partner_currency_map[pid]:
                    partner_currency_map[pid][curr] = {"foreign": Decimal("0.00"), "functional": Decimal("0.00")}

                partner_currency_map[pid][curr]["foreign"] += open_foreign
                partner_currency_map[pid][curr]["functional"] += open_func

            for pid in partner_ids:
                customer = customers_map.get(pid)
                curr_data = partner_currency_map.get(pid, {})

                if curr_data:
                    for curr, val in curr_data.items():
                        open_foreign = val["foreign"]
                        open_func = val["functional"]
                        val_to_use = open_foreign if (open_foreign > Decimal("0.00") or curr != "EGP") else open_func
                        if val_to_use > Decimal("0.00") or open_func > Decimal("0.00"):
                            dto = PartnerExposureDTO(
                                partner_id=pid,
                                partner_type="customer",
                                currency=curr,
                                debit=val_to_use,
                                credit=Decimal("0.00"),
                                net_balance=val_to_use,
                                functional_net_balance=open_func if open_func > Decimal("0.00") else val_to_use,
                                nature="RECEIVABLE",
                                raw_balance=val_to_use
                            )
                            results[pid].append(dto)

                # Fallback آمن للعملاء الذين لا يملكون سجلات تفصيلية مفتوحة ويملكون رصيداً في balance
                if not results[pid] and customer:
                    cust_balance = customer.balance or Decimal("0.00")
                    if cust_balance != Decimal("0.00"):
                        default_curr_code = customer.default_currency.code if customer.default_currency else "EGP"
                        nature = "RECEIVABLE" if cust_balance > Decimal("0.00") else "PAYABLE"
                        abs_balance = abs(cust_balance)
                        dto = PartnerExposureDTO(
                            partner_id=pid,
                            partner_type="customer",
                            currency=default_curr_code,
                            debit=abs_balance if nature == "RECEIVABLE" else Decimal("0.00"),
                            credit=Decimal("0.00") if nature == "RECEIVABLE" else abs_balance,
                            net_balance=abs_balance,
                            functional_net_balance=abs_balance,
                            nature=nature,
                            raw_balance=cust_balance if nature == "RECEIVABLE" else -cust_balance
                        )
                        results[pid].append(dto)

        return results


# Explicit Aliases for Enterprise Compatibility
PartnerExposureService = BusinessPartnerExposureService

