# -*- coding: utf-8 -*-
"""
Product Bulk Import Service
Handles importing products from Excel/CSV files
"""

import logging
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils.text import slugify
import re

logger = logging.getLogger(__name__)


class ProductImportService:
    """
    Service for bulk importing products from Excel/CSV files.
    Supports: name, category, unit, cost_price, selling_price, sku, barcode,
              description, min_stock, is_active, is_service, item_type, initial_quantity
    """

    REQUIRED_COLUMNS = ['name', 'category', 'unit', 'cost_price', 'selling_price']

    COLUMN_ALIASES = {
        'اسم المنتج': 'name',
        'اسم المنتج *': 'name',
        'الاسم': 'name',
        'name': 'name',
        'اسم المنتج بالإنجليزية': 'name_en',
        'اسم المنتج انجليزي': 'name_en',
        'الاسم بالإنجليزية': 'name_en',
        'name_en': 'name_en',
        'english_name': 'name_en',
        'التصنيف': 'category',
        'التصنيف *': 'category',
        'category': 'category',
        'الوحدة': 'unit',
        'وحدة القياس': 'unit',
        'وحدة القياس *': 'unit',
        'unit': 'unit',
        'سعر التكلفة': 'cost_price',
        'سعر التكلفة *': 'cost_price',
        'التكلفة': 'cost_price',
        'cost_price': 'cost_price',
        'سعر البيع': 'selling_price',
        'سعر البيع *': 'selling_price',
        'selling_price': 'selling_price',
        'كود المنتج': 'sku',
        'الكود': 'sku',
        'sku': 'sku',
        'الباركود': 'barcode',
        'barcode': 'barcode',
        'الوصف': 'description',
        'description': 'description',
        'الوصف بالإنجليزية': 'description_en',
        'الوصف انجليزي': 'description_en',
        'description_en': 'description_en',
        'english_description': 'description_en',
        'الحد الأدنى للمخزون': 'min_stock',
        'min_stock': 'min_stock',
        'الكمية': 'initial_quantity',
        'الكمية الافتتاحية': 'initial_quantity',
        'كمية البداية': 'initial_quantity',
        'initial_quantity': 'initial_quantity',
        'نشط': 'is_active',
        'نشط (نعم/لا)': 'is_active',
        'is_active': 'is_active',
        'خدمة': 'is_service',
        'خدمة (نعم/لا)': 'is_service',
        'is_service': 'is_service',
        'نوع المنتج': 'item_type',
        'item_type': 'item_type',
        'سعر البيع دولار': 'price_usd',
        'price_usd': 'price_usd',
        'سعر التكلفة دولار': 'cost_usd',
        'cost_usd': 'cost_usd',
        'سعر البيع يورو': 'price_eur',
        'price_eur': 'price_eur',
        'سعر التكلفة يورو': 'cost_eur',
        'cost_eur': 'cost_eur',
        'سعر البيع ريال': 'price_sar',
        'price_sar': 'price_sar',
        'سعر التكلفة ريال': 'cost_sar',
        'cost_sar': 'cost_sar',
        'نسبة الضريبة': 'tax_rate',
        'الضريبة': 'tax_rate',
        'ضريبة القيمة المضافة': 'tax_rate',
        'tax_rate': 'tax_rate',
        'tax': 'tax_rate',
        'vat': 'tax_rate',
        'معفى': 'is_tax_exempt',
        'معفى من الضريبة': 'is_tax_exempt',
        'is_tax_exempt': 'is_tax_exempt',
    }

    ITEM_TYPE_MAP = {
        'مادة متخصصة': 'educational',
        'educational': 'educational',
        'زي رسمي': 'uniform',
        'uniform': 'uniform',
        'قرطاسية': 'stationery',
        'stationery': 'stationery',
        'نشاط': 'activity',
        'activity': 'activity',
        'مطبخ': 'kitchen',
        'kitchen': 'kitchen',
        'نظافة': 'cleaning',
        'cleaning': 'cleaning',
        'طبي': 'medical',
        'medical': 'medical',
        'عام': 'general',
        'general': 'general',
    }

    def __init__(self, user):
        self.user = user
        self.errors = []
        self.warnings = []
        self.created_count = 0
        self.updated_count = 0
        self.skipped_count = 0

    def import_from_file(self, file, update_existing=False, dry_run=False):
        """
        Main entry point: parse file and import products.
        If dry_run=True, validates and previews without saving anything.
        Returns a result dict with stats and errors.
        """
        try:
            rows = self._parse_file(file)
        except Exception as e:
            return {
                'success': False,
                'error': f'فشل في قراءة الملف: {str(e)}',
                'errors': [],
                'created': 0,
                'updated': 0,
                'skipped': 0,
            }

        if not rows:
            return {
                'success': False,
                'error': 'الملف فارغ أو لا يحتوي على بيانات',
                'errors': [],
                'created': 0,
                'updated': 0,
                'skipped': 0,
            }

        normalized_rows = self._normalize_columns(rows)
        if normalized_rows is None:
            return {
                'success': False,
                'error': f'الأعمدة المطلوبة غير موجودة. الأعمدة المطلوبة: {", ".join(self.REQUIRED_COLUMNS)}',
                'errors': self.errors,
                'created': 0,
                'updated': 0,
                'skipped': 0,
            }

        if dry_run:
            return self._preview_rows(normalized_rows, update_existing)

        row_errors = []
        with transaction.atomic():
            for idx, row in enumerate(normalized_rows, start=2):
                result = self._process_row(idx, row, update_existing)
                if result.get('error'):
                    row_errors.append({'row': idx, 'message': result['error'], 'data': row.get('name', '')})

        return {
            'success': True,
            'created': self.created_count,
            'updated': self.updated_count,
            'skipped': self.skipped_count,
            'errors': row_errors,
            'total_rows': len(normalized_rows),
        }

    def _preview_rows(self, normalized_rows, update_existing):
        """Dry-run: validate each row and return preview data without saving."""
        from product.models import Product, Category, Unit

        preview_rows = []
        valid_count = 0
        error_count = 0
        update_count = 0

        for idx, row in enumerate(normalized_rows, start=2):
            name = row.get('name', '').strip()
            category_name = row.get('category', '').strip()
            unit_name = row.get('unit', '').strip()
            cost_raw = row.get('cost_price', '0')
            sell_raw = row.get('selling_price', '0')
            sku = row.get('sku', '').strip() or ''

            issues = []

            if not name:
                issues.append('اسم المنتج مطلوب')

            category = None
            if not category_name:
                issues.append('التصنيف مطلوب')
            else:
                category = Category.objects.filter(name__iexact=category_name, is_active=True).first()
                if not category:
                    issues.append(f'التصنيف "{category_name}" غير موجود')

            unit = None
            if not unit_name:
                issues.append('وحدة القياس مطلوبة')
            else:
                unit = Unit.objects.filter(name__iexact=unit_name, is_active=True).first()
                if not unit:
                    issues.append(f'وحدة القياس "{unit_name}" غير موجودة')

            try:
                cost_price = Decimal(str(cost_raw).replace(',', ''))
            except InvalidOperation:
                issues.append('سعر التكلفة غير صحيح')
                cost_price = None

            try:
                selling_price = Decimal(str(sell_raw).replace(',', ''))
            except InvalidOperation:
                issues.append('سعر البيع غير صحيح')
                selling_price = None

            initial_qty_raw = row.get('initial_quantity', '0')
            try:
                initial_quantity = int(float(str(initial_qty_raw).replace(',', ''))) if initial_qty_raw else 0
            except (ValueError, TypeError):
                initial_quantity = 0

            action = 'new'
            existing = None
            if not issues:
                if sku:
                    existing = Product.objects.filter(sku=sku).first()
                if not existing and name and category:
                    existing = Product.objects.filter(name__iexact=name, category=category).first()

                if existing:
                    action = 'update' if update_existing else 'skip'

            if issues:
                action = 'error'
                error_count += 1
            elif action == 'new':
                valid_count += 1
            elif action == 'update':
                update_count += 1

            preview_rows.append({
                'row': idx,
                'name': name or '-',
                'category': category_name or '-',
                'unit': unit_name or '-',
                'cost_price': str(cost_price) if cost_price is not None else cost_raw,
                'selling_price': str(selling_price) if selling_price is not None else sell_raw,
                'sku': sku or '(تلقائي)',
                'initial_quantity': initial_quantity,
                'item_type': row.get('item_type', '').strip() or 'general',
                'action': action,
                'issues': issues,
            })

        return {
            'success': True,
            'is_preview': True,
            'preview_rows': preview_rows,
            'valid_count': valid_count,
            'update_count': update_count,
            'error_count': error_count,
            'skip_count': len(preview_rows) - valid_count - update_count - error_count,
            'total_rows': len(normalized_rows),
        }

    def _parse_file(self, file):
        """Parse Excel or CSV file into list of dicts."""
        filename = file.name.lower()
        if filename.endswith('.csv'):
            return self._parse_csv(file)
        elif filename.endswith(('.xlsx', '.xls')):
            return self._parse_excel(file)
        else:
            raise ValueError('صيغة الملف غير مدعومة. يرجى استخدام Excel (.xlsx, .xls) أو CSV')

    def _parse_csv(self, file):
        import csv
        import io
        content = file.read()
        for encoding in ('utf-8-sig', 'utf-8', 'windows-1256', 'cp1256'):
            try:
                text = content.decode(encoding)
                reader = csv.DictReader(io.StringIO(text))
                return [row for row in reader]
            except (UnicodeDecodeError, Exception):
                continue
        raise ValueError('تعذر قراءة ملف CSV - تأكد من الترميز')

    def _parse_excel(self, file):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return []
            headers = [str(h).strip() if h is not None else '' for h in rows[0]]
            result = []
            for row in rows[1:]:
                if all(v is None or str(v).strip() == '' for v in row):
                    continue
                result.append({headers[i]: (str(row[i]).strip() if row[i] is not None else '') for i in range(len(headers))})
            return result
        except ImportError:
            try:
                import xlrd
                wb = xlrd.open_workbook(file_contents=file.read())
                ws = wb.sheet_by_index(0)
                headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
                result = []
                for r in range(1, ws.nrows):
                    row = {headers[c]: str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)}
                    if any(v for v in row.values()):
                        result.append(row)
                return result
            except Exception as e:
                raise ValueError(f'فشل في قراءة ملف Excel: {str(e)}')

    def _normalize_columns(self, rows):
        """Map Arabic/English column names to internal keys."""
        if not rows:
            return None
        sample = rows[0]
        mapping = {}
        for col in sample.keys():
            normalized = col.strip().rstrip('* ').strip()
            if normalized in self.COLUMN_ALIASES:
                mapping[col] = self.COLUMN_ALIASES[normalized]
            else:
                matched = None
                for alias_key, alias_val in self.COLUMN_ALIASES.items():
                    if alias_key in normalized or normalized in alias_key:
                        matched = alias_val
                        break
                mapping[col] = matched if matched else normalized

        mapped_values = set(mapping.values())
        missing = [r for r in self.REQUIRED_COLUMNS if r not in mapped_values]
        if missing:
            self.errors.append(f'أعمدة مفقودة: {", ".join(missing)}')
            return None

        normalized = []
        for row in rows:
            new_row = {}
            for orig_col, val in row.items():
                key = mapping.get(orig_col, orig_col)
                new_row[key] = val
            normalized.append(new_row)
        return normalized

    def _resolve_item_type(self, raw_value):
        """Resolve item_type from Arabic or English value."""
        val = str(raw_value or '').strip().lower()
        return self.ITEM_TYPE_MAP.get(val, self.ITEM_TYPE_MAP.get(raw_value.strip() if raw_value else '', 'general'))

    def _process_row(self, row_num, row, update_existing, warehouse=None):
        """Validate and create/update a single product row."""
        from product.models import Product, Category, Unit

        name = row.get('name', '').strip()
        if not name:
            self.skipped_count += 1
            return {'error': f'السطر {row_num}: اسم المنتج مطلوب'}

        category_name = row.get('category', '').strip()
        if not category_name:
            self.skipped_count += 1
            return {'error': f'السطر {row_num} ({name}): التصنيف مطلوب'}
        category = Category.objects.filter(name__iexact=category_name, is_active=True).first()
        if not category:
            self.skipped_count += 1
            return {'error': f'السطر {row_num} ({name}): التصنيف "{category_name}" غير موجود'}

        unit_name = row.get('unit', '').strip()
        if not unit_name:
            self.skipped_count += 1
            return {'error': f'السطر {row_num} ({name}): وحدة القياس مطلوبة'}
        unit = Unit.objects.filter(name__iexact=unit_name, is_active=True).first()
        if not unit:
            self.skipped_count += 1
            return {'error': f'السطر {row_num} ({name}): وحدة القياس "{unit_name}" غير موجودة'}

        try:
            cost_price = Decimal(str(row.get('cost_price', '0')).replace(',', ''))
        except InvalidOperation:
            self.skipped_count += 1
            return {'error': f'السطر {row_num} ({name}): سعر التكلفة غير صحيح'}

        try:
            selling_price = Decimal(str(row.get('selling_price', '0')).replace(',', ''))
        except InvalidOperation:
            self.skipped_count += 1
            return {'error': f'السطر {row_num} ({name}): سعر البيع غير صحيح'}

        name_en = row.get('name_en', '').strip() or None
        description_en = row.get('description_en', '').strip() or ''

        raw_tax = row.get('tax_rate')
        if raw_tax is not None and str(raw_tax).strip() != '':
            try:
                tax_rate = Decimal(str(raw_tax).replace('%', '').replace(',', '').strip())
            except Exception:
                tax_rate = Decimal('14.00')
        else:
            tax_rate = Decimal('14.00')

        is_tax_exempt = str(row.get('is_tax_exempt', '')).strip().lower() in ['true', 'yes', '1', 'نعم', 'معفى']

        try:
            if existing and update_existing:
                existing.name = name
                if name_en:
                    existing.name_en = name_en
                existing.category = category
                existing.unit = unit
                existing.cost_price = cost_price
                existing.selling_price = selling_price
                existing.description = description
                if description_en:
                    existing.description_en = description_en
                existing.min_stock = min_stock
                existing.is_active = is_active
                existing.is_service = is_service
                existing.item_type = item_type
                existing.tax_rate = tax_rate
                existing.is_tax_exempt = is_tax_exempt
                existing.updated_by = self.user
                if barcode:
                    existing.barcode = barcode
                existing.save()
                self.updated_count += 1

                if initial_quantity > 0 and not is_service:
                    self._update_existing_stock(existing, initial_quantity, cost_price, warehouse=warehouse)
            else:
                if not sku:
                    sku = self._generate_sku(name, category)

                product = Product.objects.create(
                    name=name,
                    name_en=name_en,
                    category=category,
                    unit=unit,
                    cost_price=cost_price,
                    selling_price=selling_price,
                    sku=sku,
                    barcode=barcode,
                    description=description,
                    description_en=description_en,
                    min_stock=min_stock,
                    is_active=is_active,
                    is_service=is_service,
                    item_type=item_type,
                    tax_rate=tax_rate,
                    is_tax_exempt=is_tax_exempt,
                    created_by=self.user,
                )
                self.created_count += 1

            target_product = existing if (existing and update_existing) else product
            if target_product:
                try:
                    from financial.models import Currency
                    from product.services.pricing_service import PricingService
                    for curr_code in ["USD", "EUR", "SAR"]:
                        p_val = row.get(f"price_{curr_code.lower()}")
                        c_val = row.get(f"cost_{curr_code.lower()}")
                        if p_val or c_val:
                            curr = Currency.objects.filter(code=curr_code, is_active=True).first()
                            if curr:
                                try:
                                    s_dec = Decimal(str(p_val).replace(',', '')) if p_val else None
                                    c_dec = Decimal(str(c_val).replace(',', '')) if c_val else None
                                    PricingService.update_currency_price(
                                        product=target_product,
                                        currency=curr,
                                        indicative_selling_price=s_dec,
                                        indicative_cost_price=c_dec,
                                        user=self.user,
                                        notes="استيراد من ملف إكسل"
                                    )
                                except Exception as fx_err:
                                    logger.warning(f"Error updating currency price for {target_product.name} ({curr_code}): {fx_err}")
                except Exception as e:
                    logger.warning(f"Error processing currency import: {e}")

            return {'error': None}

        except Exception as e:
            self.skipped_count += 1
            logger.error(f'Error importing product row {row_num}: {e}')
            return {'error': f'السطر {row_num} ({name}): {str(e)}'}

    def _create_initial_stock(self, product, quantity, cost_price, warehouse=None):
        """Create initial stock record and movement for a newly imported product."""
        from product.models.stock_management import Stock, StockMovement, Warehouse

        if warehouse is None:
            warehouse = Warehouse.objects.filter(is_active=True).first()
        if not warehouse:
            logger.warning(f'No active warehouse found - skipping initial stock for {product.name}')
            return

        stock, _ = Stock.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={'created_by': self.user}
        )
        stock.mark_as_service_approved()
        stock.quantity = quantity
        stock.average_cost = cost_price
        stock.save()

        movement = StockMovement(
            product=product,
            warehouse=warehouse,
            movement_type='in',
            document_type='opening',
            quantity=quantity,
            unit_cost=cost_price,
            quantity_before=0,
            quantity_after=quantity,
            notes='رصيد افتتاحي - استيراد منتجات',
            created_by=self.user,
            created_by_service='ProductImportService',
        )
        movement.mark_as_service_approved()
        movement._skip_update = True
        movement.save()

    def _update_existing_stock(self, product, quantity, cost_price, warehouse=None):
        """Update stock for an existing product during import."""
        from product.models.stock_management import Stock, StockMovement, Warehouse

        if warehouse is None:
            warehouse = Warehouse.objects.filter(is_active=True).first()
        if not warehouse:
            logger.warning(f'No active warehouse — skipping stock update for {product.name}')
            return

        existing_stocks = Stock.objects.filter(product=product, quantity__gt=0).exclude(warehouse=warehouse)
        for old_stock in existing_stocks:
            old_qty = old_stock.quantity
            old_stock.mark_as_service_approved()
            old_stock.quantity = 0
            old_stock.save()

            out_movement = StockMovement(
                product=product,
                warehouse=old_stock.warehouse,
                movement_type='out',
                document_type='adjustment',
                quantity=old_qty,
                unit_cost=old_stock.average_cost,
                quantity_before=old_qty,
                quantity_after=0,
                notes=f'تحويل رصيد إلى {warehouse.name} — استيراد منتجات',
                created_by=self.user,
                created_by_service='ProductImportService',
            )
            out_movement.mark_as_service_approved()
            out_movement._skip_update = True
            out_movement.save()

        target_stock, _ = Stock.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={'created_by': self.user}
        )
        qty_before = target_stock.quantity
        target_stock.mark_as_service_approved()
        target_stock.quantity = quantity
        target_stock.average_cost = cost_price
        target_stock.save()

        in_movement = StockMovement(
            product=product,
            warehouse=warehouse,
            movement_type='in',
            document_type='adjustment',
            quantity=quantity,
            unit_cost=cost_price,
            quantity_before=qty_before,
            quantity_after=quantity,
            notes='تحديث رصيد — استيراد منتجات',
            created_by=self.user,
            created_by_service='ProductImportService',
        )
        in_movement.mark_as_service_approved()
        in_movement._skip_update = True
        in_movement.save()

    def _generate_sku(self, name, category):
        """Generate a unique SKU from product name and category."""
        from product.models import Product
        prefix = (category.code or 'PRD')[:3].upper() if hasattr(category, 'code') and category.code else 'PRD'
        base = re.sub(r'[^a-zA-Z0-9]', '', slugify(name))[:6].upper() or 'ITEM'
        candidate = f'{prefix}-{base}'
        counter = 1
        while Product.objects.filter(sku=candidate).exists():
            candidate = f'{prefix}-{base}-{counter:03d}'
            counter += 1
        return candidate

    def _execute_from_preview(self, preview_rows, update_existing, warehouse_id=None):
        """Execute the actual import using already-validated preview rows."""
        from product.models import Product, Category, Unit
        from product.models.stock_management import Warehouse

        warehouse = None
        if warehouse_id:
            warehouse = Warehouse.objects.filter(pk=warehouse_id, is_active=True).first()
        if warehouse is None:
            warehouse = Warehouse.objects.filter(is_active=True).first()

        row_errors = []
        with transaction.atomic():
            for row in preview_rows:
                if row['action'] not in ('new', 'update'):
                    if row['action'] == 'skip':
                        self.skipped_count += 1
                    continue

                name = row['name']
                category = Category.objects.filter(name__iexact=row['category'], is_active=True).first()
                unit = Unit.objects.filter(name__iexact=row['unit'], is_active=True).first()

                if not category or not unit:
                    self.skipped_count += 1
                    row_errors.append({'row': row['row'], 'message': 'تعذر إيجاد التصنيف أو الوحدة', 'data': name})
                    continue

                try:
                    cost_price = Decimal(str(row['cost_price']).replace(',', ''))
                    selling_price = Decimal(str(row['selling_price']).replace(',', ''))
                except InvalidOperation:
                    self.skipped_count += 1
                    row_errors.append({'row': row['row'], 'message': 'سعر غير صحيح', 'data': name})
                    continue

                sku_val = row['sku'] if row['sku'] != '(تلقائي)' else None
                result = self._process_row(
                    row['row'],
                    {
                        'name': name,
                        'category': row['category'],
                        'unit': row['unit'],
                        'cost_price': str(cost_price),
                        'selling_price': str(selling_price),
                        'sku': sku_val or '',
                        'barcode': '',
                        'description': '',
                        'min_stock': '0',
                        'is_active': 'نعم',
                        'is_service': 'لا',
                        'item_type': row.get('item_type', 'general'),
                        'initial_quantity': str(row.get('initial_quantity', 0)),
                    },
                    update_existing,
                    warehouse=warehouse,
                )
                if result.get('error'):
                    row_errors.append({'row': row['row'], 'message': result['error'], 'data': name})

        return {
            'success': True,
            'created': self.created_count,
            'updated': self.updated_count,
            'skipped': self.skipped_count,
            'errors': row_errors,
            'total_rows': len(preview_rows),
        }

    @staticmethod
    def get_template_arabic_headers():
        return [
            'اسم المنتج *', 'التصنيف *', 'وحدة القياس *', 'سعر التكلفة *', 'سعر البيع *',
            'كود المنتج', 'الباركود', 'الوصف', 'الحد الأدنى للمخزون',
            'نشط (نعم/لا)', 'خدمة (نعم/لا)', 'نوع المنتج', 'الكمية'
        ]
