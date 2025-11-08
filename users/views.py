from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import User, ActivityLog, Role
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from .forms import UserProfileForm, RoleForm, UserRoleForm
from django.contrib.auth.views import LoginView
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.http import JsonResponse
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Count


# دالة تسجيل دخول مخصصة
class CustomLoginView(LoginView):
    """
    عرض مخصص لتسجيل الدخول يضمن أن form دائمًا موجود في السياق
    """

    template_name = "users/login.html"

    def form_invalid(self, form):
        """
        تعديل الدالة لضمان وجود النموذج دائمًا في السياق
        """
        return self.render_to_response(self.get_context_data(form=form))


@login_required
def profile(request):
    """
    عرض وتحديث الملف الشخصي للمستخدم الحالي
    """
    user = request.user

    # إنشاء نموذج لتعديل بيانات المستخدم (بدون الصورة - يتم رفعها تلقائياً)
    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث بياناتك الشخصية بنجاح.")
            return redirect('users:profile')
        else:
            messages.error(request, "حدث خطأ في البيانات المدخلة.")
    else:
        form = UserProfileForm(instance=user)

    context = {
        "user": user,
        "form": form,
        "title": "الملف الشخصي",
        "page_title": "الملف الشخصي",
        "page_subtitle": "إدارة معلوماتك الشخصية وإعدادات حسابك",
        "page_icon": "fas fa-user-circle",
        "header_buttons": [
            {
                "text": f"عضو منذ {user.date_joined.year}",
                "icon": "fa-calendar-alt",
                "class": "bg-primary",
                "is_badge": True,
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الملف الشخصي", "active": True},
        ],
    }

    return render(request, "users/profile.html", context)


@login_required
def user_list(request):
    """
    عرض قائمة المستخدمين (للمديرين فقط)
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    users = User.objects.all()

    # إعداد headers للجدول الموحد
    headers = [
        {"key": "id", "label": "#", "sortable": True},
        {"key": "get_full_name", "label": "الاسم", "sortable": True},
        {"key": "username", "label": "اسم المستخدم", "sortable": True},
        {"key": "email", "label": "البريد الإلكتروني", "sortable": True},
        {"key": "phone", "label": "الهاتف", "sortable": False},
        {"key": "role.display_name", "label": "الدور الوظيفي", "sortable": False},
        {"key": "is_active", "label": "الحالة", "sortable": True, "format": "status"},
        {
            "key": "last_login",
            "label": "آخر دخول",
            "sortable": True,
            "format": "datetime",
        },
    ]

    # إعداد action buttons (يظهر للمديرين فقط)
    action_buttons = []
    if request.user.can_manage_users():
        action_buttons = [
            {
                "label": "الصلاحيات",
                "url": "users:user_permissions",
                "class": "btn-sm btn-outline-info",
                "icon": "fa-key",
            },
            {
                "label": "تعديل",
                "url": "users:user_edit",
                "class": "btn-sm btn-outline-secondary",
                "icon": "fa-edit",
            },
            {
                "label": "حذف",
                "url": "users:user_delete",
                "class": "btn-sm btn-outline-danger",
                "icon": "fa-trash",
                "confirm": "هل أنت متأكد من حذف هذا المستخدم؟",
            },
        ]

    context = {
        "users": users,
        "headers": headers,
        "action_buttons": action_buttons,
        "primary_key": "id",
        "title": "المستخدمين",
        "page_title": "قائمة المستخدمين",
        "page_subtitle": "إدارة مستخدمي النظام",
        "page_icon": "fas fa-users",
        "header_buttons": [
            {
                "url": reverse("users:user_create"),
                "icon": "fa-plus",
                "text": "إضافة مستخدم",
                "class": "btn-primary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "active": True},
        ],
    }

    return render(request, "users/user_list.html", context)


@login_required
def user_create(request):
    """
    إنشاء مستخدم جديد (للمديرين فقط)
    """
    if not request.user.can_manage_users():
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية لإضافة مستخدمين"},
        )
    
    if request.method == 'POST':
        from .forms import UserCreationForm
        form = UserCreationForm(request.POST)
        
        if form.is_valid():
            try:
                user = form.save()
                
                # تعيين الدور إذا تم تحديده
                role_id = request.POST.get('role')
                if role_id:
                    try:
                        role = Role.objects.get(id=role_id)
                        user.role = role
                        user.save()
                    except Role.DoesNotExist:
                        pass
                
                messages.success(request, f'تم إنشاء المستخدم "{user.get_full_name()}" بنجاح')
                return redirect('users:user_list')
            except Exception as e:
                messages.error(request, f'حدث خطأ: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        from .forms import UserCreationForm
        form = UserCreationForm()
    
    # جلب الأدوار المتاحة
    roles = Role.objects.filter(is_active=True)
    
    context = {
        "form": form,
        "roles": roles,
        "page_title": "إضافة مستخدم جديد",
        "page_subtitle": "إضافة مستخدم جديد للنظام",
        "page_icon": "fas fa-user-plus",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "url": reverse("users:user_list"), "icon": "fas fa-users"},
            {"title": "إضافة مستخدم", "active": True},
        ],
    }
    
    return render(request, 'users/user_create.html', context)


@login_required
def user_edit(request, user_id):
    """
    تعديل بيانات مستخدم (للمديرين فقط)
    """
    from django.http import JsonResponse
    
    if not request.user.can_manage_users():
        return JsonResponse({
            'success': False,
            'message': 'ليس لديك صلاحية لتعديل المستخدمين'
        })
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        try:
            # تحديث البيانات
            user.first_name = request.POST.get('first_name', user.first_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            user.email = request.POST.get('email', user.email)
            user.phone = request.POST.get('phone', user.phone)
            user.is_active = request.POST.get('is_active') == 'on'
            user.save()
            
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث بيانات المستخدم "{user.get_full_name()}" بنجاح'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            })
    
    # GET request - إرجاع بيانات المستخدم
    return JsonResponse({
        'success': True,
        'user': {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
            'email': user.email,
            'phone': user.phone or '',
            'is_active': user.is_active,
        }
    })


@login_required
def user_delete(request, user_id):
    """
    حذف مستخدم (للمديرين فقط)
    """
    if not request.user.can_manage_users():
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية لحذف المستخدمين"},
        )
    
    user = get_object_or_404(User, id=user_id)
    
    # منع حذف نفسك
    if user == request.user:
        messages.error(request, 'لا يمكنك حذف حسابك الخاص!')
        return redirect('users:user_list')
    
    # منع حذف superuser
    if user.is_superuser:
        messages.error(request, 'لا يمكن حذف مدير النظام الرئيسي!')
        return redirect('users:user_list')
    
    if request.method == 'POST':
        user_name = user.get_full_name()
        user.delete()
        messages.success(request, f'تم حذف المستخدم "{user_name}" بنجاح')
        return redirect('users:user_list')
    
    # إذا كان GET، نعرض صفحة تأكيد الحذف
    context = {
        "user": user,
        "page_title": f'حذف المستخدم: {user.get_full_name()}',
        "page_icon": "fas fa-user-times",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "url": reverse("users:user_list"), "icon": "fas fa-users"},
            {"title": f'حذف: {user.get_full_name()}', "active": True},
        ],
    }
    
    return render(request, 'users/user_delete_confirm.html', context)


@login_required
def activity_log(request):
    """
    عرض سجل النشاطات مع إمكانية الفلترة
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # جلب جميع النشاطات
    activities = ActivityLog.objects.select_related('user').all()
    
    # فلترة حسب المستخدم
    user_filter = request.GET.get('user')
    if user_filter:
        activities = activities.filter(user_id=user_filter)
    
    # فلترة حسب نوع النشاط
    action_filter = request.GET.get('action')
    if action_filter:
        activities = activities.filter(action__icontains=action_filter)
    
    # فلترة حسب التاريخ
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        activities = activities.filter(timestamp__date__gte=date_from)
    if date_to:
        activities = activities.filter(timestamp__date__lte=date_to)
    
    # ترتيب وتحديد العدد
    activities = activities.order_by("-timestamp")[:100]
    
    # جلب قائمة المستخدمين للفلترة
    users = User.objects.filter(is_active=True).order_by('username')

    context = {
        "activities": activities,
        "users": users,
        "selected_user": user_filter,
        "selected_action": action_filter,
        "date_from": date_from,
        "date_to": date_to,
        "page_title": "سجل النشاطات",
        "page_subtitle": "عرض آخر النشاطات التي تمت في النظام",
        "page_icon": "fas fa-history",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "url": reverse("users:user_list"), "icon": "fas fa-users"},
            {"title": "سجل النشاطات", "active": True},
        ],
    }

    return render(request, "users/activity_log.html", context)


