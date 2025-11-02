from django.db import models
from django.contrib.auth.models import AbstractUser, Permission
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator


class Role(models.Model):
    """
    نموذج الأدوار - يحدد مجموعة من الصلاحيات للمستخدمين
    """
    name = models.CharField(_("اسم الدور"), max_length=50, unique=True)
    display_name = models.CharField(_("الاسم المعروض"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True)
    permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("الصلاحيات"),
        blank=True,
        related_name="user_roles"
    )
    is_system_role = models.BooleanField(
        _("دور نظام"),
        default=False,
        help_text=_("الأدوار الأساسية لا يمكن حذفها")
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    
    class Meta:
        verbose_name = _("دور")
        verbose_name_plural = _("الأدوار")
        ordering = ["display_name"]
    
    def __str__(self):
        return self.display_name
    
    @property
    def users_count(self):
        """عدد المستخدمين في هذا الدور"""
        return self.users.count()
    
    @property
    def permissions_count(self):
        """عدد الصلاحيات في هذا الدور"""
        return self.permissions.count()
    
    def get_total_users(self):
        """الحصول على عدد المستخدمين (method بدلاً من property)"""
        return self.users.count()


class User(AbstractUser):
    """
    نموذج المستخدم المخصص يوسع نموذج Django الأساسي
    """

    USER_TYPES = (
        ("admin", _("مدير")),
        ("accountant", _("محاسب")),
        ("inventory_manager", _("أمين مخزن")),
        ("sales_rep", _("مندوب مبيعات")),
    )

    USER_STATUS = (
        ("active", _("نشط")),
        ("inactive", _("غير نشط")),
    )

    phone_regex = RegexValidator(
        regex=r"^\+?1?\d{9,15}$",
        message=_(
            "يجب أن يكون رقم الهاتف بالصيغة: '+999999999'. يسمح بـ 15 رقم كحد أقصى."
        ),
    )

    email = models.EmailField(_("البريد الإلكتروني"), unique=True)
    phone = models.CharField(
        _("رقم الهاتف"), validators=[phone_regex], max_length=17, blank=True
    )
    profile_image = models.ImageField(
        _("الصورة الشخصية"), upload_to="profile_images", blank=True, null=True
    )
    user_type = models.CharField(
        _("نوع المستخدم"), max_length=20, choices=USER_TYPES, default="sales_rep"
    )
    status = models.CharField(
        _("الحالة"), max_length=10, choices=USER_STATUS, default="active"
    )
    address = models.TextField(_("العنوان"), blank=True, null=True)
    
    # نظام الأدوار والصلاحيات الجديد
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("الدور"),
        related_name="users",
        help_text=_("الدور الأساسي للمستخدم")
    )
    custom_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("صلاحيات إضافية"),
        blank=True,
        related_name="users_with_custom_permissions",
        help_text=_("صلاحيات إضافية خارج الدور الأساسي")
    )

    class Meta:
        verbose_name = _("مستخدم")
        verbose_name_plural = _("المستخدمين")

    def __str__(self):
        return (
            f"{self.first_name} {self.last_name}"
            if self.first_name and self.last_name
            else self.username
        )

    @property
    def is_admin(self):
        return self.user_type == "admin"

    @property
    def is_accountant(self):
        return self.user_type == "accountant"

    @property
    def is_inventory_manager(self):
        return self.user_type == "inventory_manager"

    @property
    def is_sales_rep(self):
        return self.user_type == "sales_rep"
    
    def get_all_permissions(self):
        """
        الحصول على جميع صلاحيات المستخدم (من الدور + الصلاحيات الإضافية)
        """
        perms = set()
        
        # صلاحيات Django الأساسية
        if self.is_superuser:
            from django.contrib.auth.models import Permission
            return set(Permission.objects.all())
        
        # صلاحيات من الدور
        if self.role:
            perms.update(self.role.permissions.all())
        
        # الصلاحيات الإضافية
        perms.update(self.custom_permissions.all())
        
        # صلاحيات Django Groups
        for group in self.groups.all():
            perms.update(group.permissions.all())
        
        return perms
    
    def has_role_permission(self, perm):
        """
        التحقق من وجود صلاحية معينة
        perm: اسم الصلاحية بالعربي (مثال: 'ادارة_المستخدمين')
        """
        if self.is_superuser or self.is_admin:
            return True
        
        return perm in [p.codename for p in self.get_all_permissions()]
    
    def can_manage_users(self):
        """التحقق من صلاحية إدارة المستخدمين"""
        return self.is_superuser or self.is_admin or self.has_role_permission('ادارة_المستخدمين')
    
    def can_manage_roles(self):
        """التحقق من صلاحية إدارة الأدوار"""
        return self.is_superuser or self.is_admin or self.has_role_permission('ادارة_الادوار_والصلاحيات')


class ActivityLog(models.Model):
    """
    سجل نشاطات المستخدمين في النظام
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("المستخدم"))
    action = models.CharField(_("الإجراء"), max_length=255)
    model_name = models.CharField(
        _("اسم النموذج"), max_length=100, blank=True, null=True
    )
    object_id = models.PositiveIntegerField(_("معرف الكائن"), blank=True, null=True)
    timestamp = models.DateTimeField(_("التوقيت"), auto_now_add=True)
    ip_address = models.GenericIPAddressField(_("عنوان IP"), blank=True, null=True)
    user_agent = models.TextField(_("متصفح المستخدم"), blank=True, null=True)
    extra_data = models.JSONField(_("بيانات إضافية"), blank=True, null=True)

    class Meta:
        verbose_name = _("سجل النشاطات")
        verbose_name_plural = _("سجلات النشاطات")
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"
