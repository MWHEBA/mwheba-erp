#!/usr/bin/env python3
"""
سكريپت النشر المحسن - Enhanced Deploy Script
رفع الملفات للخادم مع مزامنة كاملة
"""

import os
import sys
import subprocess
import hashlib
import json
import argparse
from pathlib import Path
import fnmatch
import time

# Reconfigure stdout/stderr to use UTF-8 on Windows or systems with narrow locales
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

class DeploymentManager:
    def __init__(self, env_file=None, force=False):
        self.force = force
        self.uploaded_files = []
        
        # تحميل إعدادات من .env
        self.load_env_settings(env_file=env_file)
        
        # مسار المشروع
        self.project_root = Path.cwd()
        self.hash_file = self.project_root / ".deploy_hashes.json"
        self.ignored_patterns = self.load_gitignore_patterns()
        
        print("=" * 35)
        print(f"📁 المشروع: {self.project_root.name}")
        print(f"🖥️  الخادم: {self.server_ip}:{self.ssh_port}")

    def load_env_settings(self, env_file=None):
        """تحميل إعدادات SSH من ملف .env"""
        if env_file is None:
            env_file = Path('.env')
        
        # الإعدادات الافتراضية
        self.server_ip = "84.247.179.163"
        self.username = "mwhebaco"
        self.ssh_port = "2951"
        self.ssh_password = None
        self.private_key = None
        self.ssh_key_passphrase = None
        self.remote_path = "/home/mwhebaco/mwheba_erp"
        self.site_url = None
        self.db_name = ''
        self.db_user = ''
        self.db_password = ''
        self.python_version = "3.11"
        
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            if key == 'SSH_HOST':
                                self.server_ip = value
                            elif key == 'SSH_PORT':
                                self.ssh_port = value
                            elif key == 'SSH_USER':
                                self.username = value
                            elif key == 'SSH_PASSWORD':
                                if value and value != 'your_actual_password_here':
                                    self.ssh_password = value
                            elif key == 'SSH_KEY_PATH':
                                if value:
                                    self.private_key = value
                            elif key == 'SSH_KEY_PASSPHRASE':
                                if value:
                                    self.ssh_key_passphrase = value
                            elif key == 'SSH_REMOTE_PATH':
                                self.remote_path = value
                            elif key == 'SITE_URL':
                                if value:
                                    self.site_url = value
                            elif key == 'DB_NAME':
                                self.db_name = value
                            elif key == 'DB_USER':
                                self.db_user = value
                            elif key == 'DB_PASSWORD':
                                self.db_password = value
                            elif key == 'PYTHON_VERSION':
                                if value:
                                    self.python_version = value
            except Exception as e:
                print(f"⚠️  تحذير: لا يمكن قراءة ملف .env: {e}")

    def load_gitignore_patterns(self):
        """تحميل قائمة الاستثناءات من .gitignore"""
        patterns = []
        gitignore_path = self.project_root / ".gitignore"
        
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        patterns.append(line)
        
        # إضافة patterns أساسية فقط
        patterns.extend(['__pycache__', '*.pyc', '.deploy_hashes.json', '*.log', 'deploy_logs'])
        return patterns

    def is_ignored(self, file_path):
        """فحص ما إذا كان الملف مستثنى"""
        relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
        
        # استثناء للملفات المهمة
        important_files = [
            '.htaccess',
            'passenger_wsgi.py'
        ]
        
        if relative_path in important_files:
            return False
        
        # تجاهل مجلد deployments بالكامل
        if relative_path.startswith('deployments/') or relative_path == 'deployments':
            return True

        # تجاهل مجلد deploy_logs وكل محتوياته (root)
        if relative_path.startswith('deploy_logs/') or relative_path == 'deploy_logs':
            return True

        # تجاهل جميع ملفات .deploy_hashes.json في أي مكان
        if file_path.name == '.deploy_hashes.json':
            return True
        
        # تجاهل الملفات المخفية في root فقط (مثل .git, .env)
        # لكن لا تتجاهل الملفات داخل المجلدات العادية
        parts = relative_path.split('/')
        if parts[0].startswith('.'):
            return True
            
        for pattern in self.ignored_patterns:
            # تخطي الـ patterns الخاصة بالملفات المخفية
            if pattern.startswith('.'):
                continue
            
            # مقارنة المسار الكامل أو اسم الملف
            if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                return True
                
        return False

    def get_file_hash(self, file_path):
        """حساب hash للملف"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return None

    def get_all_files(self):
        """الحصول على جميع الملفات"""
        files = []
        for file_path in self.project_root.rglob('*'):
            if file_path.is_file() and not self.is_ignored(file_path):
                files.append(file_path)
        return files

    def _create_ssh_connection(self):
        """إنشاء اتصال SSH مع دعم Key + Passphrase أو Password"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # تحضير معاملات الاتصال
        connect_params = {
            'hostname': self.server_ip,
            'port': int(self.ssh_port),
            'username': self.username,
            'timeout': 30
        }
        
        # تحديد طريقة المصادقة
        if self.private_key:
            # تحديد المسار الكامل للمفتاح
            key_path = Path(self.private_key)
            
            # إذا كان المسار نسبي، جرب المشروع الحالي أولاً ثم ~/.ssh
            if not key_path.is_absolute():
                # جرب المسار النسبي من مجلد المشروع
                project_key = self.project_root / self.private_key
                if project_key.exists():
                    key_path = project_key
                else:
                    # جرب ~/.ssh/
                    home_key = Path.home() / '.ssh' / self.private_key
                    if home_key.exists():
                        key_path = home_key
                    else:
                        # جرب المسار كما هو
                        if not key_path.exists():
                            raise Exception(f"لم يتم العثور على المفتاح: {self.private_key}")
            
            if key_path.exists():
                try:
                    # تحميل المفتاح الخاص - محاولة أنواع مختلفة
                    pkey = None
                    
                    # بناء قائمة الأنواع المتاحة فقط
                    key_types = [('RSA', paramiko.RSAKey)]
                    
                    # إضافة الأنواع الأخرى إذا كانت متاحة
                    if hasattr(paramiko, 'DSSKey'):
                        key_types.append(('DSA', paramiko.DSSKey))
                    if hasattr(paramiko, 'ECDSAKey'):
                        key_types.append(('ECDSA', paramiko.ECDSAKey))
                    if hasattr(paramiko, 'Ed25519Key'):
                        key_types.append(('Ed25519', paramiko.Ed25519Key))
                    
                    last_error = None
                    for key_type_name, key_class in key_types:
                        try:
                            if self.ssh_key_passphrase:
                                pkey = key_class.from_private_key_file(
                                    str(key_path),
                                    password=self.ssh_key_passphrase
                                )
                            else:
                                pkey = key_class.from_private_key_file(str(key_path))
                            break  # نجح التحميل
                        except paramiko.ssh_exception.PasswordRequiredException as e:
                            # المفتاح يحتاج passphrase
                            last_error = "المفتاح محمي بـ passphrase ولكن SSH_KEY_PASSPHRASE غير موجود أو خاطئ في .env"
                            break
                        except paramiko.ssh_exception.SSHException as e:
                            last_error = str(e)
                            continue  # جرب النوع التالي
                        except Exception as e:
                            last_error = str(e)
                            continue
                    
                    if pkey:
                        connect_params['pkey'] = pkey
                    else:
                        raise Exception(last_error or "فشل تحميل المفتاح - نوع غير مدعوم")
                        
                except Exception as e:
                    # Fallback لكلمة المرور
                    if self.ssh_password:
                        print(f"⚠️  فشل استخدام SSH Key: {e}")
                        print(f"🔄 محاولة استخدام كلمة المرور...")
                        connect_params['password'] = self.ssh_password
                    else:
                        raise Exception(f"فشل تحميل SSH Key ولا توجد كلمة مرور: {e}")
        elif self.ssh_password:
            connect_params['password'] = self.ssh_password
        else:
            raise Exception("لا توجد طريقة مصادقة متاحة")
        
        ssh.connect(**connect_params)
        return ssh

    def get_modified_files_vs_remote(self):
        """الحصول على الملفات المعدلة بالمقارنة مع الخادم - محسن للسرعة"""
        print("🔍 مقارنة مع الخادم...")
        
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            # الحصول على جميع الملفات المحلية
            local_files = self.get_all_files()
            local_files_dict = {}
            
            for file_path in local_files:
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                stat = file_path.stat()
                local_files_dict[relative_path] = {
                    'path': file_path,
                    'size': stat.st_size,
                    'mtime': int(stat.st_mtime)
                }
            
            # الحصول على جميع الملفات البعيدة
            remote_files_dict = {}
            self.get_remote_files_with_stats(sftp, self.remote_path, remote_files_dict)
            
            # تحديد الملفات المعدلة/الجديدة بسرعة
            modified_files = []
            new_count = 0
            size_diff_count = 0
            time_diff_count = 0
            
            for relative_path, local_info in local_files_dict.items():
                if relative_path not in remote_files_dict:
                    # ملف جديد
                    modified_files.append(local_info['path'])
                    new_count += 1
                else:
                    # مقارنة سريعة
                    remote_info = remote_files_dict[relative_path]
                    
                    # الحجم مختلف = معدل بالتأكيد
                    if local_info['size'] != remote_info['size']:
                        modified_files.append(local_info['path'])
                        size_diff_count += 1
                    else:
                        # فرق زمني معقول = معدل
                        time_diff = abs(local_info['mtime'] - remote_info['mtime'])
                        if 60 < time_diff < 86400:  # بين دقيقة ويوم
                            modified_files.append(local_info['path'])
                            time_diff_count += 1
            
            sftp.close()
            ssh.close()
            
            # ملخص مختصر
            total_modified = len(modified_files)
            if total_modified > 0:
                print(f"📊 {total_modified} ملف يحتاج رفع:")
                if new_count > 0:
                    print(f"   📄 {new_count} جديد")
                if size_diff_count > 0:
                    print(f"   📏 {size_diff_count} حجم مختلف")
                if time_diff_count > 0:
                    print(f"   ⏰ {time_diff_count} معدل حديثاً")
            else:
                print("✅ جميع الملفات محدثة")
            
            return modified_files
            
        except Exception as e:
            print(f"❌ خطأ في المقارنة: {e}")
            return []



    def test_connection(self):
        """اختبار الاتصال"""
        print("🔍 اختبار الاتصال...")
        
        if not PARAMIKO_AVAILABLE:
            print("❌ مكتبة paramiko غير متاحة!")
            return False
        
        # تحديد طريقة المصادقة
        auth_method = None
        key_path_found = None
        
        if self.private_key:
            # البحث عن المفتاح
            key_path = Path(self.private_key)
            
            if not key_path.is_absolute():
                # جرب المسار النسبي من مجلد المشروع
                project_key = self.project_root / self.private_key
                if project_key.exists():
                    key_path_found = project_key
                else:
                    # جرب ~/.ssh/
                    home_key = Path.home() / '.ssh' / self.private_key
                    if home_key.exists():
                        key_path_found = home_key
                    else:
                        # جرب المسار كما هو
                        if key_path.exists():
                            key_path_found = key_path
            else:
                if key_path.exists():
                    key_path_found = key_path
            
            if key_path_found:
                auth_method = 'key'
                print(f"🔐 استخدام SSH Key: {key_path_found}")
                if self.ssh_key_passphrase:
                    print(f"🔑 مع passphrase من .env")
            else:
                print(f"⚠️  لم يتم العثور على المفتاح: {self.private_key}")
                print(f"   تم البحث في:")
                print(f"   • {self.project_root / self.private_key}")
                print(f"   • {Path.home() / '.ssh' / self.private_key}")
                if self.ssh_password:
                    print(f"🔄 سيتم استخدام كلمة المرور بدلاً من ذلك")
                    auth_method = 'password'
                else:
                    print("❌ لا توجد كلمة مرور للاستخدام كبديل")
                    return False
        
        if not auth_method and self.ssh_password:
            auth_method = 'password'
            print(f"🔐 استخدام كلمة المرور من .env")
        
        if not auth_method:
            print("❌ لا توجد طريقة مصادقة متاحة (SSH Key أو Password)")
            print("💡 تأكد من إضافة SSH_PASSWORD أو SSH_KEY_PATH في ملف .env")
            return False
        
        try:
            ssh = self._create_ssh_connection()
            
            # اختبار تنفيذ أمر بسيط
            stdin, stdout, stderr = ssh.exec_command("echo 'اتصال ناجح'")
            result = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            
            ssh.close()
            
            if result == 'اتصال ناجح':
                print(f"✅ الاتصال ناجح! ({self.username}@{self.server_ip}:{self.ssh_port})")
                if self.site_url:
                    print(f"🌐 الموقع: {self.site_url}")
                print(f"📁 المسار: {self.remote_path}")
                self.use_paramiko = True
                return True
            else:
                print(f"❌ خطأ في تنفيذ الأمر: {error}")
                return False
                
        except paramiko.AuthenticationException as e:
            print("❌ خطأ في المصادقة!")
            print(f"\n📋 معلومات الاتصال المستخدمة:")
            print(f"   • الخادم: {self.server_ip}")
            print(f"   • المنفذ: {self.ssh_port}")
            print(f"   • المستخدم: {self.username}")
            
            if auth_method == 'key':
                print(f"   • المفتاح: {key_path_found}")
                print(f"   • Passphrase: {'موجود' if self.ssh_key_passphrase else 'غير موجود'}")
                print(f"\n💡 تحقق من:")
                print("   • صحة SSH_KEY_PASSPHRASE (قد يكون خاطئ)")
                print("   • صلاحيات الملف (يجب أن تكون 600 أو 400)")
                print("   • أن المفتاح العام مضاف في ~/.ssh/authorized_keys على السيرفر")
            else:
                print(f"   • كلمة المرور: {'*' * len(self.ssh_password) if self.ssh_password else 'غير موجودة'}")
                print(f"\n💡 تحقق من:")
                print("   • صحة SSH_USER في .env")
                print("   • صحة SSH_PASSWORD في .env")
                print("   • أن المستخدم موجود على السيرفر")
                print("   • أن SSH password authentication مفعّل على السيرفر")
            
            return False
        except paramiko.SSHException as e:
            print(f"❌ خطأ SSH: {e}")
            return False
        except Exception as e:
            print(f"❌ خطأ في الاتصال: {e}")
            return False

    def upload_files(self, files):
        """رفع الملفات"""
        if not files:
            print("📝 لا توجد ملفات للرفع")
            return True
            
        print(f"📤 رفع {len(files)} ملف...")
        
        # إنشاء مجلد مؤقت
        temp_dir = self.project_root / ".temp_deploy"
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # نسخ الملفات
            import shutil
            for file_path in files:
                if not file_path.exists():
                    continue
                    
                relative_path = file_path.relative_to(self.project_root)
                temp_file_path = temp_dir / relative_path
                temp_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # محاولة نسخ الملف مع معالجة الأخطاء
                try:
                    shutil.copy2(file_path, temp_file_path)
                except PermissionError:
                    print(f"⚠️  تخطي ملف مقفل: {relative_path}")
                    continue
                except Exception as e:
                    print(f"⚠️  خطأ في نسخ {relative_path}: {e}")
                    continue
            
            # رفع الملفات
            return self.upload_with_paramiko(temp_dir)
                
        finally:
            # حذف المجلد المؤقت مع معالجة الأخطاء
            import shutil
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except PermissionError:
                    print("⚠️  لا يمكن حذف المجلد المؤقت (ملفات مقفلة)")
                except:
                    pass

    def _create_remote_directories(self, sftp, remote_file):
        """إنشاء جميع المجلدات المطلوبة في المسار البعيد"""
        remote_dir = '/'.join(remote_file.split('/')[:-1])
        if remote_dir != self.remote_path:
            # إنشاء المجلدات بالتسلسل
            path_parts = remote_dir.replace(self.remote_path + '/', '').split('/')
            current_path = self.remote_path
            for part in path_parts:
                if part:
                    current_path = f"{current_path}/{part}"
                    try:
                        sftp.mkdir(current_path)
                    except:
                        pass  # المجلد موجود بالفعل

    def upload_with_smart_skip(self, files):
        """رفع الملفات مع تخطي المطابق 100%"""
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            total_files = len(files)
            uploaded = 0
            skipped = 0
            uploaded_files = []  # قائمة الملفات المرفوعة
            skipped_examples = []
            start_time = time.time()
            
            print(f"📤 بدء الرفع...")
            
            for i, file_path in enumerate(files):
                # تخطي الملفات غير الموجودة محلياً
                if not file_path.exists():
                    skipped += 1
                    continue
                
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                # فحص سريع - هل الملف مطابق 100%؟
                should_skip = False
                try:
                    remote_stat = sftp.stat(remote_file)
                    local_stat = file_path.stat()
                    
                    # مقارنة الحجم فقط - أكثر دقة من التوقيت
                    if remote_stat.st_size == local_stat.st_size:
                        # إذا كان الحجم متطابق، نفترض أن الملف مطابق
                        # (لتجنب مشاكل المناطق الزمنية)
                        should_skip = True
                        skipped += 1
                        if len(skipped_examples) < 15:
                            skipped_examples.append(relative_path)
                        
                except:
                    # الملف غير موجود أو خطأ - سيتم رفعه
                    should_skip = False
                
                # عرض التقدم
                percentage = ((i + 1) / total_files) * 100
                elapsed = time.time() - start_time
                remaining = total_files - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // total_files)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                print(f"\r[{bar}] {percentage:.1f}% - رفع: {uploaded}, تخطي: {skipped} - متبقي: {eta_text}", end='', flush=True)
                
                if should_skip:
                    continue
                
                # رفع الملف
                try:
                    # إنشاء جميع المجلدات في المسار
                    self._create_remote_directories(sftp, remote_file)
                    
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)
                    
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
            
            print()
            sftp.close()
            ssh.close()
            
            total_time = time.time() - start_time
            print(f"✅ اكتمل في {total_time:.1f}ث - رفع: {uploaded}, تخطي: {skipped}")
            
            # عرض تفاصيل الملفات المرفوعة
            if uploaded_files:
                print(f"\n📋 الملفات المرفوعة ({len(uploaded_files)}):")
                display_count = min(12, len(uploaded_files))
                for f in uploaded_files[:display_count]:
                    print(f"   ✅ {f}")
                if len(uploaded_files) > display_count:
                    print(f"   ... و {len(uploaded_files) - display_count} ملف آخر")
                
                # حفظ قائمة مفصلة في ملف
                self._save_upload_log(uploaded_files, "رفع كامل مع تخطي")
            
            self.uploaded_files = uploaded_files
            
            # عرض أمثلة الملفات المتخطاة
            if skipped_examples:
                print(f"\n📋 أمثلة الملفات المتخطاة (حجم مطابق):")
                for example in skipped_examples:
                    print(f"   ⏭️  {example}")
                if skipped > len(skipped_examples):
                    print(f"   ... و {skipped - len(skipped_examples)} ملف آخر")
            
            return True
            
        except Exception as e:
            print(f"\n❌ خطأ في الرفع: {e}")
            return False

    def upload_all_files(self, files):
        """رفع جميع الملفات مع استبدال (بدون تخطي)"""
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            total_files = len(files)
            uploaded = 0
            uploaded_files = []  # قائمة الملفات المرفوعة
            start_time = time.time()
            
            print(f"📤 رفع {total_files} ملف...")
            
            for i, file_path in enumerate(files):
                # تخطي الملفات غير الموجودة محلياً
                if not file_path.exists():
                    continue
                
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                try:
                    # إنشاء المجلدات
                    self._create_remote_directories(sftp, remote_file)
                    
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)
                    
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
                
                # عرض التقدم
                percentage = ((i + 1) / total_files) * 100
                elapsed = time.time() - start_time
                remaining = total_files - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // total_files)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                print(f"\r[{bar}] {percentage:.1f}% - رفع: {uploaded} - متبقي: {eta_text}", end='', flush=True)
            
            print()
            sftp.close()
            ssh.close()
            
            total_time = time.time() - start_time
            print(f"✅ تم رفع {uploaded} ملف في {total_time:.1f}ث")
            
            # عرض تفاصيل الملفات المرفوعة
            if uploaded_files:
                print(f"\n📋 الملفات المرفوعة ({len(uploaded_files)}):")
                display_count = min(15, len(uploaded_files))
                for f in uploaded_files[:display_count]:
                    print(f"   ✅ {f}")
                if len(uploaded_files) > display_count:
                    print(f"   ... و {len(uploaded_files) - display_count} ملف آخر")
                
                # حفظ قائمة مفصلة في ملف
                self._save_upload_log(uploaded_files, "رفع كامل مع استبدال")
            
            self.uploaded_files = uploaded_files
            return True
            
        except Exception as e:
            print(f"\n❌ خطأ في الرفع: {e}")
            return False

    def upload_modified_only(self, files):
        """رفع الملفات المعدلة فقط (مقارنة hash محلي)"""
        print("🔍 مقارنة مع آخر نشر...")
        
        # تحميل hashes السابقة
        previous_hashes = {}
        if self.hash_file.exists():
            try:
                with open(self.hash_file, 'r', encoding='utf-8') as f:
                    previous_hashes = json.load(f)
            except:
                print("⚠️  لا يمكن قراءة ملف hashes السابق")
        
        # تحديد الملفات المعدلة
        modified_files = []
        new_files = []
        changed_files = []
        uploaded_files = []  # قائمة الملفات المرفوعة فعلياً
        
        for file_path in files:
            # تخطي الملفات غير الموجودة محلياً
            if not file_path.exists():
                continue
            
            relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
            current_hash = self.get_file_hash(file_path)
            
            if relative_path not in previous_hashes:
                # ملف جديد
                modified_files.append(file_path)
                new_files.append(relative_path)
            elif previous_hashes[relative_path] != current_hash:
                # ملف معدل
                modified_files.append(file_path)
                changed_files.append(relative_path)
        
        if not modified_files:
            print("✅ جميع الملفات محدثة منذ آخر نشر!")
            return True
        
        print(f"📊 {len(new_files)} ملف جديد، {len(changed_files)} ملف معدل")
        
        # عرض تفاصيل أكتر للملفات الجديدة
        if new_files:
            print("📄 الملفات الجديدة:")
            display_count = min(10, len(new_files))  # عرض أول 10 ملفات
            for f in new_files[:display_count]:
                print(f"   + {f}")
            if len(new_files) > display_count:
                print(f"   ... و {len(new_files) - display_count} ملف جديد آخر")
        
        # عرض تفاصيل أكتر للملفات المعدلة
        if changed_files:
            print("📝 الملفات المعدلة:")
            display_count = min(10, len(changed_files))  # عرض أول 10 ملفات
            for f in changed_files[:display_count]:
                print(f"   ~ {f}")
            if len(changed_files) > display_count:
                print(f"   ... و {len(changed_files) - display_count} ملف معدل آخر")
        
        print(f"\n📤 رفع {len(modified_files)} ملف...")
        
        # رفع الملفات المعدلة فقط
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            uploaded = 0
            start_time = time.time()
            
            for i, file_path in enumerate(modified_files):
                # تخطي الملفات غير الموجودة محلياً
                if not file_path.exists():
                    continue
                
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                try:
                    # إنشاء المجلدات
                    self._create_remote_directories(sftp, remote_file)
                    
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)  # إضافة للقائمة المرفوعة
                    
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
                
                # عرض التقدم
                percentage = ((i + 1) / len(modified_files)) * 100
                elapsed = time.time() - start_time
                remaining = len(modified_files) - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // len(modified_files))
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                print(f"\r[{bar}] {percentage:.1f}% - رفع: {uploaded} - متبقي: {eta_text}", end='', flush=True)
            
            print()
            sftp.close()
            ssh.close()
            
            total_time = time.time() - start_time
            skipped = len(files) - len(modified_files)
            print(f"✅ رفع: {uploaded}, تخطي: {skipped} في {total_time:.1f}ث")
            
            # عرض تفاصيل الملفات المرفوعة فعلياً
            if uploaded_files:
                print(f"\n📋 الملفات المرفوعة ({len(uploaded_files)}):")
                
                # تصنيف الملفات المرفوعة
                uploaded_new = [f for f in uploaded_files if f in new_files]
                uploaded_changed = [f for f in uploaded_files if f in changed_files]
                
                if uploaded_new:
                    print(f"   📄 جديد ({len(uploaded_new)}):")
                    display_count = min(8, len(uploaded_new))
                    for f in uploaded_new[:display_count]:
                        print(f"      ✅ {f}")
                    if len(uploaded_new) > display_count:
                        print(f"      ... و {len(uploaded_new) - display_count} ملف جديد آخر")
                
                if uploaded_changed:
                    print(f"   📝 معدل ({len(uploaded_changed)}):")
                    display_count = min(8, len(uploaded_changed))
                    for f in uploaded_changed[:display_count]:
                        print(f"      ✅ {f}")
                    if len(uploaded_changed) > display_count:
                        print(f"      ... و {len(uploaded_changed) - display_count} ملف معدل آخر")
                
                # حفظ قائمة مفصلة في ملف
                self._save_upload_log(uploaded_files, "رفع المعدل فقط")
            
            self.uploaded_files = uploaded_files
            return True
            
        except Exception as e:
            print(f"\n❌ خطأ في الرفع: {e}")
            return False

    def deploy_all(self):
        """رفع جميع الملفات مع استبدال"""
        print("\n🔄 رفع جميع الملفات مع استبدال...")
        
        if not self.test_connection():
            return False
            
        files = self.get_all_files()
        print(f"📊 {len(files)} ملف للرفع")
        
        confirm = input(f"❓ رفع {len(files)} ملف مع استبدال؟ (y/N): ").lower()
        if confirm != 'y':
            print("❌ تم الإلغاء")
            return False
            
        success = self.upload_all_files(files)
        
        if success:
            # حفظ hashes
            is_first_deploy = not self.hash_file.exists()
            current_hashes = {}
            for file_path in files:
                relative_path = str(file_path.relative_to(self.project_root))
                current_hashes[relative_path] = self.get_file_hash(file_path)
            
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(current_hashes, f, indent=2, ensure_ascii=False)

            self.run_post_deploy_commands(first_deploy=is_first_deploy)
            
        return success

    def deploy_modified(self):
        """رفع الملفات مع خيارات متعددة"""
        print("\n🔄 رفع الملفات...")
        
        if not self.test_connection():
            return False
            
        all_files = self.get_all_files()
        print(f"📊 {len(all_files)} ملف للفحص")
        
        print("\n📋 اختر طريقة الرفع:")
        print("1️⃣  رفع كامل مع استبدال (يرفع كل شيء - بطيء)")
        print("2️⃣  رفع كامل مع تخطي (مقارنة مع الخادم - متوسط)")
        print("3️⃣  رفع المعدل فقط (مقارنة hash محلي - سريع جداً)")
        print("❌ أي رقم آخر للإلغاء")
        
        choice = input("\n❓ اختيارك (1/2/3): ").strip()
        
        if choice == "1":
            print("🔄 رفع كامل مع استبدال...")
            print("📝 سيتم رفع جميع الملفات مع استبدال الموجود")
            success = self.upload_all_files(all_files)
            method_name = "رفع كامل مع استبدال"
        elif choice == "2":
            print("🔄 رفع كامل مع تخطي المطابق...")
            print("📝 سيتم فحص كل ملف ورفع المختلف فقط")
            success = self.upload_with_smart_skip(all_files)
            method_name = "رفع كامل مع تخطي"
        elif choice == "3":
            print("🔄 رفع المعدل فقط...")
            print("📝 سيتم رفع الملفات الجديدة والمعدلة منذ آخر نشر فقط")
            success = self.upload_modified_only(all_files)
            method_name = "رفع المعدل فقط"
        else:
            print("❌ تم الإلغاء")
            return False
        
        if success:
            # حفظ hashes الجديدة
            is_first_deploy = not self.hash_file.exists()
            current_hashes = {}
            for file_path in all_files:
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                current_hashes[relative_path] = self.get_file_hash(file_path)
            
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(current_hashes, f, indent=2, ensure_ascii=False)
            
            print(f"\n🎉 تم بنجاح! الطريقة المستخدمة: {method_name}")
            self.run_post_deploy_commands(first_deploy=is_first_deploy)
            
        return success

    def deploy_single_file(self, filename):
        """رفع ملف واحد محدد"""
        print(f"\n🔄 رفع ملف: {filename}")
        
        file_path = self.project_root / filename
        if not file_path.exists():
            print(f"❌ الملف غير موجود: {filename}")
            return False
        
        # استثناء خاص للملفات المهمة حتى لو كانت مستثناة في .gitignore
        important_files = [
            'core/security/file_validators_temp.py',
            'core/security/__init__.py',
            'passenger_wsgi.py',
            '.htaccess'
        ]
        
        if filename not in important_files and self.is_ignored(file_path):
            print(f"❌ الملف مستثنى: {filename}")
            return False
        
        if not self.test_connection():
            return False
        
        # رفع الملف مباشرة بدون مجلد مؤقت
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            # تحديد المسار البعيد
            relative_path = file_path.relative_to(self.project_root)
            remote_file = f"{self.remote_path}/{relative_path}".replace('\\', '/')
            
            # إنشاء المجلد البعيد إذا لزم الأمر
            remote_dir = '/'.join(remote_file.split('/')[:-1])
            if remote_dir and remote_dir != self.remote_path:
                try:
                    sftp.mkdir(remote_dir)
                except:
                    pass
            
            print(f"📤 رفع الملف...")
            sftp.put(str(file_path), remote_file)
            
            sftp.close()
            ssh.close()
            
            print("✅ تم الرفع بنجاح!")
            
            # تحديث hash الملف
            previous_hashes = {}
            if self.hash_file.exists():
                try:
                    with open(self.hash_file, 'r', encoding='utf-8') as f:
                        previous_hashes = json.load(f)
                except:
                    pass
            
            relative_path_str = str(relative_path).replace('\\', '/')
            previous_hashes[relative_path_str] = self.get_file_hash(file_path)
            
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(previous_hashes, f, indent=2, ensure_ascii=False)
            
            self.uploaded_files = [filename]
            self.run_post_deploy_commands(first_deploy=False)
            return True
            
        except Exception as e:
            print(f"❌ خطأ في الرفع: {e}")
            return False

    def run_post_deploy_commands(self, first_deploy=False):
        """تنفيذ أوامر ما بعد الرفع على السيرفر"""
        remote_app_name = Path(self.remote_path).name
        venv = f"/home/{self.username}/virtualenv/{remote_app_name}/{self.python_version}/bin/python"
        manage = f"{self.remote_path}/manage.py"
        pip = f"/home/{self.username}/virtualenv/{remote_app_name}/{self.python_version}/bin/pip"

        # أوامر أول deploy فقط
        setup_commands = [
            (f"{pip} install -r {self.remote_path}/requirements.txt",
             "تثبيت متطلبات المشروع لأول مرة (pip install)"),
        ]

        # تحويل charset لو عندنا credentials
        if self.db_name and self.db_user and self.db_password:
            setup_commands.append((
                f"mysql -u {self.db_user} -p'{self.db_password}' -e \"ALTER DATABASE {self.db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\"",
                f"ALTER DATABASE {self.db_name} → utf8mb4"
            ))

        setup_commands += [
            (f"{venv} {manage} migrate --noinput",
             "عمل ميجريشن لقاعدة البيانات (migrate)"),
            (f"{venv} {manage} collectstatic --noinput",
             "تجميع الملفات الثابتة (collectstatic)"),
            (f"{venv} {manage} loaddata core/fixtures/system_modules.json",
             "تحميل موديولات النظام (loaddata system_modules)"),
            (f"{venv} {manage} loaddata core/fixtures/system_settings_final.json",
             "تحميل إعدادات النظام (loaddata system_settings)"),
        ]

        if first_deploy:
            try:
                ssh = self._create_ssh_connection()
                print("\n🚀 أول deploy - تنفيذ إعداد النظام...")
                for cmd, label in setup_commands:
                    print(f"  ⏳ {label}...")
                    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
                    exit_code = stdout.channel.recv_exit_status()
                    out = stdout.read().decode().strip()
                    err = stderr.read().decode().strip()
                    if exit_code == 0:
                        print(f"  ✅ {label}")
                    else:
                        print(f"  ❌ {label}")
                        if err:
                            print(f"     {err[-200:]}")  # آخر 200 حرف من الخطأ

                # إعادة تشغيل التطبيق بعد الإعداد الأول
                reload_cmd = f"/usr/sbin/cloudlinux-selector restart --json --interpreter python --app-root {remote_app_name}"
                stdin, stdout, stderr = ssh.exec_command(reload_cmd, timeout=300)
                exit_code = stdout.channel.recv_exit_status()
                if exit_code == 0:
                    print(f"  ✅ إعادة تشغيل تطبيق الويب (restart)")
                else:
                    # محاولة لمس ملف passenger_wsgi.py كبديل
                    touch_cmd = f"touch {self.remote_path}/passenger_wsgi.py"
                    ssh.exec_command(touch_cmd)
                    print(f"  ✅ إعادة تشغيل تطبيق الويب (عبر touch passenger_wsgi.py)")

                print("\n⚠️  لازم تعمل superuser يدوياً:")
                print(f"  python manage.py createsuperuser")
                ssh.close()
            except Exception as e:
                print(f"  ⚠️  تعذّر تنفيذ إعداد النشر الأول: {e}")
            return

        # للنشر المتتابع (ليس النشر الأول) - تشغيل التحديث الذكي تلقائياً
        run_pip = False
        run_migrate = False
        run_collectstatic = False
        run_reload = False

        # ذكي: كشف التغييرات التلقائية
        has_reqs = False
        has_migrations = False
        has_static = False
        has_py = False

        uploaded_list = getattr(self, 'uploaded_files', []) or []
        for file_path in uploaded_list:
            file_name = str(file_path).lower().replace('\\', '/')
            if 'requirements.txt' in file_name:
                has_reqs = True
            if '/migrations/' in file_name and file_name.endswith('.py') and not file_name.endswith('__init__.py'):
                has_migrations = True
            if 'static/' in file_name:
                has_static = True
            if file_name.endswith('.py'):
                has_py = True

        run_pip = has_reqs
        run_migrate = has_migrations
        run_collectstatic = has_static
        run_reload = has_py or has_migrations or has_reqs

        print("\n🔍 التحديث الذكي التلقائي اكتشف:")
        if run_pip:
            print("   📦 تعديل في requirements.txt → سيتم تثبيت المتطلبات")
        if run_migrate:
            print("   🗄️  تعديل في ملفات الميجريشن → سيتم عمل الميجريشن")
        if run_collectstatic:
            print("   🎨 تعديل في الملفات الثابتة → سيتم عمل كولكت الستاتيك")
        if run_reload:
            print("   💻 تعديل في ملفات الكود (Python) → سيتم إعادة تشغيل التطبيق")
        
        if not (run_pip or run_migrate or run_collectstatic or run_reload):
            print("   ⏭️  لم يتم كشف أي تغييرات تتطلب تثبيت متطلبات أو ميجريشن أو كولكت ستاتيك.")
            print("   💻 سيتم إعادة تشغيل التطبيق للاحتياط.")
            run_reload = True

        # تجهيز قائمة الأوامر للتشغيل
        exec_commands = []
        if run_pip:
            exec_commands.append((f"{pip} install -r {self.remote_path}/requirements.txt", "تثبيت متطلبات المشروع (pip install)"))
        if run_migrate:
            exec_commands.append((f"{venv} {manage} migrate --noinput", "عمل ميجريشن لقاعدة البيانات (migrate)"))
        if run_collectstatic:
            exec_commands.append((f"{venv} {manage} collectstatic --noinput", "تجميع الملفات الثابتة (collectstatic)"))

        # تنفيذ الأوامر
        if exec_commands or run_reload:
            try:
                ssh = self._create_ssh_connection()
                print("\n⚙️  تنفيذ أوامر ما بعد النشر...")

                for cmd, label in exec_commands:
                    print(f"  ⏳ {label}...")
                    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
                    exit_code = stdout.channel.recv_exit_status()
                    out = stdout.read().decode().strip()
                    err = stderr.read().decode().strip()
                    if exit_code == 0:
                        print(f"  ✅ {label}")
                    else:
                        print(f"  ❌ {label}")
                        if err:
                            print(f"     {err[-200:]}")

                if run_reload:
                    print("  ⏳ إعادة تشغيل تطبيق الويب (restart)...")
                    reload_cmd = f"/usr/sbin/cloudlinux-selector restart --json --interpreter python --app-root {remote_app_name}"
                    stdin, stdout, stderr = ssh.exec_command(reload_cmd, timeout=120)
                    exit_code = stdout.channel.recv_exit_status()
                    if exit_code == 0:
                        print(f"  ✅ إعادة تشغيل تطبيق الويب (restart)")
                    else:
                        # محاولة لمس ملف passenger_wsgi.py كبديل
                        touch_cmd = f"touch {self.remote_path}/passenger_wsgi.py"
                        ssh.exec_command(touch_cmd)
                        print(f"  ✅ إعادة تشغيل تطبيق الويب (عبر touch passenger_wsgi.py)")

                ssh.close()
            except Exception as e:
                print(f"  ⚠️  تعذّر تنفيذ أوامر ما بعد النشر: {e}")

    def show_status(self):
        print("\n📊 حالة الملفات:")
        
        all_files = self.get_all_files()
        print(f"📁 إجمالي الملفات: {len(all_files)}")
        
        if not self.test_connection():
            return
            
        print("🔍 فحص سريع...")
        
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            identical = 0
            different = 0
            
            for file_path in all_files[:100]:  # فحص أول 100 ملف فقط للسرعة
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                try:
                    remote_stat = sftp.stat(remote_file)
                    local_stat = file_path.stat()
                    
                    if (remote_stat.st_size == local_stat.st_size and 
                        abs(remote_stat.st_mtime - local_stat.st_mtime) <= 5):
                        identical += 1
                    else:
                        different += 1
                except:
                    different += 1
            
            sftp.close()
            ssh.close()
            
            print(f"✅ مطابق (من أول 100): {identical}")
            print(f"📝 مختلف (من أول 100): {different}")
            
        except Exception as e:
            print(f"❌ خطأ في الفحص: {e}")

    def sync_all(self):
        """رفع مع تخطي المطابق"""
        print("\n🔄 رفع مع تخطي المطابق...")
        
        if not self.test_connection():
            return False
            
        files = self.get_all_files()
        print(f"📊 {len(files)} ملف للفحص")
        
        confirm = input(f"❓ بدء الرفع مع تخطي المطابق؟ (y/N): ").lower()
        if confirm != 'y':
            print("❌ تم الإلغاء")
            return False
            
        success = self.upload_with_smart_skip(files)
        
        if success:
            # حفظ hashes الجديدة
            current_hashes = {}
            for file_path in files:
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                current_hashes[relative_path] = self.get_file_hash(file_path)
            
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(current_hashes, f, indent=2, ensure_ascii=False)
            
        return success

    def sync_with_cleanup(self, local_files):
        """مزامنة ذكية - محسن للسرعة"""
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            print("🔍 مقارنة مع الخادم...")
            
            # الحصول على قائمة الملفات المحلية
            local_files_dict = {}
            for file_path in local_files:
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                stat = file_path.stat()
                local_files_dict[relative_path] = {
                    'path': file_path,
                    'size': stat.st_size,
                    'mtime': int(stat.st_mtime)
                }
            
            # الحصول على قائمة الملفات البعيدة
            remote_files_dict = {}
            self.get_remote_files_with_stats(sftp, self.remote_path, remote_files_dict)
            
            # تحديد الملفات للرفع والحذف بسرعة
            files_to_upload = []
            new_count = 0
            modified_count = 0
            
            for relative_path, local_info in local_files_dict.items():
                if relative_path not in remote_files_dict:
                    files_to_upload.append(local_info['path'])
                    new_count += 1
                else:
                    remote_info = remote_files_dict[relative_path]
                    
                    # مقارنة سريعة
                    if local_info['size'] != remote_info['size']:
                        files_to_upload.append(local_info['path'])
                        modified_count += 1
                    else:
                        time_diff = abs(local_info['mtime'] - remote_info['mtime'])
                        if 60 < time_diff < 86400:
                            files_to_upload.append(local_info['path'])
                            modified_count += 1
            
            # الملفات للحذف من الفولدرات فقط
            local_files_set = set(local_files_dict.keys())
            remote_files_set = set(remote_files_dict.keys())
            files_to_delete = [f for f in (remote_files_set - local_files_set) if '/' in f]
            
            total_operations = len(files_to_delete) + len(files_to_upload)
            
            print(f"📊 المزامنة: {new_count} جديد، {modified_count} معدل، {len(files_to_delete)} للحذف")
            
            if total_operations == 0:
                print("✅ جميع الملفات محدثة!")
                sftp.close()
                ssh.close()
                return True
            
            start_time = time.time()
            completed = 0
            
            # حذف الملفات القديمة
            for remote_file in files_to_delete:
                try:
                    sftp.remove(f"{self.remote_path}/{remote_file}")
                    completed += 1
                    percentage = (completed / total_operations) * 100
                    self.show_progress(percentage, completed, total_operations, "حذف")
                except:
                    pass
            
            # رفع الملفات
            if files_to_upload:
                # إنشاء المجلدات
                all_dirs = set()
                for file_path in files_to_upload:
                    relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                    remote_dir = '/'.join(f"{self.remote_path}/{relative_path}".split('/')[:-1])
                    if remote_dir != self.remote_path:
                        all_dirs.add(remote_dir)
                
                for remote_dir in sorted(all_dirs):
                    try:
                        sftp.mkdir(remote_dir)
                    except:
                        pass
                
                # رفع الملفات
                for file_path in files_to_upload:
                    try:
                        relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                        remote_file = f"{self.remote_path}/{relative_path}"
                        
                        sftp.put(str(file_path), remote_file)
                        completed += 1
                        
                        percentage = (completed / total_operations) * 100
                        elapsed = time.time() - start_time
                        remaining = total_operations - completed
                        eta = int((elapsed / completed) * remaining) if completed > 0 else 0
                        eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                        
                        self.show_progress(percentage, completed, total_operations, f"رفع - متبقي: {eta_text}")
                        
                    except:
                        pass
            
            print()
            sftp.close()
            ssh.close()
            
            total_time = time.time() - start_time
            print(f"✅ تمت المزامنة في {total_time:.1f}ث")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False

    def get_remote_files_with_stats(self, sftp, remote_path, files_dict, base_path=""):
        """الحصول على قائمة الملفات البعيدة مع معلومات الحجم والوقت"""
        try:
            for item in sftp.listdir_attr(remote_path):
                # تخطي الملفات المخفية
                if item.filename.startswith('.'):
                    continue
                
                item_path = f"{remote_path}/{item.filename}"
                relative_path = f"{base_path}/{item.filename}" if base_path else item.filename
                
                if item.st_mode and item.st_mode & 0o040000:  # مجلد
                    # استكشاف المجلد
                    self.get_remote_files_with_stats(sftp, item_path, files_dict, relative_path)
                else:  # ملف
                    files_dict[relative_path] = {
                        'size': item.st_size,
                        'mtime': int(item.st_mtime)
                    }
        except Exception as e:
            # تجاهل الأخطاء في قراءة بعض المجلدات
            pass

    def get_remote_files_in_folders(self, sftp, remote_path, files_set, base_path=""):
        """الحصول على قائمة الملفات البعيدة من الفولدرات فقط (ليس الـ root)"""
        try:
            for item in sftp.listdir_attr(remote_path):
                item_path = f"{remote_path}/{item.filename}"
                relative_path = f"{base_path}/{item.filename}" if base_path else item.filename
                
                if item.st_mode and item.st_mode & 0o040000:  # مجلد
                    # استكشاف المجلد
                    self.get_remote_files_in_folders(sftp, item_path, files_set, relative_path)
                else:  # ملف
                    # إضافة الملف فقط إذا كان داخل مجلد (ليس في الـ root)
                    if base_path:  # يعني الملف داخل مجلد
                        files_set.add(relative_path)
        except Exception as e:
            # تجاهل الأخطاء في قراءة بعض المجلدات
            pass

    def show_progress(self, percentage, completed, total, operation):
        """عرض شريط التقدم"""
        bar_length = 25
        filled_length = int(bar_length * completed // total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        print(f"\r   [{bar}] {percentage:.1f}% ({completed}/{total}) {operation}", end='', flush=True)

    def _save_upload_log(self, uploaded_files, method_name):
        """حفظ تفاصيل الملفات المرفوعة في ملف log"""
        try:
            from datetime import datetime

            # log_dir يمكن تخصيصه من الخارج (مثلاً لعميل محدد)
            base_dir = getattr(self, '_log_dir', self.project_root / "deploy_logs")
            log_file = base_dir / f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"📤 تقرير الرفع - {method_name}\n")
                f.write(f"⏰ التوقيت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"🖥️  الخادم: {self.server_ip}:{self.ssh_port}\n")
                f.write(f"📁 المسار البعيد: {self.remote_path}\n")
                f.write(f"📊 إجمالي الملفات المرفوعة: {len(uploaded_files)}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, file_path in enumerate(uploaded_files, 1):
                    f.write(f"{i:4d}. {file_path}\n")
                
                f.write(f"\n" + "=" * 50 + "\n")
                f.write(f"✅ تم حفظ {len(uploaded_files)} ملف بنجاح\n")
            
            print(f"📝 تم حفظ تفاصيل الرفع في: {log_file}")
            
            # الاحتفاظ بأحدث 10 ملفات فقط وحذف الباقي
            log_dir = log_file.parent
            all_logs = sorted(log_dir.glob("upload_*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
            for old_log in all_logs[10:]:
                old_log.unlink()
            
        except Exception as e:
            print(f"⚠️  لا يمكن حفظ log الرفع: {e}")

class MultiClientDeployment:
    """نشر متعدد العملاء - Multi-Client Deployment"""

    def __init__(self):
        self.project_root = Path.cwd()
        self.deployments_dir = self.project_root / "deployments"
        self.clients_file = self.deployments_dir / "clients.json"
        self.clients = self._load_clients()

    def _load_clients(self):
        """تحميل قائمة العملاء"""
        if not self.clients_file.exists():
            print("❌ ملف clients.json غير موجود!")
            print(f"   المسار المتوقع: {self.clients_file}")
            return {}
        try:
            with open(self.clients_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('clients', {})
        except Exception as e:
            print(f"❌ خطأ في قراءة ملف العملاء: {e}")
            return {}

    def list_clients(self):
        """عرض قائمة العملاء"""
        print("\n" + "=" * 60)
        print("📋 قائمة العملاء المتاحة")
        print("=" * 60)

        if not self.clients:
            print("❌ لا يوجد عملاء مسجلين")
            return

        for client_id, info in self.clients.items():
            status = "✅ نشط" if info.get('active', True) else "⏸️  معطل"
            print(f"\n🏢 {client_id}")
            print(f"   الاسم: {info.get('name', 'غير محدد')}")
            print(f"   الدومين: {info.get('domain', 'غير محدد')}")
            print(f"   الخادم: {info.get('ssh_host', 'غير محدد')}")
            print(f"   المسار: {info.get('remote_path', 'غير محدد')}")
            print(f"   الحالة: {status}")
            if info.get('notes'):
                print(f"   ملاحظات: {info['notes']}")

        print("\n" + "=" * 60)

    def deploy(self, client_id, mode='modified', force=False):
        """نشر للعميل المحدد"""
        if client_id not in self.clients:
            print(f"❌ العميل '{client_id}' غير موجود في القائمة")
            print("💡 استخدم --list-clients لعرض العملاء المتاحين")
            return False

        client_info = self.clients[client_id]

        if not client_info.get('active', True):
            print(f"⚠️  العميل '{client_id}' معطل حالياً")
            response = input("هل تريد المتابعة؟ (y/n): ")
            if response.lower() != 'y':
                return False

        # البحث عن ملف .env الخاص بالعميل
        env_file = self.deployments_dir / client_id / ".env"
        if not env_file.exists():
            print(f"❌ ملف .env غير موجود للعميل: {client_id}")
            print(f"   المسار المتوقع: {env_file}")
            return False

        print("\n" + "=" * 60)
        print(f"🚀 بدء النشر للعميل: {client_id}")
        print("=" * 60 + "\n")
        print(f"✅ تم تحميل إعدادات العميل: {client_info['name']}")
        print(f"   الدومين: {client_info.get('domain', 'غير محدد')}")
        print(f"   الخادم: {client_info.get('ssh_host', 'غير محدد')}")

        original_wsgi = self.project_root / "passenger_wsgi.py"
        backup_wsgi = self.project_root / "passenger_wsgi.py.backup"
        import shutil

        try:
            # استخدام passenger_wsgi.py الخاص بالعميل إن وجد
            client_wsgi = self.deployments_dir / client_id / "passenger_wsgi.py"
            if not client_wsgi.exists():
                # توليد تلقائي من SSH_REMOTE_PATH في .env
                remote_path_val = '/home/user/project'  # fallback
                try:
                    for line in env_file.read_text(encoding='utf-8').splitlines():
                        if line.startswith('SSH_REMOTE_PATH='):
                            remote_path_val = line.split('=', 1)[1].strip()
                            break
                except Exception:
                    pass
                client_wsgi.write_text(f"""import os
import sys
import gc

# مسار المشروع
PROJECT_PATH = '{remote_path_val}'
sys.path.insert(0, PROJECT_PATH)

# اسم settings
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'corporate_erp.settings'
)

# Reduce GC frequency - default (700,10,10) is fine for shared hosting
gc.set_threshold(700, 10, 10)

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
""", encoding='utf-8')
                print(f"  ✅ passenger_wsgi.py generated for {client_id} → {remote_path_val}")
            if original_wsgi.exists():
                shutil.copy2(original_wsgi, backup_wsgi)
            shutil.copy2(client_wsgi, original_wsgi)
            print(f"  ✅ passenger_wsgi.py → {client_id}")

            deployer = DeploymentManager(env_file=env_file, force=force)
            # توجيه الـ logs لمجلد العميل
            deployer._log_dir = self.deployments_dir / client_id / "deploy_logs"
            # ملف hashes خاص بكل عميل
            deployer.hash_file = self.deployments_dir / client_id / ".deploy_hashes.json"

            if mode == 'test':
                success = deployer.test_connection()
                files = []
            elif mode == 'status':
                deployer.get_modified_files_vs_remote()
                success = True
                files = []
            elif mode == 'all':
                files = deployer.get_all_files()
                success = deployer.upload_all_files(files)
            elif mode == 'sync':
                files = deployer.get_all_files()
                success = deployer.upload_with_smart_skip(files)
            elif mode == 'remote':
                files = deployer.get_modified_files_vs_remote()
                success = deployer.upload_all_files(files) if files else True
            elif mode == 'file':
                filename = getattr(self, '_pending_file', None)
                if not filename:
                    print("❌ لازم تحدد الملف بـ --file")
                    return False
                success = deployer.deploy_single_file(filename)
                files = []
            else:  # modified (default) - اسأل المستخدم
                all_files = deployer.get_all_files()
                print(f"\n📊 {len(all_files)} ملف للفحص")
                print("\n📋 اختر طريقة الرفع:")
                print("1️⃣  رفع كامل مع استبدال (يرفع كل شيء - بطيء)")
                print("2️⃣  رفع كامل مع تخطي (مقارنة مع الخادم - متوسط)")
                print("3️⃣  رفع المعدل فقط (مقارنة hash محلي - سريع جداً)")
                print("❌ أي رقم آخر للإلغاء")
                choice = input("\n❓ اختيارك (1/2/3): ").strip()
                if choice == "1":
                    files = all_files
                    success = deployer.upload_all_files(files)
                elif choice == "2":
                    files = all_files
                    success = deployer.upload_with_smart_skip(files)
                elif choice == "3":
                    files = all_files
                    success = deployer.upload_modified_only(files)
                else:
                    print("❌ تم الإلغاء")
                    return False

            # تحديث hash_file الخاص بالعميل بعد أي رفع ناجح
            if success and files and mode not in ('test', 'status'):
                is_first_deploy = not deployer.hash_file.exists()
                current_hashes = {}
                for file_path in files:
                    if file_path.exists():
                        relative_path = str(file_path.relative_to(deployer.project_root)).replace('\\', '/')
                        current_hashes[relative_path] = deployer.get_file_hash(file_path)
                deployer.hash_file.parent.mkdir(parents=True, exist_ok=True)
                with open(deployer.hash_file, 'w', encoding='utf-8') as f:
                    json.dump(current_hashes, f, indent=2, ensure_ascii=False)

                # رفع .env الخاص بالعميل لو اتغير
                try:
                    env_hash_key = f"__client_env__"
                    current_env_hash = deployer.get_file_hash(env_file)
                    saved_env_hash = current_hashes.get(env_hash_key)

                    if current_env_hash != saved_env_hash:
                        ssh = deployer._create_ssh_connection()
                        sftp = ssh.open_sftp()
                        remote_env = f"{deployer.remote_path}/.env"
                        sftp.put(str(env_file), remote_env)
                        sftp.close()
                        ssh.close()
                        # حفظ hash الـ .env في ملف الـ hashes
                        current_hashes[env_hash_key] = current_env_hash
                        with open(deployer.hash_file, 'w', encoding='utf-8') as f:
                            json.dump(current_hashes, f, indent=2, ensure_ascii=False)
                        print(f"  ✅ .env → {deployer.remote_path}/.env")
                    else:
                        print(f"  ⏭️  .env لم يتغير")
                except Exception as e:
                    print(f"  ⚠️  فشل رفع .env: {e}")

                deployer.run_post_deploy_commands(first_deploy=is_first_deploy)

            if success:
                print(f"\n✅ اكتمل النشر بنجاح للعميل: {client_id}")
            else:
                print(f"\n❌ فشل النشر للعميل: {client_id}")

            return success

        except Exception as e:
            print(f"\n❌ خطأ أثناء النشر: {e}")
            return False

        finally:
            # استرجاع passenger_wsgi.py الأصلي
            if backup_wsgi.exists():
                shutil.copy2(backup_wsgi, original_wsgi)
                backup_wsgi.unlink()
            # حذف الملف المؤقت إن وجد
            temp_env = self.project_root / ".env.deploy_temp"
            if temp_env.exists():
                temp_env.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="سكريپت النشر - Deploy Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
أمثلة الاستخدام:
  %(prog)s                                   # نشر عادي (modified)
  %(prog)s --mode all                        # رفع جميع الملفات
  %(prog)s --mode sync                       # رفع مع تخطي المطابق
  %(prog)s --mode test                       # اختبار الاتصال
  %(prog)s --mode file --file path/to/file   # رفع ملف واحد

  %(prog)s --list-clients                    # عرض قائمة العملاء
  %(prog)s --client baraka                   # نشر للعميل baraka
  %(prog)s --client baraka --mode test       # اختبار اتصال العميل
  %(prog)s --client baraka --mode all        # رفع كامل للعميل
        """
    )
    parser.add_argument('--mode', choices=['all', 'modified', 'status', 'file', 'sync', 'remote', 'test'],
                        default='modified', help='وضع النشر (افتراضي: modified)')
    parser.add_argument('--file', type=str, help='ملف محدد للرفع (مع --mode file)')
    parser.add_argument('--force', action='store_true', help='بدون تأكيد')
    parser.add_argument('--client', type=str, help='اسم العميل للنشر المتعدد')
    parser.add_argument('--list-clients', action='store_true', help='عرض قائمة العملاء المتاحين')
    
    args = parser.parse_args()

    try:
        # وضع multi-client
        if args.list_clients:
            MultiClientDeployment().list_clients()
            return

        target_client = args.client

        # إذا لم يتم تحديد العميل ولم يكن الوضع إجبارياً، نعرض قائمة الاختيار التفاعلي
        if not args.client and not args.force:
            mc = MultiClientDeployment()
            if mc.clients:
                print("\n📋 اختر جهة النشر (Choose Deployment Target):")
                print("1️⃣  المنصة الرئيسية (موهبة) - MWHEBA ERP")
                
                client_list = list(mc.clients.items())
                for index, (client_id, info) in enumerate(client_list, start=2):
                    num_str = f"{index}️⃣" if index <= 9 else f"{index}"
                    print(f"{num_str}  عميل: {info.get('name', client_id)} ({client_id})")
                print("❌ أي رقم آخر للإلغاء")
                
                choice = input("\n❓ اختيارك (1/...): ").strip()
                if choice == "1":
                    target_client = None
                elif choice.isdigit() and 2 <= int(choice) <= len(client_list) + 1:
                    target_client = client_list[int(choice) - 2][0]
                else:
                    print("❌ تم الإلغاء")
                    return
            else:
                target_client = None

        if target_client:
            mc = MultiClientDeployment()
            mc._pending_file = args.file  # تمرير الملف للـ deploy method
            success = mc.deploy(target_client, args.mode, force=args.force)
            sys.exit(0 if success else 1)

        # وضع single-client (الافتراضي - موهبة)
        deploy_manager = DeploymentManager(force=args.force)

        if args.mode == 'test':
            deploy_manager.test_connection()
        elif args.mode == 'status':
            deploy_manager.show_status()
        elif args.mode == 'all':
            deploy_manager.deploy_all()
        elif args.mode == 'modified':
            deploy_manager.deploy_modified()
        elif args.mode == 'file' and args.file:
            deploy_manager.deploy_single_file(args.file)
        elif args.mode == 'sync':
            deploy_manager.sync_all()
        elif args.mode == 'remote':
            files = deploy_manager.get_modified_files_vs_remote()
            if files:
                deploy_manager.upload_all_files(files)
        else:
            print("❌ يجب تحديد ملف مع --file")

    except KeyboardInterrupt:
        print("\n❌ تم الإيقاف")
        sys.exit(1)
    except Exception as e:
        print(f"❌ خطأ: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

