"""
خدمة الاتصال بماكينات البصمة ZKTeco
"""
from datetime import datetime
import socket
from django.conf import settings


class ZKTecoService:
    """
    خدمة الاتصال بماكينات ZKTeco
    
    الحلول المتاحة للـ Dynamic IP:
    
    1. DHCP Reservation (الأفضل):
       - تثبيت IP من الراوتر
       
    2. Dynamic DNS:
       - استخدام No-IP أو DuckDNS
       - Port Forwarding من الراوتر
       
    3. Local Bridge Server:
       - سيرفر محلي يعمل كـ Bridge
       - يرسل البيانات للسيرفر الرئيسي
    """
    
    @staticmethod
    def connect_via_local_ip(ip_address, port=4370):
        """
        الاتصال المباشر (للشبكة المحلية فقط)
        """
        try:
            from zk import ZK
            
            conn = ZK(ip_address, port=port, timeout=5, password=0)
            zk = conn.connect()
            
            return {
                'success': True,
                'connection': zk,
                'message': 'تم الاتصال بنجاح'
            }
        except Exception as e:
            return {
                'success': False,
                'connection': None,
                'message': f'فشل الاتصال: {str(e)}'
            }
    
    @staticmethod
    def connect_via_ddns(domain, port=4370):
        """
        الاتصال عبر Dynamic DNS
        مثال: mydevice.ddns.net:4370
        """
        try:
            from zk import ZK
            
            # حل الـ Domain للحصول على IP الحالي
            ip_address = socket.gethostbyname(domain)
            
            conn = ZK(ip_address, port=port, timeout=5)
            zk = conn.connect()
            
            return {
                'success': True,
                'connection': zk,
                'resolved_ip': ip_address,
                'message': 'تم الاتصال بنجاح'
            }
        except Exception as e:
            return {
                'success': False,
                'connection': None,
                'message': f'فشل الاتصال: {str(e)}'
            }
    
    @staticmethod
    def get_users(connection):
        """جلب قائمة المستخدمين"""
        try:
            users = connection.get_users()
            return {
                'success': True,
                'users': users,
                'count': len(users)
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def get_attendance_records(connection, from_date=None):
        """جلب سجلات الحضور"""
        try:
            attendances = connection.get_attendance()
            
            # فلترة حسب التاريخ
            if from_date:
                attendances = [
                    att for att in attendances 
                    if att.timestamp >= from_date
                ]
            
            return {
                'success': True,
                'records': attendances,
                'count': len(attendances)
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def sync_device_to_database(device, connection):
        """
        مزامنة بيانات الماكينة مع قاعدة البيانات
        """
        from ..models import BiometricLog, BiometricSyncLog
        from django.utils import timezone
        
        sync_log = BiometricSyncLog.objects.create(
            device=device,
            started_at=timezone.now(),
            status='success'
        )
        
        try:
            # جلب السجلات
            result = ZKTecoService.get_attendance_records(connection)
            
            if not result['success']:
                sync_log.status = 'failed'
                sync_log.error_message = result['error']
                sync_log.completed_at = timezone.now()
                sync_log.save()
                return result
            
            records = result['records']
            sync_log.records_fetched = len(records)
            
            # حفظ السجلات
            processed = 0
            failed = 0
            
            for record in records:
                try:
                    # استخدام get_or_create لمنع race condition
                    log, created = BiometricLog.objects.get_or_create(
                        device=device,
                        user_id=str(record.user_id),
                        timestamp=record.timestamp,
                        defaults={
                            'log_type': 'check_in',
                            'is_processed': False,
                            'raw_data': {
                                'user_id': record.user_id,
                                'timestamp': str(record.timestamp),
                                'status': record.status if hasattr(record, 'status') else None
                            }
                        }
                    )
                    
                    if created:
                        processed += 1
                except Exception as e:
                    failed += 1
                    continue
            
            sync_log.records_processed = processed
            sync_log.records_failed = failed
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            # تحديث إحصائيات الماكينة
            device.total_records = BiometricLog.objects.filter(device=device).count()
            device.last_sync = timezone.now()
            device.save()
            
            return {
                'success': True,
                'fetched': len(records),
                'processed': processed,
                'failed': failed
            }
            
        except Exception as e:
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            return {
                'success': False,
                'error': str(e)
            }


class LocalBridgeService:
    """
    خدمة Bridge محلية
    تعمل على جهاز في نفس الشبكة المحلية
    وترسل البيانات للسيرفر الرئيسي عبر API
    """
    
    @staticmethod
    def sync_to_remote_server(device_code, records):
        """
        إرسال السجلات للسيرفر الرئيسي
        """
        import requests
        
        api_url = settings.REMOTE_SERVER_URL + '/api/biometric/sync/'
        api_token = settings.REMOTE_API_TOKEN
        
        try:
            response = requests.post(
                api_url,
                json={
                    'device_code': device_code,
                    'records': records
                },
                headers={
                    'Authorization': f'Token {api_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': 'تم إرسال البيانات بنجاح'
                }
            else:
                return {
                    'success': False,
                    'error': f'خطأ في السيرفر: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
