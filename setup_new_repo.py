#!/usr/bin/env python3
"""
سكريبت إعداد الريبو الجديد على GitHub
"""

import os
import subprocess
import sys
from pathlib import Path

def run_command(command, description=""):
    """تشغيل أمر مع معالجة الأخطاء"""
    print(f"🔄 {description}")
    print(f"   الأمر: {command}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8')
        if result.returncode == 0:
            print(f"✅ نجح: {description}")
            if result.stdout.strip():
                print(f"   النتيجة: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ فشل: {description}")
            print(f"   الخطأ: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ خطأ في تشغيل الأمر: {e}")
        return False

def setup_new_repo():
    """إعداد الريبو الجديد"""
    
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("🚀 بدء إعداد الريبو الجديد لـ MWHEBA ERP")
    print("=" * 50)
    
    # التحقق من وجود git
    if not run_command("git --version", "التحقق من وجود Git"):
        print("❌ يجب تثبيت Git أولاً")
        return False
    
    # تنظيف المشروع
    print("\n📋 الخطوة 1: تنظيف المشروع")
    if not run_command("python clean_for_git.py", "تشغيل سكريبت التنظيف"):
        print("⚠️  فشل التنظيف، لكن يمكن المتابعة")
    
    # تهيئة git
    print("\n📋 الخطوة 2: تهيئة Git")
    run_command("git init", "تهيئة مستودع Git")
    
    # إضافة الملفات
    print("\n📋 الخطوة 3: إضافة الملفات")
    run_command("git add .", "إضافة جميع الملفات")
    
    # الـ commit الأولي
    print("\n📋 الخطوة 4: الـ Commit الأولي")
    commit_message = """🎉 Initial commit: MWHEBA ERP System v2.0

✨ نظام ERP متكامل للطباعة والنشر

🏗️ المكونات الرئيسية:
• النظام المالي المتقدم مع القيود التلقائية
• نظام التسعير الذكي للطباعة والنشر  
• إدارة المخزون المتطورة مع التتبع
• إدارة العملاء والموردين
• نظام المبيعات والمشتريات
• تقارير تفاعلية وإحصائيات
• واجهة عربية كاملة مع دعم RTL

🔧 التقنيات:
• Django 4.2+ مع Python 3.8+
• PostgreSQL/SQLite قاعدة البيانات
• Redis للكاش والأداء
• Bootstrap 5 للواجهة
• DataTables للجداول التفاعلية

📊 الإحصائيات:
• 10+ تطبيقات Django
• 364+ template
• 95+ مكتبة Python
• نظام محاسبي متكامل
• دعم كامل للعربية"""
    
    if not run_command(f'git commit -m "{commit_message}"', "إنشاء الـ commit الأولي"):
        print("❌ فشل في إنشاء الـ commit")
        return False
    
    print("\n🎯 الخطوات التالية:")
    print("1. إنشاء ريبو جديد على GitHub باسم: mwheba-erp")
    print("2. تشغيل الأوامر التالية:")
    print(f"   git branch -M main")
    print(f"   git remote add origin https://github.com/MWHEBA/mwheba-erp.git")
    print(f"   git push -u origin main")
    
    # تشغيل الأوامر تلقائياً
    print("\n🚀 تشغيل الأوامر تلقائياً...")
    
    if run_command("git branch -M main", "تحويل الفرع إلى main"):
        print("✅ تم تحويل الفرع إلى main")
    
    # إضافة remote origin
    run_command("git remote remove origin", "إزالة origin القديم (إن وجد)")
    if run_command("git remote add origin https://github.com/MWHEBA/mwheba-erp.git", "إضافة remote origin"):
        print("✅ تم إضافة remote origin")
        
        # السؤال عن رفع المشروع
        push_now = input("\n❓ هل تريد رفع المشروع الآن؟ (y/n): ").strip().lower()
        if push_now in ['y', 'yes', 'نعم']:
            if run_command("git push -u origin main", "رفع المشروع إلى GitHub"):
                print("🎉 تم رفع المشروع بنجاح!")
                print("🔗 الرابط: https://github.com/MWHEBA/mwheba-erp")
            else:
                print("❌ فشل في رفع المشروع")
                print("💡 تأكد من إنشاء الريبو على GitHub أولاً")
        else:
            print("📝 يمكنك رفع المشروع لاحقاً بالأمر:")
            print("   git push -u origin main")
    
    print("\n✅ تم إعداد المشروع بنجاح!")
    print("🚀 المشروع جاهز للرفع على GitHub")
    
    return True

if __name__ == "__main__":
    setup_new_repo()
