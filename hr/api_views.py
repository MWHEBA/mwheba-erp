"""
API ViewSets لوحدة الموارد البشرية
"""
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from datetime import date

from .models import (
    Employee, Department, JobTitle, Shift, Attendance,
    LeaveType, LeaveBalance, Leave, Salary, Payroll, Advance
)
from .serializers import (
    EmployeeSerializer, DepartmentSerializer, JobTitleSerializer,
    ShiftSerializer, AttendanceSerializer, LeaveTypeSerializer,
    LeaveBalanceSerializer, LeaveSerializer, SalarySerializer,
    PayrollSerializer, AdvanceSerializer
)
from .services import EmployeeService, AttendanceService, LeaveService, PayrollService


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
    """API للموظفين"""
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'department', 'job_title', 'employment_type']
    search_fields = ['first_name_ar', 'last_name_ar', 'employee_number', 'national_id', 'work_email']
    ordering_fields = ['employee_number', 'hire_date', 'created_at']
    ordering = ['employee_number']
    
    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """إنهاء خدمة موظف"""
        employee = self.get_object()
        termination_data = request.data
        
        try:
            EmployeeService.terminate_employee(employee, termination_data, request.user)
            return Response({'status': 'success', 'message': 'تم إنهاء خدمة الموظف'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
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
    """API للحضور"""
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employee', 'date', 'status', 'shift']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar', 'employee__employee_number']
    ordering_fields = ['date', 'check_in']
    ordering = ['-date']
    
    @action(detail=False, methods=['post'])
    def check_in(self, request):
        """تسجيل حضور"""
        employee_id = request.data.get('employee_id')
        try:
            employee = Employee.objects.get(id=employee_id)
            attendance = AttendanceService.record_check_in(employee)
            serializer = self.get_serializer(attendance)
            return Response(serializer.data)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def check_out(self, request):
        """تسجيل انصراف"""
        employee_id = request.data.get('employee_id')
        try:
            employee = Employee.objects.get(id=employee_id)
            attendance = AttendanceService.record_check_out(employee)
            serializer = self.get_serializer(attendance)
            return Response(serializer.data)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def monthly_stats(self, request):
        """إحصائيات الحضور الشهرية"""
        employee_id = request.query_params.get('employee_id')
        month_str = request.query_params.get('month')  # YYYY-MM
        
        try:
            employee = Employee.objects.get(id=employee_id)
            year, month = map(int, month_str.split('-'))
            month_date = date(year, month, 1)
            
            stats = AttendanceService.calculate_monthly_attendance(employee, month_date)
            return Response(stats)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
    """API للإجازات"""
    queryset = Leave.objects.all()
    serializer_class = LeaveSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employee', 'leave_type', 'status']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar', 'reason']
    ordering_fields = ['requested_at', 'start_date']
    ordering = ['-requested_at']
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """اعتماد إجازة"""
        leave = self.get_object()
        try:
            LeaveService.approve_leave(leave, request.user)
            return Response({'status': 'success', 'message': 'تم اعتماد الإجازة'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """رفض إجازة"""
        leave = self.get_object()
        notes = request.data.get('notes', '')
        try:
            LeaveService.reject_leave(leave, request.user, notes)
            return Response({'status': 'success', 'message': 'تم رفض الإجازة'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SalaryViewSet(viewsets.ModelViewSet):
    """API للرواتب"""
    queryset = Salary.objects.all()
    serializer_class = SalarySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['employee', 'is_active']
    ordering_fields = ['effective_date']
    ordering = ['-effective_date']


class PayrollViewSet(viewsets.ModelViewSet):
    """API لكشوف الرواتب"""
    queryset = Payroll.objects.all()
    serializer_class = PayrollSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['employee', 'month', 'status']
    ordering_fields = ['month', 'processed_at']
    ordering = ['-month']
    
    @action(detail=False, methods=['post'])
    def process_monthly(self, request):
        """معالجة رواتب شهرية"""
        month_str = request.data.get('month')  # YYYY-MM
        try:
            year, month = map(int, month_str.split('-'))
            month_date = date(year, month, 1)
            
            results = PayrollService.process_monthly_payroll(month_date, request.user)
            return Response({
                'status': 'success',
                'total': len(results),
                'successful': sum(1 for r in results if r['success']),
                'failed': sum(1 for r in results if not r['success']),
                'results': results
            })
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """اعتماد كشف راتب"""
        payroll = self.get_object()
        try:
            PayrollService.approve_payroll(payroll, request.user)
            return Response({'status': 'success', 'message': 'تم اعتماد كشف الراتب'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdvanceViewSet(viewsets.ModelViewSet):
    """API للسلف"""
    queryset = Advance.objects.all()
    serializer_class = AdvanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employee', 'status', 'deducted']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar', 'reason']
    ordering_fields = ['request_date', 'amount']
    ordering = ['-request_date']
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """اعتماد سلفة"""
        advance = self.get_object()
        advance.status = 'approved'
        advance.approved_by = request.user
        advance.save()
        return Response({'status': 'success', 'message': 'تم اعتماد السلفة'})
