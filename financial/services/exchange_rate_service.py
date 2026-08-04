from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from django.core.exceptions import ValidationError
from financial.models.currency import Currency, ExchangeRate


class ExchangeRateService:
    """
    FIN-CORE-016: Multi-Currency Exchange Rate Engine (IAS 21 Compliant)
    خدمة تحويل أسعار الصرف وتجميد الصور اللحظية (Snapshots)
    """

    @classmethod
    def get_rate(cls, from_code: str, to_code: str = "EGP", date=None) -> Decimal:
        """
        الحصول على سعر الصرف اللحظي بتاريخ معين
        """
        if from_code == to_code:
            return Decimal("1.000000")

        if date is None:
            date = timezone.now().date()

        rate_obj = ExchangeRate.objects.filter(
            from_currency__code=from_code,
            to_currency__code=to_code,
            effective_date__lte=date
        ).order_by("-effective_date", "-created_at").first()

        if rate_obj:
            return rate_obj.rate

        # Inverse rate fallback check
        inv_rate_obj = ExchangeRate.objects.filter(
            from_currency__code=to_code,
            to_currency__code=from_code,
            effective_date__lte=date
        ).order_by("-effective_date", "-created_at").first()

        if inv_rate_obj and inv_rate_obj.rate > 0:
            return (Decimal("1.000000") / inv_rate_obj.rate).quantize(Decimal("0.000001"))

        # Default fallback for USD if not set
        if from_code == "USD" and to_code == "EGP":
            return Decimal("48.500000")

        return Decimal("1.000000")

    @classmethod
    def set_rate(cls, from_code: str, to_code: str, rate: Decimal, date=None, source: str = "MANUAL", user=None) -> ExchangeRate:
        """
        تعيين سعر صرف جديد وتجميده
        """
        if date is None:
            date = timezone.now().date()

        from_curr, _ = Currency.objects.get_or_create(code=from_code, defaults={"name": from_code, "is_base": (from_code == "EGP")})
        to_curr, _ = Currency.objects.get_or_create(code=to_code, defaults={"name": to_code, "is_base": (to_code == "EGP")})

        ex_rate = ExchangeRate.objects.create(
            from_currency=from_curr,
            to_currency=to_curr,
            rate=rate,
            effective_date=date,
            source=source,
            created_by=user
        )
        return ex_rate

    @classmethod
    def convert_amount(cls, amount: Decimal, from_code: str, to_code: str = "EGP", date=None) -> Dict[str, Any]:
        """
        تحويل المبلغ بين العملات وإرجاع الصورة اللحظية
        """
        rate = cls.get_rate(from_code, to_code, date)
        functional_amount = (amount * rate).quantize(Decimal("0.01"))
        return {
            "foreign_amount": amount,
            "currency": from_code,
            "exchange_rate": rate,
            "functional_amount": functional_amount
        }
