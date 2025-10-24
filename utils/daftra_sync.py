# -*- coding: utf-8 -*-
"""
نظام مزامنة Daftra
مزامنة ذكية للعملاء والموردين مع كشف التغييرات
"""

import requests
import os
from decimal import Decimal
from django.db import transaction
from django.conf import settings
from client.models import Customer
from supplier.models import Supplier
from users.models import User


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
    
    def compare_client_fields(self, customer, daftra_data):
        """مقارنة حقول العميل للكشف عن التغييرات"""
        client = daftra_data.get('Client', {})
        
        # بناء الاسم
        name = client.get('business_name', '').strip()
        if not name:
            first_name = client.get('first_name', '').strip()
            last_name = client.get('last_name', '').strip()
            name = f'{first_name} {last_name}'.strip()
        
        # دمج العنوان
        address_parts = []
        if client.get('address1'):
            address_parts.append(client['address1'])
        if client.get('address2'):
            address_parts.append(client['address2'])
        address = '\n'.join(address_parts) if address_parts else ''
        
        # المقارنة
        fields_match = (
            customer.name == name and
            customer.company_name == client.get('business_name', '') and
            customer.code == str(client.get('client_number', '')).strip() and
            customer.email == client.get('email', '') and
            customer.phone_primary == client.get('phone1', '') and
            customer.phone_secondary == client.get('phone2', '') and
            customer.address == address and
            customer.city == client.get('city', '') and
            customer.credit_limit == Decimal(str(client.get('credit_limit') or 0))
        )
        
        return fields_match, {
            'name': name,
            'company_name': client.get('business_name', ''),
            'code': str(client.get('client_number', '')).strip(),
            'email': client.get('email', ''),
            'phone_primary': client.get('phone1', ''),
            'phone_secondary': client.get('phone2', ''),
            'phone': client.get('phone1', ''),
            'address': address,
            'city': client.get('city', ''),
            'credit_limit': Decimal(str(client.get('credit_limit') or 0)),
            'balance': Decimal(str(client.get('starting_balance') or 0)),
        }
    
    def compare_supplier_fields(self, supplier, daftra_data):
        """مقارنة حقول المورد للكشف عن التغييرات"""
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
        
        # المقارنة
        fields_match = (
            supplier.name == name and
            supplier.code == str(supp.get('supplier_number', '')).strip() and
            supplier.email == supp.get('email', '') and
            supplier.phone == supp.get('phone1', '') and
            supplier.secondary_phone == supp.get('phone2', '') and
            supplier.address == address and
            supplier.city == supp.get('city', '')
        )
        
        return fields_match, {
            'name': name,
            'code': str(supp.get('supplier_number', '')).strip(),
            'email': supp.get('email', ''),
            'phone': supp.get('phone1', ''),
            'secondary_phone': supp.get('phone2', ''),
            'address': address,
            'city': supp.get('city', ''),
        }
    
    def sync_clients(self, user=None):
        """مزامنة العملاء مع Daftra"""
        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'details': []
        }
        
        if not user:
            user = User.objects.filter(is_superuser=True).first()
        
        # جلب البيانات من Daftra
        daftra_clients = self.fetch_all_clients()
        
        for item in daftra_clients:
            try:
                client_data = item.get('Client', {})
                daftra_id = client_data.get('id')
                client_number = str(client_data.get('client_number', '')).strip()
                
                if not client_number:
                    stats['skipped'] += 1
                    stats['details'].append({
                        'action': 'skip',
                        'reason': 'لا يوجد رقم عميل',
                        'name': client_data.get('business_name', 'غير معروف')
                    })
                    continue
                
                # البحث عن العميل بالمعرف أو الكود
                existing = Customer.objects.filter(
                    code=client_number
                ).first()
                
                if existing:
                    # مقارنة الحقول
                    fields_match, new_data = self.compare_client_fields(existing, item)
                    
                    if fields_match:
                        # جميع الحقول متطابقة - تخطي
                        stats['skipped'] += 1
                        stats['details'].append({
                            'action': 'skip',
                            'reason': 'البيانات متطابقة',
                            'name': existing.name,
                            'code': client_number
                        })
                    else:
                        # تحديث الحقول المختلفة
                        with transaction.atomic():
                            for key, value in new_data.items():
                                setattr(existing, key, value)
                            existing.save()
                        
                        stats['updated'] += 1
                        stats['details'].append({
                            'action': 'update',
                            'name': new_data['name'],
                            'code': client_number
                        })
                else:
                    # إنشاء عميل جديد
                    _, new_data = self.compare_client_fields(None, item)
                    new_data['created_by'] = user
                    
                    # تحديد نوع العميل
                    client_type_map = {
                        'individual': 'individual',
                        'company': 'company',
                        'government': 'government',
                        'vip': 'vip',
                    }
                    new_data['client_type'] = client_type_map.get(
                        client_data.get('type', '').lower(), 
                        'individual'
                    )
                    new_data['is_active'] = not client_data.get('suspend', False)
                    
                    with transaction.atomic():
                        Customer.objects.create(**new_data)
                    
                    stats['created'] += 1
                    stats['details'].append({
                        'action': 'create',
                        'name': new_data['name'],
                        'code': client_number
                    })
                    
            except Exception as e:
                stats['errors'] += 1
                stats['details'].append({
                    'action': 'error',
                    'reason': str(e),
                    'name': client_data.get('business_name', 'غير معروف')
                })
        
        return stats
    
    def sync_suppliers(self, user=None):
        """مزامنة الموردين مع Daftra"""
        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'details': []
        }
        
        if not user:
            user = User.objects.filter(is_superuser=True).first()
        
        # جلب البيانات من Daftra
        daftra_suppliers = self.fetch_all_suppliers()
        
        for item in daftra_suppliers:
            try:
                supplier_data = item.get('Supplier', {})
                daftra_id = supplier_data.get('id')
                supplier_number = str(supplier_data.get('supplier_number', '')).strip()
                
                if not supplier_number:
                    stats['skipped'] += 1
                    stats['details'].append({
                        'action': 'skip',
                        'reason': 'لا يوجد رقم مورد',
                        'name': supplier_data.get('business_name', 'غير معروف')
                    })
                    continue
                
                # البحث عن المورد بالمعرف أو الكود
                existing = Supplier.objects.filter(
                    code=supplier_number
                ).first()
                
                if existing:
                    # مقارنة الحقول
                    fields_match, new_data = self.compare_supplier_fields(existing, item)
                    
                    if fields_match:
                        # جميع الحقول متطابقة - تخطي
                        stats['skipped'] += 1
                        stats['details'].append({
                            'action': 'skip',
                            'reason': 'البيانات متطابقة',
                            'name': existing.name,
                            'code': supplier_number
                        })
                    else:
                        # تحديث الحقول المختلفة
                        with transaction.atomic():
                            for key, value in new_data.items():
                                setattr(existing, key, value)
                            existing.save()
                        
                        stats['updated'] += 1
                        stats['details'].append({
                            'action': 'update',
                            'name': new_data['name'],
                            'code': supplier_number
                        })
                else:
                    # إنشاء مورد جديد
                    _, new_data = self.compare_supplier_fields(None, item)
                    new_data['created_by'] = user
                    new_data['is_active'] = not supplier_data.get('suspend', False)
                    new_data['country'] = supplier_data.get('country_code', 'مصر')
                    new_data['contact_person'] = f"{supplier_data.get('first_name', '')} {supplier_data.get('last_name', '')}".strip()
                    
                    with transaction.atomic():
                        Supplier.objects.create(**new_data)
                    
                    stats['created'] += 1
                    stats['details'].append({
                        'action': 'create',
                        'name': new_data['name'],
                        'code': supplier_number
                    })
                    
            except Exception as e:
                stats['errors'] += 1
                stats['details'].append({
                    'action': 'error',
                    'reason': str(e),
                    'name': supplier_data.get('business_name', 'غير معروف')
                })
        
        return stats
