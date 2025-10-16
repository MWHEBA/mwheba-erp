from django import forms
from django.utils.translation import gettext_lazy as _
from .models import PlateSize


class PlateSizeForm(forms.ModelForm):
    """نموذج مقاس الزنك"""

    class Meta:
        model = PlateSize
        fields = [
            "name",
            "width",
            "height",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: ربع فرخ"}
            ),
            "width": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: 35.0",
                    "step": "0.1",
                    "min": "0.1",
                }
            ),
            "height": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: 50.0",
                    "step": "0.1",
                    "min": "0.1",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": _("اسم المقاس"),
            "width": _("العرض (سم)"),
            "height": _("الطول (سم)"),
            "is_active": _("نشط"),
        }
