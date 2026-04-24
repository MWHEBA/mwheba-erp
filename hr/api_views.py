"""
API ViewSets لوحدة الموارد البشرية
Phase 3: Enhanced with rate limiting, input validation, and security
"""
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date
import logging

from .models import (
    Employee, Department, JobTitle, Shift, Attendance,
    LeaveType, LeaveBalance, Leave, Payroll, Advance
)
from .serializers import (
    EmployeeSerializer, DepartmentSerializer, JobTitleSerializer,
    ShiftSerializer, AttendanceSerializer, LeaveTypeSerializer,
    LeaveBalanceSerializer, LeaveSerializer,
    PayrollSerializer, AdvanceSerializer
)
from .services import EmployeeService, AttendanceService, LeaveService, PayrollService
from .permissions import (
    IsHRManager, IsHRStaff, CanProcessPayroll, 
    CanTerminateEmployee, CanApproveLeave
)

logger = logging.getLogger(__name__)


class PayrollRateThrottle(UserRateThrottle):
    """
    Rate limiting for sensitive payroll operations
    Issue #36: No rate limiting
    """
    rate = '10/hour'


class SensitiveOperationThrottle(UserRateThrottle):
    """Rate limiting for sensitive operations like termination"""
    rate = '5/hour'


class DepartmentViewSet(viewsets.ModelViewSet):
    """API للأقسام"""
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'parent']
    search_fields = ['name_ar', 'name_en', 'code']
    ordering_fields = ['name_ar', 'created_at']
    ordering = ['name_ar']


class JobTitleViewSet(viewsets.ModelViewSet):
    """API للمسميات الوظيفية"""
    queryset = JobTitle.objects.all()
    serializer_class = JobTitleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'department']
    search_fields = ['title_ar', 'title_en', 'code']
    ordering_fields = ['title_ar', 'created_at']
    ordering = ['title_ar']


