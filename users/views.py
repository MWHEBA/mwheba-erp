from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .decorators import require_permission
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


from django.utils.translation import gettext_lazy as _
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache


# دالة تسجيل دخول مخصصة
@method_decorator(never_cache, name="dispatch")
class CustomLoginView(LoginView):
    """
    عرض مخصص لتسجيل الدخول يضمن أن form دائمًا موجود في السياق
    ويحترم الـ next parameter للـ redirect بعد اللوجن
    ويقوم بإعادة توجيه المستخدم تلقائيًا إذا كان مسجلاً دخوله بالفعل لمنع مشاكل الـ CSRF
    """

    template_name = "users/login.html"
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

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

    def form_valid(self, form):
        """
        لو المستخدم اختار 'تذكرني' → session تفضل 30 يوم
        لو ما اختارش → session تنتهي مع إغلاق المتصفح
        """
        remember_me = self.request.POST.get('remember_me')
        if not remember_me:
            self.request.session.set_expiry(0)
        else:
            self.request.session.set_expiry(60 * 60 * 24 * 30)  # 30 يوم
        return super().form_valid(form)

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
            messages.success(request, _("تم تحديث بياناتك الشخصية بنجاح."))
            return redirect('users:profile')
        else:
            messages.error(request, _("حدث خطأ في البيانات المدخلة."))
    else:
        form = UserProfileForm(instance=user)

    header_buttons = [
        {
            "toggle": "modal",
            "target": "#changePasswordModal",
            "icon": "fa-key",
            "text": _("تغيير كلمة المرور"),
            "class": "btn-outline-secondary",
        }
    ]
    if request.user.is_admin or request.user.is_superuser:
        header_buttons.append({
            "url": reverse("users:permissions_dashboard") + f"?tab=users&user_id={user.id}",
            "icon": "fa-user-shield",
            "text": _("إدارة الصلاحيات"),
            "class": "btn-outline-primary",
        })

    header_badges = [
        {
            "text": f"{_('عضو منذ')} {user.date_joined.year}",
            "icon": "fas fa-calendar-alt",
            "class": "bg-secondary",
        },
    ]

    breadcrumb_items = [
        {
            "title": _("الرئيسية"),
            "url": reverse("core:dashboard"),
            "icon": "fas fa-home",
        },
        {"title": _("الملف الشخصي"), "active": True},
    ]

    can_manage = user.is_superuser or (hasattr(user, 'can_manage_users') and user.can_manage_users()) or user.has_perm('users.view_user')

    context = {
        "user": user,
        "form": form,
        "title": _("الملف الشخصي"),
        "page_title": _("الملف الشخصي"),
        "page_subtitle": _("إدارة معلوماتك الشخصية وإعدادات حسابك"),
        "page_icon": "fas fa-user-circle",
        "header_buttons": header_buttons,
        "header_badges": header_badges,
        "breadcrumb_items": breadcrumb_items,
        "active_menu": "users" if can_manage else "profile",
    }

    return render(request, "users/profile.html", context)


