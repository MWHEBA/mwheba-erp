# -*- coding: utf-8 -*-
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts
from cheques.models import Checkbook
from cheques.services.checkbook_service import CheckbookService


class CheckbookForm(forms.ModelForm):
    """
    نموذج تسجيل دفتر شيكات بنكي جديد وتوليد أوراقه ذرياً
    """
    class Meta:
        model = Checkbook
        fields = [
            'bank_account',
            'name',
            'serial_prefix',
            'serial_from',
            'serial_to',
        ]
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم أو كود الدفتر المرجعي')}),
            'serial_prefix': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('سلسلة الأرقام إن وجدت (مثال: A, EG, NB)')}),
            'serial_from': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'serial_to': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['serial_prefix'].required = False
        self.fields['name'].required = False
        self.fields['bank_account'].queryset = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

    def clean(self):
        cleaned_data = super().clean()
        bank_account = cleaned_data.get('bank_account')
        start = cleaned_data.get('serial_from')
        end = cleaned_data.get('serial_to')
        prefix = cleaned_data.get('serial_prefix') or ""

        if start is not None and start <= 0:
            self.add_error('serial_from', _('يجب أن يكون رقم البداية أكبر من الصفر.'))

        if start is not None and end is not None:
            if end < start:
                self.add_error('serial_to', _('رقم نهاية الدفتر يجب أن يكون أكبر من أو يساوي رقم البداية.'))
            elif (end - start + 1) > 200:
                self.add_error('serial_to', _('الحد الأقصى لعدد أوراق الدفتر الواحد هو 200 ورقة.'))

        # التحقق من عدم التداخل مع دفاتر قائمة لنفس الحساب البنكي
        if bank_account and start is not None and end is not None and not self.instance.pk:
            overlapping = Checkbook.objects.filter(
                bank_account=bank_account,
                serial_prefix=prefix,
                is_active=True
            ).filter(
                serial_from__lte=end,
                serial_to__gte=start
            ).exists()

            if overlapping:
                raise ValidationError(_("يوجد دفتر شيكات آخر نشط يغطي نفس نطاق الأرقام التسلسلية لهذا الحساب البنكي."))

        return cleaned_data

    def save(self, commit=True):
        if not self.instance.pk:
            return CheckbookService.create_checkbook(
                bank_account=self.cleaned_data['bank_account'],
                serial_from=self.cleaned_data['serial_from'],
                serial_to=self.cleaned_data['serial_to'],
                user=self.user,
                serial_prefix=self.cleaned_data.get('serial_prefix', ''),
                name=self.cleaned_data.get('name')
            )
        return super().save(commit=commit)


class RuinedLeafReplacementForm(forms.Form):
    """
    نموذج استبدال ورقة شيك تالفة وتخصيص الورقة التالية من الدفتر
    """
    voided_reason = forms.CharField(
        label=_('سبب التلف والإلغاء الإلزامي'),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('أدخل سبب تلف الورقة (مثال: انحشار في الطابعة، خطأ في كتابة المبلغ)...')
        }),
        required=True
    )
    voided_image = forms.ImageField(
        label=_('صورة الشيك التالف / الملغى'),
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        required=False
    )

    def clean_voided_reason(self):
        reason = self.cleaned_data.get('voided_reason', '').strip()
        if len(reason) < 5:
            raise ValidationError(_('يجب إدخال سبب تلف مفصل لا يقل عن 5 أحرف لحماية أمان الدفاتر.'))
        return reason
