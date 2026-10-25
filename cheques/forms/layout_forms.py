# -*- coding: utf-8 -*-
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts
from cheques.models import BankChequeLayout


class BankChequeLayoutForm(forms.ModelForm):
    """
    نموذج معايرة وضبط أبعاد طباعة الشيكات البنكية بالمليمتر
    """
    class Meta:
        model = BankChequeLayout
        fields = [
            'bank_account',
            'template_name',
            'is_default',
            'paper_width_mm',
            'paper_height_mm',
            'date_pos_x_mm',
            'date_pos_y_mm',
            'date_spacing_mm',
            'date_format',
            'payee_pos_x_mm',
            'payee_pos_y_mm',
            'amount_digits_pos_x_mm',
            'amount_digits_pos_y_mm',
            'amount_words_line1_pos_x_mm',
            'amount_words_line1_pos_y_mm',
            'amount_words_line2_pos_x_mm',
            'amount_words_line2_pos_y_mm',
            'cross_mark_pos_x_mm',
            'cross_mark_pos_y_mm',
            'font_size_pt',
        ]
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'template_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم القالب (مثال: CIB Corporate 2026)')}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'paper_width_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'paper_height_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'date_pos_x_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'date_pos_y_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'date_spacing_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'date_format': forms.TextInput(attrs={'class': 'form-control'}),
            'payee_pos_x_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'payee_pos_y_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'amount_digits_pos_x_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'amount_digits_pos_y_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'amount_words_line1_pos_x_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'amount_words_line1_pos_y_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'amount_words_line2_pos_x_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'amount_words_line2_pos_y_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'cross_mark_pos_x_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'cross_mark_pos_y_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'font_size_pt': forms.NumberInput(attrs={'class': 'form-control', 'min': '6', 'max': '24'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bank_account'].queryset = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

    def clean(self):
        cleaned_data = super().clean()
        width = cleaned_data.get('paper_width_mm')
        height = cleaned_data.get('paper_height_mm')

        if width is not None and width <= 0:
            self.add_error('paper_width_mm', _('عرض الورقة يجب أن يكون أكبر من الصفر.'))
        if height is not None and height <= 0:
            self.add_error('paper_height_mm', _('ارتفاع الورقة يجب أن يكون أكبر من الصفر.'))

        return cleaned_data
