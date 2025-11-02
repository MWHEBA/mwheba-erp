from django.urls import path
from . import views
from . import api

app_name = "users"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<int:user_id>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:user_id>/delete/", views.user_delete, name="user_delete"),
    path("activity-log/", views.activity_log, name="activity_log"),
    path("update-profile-image/", views.update_profile_image, name="update_profile_image"),
    path("change-password-ajax/", views.change_password_ajax, name="change_password_ajax"),
    
    # إدارة الأدوار والصلاحيات
    path("roles/", views.role_list, name="role_list"),
    path("roles/create/", views.role_create, name="role_create"),
    path("roles/<int:role_id>/edit/", views.role_edit, name="role_edit"),
    path("roles/<int:role_id>/delete/", views.role_delete, name="role_delete"),
    path("users/<int:user_id>/permissions/", views.user_permissions, name="user_permissions"),
    
    # مسارات API
    path("api/login/", api.LoginAPIView.as_view(), name="api_login"),
    path("api/register/", api.RegisterAPIView.as_view(), name="api_register"),
    path("api/profile/", api.UserProfileAPIView.as_view(), name="api_profile"),
]
