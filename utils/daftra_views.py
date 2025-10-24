# -*- coding: utf-8 -*-
"""
مزامنة Daftra API
مزامنة العملاء والموردين مع نظام دفترة
"""

import os
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from .daftra_sync import DaftraSync


@csrf_exempt
@require_http_methods(["POST"])
def sync_clients(request):
    """مزامنة العملاء مع Daftra"""
    try:
        syncer = DaftraSync()
        stats = syncer.sync_clients(user=request.user if request.user.is_authenticated else None)
        
        return JsonResponse({
            'success': True,
            'message': f'تمت المزامنة بنجاح! ✅',
            'stats': {
                'created': stats['created'],
                'updated': stats['updated'],
                'skipped': stats['skipped'],
                'errors': stats['errors'],
            },
            'details': stats['details']
        })
        
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في الإعدادات: {str(e)}',
            'error': str(e)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في المزامنة: {str(e)}',
            'error': str(e)
        })


@csrf_exempt
@require_http_methods(["POST"])
def sync_suppliers(request):
    """مزامنة الموردين مع Daftra"""
    try:
        syncer = DaftraSync()
        stats = syncer.sync_suppliers(user=request.user if request.user.is_authenticated else None)
        
        return JsonResponse({
            'success': True,
            'message': f'تمت المزامنة بنجاح! ✅',
            'stats': {
                'created': stats['created'],
                'updated': stats['updated'],
                'skipped': stats['skipped'],
                'errors': stats['errors'],
            },
            'details': stats['details']
        })
        
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في الإعدادات: {str(e)}',
            'error': str(e)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في المزامنة: {str(e)}',
            'error': str(e)
        })
