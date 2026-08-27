"""
Enterprise Tax Math Engine - Centralized Tax & Exemption Calculation Module
Implements Egyptian Tax Authority (ETA) line-level rounding standards,
compound table taxes, 3-tier customer exemption hierarchy, Pro-Rata discount distribution,
and SHA-256 cryptographic audit generation.
"""

from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Standard Decimal Quantizer for Currency (2 decimal places)
MONEY_QUANTIZE = Decimal("0.01")
RATE_QUANTIZE = Decimal("0.0001")


def quantize_money(value: Any) -> Decimal:
    """Quantize to 2 decimal places using standard ROUND_HALF_UP (Commercial Rounding)."""
    if value is None:
        return Decimal("0.00")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


class TaxMathEngine:
    """
    Unified Tax Math Engine for MWHEBA ERP.
    Responsible for all item-level and document-level tax computations.
    """

    @classmethod
    def compute_document_taxes(
        cls,
        items: List[Dict[str, Any]],
        global_discount: Any = Decimal("0.00"),
        adjustment_amount: Any = Decimal("0.00"),
        tax_active: bool = True,
        customer_exempt: bool = False,
        exemption_max_ceiling: Optional[Any] = None,
        exemption_utilized: Optional[Any] = None,
        wht_rate: Any = Decimal("0.00"),
        document_number: str = "",
    ) -> Dict[str, Any]:
        """
        Calculate complete tax breakdown for a list of document items.

        Parameters:
        -----------
        items: list of dicts with keys:
            - product_id or id
            - quantity (Decimal or float or str)
            - unit_price (Decimal or float or str)
            - discount (Decimal or float or str, line-level discount)
            - tax_rate (Decimal or float or str, percentage e.g. 14.00)
            - is_taxable (bool, optional, defaults to True if tax_rate > 0)
            - table_tax_rate (Decimal or float or str, optional percentage e.g. 5.00)
            - is_service (bool, optional)
            - name / code (optional for audit signature)
        global_discount: Overall document discount
        adjustment_amount: Shipping, delivery, or extra adjustments
        tax_active: Document-level master tax toggle (if False, all VAT = 0)
        customer_exempt: Whether customer has a valid tax exemption certificate
        exemption_max_ceiling: Certificate monetary ceiling cap
        exemption_utilized: Previously consumed certificate amount
        wht_rate: Withholding Tax Rate (e.g. 1.00 for 1% WHT)
        document_number: Document sequence number for audit hash

        Returns:
        --------
        dict with:
            - items: processed items list with line_subtotal, line_adj, line_net_base,
                     line_table_tax, line_tax_amount, line_wht_amount, line_total, effective_rate
            - subtotal: sum of line subtotals (gross before global discount)
            - taxable_subtotal: sum of net bases for items with effective tax rate > 0
            - exempt_subtotal: sum of net bases for items with effective tax rate == 0
            - global_discount: quantized global discount
            - adjustment_amount: quantized adjustment
            - net_subtotal: subtotal - global_discount + adjustment_amount
            - total_table_tax: sum of line_table_tax
            - total_tax (total_vat): sum of line_tax_amount (ETA compliant line-rounded sum)
            - total_wht: sum of line_wht_amount
            - total: net_subtotal + total_tax
            - net_payable: total - total_wht
            - form_10_boxes: dict classifying sales into ETA Form 10 return boxes
            - audit_signature: SHA-256 cryptographic signature of tax lines
        """
        global_discount = quantize_money(global_discount)
        adjustment_amount = quantize_money(adjustment_amount)
        wht_rate = quantize_money(wht_rate)

        # 1. First Pass: Compute Line Subtotals
        processed_items = []
        raw_doc_subtotal = Decimal("0.00")

        for idx, item in enumerate(items):
            qty = Decimal(str(item.get("quantity", 1) or 1))
            price = Decimal(str(item.get("unit_price", item.get("price", 0)) or 0))
            line_disc = Decimal(str(item.get("discount", 0) or 0))

            # Line subtotal = (Qty * Price) - Line Discount (cannot be negative)
            line_raw_subtotal = max(Decimal("0.00"), (qty * price) - line_disc)
            line_subtotal = quantize_money(line_raw_subtotal)
            raw_doc_subtotal += line_subtotal

            processed_items.append({
                "index": idx,
                "product_id": item.get("product_id", item.get("id")),
                "name": str(item.get("name", "")),
                "code": str(item.get("code", "")),
                "quantity": qty,
                "unit_price": quantize_money(price),
                "discount": quantize_money(line_disc),
                "line_subtotal": line_subtotal,
                "raw_tax_rate": Decimal(str(item.get("tax_rate", 0) or 0)),
                "is_taxable": item.get("is_taxable", True),
                "table_tax_rate": Decimal(str(item.get("table_tax_rate", 0) or 0)),
                "is_service": bool(item.get("is_service", False)),
            })

        doc_subtotal = raw_doc_subtotal
        net_adjustment = adjustment_amount - global_discount

        # Exemption Ceiling Calculation
        has_ceiling = exemption_max_ceiling is not None and Decimal(str(exemption_max_ceiling)) > Decimal("0.00")
        available_ceiling = Decimal("0.00")
        if has_ceiling:
            max_c = Decimal(str(exemption_max_ceiling))
            used_c = Decimal(str(exemption_utilized or 0))
            available_ceiling = max(Decimal("0.00"), max_c - used_c)

        running_exempt_consumed = Decimal("0.00")

        # 2. Second Pass: Pro-Rata Distribution, Ceiling Consumption, and ETA Line-Level VAT Calculation
        total_taxable_subtotal = Decimal("0.00")
        total_exempt_subtotal = Decimal("0.00")
        total_table_tax = Decimal("0.00")
        total_vat = Decimal("0.00")
        total_wht = Decimal("0.00")

        # Form 10 Breakdown Boxes (Egyptian VAT Return Standard)
        form_10_boxes = {
            "box_1_goods_14": Decimal("0.00"),      # مبيعات سلع عامة
            "box_2_services_14": Decimal("0.00"),   # مبيعات خدمات عامة
            "box_3_exempt": Decimal("0.00"),        # مبيعات معفاة
            "box_4_export_zero": Decimal("0.00"),   # صادرات بسعر صفر
            "box_5_table_tax": Decimal("0.00"),     # سلع وخدمات جدول
        }

        for p_item in processed_items:
            # Pro-Rata adjustment portion (guarded against division by zero)
            if doc_subtotal > Decimal("0.00"):
                line_adj = quantize_money(
                    (p_item["line_subtotal"] / doc_subtotal) * net_adjustment
                )
            else:
                line_adj = Decimal("0.00")

            # Net Base after global discount/adjustment (guarded against negative values)
            line_net_base = max(Decimal("0.00"), p_item["line_subtotal"] + line_adj)
            p_item["line_adj"] = line_adj
            p_item["line_net_base"] = line_net_base

            # Determine Effective Tax Rate based on 3-tier hierarchy
            raw_rate = p_item["raw_tax_rate"]
            effective_rate = Decimal("0.00")
            effective_table_rate = Decimal("0.00")

            if tax_active and p_item["is_taxable"]:
                if customer_exempt:
                    if has_ceiling:
                        # If customer has a ceiling, exempt up to remaining ceiling, charge rest
                        remaining_quota = max(Decimal("0.00"), available_ceiling - running_exempt_consumed)
                        if line_net_base <= remaining_quota:
                            effective_rate = Decimal("0.00")
                            running_exempt_consumed += line_net_base
                        else:
                            # Split base or charge standard rate
                            effective_rate = raw_rate
                    else:
                        effective_rate = Decimal("0.00")
                else:
                    effective_rate = raw_rate
                    effective_table_rate = p_item["table_tax_rate"]
            else:
                effective_rate = Decimal("0.00")

            p_item["effective_tax_rate"] = effective_rate
            p_item["effective_table_rate"] = effective_table_rate

            # Table Tax Calculation (T2/T3 Compound)
            line_table_tax = Decimal("0.00")
            if effective_table_rate > Decimal("0.00"):
                line_table_tax = quantize_money(line_net_base * (effective_table_rate / Decimal("100.00")))
            p_item["line_table_tax"] = line_table_tax
            total_table_tax += line_table_tax

            # VAT Base (Net Base + Table Tax if compound)
            vat_base = line_net_base + line_table_tax

            # ETA Rounding Rule: round line VAT to 2 decimal places
            line_vat = Decimal("0.00")
            if effective_rate > Decimal("0.00"):
                line_vat = quantize_money(vat_base * (effective_rate / Decimal("100.00")))
            p_item["line_tax_amount"] = line_vat
            total_vat += line_vat

            # Withholding Tax WHT (Calculated on Net Base before VAT)
            line_wht = Decimal("0.00")
            if wht_rate > Decimal("0.00"):
                line_wht = quantize_money(line_net_base * (wht_rate / Decimal("100.00")))
            p_item["line_wht_amount"] = line_wht
            total_wht += line_wht

            # Total for line
            p_item["line_total"] = line_net_base + line_vat

            # Classify Subtotals and Form 10 Boxes
            if effective_rate > Decimal("0.00"):
                total_taxable_subtotal += line_net_base
                if p_item["is_service"]:
                    form_10_boxes["box_2_services_14"] += line_net_base
                else:
                    form_10_boxes["box_1_goods_14"] += line_net_base
            else:
                total_exempt_subtotal += line_net_base
                form_10_boxes["box_3_exempt"] += line_net_base

            if effective_table_rate > Decimal("0.00"):
                form_10_boxes["box_5_table_tax"] += line_net_base

        net_subtotal = max(Decimal("0.00"), doc_subtotal - global_discount + adjustment_amount)
        doc_total = net_subtotal + total_vat
        net_payable = max(Decimal("0.00"), doc_total - total_wht)

        # Cryptographic Audit Signature (SHA-256)
        audit_payload = {
            "document_number": document_number,
            "subtotal": str(doc_subtotal),
            "global_discount": str(global_discount),
            "adjustment": str(adjustment_amount),
            "taxable_subtotal": str(total_taxable_subtotal),
            "exempt_subtotal": str(total_exempt_subtotal),
            "total_vat": str(total_vat),
            "items": [
                {
                    "id": it["product_id"],
                    "qty": str(it["quantity"]),
                    "base": str(it["line_net_base"]),
                    "rate": str(it["effective_tax_rate"]),
                    "vat": str(it["line_tax_amount"]),
                }
                for it in processed_items
            ],
        }
        signature_hash = hashlib.sha256(
            json.dumps(audit_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return {
            "items": processed_items,
            "subtotal": doc_subtotal,
            "taxable_subtotal": total_taxable_subtotal,
            "exempt_subtotal": total_exempt_subtotal,
            "global_discount": global_discount,
            "adjustment_amount": adjustment_amount,
            "net_subtotal": net_subtotal,
            "total_table_tax": total_table_tax,
            "total_tax": total_vat,
            "total_vat": total_vat,
            "total_wht": total_wht,
            "total": doc_total,
            "net_payable": net_payable,
            "form_10_boxes": form_10_boxes,
            "audit_signature": signature_hash,
        }
