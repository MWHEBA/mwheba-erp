"""
URL configuration for mwheba_erp project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import RedirectView
from django.contrib.auth.decorators import login_required
from users.views import CustomLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    # روابط المصادقة
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # تطبيقات النظام
    path("", include("core.urls")),  # تم تفعيله لحل مشكلة NoReverseMatch
    path("users/", include("users.urls")),
    path("client/", include("client.urls")),
    path("supplier/", include("supplier.urls")),
    path("products/", include("product.urls")),
    path("printing-pricing/", include("printing_pricing.urls")),  # نظام التسعير الجديد والمحسن
    path("sales/", include("sale.urls")),
    path("purchases/", include("purchase.urls")),
    path("financial/", include("financial.urls")),
    path("hr/", include("hr.urls")),  # نظام إدارة الموارد البشرية
    path("utils/", include("utils.urls")),
    # مكتبات الجهات الخارجية
    path("select2/", include("django_select2.urls")),
    # مسارات تغيير كلمة المرور (AJAX من صفحة الملف الشخصي)
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="users/password_change.html"
        ),
        name="password_change",
    ),
    # مسارات إعادة تعيين كلمة المرور (نسيت كلمة المرور)
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="users/password_reset.html",
            email_template_name="users/password_reset_email.html",
            subject_template_name="users/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="users/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="users/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="users/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]

# إضافة مسارات الملفات الثابتة والوسائط في بيئة التطوير
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # إضافة شريط التصحيح للتطوير
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns += [
            path("__debug__/", include(debug_toolbar.urls)),
        ]
