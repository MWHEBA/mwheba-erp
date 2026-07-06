from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import WorkOrder
from client.models import Customer


class WorkOrderForm(forms.ModelForm):
    """
    نموذج إنشاء وتعديل أمر الشغل
    """
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.filter(is_active=True),
        label=_("العميل"),
        widget=forms.Select(attrs={"class": "form-control select2-init"}),
    )

    class Meta:
        model = WorkOrder
        fields = [
            "customer",
            "start_date",
            "delivery_date",
            "estimated_cost",
            "notes",
        ]
        widgets = {
            "start_date": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "data-date-picker": True,
                    "placeholder": _("اختر تاريخ البدء..."),
                }
            ),
            "delivery_date": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "data-date-picker": True,
                    "placeholder": _("اختر تاريخ التسليم المتوقع..."),
                }
            ),
            "estimated_cost": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": _("اكتب تفاصيل وملاحظات أمر الشغل هنا...")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("start_date"):
            self.initial["start_date"] = timezone.now().date().strftime("%Y-%m-%d")
