"""
Views أدوات الصيانة الإدارية
"""
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.contrib import messages
from ..decorators import hr_manager_required
from ..services.admin_maintenance_service import AdminMaintenanceService
from ..services.component_classification_service import ComponentClassificationService
import json
from datetime import date
from decimal import Decimal


def _serialize_analysis_data(analysis):
    """تحويل بيانات التحليل إلى تنسيق قابل للتسلسل JSON"""
    
    def serialize_component(component):
        """تحويل بند راتب إلى dictionary"""
        if hasattr(component, 'id'):
            return {
                'id': component.id,
                'name': component.name,
                'amount': float(component.amount) if component.amount else 0,
                'component_type': component.component_type,
                'source': getattr(component, 'source', 'unknown'),
                'is_active': component.is_active,
                'effective_from': component.effective_from.isoformat() if component.effective_from else None,
                'effective_to': component.effective_to.isoformat() if component.effective_to else None,
            }
        return component
    
    def serialize_value(value):
        """تحويل القيم إلى تنسيق قابل للتسلسل"""
        if isinstance(value, Decimal):
            return float(value)
        elif hasattr(value, 'id'):  # Django model instance
            if hasattr(value, 'name'):
                return {'id': value.id, 'name': value.name}
            else:
                return {'id': value.id}
        elif isinstance(value, list):
            return [serialize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: serialize_value(v) for k, v in value.items()}
        elif hasattr(value, 'isoformat'):  # datetime objects
            return value.isoformat()
        else:
            return value
    
    # تحويل البيانات
    serialized = {}
    for key, value in analysis.items():
        if key == 'basic_analysis' and isinstance(value, dict):
            # معالجة خاصة للتحليل الأساسي
            serialized[key] = {}
            for sub_key, sub_value in value.items():
                if sub_key in ['transferable_components', 'conflicts', 'recommendations']:
                    # هذه القوائم تحتوي على كائنات
                    if isinstance(sub_value, list):
                        serialized_items = []
                        for item in sub_value:
                            if isinstance(item, dict) and 'component' in item:
                                # معالجة transferable_components التي تحتوي على component
                                serialized_item = item.copy()
                                serialized_item['component'] = serialize_component(item['component'])
                                serialized_items.append(serialized_item)
                            elif hasattr(item, 'id'):
                                # مكون مباشر
                                serialized_items.append(serialize_component(item))
                            else:
                                # كائن آخر
                                serialized_items.append(serialize_value(item))
                        serialized[key][sub_key] = serialized_items
                    else:
                        serialized[key][sub_key] = serialize_value(sub_value)
                elif sub_key == 'classified_components':
                    # معالجة خاصة للبنود المصنفة
                    if isinstance(sub_value, dict):
                        serialized[key][sub_key] = {}
                        for source, components in sub_value.items():
                            if isinstance(components, list):
                                serialized[key][sub_key][source] = [serialize_component(comp) for comp in components]
                            else:
                                serialized[key][sub_key][source] = serialize_value(components)
                    else:
                        serialized[key][sub_key] = serialize_value(sub_value)
                else:
                    serialized[key][sub_key] = serialize_value(sub_value)
        else:
            serialized[key] = serialize_value(value)
    
    return serialized


@login_required
def test_connection_internal(request):
    """صفحة اختبار الاتصال الداخلية"""
    return render(request, 'test_connection_internal.html')


@login_required
@hr_manager_required
def maintenance_dashboard(request):
    """لوحة تحكم الصيانة الإدارية"""
    try:
        # الحصول على نظرة عامة شاملة
        overview = AdminMaintenanceService.get_system_overview()
        
        # تحليل البنود المنتهية (معاينة)
        expired_analysis = AdminMaintenanceService.cleanup_expired_components(dry_run=True)
        
        # تحليل البنود اليتيمة (معاينة)
        orphaned_analysis = AdminMaintenanceService.cleanup_orphaned_components(dry_run=True)
        
        # تحليل التضارب (معاينة)
        inconsistencies_analysis = AdminMaintenanceService.fix_data_inconsistencies(dry_run=True)
        
        # توصيات الصيانة
        recommendations = AdminMaintenanceService._generate_maintenance_recommendations(
            overview, expired_analysis, orphaned_analysis, inconsistencies_analysis
        )
        
        context = {
            'overview': overview,
            'expired_analysis': expired_analysis,
            'orphaned_analysis': orphaned_analysis,
            'inconsistencies_analysis': inconsistencies_analysis,
            'recommendations': recommendations,
            'page_title': 'لوحة تحكم الصيانة الإدارية',
            'page_subtitle': 'إدارة وصيانة بيانات النظام',
            'page_icon': 'fas fa-tools',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': '/core/dashboard/', 'icon': 'fas fa-home'},
                {'title': 'الموارد البشرية', 'url': '/hr/dashboard/', 'icon': 'fas fa-users-cog'},
                {'title': 'الصيانة الإدارية', 'active': True},
            ],
        }
        
        return render(request, 'hr/admin/maintenance_dashboard.html', context)
        
    except Exception as e:
        messages.error(request, f'حدث خطأ في تحميل لوحة التحكم: {str(e)}')
        # إنشاء بيانات افتراضية في حالة الخطأ
        default_overview = {
            'employees': {'total': 0, 'active': 0, 'inactive': 0},
            'contracts': {'total': 0, 'active': 0, 'draft': 0, 'expiring_soon': 0},
            'components': {
                'total': 0, 'active': 0, 'inactive': 0,
                'by_source': {}, 'expiring': 0, 'renewable': 0, 'orphaned': 0
            },
            'data_quality': {
                'duplicate_components': 0, 'inconsistent_records': 0, 'last_cleanup': None
            }
        }
        return render(request, 'hr/admin/maintenance_dashboard.html', {
            'overview': default_overview,
            'expired_analysis': {'total_candidates': 0},
            'orphaned_analysis': {'total_orphaned': 0},
            'inconsistencies_analysis': {'total_fixes': 0},
            'recommendations': [],
            'page_title': 'لوحة تحكم الصيانة الإدارية',
            'page_subtitle': 'إدارة وصيانة بيانات النظام',
            'page_icon': 'fas fa-tools',
        })


