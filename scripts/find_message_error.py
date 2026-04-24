#!/usr/bin/env python3
"""
البحث عن المشكلة الفعلية في معامل message
"""

import os
import re

def find_message_errors():
    """البحث عن أخطاء معامل message"""
    
    print("🔍 البحث عن أخطاء معامل message...")
    
    # البحث عن جميع ملفات HTML
    template_files = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules']]
        
        for file in files:
            if file.endswith('.html'):
                template_files.append(os.path.join(root, file))
    
    print(f"فحص {len(template_files)} ملف HTML...")
    
    errors = []
    
    for file_path in template_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                # البحث عن include مع message= ولكن ليس للقوالب المسموحة
                if '{% include' in line and 'message=' in line:
                    # التحقق من أنه ليس empty_state.html أو alert.html أو delete_modal.html
                    if not any(allowed in line for allowed in [
                        'empty_state.html',
                        'alert.html', 
                        'delete_modal.html',
                        'confirmation_message=',
                        'warning_message=',
                        'final_warning_message=',
                        'empty_message='
                    ]):
                        # هذا خطأ محتمل
                        errors.append({
                            'file': file_path,
                            'line': line_num,
                            'content': line.strip(),
                            'type': 'invalid_message_param'
                        })
                
                # البحث عن data_table مع message= بدلاً من empty_message=
                if 'data_table.html' in line and ' message=' in line and 'empty_message=' not in line:
                    errors.append({
                        'file': file_path,
                        'line': line_num,
                        'content': line.strip(),
                        'type': 'data_table_wrong_param'
                    })
                
                # البحث عن {% with message= متبوعة بـ include data_table
                if '{% with' in line and ' message=' in line:
                    # فحص الأسطر التالية للبحث عن data_table
                    for next_line_num in range(line_num, min(line_num + 5, len(lines))):
                        if next_line_num < len(lines) and 'data_table.html' in lines[next_line_num]:
                            errors.append({
                                'file': file_path,
                                'line': line_num,
                                'content': line.strip(),
                                'type': 'with_message_before_data_table',
                                'next_line': next_line_num + 1,
                                'next_content': lines[next_line_num].strip()
                            })
                            break
        
        except Exception as e:
            errors.append({
                'file': file_path,
                'line': 0,
                'content': f'خطأ في قراءة الملف: {e}',
                'type': 'file_error'
            })
    
    # عرض النتائج
    if errors:
        print(f"\n🚨 تم العثور على {len(errors)} مشكلة:")
        
        for i, error in enumerate(errors, 1):
            print(f"\n{i}. {error['type']} في {error['file']}:{error['line']}")
            print(f"   المحتوى: {error['content']}")
            
            if 'next_line' in error:
                print(f"   السطر التالي ({error['next_line']}): {error['next_content']}")
    else:
        print("✅ لم يتم العثور على مشاكل في معامل message")
    
    return errors

def fix_found_errors(errors):
    """إصلاح الأخطاء المكتشفة"""
    
    if not errors:
        return False
    
    print(f"\n🔧 بدء إصلاح {len(errors)} مشكلة...")
    
    fixed_files = set()
    
    for error in errors:
        if error['type'] == 'file_error':
            continue
        
        file_path = error['file']
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            if error['type'] == 'data_table_wrong_param':
                # تحويل message= إلى empty_message= في data_table
                pattern = r'(data_table\.html[^%]*) message=([^%]*%})'
                replacement = r'\1 empty_message=\2'
                content = re.sub(pattern, replacement, content)
            
            elif error['type'] == 'with_message_before_data_table':
                # تحويل {% with message= إلى {% with empty_message=
                pattern = r'{% with message=([^%]*%})'
                replacement = r'{% with empty_message=\1'
                content = re.sub(pattern, replacement, content)
            
            elif error['type'] == 'invalid_message_param':
                # فحص يدوي - طباعة للمراجعة
                print(f"⚠️  يحتاج مراجعة يدوية: {file_path}:{error['line']}")
                print(f"   {error['content']}")
                continue
            
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                fixed_files.add(file_path)
                print(f"✅ تم إصلاح {file_path}")
        
        except Exception as e:
            print(f"❌ خطأ في إصلاح {file_path}: {e}")
    
    print(f"\n📊 تم إصلاح {len(fixed_files)} ملف")
    return len(fixed_files) > 0

if __name__ == "__main__":
    errors = find_message_errors()
    
    if errors:
        fix_found_errors(errors)
        
        # فحص مرة أخرى
        print("\n🔍 فحص نهائي...")
        remaining_errors = find_message_errors()
        
        if not remaining_errors:
            print("✅ تم حل جميع المشاكل!")
        else:
            print(f"⚠️  تبقى {len(remaining_errors)} مشكلة تحتاج مراجعة يدوية")
    else:
        print("✅ لا توجد مشاكل للإصلاح")