@login_required
@require_permission('users.view_user')
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

    from users.services.user_management_service import UserManagementService
    from core.models import SystemModule

    is_hr_enabled = SystemModule.objects.filter(code='hr', is_enabled=True).exists()

    status = request.GET.get('status', 'active')
    is_archive_view = (status in ['inactive', 'archived'])

    # استعلام محسن مع select_related و prefetch_related لمنع N+1 queries واستبعاد الحسابات المخفية
    users_qs = User.objects.exclude(User.get_hidden_filter()).select_related('role')
    if is_hr_enabled:
        users_qs = users_qs.select_related('employee_profile')
    users = users_qs.prefetch_related('secondary_roles').order_by('-id')

    # الفلترة حسب الحالة (نشط / مؤرشف)
    if is_archive_view:
        users = users.filter(is_active=False)
    elif status == 'active':
        users = users.filter(is_active=True)
    # في حالة status == 'all' لا يتم تطبيق فلترة الحالة

    # البحث بالاسم أو اسم المستخدم أو البريد أو الهاتف أو بيانات الموظف
    q = request.GET.get('q', '').strip() or request.GET.get('search', '').strip()
    if q:
        search_filter = (
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )
        if is_hr_enabled:
            search_filter |= (
                Q(employee_profile__name__icontains=q) |
                Q(employee_profile__employee_number__icontains=q)
            )
        users = users.filter(search_filter)

    # الفلترة حسب الدور
    role_id = request.GET.get('role', '').strip()
    if role_id:
        users = users.filter(role_id=role_id)

    # التصدير المزدوج: تصدير المستخدمين حسب القائمة المعروضة
    if request.GET.get('export') == 'excel':
        from utils.export import export_queryset_to_excel
        export_filename = "archived_users.xlsx" if is_archive_view else "active_users.xlsx"
        export_fields = ["id", "username", "first_name", "last_name", "email", "phone"]
        export_headers = ["#", "اسم المستخدم", "الاسم الأول", "الاسم الأخير", "البريد الإلكتروني", "الهاتف"]
        annotations = {}
        if is_hr_enabled:
            export_fields.extend(["employee_name", "employee_number"])
            export_headers.extend(["الموظف", "رقم الموظف"])
            annotations["employee_name"] = lambda u: getattr(u, 'employee_profile').name if hasattr(u, 'employee_profile') and u.employee_profile else "-"
            annotations["employee_number"] = lambda u: getattr(u, 'employee_profile').employee_number if hasattr(u, 'employee_profile') and u.employee_profile else "-"
        export_fields.append("is_active")
        export_headers.append("نشط")

        return export_queryset_to_excel(
            users,
            filename=export_filename,
            fields=export_fields,
            headers=export_headers,
            annotations=annotations
        )

    # Whitelist الفرز الأمني
    allowed_sort_fields = {
        'id': 'id',
        'get_full_name': 'first_name',
        'username': 'username',
        'is_active': 'is_active',
        'last_login': 'last_login',
    }

    # الترقيم والفرز الـ SSR عبر المحرك المركزي
    from core.utils import paginate_queryset, render_paginated_response
    pagination_data = paginate_queryset(
        users,
        request,
        default_per_page=25,
        allowed_sort_fields=allowed_sort_fields
    )

    page_obj = pagination_data['page_obj']
    active_users_count = User.objects.exclude(User.get_hidden_filter()).filter(is_active=True).count()
    inactive_users_count = User.objects.exclude(User.get_hidden_filter()).filter(is_active=False).count()
    
    # إعداد headers للجدول الموحد مع دعم عامود الموظف الديناميكي
    headers = [
        {"key": "id", "label": "#", "sortable": True, "width": "6%" if is_hr_enabled else "8%", "class": "text-center"},
        {"key": "get_full_name", "label": "الاسم", "sortable": True, "width": "20%" if is_hr_enabled else "26%", "class": "text-center"},
    ]
    if is_hr_enabled:
        headers.append({
            "key": "employee_profile",
            "label": "الموظف",
            "sortable": False,
            "template": "users/partials/employee_column.html",
            "width": "20%",
            "class": "text-center"
        })
    headers.extend([
        {"key": "username", "label": "اسم المستخدم", "sortable": True, "width": "18%" if is_hr_enabled else "24%", "class": "text-center"},
        {"key": "role", "label": "الدور", "sortable": False, "width": "16%" if is_hr_enabled else "20%", "format": "role_badge", "class": "text-center"},
        {"key": "is_active", "label": "الحالة", "sortable": True, "format": "status", "width": "10%", "class": "text-center"},
        {
            "key": "last_login",
            "label": "آخر دخول",
            "sortable": True,
            "format": "datetime_12h",
            "width": "10%" if is_hr_enabled else "12%",
            "class": "text-center"
        }
    ])

    # إعداد action buttons حسب وضع العرض (نشط / أرشيف)
    action_buttons = []
    if request.user.can_manage_users():
        if is_archive_view:
            action_buttons = [
                {
                    "label": "تعديل",
                    "url": "users:user_edit",
                    "class": "btn-sm btn-outline-secondary edit-user-btn",
                    "icon": "fa-edit",
                },
                {
                    "label": "تفعيل",
                    "type": "button",
                    "class": "btn-sm btn-outline-success toggle-status-btn",
                    "icon": "fa-check-circle",
                    "title": "تفعيل واستعادة من الأرشيف",
                },
                {
                    "label": "حذف",
                    "type": "button",
                    "class": "btn-sm btn-outline-danger delete-user-btn",
                    "icon": "fa-trash",
                    "title": "حذف نهائي",
                },
            ]
        else:
            action_buttons = [
                {
                    "label": "تعديل",
                    "url": "users:user_edit",
                    "class": "btn-sm btn-outline-secondary edit-user-btn",
                    "icon": "fa-edit",
                },
                {
                    "label": "تعطيل",
                    "type": "button",
                    "class": "btn-sm btn-outline-danger toggle-status-btn",
                    "icon": "fa-user-slash",
                    "title": "تعطيل ونقل للأرشيف",
                },
            ]
            # زر Login As للـ superuser فقط في القائمة النشطة
            if request.user.is_superuser:
                action_buttons.insert(0, {
                    "label": "دخول كـ",
                    "type": "button",
                    "class": "btn-sm btn-outline-warning login-as-btn",
                    "icon": "fa-user-secret",
                })

    # أزرار الهيدر والبيانات الوصفية
    header_buttons = []
    if is_archive_view:
        page_title = "أرشيف المستخدمين"
        page_subtitle = f"عرض وإدارة المستخدمين المؤرشفين وغير النشطين ({page_obj.paginator.count} مستخدم مؤرشف)"
        page_icon = "fas fa-archive"
        header_buttons.append({
            "url": reverse("users:user_list"),
            "icon": "fa-users",
            "text": f"المستخدمون النشطون ({active_users_count})",
            "class": "btn-outline-primary",
        })
    else:
        page_title = "قائمة المستخدمين"
        page_subtitle = f"إدارة مستخدمي النظام ({page_obj.paginator.count} مستخدم نشط)"
        page_icon = "fas fa-users"
        header_buttons.append({
            "toggle": "modal",
            "target": "#createUserModal",
            "icon": "fa-plus",
            "text": "إضافة مستخدم",
            "class": "btn-primary",
        })
        header_buttons.append({
            "url": reverse("users:permissions_dashboard"),
            "icon": "fa-shield-alt",
            "text": "إدارة الأدوار",
            "class": "btn-outline-primary",
        })
        archive_btn_text = f"الأرشيف ({inactive_users_count})" if inactive_users_count > 0 else "الأرشيف"
        header_buttons.append({
            "url": reverse("users:user_list") + "?status=inactive",
            "icon": "fa-archive",
            "text": archive_btn_text,
            "class": "btn-outline-secondary",
        })

    # البريدكرمب
    breadcrumb_items = [
        {
            "title": "الرئيسية",
            "url": reverse("core:dashboard"),
            "icon": "fas fa-home",
        },
        {
            "title": "المستخدمين",
            "url": reverse("users:user_list") if is_archive_view else None,
            "active": not is_archive_view
        },
        *([{"title": "الأرشيف", "active": True}] if is_archive_view else []),
    ]

    all_employees = []
    if is_hr_enabled:
        from hr.models import Employee
        all_employees = Employee.objects.filter(status='active').select_related('department', 'user').order_by('name')

    context = {
        **pagination_data,
        "users": page_obj,
        "headers": headers,
        "action_buttons": action_buttons,
        "primary_key": "id",
        "show_export": True,
        "title": page_title,
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "page_icon": page_icon,
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "is_superuser": request.user.is_superuser,
        "is_archive_view": is_archive_view,
        "active_users_count": active_users_count,
        "inactive_users_count": inactive_users_count,
        "roles": Role.objects.filter(is_active=True).order_by('display_name'),
        "selected_role": role_id,
        "selected_status": status,
        "search_query": q,
        "all_employees": all_employees,
    }
    
    return render_paginated_response(
        request,
        "users/user_list.html",
        context,
        table_template_name="components/data_table.html"
    )


