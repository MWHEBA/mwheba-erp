"""
Bridge Agent API - استقبال ومعالجة البيانات اللحظية من أجهزة وماكينات البصمة
"""
from .base_imports import *
from ..models import BiometricDevice, BiometricLog, BiometricSyncLog, Employee, BiometricUserMapping
from ..utils.biometric_utils import bulk_process_logs
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
from django.utils import timezone
from dateutil import parser
from datetime import timedelta
import hmac
import random
import logging

logger = logging.getLogger(__name__)

__all__ = [
    'BridgeSyncThrottle',
    'BridgeAgentAuthentication',
    'biometric_bridge_sync',
]


class BridgeSyncThrottle(AnonRateThrottle):
    """Rate limiting for Bridge Agent API - Enhanced security"""
    rate = '30/min'


class BridgeAgentAuthentication(BaseAuthentication):
    """
    Custom authentication for Bridge Agent API
    """
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '') or request.META.get('HTTP_AUTHORIZATION', '')
        agent_code = request.data.get('agent_code')

        body_secret = request.data.get('agent_secret', '')

        if not auth_header.startswith('Bearer ') and not body_secret:
            raise AuthenticationFailed('Invalid authorization header format')

        if not agent_code:
            raise AuthenticationFailed('Agent code is required')

        agent_secret = auth_header[7:] if auth_header.startswith('Bearer ') else body_secret
        
        valid_agents = getattr(settings, 'BRIDGE_AGENTS', {})
        
        if agent_code not in valid_agents:
            logger.warning(f"Invalid agent code attempted: {agent_code}")
            raise AuthenticationFailed('Invalid agent credentials')
        
        expected_secret = valid_agents[agent_code]
        
        if not hmac.compare_digest(expected_secret, agent_secret):
            logger.warning(f"Invalid secret for agent: {agent_code}")
            raise AuthenticationFailed('Invalid agent credentials')
        
        class AgentUser:
            def __init__(self, agent_code):
                self.username = f"bridge_agent_{agent_code}"
                self.is_authenticated = True
                
        return (AgentUser(agent_code), agent_code)


def _match_employee_3tier(user_id, device):
    """
    خوارزمية المطابقة الذكية الثلاثية:
    Tier 1: المطابقة عبر كود البصمة المباشر في بطاقة الموظف Employee.biometric_user_id
    Tier 2: المطابقة عبر جدول الربط المخصص BiometricUserMapping
    Tier 3: المطابقة عبر الرقم الوظيفي Employee.employee_number
    """
    user_id_str = str(user_id).strip()

    # Tier 1
    emp = Employee.objects.filter(biometric_user_id=user_id_str).first()
    if emp:
        return emp

    # Tier 2
    mapping = BiometricUserMapping.objects.filter(
        device=device,
        biometric_user_id=user_id_str,
        is_active=True
    ).select_related('employee').first()
    if mapping and mapping.employee:
        return mapping.employee

    global_mapping = BiometricUserMapping.objects.filter(
        device__isnull=True,
        biometric_user_id=user_id_str,
        is_active=True
    ).select_related('employee').first()
    if global_mapping and global_mapping.employee:
        return global_mapping.employee

    # Tier 3
    emp = Employee.objects.filter(employee_number=user_id_str).first()
    if emp:
        return emp

    return None


@api_view(['POST'])
@authentication_classes([BridgeAgentAuthentication])
@permission_classes([AllowAny])
@throttle_classes([BridgeSyncThrottle])
def biometric_bridge_sync(request):
    """
    API لاستقبال ومعالجة البيانات لحظياً من Bridge Agent وماكينات البصمة
    """
    agent_code = request.auth
    records = request.data.get('records', [])
    
    device_identifier = request.data.get('device_code') or agent_code
    try:
        device = BiometricDevice.objects.get(device_code=device_identifier)
    except BiometricDevice.DoesNotExist:
        try:
            device = BiometricDevice.objects.get(id=int(device_identifier))
        except (ValueError, BiometricDevice.DoesNotExist):
            return Response({'error': 'Device not found for this agent'}, status=404)
    
    device.last_connection = timezone.now()
    device.status = 'active'
    
    if random.randint(1, 100) == 1:
        try:
            BiometricSyncLog.cleanup_old_logs(days=30)
        except Exception as e:
            logger.warning(f"Failed to cleanup old logs: {e}")
    
    sync_log = BiometricSyncLog.objects.create(
        device=device,
        started_at=timezone.now(),
        status='success',
        records_fetched=len(records)
    )
    
    if not records:
        device.save()
        sync_log.completed_at = timezone.now()
        sync_log.status = 'success'
        sync_log.save()
        return Response({
            'success': True,
            'message': 'Heartbeat received - No new records',
            'processed': 0,
            'skipped': 0,
            'total': 0
        })
    
    processed = 0
    skipped = 0
    failed = 0
    affected_dates = set()
    
    for record in records:
        try:
            user_id = record.get('user_id')
            timestamp_str = record.get('timestamp')
            
            timestamp = parser.parse(timestamp_str)

            # تطبيق تعويض فارق التوقيت للماكينة (DST / Timezone Drift)
            if device.timezone_offset_hours:
                timestamp = timestamp + timedelta(hours=device.timezone_offset_hours)
            
            punch = record.get('punch')
            status_val = record.get('status')
            
            log_type = 'check_in'
            if punch is not None:
                punch_map = {0: 'check_in', 1: 'check_out', 2: 'break_start', 3: 'break_end'}
                log_type = punch_map.get(punch, 'check_in')
            elif status_val is not None:
                status_map = {0: 'check_in', 1: 'check_out', 2: 'break_start', 3: 'break_end'}
                log_type = status_map.get(status_val, 'check_in')
            
            # المطابقة الثلاثية الذكية
            employee = _match_employee_3tier(user_id, device)

            # نافذة الـ Sliding Debounce (30 ثانية) لتجاهل التكرار السريع
            debounce_start = timestamp - timedelta(seconds=30)
            debounce_end = timestamp + timedelta(seconds=30)
            
            duplicate_exists = BiometricLog.objects.filter(
                device=device,
                user_id=str(user_id),
                timestamp__range=(debounce_start, debounce_end),
                log_type=log_type
            ).exists()

            if duplicate_exists:
                skipped += 1
                continue
            
            log, created = BiometricLog.objects.get_or_create(
                device=device,
                user_id=str(user_id),
                timestamp=timestamp,
                defaults={
                    'employee': employee,
                    'log_type': log_type,
                    'source': 'device',
                    'is_processed': False,
                    'raw_data': record
                }
            )
            
            if created:
                processed += 1
                affected_dates.add(timestamp.date())
            else:
                skipped += 1
                
        except Exception as e:
            logger.error(f"Error processing biometric record: {e}", exc_info=True)
            failed += 1
            continue
    
    device.total_records = BiometricLog.objects.filter(device=device).count()
    device.last_sync = timezone.now()
    device.save()
    
    # المعالجة اللحظية المباشرة لتواريخ البصمات المستلمة
    if affected_dates:
        for dt in affected_dates:
            try:
                bulk_process_logs(date=dt, unprocessed_only=True)
            except Exception as e:
                logger.error(f"Instant auto-processing error for date {dt}: {e}", exc_info=True)

    sync_log.completed_at = timezone.now()
    sync_log.records_processed = processed
    sync_log.records_failed = failed
    
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
        'message': f'Processed {processed} records, skipped {skipped}',
        'processed': processed,
        'skipped': skipped,
        'total': len(records)
    })
