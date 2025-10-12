from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import User, ActivityLog
from django.urls import reverse
from django.contrib import messages
from .forms import UserProfileForm
from django.contrib.auth.views import LoginView


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

    # إنشاء نموذج لتعديل بيانات المستخدم
    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث بياناتك الشخصية بنجاح.")
    else:
        form = UserProfileForm(instance=user)

    context = {
        "user": user,
        "form": form,
        "title": "الملف الشخصي",
        "page_title": "الملف الشخصي",
        "page_icon": "fas fa-user-circle",
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
        {"key": "full_name", "label": "الاسم", "sortable": True},
        {"key": "username", "label": "اسم المستخدم", "sortable": True},
        {"key": "email", "label": "البريد الإلكتروني", "sortable": True},
        {"key": "phone", "label": "الهاتف", "sortable": False},
        {
            "key": "user_type",
            "label": "نوع المستخدم",
            "sortable": True,
            "format": "badge",
        },
        {"key": "is_active", "label": "الحالة", "sortable": True, "format": "status"},
        {
            "key": "last_login",
            "label": "آخر دخول",
            "sortable": True,
            "format": "datetime",
        },
    ]

    # إعداد action buttons
    action_buttons = [
        {
            "label": "عرض",
            "url": "/users/{id}/",
            "class": "btn-outline-primary",
            "icon": "fas fa-eye",
        },
        {
            "label": "تعديل",
            "url": "/users/{id}/edit/",
            "class": "btn-outline-secondary",
            "icon": "fas fa-edit",
        },
        {
            "label": "حذف",
            "url": "/users/{id}/delete/",
            "class": "btn-outline-danger",
            "icon": "fas fa-trash",
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
        "page_icon": "fas fa-users",
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
def activity_log(request):
    """
    عرض سجل النشاطات
    """
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    activities = ActivityLog.objects.all().order_by("-timestamp")[:100]  # آخر 100 نشاط

    context = {
        "activities": activities,
        "page_title": "سجل النشاطات",
        "page_icon": "fas fa-history",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المستخدمين", "url": "#", "icon": "fas fa-users"},
            {"title": "سجل النشاطات", "active": True},
        ],
    }

    return render(request, "users/activity_log.html", context)
