from django.db import models
from django.contrib.auth.models import AbstractUser, Permission
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from core.security.file_validators import validate_secure_image, secure_upload_path


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
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['is_system_role']),
            models.Index(fields=['name']),
            models.Index(fields=['is_active', 'display_name']),
        ]
    
    def __str__(self):
        return self.display_name
    
    @property
    def users_count(self):
        """عدد المستخدمين في هذا الدور"""
        if hasattr(self, 'users_count_annotated'):
            return self.users_count_annotated
        return self.users.count()
    
    @property
    def permissions_count(self):
        """عدد الصلاحيات في هذا الدور"""
        if hasattr(self, 'permissions_count_annotated'):
            return self.permissions_count_annotated
        return self.permissions.count()
    
    def get_total_users(self):
        """الحصول على عدد المستخدمين"""
        return self.users.count()
    
    def has_permission(self, permission_codename):
        """التحقق من وجود صلاحية معينة في الدور"""
        return self.permissions.filter(codename=permission_codename).exists()
    
    def get_permissions_by_app(self, app_label):
        """الحصول على صلاحيات الدور لتطبيق معين"""
        return self.permissions.filter(content_type__app_label=app_label)


class User(AbstractUser):
    """
    نموذج المستخدم المخصص يوسع نموذج Django الأساسي
    """

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
        _("الصورة الشخصية"), 
        upload_to=secure_upload_path, 
        blank=True, 
        null=True,
        validators=[validate_secure_image],
        help_text=_("الحد الأقصى: 5MB، الأنواع المسموحة: JPG, PNG, GIF")
    )
    status = models.CharField(
        _("الحالة"), max_length=10, choices=USER_STATUS, default="active"
    )
    address = models.TextField(_("العنوان"), blank=True, null=True)
    
    # نظام الأدوار والصلاحيات الموحد
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
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active', 'role']),
            models.Index(fields=['email']),
            models.Index(fields=['date_joined']),
        ]

    def __str__(self):
        return (
            f"{self.first_name} {self.last_name}"
            if self.first_name and self.last_name
            else self.username
        )

    @property
    def is_admin(self):
        return self.is_superuser or bool(self.role and self.role.name == "admin")

    @property
    def is_sales_rep(self):
        return bool(self.role and self.role.name == "sales_rep")

    @property
    def is_accountant(self):
        return bool(self.role and self.role.name == "accountant")

    @property
    def is_financial_manager(self):
        return bool(self.role and self.role.name == "financial_manager")

    @property
    def is_procurement_officer(self):
        return bool(self.role and self.role.name == "procurement_officer")

    @property
    def is_inventory_manager(self):
        return bool(self.role and self.role.name == "inventory_manager")

    @property
    def is_production_supervisor(self):
        return bool(self.role and self.role.name == "production_supervisor")

    @property
    def is_sales_manager(self):
        return bool(self.role and self.role.name == "sales_manager")

    @property
    def is_hr_officer(self):
        return bool(self.role and self.role.name == "hr_officer")

    @property
    def is_viewer(self):
        return bool(self.role and self.role.name == "viewer")

    def get_all_permissions(self, obj=None):
        """
        الحصول على جميع صلاحيات المستخدم كنصوص قياسية بصيغة 'app_label.codename'
        متوافقة 100% مع عقد جانغو القياسي.
        """
        if not self.is_authenticated or not self.is_active:
            return set()

        if self.is_superuser or self.is_admin:
            return {f"{p.content_type.app_label}.{p.codename}" for p in Permission.objects.all()}

        perms = set()
        if self.role:
            perms.update(
                f"{p.content_type.app_label}.{p.codename}"
                for p in self.role.permissions.select_related('content_type')
            )
        if hasattr(self, 'custom_permissions'):
            perms.update(
                f"{p.content_type.app_label}.{p.codename}"
                for p in self.custom_permissions.select_related('content_type')
            )
        return perms

    def get_all_permission_objects(self):
        """
        الحصول على كائنات Permission للمستخدم لمن يحتاجها.
        """
        if self.is_superuser or self.is_admin:
            return set(Permission.objects.all())
        perms = set()
        if self.role:
            perms.update(self.role.permissions.select_related('content_type'))
        if hasattr(self, 'custom_permissions'):
            perms.update(self.custom_permissions.select_related('content_type'))
        return perms

    def has_role_permission(self, perm):
        """
        التحقق من وجود صلاحية معينة عبر المسار القياسي الموحد لجانغو.
        """
        return self.has_perm(perm)

    def can_manage_users(self):
        """التحقق من صلاحية إدارة المستخدمين"""
        return self.is_superuser or self.is_admin or self.has_perm('users.change_user')

    def can_manage_roles(self):
        """التحقق من صلاحية إدارة الأدوار"""
        return self.is_superuser or self.is_admin or self.has_perm('users.change_role')

    def has_role_by_name(self, role_name):
        """التحقق من وجود دور معين بالاسم"""
        return bool(self.role and self.role.name == role_name)

    def get_role_permissions_list(self):
        """الحصول على قائمة بأسماء صلاحيات الدور"""
        if not self.role:
            return []
        return [f"{p.content_type.app_label}.{p.codename}" for p in self.role.permissions.select_related('content_type')]



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
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"

    @property
    def description(self):
        if isinstance(self.extra_data, dict):
            return self.extra_data.get('description') or self.extra_data.get('details') or self.action
        return self.action

    @property
    def action_class(self):
        action_lower = self.action.strip()
        if action_lower.startswith('إنشاء'):
            return 'bg-success-soft'
        elif action_lower.startswith('تعديل'):
            return 'bg-warning-soft'
        elif action_lower.startswith('حذف'):
            return 'bg-danger-soft'
        elif 'دخول' in action_lower and 'فشل' not in action_lower:
            return 'bg-info-soft'
        elif 'خروج' in action_lower:
            return 'bg-secondary-soft'
        elif 'فشل' in action_lower:
            return 'bg-danger-soft'
        return 'bg-primary-soft'

    @property
    def action_icon(self):
        action_lower = self.action.strip()
        if action_lower.startswith('إنشاء'):
            return 'fas fa-plus-circle'
        elif action_lower.startswith('تعديل'):
            return 'fas fa-edit'
        elif action_lower.startswith('حذف'):
            return 'fas fa-trash-alt'
        elif 'دخول' in action_lower and 'فشل' not in action_lower:
            return 'fas fa-sign-in-alt'
        elif 'خروج' in action_lower:
            return 'fas fa-sign-out-alt'
        elif 'فشل' in action_lower:
            return 'fas fa-exclamation-triangle'
        return 'fas fa-info-circle'

    @property
    def model_name_ar(self):
        model_translations = {
            'Customer': 'العملاء',
            'Supplier': 'الموردين',
            'Product': 'المنتجات',
            'Sale': 'المبيعات',
            'Purchase': 'المشتريات',
            'User': 'المستخدمين',
            'Role': 'الأدوار والصلاحيات',
            'Warehouse': 'المخازن',
            'Stock': 'المخزون',
            'StockMovement': 'حركات المخزون',
            'SerialNumber': 'الأرقام التسلسلية',
            'SupplierProductPrice': 'أسعار المنتجات من الموردين',
            'PriceHistory': 'سجل الأسعار',
            'BatchVoucher': 'أذونات دفعات المنتجات',
            'BatchVoucherItem': 'بنود أذونات الدفعات',
            'Category': 'التصنيفات',
            'Unit': 'وحدات القياس',
            'StockTransfer': 'تحويلات المخزون',
            'StockSnapshot': 'لقطات المخزون',
            'InventoryAdjustment': 'تسويات المخزون',
            'StockReservation': 'حجوزات المخزون',
            'ProductBatch': 'تشغيلات المنتجات',
            'LocationZone': 'مناطق المواقع بالمخزن',
            'ProductLocation': 'موقع المنتج بالمخزن',
        }
        return model_translations.get(self.model_name, self.model_name)
