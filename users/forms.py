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
        # الحصول على الصلاحيات المخصصة فقط (بالعربي)
        from users.models import User
        user_content_type = ContentType.objects.get_for_model(User)
        self.fields['permissions'].queryset = Permission.objects.filter(
            content_type=user_content_type
        ).order_by('name')
        
    def get_grouped_permissions(self):
        """تجميع الصلاحيات حسب الفئة"""
        permissions = self.fields['permissions'].queryset
        
        groups = {
            'المبيعات': [],
            'المشتريات': [],
            'العملاء': [],
            'الموردين': [],
            'المنتجات والمخزون': [],
            'المحاسبة والمالية': [],
            'التقارير': [],
            'المستخدمين والنظام': [],
            'الإعدادات': [],
            'صلاحيات خاصة': [],
        }
        
        for perm in permissions:
            codename = perm.codename
            
            if 'مبيعات' in codename:
                groups['المبيعات'].append(perm)
            elif 'مشتريات' in codename:
                groups['المشتريات'].append(perm)
            elif 'عملاء' in codename:
                groups['العملاء'].append(perm)
            elif 'موردين' in codename:
                groups['الموردين'].append(perm)
            elif 'منتجات' in codename or 'مخزون' in codename or 'مخازن' in codename:
                groups['المنتجات والمخزون'].append(perm)
            elif 'محاسبة' in codename or 'مصروفات' in codename or 'ايرادات' in codename or 'خزن' in codename or 'فترات' in codename:
                groups['المحاسبة والمالية'].append(perm)
            elif 'تقارير' in codename:
                groups['التقارير'].append(perm)
            elif 'مستخدمين' in codename or 'ادوار' in codename or 'نشاطات' in codename:
                groups['المستخدمين والنظام'].append(perm)
            elif 'اعدادات' in codename or 'نسخ' in codename or 'سلامة' in codename or 'تسعير' in codename or 'خدمات' in codename:
                groups['الإعدادات'].append(perm)
            elif 'حذف' in codename or 'اعتماد' in codename or 'تعديل_المعاملات' in codename:
                groups['صلاحيات خاصة'].append(perm)
        
        # إزالة المجموعات الفارغة
        return {k: v for k, v in groups.items() if v}


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
