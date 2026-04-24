"""
Payroll Signal Governance Dashboard Views

This module provides web-based monitoring and control interfaces
for the payroll signal governance system.
"""

import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View

from governance.services.payroll_signal_governance import payroll_signal_governance
from governance.signals.payroll_signals import PayrollSignalFeatureFlags


def is_superuser(user):
    """Check if user is superuser"""
    return user.is_superuser


@login_required
@user_passes_test(is_superuser)
def payroll_signal_dashboard(request):
    """
    Main dashboard for payroll signal governance monitoring.
    
    Shows:
    - Overall governance status
    - Individual signal rollout status
    - Health metrics
    - Recent activity
    """
    try:
        # Get comprehensive status
        rollout_status = payroll_signal_governance.get_rollout_status()
        health_status = payroll_signal_governance.get_health_status()
        
        # Prepare context
        context = {
            'rollout_status': rollout_status,
            'health_status': health_status,
            'governance_enabled': rollout_status['governance_enabled'],
            'monitoring_active': rollout_status['monitoring_active'],
            'master_kill_switch': rollout_status['master_kill_switch'],
            'signals': rollout_status['signals'],
            'summary': rollout_status['summary'],
            'counters': rollout_status['counters'],
            'health_issues': health_status['issues'],
            'recommendations': health_status['recommendations'],
            'page_title': 'Payroll Signal Governance Dashboard'
        }
        
        return render(request, 'governance/payroll_signal_dashboard.html', context)
        
    except Exception as e:
        messages.error(request, f'Error loading dashboard: {str(e)}')
        return render(request, 'governance/payroll_signal_dashboard.html', {
            'error': str(e),
            'page_title': 'Payroll Signal Governance Dashboard'
        })


@login_required
@user_passes_test(is_superuser)
@require_http_methods(["POST"])
def enable_governance(request):
    """Enable payroll signal governance"""
    try:
        reason = request.POST.get('reason', 'Manual enable via dashboard')
        
        success = payroll_signal_governance.enable_payroll_signal_governance(
            request.user, reason
        )
        
        if success:
            messages.success(request, 'Payroll signal governance enabled successfully')
        else:
            messages.error(request, 'Failed to enable payroll signal governance')
            
    except Exception as e:
        messages.error(request, f'Error enabling governance: {str(e)}')
    
    return redirect('governance:payroll_signal_dashboard')


@login_required
@user_passes_test(is_superuser)
@require_http_methods(["POST"])
def disable_governance(request):
    """Disable payroll signal governance (safe rollback)"""
    try:
        reason = request.POST.get('reason', 'Manual disable via dashboard')
        
        success = payroll_signal_governance.disable_payroll_signal_governance(
            request.user, reason
        )
        
        if success:
            messages.warning(request, 'Payroll signal governance disabled (safe rollback)')
        else:
            messages.error(request, 'Failed to disable payroll signal governance')
            
    except Exception as e:
        messages.error(request, f'Error disabling governance: {str(e)}')
    
    return redirect('governance:payroll_signal_dashboard')


@login_required
@user_passes_test(is_superuser)
@require_http_methods(["POST"])
def activate_kill_switch(request):
    """Activate kill switch for specific signal"""
    try:
        signal_name = request.POST.get('signal_name')
        reason = request.POST.get('reason', 'Manual kill switch via dashboard')
        
        if not signal_name:
            messages.error(request, 'Signal name is required')
            return redirect('governance:payroll_signal_dashboard')
        
        success = payroll_signal_governance.activate_kill_switch(
            signal_name, request.user, reason
        )
        
        if success:
            messages.warning(request, f'Kill switch activated for {signal_name}')
        else:
            messages.error(request, f'Failed to activate kill switch for {signal_name}')
            
    except Exception as e:
        messages.error(request, f'Error activating kill switch: {str(e)}')
    
    return redirect('governance:payroll_signal_dashboard')


@login_required
@user_passes_test(is_superuser)
@require_http_methods(["POST"])
def deactivate_kill_switch(request):
    """Deactivate kill switch for specific signal"""
    try:
        signal_name = request.POST.get('signal_name')
        reason = request.POST.get('reason', 'Manual restore via dashboard')
        
        if not signal_name:
            messages.error(request, 'Signal name is required')
            return redirect('governance:payroll_signal_dashboard')
        
        success = payroll_signal_governance.deactivate_kill_switch(
            signal_name, request.user, reason
        )
        
        if success:
            messages.success(request, f'Kill switch deactivated for {signal_name}')
        else:
            messages.error(request, f'Failed to deactivate kill switch for {signal_name}')
            
    except Exception as e:
        messages.error(request, f'Error deactivating kill switch: {str(e)}')
    
    return redirect('governance:payroll_signal_dashboard')


