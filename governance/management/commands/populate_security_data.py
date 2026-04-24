from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from governance.models import SecurityIncident, BlockedIP, ActiveSession, SecurityPolicy
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate security data for testing'

    def handle(self, *args, **options):
        self.stdout.write('Creating security test data...')
        
        # Get or create admin user
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.WARNING('No admin user found, skipping...'))
            return
        
        # Create Security Policies
        self.stdout.write('Creating security policies...')
        policies = [
            {
                'policy_type': 'PASSWORD_ENCRYPTION',
                'is_enabled': True,
                'configuration': {'algorithm': 'SHA-256', 'salt_rounds': 12},
                'description': 'تشفير كلمات المرور باستخدام SHA-256'
            },
            {
                'policy_type': 'SESSION_TIMEOUT',
                'is_enabled': True,
                'configuration': {'timeout_minutes': 30},
                'description': 'انتهاء الجلسة بعد 30 دقيقة من عدم النشاط'
            },
            {
                'policy_type': 'BRUTE_FORCE_PROTECTION',
                'is_enabled': True,
                'configuration': {'max_attempts': 5, 'lockout_duration_minutes': 15},
                'description': 'حماية من هجمات البروت فورس - 5 محاولات كحد أقصى'
            },
            {
                'policy_type': 'RATE_LIMITING',
                'is_enabled': True,
                'configuration': {'requests_per_minute': 60},
                'description': 'تحديد معدل الطلبات - 60 طلب في الدقيقة'
            },
        ]
        
        for policy_data in policies:
            policy, created = SecurityPolicy.objects.get_or_create(
                policy_type=policy_data['policy_type'],
                defaults={
                    'is_enabled': policy_data['is_enabled'],
                    'configuration': policy_data['configuration'],
                    'description': policy_data['description'],
                    'updated_by': admin_user
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created policy: {policy.get_policy_type_display()}'))
        
        # Create Security Incidents
        self.stdout.write('Creating security incidents...')
        incident_types = [
            ('FAILED_LOGIN', 'MEDIUM', 'محاولة دخول فاشلة باستخدام بيانات غير صحيحة'),
            ('UNAUTHORIZED_ACCESS', 'HIGH', 'محاولة الوصول إلى صفحة محمية بدون صلاحيات'),
            ('SUSPICIOUS_ACTIVITY', 'MEDIUM', 'نشاط مشبوه - طلبات متكررة من نفس IP'),
            ('BRUTE_FORCE', 'CRITICAL', 'هجوم بروت فورس - محاولات دخول متعددة'),
            ('RATE_LIMIT_EXCEEDED', 'LOW', 'تجاوز حد الطلبات المسموح به'),
        ]
        
        ips = ['192.168.1.150', '10.0.0.25', '172.16.0.100', '192.168.1.200', '10.0.0.50']
        usernames = ['unknown', 'guest_user', 'test_user', 'admin_fake', '']
        
        for i in range(10):
            incident_type, severity, description = random.choice(incident_types)
            ip = random.choice(ips)
            username = random.choice(usernames)
            
            # Random time in last 7 days
            days_ago = random.randint(0, 7)
            hours_ago = random.randint(0, 23)
            detected_time = timezone.now() - timedelta(days=days_ago, hours=hours_ago)
            
            incident = SecurityIncident.objects.create(
                incident_type=incident_type,
                severity=severity,
                status='ACTIVE' if i < 5 else random.choice(['RESOLVED', 'UNDER_REVIEW']),
                ip_address=ip,
                username_attempted=username,
                description=description,
                user_agent=f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/{random.randint(100, 120)}.0',
                request_path=random.choice(['/login/', '/admin/', '/api/data/', '/dashboard/']),
                request_method=random.choice(['GET', 'POST']),
            )
            incident.detected_at = detected_time
            incident.save(update_fields=['detected_at'])
            
            # Resolve some incidents
            if incident.status == 'RESOLVED':
                incident.resolved_at = detected_time + timedelta(hours=random.randint(1, 24))
                incident.resolved_by = admin_user
                incident.resolution_notes = 'تم التحقق والحل'
                incident.save(update_fields=['resolved_at', 'resolved_by', 'resolution_notes'])
            
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created incident: {incident.get_incident_type_display()} - {ip}'))
        
        # Create Blocked IPs
        self.stdout.write('Creating blocked IPs...')
        blocked_ips_data = [
            ('192.168.1.200', 'BRUTE_FORCE', 'محاولات دخول متكررة فاشلة'),
            ('10.0.0.50', 'SUSPICIOUS_ACTIVITY', 'نشاط مشبوه - طلبات غير طبيعية'),
            ('172.16.0.99', 'MANUAL_BLOCK', 'حجب يدوي من قبل المسؤول'),
        ]
        
        for ip, reason, description in blocked_ips_data:
            blocked, created = BlockedIP.objects.get_or_create(
                ip_address=ip,
                defaults={
                    'reason': reason,
                    'description': description,
                    'blocked_by': admin_user,
                    'is_active': True,
                    'attempts_count': random.randint(5, 20)
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Blocked IP: {ip}'))
        
        # Create Active Sessions
        self.stdout.write('Creating active sessions...')
        users = User.objects.filter(is_active=True)[:5]
        session_ips = ['192.168.1.100', '192.168.1.105', '192.168.1.110', '10.0.0.10', '10.0.0.15']
        
        for i, user in enumerate(users):
            if i < len(session_ips):
                session, created = ActiveSession.objects.get_or_create(
                    session_key=f'test_session_{user.id}_{random.randint(1000, 9999)}',
                    defaults={
                        'user': user,
                        'ip_address': session_ips[i],
                        'user_agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/{random.randint(100, 120)}.0',
                        'is_active': True
                    }
                )
                if created:
                    # Set login time to random time in last 24 hours
                    hours_ago = random.randint(0, 24)
                    login_time = timezone.now() - timedelta(hours=hours_ago)
                    session.login_at = login_time
                    session.last_activity = timezone.now() - timedelta(minutes=random.randint(0, 60))
                    session.save(update_fields=['login_at', 'last_activity'])
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Created session: {user.username} - {session_ips[i]}'))
        
        self.stdout.write(self.style.SUCCESS('\n✓ Security data populated successfully!'))
        self.stdout.write(self.style.SUCCESS(f'  - {SecurityPolicy.objects.count()} security policies'))
        self.stdout.write(self.style.SUCCESS(f'  - {SecurityIncident.objects.count()} security incidents'))
        self.stdout.write(self.style.SUCCESS(f'  - {BlockedIP.objects.filter(is_active=True).count()} blocked IPs'))
        self.stdout.write(self.style.SUCCESS(f'  - {ActiveSession.objects.filter(is_active=True).count()} active sessions'))
