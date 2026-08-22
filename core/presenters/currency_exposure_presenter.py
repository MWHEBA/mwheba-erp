from typing import List, Dict, Any
from utils.templatetags.utils_extras import smart_float
from financial.services.partner_exposure_service import PartnerExposureDTO


def get_currency_symbol(code: str) -> str:
    """
    تحويل كود العملة الـ ISO إلى الرمز الخاص بها (Symbol)
    """
    if not code:
        return "ج.م"
    try:
        from financial.models import Currency
        curr = Currency.objects.filter(code__iexact=code).first()
        if curr and curr.symbol:
            return curr.symbol
    except Exception:
        pass

    symbols = {
        "EGP": "ج.م",
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "SAR": "ر.س",
        "AED": "د.إ",
        "KWD": "د.ك",
        "QAR": "ر.ق",
        "BHD": "د.ب",
        "OMR": "ر.ع",
        "JOD": "د.أ",
    }
    return symbols.get(code.upper(), code)


class CurrencyBadgeViewModel:
    """
    View Model مخصص لعرض شارات العملات بصرياً دون المساس بالنماذج المحاسبية
    """
    def __init__(
        self,
        currency: str,
        currency_symbol: str,
        amount: float,
        formatted_amount: str,
        label: str,
        variant: str,
        icon: str,
        nature: str
    ):
        self.currency = currency
        self.currency_symbol = currency_symbol
        self.amount = amount
        self.formatted_amount = formatted_amount
        self.label = label
        self.variant = variant
        self.icon = icon
        self.nature = nature

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "currency_symbol": self.currency_symbol,
            "amount": self.amount,
            "formatted_amount": self.formatted_amount,
            "label": self.label,
            "variant": self.variant,
            "icon": self.icon,
            "nature": self.nature,
        }


class CurrencyExposurePresenter:
    """
    الـ Presenter المعماري المسئول عن تحويل DTOs الانكشافات المالية لكائنات عرض بصرية (Badge View Models)
    Presentation & Formatting Layer (Decoupled from Models and Controllers)
    """

    @classmethod
    def build_view_models(cls, dto_list: List[PartnerExposureDTO]) -> List[CurrencyBadgeViewModel]:
        """
        تحويل قائمة PartnerExposureDTO إلى قائمة من CurrencyBadgeViewModel
        """
        view_models = []
        if not dto_list:
            return view_models

        for dto in dto_list:
            if dto.net_balance <= 0:
                continue

            # تنسيق الرقم بصيغة ذكية وشاملة
            formatted_num = smart_float(dto.net_balance, 2)
            nature = dto.nature
            curr_symbol = get_currency_symbol(dto.currency)

            if dto.partner_type == "supplier":
                if nature == "PAYABLE":
                    label = "مستحق"
                    variant = "bg-danger text-white"
                    icon = "fas fa-arrow-down"
                else:
                    label = "مسبق"
                    variant = "bg-success text-white"
                    icon = "fas fa-arrow-up"
            else: # customer
                if nature == "RECEIVABLE":
                    label = "مطلوب"
                    variant = "bg-danger text-white"
                    icon = "fas fa-exclamation-circle"
                else:
                    label = "رصيد مسبق"
                    variant = "bg-success text-white"
                    icon = "fas fa-check-circle"

            view_models.append(
                CurrencyBadgeViewModel(
                    currency=dto.currency,
                    currency_symbol=curr_symbol,
                    amount=float(dto.net_balance),
                    formatted_amount=formatted_num,
                    label=label,
                    variant=variant,
                    icon=icon,
                    nature=nature
                )
            )

        return view_models

    @classmethod
    def render_html_badges(cls, dto_list: List[PartnerExposureDTO]) -> str:
        """
        إنشاء شارات الـ HTML النهائية المنسقة بعناية لاستخدامها المباشر في جداول البيانات (DataTables)
        """
        view_models = cls.build_view_models(dto_list)
        if not view_models:
            return '<span class="text-muted">-</span>'

        html_badges = []
        for vm in view_models:
            badge_str = (
                f'<span class="badge {vm.variant} me-1 mb-1 p-2 shadow-sm" '
                f'title="{vm.label}: {vm.formatted_amount} {vm.currency_symbol}">'
                f'<i class="{vm.icon} me-1"></i>{vm.formatted_amount} {vm.currency_symbol}'
                f'</span>'
            )
            html_badges.append(badge_str)

        return f'<div class="d-inline-flex flex-wrap gap-1 align-items-center justify-content-center">{"".join(html_badges)}</div>'
