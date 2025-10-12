#!/usr/bin/env python3
"""
إصلاح نهائي لجميع مشاكل Information exposure through exceptions
"""

import os
import re

def fix_all_exception_exposures(file_path):
    """
    إصلاح شامل لجميع أنواع تسريب الأخطاء
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # إضافة logging import إذا لم يكن موجوداً
    if 'import logging' not in content:
        # البحث عن أول import line
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip().startswith('from django') or line.strip().startswith('import'):
                lines.insert(i, 'import logging')
                break
        content = '\n'.join(lines)
    
    # Pattern 1: f'message {str(e)}'
    content = re.sub(
        r"'(error|message)':\s*f'([^']*)\{str\(e\)\}([^']*)'",
        r"'\1': '\2خطأ في العملية\3'",
        content
    )
    
    # Pattern 2: f'message {e}'  
    content = re.sub(
        r"'(error|message)':\s*f'([^']*)\{e\}([^']*)'",
        r"'\1': '\2خطأ في العملية\3'",
        content
    )
    
    # Pattern 3: str(e) direct
    content = re.sub(
        r"'(error|message)':\s*str\(e\)",
        r"'\1': 'خطأ في العملية'",
        content
    )
    
    # Pattern 4: 'message' + str(e)
    content = re.sub(
        r"'(error|message)':\s*'([^']*)'\s*\+\s*str\(e\)",
        r"'\1': '\2خطأ في العملية'",
        content
    )
    
    # إضافة logging للـ exception blocks التي تم إصلاحها
    exception_blocks = re.finditer(
        r'except Exception as e:\s*\n(\s+)return JsonResponse\(\{\s*\n\s+[\'"]success[\'"]:\s*False,\s*\n\s+[\'"](?:error|message)[\'"]:\s*[\'"]([^\'"]*)[\'"]\s*\n\s+\}\)',
        content,
        re.MULTILINE
    )
    
    for match in reversed(list(exception_blocks)):
        indent = match.group(1)
        error_msg = match.group(2)
        
        replacement = f"""except Exception as e:
{indent}logger = logging.getLogger(__name__)
{indent}logger.error(f'Error in {os.path.basename(file_path)}: {{str(e)}}', exc_info=True)
{indent}return JsonResponse({{
{indent}    'success': False,
{indent}    'error': '{error_msg}'
{indent}}})"""
        
        content = content[:match.start()] + replacement + content[match.end():]
    
    return content, content != original_content

def main():
    """
    تطبيق الإصلاحات على جميع الملفات
    """
    files_to_fix = [
        'pricing/views.py',
        'financial/views.py',
        'supplier/views_pricing.py', 
        'product/views.py',
        'purchase/views.py',
        'sale/views.py',
        'supplier/views.py',
        'utils/views.py'
    ]
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    fixed_count = 0
    
    print("🔧 إصلاح نهائي لمشاكل Information exposure...")
    print("=" * 50)
    
    for file_path in files_to_fix:
        full_path = os.path.join(base_dir, file_path)
        
        if os.path.exists(full_path):
            try:
                content, changed = fix_all_exception_exposures(full_path)
                
                if changed:
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"✅ Fixed: {file_path}")
                    fixed_count += 1
                else:
                    print(f"⏭️  No changes: {file_path}")
                    
            except Exception as e:
                print(f"❌ Error fixing {file_path}: {e}")
        else:
            print(f"⚠️  Not found: {file_path}")
    
    print("=" * 50)
    print(f"✨ تم إصلاح {fixed_count} ملف!")

if __name__ == '__main__':
    main()
