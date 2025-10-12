from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import models
import os
import subprocess
import datetime
import tempfile
import json
import sqlite3
import shutil
import zipfile
import io
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.db.models import Q

from .logs import create_log
from django.contrib.admin.views.decorators import staff_member_required
from .models import SystemLog
from product.models import Stock, Product, StockMovement
from django.contrib.auth import get_user_model
import logging

def is_superuser(user):
    """
    التحقق مما إذا كان المستخدم مشرفًا
    """
    return user.is_superuser

@login_required
@user_passes_test(is_superuser)
def backup_database(request):
    """
    نسخ قاعدة البيانات احتياطيًا
    """
    if request.method == 'POST':
        # سجل النشاط
        create_log(
            user=request.user,
            action=_("طلب نسخة احتياطية من قاعدة البيانات"),
            model_name="Database",
            ip_address=request.META.get('REMOTE_ADDR', None)
        )
        
        # الحصول على إعدادات قاعدة البيانات
        db_settings = settings.DATABASES['default']
        
        # التعامل مع قاعدة بيانات SQLite
        if db_settings['ENGINE'] == 'django.db.backends.sqlite3':
            db_path = db_settings['NAME']
            
            # إنشاء نسخة من الملف
            backup_date = timezone.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{backup_date}.sqlite3"
            
            # إنشاء الملف المضغوط
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.write(db_path, arcname=backup_filename)
            
            # إعادة البيانات للمستخدم
            response = HttpResponse(zip_buffer.getvalue(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="db_backup_{backup_date}.zip"'
            return response
        
        # التعامل مع قاعدة بيانات MySQL
        elif db_settings['ENGINE'] == 'django.db.backends.mysql':
            # إنشاء ملف مؤقت للنسخ الاحتياطي
            backup_date = timezone.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{backup_date}.sql"
            temp_dir = tempfile.gettempdir()
            backup_path = os.path.join(temp_dir, backup_filename)
            
            # تنفيذ أمر النسخ الاحتياطي باستخدام mysqldump
            dump_command = [
                'mysqldump',
                f'--host={db_settings["HOST"]}',
                f'--port={db_settings["PORT"]}',
                f'--user={db_settings["USER"]}',
                f'--password={db_settings["PASSWORD"]}',
                f'{db_settings["NAME"]}',
                f'--result-file={backup_path}'
            ]
            
            try:
                subprocess.run(dump_command, check=True)
                
                # إنشاء الملف المضغوط
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zip_file:
                    zip_file.write(backup_path, arcname=backup_filename)
                
                # حذف الملف المؤقت
                os.remove(backup_path)
                
                # إعادة البيانات للمستخدم
                response = HttpResponse(zip_buffer.getvalue(), content_type='application/octet-stream')
                response['Content-Disposition'] = f'attachment; filename="db_backup_{backup_date}.zip"'
                return response
            except Exception as e:
                messages.error(request, f_("حدث خطأ أثناء عملية النسخ الاحتياطي: {str(e)}"))
                return redirect('utils:backup_database')
        
        else:
            messages.error(request, _("نوع قاعدة البيانات غير مدعوم للنسخ الاحتياطي التلقائي."))
            return redirect('utils:backup_database')
    
    # عرض صفحة النسخ الاحتياطي
    return render(request, 'utils/backup.html', {
        'title': _('النسخ الاحتياطي لقاعدة البيانات'),
        'page_title': _('النسخ الاحتياطي لقاعدة البيانات'),
        'page_icon': 'fas fa-database',
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': 'core:dashboard', 'icon': 'fas fa-home'},
            {'title': _('النسخ الاحتياطي'), 'active': True}
        ]
    })


@login_required
@user_passes_test(is_superuser)
def restore_database(request):
    """
    استعادة قاعدة البيانات من نسخة احتياطية
    """
    if request.method == 'POST' and request.FILES.get('backup_file'):
        # سجل النشاط
        create_log(
            user=request.user,
            action=_("محاولة استعادة قاعدة البيانات"),
            model_name="Database",
            ip_address=request.META.get('REMOTE_ADDR', None)
        )
        
        backup_file = request.FILES['backup_file']
        
        # التحقق من نوع الملف
        if not (backup_file.name.endswith('.zip') or backup_file.name.endswith('.sql') or backup_file.name.endswith('.sqlite3')):
            messages.error(request, _("نوع الملف غير مدعوم. يجب أن يكون الملف بصيغة .zip أو .sql أو .sqlite3"))
            return redirect('utils:restore_database')
        
        # الحصول على إعدادات قاعدة البيانات
        db_settings = settings.DATABASES['default']
        
        try:
            # ملف ZIP
            if backup_file.name.endswith('.zip'):
                zip_file = zipfile.ZipFile(backup_file)
                # استخراج الملفات إلى مجلد مؤقت
                temp_dir = tempfile.mkdtemp()
                zip_file.extractall(temp_dir)
                
                # البحث عن ملف قاعدة البيانات في المجلد المؤقت
                for file_name in os.listdir(temp_dir):
                    full_path = os.path.join(temp_dir, file_name)
                    
                    # استعادة قاعدة بيانات SQLite
                    if file_name.endswith('.sqlite3') and db_settings['ENGINE'] == 'django.db.backends.sqlite3':
                        # نسخ الملف المستخرج إلى مسار قاعدة البيانات
                        shutil.copy2(full_path, db_settings['NAME'])
                        messages.success(request, _("تم استعادة قاعدة البيانات بنجاح"))
                        return redirect('utils:restore_database')
                    
                    # استعادة قاعدة بيانات MySQL
                    elif file_name.endswith('.sql') and db_settings['ENGINE'] == 'django.db.backends.mysql':
                        # تنفيذ استعادة MySQL
                        restore_command = [
                            'mysql',
                            f'--host={db_settings["HOST"]}',
                            f'--port={db_settings["PORT"]}',
                            f'--user={db_settings["USER"]}',
                            f'--password={db_settings["PASSWORD"]}',
                            f'{db_settings["NAME"]}',
                            f'< {full_path}'
                        ]
                        
                        subprocess.run(" ".join(restore_command), shell=True, check=True)
                        messages.success(request, _("تم استعادة قاعدة البيانات بنجاح"))
                        return redirect('utils:restore_database')
                
                # حذف المجلد المؤقت
                shutil.rmtree(temp_dir)
                
                messages.error(request, _("لم يتم العثور على ملف قاعدة بيانات صالح في الأرشيف"))
                return redirect('utils:restore_database')
            
            # ملف SQL مباشر
            elif backup_file.name.endswith('.sql') and db_settings['ENGINE'] == 'django.db.backends.mysql':
                # حفظ الملف مؤقتًا
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.sql')
                for chunk in backup_file.chunks():
                    temp_file.write(chunk)
                temp_file.close()
                
                # تنفيذ استعادة MySQL
                restore_command = [
                    'mysql',
                    f'--host={db_settings["HOST"]}',
                    f'--port={db_settings["PORT"]}',
                    f'--user={db_settings["USER"]}',
                    f'--password={db_settings["PASSWORD"]}',
                    f'{db_settings["NAME"]}',
                    f'< {temp_file.name}'
                ]
                
                subprocess.run(" ".join(restore_command), shell=True, check=True)
                
                # حذف الملف المؤقت
                os.unlink(temp_file.name)
                
                messages.success(request, _("تم استعادة قاعدة البيانات بنجاح"))
                return redirect('utils:restore_database')
            
            # ملف SQLite مباشر
            elif backup_file.name.endswith('.sqlite3') and db_settings['ENGINE'] == 'django.db.backends.sqlite3':
                # حفظ الملف مباشرة إلى مسار قاعدة البيانات
                with open(db_settings['NAME'], 'wb+') as destination:
                    for chunk in backup_file.chunks():
                        destination.write(chunk)
                
                messages.success(request, _("تم استعادة قاعدة البيانات بنجاح"))
                return redirect('utils:restore_database')
            
            # نوع ملف غير مدعوم
            else:
                messages.error(request, _("نوع قاعدة البيانات غير متوافق مع ملف النسخة الاحتياطية"))
                return redirect('utils:restore_database')
        
        except Exception as e:
            messages.error(request, f_("حدث خطأ أثناء عملية الاستعادة: {str(e)}"))
            return redirect('utils:restore_database')
    
    # عرض صفحة الاستعادة
    return render(request, 'utils/restore.html', {
        'title': _('استعادة قاعدة البيانات'),
        'page_title': _('استعادة قاعدة البيانات'),
        'page_icon': 'fas fa-upload',
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': 'core:dashboard', 'icon': 'fas fa-home'},
            {'title': _('استعادة قاعدة البيانات'), 'active': True}
        ]
    })


