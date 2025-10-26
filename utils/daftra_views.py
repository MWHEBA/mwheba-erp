# -*- coding: utf-8 -*-
"""
مزامنة Daftra API
مزامنة العملاء والموردين مع نظام دفترة
"""

import os
import json
import logging
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from .daftra_sync import DaftraSync

logger = logging.getLogger(__name__)


def sync_progress_generator(sync_type='clients', user=None):
    """مولد التقدم المباشر للمزامنة"""
    try:
        syncer = DaftraSync()
        
        # جلب البيانات من Daftra
        yield json.dumps({
            'type': 'status',
            'message': 'جاري جلب البيانات من دفترة...',
            'progress': 5
        }) + '\n'
        
        if sync_type == 'clients':
            daftra_items = syncer.fetch_all_clients()
        else:
            daftra_items = syncer.fetch_all_suppliers()
        
        total = len(daftra_items)
        
        yield json.dumps({
            'type': 'status',
            'message': f'تم جلب {total} سجل من دفترة',
            'progress': 10,
            'total': total
        }) + '\n'
        
        # معالجة كل سجل
        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'details': []
        }
        
        for index, item in enumerate(daftra_items, 1):
            # حساب التقدم (من 10% إلى 95%)
            progress = 10 + int((index / total) * 85)
            
            try:
                if sync_type == 'clients':
                    result = syncer._process_single_client(item, user, stats)
                else:
                    result = syncer._process_single_supplier(item, user, stats)
                
                # إرسال تحديث التقدم
                yield json.dumps({
                    'type': 'progress',
                    'current': index,
                    'total': total,
                    'progress': progress,
                    'stats': {
                        'created': stats['created'],
                        'updated': stats['updated'],
                        'skipped': stats['skipped'],
                        'errors': stats['errors']
                    }
                }) + '\n'
                
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"خطأ في معالجة السجل {index}: {str(e)}")
        
        # إرسال النتيجة النهائية
        yield json.dumps({
            'type': 'complete',
            'progress': 100,
            'message': 'تمت المزامنة! ✅',
            'stats': stats,
            'error_samples': [d for d in stats['details'] if d.get('action') == 'error'][:5]
        }) + '\n'
        
    except Exception as e:
        logger.exception(f"خطأ في مزامنة {sync_type}")
        yield json.dumps({
            'type': 'error',
            'message': f'خطأ في المزامنة: {str(e)}'
        }) + '\n'


@csrf_exempt
@require_http_methods(["POST"])
def sync_clients(request):
    """مزامنة العملاء مع Daftra - مع تقدم مباشر"""
    user = request.user if request.user.is_authenticated else None
    
    response = StreamingHttpResponse(
        sync_progress_generator('clients', user),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    
    return response


@csrf_exempt
@require_http_methods(["POST"])
def sync_suppliers(request):
    """مزامنة الموردين مع Daftra - مع تقدم مباشر"""
    user = request.user if request.user.is_authenticated else None
    
    response = StreamingHttpResponse(
        sync_progress_generator('suppliers', user),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    
    return response


@csrf_exempt
@require_http_methods(["POST"])
def sync_suppliers_old(request):
    """مزامنة الموردين مع Daftra (النسخة القديمة)"""
    try:
        syncer = DaftraSync()
        stats = syncer.sync_suppliers(user=request.user if request.user.is_authenticated else None)
        
        # تسجيل الأخطاء
        if stats['errors'] > 0:
            error_details = [d for d in stats['details'] if d.get('action') == 'error']
            logger.error(f"أخطاء في مزامنة الموردين: {stats['errors']} خطأ")
            for error in error_details[:5]:  # أول 5 أخطاء
                logger.error(f"  - {error.get('name')}: {error.get('reason')}")
        
        return JsonResponse({
            'success': True,
            'message': f'تمت المزامنة! ✅',
            'stats': {
                'created': stats['created'],
                'updated': stats['updated'],
                'skipped': stats['skipped'],
                'errors': stats['errors'],
            },
            'details': stats['details'][:10],  # أول 10 تفاصيل فقط
            'error_samples': [d for d in stats['details'] if d.get('action') == 'error'][:5]
        })
        
    except ValueError as e:
        logger.error(f"خطأ في إعدادات Daftra: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'خطأ في الإعدادات: {str(e)}',
            'error': str(e)
        })
    except Exception as e:
        logger.exception("خطأ غير متوقع في مزامنة الموردين")
        return JsonResponse({
            'success': False,
            'message': f'خطأ في المزامنة: {str(e)}',
            'error': str(e)
        })
