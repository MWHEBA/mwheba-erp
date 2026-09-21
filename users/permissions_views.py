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
from django.core.exceptions import ValidationError
import json

from .models import User, Role
from .forms import RoleForm, UserRoleForm
from .services.permission_service import PermissionService
from .services.monitoring import PermissionMonitoringService
from .decorators import require_admin, secure_admin_operation


def _get_arabic_permission_name(permission):
    """Convert Django permission names to standard Arabic equivalents."""
    codename = permission.codename.lower()
    model_name = permission.content_type.model.lower()
    
    # 1. Exact Custom Business Permissions Mapping (First Priority)
    exact_custom_translations = {
        # Financial & Multi-Currency
        'close_accounting_period': 'إغلاق الفترة المحاسبية',
        'reopen_accounting_period': 'إعادة فتح فترة محاسبية',
        'run_fx_revaluation': 'إعادة تقييم فروق العملات',
        'post_journal_entry': 'ترحيل القيود اليومية',
        'reverse_journal_entry': 'عكس قيد محاسبي',
        'view_cost_breakdown': 'الاطلاع على تفاصيل تكلفة الخامات',
        'view_profit_margins': 'الاطلاع على هوامش الأرباح',
        'view_all_orders': 'عرض كافة طلبات وأوامر التشغيل',
        
        # Sales & Pricing Rules
        'change_unit_price': 'تعديل سعر الوحدة بالفاتورة',
        'apply_special_discount': 'تطبيق خصم خاص إضافي',
        'cancel_approved_sale': 'إلغاء فاتورة بيع معتمدة',
        'print_sale_invoice': 'طباعة فاتورة المبيعات',
        'view_all_sales': 'عرض كافة مبيعات المنظومة',
        'change_sale_salesman': 'تغيير مندوب المبيعات',
        'change_quotation_price': 'تعديل أسعار عروض الأسعار',
        'view_all_quotations': 'عرض كافة عروض الأسعار',
        'convert_to_order': 'تحويل عرض السعر إلى أمر بيع',
        'approve_salesorder': 'اعتماد أوامر البيع',
        
        # Purchases & Suppliers
        'approve_purchase': 'اعتماد فواتير الشراء',
        'change_unit_cost': 'تعديل تكلفة الشراء بالفاتورة',
        'cancel_approved_purchase': 'إلغاء فاتورة شراء معتمدة',
        'approve_purchaseorder': 'اعتماد أوامر الشراء',
        
        # Warehouses & Inventory
        'approve_inventory_adjustment': 'اعتماد تسويات الجرد المخزني',
        'approve_batchvoucher': 'اعتماد أذون الخامات والمجموعات',
        
        # Printing & Pricing Settings
        'override_pricing_rules': 'تجاوز قواعد التسعير المعيارية',
        'manage_pricing_settings': 'إدارة إعدادات وقواعد التسعير',
        'change_workorder_status': 'تغيير حالة أمر الشغل والإنتاج',
        'cancel_workorder': 'إلغاء أمر الشغل والإنتاج',
    }
    
    if codename in exact_custom_translations:
        return exact_custom_translations[codename]
    
    # 2. Comprehensive Model Translations
    model_translations = {
        # Sales & Quotations
        'sale': 'فواتير المبيعات',
        'quotation': 'عروض الأسعار',
        'salesorder': 'أوامر البيع',
        'deliverynote': 'أذون التسليم',
        'salereturn': 'مرتجعات المبيعات',
        
        # Purchases & Suppliers
        'purchase': 'فواتير المشتريات',
        'purchaseorder': 'أوامر الشراء',
        'goodsreceivednote': 'أذون الاستلام المخزني',
        'purchasereturn': 'مردودات المشتريات',
        'supplier': 'الموردين',
        
        # Inventory & Products
        'product': 'الأصناف والمنتجات',
        'warehouse': 'المخازن',
        'stock': 'أرصدة المخزون',
        'stockmovement': 'حركات المخزون',
        'inventorymovement': 'حركات المخزون',
        'inventoryadjustment': 'تسويات الجرد',
        'unit': 'وحدات القياس',
        'category': 'تصنيفات الأصناف',
        'batchvoucher': 'أذون الخامات والمجموعات',
        'landedcostdocument': 'تكاليف الإنزال',
        
        # Financial & Accounts
        'journalentry': 'القيود اليومية',
        'accountingperiod': 'الفترات المحاسبية',
        'chartofaccounts': 'شجرة الحسابات',
        'account': 'الحسابات',
        'currency': 'العملات وأسعار الصرف',
        'paymentvoucher': 'سندات الصرف',
        'receiptvoucher': 'سندات القبض',
        'customerpayment': 'دفعات العملاء',
        'transaction': 'المعاملات المالية',
        'invoice': 'الفواتير',
        
        # Printing & Work Orders
        'workorder': 'أوامر الشغل والإنتاج',
        'printingorder': 'طلبات تسعير المطبوعات',
        
        # Customers & HR & Users
        'customer': 'العملاء',
        'employee': 'الموظفين',
        'contract': 'عقود العمل',
        'leave': 'الإجازات',
        'attendance': 'الحضور والانصراف',
        'user': 'المستخدمين',
        'role': 'الأدوار والصلاحيات',
        
        # System & Auditing
        'audittrail': 'سجلات التدقيق',
        'report': 'التقارير',
        'dashboard': 'لوحة التحكم',
    }
    
    model_arabic = model_translations.get(model_name, model_name)
    
    # 3. Action Prefix Handling
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
        return f"إدارة {model_translations.get(action_part, model_arabic)}"
    elif codename.startswith('can_export_'):
        action_part = codename.replace('can_export_', '')
        return f"تصدير {model_translations.get(action_part, model_arabic)}"
    elif codename.startswith('can_view_'):
        action_part = codename.replace('can_view_', '')
        return f"عرض {model_translations.get(action_part, model_arabic)}"
    elif codename.startswith('can_process_'):
        action_part = codename.replace('can_process_', '')
        return f"معالجة {model_translations.get(action_part, model_arabic)}"
    
    return f"{codename} ({model_arabic})"


