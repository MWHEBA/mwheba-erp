from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.models import Permission
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


BUSINESS_APPS = [
    'sale',
    'purchase',
    'financial',
    'product',
    'customer',
    'supplier',
    'users',
    'hr',
    'printing_pricing',
    'work_order',
]


class RoleForm(forms.ModelForm):
    """
    نموذج إنشاء وتعديل الأدوار
    """
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("الصلاحيات")
    )
    
    class Meta:
        model = Role
        fields = ['name', 'display_name', 'description', 'parent_role', 'permissions', 'is_active']
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
            'parent_role': forms.Select(attrs={
                'class': 'form-select select2-filter',
                'dir': 'rtl'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['permissions'].queryset = Permission.objects.filter(
            content_type__app_label__in=BUSINESS_APPS
        ).select_related(
            'content_type'
        ).order_by('content_type__app_label', 'codename')

        self.fields['parent_role'].queryset = Role.objects.filter(is_active=True).order_by('display_name')
        if self.instance and self.instance.pk:
            # استبعاد الدور نفسه وجميع أحفاده لمنع الحلقات التكرارية
            exclude_ids = {self.instance.pk}
            if hasattr(self.instance, 'get_all_descendant_roles'):
                exclude_ids.update(r.pk for r in self.instance.get_all_descendant_roles())
            self.fields['parent_role'].queryset = self.fields['parent_role'].queryset.exclude(pk__in=exclude_ids)
        
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
        return groups

    def save(self, commit=True):
        role = super().save(commit=commit)
        if commit:
            from users.services.permission_dependency import PermissionDependencyService
            PermissionDependencyService.auto_resolve_dependencies_for_role(role)
        else:
            original_save_m2m = getattr(self, 'save_m2m', None)
            def _save_m2m():
                if original_save_m2m:
                    original_save_m2m()
                from users.services.permission_dependency import PermissionDependencyService
                PermissionDependencyService.auto_resolve_dependencies_for_role(role)
            self.save_m2m = _save_m2m
        return role



class UserRoleForm(forms.ModelForm):
    """
    نموذج تعيين دور وصلاحيات إضافية للمستخدم
    """
    secondary_roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        required=False,
        label=_("الأدوار الثانوية")
    )
    custom_permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("صلاحيات إضافية")
    )
    
    class Meta:
        model = User
        fields = ['role', 'secondary_roles', 'custom_permissions']
        widgets = {
            'role': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].queryset = Role.objects.filter(is_active=True).order_by('display_name')
        self.fields['secondary_roles'].queryset = Role.objects.filter(is_active=True).order_by('display_name')
        self.fields['custom_permissions'].queryset = Permission.objects.filter(
            content_type__app_label__in=BUSINESS_APPS
        ).select_related(
            'content_type'
        ).order_by('content_type__app_label', 'codename')

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            if 'secondary_roles' in self.cleaned_data:
                user.secondary_roles.set(self.cleaned_data['secondary_roles'])
            self._resolve_user_custom_permission_deps(user)
        else:
            original_save_m2m = getattr(self, 'save_m2m', None)
            def _save_m2m():
                if original_save_m2m:
                    original_save_m2m()
                if 'secondary_roles' in self.cleaned_data:
                    user.secondary_roles.set(self.cleaned_data['secondary_roles'])
                self._resolve_user_custom_permission_deps(user)
            self.save_m2m = _save_m2m
        return user

    def _resolve_user_custom_permission_deps(self, user):
        from users.services.permission_dependency import PermissionDependencyService
        PermissionDependencyService.auto_resolve_dependencies_for_user(user)

