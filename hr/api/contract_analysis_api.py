from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from hr.models import Employee, Contract, SalaryComponent
from hr.services.unified_contract_service import UnifiedContractService
from hr.services.smart_contract_analyzer import SmartContractAnalyzer
from hr.services.component_intelligence import ComponentIntelligence
import json
import logging

logger = logging.getLogger(__name__)


@method_decorator([login_required], name='dispatch')
class ContractAnalysisAPI(View):
    """API لتحليل العقود وبنود الراتب"""
    
    def __init__(self):
        super().__init__()
        self.unified_service = UnifiedContractService()
        self.analyzer = SmartContractAnalyzer()
        self.intelligence = ComponentIntelligence()
    
    def get(self, request, employee_id):
        """تحليل بنود الموظف للعقد الجديد"""
        
        try:
            employee = get_object_or_404(Employee, id=employee_id)
            
            # تحليل شامل لبنود الموظف
            analysis = self.unified_service.get_employee_component_analysis(employee)
            
            # تحضير البيانات للإرجاع
            response_data = {
                'success': True,
                'employee': {
                    'id': employee.id,
                    'name': employee.name,
                    'employee_number': employee.employee_number
                },
                'analysis': self._serialize_analysis(analysis),
                'summary': self._create_analysis_summary(analysis)
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"خطأ في تحليل بنود الموظف {employee_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator([login_required], name='dispatch')
class ContractActivationPreviewAPI(View):
    """API لمعاينة تفعيل العقد"""
    
    def __init__(self):
        super().__init__()
        self.unified_service = UnifiedContractService()
    
    def post(self, request, contract_id):
        """معاينة تفعيل العقد مع اختيارات المستخدم"""
        
        try:
            contract = get_object_or_404(Contract, id=contract_id)
            
            # جلب اختيارات المستخدم (إن وجدت)
            user_selections = None
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                user_selections = data.get('user_selections')
            
            # معاينة التفعيل
            preview = self.unified_service.preview_contract_activation(
                contract, user_selections
            )
            
            response_data = {
                'success': True,
                'contract': {
                    'id': contract.id,
                    'employee_name': contract.employee.name,
                    'basic_salary': float(contract.basic_salary) if contract.basic_salary else 0,
                    'start_date': contract.start_date.isoformat() if contract.start_date else None
                },
                'preview': self._serialize_preview(preview),
                'recommendations': self._extract_recommendations(preview)
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"خطأ في معاينة تفعيل العقد {contract_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator([login_required, csrf_exempt], name='dispatch')
class SmartContractActivationAPI(View):
    """API للتفعيل الذكي للعقد"""
    
    def __init__(self):
        super().__init__()
        self.unified_service = UnifiedContractService()
    
    def post(self, request, contract_id):
        """تفعيل ذكي للعقد"""
        
        try:
            contract = get_object_or_404(Contract, id=contract_id)
            
            # جلب اختيارات المستخدم
            user_selections = None
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                user_selections = data.get('user_selections')
            
            # تفعيل العقد
            result = self.unified_service.smart_activate_contract(
                contract, user_selections, request.user
            )
            
            response_data = {
                'success': True,
                'contract': {
                    'id': contract.id,
                    'status': contract.status,
                    'activation_date': contract.activation_date.isoformat() if contract.activation_date else None
                },
                'results': self._serialize_activation_results(result),
                'summary': result['summary']
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"خطأ في تفعيل العقد {contract_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator([login_required], name='dispatch')
class ComponentIntelligenceAPI(View):
    """API لذكاء البنود"""
    
    def __init__(self):
        super().__init__()
        self.intelligence = ComponentIntelligence()
    
    def get(self, request, employee_id):
        """تحليل أنماط بنود الموظف"""
        
        try:
            employee = get_object_or_404(Employee, id=employee_id)
            
            # تحليل الأنماط
            patterns = self.intelligence.analyze_component_patterns(employee)
            
            response_data = {
                'success': True,
                'employee': {
                    'id': employee.id,
                    'name': employee.name
                },
                'patterns': self._serialize_patterns(patterns)
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"خطأ في تحليل أنماط الموظف {employee_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def post(self, request, component_id):
        """اقتراح تصنيف للبند"""
        
        try:
            component = get_object_or_404(SalaryComponent, id=component_id)
            
            # اقتراح التصنيف
            suggested_source = self.intelligence.suggest_component_source(component)
            
            # تحليل التجديد
            renewal_prediction = self.intelligence.predict_component_renewal(component)
            
            response_data = {
                'success': True,
                'component': {
                    'id': component.id,
                    'name': component.name,
                    'current_source': component.source
                },
                'suggested_source': suggested_source,
                'renewal_prediction': renewal_prediction
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"خطأ في تحليل البند {component_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


# Helper Methods للتسلسل
class APISerializerMixin:
    """مساعد لتسلسل البيانات"""
    
    def _serialize_analysis(self, analysis):
        """تسلسل تحليل البنود"""
        
        basic = analysis['basic_analysis']
        pattern = analysis['pattern_analysis']
        
        return {
            'total_components': basic['total_components'],
            'classified_components': self._serialize_classified_components(basic['classified_components']),
            'transferable_components': self._serialize_transferable_components(basic['transferable_components']),
            'conflicts': self._serialize_conflicts(basic['conflicts']),
            'financial_impact': basic['financial_impact'],
            'pattern_analysis': {
                'by_source': pattern['by_source'],
                'financial_summary': pattern['financial_summary'],
                'anomalies_count': len(pattern['anomalies']),
                'recommendations_count': len(pattern['recommendations'])
            },
            'health_assessment': analysis['overall_health']
        }
    
    def _serialize_classified_components(self, classified):
        """تسلسل البنود المصنفة"""
        
        serialized = {}
        for source, components in classified.items():
            serialized[source] = [
                {
                    'id': comp.id,
                    'name': comp.name,
                    'amount': float(comp.amount),
                    'component_type': comp.component_type,
                    'is_active': comp.is_active,
                    'effective_to': comp.effective_to.isoformat() if comp.effective_to else None
                }
                for comp in components
            ]
        
        return serialized
    
    def _serialize_transferable_components(self, transferable):
        """تسلسل البنود القابلة للنقل"""
        
        return [
            {
                'component': {
                    'id': item['component'].id,
                    'name': item['component'].name,
                    'amount': float(item['component'].amount),
                    'source': item['component'].source
                },
                'transfer_type': item['transfer_type'],
                'reason': item['reason'],
                'priority': item['priority']
            }
            for item in transferable
        ]
    
    def _serialize_conflicts(self, conflicts):
        """تسلسل التضارب"""
        
        return [
            {
                'type': conflict['type'],
                'message': conflict['message'],
                'severity': conflict['severity'],
                'component_id': conflict['component'].id if 'component' in conflict else None
            }
            for conflict in conflicts
        ]
    
    def _serialize_preview(self, preview):
        """تسلسل معاينة التفعيل"""
        
        return {
            'total_components': preview['transfer_preview']['total_components'],
            'auto_transfer_count': preview['transfer_preview']['auto_transfer_count'],
            'manual_review_count': preview['transfer_preview']['manual_review_count'],
            'archive_count': preview['transfer_preview']['archive_count'],
            'estimated_impact': preview['estimated_impact']
        }
    
    def _serialize_activation_results(self, result):
        """تسلسل نتائج التفعيل"""
        
        transfer_results = result['transfer_results']
        
        return {
            'transferred_count': len(transfer_results['transferred']),
            'archived_count': len(transfer_results['archived']),
            'errors_count': len(transfer_results['errors']),
            'transferred_components': [
                {
                    'original_id': item['original'].id,
                    'new_id': item['new'].id,
                    'name': item['new'].name,
                    'reason': item['reason']
                }
                for item in transfer_results['transferred']
            ]
        }
    
    def _serialize_patterns(self, patterns):
        """تسلسل أنماط البنود"""
        
        return {
            'total_components': patterns['total_components'],
            'by_source': {
                source: {
                    'count': data['count'],
                    'total_amount': float(data['total_amount'])
                }
                for source, data in patterns['by_source'].items()
            },
            'financial_summary': {
                key: float(value) if isinstance(value, (int, float)) else value
                for key, value in patterns['financial_summary'].items()
            },
            'anomalies_count': len(patterns['anomalies']),
            'recommendations_count': len(patterns['recommendations'])
        }
    
    def _create_analysis_summary(self, analysis):
        """إنشاء ملخص التحليل"""
        
        basic = analysis['basic_analysis']
        health = analysis['overall_health']
        
        return {
            'total_components': basic['total_components'],
            'transferable_count': len(basic['transferable_components']),
            'conflicts_count': len(basic['conflicts']),
            'health_score': health['score'],
            'health_level': health['level'],
            'requires_attention': health['score'] < 75 or len(basic['conflicts']) > 0
        }
    
    def _extract_recommendations(self, preview):
        """استخراج التوصيات من المعاينة"""
        
        recommendations = []
        
        # توصيات من التحليل
        for rec in preview['analysis']['recommendations']:
            recommendations.append({
                'type': rec['type'],
                'title': rec['title'],
                'message': rec['message'],
                'priority': rec['priority']
            })
        
        # توصيات من معاينة النقل
        for rec in preview['transfer_preview']['recommendations']:
            recommendations.append({
                'type': rec['type'],
                'message': rec['message'],
                'priority': rec['priority']
            })
        
        return recommendations


# تطبيق Mixin على جميع الـ APIs
ContractAnalysisAPI.__bases__ += (APISerializerMixin,)
ContractActivationPreviewAPI.__bases__ += (APISerializerMixin,)
SmartContractActivationAPI.__bases__ += (APISerializerMixin,)
ComponentIntelligenceAPI.__bases__ += (APISerializerMixin,)


# Function-based views للتوافق مع الأنظمة القديمة
@login_required
@require_http_methods(["GET"])
def employee_components_analysis(request, employee_id):
    """تحليل بنود الموظف - Function-based view"""
    
    api = ContractAnalysisAPI()
    return api.get(request, employee_id)


@login_required
@require_http_methods(["POST"])
def contract_activation_preview(request, contract_id):
    """معاينة تفعيل العقد - Function-based view"""
    
    api = ContractActivationPreviewAPI()
    return api.post(request, contract_id)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def smart_contract_activation(request, contract_id):
    """تفعيل ذكي للعقد - Function-based view"""
    
    api = SmartContractActivationAPI()
    return api.post(request, contract_id)
