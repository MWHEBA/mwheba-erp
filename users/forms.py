from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from .models import User, Role


class UserCreationForm(forms.ModelForm):
    """
    نموذج إنشاء مستخدم جديد يتضمن كافة الحقول المطلوبة، بالإضافة إلى كلمة مرور مكررة للتحقق
    """

    password1 = forms.CharField(label=_("كلمة المرور"), widget=forms.PasswordInput)
    password2 = forms.CharField(
        label=_("تأكيد كلمة المرور"), widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def clean_password2(self):
        # التحقق من تطابق كلمتي المرور
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("كلمتا المرور غير متطابقتين"))
        return password2

    def save(self, commit=True):
        # حفظ كلمة المرور بصيغة مشفرة
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    """
    نموذج لتحديث معلومات المستخدم، يستخدم ReadOnlyPasswordHashField لعرض كلمة المرور المشفرة فقط
    """

    password = ReadOnlyPasswordHashField(
        label=_("كلمة المرور"),
        help_text=_(
            "كلمات المرور مشفرة، ولا يمكن رؤية كلمة المرور الحالية لهذا المستخدم، "
            'ولكن يمكنك تغييرها باستخدام <a href="../password/">هذا النموذج</a>.'
        ),
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )


class UserProfileForm(forms.ModelForm):
    """
    نموذج تحديث بيانات الملف الشخصي للمستخدم
    """

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "profile_image",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "dir": "ltr"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "profile_image": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }


class RoleForm(forms.ModelForm):
    """
    نموذج إنشاء وتعديل الأدوار
    """
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("الصلاحيات")
    )
    
    class Meta:
        model = Role
        fields = ['name', 'display_name', 'description', 'permissions', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: admin, accountant'
            }),
            'display_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: مدير النظام'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف مختصر للدور وصلاحياته'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['permissions'].queryset = Permission.objects.select_related(
            'content_type'
        ).order_by('content_type__app_label', 'codename')
        
    def get_grouped_permissions(self):
        """تجميع الصلاحيات حسب التطبيق المعياري"""
        app_labels_ar = {
            'sale': 'المبيعات وعروض الأسعار',
            'purchase': 'المشتريات',
            'financial': 'الإدارة المالية والحسابات',
            'product': 'المخازن والمنتجات',
            'customer': 'العملاء',
            'supplier': 'الموردين',
            'users': 'المستخدمين والأدوار',
            'hr': 'الموارد البشرية والرواتب',
            'printing_pricing': 'التسعير وتكاليف الطباعة',
            'work_order': 'أوامر العمل والتشغيل',
        }
        groups = {}
        for perm in self.fields['permissions'].queryset:
            app_label = perm.content_type.app_label
            group_name = app_labels_ar.get(app_label, app_label)
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(perm)
        return groups


class UserRoleForm(forms.ModelForm):
    """
    نموذج تعيين دور وصلاحيات إضافية للمستخدم
    """
    custom_permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("صلاحيات إضافية")
    )
    
    class Meta:
        model = User
        fields = ['role', 'custom_permissions']
        widgets = {
            'role': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].queryset = Role.objects.filter(is_active=True)
        self.fields['custom_permissions'].queryset = Permission.objects.select_related(
            'content_type'
        ).order_by('content_type__app_label', 'codename')
