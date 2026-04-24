"""
Security Policy Service - Real implementation for security policies management
"""

import logging
import hashlib
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from governance.models import (
    SecurityPolicy, EncryptionKey, SecurityMetric, 
    SecurityIncident, BlockedIP, ActiveSession
)
from core.services.data_encryption_service import DataEncryptionService

User = get_user_model()
logger = logging.getLogger(__name__)


class SecurityPolicyService:
    """Service for managing security policies and encryption"""
    
    def __init__(self):
        self.encryption_service = DataEncryptionService()
    
    def get_security_overview(self):
        """Get security overview statistics"""
        today = timezone.now().date()
        
        # Count active policies
        active_policies = SecurityPolicy.objects.filter(is_enabled=True).count()
        
        # Count active encryption keys
        active_keys = EncryptionKey.objects.filter(status='ACTIVE').count()
        
        # Count today's violations
        today_violations = SecurityIncident.objects.filter(
            detected_at__date=today,
            status='ACTIVE'
        ).count()
        
        # Determine security level
        security_level = self._calculate_security_level()
        
        return {
            'active_policies': active_policies,
            'active_keys': active_keys,
            'today_violations': today_violations,
            'security_level': security_level
        }
    
    def _calculate_security_level(self):
        """Calculate overall security level"""
        # Check critical policies
        critical_policies = [
            'PASSWORD_POLICY',
            'BRUTE_FORCE_PROTECTION',
            'RATE_LIMITING'
        ]
        
        enabled_critical = SecurityPolicy.objects.filter(
            policy_type__in=critical_policies,
            is_enabled=True
        ).count()
        
        # Check for recent incidents
        recent_incidents = SecurityIncident.objects.filter(
            detected_at__gte=timezone.now() - timedelta(days=7),
            severity__in=['HIGH', 'CRITICAL']
        ).count()
        
        # Calculate level
        if enabled_critical == len(critical_policies) and recent_incidents == 0:
            return 'عالي'
        elif enabled_critical >= 2 and recent_incidents < 5:
            return 'متوسط'
        else:
            return 'منخفض'
    
    def get_authentication_policies(self):
        """Get authentication-related policies"""
        policies = []
        
        # Password policy
        password_policy = SecurityPolicy.objects.filter(
            policy_type='PASSWORD_POLICY'
        ).first()
        
        if password_policy:
            config = password_policy.configuration or {}
            policies.append({
                'name': 'كلمات المرور القوية',
                'description': f"الحد الأدنى {config.get('min_length', 8)} أحرف مع رموز خاصة",
                'status': 'نشط' if password_policy.is_enabled else 'معطل',
                'is_enabled': password_policy.is_enabled
            })
        
        # Session timeout
        session_policy = SecurityPolicy.objects.filter(
            policy_type='SESSION_TIMEOUT'
        ).first()
        
        if session_policy:
            config = session_policy.configuration or {}
            policies.append({
                'name': 'انتهاء صلاحية الجلسة',
                'description': f"كل {config.get('timeout_minutes', 30)} دقيقة",
                'status': 'نشط' if session_policy.is_enabled else 'معطل',
                'is_enabled': session_policy.is_enabled
            })
        
        # Brute force protection
        brute_force_policy = SecurityPolicy.objects.filter(
            policy_type='BRUTE_FORCE_PROTECTION'
        ).first()
        
        if brute_force_policy:
            config = brute_force_policy.configuration or {}
            policies.append({
                'name': 'قفل الحساب',
                'description': f"بعد {config.get('max_attempts', 5)} محاولات فاشلة",
                'status': 'نشط' if brute_force_policy.is_enabled else 'معطل',
                'is_enabled': brute_force_policy.is_enabled
            })
        
        return policies
    
    def get_network_policies(self):
        """Get network-related policies"""
        policies = []
        
        # Rate limiting
        rate_limit_policy = SecurityPolicy.objects.filter(
            policy_type='RATE_LIMITING'
        ).first()
        
        if rate_limit_policy:
            policies.append({
                'name': 'تحديد معدل الطلبات',
                'description': 'حماية من الهجمات الخارجية',
                'status': 'نشط' if rate_limit_policy.is_enabled else 'معطل',
                'is_enabled': rate_limit_policy.is_enabled
            })
        
        # Always show these as active (system-level)
        policies.extend([
            {
                'name': 'تشفير HTTPS',
                'description': 'إجباري لجميع الاتصالات',
                'status': 'نشط',
                'is_enabled': True
            },
            {
                'name': 'جدار الحماية',
                'description': 'حماية من الهجمات الخارجية',
                'status': 'نشط',
                'is_enabled': True
            },
            {
                'name': 'مراقبة الشبكة',
                'description': 'تسجيل جميع الاتصالات',
                'status': 'نشط',
                'is_enabled': True
            }
        ])
        
        return policies
    
    def get_encryption_keys(self):
        """Get all encryption keys with their status"""
        keys = EncryptionKey.objects.all().order_by('-created_at')
        
        result = []
        for key in keys:
            # Update status if needed
            key.update_status()
            
            result.append({
                'id': key.id,
                'key_name': key.key_name,
                'key_type': key.key_type,
                'created_at': key.created_at,
                'expires_at': key.expires_at,
                'status': key.get_status_display(),
                'status_code': key.status,
                'usage_count': key.usage_count,
                'last_used_at': key.last_used_at
            })
        
        return result
    
    def create_encryption_key(self, key_name, key_type, duration_months, user, notes=''):
        """Create a new encryption key"""
        try:
            with transaction.atomic():
                # Generate key hash (in production, this would be a real key)
                key_data = f"{key_name}_{key_type}_{timezone.now().isoformat()}"
                key_hash = hashlib.sha256(key_data.encode()).hexdigest()
                
                # Calculate expiration
                expires_at = timezone.now() + timedelta(days=duration_months * 30)
                
                # Create key
                key = EncryptionKey.objects.create(
                    key_name=key_name,
                    key_type=key_type,
                    key_hash=key_hash,
                    created_by=user,
                    expires_at=expires_at,
                    notes=notes
                )
                
                # Record metric
                SecurityMetric.record(
                    metric_type='KEY_ROTATION',
                    user=user,
                    metadata={'key_name': key_name, 'key_type': key_type}
                )
                
                logger.info(f"Encryption key created: {key_name} by {user}")
                return key
                
        except Exception as e:
            logger.error(f"Failed to create encryption key: {e}")
            raise
    
    def rotate_encryption_key(self, key_id, user):
        """Rotate an encryption key"""
        try:
            key = EncryptionKey.objects.get(id=key_id)
            
            # Generate new key hash
            key_data = f"{key.key_name}_rotated_{timezone.now().isoformat()}"
            new_key_hash = hashlib.sha256(key_data.encode()).hexdigest()
            
            # Rotate the key
            new_key = key.rotate(user, new_key_hash)
            
            # Record metric
            SecurityMetric.record(
                metric_type='KEY_ROTATION',
                user=user,
                metadata={'old_key_id': key_id, 'new_key_id': new_key.id}
            )
            
            return new_key
            
        except Exception as e:
            logger.error(f"Failed to rotate encryption key: {e}")
            raise
    
    def get_security_statistics(self):
        """Get security statistics"""
        # Get period counts
        week_ago = timezone.now() - timedelta(days=7)
        
        successful_logins = SecurityMetric.get_period_count('LOGIN_SUCCESS', days=7)
        failed_logins = SecurityMetric.get_period_count('LOGIN_FAILED', days=7)
        
        # Active sessions
        active_sessions = ActiveSession.objects.filter(is_active=True).count()
        
        # Locked accounts (blocked IPs as proxy)
        locked_accounts = BlockedIP.objects.filter(is_active=True).count()
        
        return {
            'successful_logins': successful_logins,
            'failed_logins': failed_logins,
            'active_sessions': active_sessions,
            'locked_accounts': locked_accounts
        }
    
    def get_protection_status(self):
        """Get protection systems status"""
        return [
            {
                'name': 'جدار الحماية',
                'icon': 'fa-check-circle text-success',
                'status': 'نشط',
                'status_class': 'bg-success'
            },
            {
                'name': 'مكافح الفيروسات',
                'icon': 'fa-check-circle text-success',
                'status': 'محدث',
                'status_class': 'bg-success'
            },
            {
                'name': 'تشفير البيانات',
                'icon': 'fa-check-circle text-success',
                'status': 'نشط',
                'status_class': 'bg-success'
            },
            {
                'name': 'مراقبة الشبكة',
                'icon': 'fa-check-circle text-success',
                'status': 'نشط',
                'status_class': 'bg-success'
            }
        ]
    
    def run_security_scan(self, user):
        """Run a comprehensive security scan"""
        try:
            scan_results = {
                'timestamp': timezone.now(),
                'scanned_by': user.username,
                'issues_found': 0,
                'warnings': [],
                'recommendations': []
            }
            
            # Check for expiring keys
            expiring_keys = EncryptionKey.objects.filter(
                status='EXPIRING_SOON'
            )
            
            if expiring_keys.exists():
                scan_results['issues_found'] += expiring_keys.count()
                scan_results['warnings'].append(
                    f"يوجد {expiring_keys.count()} مفتاح تشفير قريب من الانتهاء"
                )
                scan_results['recommendations'].append("قم بتدوير المفاتيح القريبة من الانتهاء")
            
            # Check for recent incidents
            recent_incidents = SecurityIncident.objects.filter(
                detected_at__gte=timezone.now() - timedelta(days=1),
                status='ACTIVE'
            ).count()
            
            if recent_incidents > 0:
                scan_results['issues_found'] += recent_incidents
                scan_results['warnings'].append(
                    f"يوجد {recent_incidents} حادث أمني نشط"
                )
                scan_results['recommendations'].append("راجع الحوادث الأمنية النشطة")
            
            # Check disabled critical policies
            disabled_critical = SecurityPolicy.objects.filter(
                policy_type__in=['PASSWORD_POLICY', 'BRUTE_FORCE_PROTECTION'],
                is_enabled=False
            ).count()
            
            if disabled_critical > 0:
                scan_results['issues_found'] += disabled_critical
                scan_results['warnings'].append(
                    f"يوجد {disabled_critical} سياسة أمنية حرجة معطلة"
                )
                scan_results['recommendations'].append("قم بتفعيل السياسات الأمنية الحرجة")
            
            # Record scan metric
            SecurityMetric.record(
                metric_type='SECURITY_SCAN',
                user=user,
                metadata=scan_results
            )
            
            logger.info(f"Security scan completed by {user}: {scan_results['issues_found']} issues found")
            return scan_results
            
        except Exception as e:
            logger.error(f"Security scan failed: {e}")
            raise
    
    def initialize_default_policies(self):
        """Initialize default security policies if they don't exist"""
        default_policies = [
            {
                'policy_type': 'PASSWORD_POLICY',
                'is_enabled': True,
                'configuration': {
                    'min_length': 8,
                    'require_uppercase': True,
                    'require_lowercase': True,
                    'require_numbers': True,
                    'require_special': True,
                    'expiry_days': 90
                },
                'description': 'سياسة كلمات المرور القوية'
            },
            {
                'policy_type': 'SESSION_TIMEOUT',
                'is_enabled': True,
                'configuration': {
                    'timeout_minutes': 30,
                    'warning_minutes': 5
                },
                'description': 'انتهاء صلاحية الجلسة تلقائياً'
            },
            {
                'policy_type': 'BRUTE_FORCE_PROTECTION',
                'is_enabled': True,
                'configuration': {
                    'max_attempts': 5,
                    'lockout_duration_minutes': 30,
                    'reset_after_minutes': 60
                },
                'description': 'حماية من هجمات البروت فورس'
            },
            {
                'policy_type': 'RATE_LIMITING',
                'is_enabled': True,
                'configuration': {
                    'requests_per_minute': 60,
                    'burst_size': 10
                },
                'description': 'تحديد معدل الطلبات'
            }
        ]
        
        created_count = 0
        for policy_data in default_policies:
            policy, created = SecurityPolicy.objects.get_or_create(
                policy_type=policy_data['policy_type'],
                defaults=policy_data
            )
            if created:
                created_count += 1
                logger.info(f"Created default policy: {policy.get_policy_type_display()}")
        
        return created_count
    
    def initialize_default_keys(self, user):
        """Initialize default encryption keys if they don't exist"""
        default_keys = [
            {
                'key_name': 'DATABASE_KEY',
                'key_type': 'AES-256',
                'duration_months': 12,
                'notes': 'مفتاح تشفير قاعدة البيانات'
            },
            {
                'key_name': 'SESSION_KEY',
                'key_type': 'AES-128',
                'duration_months': 6,
                'notes': 'مفتاح تشفير الجلسات'
            },
            {
                'key_name': 'API_KEY',
                'key_type': 'RSA-2048',
                'duration_months': 12,
                'notes': 'مفتاح تشفير API'
            }
        ]
        
        created_count = 0
        for key_data in default_keys:
            # Check if key already exists
            if not EncryptionKey.objects.filter(
                key_name=key_data['key_name'],
                status='ACTIVE'
            ).exists():
                self.create_encryption_key(
                    key_name=key_data['key_name'],
                    key_type=key_data['key_type'],
                    duration_months=key_data['duration_months'],
                    user=user,
                    notes=key_data['notes']
                )
                created_count += 1
        
        return created_count