@login_required
def permissions_dashboard(request):
    """
    Unified permissions management dashboard with tabs.
    """
    try:
        # Check user permissions for admin features
        user_can_manage_roles = request.user.is_superuser or getattr(request.user, 'is_admin', False)
        user_can_view_permissions = (
            user_can_manage_roles or 
            (hasattr(request.user, 'can_manage_users') and request.user.can_manage_users()) or
            request.user.has_perm('users.view_user')
        )
        
        if not user_can_view_permissions:
            return render(
                request,
                'core/permission_denied.html',
                {'title': 'غير مصرح', 'message': 'ليس لديك صلاحية لعرض لوحة تحكم الصلاحيات'},
                status=403
            )

        # Get current tab from URL parameter
        current_tab = request.GET.get('tab', 'overview')
        
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
                    'toggle': 'modal',
                    'target': '#createRoleModal',
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
                'role': request.user.role.name if request.user.role else 'no_role',
                'role_display': request.user.role.display_name if request.user.role else 'بدون دور',
                'can_manage_users': request.user.can_manage_users() if hasattr(request.user, 'can_manage_users') else False,
            }
        }
        
        # Base roles queryset available across all tabs for modals and filters
        available_roles = Role.objects.filter(is_active=True).order_by('display_name')
        context['available_roles'] = available_roles
        
        # Load data on demand for the requested tab only (SSR-Safe & Pagination Collision Free)
        if current_tab == 'roles':
            try:
                context.update(_get_roles_tab_data(request))
            except Exception as e:
                context.update({'roles': [], 'search': '', 'total_roles': 0, 'roles_error': str(e)})
        elif current_tab == 'users':
            try:
                context.update(_get_users_tab_data(request))
            except Exception as e:
                context.update({'users': [], 'total_users': 0, 'users_error': str(e)})
        elif current_tab == 'monitoring':
            try:
                context.update(_get_monitoring_tab_data(request))
            except Exception as e:
                context.update({'recent_changes': [], 'days_filter': 7, 'total_changes': 0, 'monitoring_error': str(e)})
        else:
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
        # Get all roles with user counts and annotated permissions count (N+1 free)
        roles = Role.objects.select_related('parent_role').annotate(
            user_count=Count('users', filter=Q(users__is_active=True), distinct=True),
            permissions_count_annotated=Count('permissions', distinct=True)
        ).order_by('-is_system_role', 'display_name')
        
        # Search functionality
        search = request.GET.get('search', '')
        if search:
            roles = roles.filter(
                Q(name__icontains=search) |
                Q(display_name__icontains=search) |
                Q(description__icontains=search)
            )
        
        # Pagination SSR
        from core.utils import paginate_queryset
        roles_pagination = paginate_queryset(roles, request, default_per_page=25)
        roles_page = roles_pagination["page_obj"]
        
        return {
            'roles': roles_page,
            'roles_pagination': roles_pagination,
            'page_obj': roles_page,
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
    
    # Pagination SSR
    from core.utils import paginate_queryset
    users_pagination = paginate_queryset(users_data, request, default_per_page=25)
    users_page = users_pagination["page_obj"]
    
    # Get roles for filter dropdown
    available_roles = Role.objects.filter(is_active=True).order_by('display_name')
    
    return {
        'users': users_page,
        'users_pagination': users_pagination,
        'page_obj': users_page,
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
        
        # Pagination SSR for changes
        from core.utils import paginate_queryset
        changes_pagination = paginate_queryset(recent_changes, request, default_per_page=25)
        changes_page = changes_pagination["page_obj"]
        
        return {
            'monitoring_data': monitoring_data,
            'recent_changes': changes_page,
            'changes_pagination': changes_pagination,
            'page_obj': changes_page,
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


def _resolve_permissions_from_input(perm_inputs):
    """Resolve permissions from list of IDs (int) or codenames/app.codename (str)."""
    if not perm_inputs:
        return Permission.objects.none()
    
    int_ids = []
    string_perms = []
    for p in perm_inputs:
        if isinstance(p, int) or (isinstance(p, str) and p.isdigit()):
            int_ids.append(int(p))
        elif isinstance(p, str):
            string_perms.append(p)
            
    from django.db.models import Q
    query = Q()
    if int_ids:
        query |= Q(id__in=int_ids)
    for sp in string_perms:
        if '.' in sp:
            app_label, codename = sp.split('.', 1)
            query |= Q(content_type__app_label=app_label, codename=codename)
        else:
            query |= Q(codename=sp)
            
    return Permission.objects.filter(query) if query else Permission.objects.none()


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
            
            # Get permissions (supports both integer IDs and string codenames)
            permissions = _resolve_permissions_from_input(permission_ids)
            
            # Parent role if provided
            parent_role_id = data.get('parent_role_id')
            parent_role = None
            if parent_role_id:
                parent_role = get_object_or_404(Role, id=parent_role_id)
            
            # Create role using service
            role = PermissionService.create_role(
                name=name,
                display_name=display_name,
                description=description,
                permissions=list(permissions),
                created_by=request.user
            )
            if parent_role:
                role.parent_role = parent_role
                role.save()
            
            # Auto-resolve prerequisites explicitly in DB (Dual-Guarded SSOT)
            from users.services.permission_dependency import PermissionDependencyService
            PermissionDependencyService.auto_resolve_dependencies_for_role(role)
            
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
            
        except ValidationError as e:
            msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
            return JsonResponse({
                'success': False,
                'message': msg
            }, status=400)
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
                'parent_role_id': role.parent_role_id,
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
            if 'parent_role_id' in data:
                pr_id = data.get('parent_role_id')
                role.parent_role = get_object_or_404(Role, id=pr_id) if pr_id else None
            role.save()
            
            # Update permissions if provided (supports both IDs and string codenames)
            raw_perms = data.get('permissions')
            if raw_perms is None and 'permission_ids' in data:
                raw_perms = data.get('permission_ids')
            if raw_perms is not None:
                permissions = _resolve_permissions_from_input(raw_perms)
                PermissionService.update_role_permissions(
                    role=role,
                    permissions=list(permissions),
                    updated_by=request.user
                )
                from users.services.permission_dependency import PermissionDependencyService
                PermissionDependencyService.auto_resolve_dependencies_for_role(role)
            
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث الدور "{role.display_name}" بنجاح'
            })
            
        except ValidationError as e:
            msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
            return JsonResponse({
                'success': False,
                'message': msg
            }, status=400)
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
        
        # Check if role has active secondary users
        secondary_users_count = role.secondary_users.filter(is_active=True).count()
        if secondary_users_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'لا يمكن حذف الدور لأنه مرتبط بـ {secondary_users_count} مستخدم كدور ثانوي'
            }, status=400)
        
        # Check if role has active child roles inheriting from it
        child_roles_count = role.child_roles.filter(is_active=True).count()
        if child_roles_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'لا يمكن حذف الدور لأنه مستخدم كدور أب لـ {child_roles_count} أدوار تابعة نشطة'
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
@require_admin()
def user_assign_role(request, user_id):
    """AJAX endpoint for assigning primary and secondary roles to user."""
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        
        if user.is_superuser:
            return JsonResponse({
                'success': False,
                'message': 'لا يمكن تعديل أدوار المدير العام (Superuser)'
            }, status=400)
        
        try:
            data = json.loads(request.body)
            role_id = data.get('role_id')
            secondary_role_ids = data.get('secondary_role_ids', [])
            
            # Primary role assignment
            if role_id:
                role = get_object_or_404(Role, id=role_id)
                user.role = role
            else:
                user.role = None
            user.save()
            
            # Secondary roles assignment
            clean_secondary_ids = [int(rid) for rid in secondary_role_ids if str(rid).isdigit() and int(rid) != (user.role.id if user.role else None)]
            user.secondary_roles.set(Role.objects.filter(id__in=clean_secondary_ids, is_active=True))
            
            # Invalidate user cache
            if hasattr(user, '_cached_permissions'):
                delattr(user, '_cached_permissions')
            from users.services.permission_cache import PermissionCacheService
            PermissionCacheService.invalidate_user_cache(user.id)
            
            user_name = user.get_full_name() or user.username
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث أدوار المستخدم "{user_name}" بنجاح'
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
    
    try:
        # Get business-relevant permissions
        available_permissions = list(PermissionService.get_custom_permissions_only().select_related('content_type'))
        available_ids = {p.id for p in available_permissions}
        
        # Role permissions (including secondary roles and parent role hierarchy via bulk O(1) query)
        role_permissions_set = set()
        roles_to_inspect = []
        if user.role:
            roles_to_inspect.append(user.role)
        if hasattr(user, 'secondary_roles'):
            roles_to_inspect.extend(list(user.secondary_roles.all()))

        visited_role_ids = set()
        while roles_to_inspect:
            current_role = roles_to_inspect.pop()
            if not current_role or current_role.id in visited_role_ids:
                continue
            visited_role_ids.add(current_role.id)
            if current_role.parent_role_id and current_role.parent_role_id not in visited_role_ids:
                roles_to_inspect.append(current_role.parent_role)

        if visited_role_ids:
            role_permissions_set = set(
                Permission.objects.filter(
                    user_roles__in=visited_role_ids,
                    id__in=available_ids
                ).select_related('content_type').distinct()
            )

        # Direct custom permissions
        direct_permissions_set = set(
            user.user_permissions.filter(id__in=available_ids).select_related('content_type')
        )
        if hasattr(user, 'custom_permissions'):
            direct_permissions_set |= set(
                user.custom_permissions.filter(id__in=available_ids).select_related('content_type')
            )

        # Revoked permissions
        revoked_permissions_set = set()
        if hasattr(user, 'revoked_permissions'):
            revoked_permissions_set = set(
                user.revoked_permissions.filter(id__in=available_ids).select_related('content_type')
            )

        # Format lists
        role_permissions = [
            {
                'id': p.id,
                'name': _get_arabic_permission_name(p),
                'codename': p.codename,
                'category': _get_permission_category(p),
                'category_name': _get_category_display_name(_get_permission_category(p)),
                'category_icon': _get_category_icon(_get_permission_category(p)),
                'category_color': _get_category_color(_get_permission_category(p))
            }
            for p in role_permissions_set
        ]

        custom_permissions = [
            {
                'id': p.id,
                'name': _get_arabic_permission_name(p),
                'codename': p.codename,
                'category': _get_permission_category(p),
                'category_name': _get_category_display_name(_get_permission_category(p)),
                'category_icon': _get_category_icon(_get_permission_category(p)),
                'category_color': _get_category_color(_get_permission_category(p))
            }
            for p in direct_permissions_set
        ]

        revoked_permissions = [
            {
                'id': p.id,
                'name': _get_arabic_permission_name(p),
                'codename': p.codename,
                'category': _get_permission_category(p),
                'category_name': _get_category_display_name(_get_permission_category(p)),
                'category_icon': _get_category_icon(_get_permission_category(p)),
                'category_color': _get_category_color(_get_permission_category(p))
            }
            for p in revoked_permissions_set
        ]

        available_custom_permissions = [
            {
                'id': p.id,
                'name': _get_arabic_permission_name(p),
                'codename': p.codename,
                'category': _get_permission_category(p),
                'category_name': _get_category_display_name(_get_permission_category(p)),
                'category_icon': _get_category_icon(_get_permission_category(p)),
                'category_color': _get_category_color(_get_permission_category(p))
            }
            for p in available_permissions
        ]

        # Categories breakdown for UI and JS
        categories_dict = {}
        all_categories = ['sale', 'purchase', 'financial', 'product', 'customer', 'supplier', 'printing_pricing', 'work_order', 'hr', 'system']

        for cat in all_categories:
            cat_role_perms = [p for p in role_permissions if p['category'] == cat]
            cat_direct_perms = [p for p in custom_permissions if p['category'] == cat]
            cat_revoked_perms = [p for p in revoked_permissions if p['category'] == cat]
            cat_total_perms = [p for p in available_custom_permissions if p['category'] == cat]

            categories_dict[cat] = {
                'name': _get_category_display_name(cat),
                'icon': _get_category_icon(cat),
                'color': _get_category_color(cat),
                'total': len(cat_total_perms),
                'assigned': len(cat_role_perms) + len(cat_direct_perms) - len(cat_revoked_perms),
                'role_permissions': cat_role_perms,
                'direct_permissions': cat_direct_perms,
                'revoked_permissions': cat_revoked_perms,
            }

        total_unique = len(({p['id'] for p in role_permissions} | {p['id'] for p in custom_permissions}) - {p['id'] for p in revoked_permissions})

        return JsonResponse({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name() or user.username,
                'email': user.email,
                'is_active': user.is_active,
                'is_superuser': user.is_superuser,
                'role_name': user.role.display_name if user.role else 'بدون دور',
                'role_code': user.role.name if user.role else None,
                'secondary_roles': [r.display_name for r in user.secondary_roles.all()] if hasattr(user, 'secondary_roles') else []
            },
            'permissions_overview': {
                'total_custom_permissions': total_unique,
                'role_permissions_count': len(role_permissions),
                'direct_permissions_count': len(custom_permissions),
                'revoked_permissions_count': len(revoked_permissions),
            },
            'categories': categories_dict,
            'role_permissions': role_permissions,
            'custom_permissions': custom_permissions,
            'revoked_permissions': revoked_permissions,
            'available_custom_permissions': available_custom_permissions,
            'summary': {
                'role_permissions_count': len(role_permissions),
                'custom_permissions_count': len(custom_permissions),
                'revoked_permissions_count': len(revoked_permissions),
                'total_permissions_count': total_unique,
                'categories_breakdown': categories_dict
            },
            'last_updated': user.last_login.isoformat() if user.last_login else None
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في تحميل صلاحيات المستخدم: {str(e)}'
        }, status=500)


