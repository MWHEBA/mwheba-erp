"""
Imports مشتركة لجميع ملفات Views في وحدة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from django.db.models import Count, Sum, Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from datetime import date, timedelta, datetime
import logging
import hmac
import csv
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

# Django REST Framework imports
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

# Local imports
from ..models import Employee, Department, JobTitle, Attendance, Leave, LeaveBalance, LeaveType, Payroll, Shift, Advance, Contract, BiometricDevice, BiometricLog, BiometricSyncLog
from ..forms.employee_forms import EmployeeForm, DepartmentForm
from ..forms.attendance_forms import AttendanceForm
from ..forms.leave_forms import LeaveRequestForm
from ..forms.payroll_forms import PayrollProcessForm
from ..services.attendance_service import AttendanceService
from ..services.leave_service import LeaveService
from ..services.payroll_service import PayrollService
from ..reports import (
    reports_home, attendance_report, leave_report,
    payroll_report, employee_report
)

# Logger
logger = logging.getLogger(__name__)