@login_required
def update_profile_image(request):
    """
    تحديث أو حذف الصورة الشخصية عبر AJAX
    """
    if request.method == 'POST':
        user = request.user
        action = request.POST.get('action')
        
        if action == 'delete':
            # حذف الصورة
            if user.profile_image:
                user.profile_image.delete(save=False)
                user.profile_image = None
                user.save()
                return JsonResponse({
                    'success': True,
                    'message': 'تم حذف الصورة بنجاح',
                    'has_image': False
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'لا توجد صورة لحذفها'
                }, status=400)
        
        elif action == 'upload':
            # رفع صورة جديدة
            if 'profile_image' in request.FILES:
                # حذف الصورة القديمة إن وجدت
                if user.profile_image:
                    user.profile_image.delete(save=False)
                
                user.profile_image = request.FILES['profile_image']
                user.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'تم رفع الصورة بنجاح',
                    'image_url': user.profile_image.url,
                    'has_image': True
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'لم يتم اختيار صورة'
                }, status=400)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
def change_password_ajax(request):
    """
    تغيير كلمة المرور عبر AJAX
    """
    if request.method == 'POST':
        # طباعة البيانات المستلمة للتأكد
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"POST data: {request.POST}")
        
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # تحديث الجلسة لتجنب تسجيل الخروج
            update_session_auth_hash(request, user)
            return JsonResponse({
                'success': True,
                'message': 'تم تغيير كلمة المرور بنجاح'
            })
        else:
            # طباعة الأخطاء للتشخيص
            logger.info(f"Form errors: {form.errors}")
            logger.info(f"Form errors dict: {dict(form.errors)}")
            
            # إرجاع الأخطاء مترجمة
            errors = []
            
            # أخطاء كلمة المرور القديمة
            if 'old_password' in form.errors:
                errors.append('كلمة المرور الحالية غير صحيحة')
            
            # أخطاء كلمة المرور الجديدة
            if 'new_password1' in form.errors:
                for error in form.errors['new_password1']:
                    error_str = str(error)
                    if 'too short' in error_str or 'قصيرة' in error_str:
                        errors.append('كلمة المرور الجديدة قصيرة جداً (يجب أن تكون 8 أحرف على الأقل)')
                    elif 'too common' in error_str or 'شائعة' in error_str:
                        errors.append('كلمة المرور الجديدة شائعة جداً')
                    elif 'numeric' in error_str or 'أرقام' in error_str:
                        errors.append('كلمة المرور لا يمكن أن تكون أرقام فقط')
                    elif 'similar' in error_str or 'مشابهة' in error_str:
                        errors.append('كلمة المرور مشابهة جداً لمعلوماتك الشخصية')
                    else:
                        errors.append(error_str)
            
            # أخطاء تأكيد كلمة المرور
            if 'new_password2' in form.errors:
                for error in form.errors['new_password2']:
                    error_str = str(error)
                    if "didn't match" in error_str or 'لا تتطابق' in error_str or "didn't match" in error_str:
                        errors.append('كلمتا المرور الجديدتان غير متطابقتين')
                    else:
                        errors.append(error_str)
            
            # إذا لم نجد أخطاء محددة، نضيف رسالة عامة
            if not errors:
                errors.append('حدث خطأ في البيانات المدخلة. يرجى المحاولة مرة أخرى.')
            
            return JsonResponse({
                'success': False,
                'errors': errors,
                'debug_errors': dict(form.errors)  # للتشخيص فقط
            }, status=400)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


