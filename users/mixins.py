# -*- coding: utf-8 -*-
"""
Smart Permission Mixins for Class-Based Views
"""
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render


class SmartPermissionRequiredMixin(PermissionRequiredMixin):
    """
    CBV Mixin that intelligently checks permissions and handles AJAX requests
    cleanly with JSON 403 responses without crashing front-end JSON parsers.
    """
    def has_permission(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, 'is_admin', False):
            return True
        perms = self.get_permission_required()
        return user.has_perms(perms)

    def handle_no_permission(self):
        request = self.request
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.headers.get('Accept') == 'application/json'
            or getattr(request, 'content_type', '') == 'application/json'
            or request.GET.get('precheck') == '1'
            or request.GET.get('ajax') == '1'
        )
        if not request.user.is_authenticated:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': 'unauthenticated',
                    'message': 'يرجى تسجيل الدخول للمتابعة.'
                }, status=401)
            return super().handle_no_permission()

        perms = self.get_permission_required()
        perm_str = ", ".join(perms) if isinstance(perms, (list, tuple, set)) else str(perms)
        message = f"غير مصرح لك بتنفيذ هذا الإجراء. يتطلب صلاحية: {perm_str}"

        if is_ajax:
            return JsonResponse({
                'success': False,
                'can_delete': False,
                'error': 'permission_denied',
                'message': message
            }, status=403)

        return render(request, 'core/permission_denied.html', {
            'title': 'غير مصرح',
            'message': message
        }, status=403)
