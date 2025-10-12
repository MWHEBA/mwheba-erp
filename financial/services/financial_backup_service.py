"""
خدمة النسخ الاحتياطي للبيانات المالية
"""
import os
import json
import gzip
import shutil
from datetime import datetime, date
from django.core import serializers
from django.db import transaction
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from typing import Dict, List, Optional, Any
import logging

from ..models.chart_of_accounts import ChartOfAccounts, AccountType, AccountGroup
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..models.enhanced_balance import BalanceSnapshot, AccountBalanceCache, BalanceAuditLog
from ..models.payment_sync import PaymentSyncOperation, PaymentSyncRule

logger = logging.getLogger(__name__)


class FinancialBackupService:
    """
    خدمة النسخ الاحتياطي المتقدمة للبيانات المالية
    """
    
    def __init__(self):
        self.backup_dir = getattr(settings, 'FINANCIAL_BACKUP_DIR', 
                                 os.path.join(settings.BASE_DIR, 'backups', 'financial'))
        self.ensure_backup_directory()
    
    def ensure_backup_directory(self):
        """إنشاء مجلد النسخ الاحتياطي إذا لم يكن موجوداً"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_full_backup(self, include_logs: bool = False) -> Dict:
        """
        إنشاء نسخة احتياطية كاملة للبيانات المالية
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"financial_full_backup_{timestamp}"
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        try:
            os.makedirs(backup_path, exist_ok=True)
            
            backup_info = {
                'backup_name': backup_name,
                'backup_path': backup_path,
                'timestamp': timestamp,
                'created_at': timezone.now().isoformat(),
                'type': 'full',
                'include_logs': include_logs,
                'models_backed_up': [],
                'files_created': [],
                'total_records': 0,
                'status': 'in_progress'
            }
            
            # النماذج المطلوب نسخها
            models_to_backup = [
                (AccountType, 'account_types'),
                (ChartOfAccounts, 'chart_of_accounts'),
                (AccountGroup, 'account_groups'),
                (AccountingPeriod, 'accounting_periods'),
                (JournalEntry, 'journal_entries'),
                (JournalEntryLine, 'journal_entry_lines'),
                (BalanceSnapshot, 'balance_snapshots'),
                (AccountBalanceCache, 'balance_cache'),
                (PaymentSyncRule, 'payment_sync_rules'),
            ]
            
            # إضافة السجلات إذا طُلبت
            if include_logs:
                models_to_backup.extend([
                    (BalanceAuditLog, 'balance_audit_logs'),
                    (PaymentSyncOperation, 'payment_sync_operations'),
                ])
            
            # نسخ كل نموذج
            for model_class, filename in models_to_backup:
                records_count = self._backup_model(
                    model_class, backup_path, filename
                )
                
                backup_info['models_backed_up'].append({
                    'model': model_class.__name__,
                    'filename': f"{filename}.json.gz",
                    'records_count': records_count
                })
                
                backup_info['total_records'] += records_count
                backup_info['files_created'].append(f"{filename}.json.gz")
            
            # إنشاء ملف معلومات النسخة الاحتياطية
            info_file = os.path.join(backup_path, 'backup_info.json')
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(backup_info, f, ensure_ascii=False, indent=2, default=str)
            
            backup_info['files_created'].append('backup_info.json')
            backup_info['status'] = 'completed'
            
            # إنشاء أرشيف مضغوط
            archive_path = f"{backup_path}.tar.gz"
            shutil.make_archive(backup_path, 'gztar', backup_path)
            
            # حذف المجلد المؤقت
            shutil.rmtree(backup_path)
            
            backup_info['archive_path'] = archive_path
            backup_info['archive_size'] = os.path.getsize(archive_path)
            
            logger.info(f"تم إنشاء النسخة الاحتياطية الكاملة: {backup_name}")
            return backup_info
            
        except Exception as e:
            backup_info['status'] = 'failed'
            backup_info['error'] = str(e)
            logger.error(f"خطأ في إنشاء النسخة الاحتياطية: {str(e)}")
            
            # تنظيف الملفات في حالة الخطأ
            if os.path.exists(backup_path):
                shutil.rmtree(backup_path)
            
            raise
    
    def _backup_model(self, model_class, backup_path: str, filename: str) -> int:
        """
        نسخ نموذج معين
        """
        try:
            # الحصول على جميع السجلات
            queryset = model_class.objects.all()
            records_count = queryset.count()
            
            if records_count == 0:
                logger.info(f"لا توجد سجلات لنسخها من {model_class.__name__}")
                return 0
            
            # تسلسل البيانات
            serialized_data = serializers.serialize('json', queryset, indent=2)
            
            # ضغط وحفظ البيانات
            file_path = os.path.join(backup_path, f"{filename}.json.gz")
            with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                f.write(serialized_data)
            
            logger.info(f"تم نسخ {records_count} سجل من {model_class.__name__}")
            return records_count
            
        except Exception as e:
            logger.error(f"خطأ في نسخ {model_class.__name__}: {str(e)}")
            raise
    
    def create_incremental_backup(self, since_date: datetime) -> Dict:
        """
        إنشاء نسخة احتياطية تدريجية (التغييرات فقط)
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"financial_incremental_backup_{timestamp}"
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        try:
            os.makedirs(backup_path, exist_ok=True)
            
            backup_info = {
                'backup_name': backup_name,
                'backup_path': backup_path,
                'timestamp': timestamp,
                'created_at': timezone.now().isoformat(),
                'type': 'incremental',
                'since_date': since_date.isoformat(),
                'models_backed_up': [],
                'files_created': [],
                'total_records': 0,
                'status': 'in_progress'
            }
            
            # النماذج مع حقول التاريخ
            models_with_dates = [
                (JournalEntry, 'journal_entries', 'created_at'),
                (JournalEntryLine, 'journal_entry_lines', 'created_at'),
                (BalanceSnapshot, 'balance_snapshots', 'created_at'),
                (BalanceAuditLog, 'balance_audit_logs', 'timestamp'),
                (PaymentSyncOperation, 'payment_sync_operations', 'created_at'),
            ]
            
            # نسخ السجلات المحدثة فقط
            for model_class, filename, date_field in models_with_dates:
                records_count = self._backup_model_incremental(
                    model_class, backup_path, filename, date_field, since_date
                )
                
                if records_count > 0:
                    backup_info['models_backed_up'].append({
                        'model': model_class.__name__,
                        'filename': f"{filename}.json.gz",
                        'records_count': records_count
                    })
                    
                    backup_info['total_records'] += records_count
                    backup_info['files_created'].append(f"{filename}.json.gz")
            
            # إنشاء ملف معلومات النسخة الاحتياطية
            info_file = os.path.join(backup_path, 'backup_info.json')
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(backup_info, f, ensure_ascii=False, indent=2, default=str)
            
            backup_info['files_created'].append('backup_info.json')
            backup_info['status'] = 'completed'
            
            # إنشاء أرشيف مضغوط
            archive_path = f"{backup_path}.tar.gz"
            shutil.make_archive(backup_path, 'gztar', backup_path)
            
            # حذف المجلد المؤقت
            shutil.rmtree(backup_path)
            
            backup_info['archive_path'] = archive_path
            backup_info['archive_size'] = os.path.getsize(archive_path)
            
            logger.info(f"تم إنشاء النسخة الاحتياطية التدريجية: {backup_name}")
            return backup_info
            
        except Exception as e:
            backup_info['status'] = 'failed'
            backup_info['error'] = str(e)
            logger.error(f"خطأ في إنشاء النسخة الاحتياطية التدريجية: {str(e)}")
            raise
    
    def _backup_model_incremental(
        self, 
        model_class, 
        backup_path: str, 
        filename: str, 
        date_field: str, 
        since_date: datetime
    ) -> int:
        """
        نسخ تدريجية لنموذج معين
        """
        try:
            # الحصول على السجلات المحدثة فقط
            filter_kwargs = {f"{date_field}__gte": since_date}
            queryset = model_class.objects.filter(**filter_kwargs)
            records_count = queryset.count()
            
            if records_count == 0:
                return 0
            
            # تسلسل البيانات
            serialized_data = serializers.serialize('json', queryset, indent=2)
            
            # ضغط وحفظ البيانات
            file_path = os.path.join(backup_path, f"{filename}.json.gz")
            with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                f.write(serialized_data)
            
            logger.info(f"تم نسخ {records_count} سجل محدث من {model_class.__name__}")
            return records_count
            
        except Exception as e:
            logger.error(f"خطأ في النسخ التدريجي لـ {model_class.__name__}: {str(e)}")
            raise
    
    def restore_backup(self, backup_path: str, selective_restore: List[str] = None) -> Dict:
        """
        استعادة نسخة احتياطية
        """
        try:
            restore_info = {
                'backup_path': backup_path,
                'started_at': timezone.now().isoformat(),
                'type': 'restore',
                'models_restored': [],
                'total_records_restored': 0,
                'status': 'in_progress'
            }
            
            # استخراج الأرشيف
            extract_path = backup_path.replace('.tar.gz', '_extract')
            shutil.unpack_archive(backup_path, extract_path)
            
            # قراءة معلومات النسخة الاحتياطية
            info_file = os.path.join(extract_path, 'backup_info.json')
            with open(info_file, 'r', encoding='utf-8') as f:
                backup_info = json.load(f)
            
            # استعادة كل نموذج
            with transaction.atomic():
                for model_info in backup_info['models_backed_up']:
                    model_name = model_info['model']
                    filename = model_info['filename']
                    
                    # تخطي إذا لم يكن في القائمة المحددة
                    if selective_restore and model_name not in selective_restore:
                        continue
                    
                    records_restored = self._restore_model(
                        extract_path, filename, model_name
                    )
                    
                    restore_info['models_restored'].append({
                        'model': model_name,
                        'records_restored': records_restored
                    })
                    
                    restore_info['total_records_restored'] += records_restored
            
            # تنظيف المجلد المؤقت
            shutil.rmtree(extract_path)
            
            restore_info['status'] = 'completed'
            restore_info['completed_at'] = timezone.now().isoformat()
            
            logger.info(f"تم استعادة النسخة الاحتياطية بنجاح")
            return restore_info
            
        except Exception as e:
            restore_info['status'] = 'failed'
            restore_info['error'] = str(e)
            logger.error(f"خطأ في استعادة النسخة الاحتياطية: {str(e)}")
            
            # تنظيف في حالة الخطأ
            if 'extract_path' in locals() and os.path.exists(extract_path):
                shutil.rmtree(extract_path)
            
            raise
    
    def _restore_model(self, extract_path: str, filename: str, model_name: str) -> int:
        """
        استعادة نموذج معين
        """
        try:
            file_path = os.path.join(extract_path, filename)
            
            if not os.path.exists(file_path):
                logger.warning(f"ملف {filename} غير موجود")
                return 0
            
            # قراءة البيانات المضغوطة
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                serialized_data = f.read()
            
            # استعادة البيانات
            records_restored = 0
            for deserialized_object in serializers.deserialize('json', serialized_data):
                deserialized_object.save()
                records_restored += 1
            
            logger.info(f"تم استعادة {records_restored} سجل من {model_name}")
            return records_restored
            
        except Exception as e:
            logger.error(f"خطأ في استعادة {model_name}: {str(e)}")
            raise
    
    def list_backups(self) -> List[Dict]:
        """
        قائمة النسخ الاحتياطية المتاحة
        """
        backups = []
        
        try:
            for item in os.listdir(self.backup_dir):
                if item.endswith('.tar.gz'):
                    backup_path = os.path.join(self.backup_dir, item)
                    backup_info = {
                        'name': item,
                        'path': backup_path,
                        'size': os.path.getsize(backup_path),
                        'created_at': datetime.fromtimestamp(
                            os.path.getctime(backup_path)
                        ).isoformat()
                    }
                    
                    # محاولة قراءة معلومات إضافية
                    try:
                        extract_path = backup_path.replace('.tar.gz', '_temp_extract')
                        shutil.unpack_archive(backup_path, extract_path)
                        
                        info_file = os.path.join(extract_path, 'backup_info.json')
                        if os.path.exists(info_file):
                            with open(info_file, 'r', encoding='utf-8') as f:
                                detailed_info = json.load(f)
                                backup_info.update({
                                    'type': detailed_info.get('type', 'unknown'),
                                    'total_records': detailed_info.get('total_records', 0),
                                    'models_count': len(detailed_info.get('models_backed_up', []))
                                })
                        
                        shutil.rmtree(extract_path)
                        
                    except Exception:
                        # إذا فشل في قراءة التفاصيل، استمر بالمعلومات الأساسية
                        pass
                    
                    backups.append(backup_info)
            
            # ترتيب حسب تاريخ الإنشاء
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            
        except Exception as e:
            logger.error(f"خطأ في قراءة قائمة النسخ الاحتياطية: {str(e)}")
        
        return backups
    
    def delete_backup(self, backup_name: str) -> bool:
        """
        حذف نسخة احتياطية
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            if os.path.exists(backup_path):
                os.remove(backup_path)
                logger.info(f"تم حذف النسخة الاحتياطية: {backup_name}")
                return True
            else:
                logger.warning(f"النسخة الاحتياطية غير موجودة: {backup_name}")
                return False
                
        except Exception as e:
            logger.error(f"خطأ في حذف النسخة الاحتياطية: {str(e)}")
            return False
    
    def cleanup_old_backups(self, keep_days: int = 30) -> Dict:
        """
        تنظيف النسخ الاحتياطية القديمة
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            deleted_count = 0
            total_size_freed = 0
            
            for backup in self.list_backups():
                backup_date = datetime.fromisoformat(backup['created_at'])
                
                if backup_date < cutoff_date:
                    total_size_freed += backup['size']
                    if self.delete_backup(backup['name']):
                        deleted_count += 1
            
            return {
                'deleted_count': deleted_count,
                'total_size_freed': total_size_freed,
                'cutoff_date': cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"خطأ في تنظيف النسخ الاحتياطية: {str(e)}")
            return {'error': str(e)}
    
    def verify_backup_integrity(self, backup_path: str) -> Dict:
        """
        التحقق من سلامة النسخة الاحتياطية
        """
        try:
            verification_result = {
                'backup_path': backup_path,
                'is_valid': True,
                'errors': [],
                'warnings': [],
                'files_checked': [],
                'total_records': 0
            }
            
            # استخراج مؤقت للتحقق
            extract_path = backup_path.replace('.tar.gz', '_verify_extract')
            shutil.unpack_archive(backup_path, extract_path)
            
            try:
                # التحقق من ملف المعلومات
                info_file = os.path.join(extract_path, 'backup_info.json')
                if not os.path.exists(info_file):
                    verification_result['errors'].append('ملف معلومات النسخة الاحتياطية مفقود')
                    verification_result['is_valid'] = False
                else:
                    with open(info_file, 'r', encoding='utf-8') as f:
                        backup_info = json.load(f)
                    
                    # التحقق من كل ملف
                    for model_info in backup_info.get('models_backed_up', []):
                        filename = model_info['filename']
                        file_path = os.path.join(extract_path, filename)
                        
                        if not os.path.exists(file_path):
                            verification_result['errors'].append(f'الملف مفقود: {filename}')
                            verification_result['is_valid'] = False
                        else:
                            # التحقق من إمكانية قراءة الملف
                            try:
                                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                                    data = f.read()
                                    # محاولة تحليل JSON
                                    json.loads(data)
                                
                                verification_result['files_checked'].append({
                                    'filename': filename,
                                    'status': 'valid',
                                    'expected_records': model_info.get('records_count', 0)
                                })
                                
                                verification_result['total_records'] += model_info.get('records_count', 0)
                                
                            except Exception as e:
                                verification_result['errors'].append(f'خطأ في قراءة {filename}: {str(e)}')
                                verification_result['is_valid'] = False
            
            finally:
                # تنظيف المجلد المؤقت
                shutil.rmtree(extract_path)
            
            return verification_result
            
        except Exception as e:
            return {
                'backup_path': backup_path,
                'is_valid': False,
                'errors': [f'خطأ في التحقق: {str(e)}']
            }