@login_required
@hr_manager_required
@require_http_methods(["POST"])
def maintenance_cleanup_expired(request):
    """تنظيف البنود المنتهية"""
    try:
        data = json.loads(request.body)
        days_old = data.get('days_old', 90)
        dry_run = data.get('dry_run', False)
        
        result = AdminMaintenanceService.cleanup_expired_components(
            days_old=days_old,
            dry_run=dry_run
        )
        
        return JsonResponse({
            'success': True,
            'results': result,
            'message': f'تم تنظيف {result.get("deleted_count", 0)} بند منتهي' if not dry_run else 'معاينة التنظيف'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في تنظيف البنود المنتهية: {str(e)}'
        })


@login_required
@hr_manager_required
@require_http_methods(["POST"])
def maintenance_cleanup_orphaned(request):
    """تنظيف البنود اليتيمة"""
    try:
        data = json.loads(request.body)
        dry_run = data.get('dry_run', False)
        
        result = AdminMaintenanceService.cleanup_orphaned_components(dry_run=dry_run)
        
        return JsonResponse({
            'success': True,
            'results': result,
            'message': f'تم تنظيف {result.get("deleted_count", 0)} بند يتيم' if not dry_run else 'معاينة التنظيف'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في تنظيف البنود اليتيمة: {str(e)}'
        })


@login_required
@hr_manager_required
@require_http_methods(["POST"])
def maintenance_fix_inconsistencies(request):
    """إصلاح تضارب البيانات"""
    try:
        data = json.loads(request.body)
        dry_run = data.get('dry_run', False)
        
        result = AdminMaintenanceService.fix_data_inconsistencies(dry_run=dry_run)
        
        return JsonResponse({
            'success': True,
            'results': result,
            'message': f'تم إصلاح {result.get("total_fixes", 0)} مشكلة' if not dry_run else 'معاينة الإصلاح'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في إصلاح البيانات: {str(e)}'
        })


@login_required
@hr_manager_required
@require_http_methods(["POST"])
def maintenance_auto_renewals(request):
    """معالجة التجديد التلقائي للبنود"""
    try:
        data = json.loads(request.body)
        dry_run = data.get('dry_run', False)
        
        # الحصول على البنود القابلة للتجديد التلقائي
        renewable_components = ComponentClassificationService.get_expiring_components().filter(
            auto_renew=True
        )
        
        renewed_count = 0
        if not dry_run:
            for component in renewable_components:
                try:
                    ComponentClassificationService.renew_component(
                        component, 
                        renewed_by=request.user
                    )
                    renewed_count += 1
                except Exception as e:
                    print(f"Error renewing component {component.id}: {e}")
        
        result = {
            'total_renewable': renewable_components.count(),
            'renewed_count': renewed_count if not dry_run else 0,
            'dry_run': dry_run
        }
        
        return JsonResponse({
            'success': True,
            'results': result,
            'message': f'تم تجديد {renewed_count} بند تلقائياً' if not dry_run else f'يمكن تجديد {result["total_renewable"]} بند'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في التجديد التلقائي: {str(e)}'
        })


@login_required
@hr_manager_required
def maintenance_overview(request):
    """API للحصول على نظرة عامة محدثة"""
    try:
        overview = AdminMaintenanceService.get_system_overview()
        
        return JsonResponse({
            'success': True,
            'overview': overview,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في تحديث الإحصائيات: {str(e)}'
        })


