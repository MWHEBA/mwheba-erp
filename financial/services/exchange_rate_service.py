from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from financial.models.currency import Currency, ExchangeRate



class ExchangeRateService:
    """
    FIN-CORE-016: Multi-Currency Exchange Rate Engine
    محرك حوكمة وتتبع وتحديث أسعار الصرف التاريخية للعملات الأجنبيةnapshots)
    """

    @classmethod
    def get_functional_currency(cls) -> Optional[Currency]:
        """الحصول على العملة الوظيفية/الأساسية للمؤسسة مع غطاء حماية عند تفريغ قاعدة البيانات"""
        curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.filter(code="EGP").first()
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

    @classmethod
    def calculate_payment_settlement(
        cls,
        invoice_amount: Decimal,
        invoice_currency_code: str,
        invoice_rate: Decimal,
        payment_currency_code: str,
        settlement_rate: Decimal,
        treasury_rate: Optional[Decimal] = None,
        date=None,
    ) -> Dict[str, Any]:
        """
        Enterprise Multi-Currency Settlement Engine.
        يحسب المبالغ المتقاطعة والمعادل الوظيفي وفروق أسعار الصرف بدقة متناهية.
        """
        invoice_amount = Decimal(str(invoice_amount or 0)).quantize(Decimal("0.01"))
        invoice_rate = Decimal(str(invoice_rate or 1.0)).quantize(Decimal("0.000001"))
        settlement_rate = Decimal(str(settlement_rate or 1.0)).quantize(Decimal("0.000001"))
        if settlement_rate <= Decimal("0.000000"):
            settlement_rate = Decimal("1.000000")

        func_curr = cls.get_functional_currency()
        func_code = getattr(func_curr, 'code', 'EGP') or 'EGP'
        
        inv_curr = (invoice_currency_code or func_code).upper()
        pmt_curr = (payment_currency_code or func_code).upper()
        
        # 1. المعادل الوظيفي الدفتري لقيمة الفاتورة
        inv_book_functional = (invoice_amount * invoice_rate).quantize(Decimal("0.01"))
        
        # 2. حساب المبلغ الفعلي المسحوب من الخزينة ومعادله الوظيفي
        if pmt_curr == inv_curr:
            # السيناريو 1 و 2: نفس العملة
            amount_paid_currency = invoice_amount
            if pmt_curr == func_code:
                # محلي لمحلي (EGP -> EGP)
                amount_functional = invoice_amount
                realized_fx = Decimal("0.00")
            else:
                # أجنبي لأجنبي (USD -> USD)
                amount_functional = (amount_paid_currency * settlement_rate).quantize(Decimal("0.01"))
                realized_fx = (amount_functional - inv_book_functional).quantize(Decimal("0.01"))
        elif inv_curr == func_code:
            # السيناريو 4: فاتورة محلية مسددة من خزينة أجنبية (EGP -> USD)
            # المبلغ المطلوب بالدولار = المبلغ بالجنيه ÷ سعر صرف الدولار
            amount_paid_currency = (invoice_amount / settlement_rate).quantize(Decimal("0.01"))
            amount_functional = invoice_amount
            realized_fx = Decimal("0.00")
        elif pmt_curr == func_code:
            # السيناريو 3: فاتورة أجنبية مسددة من خزينة محلية (USD -> EGP)
            # المبلغ المطلوب بالجنيه = المبلغ بالدولار × سعر صرف الدولار
            amount_paid_currency = (invoice_amount * settlement_rate).quantize(Decimal("0.01"))
            amount_functional = amount_paid_currency
            realized_fx = (amount_functional - inv_book_functional).quantize(Decimal("0.01"))
        else:
            # السيناريو 5: تقاطع عملتين أجنبيتين (EUR -> USD)
            amount_paid_currency = (inv_book_functional / settlement_rate).quantize(Decimal("0.01"))
            amount_functional = (amount_paid_currency * settlement_rate).quantize(Decimal("0.01"))
            realized_fx = (amount_functional - inv_book_functional).quantize(Decimal("0.01"))

        # تحديد نوع حركة فروق العملة
        if realized_fx > Decimal("0.00"):
            fx_type = "LOSS"
        elif realized_fx < Decimal("0.00"):
            fx_type = "GAIN"
        else:
            fx_type = "NONE"

        return {
            "settled_invoice_amt": invoice_amount,
            "invoice_currency": inv_curr,
            "invoice_rate": invoice_rate,
            "payment_currency": pmt_curr,
            "settlement_rate": settlement_rate,
            "amount_paid_currency": amount_paid_currency,
            "amount_functional": amount_functional,
            "invoice_book_functional": inv_book_functional,
            "realized_fx_difference": realized_fx,
            "fx_type": fx_type,
        }

    @classmethod
    def validate_payment_invariants(
        cls,
        invoice_amount: Decimal,
        invoice_currency_code: str,
        invoice_rate: Decimal,
        payment_currency_code: str,
        settlement_rate: Decimal,
        submitted_paid_amt: Optional[Decimal] = None,
        tolerance: Decimal = Decimal("0.05"),
    ) -> Dict[str, Any]:
        """
        صمام أمان صارم (Fail-Fast Invariant Guard)
        يتحقق من صحة المعاملات المالية قبل ترحيلها ويمنع أي قيم مشوهة
        """
        expected = cls.calculate_payment_settlement(
            invoice_amount=invoice_amount,
            invoice_currency_code=invoice_currency_code,
            invoice_rate=invoice_rate,
            payment_currency_code=payment_currency_code,
            settlement_rate=settlement_rate,
        )
        
        if submitted_paid_amt is not None and Decimal(str(submitted_paid_amt)) > Decimal("0.00"):
            submitted_dec = Decimal(str(submitted_paid_amt)).quantize(Decimal("0.01"))
            expected_dec = expected["amount_paid_currency"]
            diff = abs(submitted_dec - expected_dec)
            if diff > tolerance:
                raise ValidationError(
                    f"قيمة السداد المدخلة ({submitted_dec}) غير متوافقة مع القيمة المحسوبة نظامياً ({expected_dec}) لسعر الصرف المحدد. "
                    f"الفارق المالي المكتشف ({diff}) يتجاوز الحد المسموح به ({tolerance})."
                )
        return expected


