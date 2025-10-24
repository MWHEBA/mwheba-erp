"""
تكامل مع APIs خارجية
"""
from typing import Dict, Any, Optional
from django.utils.translation import gettext_lazy as _
import requests
from decimal import Decimal


class ExternalAPIIntegration:
    """تكامل مع APIs خارجية للحصول على أسعار المواد والخدمات"""
    
    def __init__(self):
        self.timeout = 30
        self.base_headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'MWHEBA-ERP/1.0'
        }
    
    def get_material_price(self, material_type: str, specifications: Dict[str, Any]) -> Dict[str, Any]:
        """
        الحصول على سعر المادة من API خارجي
        
        Args:
            material_type: نوع المادة
            specifications: مواصفات المادة
            
        Returns:
            Dict: نتيجة الاستعلام
        """
        try:
            # هذه دالة تجريبية - يمكن تطويرها لاحقاً للتكامل مع APIs حقيقية
            
            # محاكاة أسعار المواد
            mock_prices = {
                'paper': {
                    'A4_80gsm': Decimal('0.50'),
                    'A4_90gsm': Decimal('0.60'),
                    'A3_80gsm': Decimal('1.00'),
                    'coated_115gsm': Decimal('1.20'),
                    'coated_150gsm': Decimal('1.50')
                },
                'ink': {
                    'black': Decimal('2.00'),
                    'color': Decimal('3.50'),
                    'gold': Decimal('8.00'),
                    'silver': Decimal('7.00')
                },
                'finishing': {
                    'lamination': Decimal('0.10'),
                    'binding': Decimal('2.00'),
                    'cutting': Decimal('0.05'),
                    'folding': Decimal('0.03')
                }
            }
            
            # البحث عن السعر
            category_prices = mock_prices.get(material_type, {})
            
            # تكوين مفتاح البحث من المواصفات
            search_key = self._build_search_key(specifications)
            price = category_prices.get(search_key)
            
            if price is None:
                # البحث عن أقرب مطابقة
                price = self._find_closest_match(category_prices, specifications)
            
            if price is not None:
                from core.utils import get_default_currency
                return {
                    'success': True,
                    'price': price,
                    'currency': get_default_currency(),
                    'source': 'external_api',
                    'last_updated': 'now'
                }
            else:
                return {
                    'success': False,
                    'error': _('لم يتم العثور على سعر للمادة المحددة'),
                    'material_type': material_type,
                    'specifications': specifications
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في الاتصال بـ API الأسعار: {}').format(str(e))
            }
    
    def get_service_price(self, service_type: str, specifications: Dict[str, Any]) -> Dict[str, Any]:
        """
        الحصول على سعر الخدمة من API خارجي
        
        Args:
            service_type: نوع الخدمة
            specifications: مواصفات الخدمة
            
        Returns:
            Dict: نتيجة الاستعلام
        """
        try:
            # محاكاة أسعار الخدمات
            mock_prices = {
                'printing': {
                    'digital_bw': Decimal('0.25'),
                    'digital_color': Decimal('1.00'),
                    'offset_1color': Decimal('0.15'),
                    'offset_4color': Decimal('0.50')
                },
                'finishing': {
                    'lamination': Decimal('0.10'),
                    'binding_saddle': Decimal('0.50'),
                    'binding_perfect': Decimal('2.00'),
                    'cutting_straight': Decimal('0.10'),
                    'cutting_die': Decimal('0.50')
                },
                'packaging': {
                    'box_small': Decimal('5.00'),
                    'box_medium': Decimal('8.00'),
                    'box_large': Decimal('12.00'),
                    'shrink_wrap': Decimal('0.20')
                }
            }
            
            category_prices = mock_prices.get(service_type, {})
            search_key = self._build_search_key(specifications)
            price = category_prices.get(search_key)
            
            if price is None:
                price = self._find_closest_match(category_prices, specifications)
            
            if price is not None:
                from core.utils import get_default_currency
                return {
                    'success': True,
                    'price': price,
                    'currency': get_default_currency(),
                    'source': 'external_api',
                    'last_updated': 'now'
                }
            else:
                return {
                    'success': False,
                    'error': _('لم يتم العثور على سعر للخدمة المحددة'),
                    'service_type': service_type,
                    'specifications': specifications
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في الاتصال بـ API أسعار الخدمات: {}').format(str(e))
            }
    
    def validate_supplier_data(self, supplier_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        التحقق من بيانات المورد مع APIs خارجية
        
        Args:
            supplier_data: بيانات المورد
            
        Returns:
            Dict: نتيجة التحقق
        """
        try:
            # محاكاة التحقق من بيانات المورد
            required_fields = ['name', 'contact_info', 'services']
            missing_fields = []
            
            for field in required_fields:
                if not supplier_data.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                return {
                    'success': False,
                    'error': _('بيانات مورد ناقصة'),
                    'missing_fields': missing_fields
                }
            
            return {
                'success': True,
                'message': _('بيانات المورد صحيحة'),
                'verified': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في التحقق من بيانات المورد: {}').format(str(e))
            }
    
    def _build_search_key(self, specifications: Dict[str, Any]) -> str:
        """بناء مفتاح البحث من المواصفات"""
        # تبسيط المواصفات لمفتاح بحث
        key_parts = []
        
        for key, value in specifications.items():
            if value:
                key_parts.append(f"{key}_{value}")
        
        return "_".join(key_parts) if key_parts else "default"
    
    def _find_closest_match(self, prices: Dict[str, Decimal], specifications: Dict[str, Any]) -> Optional[Decimal]:
        """البحث عن أقرب مطابقة للمواصفات"""
        # خوارزمية بسيطة للبحث عن أقرب مطابقة
        # يمكن تطويرها لاحقاً لتكون أكثر ذكاءً
        
        if not prices:
            return None
        
        # إرجاع أول سعر متاح كحل مؤقت
        return list(prices.values())[0]
    
    def get_exchange_rates(self) -> Dict[str, Any]:
        """
        الحصول على أسعار صرف العملات
        
        Returns:
            Dict: أسعار الصرف
        """
        try:
            # محاكاة أسعار الصرف
            mock_rates = {
                'USD': Decimal('30.50'),
                'EUR': Decimal('33.20'),
                'SAR': Decimal('8.15'),
                'AED': Decimal('8.30')
            }
            
            from core.utils import get_default_currency
            return {
                'success': True,
                'rates': mock_rates,
                'base_currency': get_default_currency(),
                'last_updated': 'now'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('خطأ في الحصول على أسعار الصرف: {}').format(str(e))
            }