@login_required
def user_link_employee(request, user_id):
    """ربط مستخدم بموظف أو فك الربط (عبر المودال التفاعلي)"""
    if not request.user.can_manage_users():
        return JsonResponse({'success': False, 'message': 'ليس لديك صلاحية لإدارة ربط الموظفين.'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة الطلب غير صالحة.'}, status=405)
    
    target_user = get_object_or_404(User.objects.exclude(User.get_hidden_filter()), pk=user_id)
    employee_id = request.POST.get('employee_id', '').strip()
    
    from hr.models import Employee
    from django.db import transaction
    
    try:
        with transaction.atomic():
            # إذا تم إرسال معرّف فارغ -> فك الربط
            if not employee_id:
                if hasattr(target_user, 'employee_profile') and target_user.employee_profile:
                    old_emp = target_user.employee_profile
                    old_emp.user = None
                    old_emp.save(update_fields=['user'])
                    return JsonResponse({
                        'success': True,
                        'message': f'تم فك ربط المستخدم ({target_user.username}) من الموظف ({old_emp.name}) بنجاح.'
                    })
                return JsonResponse({'success': True, 'message': 'المستخدم غير مرتبط بأي موظف حالياً.'})
            
            # ربط بموظف محدد
            target_emp = get_object_or_404(Employee, pk=employee_id)
            
            # فك ربط الموظف القديم إذا كان هذا المستخدم مرتبطاً بآخر
            if hasattr(target_user, 'employee_profile') and target_user.employee_profile and target_user.employee_profile != target_emp:
                prev_emp = target_user.employee_profile
                prev_emp.user = None
                prev_emp.save(update_fields=['user'])
            
            # فك ربط أي مستخدم آخر كان مرتبطاً بهذا الموظف المستهدف
            if target_emp.user and target_emp.user != target_user:
                target_emp.user = None
                target_emp.save(update_fields=['user'])
            
            # تعيين الربط الجديد
            target_emp.user = target_user
            target_emp.save(update_fields=['user'])
            
            return JsonResponse({
                'success': True,
                'message': f'تم ربط المستخدم ({target_user.username}) بالموظف ({target_emp.name}) بنجاح.'
            })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'حدث خطأ أثناء تنفيذ الربط: {str(e)}'}, status=400)