@login_required
@user_passes_test(is_superuser)
@require_http_methods(["POST"])
def promote_signal(request):
    """Promote signal rollout to higher percentage"""
    try:
        signal_name = request.POST.get('signal_name')
        target_percentage = request.POST.get('target_percentage')
        
        if not signal_name:
            messages.error(request, 'Signal name is required')
            return redirect('governance:payroll_signal_dashboard')
        
        # Convert percentage to int if provided
        target_percentage = int(target_percentage) if target_percentage else None
        
        success = payroll_signal_governance.promote_signal_rollout(
            signal_name, request.user, target_percentage
        )
        
        if success:
            percentage_text = f' to {target_percentage}%' if target_percentage else ''
            messages.success(request, f'Promoted {signal_name}{percentage_text}')
        else:
            messages.error(request, f'Failed to promote {signal_name} (conditions not met)')
            
    except Exception as e:
        messages.error(request, f'Error promoting signal: {str(e)}')
    
    return redirect('governance:payroll_signal_dashboard')


@login_required
@user_passes_test(is_superuser)
def api_status(request):
    """API endpoint for real-time status updates"""
    try:
        rollout_status = payroll_signal_governance.get_rollout_status()
        health_status = payroll_signal_governance.get_health_status()
        
        return JsonResponse({
            'success': True,
            'rollout_status': rollout_status,
            'health_status': health_status,
            'timestamp': rollout_status.get('timestamp', None)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_superuser)
def api_signal_metrics(request, signal_name):
    """API endpoint for specific signal metrics"""
    try:
        rollout_status = payroll_signal_governance.get_rollout_status()
        
        if signal_name not in rollout_status['signals']:
            return JsonResponse({
                'success': False,
                'error': f'Signal not found: {signal_name}'
            }, status=404)
        
        signal_data = rollout_status['signals'][signal_name]
        
        return JsonResponse({
            'success': True,
            'signal_name': signal_name,
            'signal_data': signal_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


class PayrollSignalControlView(View):
    """
    AJAX view for real-time signal control operations.
    """
    
    @method_decorator(login_required)
    @method_decorator(user_passes_test(is_superuser))
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request):
        """Handle control operations via AJAX"""
        try:
            data = json.loads(request.body)
            action = data.get('action')
            signal_name = data.get('signal_name')
            reason = data.get('reason', 'AJAX control operation')
            
            if action == 'kill_switch':
                success = payroll_signal_governance.activate_kill_switch(
                    signal_name, request.user, reason
                )
                message = f'Kill switch activated for {signal_name}'
                
            elif action == 'restore_switch':
                success = payroll_signal_governance.deactivate_kill_switch(
                    signal_name, request.user, reason
                )
                message = f'Kill switch deactivated for {signal_name}'
                
            elif action == 'promote':
                target_percentage = data.get('target_percentage')
                success = payroll_signal_governance.promote_signal_rollout(
                    signal_name, request.user, target_percentage
                )
                percentage_text = f' to {target_percentage}%' if target_percentage else ''
                message = f'Promoted {signal_name}{percentage_text}'
                
            elif action == 'enable_governance':
                success = payroll_signal_governance.enable_payroll_signal_governance(
                    request.user, reason
                )
                message = 'Payroll signal governance enabled'
                
            elif action == 'disable_governance':
                success = payroll_signal_governance.disable_payroll_signal_governance(
                    request.user, reason
                )
                message = 'Payroll signal governance disabled'
                
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'Unknown action: {action}'
                }, status=400)
            
            if success:
                # Get updated status
                rollout_status = payroll_signal_governance.get_rollout_status()
                
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'rollout_status': rollout_status
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'Operation failed: {action}'
                }, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data'
            }, status=400)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


# URL patterns for the dashboard
from django.urls import path

app_name = 'governance'

urlpatterns = [
    path('payroll-signals/', payroll_signal_dashboard, name='payroll_signal_dashboard'),
    path('payroll-signals/enable/', enable_governance, name='enable_payroll_governance'),
    path('payroll-signals/disable/', disable_governance, name='disable_payroll_governance'),
    path('payroll-signals/kill-switch/', activate_kill_switch, name='activate_kill_switch'),
    path('payroll-signals/restore-switch/', deactivate_kill_switch, name='deactivate_kill_switch'),
    path('payroll-signals/promote/', promote_signal, name='promote_signal'),
    path('payroll-signals/api/status/', api_status, name='api_payroll_status'),
    path('payroll-signals/api/signal/<str:signal_name>/', api_signal_metrics, name='api_signal_metrics'),
    path('payroll-signals/control/', PayrollSignalControlView.as_view(), name='payroll_signal_control'),
]