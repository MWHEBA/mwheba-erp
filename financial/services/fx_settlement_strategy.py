from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any, List, Optional
import logging

from governance.services import JournalEntryLineData

logger = logging.getLogger("financial.services.fx_settlement_strategy")


class FXSettlementStrategy(ABC):
    """
    Abstract Strategy Interface for IAS 21 Realized FX Difference Calculations
    واجهة مجردة لاحتساب وتجهيز قيود أرباح وخسائر فروق العملة المحققة
    """

    @abstractmethod
    def calculate_difference(
        self,
        advance_exchange_rate: Decimal,
        invoice_exchange_rate: Decimal,
        allocated_amount: Decimal
    ) -> Decimal:
        """
        حساب فارق التقويم بالعملة المحلية بين تاريخ الدفعة وتاريخ الفاتورة
        Functional Difference = Allocated_Amount * (Invoice_Rate - Advance_Rate)
        """
        pass

    @abstractmethod
    def generate_entries(
        self,
        difference: Decimal,
        advance_account_code: str,
        partner_account_code: str,
        fx_gain_account_code: str = "43100",
        fx_loss_account_code: str = "54300",
        reference_note: str = ""
    ) -> List[JournalEntryLineData]:
        """
        توليد بنود القيد المحاسبي المزدوج المتزن لفروق الصرف المحققة
        """
        pass


class CustomerAdvanceLiabilityStrategy(FXSettlementStrategy):
    """
    IAS 21 Strategy for Customer Prepaid Allocations (AR / Customer Advance Liability)
    استراتيجية تسوية فروق العملة المحققة لدفعات العملاء المقدمة (التزامات دفعات مقدمة عملاء 20200 vs ذمم عملاء 10200)
    """

    def calculate_difference(
        self,
        advance_exchange_rate: Decimal,
        invoice_exchange_rate: Decimal,
        allocated_amount: Decimal
    ) -> Decimal:
        advance_rate = Decimal(str(advance_exchange_rate or "1.0"))
        invoice_rate = Decimal(str(invoice_exchange_rate or "1.0"))
        amount = Decimal(str(allocated_amount or "0.0"))

        advance_functional = (amount * advance_rate).quantize(Decimal("0.01"))
        invoice_functional = (amount * invoice_rate).quantize(Decimal("0.01"))

        # Difference = Invoice Functional Value - Advance Functional Value
        return invoice_functional - advance_functional

    def generate_entries(
        self,
        difference: Decimal,
        advance_account_code: str,
        partner_account_code: str,
        fx_gain_account_code: str = "43100",
        fx_loss_account_code: str = "54300",
        reference_note: str = ""
    ) -> List[JournalEntryLineData]:
        """
        توليد بنود القيد المحاسبي المزدوج المتزن لتسوية دفعة العميل المقدمة
        - Debit Advance Liability (بسعر صرف الدفعة التاريخي)
        - Credit Customer AR (بسعر صرف الفاتورة الحالي)
        - Balancing Debit FX Loss / Credit FX Gain
        """
        diff = Decimal(str(difference or "0.00")).quantize(Decimal("0.01"))
        if diff == Decimal("0.00"):
            return []

        lines = []
        if diff > Decimal("0.00"):
            # Invoice EGP > Advance EGP -> Realized FX Loss for seller (Debit 50400)
            lines.append(
                JournalEntryLineData(
                    account_code=fx_loss_account_code,
                    debit=diff,
                    credit=Decimal("0.00"),
                    description=f"خسائر فروق عملة محققة - تسوية دفعة عميل ({reference_note})"
                )
            )
        else:
            # Advance EGP > Invoice EGP -> Realized FX Gain for seller (Credit 40400)
            abs_diff = abs(diff)
            lines.append(
                JournalEntryLineData(
                    account_code=fx_gain_account_code,
                    debit=Decimal("0.00"),
                    credit=abs_diff,
                    description=f"أرباح فروق عملة محققة - تسوية دفعة عميل ({reference_note})"
                )
            )

        return lines


CustomerFXStrategy = CustomerAdvanceLiabilityStrategy


class SupplierAdvanceAssetStrategy(FXSettlementStrategy):
    """
    IAS 21 Strategy for Supplier Advance Allocations (AP / Supplier Advance Asset)
    استراتيجية تسوية فروق العملة المحققة لدفعات الموردين المقدمة (أصول دفعات مقدمة موردين 10500 vs دائنية موردين 20100)
    """

    def calculate_difference(
        self,
        advance_exchange_rate: Decimal,
        invoice_exchange_rate: Decimal,
        allocated_amount: Decimal
    ) -> Decimal:
        advance_rate = Decimal(str(advance_exchange_rate or "1.0"))
        invoice_rate = Decimal(str(invoice_exchange_rate or "1.0"))
        amount = Decimal(str(allocated_amount or "0.0"))

        advance_functional = (amount * advance_rate).quantize(Decimal("0.01"))
        invoice_functional = (amount * invoice_rate).quantize(Decimal("0.01"))

        # Difference = Invoice Functional Value - Advance Functional Value
        return invoice_functional - advance_functional

    def generate_entries(
        self,
        difference: Decimal,
        advance_account_code: str,
        partner_account_code: str,
        fx_gain_account_code: str = "43100",
        fx_loss_account_code: str = "54300",
        reference_note: str = ""
    ) -> List[JournalEntryLineData]:
        """
        توليد بنود القيد المحاسبي المزدوج المتزن لتسوية دفعة المورد المقدمة
        - Debit Supplier AP (بسعر صرف الفاتورة)
        - Credit Supplier Advance Asset (بسعر صرف الدفعة التاريخي)
        - Balancing Credit FX Gain / Debit FX Loss
        """
        diff = Decimal(str(difference or "0.00")).quantize(Decimal("0.01"))
        if diff == Decimal("0.00"):
            return []

        lines = []
        if diff > Decimal("0.00"):
            # Bill EGP > Advance EGP -> Purchased at cheaper advance rate -> Realized FX Gain (Credit 40400)
            lines.append(
                JournalEntryLineData(
                    account_code=fx_gain_account_code,
                    debit=Decimal("0.00"),
                    credit=diff,
                    description=f"أرباح فروق عملة محققة - تسوية دفعة مورد ({reference_note})"
                )
            )
        else:
            # Advance EGP > Bill EGP -> Paid higher advance rate -> Realized FX Loss (Debit 50400)
            abs_diff = abs(diff)
            lines.append(
                JournalEntryLineData(
                    account_code=fx_loss_account_code,
                    debit=abs_diff,
                    credit=Decimal("0.00"),
                    description=f"خسائر فروق عملة محققة - تسوية دفعة مورد ({reference_note})"
                )
            )

        return lines


SupplierFXStrategy = SupplierAdvanceAssetStrategy