def _get_permission_category(perm):
    """Get category for permission based on app_label or codename."""
    app_to_category = {
        'sale': 'sale',
        'purchase': 'purchase',
        'financial': 'financial',
        'governance': 'financial',
        'product': 'product',
        'customer': 'customer',
        'supplier': 'supplier',
        'printing_pricing': 'printing_pricing',
        'work_order': 'work_order',
        'hr': 'hr',
        'users': 'system',
        'core': 'system',
    }
    if hasattr(perm, 'content_type'):
        app_label = perm.content_type.app_label.lower()
        return app_to_category.get(app_label, 'system')
            
    codename = str(getattr(perm, 'codename', perm)).lower()
    for app in ['sale', 'purchase', 'financial', 'product', 'customer', 'supplier', 'printing_pricing', 'work_order', 'hr']:
        if app in codename:
            return app
    return 'system'


def _get_category_display_name(category):
    """Get display name for category."""
    names = {
        'sale': 'المبيعات وعروض الأسعار',
        'purchase': 'المشتريات والموردين',
        'financial': 'الإدارة المالية والحسابات',
        'product': 'المخازن والمنتجات',
        'customer': 'العملاء',
        'supplier': 'الموردين',
        'printing_pricing': 'التسعير وتكاليف الطباعة',
        'work_order': 'أوامر العمل والتشغيل',
        'hr': 'الموارد البشرية والرواتب',
        'system': 'إدارة النظام والمستخدمين',
    }
    return names.get(category, category)