@login_required
def user_create(request):
    """
    إنشاء مستخدم جديد (للمديرين فقط) - معالجة طلبات الإضافة عبر المودال (POST/AJAX)
    وإعادة التوجيه التلقائي للمودال في قائمة المستخدمين عند طلب الرابط عبر (GET) لمنع التكرار
    """
    if not request.user.can_manage_users():
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json':
            return JsonResponse({'success': False, 'message': 'ليس لديك صلاحية لإضافة مستخدمين'}, status=403)
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية لإضافة مستخدمين"},
        )
    
    # في حالة طلب الرابط عبر GET يتم التوجيه لقائمة المستخدمين مع فتح المودال تلقائياً
    if request.method == 'GET':
        return redirect(reverse('users:user_list') + '?action=create')
    
    if request.method == 'POST':
        from .forms import UserCreationForm
        form = UserCreationForm(request.POST)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json'
        
        if form.is_valid():
            try:
                user = form.save(commit=False)
                
                # تعيين الهاتف والعنوان
                phone = request.POST.get('phone', '').strip()
                if phone:
                    user.phone = phone
                address = request.POST.get('address', '').strip()
                if address:
                    user.address = address
                
                # تعيين حالة التفعيل
                if 'is_active' in request.POST:
                    user.is_active = (request.POST.get('is_active') in ['1', 'true', 'on', True])
                
                # تعيين الدور إذا تم تحديده
                role_id = request.POST.get('role') or request.POST.get('role_id')
                if role_id:
                    try:
                        role = Role.objects.get(id=role_id)
                        user.role = role
                    except Role.DoesNotExist:
                        pass
                
                user.save()
                
                success_msg = f'تم إنشاء المستخدم "{user.get_full_name() or user.username}" بنجاح'
                if is_ajax:
                    return JsonResponse({'success': True, 'message': success_msg, 'user_id': user.id})
                messages.success(request, success_msg)
                return redirect('users:user_list')
            except Exception as e:
                error_msg = f'حدث خطأ أثناء حفظ المستخدم: {str(e)}'
                if is_ajax:
                    return JsonResponse({'success': False, 'message': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('users:user_list')
        else:
            errors_list = []
            for field, errors in form.errors.items():
                for error in errors:
                    field_label = form.fields[field].label if field in form.fields else field
                    errors_list.append(f'{field_label}: {error}')
            error_msg = ' | '.join(errors_list) or 'يرجى مراجعة البيانات المدخلة والتحقق من صحتها.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg, 'errors': form.errors}, status=400)
            for err in errors_list:
                messages.error(request, err)
            return redirect('users:user_list')


@login_required
def user_edit(request, user_id):
    """
    تعديل بيانات مستخدم (للمديرين فقط)
    """
    from django.http import JsonResponse
    from users.services.user_management_service import UserManagementService

    if not request.user.can_manage_users():
        return JsonResponse({
            'success': False,
            'error': 'permission_denied',
            'message': 'ليس لديك صلاحية لتعديل المستخدمين'
        }, status=403)

    user = get_object_or_404(User.objects.exclude(User.get_hidden_filter()), id=user_id)

    if request.method == 'POST':
        try:
            target_is_active = request.POST.get('is_active') == 'on'

            # إذا تغيرت حالة النشاط، نمررها عبر السيرفيس المركزية لضمان الأمان والرقابة
            if target_is_active != user.is_active:
                toggle_res = UserManagementService.toggle_user_status(
                    user,
                    current_user=request.user,
                    target_active=target_is_active
                )
                if not toggle_res.get('success'):
                    return JsonResponse(toggle_res, status=400)

            from utils.validators import sanitize_email
            user.first_name = request.POST.get('first_name', user.first_name).strip() if request.POST.get('first_name') else user.first_name
            user.last_name = request.POST.get('last_name', user.last_name).strip() if request.POST.get('last_name') else user.last_name
            raw_email = request.POST.get('email')
            if raw_email:
                user.email = sanitize_email(raw_email)
            user.phone = request.POST.get('phone', user.phone)
            user.address = request.POST.get('address', user.address)

            role_id = request.POST.get('role_id')
            if role_id:
                user.role = Role.objects.filter(id=role_id).first()
            elif role_id == '':
                user.role = None

            # تعديل كلمة المرور للسوبر أدمن فقط
            new_password = request.POST.get('new_password', '').strip()
            if new_password:
                if not request.user.is_superuser:
                    return JsonResponse({
                        'success': False,
                        'message': 'ليس لديك صلاحية لتعديل كلمة المرور (مخصصة لمدير النظام الرئيسي فقط).'
                    }, status=403)
                
                if len(new_password) < 6:
                    return JsonResponse({
                        'success': False,
                        'message': 'كلمة المرور الجديدة يجب ألا تقل عن 6 أحرف.'
                    }, status=400)
                
                user.set_password(new_password)
                
                # إنهاء جلسات المستخدم الأخرى أو الحفاظ على جلسة السوبر أدمن إذا كان يعدل حسابه الخاص
                if request.user.id == user.id:
                    from django.contrib.auth import update_session_auth_hash
                    update_session_auth_hash(request, user)
                else:
                    UserManagementService.invalidate_user_sessions(user.id)
                
                # توثيق تغيير كلمة المرور في ActivityLog
                try:
                    from users.models import ActivityLog
                    ActivityLog.objects.create(
                        user=request.user,
                        action="تغيير كلمة مرور المستخدم",
                        model_name='User',
                        object_id=user.id,
                        extra_data={
                            'target_username': user.username,
                            'target_user_id': user.id,
                            'changed_by': request.user.username,
                            'details': f"قام مدير النظام {request.user.username} بتعيين كلمة مرور جديدة للمستخدم {user.username}"
                        }
                    )
                except Exception as log_err:
                    import logging
                    logging.getLogger('users.views').warning(f"Could not log password change: {log_err}")

            user.save()

            return JsonResponse({
                'success': True,
                'message': f'تم تحديث بيانات المستخدم "{user.get_full_name() or user.username}" بنجاح'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            })

    # GET request - إرجاع بيانات المستخدم مع قائمة الأدوار (تشمل دور المستخدم حتى لو كان الدور معطلاً)
    roles_qs = Role.objects.filter(Q(is_active=True) | Q(id=user.role_id) if user.role_id else Q(is_active=True)).distinct()
    roles = list(roles_qs.values('id', 'display_name'))
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
            'is_active': user.is_active,
            'role_id': user.role.id if user.role else None,
        },
        'roles': roles,
    })


