# -*- coding: utf-8 -*-
"""
Unified Permissions Management Views

This module provides comprehensive permission management functionality
through a unified dashboard interface.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.db.models import Q, Count
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
import json

from .models import User, Role
from .forms import RoleForm, UserRoleForm
from .services.permission_service import PermissionService
from .services.monitoring import PermissionMonitoringService
from .decorators import require_admin, secure_admin_operation


def _get_arabic_permission_name(permission):
    """Convert Django permission names to Arabic equivalents."""
    codename = permission.codename.lower()
    model_name = permission.content_type.model
    
    # Model name translations
    model_translations = {
        'customer': 'العملاء',
        'client': 'العملاء',
        'employee': 'الموظفين',
        'user': 'المستخدمين',
        'role': 'الأدوار',
        'product': 'المنتجات',
        'sale': 'المبيعات',
        'purchase': 'المشتريات',
        'supplier': 'الموردين',
        'transaction': 'المعاملات المالية',
        'invoice': 'الفواتير',
        'payment': 'المدفوعات',
        'fee': 'الرسوم',
        'customer': 'العملاء',
        'customerpayment': 'دفعات العملاء',
        'account': 'الحسابات',
        'audittrail': 'سجلات التدقيق',
        'balanceauditlog': 'سجلات مراجعة الرصيد',
        'report': 'التقارير',
        'dashboard': 'لوحة التحكم',
        'dashboardstat': 'إحصائيات لوحة التحكم',
        'dataprotectionaudit': 'سجلات حماية البيانات',
        'auditlog': 'سجلات التدقيق',
        'qrauditlog': 'سجلات تدقيق QR',
        'invoiceauditlog': 'سجلات تدقيق الفواتير',
        'validationauditlog': 'سجلات تدقيق التحقق',
        'settlementauditlog': 'سجلات تدقيق التسوية'
    }
    
    # Get model translation
    model_arabic = model_translations.get(model_name, model_name)
    
    # Action translations with better handling
    if codename.startswith('add_'):
        return f"إضافة {model_arabic}"
    elif codename.startswith('change_'):
        return f"تعديل {model_arabic}"
    elif codename.startswith('delete_'):
        return f"حذف {model_arabic}"
    elif codename.startswith('view_'):
        return f"عرض {model_arabic}"
    elif codename.startswith('can_manage_'):
        action_part = codename.replace('can_manage_', '')
        if action_part == 'contracts':
            return 'إدارة العقود'
        elif action_part == 'employees':
            return 'إدارة الموظفين'
        elif action_part == 'buses':
            return 'إدارة وسائل النقل'
        elif action_part == 'routes':
            return 'إدارة المسارات'
        elif action_part == 'enrollments':
            return 'إدارة التسجيلات'
        elif action_part == 'emergencies':
            return 'إدارة حالات الطوارئ'
        else:
            return f"إدارة {model_arabic}"
    elif codename.startswith('can_export_'):
        action_part = codename.replace('can_export_', '')
        if action_part == 'audit_logs':
            return 'تصدير سجلات التدقيق'
        elif action_part == 'data':
            return 'تصدير البيانات'
        else:
            return f"تصدير {model_arabic}"
    elif codename.startswith('can_view_'):
        action_part = codename.replace('can_view_', '')
        if action_part == 'audit_logs':
            return 'عرض سجلات التدقيق'
        else:
            return f"عرض {model_arabic}"
    elif codename.startswith('can_process_'):
        action_part = codename.replace('can_process_', '')
        if action_part == 'payroll':
            return 'معالجة الرواتب'
        else:
            return f"معالجة {model_arabic}"
    
    # Special cases for specific permissions
    special_cases = {
        'dashboard': 'لوحة التحكم',
        'audit': 'مراجعة السجلات',
        'monitor': 'مراقبة النظام',
        'export_data': 'تصدير البيانات',
        'view_reports': 'عرض التقارير',
        'manage_settings': 'إدارة الإعدادات'
    }
    
    if codename in special_cases:
        return special_cases[codename]
    
    # If no specific translation found, return the Arabic model name
    return model_arabic


@login_required
def permissions_dashboard(request):
    """
    Unified permissions management dashboard with tabs.
    """
    try:
        # Get current tab from URL parameter
        current_tab = request.GET.get('tab', 'overview')
        
        # Check user permissions for admin features
        user_can_manage_roles = request.user.is_superuser or request.user.is_admin
        user_can_view_permissions = (
            user_can_manage_roles or 
            request.user.can_manage_users() or
            request.user.is_reception or
            request.user.user_type == 'reception'
        )
        
        # Base context for all tabs
        context = {
            'current_tab': current_tab,
            'title': 'إدارة الصلاحيات',
            'page_title': 'إدارة الصلاحيات والأدوار',
            'page_subtitle': 'نظام موحد لإدارة صلاحيات المستخدمين والأدوار',
            'page_icon': 'fas fa-shield-alt',
            'breadcrumb_items': [
                {
                    'title': 'الرئيسية',
                    'url': reverse('core:dashboard'),
                    'icon': 'fas fa-home'
                },
                {
                    'title': 'المستخدمين',
                    'url': reverse('users:user_list'),
                    'icon': 'fas fa-users'
                },
                {
                    'title': 'إدارة الصلاحيات',
                    'active': True
                }
            ],
            'header_buttons': [
                {
                    'url': reverse('users:role_quick_create'),
                    'icon': 'fa-plus',
                    'text': 'إضافة دور جديد',
                    'class': 'btn-primary'
                },
                {
                    'url': reverse('users:user_create'),
                    'icon': 'fa-user-plus',
                    'text': 'إضافة مستخدم',
                    'class': 'btn-outline-primary'
                }
            ] if user_can_manage_roles else [],
            'user_can_manage_roles': user_can_manage_roles,
            'user_can_view_permissions': user_can_view_permissions,
            'user_permissions_info': {
                'is_admin': request.user.is_admin,
                'is_superuser': request.user.is_superuser,
                'user_type': getattr(request.user, 'user_type', 'unknown'),
                'can_manage_users': request.user.can_manage_users() if hasattr(request.user, 'can_manage_users') else False,
            }
        }
        
        # Load data for ALL tabs to avoid refresh issues
        # This ensures data is always available regardless of which tab is active
        try:
            context.update(_get_roles_tab_data(request))
        except Exception as e:
            context.update({'roles': [], 'search': '', 'total_roles': 0, 'roles_error': str(e)})
        
        try:
            context.update(_get_users_tab_data(request))
        except Exception as e:
            context.update({'users': [], 'available_roles': [], 'total_users': 0, 'users_error': str(e)})
        
        try:
            context.update(_get_monitoring_tab_data(request))
        except Exception as e:
            context.update({'recent_changes': [], 'days_filter': 7, 'total_changes': 0, 'monitoring_error': str(e)})
        
        # Add overview data
        try:
            context.update(_get_overview_tab_data(request))
        except Exception as e:
            context.update({'overview_error': str(e)})
        
        return render(request, 'users/permissions/dashboard.html', context)
        
    except Exception as e:
        # Debug: show the error
        from django.http import HttpResponse
        import traceback
        return HttpResponse(f"Error: {e}<br><br>{traceback.format_exc()}")


def _get_overview_tab_data(request):
    """Get data for overview tab."""
    try:
        # Basic statistics
        total_users = User.objects.filter(is_active=True).count()
        total_roles = Role.objects.filter(is_active=True).count()
        users_with_roles = User.objects.filter(role__isnull=False, is_active=True).count()
        users_without_roles = total_users - users_with_roles
        
        # Recent activity (last 7 days)
        from django.utils import timezone
        from datetime import timedelta
        week_ago = timezone.now() - timedelta(days=7)
        
        # Get recent users (created in last 7 days)
        recent_users = User.objects.filter(
            date_joined__gte=week_ago,
            is_active=True
        ).select_related('role').order_by('-date_joined')[:5]
        
        # Get active roles with user counts - using different field name
        active_roles = Role.objects.filter(is_active=True).annotate(
            user_count=Count('users', filter=Q(users__is_active=True))
        ).order_by('-user_count')[:5]
        
        return {
            'overview_stats': {
                'total_users': total_users,
                'total_roles': total_roles,
                'users_with_roles': users_with_roles,
                'users_without_roles': users_without_roles,
                'roles_utilization': round((users_with_roles / total_users * 100) if total_users > 0 else 0, 1)
            },
            'recent_users': recent_users,
            'active_roles': active_roles,
        }
        
    except Exception as e:
        return {
            'overview_stats': {
                'total_users': 0,
                'total_roles': 0,
                'users_with_roles': 0,
                'users_without_roles': 0,
                'roles_utilization': 0
            },
            'recent_users': [],
            'active_roles': [],
            'overview_error': str(e)
        }


def _get_roles_tab_data(request):
    """Get data for roles management tab."""
    try:
        # Get all roles with user counts (using different name to avoid conflict with property)
        roles = Role.objects.annotate(
            user_count=Count('users', filter=Q(users__is_active=True))
        ).order_by('-is_system_role', 'display_name')
        
        # Search functionality
        search = request.GET.get('search', '')
        if search:
            roles = roles.filter(
                Q(name__icontains=search) |
                Q(display_name__icontains=search) |
                Q(description__icontains=search)
            )
        
        # Pagination
        paginator = Paginator(roles, 10)
        page_number = request.GET.get('page')
        roles_page = paginator.get_page(page_number)
        
        return {
            'roles': roles_page,
            'search': search,
            'total_roles': roles.count(),
        }
        
    except Exception as e:
        # Debug: return empty data with error info
        return {
            'roles': [],
            'search': '',
            'total_roles': 0,
            'error': str(e)
        }


def _get_users_tab_data(request):
    """Get data for users management tab with custom permissions statistics."""
    # Import the services here to avoid circular imports
    from .services.user_management_service import UserManagementService
    
    # Search functionality
    search = request.GET.get('search', '')
    role_filter = request.GET.get('role')
    has_permissions = request.GET.get('has_permissions')
    
    # Convert has_permissions to boolean if provided
    has_permissions_bool = None
    if has_permissions == 'true':
        has_permissions_bool = True
    elif has_permissions == 'false':
        has_permissions_bool = False
    
    # Create service instance and get users with custom permission statistics
    service = UserManagementService()
    users_data = service.perform_operation(
        'search_users',
        query=search,
        role_id=int(role_filter) if role_filter and role_filter != 'no_role' else None,
        has_permissions=has_permissions_bool
    )
    
    # Handle special case for users without roles
    if role_filter == 'no_role':
        users_data = [u for u in users_data if u['user'].role is None]
    
    # Pagination
    paginator = Paginator(users_data, 15)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)
    
    # Get roles for filter dropdown
    available_roles = Role.objects.filter(is_active=True).order_by('display_name')
    
    return {
        'users': users_page,
        'search': search,
        'role_filter': role_filter,
        'has_permissions_filter': has_permissions,
        'available_roles': available_roles,
        'total_users': len(users_data),
    }


def _get_monitoring_tab_data(request):
    """Get data for enhanced monitoring tab."""
    try:
        # Get days filter
        days = int(request.GET.get('days', 7))
        
        # Try to get monitoring data from service, fallback to basic data
        try:
            monitoring_data = PermissionMonitoringService.get_monitoring_dashboard_data()
        except Exception:
            monitoring_data = {
                'system_health': {
                    'permissions_system': 'healthy',
                    'governance_system': 'healthy',
                    'audit_logging': 'healthy'
                },
                'security_alerts': [],
                'usage_statistics': {},
                'cache_status': {}
            }
        
        # Try to get recent changes, fallback to empty list
        try:
            recent_changes = PermissionService.get_recent_permission_changes(days=days)
        except Exception:
            recent_changes = []
        
        # Pagination for changes
        paginator = Paginator(recent_changes, 20)
        page_number = request.GET.get('page')
        changes_page = paginator.get_page(page_number)
        
        return {
            'monitoring_data': monitoring_data,
            'recent_changes': changes_page,
            'days_filter': days,
            'total_changes': len(recent_changes),
            'system_health': monitoring_data.get('system_health', {}),
            'security_alerts': monitoring_data.get('security_alerts', []),
            'security_events': monitoring_data.get('security_alerts', [])[:5],  # First 5 for display
            'usage_statistics': monitoring_data.get('usage_statistics', {}),
            'cache_status': monitoring_data.get('cache_status', {})
        }
        
    except Exception as e:
        # Fallback to basic data if everything fails
        return {
            'monitoring_data': {},
            'recent_changes': [],
            'days_filter': 7,
            'total_changes': 0,
            'system_health': {},
            'security_alerts': [],
            'security_events': [],
            'usage_statistics': {},
            'cache_status': {},
            'error': str(e)
        }


@login_required
@secure_admin_operation('role_quick_create')
def role_quick_create(request):
    """AJAX endpoint for quick role creation."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            name = data.get('name', '').strip()
            display_name = data.get('display_name', '').strip()
            description = data.get('description', '').strip()
            permission_ids = data.get('permissions', [])
            
            if not name or not display_name:
                return JsonResponse({
                    'success': False,
                    'message': 'اسم الدور والاسم المعروض مطلوبان'
                }, status=400)
            
            # Check if role exists
            if Role.objects.filter(name=name).exists():
                return JsonResponse({
                    'success': False,
                    'message': f'دور بالاسم "{name}" موجود بالفعل'
                }, status=400)
            
            # Get permissions
            permissions = Permission.objects.filter(id__in=permission_ids)
            
            # Create role using service
            role = PermissionService.create_role(
                name=name,
                display_name=display_name,
                description=description,
                permissions=list(permissions),
                created_by=request.user
            )
            
            return JsonResponse({
                'success': True,
                'message': f'تم إنشاء الدور "{role.display_name}" بنجاح',
                'role': {
                    'id': role.id,
                    'name': role.name,
                    'display_name': role.display_name,
                    'permissions_count': role.permissions.count()
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
@require_admin()
def role_quick_edit(request, role_id):
    """AJAX endpoint for quick role editing."""
    role = get_object_or_404(Role, id=role_id)
    
    if request.method == 'GET':
        # Return role data for editing
        return JsonResponse({
            'success': True,
            'role': {
                'id': role.id,
                'name': role.name,
                'display_name': role.display_name,
                'description': role.description,
                'is_active': role.is_active,
                'permissions': list(role.permissions.values_list('id', flat=True))
            }
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Update basic fields
            role.display_name = data.get('display_name', role.display_name)
            role.description = data.get('description', role.description)
            role.is_active = data.get('is_active', role.is_active)
            role.save()
            
            # Update permissions if provided
            permission_ids = data.get('permissions')
            if permission_ids is not None:
                permissions = Permission.objects.filter(id__in=permission_ids)
                PermissionService.update_role_permissions(
                    role=role,
                    permissions=list(permissions),
                    updated_by=request.user
                )
            
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث الدور "{role.display_name}" بنجاح'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
@require_admin()
def role_delete(request, role_id):
    """AJAX endpoint for role deletion."""
    if request.method == 'POST':
        # Get role with annotated user count to avoid N+1 query
        role = get_object_or_404(
            Role.objects.annotate(
                active_users_count=Count('users', filter=Q(users__is_active=True))
            ),
            id=role_id
        )
        
        # Check if it's a system role
        if role.is_system_role:
            return JsonResponse({
                'success': False,
                'message': 'لا يمكن حذف أدوار النظام الأساسية'
            }, status=400)
        
        # Check if role has users using annotated count
        if role.active_users_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'لا يمكن حذف الدور لأنه مرتبط بـ {role.active_users_count} مستخدم نشط'
            }, status=400)
        
        try:
            role_name = role.display_name
            role.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'تم حذف الدور "{role_name}" بنجاح'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
def user_assign_role(request, user_id):
    """AJAX endpoint for assigning role to user."""
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        
        try:
            data = json.loads(request.body)
            role_id = data.get('role_id')
            
            if role_id:
                role = get_object_or_404(Role, id=role_id)
                
                # Direct assignment
                user.role = role
                user.save()
                
                message = f'تم تعيين الدور "{role.display_name}" للمستخدم "{user.get_full_name()}"'
            else:
                # Remove role
                user.role = None
                user.save()
                message = f'تم إزالة الدور من المستخدم "{user.get_full_name()}"'
            
            return JsonResponse({
                'success': True,
                'message': message
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
@require_admin()
def user_permissions_detail(request, user_id):
    """Get detailed user custom permissions for modal display."""
    user = get_object_or_404(User, id=user_id)
    
    # Import the services here to avoid circular imports
    from .services.user_management_service import UserManagementService
    from django.contrib.contenttypes.models import ContentType
    
    try:
        # Get user's role permissions (custom permissions only)
        role_permissions = []
        if user.role:
            user_content_type = ContentType.objects.get_for_model(User)
            role_custom_permissions = user.role.permissions.filter(content_type=user_content_type)
            
            for perm in role_custom_permissions:
                role_permissions.append({
                    'id': perm.id,
                    'name': perm.name,
                    'codename': perm.codename,
                    'category': _get_permission_category(perm.codename),
                    'category_name': _get_category_display_name(_get_permission_category(perm.codename)),
                    'category_icon': _get_category_icon(_get_permission_category(perm.codename)),
                    'category_color': _get_category_color(_get_permission_category(perm.codename))
                })
        
        # Get user's custom permissions (direct assignments)
        user_content_type = ContentType.objects.get_for_model(User)
        user_custom_permissions = user.user_permissions.filter(content_type=user_content_type)
        
        custom_permissions = []
        for perm in user_custom_permissions:
            custom_permissions.append({
                'id': perm.id,
                'name': perm.name,
                'codename': perm.codename,
                'category': _get_permission_category(perm.codename)
            })
        
        # Get all available custom permissions
        all_custom_permissions = Permission.objects.filter(content_type=user_content_type)
        available_custom_permissions = []
        
        for perm in all_custom_permissions:
            available_custom_permissions.append({
                'id': perm.id,
                'name': perm.name,
                'codename': perm.codename,
                'category': _get_permission_category(perm.codename),
                'category_name': _get_category_display_name(_get_permission_category(perm.codename)),
                'category_icon': _get_category_icon(_get_permission_category(perm.codename)),
                'category_color': _get_category_color(_get_permission_category(perm.codename))
            })
        
        # Calculate summary
        total_role_permissions = len(role_permissions)
        total_custom_permissions = len(custom_permissions)
        
        # Categories breakdown
        categories_breakdown = {}
        categories = ['customers_suppliers', 'inventory', 'financial', 'reports', 'system_admin']
        
        for category in categories:
            category_perms = [p for p in available_custom_permissions if p['category'] == category]
            assigned_role_perms = [p for p in role_permissions if p['category'] == category]
            assigned_custom_perms = [p for p in custom_permissions if p['category'] == category]
            
            categories_breakdown[category] = {
                'name': _get_category_display_name(category),
                'icon': _get_category_icon(category),
                'color': _get_category_color(category),
                'total': len(category_perms),
                'assigned': len(assigned_role_perms) + len(assigned_custom_perms)
            }
        
        return JsonResponse({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name(),
                'email': user.email,
                'is_active': user.is_active,
                'is_superuser': user.is_superuser,
                'role_name': user.role.display_name if user.role else None,
                'user_type': user.user_type
            },
            'role_permissions': role_permissions,
            'custom_permissions': custom_permissions,
            'available_custom_permissions': available_custom_permissions,
            'summary': {
                'role_permissions_count': total_role_permissions,
                'custom_permissions_count': total_custom_permissions,
                'total_permissions_count': total_role_permissions + total_custom_permissions,
                'categories_breakdown': categories_breakdown
            },
            'last_updated': user.last_login.isoformat() if user.last_login else None
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في تحميل صلاحيات المستخدم: {str(e)}'
        }, status=500)


def _get_permission_category(codename):
    """Get category for permission based on codename."""
    codename = codename.lower()
    
    if any(keyword in codename for keyword in ['عملاء', 'موردين', 'مدفوعات']):
        return 'customers_suppliers'
    elif any(keyword in codename for keyword in ['منتجات', 'مخزون', 'مخازن', 'مبيعات', 'مشتريات', 'مرتجعات']):
        return 'inventory'
    elif any(keyword in codename for keyword in ['محاسبة', 'مالية', 'مصروفات', 'ايرادات', 'خزن', 'حسابات', 'فترات']):
        return 'financial'
    elif 'تقارير' in codename:
        return 'reports'
    else:
        return 'system_admin'


def _get_category_display_name(category):
    """Get display name for category."""
    names = {
        'customers_suppliers': 'العملاء والموردين',
        'inventory': 'المنتجات والمخزون',
        'financial': 'المالية والمحاسبة',
        'reports': 'التقارير',
        'system_admin': 'إدارة النظام'
    }
    return names.get(category, category)


def _get_category_icon(category):
    """Get icon for category."""
    icons = {
        'customers_suppliers': 'fas fa-users',
        'inventory': 'fas fa-boxes',
        'financial': 'fas fa-money-bill-wave',
        'reports': 'fas fa-chart-bar',
        'system_admin': 'fas fa-cogs'
    }
    return icons.get(category, 'fas fa-key')


def _get_category_color(category):
    """Get color for category."""
    colors = {
        'customers_suppliers': 'info',
        'inventory': 'warning',
        'financial': 'success',
        'reports': 'secondary',
        'system_admin': 'danger'
    }
    return colors.get(category, 'primary')


@login_required
@login_required
def get_available_permissions(request):
    """Get available custom permissions for role/user assignment."""
    try:
        # التحقق من الصلاحيات بطريقة أكثر مرونة
        user = request.user
        
        # السماح لمستخدمي الريسيبشن بعرض الصلاحيات (للقراءة فقط)
        can_view_permissions = (
            user.is_superuser or 
            user.is_admin or 
            user.can_manage_roles() or
            user.is_reception or
            user.user_type == 'reception'
        )
        
        if not can_view_permissions:
            return JsonResponse({
                'success': False,
                'error': 'permission_denied',
                'message': f'ليس لديك صلاحية للوصول لهذه البيانات. نوع المستخدم: {user.user_type}',
                'debug': {
                    'user_type': user.user_type,
                    'is_admin': user.is_admin,
                    'is_superuser': user.is_superuser,
                    'can_manage_roles': user.can_manage_roles(),
                    'is_reception': getattr(user, 'is_reception', False)
                }
            }, status=403)
        
        # Get only custom permissions organized by categories
        categorized_permissions = PermissionService.get_categorized_custom_permissions()
        
        # Add informational alert about hidden Django permissions
        total_django_permissions = Permission.objects.count()
        total_custom_permissions = PermissionService.get_custom_permissions_only().count()
        hidden_permissions_count = total_django_permissions - total_custom_permissions
        
        # Convert permissions to serializable format with Arabic names
        serializable_permissions = {}
        for category_key, category_data in categorized_permissions.items():
            serializable_permissions[category_key] = {
                'name': category_data['name'],
                'name_en': category_data['name_en'],
                'icon': category_data['icon'],
                'description': category_data['description'],
                'count': category_data['count'],
                'permissions': [
                    {
                        'id': perm.id,
                        'codename': perm.codename,
                        'name': _get_arabic_permission_name(perm),
                        'original_name': perm.name,
                        'content_type': perm.content_type.model,
                        'app_label': perm.content_type.app_label
                    }
                    for perm in category_data['permissions']
                ]
            }
        
        return JsonResponse({
            'success': True,
            'permissions': serializable_permissions,
            'stats': {
                'total_django_permissions': total_django_permissions,
                'total_custom_permissions': total_custom_permissions,
                'hidden_permissions_count': hidden_permissions_count
            }
        })
    
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        error_details = traceback.format_exc()
        logger.error(f"Error in get_available_permissions: {error_details}")
        
        return JsonResponse({
            'success': False,
            'message': f'خطأ في تحميل الصلاحيات: {str(e)}',
            'error_details': error_details if request.user.is_superuser else None
        }, status=500)


def _get_app_display_name(app_label):
    """Get display name for app label."""
    app_names = {
        'users': 'المستخدمين',
        'core': 'النظام الأساسي',
        'financial': 'المالي',
        'product': 'المنتجات',
        'hr': 'الموارد البشرية',
        'governance': 'الحوكمة',
        'purchase': 'المشتريات',
        'supplier': 'الموردين',
        'auth': 'المصادقة',
        'contenttypes': 'أنواع المحتوى',
        'sessions': 'الجلسات',
        'admin': 'الإدارة'
    }
    return app_names.get(app_label, app_label.title())


@login_required
@secure_admin_operation('monitoring_data')
def get_monitoring_data(request):
    """Get real-time monitoring data for dashboard."""
    if request.method == 'GET':
        try:
            data_type = request.GET.get('type', 'all')
            
            if data_type == 'health':
                data = PermissionMonitoringService.get_system_health()
            elif data_type == 'alerts':
                hours = int(request.GET.get('hours', 24))
                data = PermissionMonitoringService.get_security_alerts(hours)
            elif data_type == 'usage':
                days = int(request.GET.get('days', 7))
                data = PermissionMonitoringService.get_usage_statistics(days)
            elif data_type == 'performance':
                data = PermissionService.get_performance_metrics()
            else:
                data = PermissionMonitoringService.get_monitoring_dashboard_data()
            
            return JsonResponse({
                'success': True,
                'data': data,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
@secure_admin_operation('bulk_role_assignment')
def bulk_assign_roles(request):
    """AJAX endpoint for bulk role assignment."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            user_ids = data.get('user_ids', [])
            role_id = data.get('role_id')
            
            if not user_ids or not role_id:
                return JsonResponse({
                    'success': False,
                    'message': 'معرفات المستخدمين والدور مطلوبة'
                }, status=400)
            
            # Get users and role
            users = User.objects.filter(id__in=user_ids, is_active=True)
            role = get_object_or_404(Role, id=role_id, is_active=True)
            
            if not users.exists():
                return JsonResponse({
                    'success': False,
                    'message': 'لم يتم العثور على مستخدمين صالحين'
                }, status=400)
            
            # Prepare user-role pairs
            user_role_pairs = [(user, role) for user in users]
            
            # Perform bulk assignment
            results = PermissionService.bulk_assign_roles(user_role_pairs, request.user)
            
            return JsonResponse({
                'success': True,
                'message': f'تم تعيين الدور لـ {len(results["success"])} مستخدم بنجاح',
                'results': results
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
@secure_admin_operation('role_comparison')
def compare_roles(request):
    """AJAX endpoint for role comparison."""
    if request.method == 'GET':
        role1_id = request.GET.get('role1_id')
        role2_id = request.GET.get('role2_id')
        
        if not role1_id or not role2_id:
            return JsonResponse({
                'success': False,
                'message': 'معرفات الأدوار مطلوبة'
            }, status=400)
        
        try:
            role1 = get_object_or_404(Role, id=role1_id)
            role2 = get_object_or_404(Role, id=role2_id)
            
            comparison = PermissionService.compare_roles(role1, role2)
            
            return JsonResponse({
                'success': True,
                'comparison': comparison
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)



@login_required
@secure_admin_operation('export_roles')
def export_roles(request):
    """Export role configuration."""
    if request.method == 'GET':
        try:
            role_ids = request.GET.getlist('role_ids')
            role_ids = [int(rid) for rid in role_ids if rid.isdigit()] if role_ids else None
            
            export_data = PermissionService.export_role_configuration(role_ids)
            
            return JsonResponse({
                'success': True,
                'export_data': export_data,
                'filename': f'roles_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)


@login_required
@require_admin()
def user_update_custom_permissions(request, user_id):
    """AJAX endpoint for updating user's custom permissions (42 custom permissions only)."""
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        
        try:
            data = json.loads(request.body)
            permission_ids = data.get('permission_ids', [])
            
            # Validate that all permissions are custom permissions only
            from django.contrib.contenttypes.models import ContentType
            user_content_type = ContentType.objects.get_for_model(User)
            
            # Get only custom permissions
            custom_permissions = Permission.objects.filter(
                id__in=permission_ids,
                content_type=user_content_type
            )
            
            if len(custom_permissions) != len(permission_ids):
                return JsonResponse({
                    'success': False,
                    'message': 'بعض الصلاحيات المحددة غير صحيحة أو ليست من الصلاحيات المخصصة'
                }, status=400)
            
            # Update user's custom permissions (replace existing custom permissions)
            user.user_permissions.filter(content_type=user_content_type).delete()
            user.user_permissions.add(*custom_permissions)
            
            # Log the change
            from .models import ActivityLog
            ActivityLog.objects.create(
                user=request.user,
                action='update_user_custom_permissions',
                description=f'تحديث الصلاحيات المخصصة للمستخدم {user.get_full_name()}',
                details={
                    'target_user_id': user.id,
                    'target_user_name': user.get_full_name(),
                    'custom_permissions_count': len(custom_permissions),
                    'permission_ids': permission_ids
                }
            )
            
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث الصلاحيات المخصصة للمستخدم "{user.get_full_name()}" بنجاح',
                'custom_permissions_count': len(custom_permissions),
                'total_custom_available': Permission.objects.filter(content_type=user_content_type).count()
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'بيانات غير صحيحة'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)