@login_required
@hr_manager_required
def maintenance_report(request):
    """توليد تقرير صيانة شامل"""
    try:
        report = AdminMaintenanceService.generate_maintenance_report()
        
        # إنشاء HTML للتقرير
        html_content = f"""
        <!DOCTYPE html>
        <html dir="rtl" lang="ar">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>تقرير الصيانة الإدارية</title>
            <style>
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    margin: 20px; 
                    direction: rtl; 
                    text-align: right;
                }}
                .header {{ 
                    text-align: center; 
                    border-bottom: 2px solid #007bff; 
                    padding-bottom: 20px; 
                    margin-bottom: 30px; 
                }}
                .section {{ 
                    margin-bottom: 30px; 
                    padding: 20px; 
                    border: 1px solid #dee2e6; 
                    border-radius: 8px; 
                }}
                .section h3 {{ 
                    color: #007bff; 
                    border-bottom: 1px solid #dee2e6; 
                    padding-bottom: 10px; 
                }}
                .stats {{ 
                    display: grid; 
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                    gap: 15px; 
                    margin: 20px 0; 
                }}
                .stat-card {{ 
                    background: #f8f9fa; 
                    padding: 15px; 
                    border-radius: 8px; 
                    text-align: center; 
                }}
                .stat-number {{ 
                    font-size: 2em; 
                    font-weight: bold; 
                    color: #007bff; 
                }}
                .recommendation {{ 
                    background: #fff3cd; 
                    border: 1px solid #ffeaa7; 
                    border-radius: 8px; 
                    padding: 15px; 
                    margin: 10px 0; 
                }}
                .recommendation.high {{ 
                    background: #f8d7da; 
                    border-color: #f5c6cb; 
                }}
                .recommendation.medium {{ 
                    background: #fff3cd; 
                    border-color: #ffeaa7; 
                }}
                .recommendation.low {{ 
                    background: #d1ecf1; 
                    border-color: #bee5eb; 
                }}
                .footer {{ 
                    text-align: center; 
                    margin-top: 40px; 
                    padding-top: 20px; 
                    border-top: 1px solid #dee2e6; 
                    color: #6c757d; 
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>تقرير الصيانة الإدارية</h1>
                <p>تاريخ التوليد: {report['generated_at'].strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="section">
                <h3>نظرة عامة على النظام</h3>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">{report['system_overview']['employees']['active']}</div>
                        <div>موظف نشط</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{report['system_overview']['contracts']['active']}</div>
                        <div>عقد نشط</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{report['system_overview']['components']['active']}</div>
                        <div>بند نشط</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{report['system_overview']['components']['expiring']}</div>
                        <div>بند منتهي قريباً</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h3>تحليل الصيانة</h3>
                <p><strong>البنود المنتهية:</strong> {report['maintenance_analysis']['expired_components']['total_candidates']} بند</p>
                <p><strong>البنود اليتيمة:</strong> {report['maintenance_analysis']['orphaned_components']['total_orphaned']} بند</p>
                <p><strong>مشاكل البيانات:</strong> {report['maintenance_analysis']['data_inconsistencies']['total_fixes']} مشكلة</p>
            </div>
            
            <div class="section">
                <h3>التوصيات</h3>
        """
        
        for rec in report['recommendations']:
            html_content += f"""
                <div class="recommendation {rec['priority']}">
                    <h4>{rec['title']}</h4>
                    <p>{rec['description']}</p>
                    <small>الوقت المقدر: {rec['estimated_time']}</small>
                </div>
            """
        
        html_content += f"""
            </div>
            
            <div class="footer">
                <p>تم توليد هذا التقرير بواسطة نظام MWHEBA ERP</p>
                <p>التاريخ التالي للصيانة المقترحة: {report['next_maintenance_date']}</p>
            </div>
        </body>
        </html>
        """
        
        response = HttpResponse(html_content, content_type='text/html; charset=utf-8')
        response['Content-Disposition'] = f'inline; filename="maintenance_report_{date.today()}.html"'
        
        return response
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في توليد التقرير: {str(e)}'
        })


@login_required  
@hr_manager_required
def employee_components_analysis(request, employee_id):
    """API تحليل بنود موظف معين"""
    try:
        from ..models import Employee
        from ..services.unified_contract_service import UnifiedContractService
        
        employee = Employee.objects.get(id=employee_id)
        
        # استخدام الخدمة الموحدة للتحليل
        unified_service = UnifiedContractService()
        analysis = unified_service.get_employee_component_analysis(employee)
        
        # تحويل البيانات إلى تنسيق قابل للتسلسل
        serializable_analysis = _serialize_analysis_data(analysis)
        
        return JsonResponse({
            'success': True,
            'analysis': serializable_analysis
        })
        
    except Employee.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'الموظف غير موجود'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ في التحليل: {str(e)}'
        })
