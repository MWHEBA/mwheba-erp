#!/usr/bin/env python
"""
سكريبت للبحث عن أخطاء شائعة في القوالب
"""
import os
import re
from pathlib import Path

def find_template_errors():
    """البحث عن أخطاء في القوالب"""
    templates_dir = Path('templates')
    errors_found = []
    
    # الأنماط المشبوهة
    patterns = {
        'empty_static': r'{%\s*static\s+["\']["\']',
        'unclosed_script': r'<script[^>]*>(?!.*</script>)',
        'double_semicolon': r';;+',
        'unclosed_tag': r'{%\s*\w+.*(?<!%})',
    }
    
    for html_file in templates_dir.rglob('*.html'):
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                
                # فحص كل نمط
                for pattern_name, pattern in patterns.items():
                    matches = re.finditer(pattern, content, re.MULTILINE)
                    for match in matches:
                        # حساب رقم السطر
                        line_num = content[:match.start()].count('\n') + 1
                        errors_found.append({
                            'file': str(html_file),
                            'line': line_num,
                            'type': pattern_name,
                            'content': lines[line_num - 1].strip()[:100]
                        })
        
        except Exception as e:
            print(f"خطأ في قراءة {html_file}: {e}")
    
    return errors_found

if __name__ == '__main__':
    print("جاري البحث عن أخطاء في القوالب...")
    errors = find_template_errors()
    
    if errors:
        print(f"\nتم العثور على {len(errors)} مشكلة محتملة:\n")
        for error in errors:
            print(f"📄 {error['file']}")
            print(f"   السطر {error['line']}: {error['type']}")
            print(f"   {error['content']}\n")
    else:
        print("\n✅ لم يتم العثور على مشاكل واضحة في القوالب")
