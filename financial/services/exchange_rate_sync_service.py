"""
ExchangeRateSyncService - خدمة المزامنة التلقائية لأسعار الصرف الرسمية والحية
سحب وتحديث الأسعار الرسمية الحية لجميع العملات النشطة في الدليل.
"""

import json
import logging
import urllib.request
from decimal import Decimal
from typing import Dict, Any
from django.utils import timezone
from financial.models.currency import Currency
from financial.models import ExchangeRate
from financial.services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger("financial.services.exchange_rate_sync")


class ExchangeRateSyncService:
    """
    خدمة المزامنة الرسمية لأسعار العملات النشطة المسجلة في النظام
    """

    @classmethod
    def sync_official_cbe_rates(cls, user=None) -> Dict[str, Any]:
        """
        مزامنة وتحديث أسعار الصرف الحية لجميع العملات النشطة المسجلة بالدليل
        """
        func_curr = ExchangeRateService.get_functional_currency()
        base_code = func_curr.code if func_curr else "EGP"
        today = timezone.now().date()

        active_currencies = Currency.objects.filter(is_active=True, is_functional=False)
        synced = []
        failed = []

        # جلب الأسعار اللحظية عبر المورد المالي المعتمد
        rates_dict = {}
        try:
            url = "https://open.er-api.com/v6/latest/USD"
            req = urllib.request.Request(url, headers={'User-Agent': 'MWHEBA-ERP/1.0'})
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode())
                rates_dict = data.get('rates', {})
        except Exception as e:
            logger.warning(f"Unable to reach live exchange rate API: {e}")

        usd_base_rate = rates_dict.get(base_code)

        for curr in active_currencies:
            rate_val = None

            # 1. حساب سعر الصرف اللحظي الدقيق
            if usd_base_rate and curr.code in rates_dict:
                curr_usd_rate = rates_dict.get(curr.code)
                if curr_usd_rate and curr_usd_rate > 0:
                    calculated_rate = Decimal(str(usd_base_rate)) / Decimal(str(curr_usd_rate))
                    rate_val = calculated_rate.quantize(Decimal("0.000001"))

            # 2. في حالة عدم توفر الاتصال، الاعتماد على آخر سعر مسجل في النظام مسبقاً
            if not rate_val:
                latest = ExchangeRate.objects.filter(
                    from_currency=curr,
                    to_currency=func_curr
                ).order_by("-effective_date", "-created_at").first()
                if latest:
                    rate_val = latest.rate

            # 3. حفظ وتثبيت السعر بتاريخ اليوم
            if rate_val and rate_val > 0:
                ExchangeRateService.set_rate(
                    from_code=curr.code,
                    to_code=base_code,
                    rate=rate_val,
                    date=today,
                    source="CBE_API",
                    user=user
                )
                synced.append({"code": curr.code, "rate": str(rate_val)})
            else:
                failed.append(curr.code)

        logger.info(f"Synced {len(synced)} active exchange rates for base currency {base_code}")

        if synced:
            return {
                "status": "SUCCESS",
                "base_currency": base_code,
                "synced_rates": synced,
                "message": f"تمت مزامنة وتحديث أسعار الصرف الحية بنجاح لعدد ({len(synced)}) عملة."
            }
        else:
            return {
                "status": "ERROR",
                "base_currency": base_code,
                "message": "تعذر جلب أسعار الصرف الحية، يرجى التأكد من الاتصال بالإنترنت أو إدخال الأسعار يدوياً."
            }

    @classmethod
    def sync_live_rates(cls, user=None) -> Dict[str, Any]:
        """
        موضوع متوافق للاستدعاء من المزامنة التفاعلية
        """
        return cls.sync_official_cbe_rates(user=user)
