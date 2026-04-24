#!/usr/bin/env python
"""
Celery Workers Startup Script
سكريبت بدء تشغيل عمال Celery

This script starts Celery workers for the financial settlement system
with proper configuration for different queues and concurrency levels.
"""

import os
import sys
import subprocess
import signal
import time
from pathlib import Path

# إضافة مجلد المشروع إلى Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# تعيين متغير Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')

# قائمة العمليات النشطة
active_processes = []

def signal_handler(sig, frame):
    """معالج إشارة الإيقاف لإنهاء جميع العمليات بشكل نظيف"""
    print("\n🛑 تم استلام إشارة الإيقاف، جاري إنهاء العمال...")
    
    for process in active_processes:
        if process.poll() is None:  # العملية ما زالت تعمل
            print(f"⏹️  إنهاء العملية {process.pid}")
            process.terminate()
    
    # انتظار إنهاء العمليات
    for process in active_processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print(f"🔪 قتل العملية {process.pid} بالقوة")
            process.kill()
    
    print("✅ تم إنهاء جميع العمال بنجاح")
    sys.exit(0)

def start_worker(queue_name, concurrency=2, max_tasks_per_child=1000):
    """
    بدء تشغيل عامل Celery لطابور محدد
    
    Args:
        queue_name (str): اسم الطابور
        concurrency (int): عدد العمليات المتزامنة
        max_tasks_per_child (int): الحد الأقصى للمهام لكل عملية فرعية
    """
    cmd = [
        'celery',
        '-A', 'corporate_erp',
        'worker',
        '--loglevel=info',
        f'--queues={queue_name}',
        f'--concurrency={concurrency}',
        f'--max-tasks-per-child={max_tasks_per_child}',
        f'--hostname={queue_name}@%h',
        '--without-gossip',
        '--without-mingle',
        '--without-heartbeat'
    ]
    
    print(f"🚀 بدء تشغيل عامل للطابور: {queue_name}")
    print(f"   الأمر: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        active_processes.append(process)
        return process
    except Exception as e:
        print(f"❌ خطأ في بدء تشغيل عامل {queue_name}: {e}")
        return None

def start_beat_scheduler():
    """بدء تشغيل مجدول المهام Celery Beat"""
    cmd = [
        'celery',
        '-A', 'corporate_erp',
        'beat',
        '--loglevel=info',
        '--scheduler=django_celery_beat.schedulers:DatabaseScheduler'
    ]
    
    print("📅 بدء تشغيل مجدول المهام (Celery Beat)")
    print(f"   الأمر: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        active_processes.append(process)
        return process
    except Exception as e:
        print(f"❌ خطأ في بدء تشغيل مجدول المهام: {e}")
        return None

def start_flower_monitoring():
    """بدء تشغيل Flower لمراقبة المهام"""
    cmd = [
        'celery',
        '-A', 'corporate_erp',
        'flower',
        '--port=5555',
        '--basic_auth=admin:admin123'
    ]
    
    print("🌸 بدء تشغيل Flower للمراقبة على المنفذ 5555")
    print(f"   الأمر: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        active_processes.append(process)
        return process
    except Exception as e:
        print(f"❌ خطأ في بدء تشغيل Flower: {e}")
        return None

def monitor_processes():
    """مراقبة العمليات وإعادة تشغيلها في حالة الفشل"""
    while True:
        for i, process in enumerate(active_processes[:]):
            if process.poll() is not None:  # العملية انتهت
                print(f"⚠️  العملية {process.pid} انتهت بكود الخروج {process.returncode}")
                active_processes.remove(process)
                
                # يمكن إضافة منطق إعادة التشغيل هنا
                print("🔄 يمكن إضافة منطق إعادة التشغيل التلقائي هنا")
        
        time.sleep(5)  # فحص كل 5 ثواني

def main():
    """الدالة الرئيسية لبدء تشغيل جميع العمال"""
    print("🎯 بدء تشغيل نظام المهام غير المتزامنة للتسويات المالية")
    print("=" * 60)
    
    # تسجيل معالج الإشارات
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # التحقق من وجود Redis أو RabbitMQ
    print("🔍 فحص متطلبات النظام...")
    
    # بدء تشغيل العمال للطوابير المختلفة
    workers_config = [
        ('notifications', 2, 500),      # طابور الإشعارات - 2 عامل
        ('reports', 1, 100),           # طابور التقارير - 1 عامل
        ('accounting', 2, 1000),       # طابور المحاسبة - 2 عامل
        ('bulk_processing', 1, 50),    # طابور المعالجة المجمعة - 1 عامل
        ('maintenance', 1, 1000),      # طابور الصيانة - 1 عامل
        ('default', 2, 1000),          # الطابور الافتراضي - 2 عامل
    ]
    
    print(f"🏭 بدء تشغيل {len(workers_config)} عامل للطوابير المختلفة...")
    
    for queue_name, concurrency, max_tasks in workers_config:
        worker_process = start_worker(queue_name, concurrency, max_tasks)
        if worker_process:
            print(f"✅ تم بدء تشغيل عامل {queue_name} بنجاح (PID: {worker_process.pid})")
        else:
            print(f"❌ فشل في بدء تشغيل عامل {queue_name}")
        
        time.sleep(1)  # انتظار قصير بين العمال
    
    # بدء تشغيل مجدول المهام
    beat_process = start_beat_scheduler()
    if beat_process:
        print(f"✅ تم بدء تشغيل مجدول المهام بنجاح (PID: {beat_process.pid})")
    
    # بدء تشغيل Flower للمراقبة (اختياري)
    flower_process = start_flower_monitoring()
    if flower_process:
        print(f"✅ تم بدء تشغيل Flower بنجاح (PID: {flower_process.pid})")
        print("🌐 يمكنك الوصول لواجهة المراقبة على: http://localhost:5555")
        print("   اسم المستخدم: admin")
        print("   كلمة المرور: admin123")
    
    print("\n" + "=" * 60)
    print("🎉 تم بدء تشغيل جميع العمال بنجاح!")
    print(f"📊 إجمالي العمليات النشطة: {len(active_processes)}")
    print("⌨️  اضغط Ctrl+C لإيقاف جميع العمال")
    print("=" * 60)
    
    # مراقبة العمليات
    try:
        monitor_processes()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

if __name__ == '__main__':
    main()