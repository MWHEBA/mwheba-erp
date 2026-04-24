from django.urls import path
from django.shortcuts import redirect
from users import views
from users import api
from users.permissions_views import (
    permissions_dashboard, role_quick_create, role_quick_edit, 
    role_delete, user_assign_role, user_permissions_detail, 
    get_available_permissions, bulk_assign_roles, compare_roles, export_roles,
    get_monitoring_data, user_update_custom_permissions
)

app_name = "users"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("", views.user_list, name="user_list"),  # تغيير من "users/" لـ ""
    path("create/", views.user_create, name="user_create"),  # تغيير من "users/create/" لـ "create/"
    path("<int:user_id>/edit/", views.user_edit, name="user_edit"),  # تغيير من "users/<int:user_id>/edit/" لـ "<int:user_id>/edit/"
    path("<int:user_id>/delete/", views.user_delete, name="user_delete"),  # تغيير من "users/<int:user_id>/delete/" لـ "<int:user_id>/delete/"
    path("activity-log/", views.activity_log, name="activity_log"),
    path("update-profile-image/", views.update_profile_image, name="update_profile_image"),
    path("change-password-ajax/", views.change_password_ajax, name="change_password_ajax"),
    
    # نظام الصلاحيات الموحد (يحل محل النظام القديم)
    path("permissions/", permissions_dashboard, name="permissions_dashboard"),
    path("permissions/roles/create/", role_quick_create, name="role_quick_create"),
    path("permissions/roles/<int:role_id>/edit/", role_quick_edit, name="role_quick_edit"),
    path("permissions/roles/<int:role_id>/delete/", role_delete, name="role_quick_delete"),
    path("permissions/users/<int:user_id>/assign-role/", user_assign_role, name="user_assign_role"),
    path("permissions/users/<int:user_id>/permissions/", user_permissions_detail, name="user_permissions_detail"),
    path("permissions/users/<int:user_id>/update-custom-permissions/", user_update_custom_permissions, name="user_update_custom_permissions"),
    path("permissions/available-permissions/", get_available_permissions, name="get_available_permissions"),
    
    # العمليات الجماعية والمتقدمة
    path("permissions/bulk-assign-roles/", bulk_assign_roles, name="bulk_assign_roles"),
    path("permissions/compare-roles/", compare_roles, name="compare_roles"),
    path("permissions/export-roles/", export_roles, name="export_roles"),
    path("permissions/monitoring-data/", get_monitoring_data, name="get_monitoring_data"),
    
    # إعادة توجيه المسارات القديمة للنظام الجديد
    path("roles/", lambda request: redirect('users:permissions_dashboard', permanent=True)),
    path("users/<int:user_id>/permissions/", lambda request, user_id: redirect('users:user_permissions_detail', user_id=user_id, permanent=True)),
    
    # مسارات API
    path("api/login/", api.LoginAPIView.as_view(), name="api_login"),
    path("api/register/", api.RegisterAPIView.as_view(), name="api_register"),
    path("api/profile/", api.UserProfileAPIView.as_view(), name="api_profile"),
]