def _get_category_icon(category):
    """Get icon for category."""
    icons = {
        'sale': 'fas fa-cash-register',
        'purchase': 'fas fa-shopping-cart',
        'financial': 'fas fa-calculator',
        'product': 'fas fa-boxes',
        'customer': 'fas fa-users',
        'supplier': 'fas fa-truck',
        'printing_pricing': 'fas fa-print',
        'work_order': 'fas fa-cogs',
        'hr': 'fas fa-user-tie',
        'system': 'fas fa-shield-alt',
    }
    return icons.get(category, 'fas fa-key')


def _get_category_color(category):
    """Get color for category."""
    colors = {
        'sale': 'success',
        'purchase': 'warning',
        'financial': 'primary',
        'product': 'info',
        'customer': 'info',
        'supplier': 'secondary',
        'printing_pricing': 'secondary',
        'work_order': 'warning',
        'hr': 'secondary',
        'system': 'danger',
    }
    return colors.get(category, 'primary')


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
            user.can_manage_roles()
        )
        
        if not can_view_permissions:
            role_label = user.role.display_name if user.role else 'بدون دور'
            return JsonResponse({
                'success': False,
                'error': 'permission_denied',
                'message': f'ليس لديك صلاحية للوصول لهذه البيانات. الدور الحالي: {role_label}',
                'debug': {
                    'role': user.role.name if user.role else None,
                    'is_admin': user.is_admin,
                    'is_superuser': user.is_superuser,
                    'can_manage_roles': user.can_manage_roles(),
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
        
        from users.services.permission_dependency import PermissionDependencyService
        return JsonResponse({
            'success': True,
            'permissions': serializable_permissions,
            'dependencies': PermissionDependencyService.get_unified_dependency_map(),
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
    """AJAX endpoint for updating user's custom permissions."""
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        
        if user.is_superuser:
            return JsonResponse({
                'success': False,
                'message': 'لا يمكن تعديل أو حجب صلاحيات المدير العام (Superuser)'
            }, status=400)
        
        try:
            data = json.loads(request.body)
            raw_perms = data.get('permission_ids') if 'permission_ids' in data else data.get('permissions', [])
            
            # Fetch valid permissions (supports both integer IDs and string codenames)
            valid_permissions = _resolve_permissions_from_input(raw_perms)

            # Old permissions for forensic diff
            old_custom_set = set(user.user_permissions.values_list('codename', flat=True))
            old_revoked_set = set(user.revoked_permissions.values_list('codename', flat=True)) if hasattr(user, 'revoked_permissions') else set()

            # Update user's custom_permissions and sync with standard user_permissions
            user.user_permissions.set(valid_permissions)
            if hasattr(user, 'custom_permissions'):
                user.custom_permissions.set(valid_permissions)

            # Update revoked permissions if provided
            valid_revoked = []
            if 'revoked_permission_ids' in data or 'revoked_permissions' in data:
                raw_revoked = data.get('revoked_permission_ids') if 'revoked_permission_ids' in data else data.get('revoked_permissions', [])
                valid_revoked = _resolve_permissions_from_input(raw_revoked)
                if hasattr(user, 'revoked_permissions'):
                    user.revoked_permissions.set(valid_revoked)

            from users.services.permission_dependency import PermissionDependencyService
            PermissionDependencyService.auto_resolve_dependencies_for_user(user)

            # New permissions for forensic diff
            new_custom_set = set(user.user_permissions.values_list('codename', flat=True))
            new_revoked_set = set(user.revoked_permissions.values_list('codename', flat=True)) if hasattr(user, 'revoked_permissions') else set()

            added_perms = list(new_custom_set - old_custom_set)
            removed_perms = list(old_custom_set - new_custom_set)
            added_revoked = list(new_revoked_set - old_revoked_set)
            removed_revoked = list(old_revoked_set - new_revoked_set)

            # Clear cached permissions in all tiers
            if hasattr(user, '_cached_permissions'):
                delattr(user, '_cached_permissions')
            from users.services.permission_cache import PermissionCacheService
            PermissionCacheService.invalidate_user_cache(user.id)

            # Log to AuditService (Forensic Audit Trail)
            from governance.services.audit_service import AuditService
            AuditService.log_operation(
                model_name='User',
                object_id=user.id,
                operation='UPDATE_USER_PERMISSIONS',
                source_service='PermissionService',
                user=request.user,
                before_data={'permissions': list(old_custom_set), 'revoked': list(old_revoked_set)},
                after_data={'permissions': list(new_custom_set), 'revoked': list(new_revoked_set), 'added': added_perms, 'removed': removed_perms}
            )

            # Log the change to ActivityLog
            from .models import ActivityLog
            from utils.logs import get_client_ip
            ActivityLog.objects.create(
                user=request.user,
                action='تحديث صلاحيات إضافية',
                model_name='User',
                object_id=user.id,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                extra_data={
                    'description': f'تحديث الصلاحيات للمستخدم {user.get_full_name() or user.username}',
                    'target_user_id': user.id,
                    'target_user_name': user.get_full_name() or user.username,
                    'custom_permissions_count': valid_permissions.count(),
                    'revoked_permissions_count': len(valid_revoked),
                    'added_permissions': added_perms,
                    'removed_permissions': removed_perms,
                    'added_revoked': added_revoked,
                    'removed_revoked': removed_revoked,
                    'permission_ids': list(valid_permissions.values_list('id', flat=True))
                }
            )
            
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث الصلاحيات الإضافية للمستخدم "{user.get_full_name() or user.username}" بنجاح',
                'custom_permissions_count': valid_permissions.count(),
                'total_custom_available': PermissionService.get_custom_permissions_only().count()
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