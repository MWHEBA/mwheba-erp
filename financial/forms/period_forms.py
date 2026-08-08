from django import forms
from django.utils.translation import gettext_lazy as _
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod
from financial.models.closing_engine_models import PeriodModuleLock, ClosingRule
from financial.models.chart_of_accounts import ChartOfAccounts


class FiscalYearForm(forms.ModelForm):
    """نموذج إنشاء وتعديل السنوات المالية"""
    retained_earnings_account = forms.ModelChoiceField(
        queryset=ChartOfAccounts.objects.filter(is_active=True),
        required=False,
        label=_("حساب الأرباح والخسائر المرحلة (اختياري)"),
        help_text=_("في حال اتركه فارغاً، سيتم اختيار الحساب الافتراضي النظامي 30200 تلقائياً"),
        widget=forms.Select(attrs={'class': 'form-select select2-filter'})
    )

    class Meta:
        model = FiscalYear
        fields = ['year_code', 'name', 'start_date', 'end_date', 'status', 'retained_earnings_account']
        widgets = {
            'year_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'FY2026'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'السنة المالية 2026'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError(_("تاريخ بداية السنة المالية يجب أن يكون قبل تاريخ النهاية."))
        return cleaned_data


class AccountingPeriodForm(forms.ModelForm):
    """نموذج إنشاء وتعديل الفترات المحاسبية"""
    class Meta:
        model = AccountingPeriod
        fields = ['name', 'fiscal_year', 'period_number', 'start_date', 'end_date', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'fiscal_year': forms.Select(attrs={'class': 'form-select select2-filter'}),
            'period_number': forms.NumberInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class PeriodForceCloseForm(forms.Form):
    """نموذج الإغلاق بالتجاوز التوثيقي"""
    force_close_reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _("سبب التجاوز والإغلاق الفوري...")}),
        required=True,
        label=_("سبب التجاوز المعتمد من المدير المالي")
    )


class PeriodReopenForm(forms.Form):
    """نموذج إعادة فتح الفترة المغلقة"""
    reopen_reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _("سبب إعادة فتح الفترة...")}),
        required=True,
        label=_("سبب إعادة الفتح")
    )