@login_required
def user_check_delete(request, user_id):
    """
    فحص استباقي لإمكانية حذف المستخدم وبيان العمليات المرتبطة
    """
    from django.http import JsonResponse
    from users.services.user_management_service import UserManagementService

    if not request.user.can_manage_users():
        return JsonResponse({
            'success': False,
            'message': 'ليس لديك صلاحية لحذف المستخدمين'
        }, status=403)

    user = get_object_or_404(User.objects.exclude(User.get_hidden_filter()), id=user_id)
    can_del, summary, msg = UserManagementService.can_delete_user(user, current_user=request.user)

    return JsonResponse({
        'success': True,
        'can_delete': can_del,
        'user_name': user.get_full_name() or user.username,
        'username': user.username,
        'is_active': user.is_active,
        'operations_summary': summary,
        'message': msg
    })


@login_required
def user_toggle_status(request, user_id):
    """
    تبديل حالة المستخدم (تعطيل وأرشفة / تفعيل واستعادة) عبر AJAX
    """
    from django.http import JsonResponse
    from users.services.user_management_service import UserManagementService

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة الطلب غير مسموحة'}, status=405)

    if not request.user.can_manage_users():
        return JsonResponse({
            'success': False,
            'message': 'ليس لديك صلاحية لتعديل حالة المستخدمين'
        }, status=403)

    user = get_object_or_404(User.objects.exclude(User.get_hidden_filter()), id=user_id)
    result = UserManagementService.toggle_user_status(user, current_user=request.user)

    status_code = 200 if result.get('success') else 400
    return JsonResponse(result, status=status_code)


