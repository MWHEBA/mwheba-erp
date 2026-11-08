# -*- coding: utf-8 -*-
"""
Engineering & Site Progress Forms
MWHEBA ERP — Track 3 (WBS & Architectural Site Progress)
"""
from django import forms
from django.utils.translation import gettext_lazy as _
from real_estate.models import SiteDailyLog, UnitSiteProgressRecord, ProjectActivity


class SiteDailyLogForm(forms.ModelForm):
    """نموذج تسجيل يومية الموقع الميدانية FIDIC"""
    class Meta:
        model = SiteDailyLog
        fields = [
            'project',
            'log_date',
            'weather',
            'total_manpower_count',
            'stoppage_reason',
            'delays_recorded_hours',
            'notes',
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'log_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'weather': forms.Select(attrs={'class': 'form-select'}),
            'total_manpower_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'stoppage_reason': forms.Select(attrs={'class': 'form-select'}),
            'delays_recorded_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': 0}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _('سجل ملاحظات الموقع أو توقفات الصب والأعمال...')}),
        }


class ProjectActivityForm(forms.ModelForm):
    """نموذج إنشاء وتعديل أنشطة مقايسة المشروع WBS مع جسر الربط الميداني للوحدات"""
    class Meta:
        model = ProjectActivity
        fields = [
            'project',
            'block',
            'parent_activity',
            'master_boq_item',
            'code',
            'name',
            'weight_percentage',
            'progress_percentage',
            'is_milestone',
            'activity_type',
            'trade_category',
            'trade_stage',
            'auto_sync_progress',
            'baseline_start_date',
            'baseline_end_date',
            'actual_start_date',
            'actual_end_date',
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'block': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'parent_activity': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'master_boq_item': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'code': forms.TextInput(attrs={'class': 'form-control font-monospace'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'weight_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': 0, 'max': 100}),
            'progress_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0, 'max': 100}),
            'is_milestone': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'activity_type': forms.Select(attrs={'class': 'form-select', 'dir': 'rtl'}),
            'trade_category': forms.Select(attrs={'class': 'form-select', 'dir': 'rtl'}),
            'trade_stage': forms.Select(
                choices=[('', _('--- غير محدد / اختر بنداً معمارياً ---'))] + list(UnitSiteProgressRecord.InspectionTrade.choices),
                attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}
            ),
            'auto_sync_progress': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'baseline_start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'baseline_end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'actual_start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'actual_end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'project' in self.fields:
            self.fields['project'].required = False
        if 'parent_activity' in self.fields:
            self.fields['parent_activity'].required = False
        if 'block' in self.fields:
            self.fields['block'].required = False
        if 'master_boq_item' in self.fields:
            self.fields['master_boq_item'].required = False
