"""
Django admin interface for Governance Switchboard.
Provides web-based management of governance feature flags.
"""

from django.contrib import admin
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import path
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .services import governance_switchboard
import json


def superuser_required(user):
    """Check if user is superuser (required for governance changes)"""
    return user.is_superuser


class GovernanceSwitchboardAdmin:
    """
    Admin interface for Governance Switchboard.
    Provides web-based management of all governance flags.
    """
    
    def get_urls(self):
        """Define admin URLs for switchboard management"""
        urls = [
            path('', self.admin_site.admin_view(self.switchboard_view), name='governance_switchboard'),
            path('api/status/', self.admin_site.admin_view(self.api_status), name='governance_api_status'),
            path('api/toggle-component/', self.admin_site.admin_view(self.api_toggle_component), name='governance_api_toggle_component'),
            path('api/toggle-workflow/', self.admin_site.admin_view(self.api_toggle_workflow), name='governance_api_toggle_workflow'),
            path('api/emergency/', self.admin_site.admin_view(self.api_emergency), name='governance_api_emergency'),
        ]
        return urls
    
    @method_decorator(user_passes_test(superuser_required))
    def switchboard_view(self, request):
        """Main switchboard management view"""
        context = {
            'title': 'Governance Switchboard',
            'has_permission': True,
            'opts': {'app_label': 'governance', 'model_name': 'switchboard'},
            'stats': governance_switchboard.get_governance_statistics(),
            'component_flags': governance_switchboard.COMPONENT_FLAGS,
            'workflow_flags': governance_switchboard.WORKFLOW_FLAGS,
            'emergency_flags': governance_switchboard.EMERGENCY_FLAGS,
            'current_state': {
                'components': dict(governance_switchboard._component_flags),
                'workflows': dict(governance_switchboard._workflow_flags),
                'emergencies': dict(governance_switchboard._emergency_flags)
            }
        }
        
        return render(request, 'governance/admin/switchboard.html', context)
    
    @method_decorator(user_passes_test(superuser_required))
    def api_status(self, request):
        """API endpoint for current status"""
        if request.method != 'GET':
            return JsonResponse({'error': 'Method not allowed'}, status=405)
        
        stats = governance_switchboard.get_governance_statistics()
        return JsonResponse(stats)
    
    @method_decorator(user_passes_test(superuser_required))
    @require_http_methods(["POST"])
    def api_toggle_component(self, request):
        """API endpoint for toggling component flags"""
        try:
            data = json.loads(request.body)
            component_name = data.get('component')
            enabled = data.get('enabled')
            reason = data.get('reason', 'Admin panel toggle')
            
            if not component_name or enabled is None:
                return JsonResponse({'error': 'Missing component or enabled parameter'}, status=400)
            
            if component_name not in governance_switchboard.COMPONENT_FLAGS:
                return JsonResponse({'error': f'Unknown component: {component_name}'}, status=400)
            
            # Toggle the component
            if enabled:
                success = governance_switchboard.enable_component(component_name, reason, request.user)
            else:
                success = governance_switchboard.disable_component(component_name, reason, request.user)
            
            if success:
                return JsonResponse({
                    'success': True,
                    'component': component_name,
                    'enabled': enabled,
                    'message': f"Component '{component_name}' {'enabled' if enabled else 'disabled'}"
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': f"Failed to {'enable' if enabled else 'disable'} component '{component_name}'"
                }, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    @method_decorator(user_passes_test(superuser_required))
    @require_http_methods(["POST"])
    def api_toggle_workflow(self, request):
        """API endpoint for toggling workflow flags"""
        try:
            data = json.loads(request.body)
            workflow_name = data.get('workflow')
            enabled = data.get('enabled')
            reason = data.get('reason', 'Admin panel toggle')
            
            if not workflow_name or enabled is None:
                return JsonResponse({'error': 'Missing workflow or enabled parameter'}, status=400)
            
            if workflow_name not in governance_switchboard.WORKFLOW_FLAGS:
                return JsonResponse({'error': f'Unknown workflow: {workflow_name}'}, status=400)
            
            # Toggle the workflow
            if enabled:
                success = governance_switchboard.enable_workflow(workflow_name, reason, request.user)
            else:
                success = governance_switchboard.disable_workflow(workflow_name, reason, request.user)
            
            if success:
                return JsonResponse({
                    'success': True,
                    'workflow': workflow_name,
                    'enabled': enabled,
                    'message': f"Workflow '{workflow_name}' {'enabled' if enabled else 'disabled'}"
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': f"Failed to {'enable' if enabled else 'disable'} workflow '{workflow_name}'"
                }, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    @method_decorator(user_passes_test(superuser_required))
    @require_http_methods(["POST"])
    def api_emergency(self, request):
        """API endpoint for emergency flag operations"""
        try:
            data = json.loads(request.body)
            emergency_name = data.get('emergency')
            action = data.get('action')  # 'activate' or 'deactivate'
            reason = data.get('reason')
            
            if not emergency_name or not action or not reason:
                return JsonResponse({'error': 'Missing emergency, action, or reason parameter'}, status=400)
            
            if emergency_name not in governance_switchboard.EMERGENCY_FLAGS:
                return JsonResponse({'error': f'Unknown emergency flag: {emergency_name}'}, status=400)
            
            if action not in ['activate', 'deactivate']:
                return JsonResponse({'error': 'Action must be activate or deactivate'}, status=400)
            
            # Perform emergency action
            if action == 'activate':
                success = governance_switchboard.activate_emergency_flag(emergency_name, reason, request.user)
            else:
                success = governance_switchboard.deactivate_emergency_flag(emergency_name, reason, request.user)
            
            if success:
                return JsonResponse({
                    'success': True,
                    'emergency': emergency_name,
                    'action': action,
                    'message': f"Emergency flag '{emergency_name}' {action}d"
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': f"Failed to {action} emergency flag '{emergency_name}'"
                }, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# Register the switchboard admin
governance_switchboard_admin = GovernanceSwitchboardAdmin()


# Add to Django admin site
class GovernanceSwitchboardProxy:
    """Proxy model for admin registration"""
    class Meta:
        verbose_name = "Governance Switchboard"
        verbose_name_plural = "Governance Switchboard"
        app_label = 'governance'


@admin.register(GovernanceSwitchboardProxy)
class GovernanceSwitchboardAdminModel(admin.ModelAdmin):
    """Django admin model for switchboard"""
    
    def has_module_permission(self, request):
        """Only superusers can access governance switchboard"""
        return request.user.is_superuser
    
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def has_add_permission(self, request):
        return False  # No adding - this is a management interface
    
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        return False  # No deleting - this is a management interface
    
    def changelist_view(self, request, extra_context=None):
        """Redirect to custom switchboard view"""
        return redirect('admin:governance_switchboard')
    
    def get_urls(self):
        """Add custom URLs"""
        urls = super().get_urls()
        custom_urls = governance_switchboard_admin.get_urls()
        return custom_urls + urls