# ==================== إدارة الأدوار ====================

@login_required
def role_list(request):
    """
    عرض قائمة الأدوار
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )
    
    # جلب جميع الأدوار مع عدد المستخدمين
    roles = Role.objects.annotate(
        total_users=Count('users')
    ).order_by('-is_system_role', 'display_name')
    
    # البحث
    search = request.GET.get('search', '')
    if search:
        roles = roles.filter(
            Q(name__icontains=search) |
            Q(display_name__icontains=search) |
            Q(description__icontains=search)
        )
    
    context = {
        "roles": roles,
        "search": search,
        "page_title": "إدارة الأدوار",
        "page_subtitle": "إدارة أدوار المستخدمين وصلاحياتهم",
        "page_icon": "fas fa-user-tag",
        "header_buttons": [
            {
                "url": reverse("users:role_create"),
                "icon": "fa-plus",
                "text": "إضافة دور جديد",
                "class": "btn-primary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "url": reverse("users:user_list"), "icon": "fas fa-users"},
            {"title": "الأدوار", "active": True},
        ],
    }
    
    return render(request, "users/roles/role_list.html", context)


@login_required
def role_create(request):
    """
    إنشاء دور جديد
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )
    
    if request.method == 'POST':
        form = RoleForm(request.POST)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'تم إنشاء الدور "{role.display_name}" بنجاح')
            return redirect('users:role_list')
    else:
        form = RoleForm()
    
    # الحصول على الصلاحيات المقسمة
    grouped_permissions = form.get_grouped_permissions()
    
    context = {
        "form": form,
        "grouped_permissions": grouped_permissions,
        "page_title": "إنشاء دور جديد",
        "page_subtitle": "إضافة دور جديد مع صلاحيات مخصصة",
        "page_icon": "fas fa-plus",
        "header_buttons": [
            {
                "url": reverse("users:role_list"),
                "icon": "fa-list",
                "text": "العودة للقائمة",
                "class": "btn-outline-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "url": reverse("users:user_list"), "icon": "fas fa-users"},
            {"title": "الأدوار", "url": reverse("users:role_list")},
            {"title": "إنشاء دور", "active": True},
        ],
    }
    
    return render(request, "users/roles/role_form.html", context)


@login_required
def role_edit(request, role_id):
    """
    تعديل دور موجود
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )
    
    role = get_object_or_404(Role, id=role_id)
    
    if request.method == 'POST':
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'تم تحديث الدور "{role.display_name}" بنجاح')
            return redirect('users:role_list')
    else:
        form = RoleForm(instance=role)
    
    # الحصول على الصلاحيات المقسمة
    grouped_permissions = form.get_grouped_permissions()
    
    context = {
        "form": form,
        "role": role,
        "grouped_permissions": grouped_permissions,
        "page_title": f'تعديل الدور: {role.display_name}',
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "url": reverse("users:user_list"), "icon": "fas fa-users"},
            {"title": "الأدوار", "url": reverse("users:role_list")},
            {"title": role.display_name, "active": True},
        ],
    }
    
    return render(request, "users/roles/role_form.html", context)


@login_required
def role_delete(request, role_id):
    """
    حذف دور
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.can_manage_roles():
        messages.error(request, 'ليس لديك صلاحية لحذف الأدوار')
        return redirect('users:role_list')
    
    role = get_object_or_404(Role, id=role_id)
    
    # التحقق من أن الدور ليس دور نظام
    if role.is_system_role:
        messages.error(request, 'لا يمكن حذف أدوار النظام الأساسية')
        return redirect('users:role_list')
    
    # التحقق من عدم وجود مستخدمين
    if role.users.exists():
        return JsonResponse({
            'success': False,
            'message': f'لا يمكن حذف الدور لأنه مرتبط بـ {role.users.count()} مستخدم'
        }, status=400)
    
    role_name = role.display_name
    role.delete()
    
    messages.success(request, f'تم حذف الدور "{role_name}" بنجاح')
    return redirect('users:role_list')


@login_required
def user_permissions(request, user_id):
    """
    إدارة صلاحيات مستخدم معين
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = UserRoleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تحديث صلاحيات المستخدم "{user}" بنجاح')
            return redirect('users:user_list')
    else:
        form = UserRoleForm(instance=user)
    
    # تنظيم الصلاحيات حسب التطبيق
    permissions_by_app = {}
    for perm in Permission.objects.select_related('content_type').order_by('content_type__app_label', 'codename'):
        app_label = perm.content_type.app_label
        if app_label not in permissions_by_app:
            permissions_by_app[app_label] = []
        permissions_by_app[app_label].append(perm)
    
    # الحصول على جميع صلاحيات المستخدم
    user_all_permissions = user.get_all_permissions()
    role_permissions = set(user.role.permissions.all()) if user.role else set()
    
    context = {
        "form": form,
        "target_user": user,
        "permissions_by_app": permissions_by_app,
        "user_all_permissions": user_all_permissions,
        "role_permissions": role_permissions,
        "page_title": f'صلاحيات: {user}',
        "page_icon": "fas fa-key",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "url": reverse("users:user_list"), "icon": "fas fa-users"},
            {"title": str(user), "active": True},
        ],
    }
    
    return render(request, "users/roles/user_permissions.html", context)
