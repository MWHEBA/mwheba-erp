"""
Bridge Agent API - استقبال البيانات من أجهزة البصمة
"""
from .base_imports import *
from ..models import BiometricDevice, BiometricLog, BiometricSyncLog, Employee
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from dateutil import parser
import hmac
import random
import logging

logger = logging.getLogger(__name__)

__all__ = [
    'BridgeSyncThrottle',
    'biometric_bridge_sync',
]


class BridgeSyncThrottle(AnonRateThrottle):
    """Rate limiting for Bridge Agent API"""
    rate = '100/hour'  # 100 requests per hour

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([BridgeSyncThrottle])
def biometric_bridge_sync(request):
    """
    API لاستقبال البيانات من Bridge Agent
    """
    # Logging بدلاً من print
    logger.info("=" * 60)
    logger.info("Bridge Sync Request Received!")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Data: {request.data}")
    logger.info("=" * 60)
    
    # التحقق من Agent Code و Secret
    auth_header = request.headers.get('Authorization', '')
    agent_code = request.data.get('agent_code')
    
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Invalid authorization header'}, status=401)
    
    agent_secret = auth_header.replace('Bearer ', '')
    
    # التحقق من Agent (يمكن تخزين الـ Agents في قاعدة البيانات)
    # هنا نستخدم إعدادات بسيطة
    valid_agents = getattr(settings, 'BRIDGE_AGENTS', {})
    
    # Debug logging
    logger.info(f"Agent Code: {agent_code}")
    logger.info(f"Agent Secret Received: {agent_secret}")
    logger.info(f"Valid Agents: {valid_agents}")
    
    if agent_code not in valid_agents:
        logger.error(f"Agent code '{agent_code}' not found in valid agents")
        return Response({'error': 'Invalid agent credentials'}, status=401)
    
    expected_secret = valid_agents[agent_code]
    # استخدام hmac.compare_digest لمنع timing attacks
    if not hmac.compare_digest(expected_secret, agent_secret):
        logger.error(f"Secret mismatch!")
        logger.error(f"  Agent Code: {agent_code}")
        return Response({'error': 'Invalid agent credentials'}, status=401)
    
    # جلب السجلات
    records = request.data.get('records', [])
    
    # البحث عن الماكينة المرتبطة بالـ Agent
    try:
        device = BiometricDevice.objects.get(device_code=agent_code)
    except BiometricDevice.DoesNotExist:
        return Response({'error': 'Device not found for this agent'}, status=404)
    
    # تحديث last_connection حتى لو مافيش سجلات (heartbeat)
    device.last_connection = timezone.now()
    device.status = 'active'
    
    # تنظيف السجلات القديمة (أقدم من 30 يوم) - مرة واحدة كل 100 مزامنة
    if random.randint(1, 100) == 1:
        try:
            deleted = BiometricSyncLog.cleanup_old_logs(days=30)
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old sync logs")
        except Exception as e:
            logger.warning(f"Failed to cleanup old logs: {e}")
    
    # إنشاء سجل المزامنة
    sync_log = BiometricSyncLog.objects.create(
        device=device,
        started_at=timezone.now(),
        status='success',  # سيتم تحديثه لاحقاً
        records_fetched=len(records)
    )
    
    # لو مافيش سجلات، نرجع heartbeat response
    if not records:
        device.save()
        sync_log.completed_at = timezone.now()
        sync_log.status = 'success'
        sync_log.save()
        logger.info(f"Heartbeat received from {agent_code} - No records")
        return Response({
            'success': True,
            'message': 'Heartbeat received - No new records',
            'processed': 0,
            'skipped': 0,
            'total': 0
        })
    
    # معالجة السجلات
    processed = 0
    skipped = 0
    failed = 0
    
    for record in records:
        try:
            user_id = record.get('user_id')
            timestamp_str = record.get('timestamp')
            
            # تحويل التاريخ
            timestamp = parser.parse(timestamp_str)
            
            # تحديد نوع البصمة من بيانات الجهاز
            punch = record.get('punch')
            status_val = record.get('status')
            
            # تحديد log_type بناءً على punch أو status
            log_type = 'check_in'  # افتراضي
            if punch is not None:
                punch_map = {
                    0: 'check_in',
                    1: 'check_out',
                    2: 'break_start',
                    3: 'break_end'
                }
                log_type = punch_map.get(punch, 'check_in')
            elif status_val is not None:
                status_map = {
                    0: 'check_in',
                    1: 'check_out',
                    2: 'break_start',
                    3: 'break_end'
                }
                log_type = status_map.get(status_val, 'check_in')
            
            # محاولة ربط بالموظف
            employee = None
            try:
                employee = Employee.objects.get(employee_number=user_id)
            except Employee.DoesNotExist:
                pass
            
            # استخدام get_or_create لمنع race condition
            log, created = BiometricLog.objects.get_or_create(
                device=device,
                user_id=user_id,
                timestamp=timestamp,
                defaults={
                    'employee': employee,
                    'log_type': log_type,  # ✅ استخدام النوع المحدد من الجهاز
                    'is_processed': False,
                    'raw_data': record
                }
            )
            
            if created:
                processed += 1
            else:
                skipped += 1
                
        except Exception as e:
            logger.error(f"Error processing record: {e}")
            failed += 1
            continue
    
    # تحديث إحصائيات الماكينة
    device.total_records = BiometricLog.objects.filter(device=device).count()
    device.last_sync = timezone.now()
    device.save()
    
    # تحديث سجل المزامنة
    sync_log.completed_at = timezone.now()
    sync_log.records_processed = processed
    sync_log.records_failed = failed
    
    # تحديد حالة المزامنة
    if failed > 0 and processed > 0:
        sync_log.status = 'partial'
    elif failed > 0 and processed == 0:
        sync_log.status = 'failed'
        sync_log.error_message = f'فشلت معالجة {failed} سجل'
    else:
        sync_log.status = 'success'
    
    sync_log.save()
    
    return Response({
        'success': True,
        'message': f'Processed {processed} records',
        'processed': processed,
        'skipped': skipped,
        'total': len(records)
    })
