from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from financial.models.currency import Currency, ExchangeRate



class ExchangeRateService:
    """
    FIN-CORE-016: Multi-Currency Exchange Rate Engine (IAS 21 Compliant)
    خدمة تحويل أسعار الصرف وتجميد الصور اللحظية (Snapshots)
    """

    @classmethod
    def get_functional_currency(cls) -> Optional[Currency]:
        """الحصول على العملة الوظيفية/الأساسية للمؤسسة مع غطاء حماية عند تفريغ قاعدة البيانات"""
        curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.first()
        if not curr:
            from types import SimpleNamespace
            return SimpleNamespace(
                id=None,
                code="EGP",
                name="جنيه مصري",
                symbol="ج.م",
                decimal_places=2,
                is_functional=True,
                is_active=True
            )
        return curr

    @classmethod
    def get_exchange_rate(cls, currency_or_code, date=None) -> Decimal:
        """
        الحصول الآمن على سعر الصرف للعملة مقابل العملة الوظيفية
        """
        if not currency_or_code:
            return Decimal("1.000000")
        if hasattr(currency_or_code, "is_functional") and currency_or_code.is_functional:
            return Decimal("1.000000")
        code = currency_or_code.code if hasattr(currency_or_code, "code") else str(currency_or_code)
        try:
            return cls.get_rate(from_code=code, date=date)
        except Exception:
            return Decimal("1.000000")



    @classmethod
    def get_rate(cls, from_code: str, to_code: Optional[str] = None, date=None) -> Decimal:
        """
        الحصول على سعر الصرف اللحظي بتاريخ معين وفق سياسة الرفض الصارم (Fail Fast)
        """
        if to_code is None:
            func_curr = cls.get_functional_currency()
            if not func_curr:
                raise ValidationError("لم يتم تعيين العملة الأساسية الوظيفية للمؤسسة في قاعدة البيانات. يرجى تعيين العملة الأساسية أولاً.")
            to_code = func_curr.code

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

        # 3. Triangular Cross-Rate Resolution (حل أسعار الصرف التبادلية الثلاثية عبر العملة الأساسية)
        func_curr = cls.get_functional_currency()
        func_code = func_curr.code if func_curr else "EGP"
        if from_code != func_code and to_code != func_code:
            try:
                rate_from_base = cls.get_rate(from_code, func_code, date)
                rate_to_base = cls.get_rate(to_code, func_code, date)
                if rate_to_base > 0:
                    return (rate_from_base / rate_to_base).quantize(Decimal("0.000001"))
            except Exception:
                pass

        # Fail Fast Policy: Raise ValidationError when no exchange rate is recorded
        raise ValidationError(
            f"لا يوجد سعر صرف مسجل بين العملة ({from_code}) والعملة ({to_code}) بتاريخ {date}. يرجى تسجيل سعر الصرف رسمياً في النظام أولاً."
        )

    @classmethod
    def set_rate(cls, from_code: str, to_code: str, rate: Decimal, date=None, source: str = "MANUAL", user=None) -> ExchangeRate:
        """
        تعيين سعر صرف جديد وتجميده
        """
        if date is None:
            date = timezone.now().date()

        from_curr, _ = Currency.objects.get_or_create(code=from_code, defaults={"name": from_code})
        to_curr, _ = Currency.objects.get_or_create(code=to_code, defaults={"name": to_code})

        defaults = {
            "rate": rate,
            "source": source,
        }
        if user is not None:
            defaults["created_by"] = user

        ex_rate, created = ExchangeRate.objects.update_or_create(
            from_currency=from_curr,
            to_currency=to_curr,
            effective_date=date,
            defaults=defaults
        )
        if not created and user is not None and ex_rate.created_by is None:
            ex_rate.created_by = user
            ex_rate.save(update_fields=["created_by"])
        return ex_rate

    @classmethod
    def convert_amount(cls, amount: Decimal, from_code: str, to_code: Optional[str] = None, date=None) -> Dict[str, Any]:
        """
        تحويل المبلغ بين العملات وإرجاع الصورة اللحظية
        """
        if to_code is None:
            func_curr = cls.get_functional_currency()
            if not func_curr:
                raise ValidationError("لم يتم تعيين العملة الأساسية الوظيفية للمؤسسة في قاعدة البيانات. يرجى تعيين العملة الأساسية أولاً.")
            to_code = func_curr.code

        rate = cls.get_rate(from_code, to_code, date)
        functional_amount = (amount * rate).quantize(Decimal("0.01"))
        return {
            "foreign_amount": amount,
            "currency": from_code,
            "exchange_rate": rate,
            "functional_amount": functional_amount
        }

