from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
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
    ويحترم الـ next parameter للـ redirect بعد اللوجن
    """

    template_name = "users/login.html"

    def get_success_url(self):
        """
        Redirect to 'next' if present and safe, otherwise go to LOGIN_REDIRECT_URL
        """
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url:
            from django.utils.http import url_has_allowed_host_and_scheme
            if url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts=self.request.get_host(),
                require_https=self.request.is_secure(),
            ):
                return next_url
        return str(self.get_default_redirect_url())

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
@permission_required('users.view_user', raise_exception=True)
def user_list(request):
    """
    عرض قائمة المستخدمين (للمديرين فقط)
    """
    # تنظيف شامل لأي رسائل قديمة
    from django.contrib import messages
    from django.core.paginator import Paginator
    from django.core.cache import cache
    
    # طريقة أقوى لتنظيف الرسائل
    storage = messages.get_messages(request)
    storage.used = True  # تعليم جميع الرسائل كمستخدمة
    
    # تنظيف إضافي للـ session
    if '_messages' in request.session:
        del request.session['_messages']
    
    # التحقق من صلاحيات المستخدم - إضافة طبقة حماية إضافية
    if not request.user.is_admin and not request.user.is_superuser and not request.user.can_manage_users():
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # استخدام select_related لتحسين الأداء وتجنب N+1 queries
    # only() لجلب الحقول المطلوبة فقط
    users = User.objects.select_related('role').only(
        'id', 'first_name', 'last_name', 'username', 'email', 'phone',
        'is_active', 'last_login', 'role__name', 'role__display_name'
    ).order_by('-id')

    # Pagination - عرض 50 مستخدم في الصفحة
    paginator = Paginator(users, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # إعداد headers للجدول الموحد
    headers = [
        {"key": "id", "label": "#", "sortable": True, "width": "8%"},
        {"key": "get_full_name", "label": "الاسم", "sortable": True, "width": "20%"},
        {"key": "username", "label": "اسم المستخدم", "sortable": True, "width": "20%"},
        {"key": "phone", "label": "الهاتف", "sortable": False, "width": "15%"},
        {"key": "role", "label": "الدور", "sortable": False, "width": "15%", "format": "role_badge"},
        {"key": "is_active", "label": "الحالة", "sortable": True, "format": "status", "width": "10%", "class": "text-center"},
        {
            "key": "last_login",
            "label": "آخر دخول",
            "sortable": True,
            "format": "datetime",
            "width": "12%",
            "class": "text-center"
        }
    ]

    # إعداد action buttons (يظهر للمديرين فقط)
    action_buttons = []
    if request.user.can_manage_users():
        action_buttons = [
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
        "users": page_obj,  # استخدام page_obj بدل users
        "page_obj": page_obj,  # للـ pagination controls
        "headers": headers,
        "action_buttons": action_buttons,
        "primary_key": "id",
        "title": "المستخدمين",
        "page_title": "قائمة المستخدمين",
        "page_subtitle": f"إدارة مستخدمي النظام ({paginator.count} مستخدم)",
        "page_icon": "fas fa-users",
        "header_buttons": [
            {
                "url": reverse("users:user_create"),
                "icon": "fa-plus",
                "text": "إضافة مستخدم",
                "class": "btn-primary",
            },
            {
                "url": reverse("users:permissions_dashboard"),
                "icon": "fa-shield-alt",
                "text": "إدارة الأدوار",
                "class": "btn-outline-primary",
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
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Role with id {role_id} not found")
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
            user.first_name = request.POST.get('first_name', user.first_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            user.email = request.POST.get('email', user.email)
            user.phone = request.POST.get('phone', user.phone)
            user.address = request.POST.get('address', user.address)
            user.user_type = request.POST.get('user_type', user.user_type)
            user.is_active = request.POST.get('is_active') == 'on'

            role_id = request.POST.get('role_id')
            if role_id:
                user.role = Role.objects.filter(id=role_id).first()
            elif role_id == '':
                user.role = None

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

    # GET request - إرجاع بيانات المستخدم مع قائمة الأدوار
    roles = list(Role.objects.filter(is_active=True).values('id', 'display_name'))
    return JsonResponse({
        'success': True,
        'user': {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
            'email': user.email,
            'phone': user.phone or '',
            'address': user.address or '',
            'user_type': user.user_type,
            'is_active': user.is_active,
            'role_id': user.role.id if user.role else None,
        },
        'roles': roles,
        'user_types': [{'value': k, 'label': str(v)} for k, v in User.USER_TYPES],
    })


@login_required
def user_delete(request, user_id):
    """
    حذف مستخدم عبر AJAX (للمديرين فقط)
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)
    
    if not request.user.can_manage_users():
        return JsonResponse({
            'success': False, 
            'message': 'ليس لديك صلاحية لحذف المستخدمين'
        }, status=403)
    
    user = get_object_or_404(User, id=user_id)
    
    # منع حذف نفسك
    if user == request.user:
        return JsonResponse({
            'success': False,
            'message': 'لا يمكنك حذف حسابك الخاص!'
        }, status=400)
    
    # منع حذف superuser
    if user.is_superuser:
        return JsonResponse({
            'success': False,
            'message': 'لا يمكن حذف مدير النظام الرئيسي!'
        }, status=400)
    
    try:
        user_name = user.get_full_name()
        user.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'تم حذف المستخدم "{user_name}" بنجاح'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء حذف المستخدم: {str(e)}'
        }, status=500)


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
# تم نقل جميع وظائف إدارة الأدوار إلى النظام الموحد في permissions_views.py
# للوصول إلى إدارة الأدوار، استخدم: /users/permissions/
