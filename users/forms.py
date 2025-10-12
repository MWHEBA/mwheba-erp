from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth import get_user_model
from .models import User


class UserCreationForm(forms.ModelForm):
    """
    نموذج إنشاء مستخدم جديد يتضمن كافة الحقول المطلوبة، بالإضافة إلى كلمة مرور مكررة للتحقق
    """
    password1 = forms.CharField(label=_('كلمة المرور'), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_('تأكيد كلمة المرور'), widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

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
            "ولكن يمكنك تغييرها باستخدام <a href=\"../password/\">هذا النموذج</a>."
        ),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')


class UserProfileForm(forms.ModelForm):
    """
    نموذج تحديث بيانات الملف الشخصي للمستخدم
    """
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone', 
            'address', 'profile_image'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'dir': 'ltr'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'dir': 'ltr'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'profile_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        } 