class EmployeeViewSet(viewsets.ModelViewSet):
    """
    API للموظفين مع Rate Limiting و Authority Validation
    Issues #1, #36: Missing permissions and rate limiting
    """
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, IsHRStaff]
    throttle_classes = [UserRateThrottle]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'department', 'job_title', 'employment_type']
    search_fields = ['name', 'employee_number', 'national_id', 'work_email']
    ordering_fields = ['employee_number', 'hire_date', 'created_at']
    ordering = ['employee_number']
    
    @action(
        detail=True, 
        methods=['post'],
        permission_classes=[IsAuthenticated, CanTerminateEmployee],
        throttle_classes=[SensitiveOperationThrottle]
    )
    def terminate(self, request, pk=None):
        """
        إنهاء خدمة موظف مع Authority Validation
        Issue #1: Missing API permissions
        """
        employee = self.get_object()
        termination_data = request.data
        
        # Validate termination data
        if not termination_data.get('termination_date'):
            return Response(
                {'error': 'تاريخ إنهاء الخدمة مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not termination_data.get('termination_reason'):
            return Response(
                {'error': 'سبب إنهاء الخدمة مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            EmployeeService.terminate_employee(employee, termination_data, request.user)
            return Response({
                'status': 'success', 
                'message': 'تم إنهاء خدمة الموظف'
            })
        except ValidationError as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error terminating employee: {e}")
            return Response(
                {'status': 'error', 'message': 'حدث خطأ أثناء إنهاء الخدمة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """ملخص شامل للموظف"""
        employee = self.get_object()
        summary = EmployeeService.get_employee_summary(employee)
        return Response(summary)


class ShiftViewSet(viewsets.ModelViewSet):
    """API للورديات"""
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'shift_type']
    search_fields = ['name']
    ordering_fields = ['name', 'start_time']
    ordering = ['start_time']


class AttendanceViewSet(viewsets.ModelViewSet):
    """
    API للحضور مع Input Validation
    Issue #37: Missing attendance validation
    """
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employee', 'date', 'status', 'shift']
    search_fields = ['employee__name', 'employee__employee_number']
    ordering_fields = ['date', 'check_in']
    ordering = ['-date']
    
    @action(detail=False, methods=['post'])
    def check_in(self, request):
        """
        تسجيل حضور مع Comprehensive Validation
        Issue #37: Missing attendance validation
        """
        employee_id = request.data.get('employee_id')
        
        # Validate employee_id provided
        if not employee_id:
            return Response(
                {'error': 'رقم الموظف مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Validate employee exists and is active
            employee = Employee.objects.get(id=employee_id)
            
            if employee.status != 'active':
                return Response(
                    {'error': f'الموظف غير نشط. الحالة: {employee.get_status_display()}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if already checked in today
            today = timezone.now().date()
            existing = Attendance.objects.filter(
                employee=employee,
                date=today,
                check_in__isnull=False
            ).first()
            
            if existing:
                return Response(
                    {
                        'error': 'تم تسجيل الحضور بالفعل اليوم',
                        'check_in_time': existing.check_in.strftime('%H:%M:%S') if existing.check_in else None
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Record check-in
            attendance = AttendanceService.record_check_in(employee)
            serializer = self.get_serializer(attendance)
            
            
            return Response({
                'status': 'success',
                'message': 'تم تسجيل الحضور بنجاح',
                'data': serializer.data
            })
            
        except Employee.DoesNotExist:
            return Response(
                {'error': 'الموظف غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error recording check-in: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء تسجيل الحضور'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def check_out(self, request):
        """
        تسجيل انصراف مع Validation
        Issue #37: Missing attendance validation
        """
        employee_id = request.data.get('employee_id')
        
        if not employee_id:
            return Response(
                {'error': 'رقم الموظف مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            employee = Employee.objects.get(id=employee_id, status='active')
            
            # Check if checked in today
            today = timezone.now().date()
            attendance = Attendance.objects.filter(
                employee=employee,
                date=today,
                check_in__isnull=False,
                check_out__isnull=True
            ).first()
            
            if not attendance:
                return Response(
                    {'error': 'لم يتم تسجيل حضور اليوم أو تم تسجيل الانصراف بالفعل'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Record check-out
            attendance = AttendanceService.record_check_out(employee)
            serializer = self.get_serializer(attendance)
            
            
            return Response({
                'status': 'success',
                'message': 'تم تسجيل الانصراف بنجاح',
                'data': serializer.data
            })
            
        except Employee.DoesNotExist:
            return Response(
                {'error': 'الموظف غير موجود أو غير نشط'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error recording check-out: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء تسجيل الانصراف'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def monthly_stats(self, request):
        """إحصائيات الحضور الشهرية"""
        employee_id = request.query_params.get('employee_id')
        month_str = request.query_params.get('month')  # YYYY-MM
        
        if not employee_id or not month_str:
            return Response(
                {'error': 'رقم الموظف والشهر مطلوبان'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            employee = Employee.objects.get(id=employee_id)
            year, month = map(int, month_str.split('-'))
            month_date = date(year, month, 1)
            
            stats = AttendanceService.calculate_monthly_attendance(employee, month_date)
            return Response(stats)
        except Employee.DoesNotExist:
            return Response(
                {'error': 'الموظف غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {'error': 'صيغة الشهر غير صحيحة. استخدم YYYY-MM'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error calculating monthly stats: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء حساب الإحصائيات'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LeaveTypeViewSet(viewsets.ModelViewSet):
    """API لأنواع الإجازات"""
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_paid', 'requires_approval']
    search_fields = ['name_ar', 'name_en', 'code']
    ordering_fields = ['name_ar']
    ordering = ['name_ar']


class LeaveBalanceViewSet(viewsets.ModelViewSet):
    """API لرصيد الإجازات"""
    queryset = LeaveBalance.objects.all()
    serializer_class = LeaveBalanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['employee', 'leave_type', 'year']
    ordering_fields = ['year']
    ordering = ['-year']


class LeaveViewSet(viewsets.ModelViewSet):
    """
    API للإجازات مع Permissions
    """
    queryset = Leave.objects.all()
    serializer_class = LeaveSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employee', 'leave_type', 'status']
    search_fields = ['employee__name', 'reason']
    ordering_fields = ['requested_at', 'start_date']
    ordering = ['-requested_at']
    
    @action(
        detail=True, 
        methods=['post'],
        permission_classes=[IsAuthenticated, CanApproveLeave]
    )
    def approve(self, request, pk=None):
        """اعتماد إجازة"""
        leave = self.get_object()
        
        if leave.status != 'pending':
            return Response(
                {'error': f'لا يمكن اعتماد إجازة بحالة {leave.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            LeaveService.approve_leave(leave, request.user)
            return Response({
                'status': 'success', 
                'message': 'تم اعتماد الإجازة'
            })
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error approving leave: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء اعتماد الإجازة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(
        detail=True, 
        methods=['post'],
        permission_classes=[IsAuthenticated, CanApproveLeave]
    )
    def reject(self, request, pk=None):
        """رفض إجازة"""
        leave = self.get_object()
        notes = request.data.get('notes', '')
        
        if leave.status != 'pending':
            return Response(
                {'error': f'لا يمكن رفض إجازة بحالة {leave.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not notes:
            return Response(
                {'error': 'سبب الرفض مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            LeaveService.reject_leave(leave, request.user, notes)
            return Response({
                'status': 'success', 
                'message': 'تم رفض الإجازة'
            })
        except Exception as e:
            logger.error(f"Error rejecting leave: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء رفض الإجازة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PayrollViewSet(viewsets.ModelViewSet):
    """
    API لقسائم الرواتب مع Rate Limiting
    Issue #36: No rate limiting
    """
    queryset = Payroll.objects.all()
    serializer_class = PayrollSerializer
    permission_classes = [IsAuthenticated, CanProcessPayroll]
    throttle_classes = [PayrollRateThrottle]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['employee', 'month', 'status']
    ordering_fields = ['month', 'processed_at']
    ordering = ['-month']
    
    @action(detail=False, methods=['post'])
    def process_monthly(self, request):
        """
        معالجة رواتب شهرية مع Input Validation
        Issue #2: Unvalidated input
        """
        month_str = request.data.get('month')  # YYYY-MM
        
        if not month_str:
            return Response(
                {'error': 'الشهر مطلوب بصيغة YYYY-MM'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            year, month = map(int, month_str.split('-'))
            
            # Validate month range
            if not (1 <= month <= 12):
                return Response(
                    {'error': 'الشهر يجب أن يكون بين 1 و 12'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate year range
            current_year = timezone.now().year
            if not (2020 <= year <= current_year + 1):
                return Response(
                    {'error': f'السنة يجب أن تكون بين 2020 و {current_year + 1}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            month_date = date(year, month, 1)
            
            # Check if future month
            if month_date > timezone.now().date():
                return Response(
                    {'error': 'لا يمكن معالجة رواتب لشهر مستقبلي'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            results = PayrollService.process_monthly_payroll(month_date, request.user)
            
            
            return Response({
                'status': 'success',
                'total': len(results),
                'successful': sum(1 for r in results if r['success']),
                'failed': sum(1 for r in results if not r['success']),
                'results': results
            })
            
        except ValueError:
            return Response(
                {'error': 'صيغة الشهر غير صحيحة. استخدم YYYY-MM'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error processing monthly payroll: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء معالجة الرواتب'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """اعتماد قسيمة راتب"""
        payroll = self.get_object()
        
        if payroll.status != 'calculated':
            return Response(
                {'error': f'لا يمكن اعتماد راتب بحالة {payroll.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            PayrollService.approve_payroll(payroll, request.user)
            return Response({
                'status': 'success', 
                'message': 'تم اعتماد قسيمة الراتب'
            })
        except Exception as e:
            logger.error(f"Error approving payroll: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء اعتماد الراتب'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdvanceViewSet(viewsets.ModelViewSet):
    """
    API للسلف مع Input Validation
    Issue #2: Unvalidated input
    """
    queryset = Advance.objects.all()
    serializer_class = AdvanceSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employee', 'status']
    search_fields = ['employee__name', 'reason']
    ordering_fields = ['requested_at', 'amount']
    ordering = ['-requested_at']
    
    def create(self, request, *args, **kwargs):
        """
        Create advance with comprehensive validation
        Issue #2: Unvalidated input
        """
        from decimal import Decimal
        
        employee_id = request.data.get('employee')
        amount = request.data.get('amount')
        
        # Validate required fields
        if not employee_id:
            return Response(
                {'error': 'رقم الموظف مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not amount:
            return Response(
                {'error': 'مبلغ السلفة مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            amount = Decimal(str(amount))
            
            # Validate amount is positive
            if amount <= 0:
                return Response(
                    {'error': 'مبلغ السلفة يجب أن يكون أكبر من صفر'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate minimum amount
            if amount < Decimal('100'):
                return Response(
                    {'error': 'الحد الأدنى للسلفة 100 جنيه'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get employee and validate
            employee = Employee.objects.get(id=employee_id)
            
            if employee.status != 'active':
                return Response(
                    {'error': 'الموظف غير نشط'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get active contract
            contract = employee.get_active_contract()
            if not contract:
                return Response(
                    {'error': 'لا يوجد عقد نشط للموظف'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate amount doesn't exceed salary
            if amount > contract.basic_salary:
                return Response(
                    {
                        'error': f'مبلغ السلفة ({amount}) يتجاوز الأجر الأساسي ({contract.basic_salary})'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check total advances limit
            from django.db.models import Sum
            total_advances = employee.advances.filter(
                status__in=['paid', 'in_progress']
            ).aggregate(Sum('remaining_amount'))['remaining_amount__sum'] or Decimal('0')
            
            max_allowed = contract.basic_salary * 2  # Max 2x salary
            if total_advances + amount > max_allowed:
                return Response(
                    {
                        'error': f'إجمالي السلف ({total_advances + amount}) يتجاوز الحد المسموح ({max_allowed})'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Proceed with creation
            return super().create(request, *args, **kwargs)
            
        except Employee.DoesNotExist:
            return Response(
                {'error': 'الموظف غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        except (ValueError, TypeError):
            return Response(
                {'error': 'مبلغ السلفة غير صحيح'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating advance: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء إنشاء السلفة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsHRManager])
    def approve(self, request, pk=None):
        """اعتماد سلفة"""
        advance = self.get_object()
        
        if advance.status != 'pending':
            return Response(
                {'error': f'لا يمكن اعتماد سلفة بحالة {advance.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            advance.status = 'approved'
            advance.approved_by = request.user
            advance.save()
            
            
            return Response({
                'status': 'success', 
                'message': 'تم اعتماد السلفة'
            })
        except Exception as e:
            logger.error(f"Error approving advance: {e}")
            return Response(
                {'error': 'حدث خطأ أثناء اعتماد السلفة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