@login_required
@user_passes_test(is_superuser)
def system_logs(request):
    """
    عرض سجلات النظام
    """
    from .logs import get_logs
    
    # الحصول على المعلمات من الطلب
    user_id = request.GET.get('user_id')
    model_name = request.GET.get('model_name')
    action = request.GET.get('action')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    try:
        # الحصول على السجلات مع تطبيق التصفية
        logs = get_logs(
            user_id=user_id,
            model_name=model_name,
            action=action,
            date_from=date_from,
            date_to=date_to
        )
        
        # التأكد من أن هناك سجلات حتى إذا كانت فارغة
        if logs is None:
            logs = []
    except Exception as e:
        # في حالة وجود خطأ، سجل الخطأ وأعد قائمة فارغة
        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في استرجاع سجلات النظام: {str(e)}")
        logs = []
    
    # عرض صفحة السجلات
    return render(request, 'utils/logs.html', {
        'logs': logs,
        'title': _('سجلات النظام'),
        'page_title': _('سجلات النظام'),
        'page_icon': 'fas fa-history',
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': 'core:dashboard', 'icon': 'fas fa-home'},
            {'title': _('سجلات النظام'), 'active': True}
        ]
    })

class SystemLogView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    عرض سجلات النظام مع إمكانية التصفية حسب المستخدم والنموذج والإجراء والتاريخ
    """
    def test_func(self):
        """
        التحقق من أن المستخدم مشرف
        """
        return self.request.user.is_superuser

    def get(self, request):
        # الحصول على معايير التصفية من الطلب
        user_id = request.GET.get('user_id')
        model_name = request.GET.get('model_name')
        action = request.GET.get('action')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        # البدء بجميع السجلات
        logs = SystemLog.objects.all().order_by('-timestamp')
        
        # تطبيق التصفية إذا تم تقديم المعايير
        if user_id:
            logs = logs.filter(user_id=user_id)
        
        if model_name:
            logs = logs.filter(model_name=model_name)
        
        if action:
            logs = logs.filter(action=action)
        
        # معالجة نطاق التاريخ
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                logs = logs.filter(timestamp__date__gte=date_from_obj)
            except ValueError:
                messages.error(request, _("تنسيق تاريخ البداية غير صالح"))
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                # إضافة يوم واحد لتضمين اليوم المحدد بالكامل
                date_to_obj = date_to_obj + datetime.timedelta(days=1)
                logs = logs.filter(timestamp__date__lt=date_to_obj)
            except ValueError:
                messages.error(request, _("تنسيق تاريخ النهاية غير صالح"))
        
        # الحصول على القيم الفريدة للقوائم المنسدلة
        users = get_user_model().objects.filter(is_active=True).order_by('first_name', 'last_name')
        models = SystemLog.objects.values_list('model_name', flat=True).distinct().order_by('model_name')
        actions = SystemLog.objects.values_list('action', flat=True).distinct().order_by('action')
        
        context = {
            'logs': logs[:200],  # تحديد عدد السجلات لتجنب البطء
            'users': users,
            'models': models,
            'actions': actions,
            'title': _('سجلات النظام'),
            'page_title': _('سجلات النظام'),
            'page_icon': 'fas fa-history',
        }
        
        return render(request, 'utils/logs.html', context)

@login_required
def inventory_check(request):
    """
    فحص المخزون للتأكد من صحة البيانات وتحديد المنتجات منخفضة المخزون
    """
    # المنتجات التي بها مخزون أقل من الحد الأدنى
    low_stock_items = Stock.objects.filter(quantity__lt=models.F('product__min_stock'))

    # المنتجات التي نفذت من المخزون
    out_of_stock_items = Stock.objects.filter(quantity__lte=0)

    context = {
        'title': _('فحص المخزون'),
        'page_title': _('فحص المخزون'),
        'page_icon': 'fas fa-clipboard-check',
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': 'core:dashboard', 'icon': 'fas fa-home'},
            {'title': _('فحص المخزون'), 'active': True}
        ],
        'low_stock_items': low_stock_items,
        'out_of_stock_items': out_of_stock_items,
    }

    return render(request, 'utils/inventory_check.html', context)

@login_required
def system_help(request):
    """
    عرض صفحة المساعدة والدعم الفني
    """
    context = {
        'title': _('المساعدة والدعم'),
        'page_title': _('المساعدة والدعم'),
        'page_icon': 'fas fa-question-circle',
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': 'core:dashboard', 'icon': 'fas fa-home'},
            {'title': _('المساعدة والدعم'), 'active': True}
        ],
    }

    return render(request, 'utils/system_help.html', context)

@login_required
@user_passes_test(is_superuser)
def backup_system(request):
    """
    عمل نسخة احتياطية من النظام (واجهة لـ backup_database)
    """
    return backup_database(request) 