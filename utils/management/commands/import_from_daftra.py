# -*- coding: utf-8 -*-
"""
أمر استيراد البيانات من Daftra API
يدعم استيراد العملاء والموردين مع معالجة شاملة للأخطاء
"""

import requests
import time
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from client.models import Customer
from supplier.models import Supplier
from users.models import User


class Command(BaseCommand):
    help = 'استيراد العملاء والموردين من Daftra API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['clients', 'suppliers', 'both'],
            default='both',
            help='نوع البيانات المراد استيرادها'
        )
        parser.add_argument(
            '--api-key',
            type=str,
            help='API Key من Daftra (اختياري - يُقرأ من .env)'
        )
        parser.add_argument(
            '--domain',
            type=str,
            help='نطاق Daftra الخاص بك (اختياري - يُقرأ من .env)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='عدد السجلات في كل صفحة'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='تجربة بدون حفظ فعلي في قاعدة البيانات'
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='تحديث السجلات الموجودة بدلاً من تخطيها'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.update_existing = options['update_existing']
        self.limit = options['limit']

        # قراءة الإعدادات من DB أو من الـ arguments
        try:
            from core.models import SystemSetting
            db_domain = SystemSetting.get_setting('daftra_domain', '')
            db_api_key = SystemSetting.get_setting('daftra_api_key', '')
        except Exception:
            db_domain = ''
            db_api_key = ''

        self.domain = options.get('domain') or db_domain
        self.api_key = options.get('api_key') or db_api_key

        if not self.domain:
            raise CommandError('DAFTRA_DOMAIN غير موجود. أضفه في إعدادات النظام أو استخدم --domain')
        if not self.api_key:
            raise CommandError('DAFTRA_API_KEY غير موجود. أضفه في إعدادات النظام أو استخدم --api-key')
        
        # الحصول على المستخدم الحالي للتسجيل
        self.current_user = User.objects.filter(is_superuser=True).first()
        
        # إحصائيات
        self.stats = {
            'clients_created': 0,
            'clients_updated': 0,
            'clients_skipped': 0,
            'clients_errors': 0,
            'suppliers_created': 0,
            'suppliers_updated': 0,
            'suppliers_skipped': 0,
            'suppliers_errors': 0,
        }

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('🚀 بدء استيراد البيانات من Daftra'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('⚠️  وضع التجربة - لن يتم حفظ البيانات'))
        
        import_type = options['type']
        
        try:
            if import_type in ['clients', 'both']:
                self.stdout.write('\n📋 استيراد العملاء...')
                self.import_clients()
            
            if import_type in ['suppliers', 'both']:
                self.stdout.write('\n📦 استيراد الموردين...')
                self.import_suppliers()
            
            # عرض الإحصائيات النهائية
            self.print_statistics()
            
        except Exception as e:
            raise CommandError(f'خطأ في الاستيراد: {str(e)}')

    def get_api_headers(self):
        """إنشاء headers للـ API"""
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'APIKEY': self.api_key,
        }

    def get_api_url(self, endpoint):
        """بناء URL كامل للـ API"""
        return f'https://{self.domain}.daftra.com/api2/{endpoint}'

    def fetch_data(self, endpoint, params=None):
        """جلب البيانات من Daftra API مع معالجة pagination"""
        all_data = []
        page = 1
        
        if params is None:
            params = {}
        
        params['limit'] = self.limit
        
        while True:
            params['page'] = page
            
            try:
                self.stdout.write(f'  📄 جلب الصفحة {page}...')
                
                response = requests.get(
                    self.get_api_url(endpoint),
                    headers=self.get_api_headers(),
                    params=params,
                    timeout=30
                )
                
                response.raise_for_status()
                data = response.json()
                
                if data.get('code') != 200:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ خطأ من API: {data.get("result", "Unknown error")}')
                    )
                    break
                
                items = data.get('data', [])
                if not items:
                    break
                
                all_data.extend(items)
                self.stdout.write(
                    self.style.SUCCESS(f'  ✅ تم جلب {len(items)} سجل')
                )
                
                # التحقق من وجود صفحات إضافية
                pagination = data.get('pagination', {})
                if not pagination.get('next'):
                    break
                
                page += 1
                time.sleep(0.5)  # تأخير بسيط لتجنب rate limiting
                
            except requests.exceptions.RequestException as e:
                self.stdout.write(
                    self.style.ERROR(f'  ❌ خطأ في الاتصال: {str(e)}')
                )
                break
        
        self.stdout.write(
            self.style.SUCCESS(f'  📊 إجمالي السجلات المجلوبة: {len(all_data)}')
        )
        return all_data

    def import_clients(self):
        """استيراد العملاء من Daftra"""
        clients_data = self.fetch_data('clients')
        
        if not clients_data:
            self.stdout.write(self.style.WARNING('  ⚠️  لا توجد بيانات عملاء'))
            return
        
        self.stdout.write(f'\n  🔄 معالجة {len(clients_data)} عميل...\n')
        
        for item in clients_data:
            client_data = item.get('Client', {})
            self.process_client(client_data)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n  ✅ تم: {self.stats["clients_created"]} جديد | '
                f'{self.stats["clients_updated"]} محدث | '
                f'{self.stats["clients_skipped"]} متخطى | '
                f'{self.stats["clients_errors"]} خطأ'
            )
        )

    def process_client(self, data):
        """معالجة بيانات عميل واحد"""
        try:
            # استخراج البيانات الأساسية
            client_number = str(data.get('client_number', '')).strip()
            if not client_number:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  تخطي عميل بدون رقم: {data.get("business_name")}')
                )
                self.stats['clients_skipped'] += 1
                return
            
            # التحقق من وجود العميل
            existing = Customer.objects.filter(code=client_number).first()
            
            if existing and not self.update_existing:
                self.stdout.write(
                    self.style.WARNING(f'  ⏭️  موجود: {data.get("business_name")} ({client_number})')
                )
                self.stats['clients_skipped'] += 1
                return
            
            # تحضير البيانات
            customer_data = self.map_client_data(data)
            
            if self.dry_run:
                action = 'تحديث' if existing else 'إنشاء'
                self.stdout.write(
                    self.style.SUCCESS(f'  🔍 [تجربة] {action}: {customer_data["name"]} ({client_number})')
                )
                if existing:
                    self.stats['clients_updated'] += 1
                else:
                    self.stats['clients_created'] += 1
                return
            
            # الحفظ الفعلي
            with transaction.atomic():
                if existing:
                    for key, value in customer_data.items():
                        setattr(existing, key, value)
                    existing.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✏️  محدث: {customer_data["name"]} ({client_number})')
                    )
                    self.stats['clients_updated'] += 1
                else:
                    customer = Customer.objects.create(**customer_data)
                    self.stdout.write(
                        self.style.SUCCESS(f'  ➕ جديد: {customer.name} ({client_number})')
                    )
                    self.stats['clients_created'] += 1
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ خطأ في معالجة عميل: {str(e)}')
            )
            self.stats['clients_errors'] += 1

    def map_client_data(self, data):
        """تحويل بيانات Daftra إلى بيانات نموذج Customer"""
        # دمج الاسم الأول والأخير إذا كان business_name فارغ
        name = data.get('business_name', '').strip()
        if not name:
            first_name = data.get('first_name', '').strip()
            last_name = data.get('last_name', '').strip()
            name = f'{first_name} {last_name}'.strip() or 'عميل بدون اسم'
        
        # دمج العنوان
        address_parts = []
        if data.get('address1'):
            address_parts.append(data['address1'])
        if data.get('address2'):
            address_parts.append(data['address2'])
        address = '\n'.join(address_parts) if address_parts else ''
        
        # تحويل suspend إلى is_active (عكسي)
        is_active = not data.get('suspend', False)
        
        # تحويل الرصيد
        balance = Decimal(str(data.get('starting_balance') or 0))
        credit_limit = Decimal(str(data.get('credit_limit') or 0))
        
        # تحديد نوع العميل
        client_type_map = {
            'individual': 'individual',
            'company': 'company',
            'government': 'government',
            'vip': 'vip',
        }
        client_type = client_type_map.get(
            data.get('type', '').lower(), 
            'individual'
        )
        
        return {
            'name': name,
            'company_name': data.get('business_name', ''),
            'code': str(data.get('client_number', '')).strip(),
            'email': data.get('email', ''),
            'phone_primary': data.get('phone1', ''),
            'phone_secondary': data.get('phone2', ''),
            'phone': data.get('phone1', ''),  # للتوافق مع validator
            'address': address,
            'city': data.get('city', ''),
            'balance': balance,
            'credit_limit': credit_limit,
            'is_active': is_active,
            'tax_number': data.get('tax_number', ''),
            'client_type': client_type,
            'notes': data.get('notes', ''),
            'created_by': self.current_user,
        }

    def import_suppliers(self):
        """استيراد الموردين من Daftra"""
        suppliers_data = self.fetch_data('suppliers')
        
        if not suppliers_data:
            self.stdout.write(self.style.WARNING('  ⚠️  لا توجد بيانات موردين'))
            return
        
        self.stdout.write(f'\n  🔄 معالجة {len(suppliers_data)} مورد...\n')
        
        for item in suppliers_data:
            supplier_data = item.get('Supplier', {})
            self.process_supplier(supplier_data)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n  ✅ تم: {self.stats["suppliers_created"]} جديد | '
                f'{self.stats["suppliers_updated"]} محدث | '
                f'{self.stats["suppliers_skipped"]} متخطى | '
                f'{self.stats["suppliers_errors"]} خطأ'
            )
        )

    def process_supplier(self, data):
        """معالجة بيانات مورد واحد"""
        try:
            # استخراج البيانات الأساسية
            supplier_number = str(data.get('supplier_number', '')).strip()
            if not supplier_number:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  تخطي مورد بدون رقم: {data.get("business_name")}')
                )
                self.stats['suppliers_skipped'] += 1
                return
            
            # التحقق من وجود المورد
            existing = Supplier.objects.filter(code=supplier_number).first()
            
            if existing and not self.update_existing:
                self.stdout.write(
                    self.style.WARNING(f'  ⏭️  موجود: {data.get("business_name")} ({supplier_number})')
                )
                self.stats['suppliers_skipped'] += 1
                return
            
            # تحضير البيانات
            supplier_data = self.map_supplier_data(data)
            
            if self.dry_run:
                action = 'تحديث' if existing else 'إنشاء'
                self.stdout.write(
                    self.style.SUCCESS(f'  🔍 [تجربة] {action}: {supplier_data["name"]} ({supplier_number})')
                )
                if existing:
                    self.stats['suppliers_updated'] += 1
                else:
                    self.stats['suppliers_created'] += 1
                return
            
            # الحفظ الفعلي
            with transaction.atomic():
                if existing:
                    for key, value in supplier_data.items():
                        setattr(existing, key, value)
                    existing.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✏️  محدث: {supplier_data["name"]} ({supplier_number})')
                    )
                    self.stats['suppliers_updated'] += 1
                else:
                    supplier = Supplier.objects.create(**supplier_data)
                    self.stdout.write(
                        self.style.SUCCESS(f'  ➕ جديد: {supplier.name} ({supplier_number})')
                    )
                    self.stats['suppliers_created'] += 1
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ خطأ في معالجة مورد: {str(e)}')
            )
            self.stats['suppliers_errors'] += 1

    def map_supplier_data(self, data):
        """تحويل بيانات Daftra إلى بيانات نموذج Supplier"""
        # دمج الاسم الأول والأخير إذا كان business_name فارغ
        name = data.get('business_name', '').strip()
        if not name:
            first_name = data.get('first_name', '').strip()
            last_name = data.get('last_name', '').strip()
            name = f'{first_name} {last_name}'.strip() or 'مورد بدون اسم'
        
        # دمج العنوان
        address_parts = []
        if data.get('address1'):
            address_parts.append(data['address1'])
        if data.get('address2'):
            address_parts.append(data['address2'])
        address = '\n'.join(address_parts) if address_parts else ''
        
        # تحويل suspend إلى is_active (عكسي)
        is_active = not data.get('suspend', False)
        
        return {
            'name': name,
            'code': str(data.get('supplier_number', '')).strip(),
            'email': data.get('email', ''),
            'phone': data.get('phone1', ''),
            'secondary_phone': data.get('phone2', ''),
            'address': address,
            'city': data.get('city', ''),
            'country': data.get('country_code', 'مصر'),
            'is_active': is_active,
            'contact_person': f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
            'created_by': self.current_user,
        }

    def print_statistics(self):
        """عرض إحصائيات الاستيراد"""
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('📊 إحصائيات الاستيراد'))
        self.stdout.write('=' * 60)
        
        # إحصائيات العملاء
        if any([
            self.stats['clients_created'],
            self.stats['clients_updated'],
            self.stats['clients_skipped'],
            self.stats['clients_errors']
        ]):
            self.stdout.write('\n👥 العملاء:')
            self.stdout.write(f"  ➕ جديد: {self.stats['clients_created']}")
            self.stdout.write(f"  ✏️  محدث: {self.stats['clients_updated']}")
            self.stdout.write(f"  ⏭️  متخطى: {self.stats['clients_skipped']}")
            if self.stats['clients_errors'] > 0:
                self.stdout.write(
                    self.style.ERROR(f"  ❌ أخطاء: {self.stats['clients_errors']}")
                )
        
        # إحصائيات الموردين
        if any([
            self.stats['suppliers_created'],
            self.stats['suppliers_updated'],
            self.stats['suppliers_skipped'],
            self.stats['suppliers_errors']
        ]):
            self.stdout.write('\n📦 الموردين:')
            self.stdout.write(f"  ➕ جديد: {self.stats['suppliers_created']}")
            self.stdout.write(f"  ✏️  محدث: {self.stats['suppliers_updated']}")
            self.stdout.write(f"  ⏭️  متخطى: {self.stats['suppliers_skipped']}")
            if self.stats['suppliers_errors'] > 0:
                self.stdout.write(
                    self.style.ERROR(f"  ❌ أخطاء: {self.stats['suppliers_errors']}")
                )
        
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('✅ اكتمل الاستيراد بنجاح!'))
        self.stdout.write('=' * 60 + '\n')
