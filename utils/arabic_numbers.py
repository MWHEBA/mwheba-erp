# -*- coding: utf-8 -*-
"""
أداة تحويل الأرقام والمبالغ المالية إلى كلمات باللغة العربية (Tafqeet)
"""

from decimal import Decimal
from typing import Optional, Union

ONES = [
    "", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة",
    "عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر",
    "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"
]

TENS = [
    "", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"
]

HUNDREDS = [
    "", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة", "سبعمائة", "ثمانمائة", "تسعمائة"
]

CURRENCIES = {
    "EGP": {"main": "جنيه مصري", "main_plural": "جنيهات مصرية", "sub": "قرش", "sub_plural": "قروش"},
    "USD": {"main": "دولار أمريكي", "main_plural": "دولارات أمريكية", "sub": "سنت", "sub_plural": "سنتات"},
    "EUR": {"main": "يورو", "main_plural": "يورو", "sub": "سنت", "sub_plural": "سنتات"},
    "SAR": {"main": "ريال سعودي", "main_plural": "ريالات سعودية", "sub": "هللة", "sub_plural": "هللات"},
    "AED": {"main": "درهم إماراتي", "main_plural": "دراهم إماراتية", "sub": "فلس", "sub_plural": "فلوس"},
}


def _convert_group(n: int) -> str:
    """تحويل مجموعة من 3 أرقام إلى كلمات عربية"""
    if n == 0:
        return ""

    h = n // 100
    rem = n % 100
    parts = []

    if h > 0:
        parts.append(HUNDREDS[h])

    if rem > 0:
        if rem < 20:
            parts.append(ONES[rem])
        else:
            unit = rem % 10
            ten = rem // 10
            if unit > 0:
                parts.append(f"{ONES[unit]} و{TENS[ten]}")
            else:
                parts.append(TENS[ten])

    return " و".join(parts)


def number_to_arabic_words(num: Union[int, Decimal, float]) -> str:
    """تحويل أي رقم صحيح إلى كلمات عربية كاملة"""
    try:
        n = int(num)
    except (ValueError, TypeError):
        return ""

    if n == 0:
        return "صفر"

    if n < 0:
        return f"سالب {number_to_arabic_words(-n)}"

    billions = n // 1000000000
    millions = (n % 1000000000) // 1000000
    thousands = (n % 1000000) // 1000
    rem = n % 1000

    parts = []

    if billions > 0:
        if billions == 1:
            parts.append("مليار")
        elif billions == 2:
            parts.append("ملياران")
        elif 3 <= billions <= 10:
            parts.append(f"{_convert_group(billions)} مليارات")
        else:
            parts.append(f"{_convert_group(billions)} مليار")

    if millions > 0:
        if millions == 1:
            parts.append("مليون")
        elif millions == 2:
            parts.append("مليونان")
        elif 3 <= millions <= 10:
            parts.append(f"{_convert_group(millions)} ملايين")
        else:
            parts.append(f"{_convert_group(millions)} مليون")

    if thousands > 0:
        if thousands == 1:
            parts.append("ألف")
        elif thousands == 2:
            parts.append("ألفان")
        elif 3 <= thousands <= 10:
            parts.append(f"{_convert_group(thousands)} آلاف")
        else:
            parts.append(f"{_convert_group(thousands)} ألف")

    if rem > 0:
        parts.append(_convert_group(rem))

    return " و".join(parts)


def amount_to_arabic_words(amount: Union[int, Decimal, float], currency: Optional[str] = "EGP") -> str:
    """
    تحويل المبلغ المالي إلى تفقيط عربي مع العملة والكسور (القرش / السنت)
    مثال: 1250.50 EGP -> ألف ومائتان وخمسون جنيهاً مصرياً وخمسون قرشاً فقط لا غير
    """
    if amount is None:
        return ""

    try:
        dec_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception:
        return ""

    if dec_amount == Decimal("0.00"):
        return "صفر"

    is_negative = dec_amount < 0
    dec_amount = abs(dec_amount)

    integer_part = int(dec_amount)
    fraction_part = int((dec_amount - Decimal(integer_part)) * 100)

    curr_info = CURRENCIES.get(currency.upper() if currency else "EGP", CURRENCIES["EGP"])

    parts = []

    if integer_part > 0:
        words = number_to_arabic_words(integer_part)
        main_unit = curr_info["main_plural"] if (3 <= (integer_part % 100) <= 10) else curr_info["main"]
        parts.append(f"{words} {main_unit}")

    if fraction_part > 0:
        frac_words = number_to_arabic_words(fraction_part)
        sub_unit = curr_info["sub_plural"] if (3 <= fraction_part <= 10) else curr_info["sub"]
        parts.append(f"{frac_words} {sub_unit}")

    result = " و".join(parts)
    prefix = "سالب " if is_negative else ""
    return f"فقط {prefix}{result} لا غير"