@login_required
def user_delete(request, user_id):
    """
    حذف مستخدم عبر AJAX بعد التحقق من شروط الحذف الصارمة
    """
    from django.http import JsonResponse
    from users.services.user_management_service import UserManagementService

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)
    
    if not request.user.can_manage_users():
        return JsonResponse({
            'success': False, 
            'message': 'ليس لديك صلاحية لحذف المستخدمين'
        }, status=403)
    
    user = get_object_or_404(User.objects.exclude(User.get_hidden_filter()), id=user_id)
    result = UserManagementService.delete_user(user, current_user=request.user)

    status_code = 200 if result.get('success') else 400
    return JsonResponse(result, status=status_code)


@login_required
def login_as_user(request, user_id):
    """
    تسجيل الدخول كمستخدم آخر (للـ superuser فقط)
    مع توثيق رقابي كامل ومسح كاش الصلاحيات
    """
    if not request.user.is_superuser:
        return JsonResponse({
            'success': False,
            'message': 'هذه الميزة متاحة للمدير الرئيسي فقط'
        }, status=403)

    # منع الانتحال المتداخل
    if request.session.get('is_impersonating') or request.session.get('impersonated_by'):
        return JsonResponse({
            'success': False,
            'message': 'يجب إنهاء جلسة الانتحال الحالية أولاً قبل انتحال مستخدم آخر'
        }, status=400)

    target_user = get_object_or_404(User.objects.exclude(User.get_hidden_filter()), id=user_id)

    # حظر تسجيل الدخول بحساب معطل ومؤرشف
    if not target_user.is_active:
        return JsonResponse({
            'success': False,
            'message': 'لا يمكن تسجيل الدخول بحساب مستخدم معطل ومؤرشف'
        }, status=400)

    # منع الدخول كنفسك
    if target_user == request.user:
        return JsonResponse({
            'success': False,
            'message': 'أنت بالفعل مسجل الدخول بهذا الحساب'
        }, status=400)

    # حظر انتحال مدير رئيسي آخر
    if target_user.is_superuser:

        return JsonResponse({
            'success': False,
            'message': 'لا يمكن انتحال حساب مدير رئيسي آخر لأسباب أمنية'
        }, status=403)

    from django.contrib.auth import login as auth_login
    from users.services.permission_cache import PermissionCacheService
    original_user = request.user
    original_user_id = original_user.id

    # تسجيل حركة بدء الانتحال في سجل النشاطات (Non-Repudiation Audit)
    try:
        ActivityLog.objects.create(
            user=original_user,
            action='IMPERSONATION_START',
            model_name='User',
            object_id=target_user.id,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            extra_data={
                'impersonator_id': original_user_id,
                'impersonator_username': original_user.username,
                'target_user_id': target_user.id,
                'target_username': target_user.username,
                'details': f"بدأ المشرف {original_user.username} جلسة انتحال هوية للمستخدم {target_user.username}"
            }
        )
    except Exception:
        pass

    # تسجيل الدخول كالمستخدم المستهدف
    target_user.backend = 'users.backends.EmailOrUsernameModelBackend'
    auth_login(request, target_user)

    # تنظيف كاش الصلاحيات فوراً لمنع تسرب الصلاحيات بين الحسابين
    PermissionCacheService.invalidate_user_cache(original_user_id)
    PermissionCacheService.invalidate_user_cache(target_user.id)
    if hasattr(request, '_perm_cache'):
        delattr(request, '_perm_cache')

    # حفظ معرف المستخدم الأصلي للرجوع لاحقاً
    request.session['original_user_id'] = original_user_id
    request.session['impersonated_by'] = original_user_id
    request.session['is_impersonating'] = True

    return JsonResponse({
        'success': True,
        'message': f'تم تسجيل الدخول كـ {target_user.get_full_name() or target_user.username}',
        'redirect_url': reverse('core:dashboard')
    })


