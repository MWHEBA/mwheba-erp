# -*- coding: utf-8 -*-
"""
أمر إدارة لإعادة حساب مخزون المنتجات المجمعة
Bundle Stock Recalculation Management Command

Requirements: 10.5
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from typing import Dict, List, Any
import logging

from product.models import Product
from product.services.stock_calculation_engine import StockCalculationEngine

logger = logging.getLogger('bundle_system')


class Command(BaseCommand):
    help = 'إعادة حساب مخزون المنتجات المجمعة'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--bundle-id',
            type=int,
            help='إعادة حساب منتج مجمع محدد فقط'
        )
        
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='إعادة حساب المنتجات النشطة فقط'
        )
        
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='حجم الدفعة لمعالجة المنتجات (افتراضي: 50)'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='عرض تفاصيل إضافية'
        )
    
    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        self.verbose = options.get('verbose', False)
        self.bundle_id = options.get('bundle_id')
        self.active_only = options.get('active_only', False)
        self.batch_size = options.get('batch_size', 50)
        
        self.stdout.write(
            self.style.SUCCESS('بدء إعادة حساب مخزون المنتجات المجمعة...')
        )
        
        try:
            # تحديد المنتجات المجمعة للمعالجة
            bundles_query = Product.objects.filter(is_bundle=True)
            
            if self.bundle_id:
                bundles_query = bundles_query.filter(id=self.bundle_id)
                if not bundles_query.exists():
                    raise CommandError(f'المنتج المجمع {self.bundle_id} غير موجود')
            
            if self.active_only:
                bundles_query = bundles_query.filter(is_active=True)
            
            total_bundles = bundles_query.count()
            
            if total_bundles == 0:
                self.stdout.write(
                    self.style.WARNING('لا توجد منتجات مجمعة للمعالجة')
                )
                return
            
            self.stdout.write(f'سيتم معالجة {total_bundles} منتج مجمع...')
            
            # معالجة المنتجات على دفعات
            processed = 0
            errors = 0
            updated_stocks = {}
            
            for i in range(0, total_bundles, self.batch_size):
                batch = bundles_query[i:i + self.batch_size]
                
                for bundle in batch:
                    try:
                        old_stock = getattr(bundle, 'calculated_stock', 0)
                        new_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
                        
                        # تحديث المخزون إذا تغير
                        if hasattr(bundle, 'calculated_stock'):
                            if old_stock != new_stock:
                                bundle.calculated_stock = new_stock
                                bundle.save(update_fields=['calculated_stock'])
                                updated_stocks[bundle.id] = {
                                    'name': bundle.name,
                                    'old_stock': old_stock,
                                    'new_stock': new_stock
                                }
                        
                        processed += 1
                        
                        if self.verbose:
                            self.stdout.write(
                                f'  ✓ {bundle.name}: {new_stock}'
                            )
                        
                    except Exception as e:
                        errors += 1
                        logger.error(f'خطأ في إعادة حساب مخزون {bundle.name}: {str(e)}')
                        self.stdout.write(
                            self.style.ERROR(f'  ❌ خطأ في {bundle.name}: {str(e)}')
                        )
                
                # عرض التقدم
                if self.verbosity >= 1:
                    progress = ((i + self.batch_size) / total_bundles) * 100
                    self.stdout.write(f'التقدم: {min(progress, 100):.1f}%')
            
            # عرض النتائج النهائية
            self.display_results(processed, errors, updated_stocks, total_bundles)
            
        except Exception as e:
            logger.error(f'خطأ في إعادة حساب مخزون المنتجات المجمعة: {str(e)}')
            raise CommandError(f'خطأ في تشغيل الأمر: {str(e)}')
    
    def display_results(self, processed: int, errors: int, updated_stocks: Dict, total: int):
        """عرض نتائج المعالجة"""
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('نتائج إعادة حساب المخزون'))
        self.stdout.write('='*50)
        
        self.stdout.write(f'إجمالي المنتجات: {total}')
        self.stdout.write(f'تم معالجتها بنجاح: {processed}')
        self.stdout.write(f'الأخطاء: {errors}')
        self.stdout.write(f'تم تحديث المخزون: {len(updated_stocks)}')
        
        if updated_stocks and self.verbose:
            self.stdout.write('\nالمنتجات المحدثة:')
            for bundle_id, info in updated_stocks.items():
                self.stdout.write(
                    f'  • {info["name"]}: {info["old_stock"]} → {info["new_stock"]}'
                )
        
        if errors == 0:
            self.stdout.write(
                self.style.SUCCESS('\n✅ تمت العملية بنجاح!')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'\n⚠️ تمت العملية مع {errors} خطأ')
            )
        
        self.stdout.write('='*50)