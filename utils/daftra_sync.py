# -*- coding: utf-8 -*-
"""
نظام مزامنة Daftra
مزامنة ذكية للعملاء والموردين مع كشف التغييرات
"""

import requests
import os
import logging
from decimal import Decimal
from django.db import transaction
from django.conf import settings
from client.models import Customer
from supplier.models import Supplier
from users.models import User
from financial.models import ChartOfAccounts

logger = logging.getLogger('utils.daftra_sync')


class DaftraSync:
    """فئة المزامنة مع Daftra API"""
    
    def __init__(self, domain=None, api_key=None):
        self.domain = domain or os.getenv('DAFTRA_DOMAIN', 'mwheba')
        self.api_key = api_key or os.getenv('DAFTRA_API_KEY', '')
        self.base_url = f'https://{self.domain}.daftra.com/api2'
        
        if not self.api_key:
            raise ValueError('DAFTRA_API_KEY غير موجود في .env')
        
    def get_headers(self):
        """إنشاء headers للـ API"""
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'APIKEY': self.api_key,
        }
    
    def fetch_all_clients(self):
        """جلب جميع العملاء من Daftra"""
        all_clients = []
        page = 1
        
        while True:
            try:
                response = requests.get(
                    f'{self.base_url}/clients',
                    headers=self.get_headers(),
                    params={'limit': 100, 'page': page},
                    timeout=30
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                if data.get('code') != 200:
                    break
                
                items = data.get('data', [])
                if not items:
                    break
                
                all_clients.extend(items)
                
                # التحقق من وجود صفحات إضافية
                pagination = data.get('pagination', {})
                if not pagination.get('next'):
                    break
                
                page += 1
                
            except Exception as e:
                print(f"خطأ في جلب العملاء: {str(e)}")
                break
        
        return all_clients
    
    def fetch_all_suppliers(self):
        """جلب جميع الموردين من Daftra"""
        all_suppliers = []
        page = 1
        
        while True:
            try:
                response = requests.get(
                    f'{self.base_url}/suppliers',
                    headers=self.get_headers(),
                    params={'limit': 100, 'page': page},
                    timeout=30
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                if data.get('code') != 200:
                    break
                
                items = data.get('data', [])
                if not items:
                    break
                
                all_suppliers.extend(items)
                
                # التحقق من وجود صفحات إضافية
                pagination = data.get('pagination', {})
                if not pagination.get('next'):
                    break
                
                page += 1
                
            except Exception as e:
                print(f"خطأ في جلب الموردين: {str(e)}")
                break
        
        return all_suppliers
    
    def compare_client_fields(self, customer, daftra_data, stats=None, force_active=False):
        """مقارنة حقول العميل للكشف عن التغييرات"""
        client = daftra_data.get('Client', {})
        
        # بناء الاسم بذكاء لتجنب التكرار
        business_name = client.get('business_name', '').strip()
        first_name = client.get('first_name', '').strip()
        last_name = client.get('last_name', '').strip()
        
        if business_name:
            # إذا كان هناك اسم شركة، استخدمه كاسم رئيسي
            name = business_name
            company_name = business_name
        else:
            # إذا لم يكن هناك اسم شركة، استخدم الاسم الشخصي
            name = f'{first_name} {last_name}'.strip()
            company_name = ''
        
        # دمج العنوان
        address_parts = []
        if client.get('address1'):
            address_parts.append(client['address1'])
        if client.get('address2'):
            address_parts.append(client['address2'])
        address = '\n'.join(address_parts) if address_parts else ''
        
        # حل جذري: جميع العملاء نشطين دائماً
        is_active_status = True
        
        # تتبع الإحصائيات (مبسط)
        if stats:
            stats.setdefault('active_clients', 0)
            stats['active_clients'] += 1
        
        # بناء البيانات الجديدة
        new_data = {
            'name': name,
            'company_name': company_name,
            'code': str(client.get('client_number', '')).strip(),
            'email': client.get('email', '') or None,
            'phone_primary': client.get('phone1', ''),
            'phone_secondary': client.get('phone2', ''),
            'phone': client.get('phone1', ''),  # استخدام البيانات كما هي
            'address': address,
            'city': client.get('city', ''),
            'credit_limit': Decimal(str(client.get('credit_limit') or 0)),
            'balance': Decimal(str(client.get('starting_balance') or 0)),
            'is_active': is_active_status,  # نشط إذا لم يكن معلق في دفترة
        }
        
        # مقارنة شاملة للعملاء الموجودين
        if customer:
            fields_match = (
                customer.name == name and
                customer.company_name == company_name and
                customer.code == str(client.get('client_number', '')).strip() and
                customer.email == (client.get('email', '') or None) and
                customer.phone_primary == client.get('phone1', '') and
                customer.phone_secondary == client.get('phone2', '') and
                customer.phone == client.get('phone1', '') and
                customer.address == address and
                customer.city == client.get('city', '') and
                customer.credit_limit == Decimal(str(client.get('credit_limit') or 0)) and
                customer.balance == Decimal(str(client.get('starting_balance') or 0)) and
                customer.is_active == True  # دائماً نشط
            )
        else:
            fields_match = False
        
        return fields_match, new_data
    
    def compare_supplier_fields(self, supplier, daftra_data, stats=None):
        """مقارنة حقول المورد - محسن للسرعة"""
        supp = daftra_data.get('Supplier', {})
        
        # بناء الاسم
        name = supp.get('business_name', '').strip()
        if not name:
            first_name = supp.get('first_name', '').strip()
            last_name = supp.get('last_name', '').strip()
            name = f'{first_name} {last_name}'.strip()
        
        # دمج العنوان
        address_parts = []
        if supp.get('address1'):
            address_parts.append(supp['address1'])
        if supp.get('address2'):
            address_parts.append(supp['address2'])
        address = '\n'.join(address_parts) if address_parts else ''
        
        # حل جذري: جميع الموردين نشطين دائماً
        is_active_status = True
        
        # تتبع الإحصائيات (مبسط)
        if stats:
            stats.setdefault('active_suppliers', 0)
            stats['active_suppliers'] += 1
        
        # بناء البيانات الجديدة
        new_data = {
            'name': name,
            'code': str(supp.get('supplier_number', '')).strip(),
            'email': supp.get('email', ''),
            'phone': str(supp.get('phone1', '') or '')[:17],
            'secondary_phone': str(supp.get('phone2', '') or '')[:17],
            'address': address,
            'city': supp.get('city', ''),
            'is_active': is_active_status,  # ✅ جميع الموردين نشطين دائماً
        }
        
        # مقارنة شاملة للموردين الموجودين
        if supplier:
            fields_match = (
                supplier.name == name and
                supplier.code == str(supp.get('supplier_number', '')).strip() and
                supplier.email == supp.get('email', '') and
                supplier.phone == supp.get('phone1', '') and
                supplier.secondary_phone == supp.get('phone2', '') and
                supplier.address == address and
                supplier.city == supp.get('city', '') and
                supplier.is_active == True  # دائماً نشط
            )
        else:
            fields_match = False
        
        return fields_match, new_data
    
    def _process_single_client(self, item, user, stats, force_active=False):
        """معالجة عميل واحد - محسن للسرعة"""
        client_data = item.get('Client', {})
        client_number = str(client_data.get('client_number', '')).strip()
        
        if not client_number:
            stats['skipped'] += 1
            return
        
        # البحث عن العميل بالكود
        existing = Customer.objects.filter(code=client_number).first()
        
        if existing:
            # مقارنة الحقول
            fields_match, new_data = self.compare_client_fields(existing, item, stats, force_active)
            
            if fields_match:
                stats['skipped'] += 1
            else:
                # طباعة سبب عدم التطابق (للتشخيص)
                if not hasattr(self, '_debug_printed'):
                    self._debug_printed = 0
                if self._debug_printed < 3:  # أول 3 عملاء فقط
                    print(f"🔍 عميل يحتاج تحديث: {existing.name}")
                    if existing.name != new_data['name']:
                        print(f"   - الاسم: '{existing.name}' → '{new_data['name']}'")
                    if existing.company_name != new_data['company_name']:
                        print(f"   - الشركة: '{existing.company_name}' → '{new_data['company_name']}'")
                    if existing.email != new_data['email']:
                        print(f"   - الإيميل: '{existing.email}' → '{new_data['email']}'")
                    if existing.phone_primary != new_data['phone_primary']:
                        print(f"   - الهاتف: '{existing.phone_primary}' → '{new_data['phone_primary']}'")
                    if existing.address != new_data['address']:
                        print(f"   - العنوان: '{existing.address}' → '{new_data['address']}'")
                    if existing.credit_limit != new_data['credit_limit']:
                        print(f"   - الحد الائتماني: {existing.credit_limit} → {new_data['credit_limit']}")
                    if existing.balance != new_data['balance']:
                        print(f"   - الرصيد: {existing.balance} → {new_data['balance']}")
                    self._debug_printed += 1
                
                # تحديث سريع
                for key, value in new_data.items():
                    setattr(existing, key, value)
                existing.save()
                stats['updated'] += 1
        else:
            # إنشاء عميل جديد
            _, new_data = self.compare_client_fields(None, item, stats, force_active)
            new_data['created_by'] = user
            
            # إعداد سريع للعميل الجديد
            new_data['client_type'] = 'individual'  # افتراضي للسرعة
            
            # إنشاء العميل بدون حساب مالي (للسرعة)
            try:
                customer = Customer.objects.create(**new_data)
                stats['created'] += 1
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"[Daftra] فشل إنشاء عميل [{new_data.get('name')}] كود [{client_number}]: {type(e).__name__}: {e}")
                stats['details'].append({'action': 'error', 'name': new_data.get('name'), 'code': client_number, 'reason': str(e)})
    
    def sync_clients(self, user=None, force_active=False):
        """مزامنة العملاء مع Daftra - محسن للسرعة"""
        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'active_clients': 0
        }
        
        if not user:
            user = User.objects.filter(is_superuser=True).first()
        
        # جلب البيانات من Daftra
        daftra_clients = self.fetch_all_clients()
        
        # معالجة مجمعة للسرعة
        print(f"🚀 بدء معالجة {len(daftra_clients)} عميل...")
        
        for i, item in enumerate(daftra_clients, 1):
            try:
                self._process_single_client(item, user, stats, force_active)
                
                # طباعة التقدم كل 100 عميل
                if i % 100 == 0:
                    print(f"⚡ تمت معالجة {i}/{len(daftra_clients)} عميل...")
                    
            except Exception as e:
                stats['errors'] += 1
                print(f"❌ خطأ في السجل {i}: {str(e)}")
        
        # تقرير مبسط وسريع
        print(f"\n🎉 اكتملت المزامنة!")
        print(f"✅ تم إنشاء: {stats['created']} عميل")
        print(f"🔄 تم تحديث: {stats['updated']} عميل") 
        print(f"⏭️ تم تخطي: {stats['skipped']} عميل")
        print(f"❌ أخطاء: {stats['errors']} عميل")
        print(f"🟢 جميع العملاء نشطين: {stats['active_clients']} عميل")
        print("="*50)
        
        return stats
    
    def fix_duplicate_client_names(self):
        """إصلاح أسماء العملاء المكررة"""
        from client.models import Customer
        from django.db import models
        
        try:
            # البحث عن العملاء الذين لديهم نفس الاسم والشركة
            duplicates = Customer.objects.filter(name=models.F('company_name')).exclude(company_name='')
            count = duplicates.count()
            
            if count > 0:
                print(f"🔧 إصلاح {count} عميل لديهم أسماء مكررة...")
                
                for customer in duplicates:
                    # إذا كان الاسم والشركة متطابقين، اجعل company_name فارغ
                    if customer.name == customer.company_name:
                        customer.company_name = ''
                        customer.save()
                        print(f"✅ تم إصلاح: {customer.name}")
                
                print(f"🎉 تم إصلاح جميع الأسماء المكررة!")
                return {'fixed_count': count}
            else:
                print(f"✅ لا توجد أسماء مكررة!")
                return {'fixed_count': 0}
                
        except Exception as e:
            print(f"❌ خطأ في إصلاح الأسماء: {e}")
            return {'error': str(e)}
    
    def activate_all_existing_clients(self):
        """تفعيل جميع العملاء الموجودين - سريع"""
        from client.models import Customer
        
        try:
            updated = Customer.objects.filter(is_active=False).update(is_active=True)
            print(f"✅ تم تفعيل {updated} عميل")
            return {'activated_count': updated}
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return {'error': str(e)}
    
    def _process_single_supplier(self, item, user, stats):
        """معالجة مورد واحد - محسن للسرعة"""
        supplier_data = item.get('Supplier', {})
        supplier_number = str(supplier_data.get('supplier_number', '')).strip()
        
        if not supplier_number:
            stats['skipped'] += 1
            return
        
        # البحث عن المورد بالكود
        existing = Supplier.objects.filter(code=supplier_number).first()
        
        if existing:
            # مقارنة الحقول
            fields_match, new_data = self.compare_supplier_fields(existing, item, stats)
            
            if fields_match:
                stats['skipped'] += 1
            else:
                # تحديث سريع
                for key, value in new_data.items():
                    setattr(existing, key, value)
                existing.save()
                stats['updated'] += 1
        else:
            # إنشاء مورد جديد
            _, new_data = self.compare_supplier_fields(None, item, stats)
            new_data['created_by'] = user
            
            # تعيين النوع الافتراضي إذا لم يكن موجوداً
            if 'primary_type' not in new_data or not new_data.get('primary_type'):
                from supplier.models import SupplierType
                default_type = SupplierType.objects.first()
                if not default_type:
                    stats['errors'] += 1
                    return
                new_data['primary_type'] = default_type
            
            try:
                supplier = Supplier.objects.create(**new_data)
                stats['created'] += 1
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"[Daftra] فشل إنشاء مورد [{new_data.get('name')}] كود [{supplier_number}]: {type(e).__name__}: {e}")
                stats['details'].append({'action': 'error', 'name': new_data.get('name'), 'code': supplier_number, 'reason': str(e)})
    
    def sync_suppliers(self, user=None):
        """مزامنة الموردين مع Daftra - محسن للسرعة"""
        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'active_suppliers': 0
        }
        
        if not user:
            user = User.objects.filter(is_superuser=True).first()
        
        # جلب البيانات من Daftra
        daftra_suppliers = self.fetch_all_suppliers()
        
        # معالجة مجمعة للسرعة
        print(f"🚀 بدء معالجة {len(daftra_suppliers)} مورد...")
        
        for i, item in enumerate(daftra_suppliers, 1):
            try:
                self._process_single_supplier(item, user, stats)
                
                # طباعة التقدم كل 100 مورد
                if i % 100 == 0:
                    print(f"⚡ تمت معالجة {i}/{len(daftra_suppliers)} مورد...")
                    
            except Exception as e:
                stats['errors'] += 1
                print(f"❌ خطأ في السجل {i}: {str(e)}")
        
        # تقرير مبسط وسريع
        print(f"\n🎉 اكتملت مزامنة الموردين!")
        print(f"✅ تم إنشاء: {stats['created']} مورد")
        print(f"🔄 تم تحديث: {stats['updated']} مورد") 
        print(f"⏭️ تم تخطي: {stats['skipped']} مورد")
        print(f"❌ أخطاء: {stats['errors']} مورد")
        print(f"🟢 جميع الموردين نشطين: {stats['active_suppliers']} مورد")
        print("="*50)
        
        return stats
    
    def activate_all_existing_suppliers(self):
        """تفعيل جميع الموردين الموجودين - سريع"""
        from supplier.models import Supplier
        
        try:
            updated = Supplier.objects.filter(is_active=False).update(is_active=True)
            print(f"✅ تم تفعيل {updated} مورد")
            return {'activated_count': updated}
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return {'error': str(e)}
