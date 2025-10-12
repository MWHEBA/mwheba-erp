#!/usr/bin/env python3
"""
سكريبت تنظيف المشروع قبل رفعه على GitHub
يحذف الملفات المؤقتة وقاعدة البيانات والكاش
"""

import os
import shutil
import glob
from pathlib import Path

def clean_project():
    """تنظيف المشروع من الملفات غير المطلوبة"""
    
    project_root = Path(__file__).parent
    print(f"🧹 بدء تنظيف المشروع في: {project_root}")
    
    # الملفات والمجلدات المراد حذفها
    patterns_to_delete = [
        # Python cache
        "**/__pycache__",
        "**/*.pyc",
        "**/*.pyo",
        "**/*.pyd",
        "**/.Python",
        
        # Temporary files
        "**/*.tmp",
        "**/*.temp",
        "**/*_temp.py",
        "**/*_backup.py",
        "**/*.bak",
        "**/*.backup",
        
        # IDE files
        ".vscode",
        ".idea",
        "**/*.swp",
        "**/*.swo",
        
        # Environment
        "venv",
        "env",
        "ENV",
        
        # Test and coverage
        ".pytest_cache",
        ".coverage",
        "htmlcov",
        
        # Documentation temp files
        "**/*_FIX.md",
        "**/*_UPDATE.md",
        "**/*_COMPLETE.md",
        "**/*_ENHANCEMENT.md",
        "**/*_SOLUTION.md",
        "**/*_TEMPLATES.md",
    ]
    
    deleted_count = 0
    
    for pattern in patterns_to_delete:
        matches = list(project_root.glob(pattern))
        for match in matches:
            try:
                if match.is_file():
                    match.unlink()
                    print(f"🗑️  حذف ملف: {match.relative_to(project_root)}")
                    deleted_count += 1
                elif match.is_dir():
                    shutil.rmtree(match)
                    print(f"📁 حذف مجلد: {match.relative_to(project_root)}")
                    deleted_count += 1
            except Exception as e:
                print(f"⚠️  فشل حذف {match}: {e}")
    
    # التأكد من وجود .gitkeep في media إذا كان فارغ
    media_dir = project_root / "media"
    if media_dir.exists() and not any(media_dir.iterdir()):
        (media_dir / ".gitkeep").touch()
        print("📁 تم إضافة .gitkeep لمجلد media الفارغ")
    
    # إنشاء مجلد staticfiles فارغ مع .gitkeep
    static_dir = project_root / "staticfiles"
    if not static_dir.exists():
        static_dir.mkdir()
        (static_dir / ".gitkeep").touch()
        print("📁 تم إنشاء مجلد staticfiles مع .gitkeep")
    
    print(f"\n✅ تم الانتهاء من التنظيف!")
    print(f"📊 تم حذف {deleted_count} عنصر")
    print(f"🎯 المشروع جاهز للرفع على GitHub")

if __name__ == "__main__":
    clean_project()
