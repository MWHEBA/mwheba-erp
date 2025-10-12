#!/usr/bin/env python3
"""
سكريبت لإصلاح مشاكل Information exposure through exceptions
"""

import os
import re

def fix_exception_handling_in_file(file_path):
    """
    إصلاح مشاكل exception handling في ملف معين
    """
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # البحث عن patterns خطيرة وإصلاحها
    patterns_to_fix = [
        # Pattern: f'message with {str(e)}'
        (r"'message': f'[^']*\{str\(e\)\}[^']*'", "'message': 'حدث خطأ غير متوقع'"),
        # Pattern: f'message with {e}'
        (r"'message': f'[^']*\{e\}[^']*'", "'message': 'حدث خطأ غير متوقع'"),
        # Pattern: str(e) in message
        (r"'message': '[^']*' \+ str\(e\)", "'message': 'حدث خطأ غير متوقع'")
    ]
    
    original_content = content
    
    for pattern, replacement in patterns_to_fix:
        if callable(replacement):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
        else:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    # إضافة import للأدوات الآمنة في بداية الملف
    if 'from core.security_utils import' not in content:
        # البحث عن آخر import
        import_lines = []
        lines = content.split('\n')
        last_import_index = -1
        
        for i, line in enumerate(lines):
            if line.strip().startswith('import ') or line.strip().startswith('from '):
                last_import_index = i
        
        if last_import_index >= 0:
            lines.insert(last_import_index + 1, 'from core.security_utils import SecureExceptionHandler, safe_error_response')
            content = '\n'.join(lines)
    
    # كتابة الملف المحدث
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed exception handling in: {file_path}")
        return True
    else:
        print(f"No changes needed in: {file_path}")
        return False

def main():
    """
    تشغيل الإصلاحات على الملفات المحددة
    """
    files_to_fix = [
        'financial/views.py',
        'pricing/views.py'
    ]
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    for file_path in files_to_fix:
        full_path = os.path.join(base_dir, file_path)
        fix_exception_handling_in_file(full_path)

if __name__ == '__main__':
    main()