@login_required
def stop_impersonation(request):
    """
    إيقاف انتحال الهوية والرجوع للمستخدم الأصلي مع التوثيق ومسح الكاش
    """
    original_user_id = request.session.get('impersonated_by') or request.session.get('original_user_id')
    if not original_user_id:
        return redirect('core:dashboard')

    current_target_user = request.user

    try:
        original_user = User.objects.get(id=original_user_id)
        from django.contrib.auth import login as auth_login
        from users.services.permission_cache import PermissionCacheService

        # توثيق إنهاء جلسة الانتحال
        try:
            ActivityLog.objects.create(
                user=original_user,
                action='IMPERSONATION_STOP',
                model_name='User',
                object_id=current_target_user.id if current_target_user.is_authenticated else None,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                extra_data={
                    'impersonator_id': original_user.id,
                    'impersonator_username': original_user.username,
                    'target_user_id': current_target_user.id if current_target_user.is_authenticated else None,
                    'target_username': current_target_user.username if current_target_user.is_authenticated else '',
                    'details': f"أنهى المشرف {original_user.username} جلسة انتحال الهوية"
                }
            )
        except Exception:
            pass

        original_user.backend = 'users.backends.EmailOrUsernameModelBackend'
        auth_login(request, original_user)

        # تنظيف كاش الصلاحيات
        PermissionCacheService.invalidate_user_cache(original_user.id)
        if current_target_user.is_authenticated:
            PermissionCacheService.invalidate_user_cache(current_target_user.id)
        if hasattr(request, '_perm_cache'):
            delattr(request, '_perm_cache')

        # تنظيف الـ session
        request.session.pop('original_user_id', None)
        request.session.pop('impersonated_by', None)
        request.session.pop('is_impersonating', None)

        messages.success(request, f'تم الرجوع لحسابك الأصلي: {original_user.get_full_name() or original_user.username}')
    except User.DoesNotExist:
        request.session.pop('original_user_id', None)
        request.session.pop('impersonated_by', None)
        request.session.pop('is_impersonating', None)

    return redirect('core:dashboard')


@login_required
def activity_log(request):
    """
    عرض سجل النشاطات مع إمكانية الفلترة
    """
    from django.core.paginator import Paginator
    import datetime

    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # جلب جميع النشاطات واستبعاد نشاطات الحسابات المخفية
    activities = ActivityLog.objects.exclude(
        Q(user__username__icontains='mwheba') | Q(user__email__icontains='info@mwheba.com')
    ).select_related('user').all()
    
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
        try:
            dt_from = datetime.datetime.strptime(date_from, '%Y-%m-%d')
            activities = activities.filter(timestamp__gte=dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.datetime.strptime(date_to, '%Y-%m-%d') + datetime.timedelta(days=1)
            activities = activities.filter(timestamp__lt=dt_to)
        except ValueError:
            pass
    
    # ترتيب
    activities = activities.order_by("-timestamp")
    
    # ترقيم الصفحات SSR
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(activities, request, default_per_page=50)
    page_obj = pagination_context["page_obj"]
    
    # جلب قائمة المستخدمين للفلترة مع استبعاد الحسابات المخفية
    users = User.objects.exclude(User.get_hidden_filter()).filter(is_active=True).order_by('username')

    context = {
        "page_obj": page_obj,
        "activities": page_obj.object_list,
        **pagination_context,
        "users": users,
        "selected_user": user_filter or '',
        "selected_action": action_filter or '',
        "date_from": date_from or '',
        "date_to": date_to or '',
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
