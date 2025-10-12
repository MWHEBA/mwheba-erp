from django.urls import path
from . import views
from . import api

app_name = 'users'

urlpatterns = [
    path('profile/', views.profile, name='profile'),
    path('users/', views.user_list, name='user_list'),
    path('activity-log/', views.activity_log, name='activity_log'),
    
    # مسارات API
    path('api/login/', api.LoginAPIView.as_view(), name='api_login'),
    path('api/register/', api.RegisterAPIView.as_view(), name='api_register'),
    path('api/profile/', api.UserProfileAPIView.as_view(), name='api_profile'),
] 