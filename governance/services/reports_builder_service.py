"""
Reports Builder Service
خدمة بناء وتنفيذ التقارير المخصصة
"""

from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from django.apps import apps
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ReportsBuilderService:
    """
    خدمة بناء وتنفيذ التقارير المخصصة
    """
    
    # Data source configurations
    DATA_SOURCE_CONFIG = {
        'customers': {
            'model': 'client.Customer',
            'fields': {
                'name': {'label': 'اسم العميل', 'type': 'text'},
                'code': {'label': 'كود العميل', 'type': 'text'},
                'company_name': {'label': 'اسم الشركة', 'type': 'text'},
                'phone': {'label': 'الهاتف', 'type': 'text'},
                'email': {'label': 'البريد الإلكتروني', 'type': 'text'},
                'address': {'label': 'العنوان', 'type': 'text'},
                'city': {'label': 'المدينة', 'type': 'text'},
                'client_type': {'label': 'نوع العميل', 'type': 'text'},
                'balance': {'label': 'الرصيد', 'type': 'number'},
                'credit_limit': {'label': 'حد الائتمان', 'type': 'number'},
                'is_active': {'label': 'نشط', 'type': 'boolean'},
            }
        },
        'sales': {
            'model': 'sale.Sale',
            'fields': {
                'number': {'label': 'رقم الفاتورة', 'type': 'text'},
                'customer__name': {'label': 'اسم العميل', 'type': 'text'},
                'date': {'label': 'التاريخ', 'type': 'date'},
                'subtotal': {'label': 'المجموع الفرعي', 'type': 'number'},
                'discount': {'label': 'الخصم', 'type': 'number'},
                'tax': {'label': 'الضريبة', 'type': 'number'},
                'total': {'label': 'الإجمالي', 'type': 'number'},
                'status': {'label': 'الحالة', 'type': 'text'},
                'payment_status': {'label': 'حالة الدفع', 'type': 'text'},
            }
        },
        'purchases': {
            'model': 'purchase.Purchase',
            'fields': {
                'number': {'label': 'رقم الفاتورة', 'type': 'text'},
                'supplier__name': {'label': 'اسم المورد', 'type': 'text'},
                'date': {'label': 'التاريخ', 'type': 'date'},
                'subtotal': {'label': 'المجموع الفرعي', 'type': 'number'},
                'discount': {'label': 'الخصم', 'type': 'number'},
                'tax': {'label': 'الضريبة', 'type': 'number'},
                'total': {'label': 'الإجمالي', 'type': 'number'},
                'status': {'label': 'الحالة', 'type': 'text'},
                'payment_status': {'label': 'حالة الدفع', 'type': 'text'},
            }
        },
        'payments': {
            'model': 'client.CustomerPayment',
            'fields': {
                'customer__name': {'label': 'اسم العميل', 'type': 'text'},
                'amount': {'label': 'المبلغ', 'type': 'number'},
                'payment_date': {'label': 'تاريخ الدفع', 'type': 'date'},
                'payment_method': {'label': 'طريقة الدفع', 'type': 'text'},
                'status': {'label': 'الحالة', 'type': 'text'},
                'notes': {'label': 'ملاحظات', 'type': 'text'},
            }
        },
        'employees': {
            'model': 'hr.Employee',
            'fields': {
                'name': {'label': 'الاسم', 'type': 'text'},
                'employee_number': {'label': 'رقم الموظف', 'type': 'text'},
                'department__name_ar': {'label': 'القسم', 'type': 'text'},
                'job_title__title_ar': {'label': 'المسمى الوظيفي', 'type': 'text'},
                'hire_date': {'label': 'تاريخ التعيين', 'type': 'date'},
                'employment_type': {'label': 'نوع التوظيف', 'type': 'text'},
                'status': {'label': 'الحالة', 'type': 'text'},
                'gender': {'label': 'النوع', 'type': 'text'},
            }
        },
        'journal_entries': {
            'model': 'financial.JournalEntry',
            'fields': {
                'number': {'label': 'رقم القيد', 'type': 'text'},
                'date': {'label': 'التاريخ', 'type': 'date'},
                'description': {'label': 'الوصف', 'type': 'text'},
                'entry_type': {'label': 'نوع القيد', 'type': 'text'},
                'status': {'label': 'الحالة', 'type': 'text'},
                'reference': {'label': 'المرجع', 'type': 'text'},
                'created_at': {'label': 'تاريخ الإنشاء', 'type': 'date'},
            }
        },
        'products': {
            'model': 'product.Product',
            'fields': {
                'name': {'label': 'اسم المنتج', 'type': 'text'},
                'sku': {'label': 'الكود', 'type': 'text'},
                'category__name': {'label': 'الفئة', 'type': 'text'},
                'selling_price': {'label': 'سعر البيع', 'type': 'number'},
                'cost_price': {'label': 'سعر التكلفة', 'type': 'number'},
                'is_active': {'label': 'نشط', 'type': 'boolean'},
                'is_service': {'label': 'خدمة', 'type': 'boolean'},
                'created_at': {'label': 'تاريخ الإنشاء', 'type': 'date'},
            }
        },
        'suppliers': {
            'model': 'supplier.Supplier',
            'fields': {
                'name': {'label': 'اسم المورد', 'type': 'text'},
                'code': {'label': 'الكود', 'type': 'text'},
                'phone': {'label': 'الهاتف', 'type': 'text'},
                'email': {'label': 'البريد الإلكتروني', 'type': 'text'},
                'address': {'label': 'العنوان', 'type': 'text'},
                'balance': {'label': 'الرصيد', 'type': 'number'},
                'is_active': {'label': 'نشط', 'type': 'boolean'},
            }
        },
    }
    
    @classmethod
    def get_available_fields(cls, data_source):
        """
        الحصول على الحقول المتاحة لمصدر بيانات معين
        """
        config = cls.DATA_SOURCE_CONFIG.get(data_source)
        if not config:
            return []
        
        return [
            {'name': field_name, **field_config}
            for field_name, field_config in config['fields'].items()
        ]
    
    @classmethod
    def execute_report(cls, report_config, user=None):
        """
        تنفيذ تقرير
        
        Args:
            report_config: dict with keys: data_source, selected_fields, filters, group_by, sort_by, sort_order
            user: User object (for permission checks)
        
        Returns:
            dict with keys: success, data, rows_count, error
        """
        from governance.models import ReportExecution
        
        try:
            data_source = report_config.get('data_source')
            selected_fields = report_config.get('selected_fields', [])
            filters = report_config.get('filters', [])  # Can be list or dict
            group_by = report_config.get('group_by', '')
            sort_by = report_config.get('sort_by', '')
            sort_order = report_config.get('sort_order', 'asc')
            
            # Get model
            config = cls.DATA_SOURCE_CONFIG.get(data_source)
            if not config:
                return {
                    'success': False,
                    'error': f'مصدر البيانات غير معروف: {data_source}',
                    'data': [],
                    'rows_count': 0
                }
            
            try:
                Model = apps.get_model(config['model'])
            except LookupError:
                return {
                    'success': False,
                    'error': f'النموذج غير موجود: {config["model"]}',
                    'data': [],
                    'rows_count': 0
                }
            
            # Build queryset
            queryset = Model.objects.all()
            
            # Apply filters
            if filters:
                queryset = cls._apply_filters(queryset, filters)
            
            # Select only needed fields
            if selected_fields:
                # Make sure we have valid field names
                valid_fields = [f for f in selected_fields if f in config['fields']]
                if valid_fields:
                    queryset = queryset.values(*valid_fields)
                else:
                    # No valid fields selected, use all available fields
                    queryset = queryset.values(*list(config['fields'].keys()))
            else:
                # No fields selected, use all available fields
                queryset = queryset.values(*list(config['fields'].keys()))
            
            # Apply grouping
            if group_by and group_by in config['fields']:
                queryset = queryset.values(group_by).annotate(count=Count('id'))
            
            # Apply sorting
            if sort_by and sort_by in config['fields']:
                order_field = f"-{sort_by}" if sort_order == 'desc' else sort_by
                queryset = queryset.order_by(order_field)
            
            # Execute query
            data = list(queryset[:1000])  # Limit to 1000 rows for performance
            rows_count = len(data)
            
            # Format data
            formatted_data = cls._format_data(data, config['fields'])
            
            return {
                'success': True,
                'data': formatted_data,
                'rows_count': rows_count,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error executing report: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'rows_count': 0
            }
    
    @classmethod
    def _apply_filters(cls, queryset, filters):
        """
        تطبيق المرشحات على الـ queryset
        """
        q_objects = Q()
        
        for filter_config in filters:
            field = filter_config.get('field')
            operator = filter_config.get('operator')
            value = filter_config.get('value')
            
            if not all([field, operator, value]):
                continue
            
            # Build Q object based on operator
            if operator == 'equals':
                q_objects &= Q(**{field: value})
            elif operator == 'not_equals':
                q_objects &= ~Q(**{field: value})
            elif operator == 'contains':
                q_objects &= Q(**{f"{field}__icontains": value})
            elif operator == 'greater_than':
                q_objects &= Q(**{f"{field}__gt": value})
            elif operator == 'less_than':
                q_objects &= Q(**{f"{field}__lt": value})
            elif operator == 'greater_equal':
                q_objects &= Q(**{f"{field}__gte": value})
            elif operator == 'less_equal':
                q_objects &= Q(**{f"{field}__lte": value})
        
        return queryset.filter(q_objects)
    
    @classmethod
    def _format_data(cls, data, fields_config):
        """
        تنسيق البيانات للعرض
        """
        formatted = []
        
        for row in data:
            formatted_row = {}
            for field_name, value in row.items():
                field_config = fields_config.get(field_name, {})
                field_type = field_config.get('type', 'text')
                
                # Format based on type
                if field_type == 'date' and value:
                    try:
                        if isinstance(value, datetime):
                            formatted_row[field_name] = value.strftime('%Y-%m-%d')
                        else:
                            formatted_row[field_name] = str(value)
                    except Exception:
                        formatted_row[field_name] = str(value) if value is not None else ''
                elif field_type == 'number' and value is not None:
                    try:
                        formatted_row[field_name] = float(value)
                    except (ValueError, TypeError):
                        formatted_row[field_name] = str(value)
                elif field_type == 'boolean':
                    formatted_row[field_name] = bool(value)
                else:
                    formatted_row[field_name] = str(value) if value is not None else ''
            
            formatted.append(formatted_row)
        
        return formatted
    
    @classmethod
    def get_report_statistics(cls):
        """
        الحصول على إحصائيات التقارير
        """
        from governance.models import SavedReport, ReportSchedule, ReportExecution
        
        # Total saved reports
        total_reports = SavedReport.objects.filter(status='ACTIVE').count()
        
        # Scheduled reports
        scheduled_reports = ReportSchedule.objects.filter(status='ACTIVE').count()
        
        # Executions today
        today = timezone.now().date()
        executions_today = ReportExecution.objects.filter(
            started_at__date=today,
            status='SUCCESS'
        ).count()
        
        # Active users (users who created reports)
        active_users = SavedReport.objects.values('created_by').distinct().count()
        
        return {
            'total_reports': total_reports,
            'scheduled_reports': scheduled_reports,
            'executions_today': executions_today,
            'active_users': active_users,
        }
    
    @classmethod
    def get_saved_reports(cls, user=None, include_public=True):
        """
        الحصول على التقارير المحفوظة
        """
        from governance.models import SavedReport
        
        queryset = SavedReport.objects.filter(status='ACTIVE')
        
        if user and not user.is_superuser:
            if include_public:
                queryset = queryset.filter(Q(created_by=user) | Q(is_public=True))
            else:
                queryset = queryset.filter(created_by=user)
        
        return queryset.order_by('-created_at')
    
    @classmethod
    def get_scheduled_reports(cls, user=None):
        """
        الحصول على التقارير المجدولة
        """
        from governance.models import ReportSchedule
        
        queryset = ReportSchedule.objects.select_related('report', 'created_by')
        
        if user and not user.is_superuser:
            queryset = queryset.filter(created_by=user)
        
        return queryset.order_by('next_run_at')
