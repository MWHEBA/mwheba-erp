#!/usr/bin/env python3
"""
سكريپت شامل لإصلاح جميع مشاكل Information exposure through exceptions
"""

import os
import re
import glob


def fix_exception_patterns(content):
    """
    إصلاح patterns مختلفة لـ exception handling
    """
    # Pattern 1: f'message {str(e)}'
    content = re.sub(
        r"'message':\s*f'[^']*\{str\(e\)\}[^']*'",
        "'message': 'حدث خطأ غير متوقع'",
        content,
    )

    # Pattern 2: f'message {e}'
    content = re.sub(
        r"'message':\s*f'[^']*\{e\}[^']*'", "'message': 'حدث خطأ غير متوقع'", content
    )

    # Pattern 3: 'message' + str(e)
    content = re.sub(
        r"'message':\s*'[^']*'\s*\+\s*str\(e\)",
        "'message': 'حدث خطأ غير متوقع'",
        content,
    )

    # Pattern 4: str(e) in message
    content = re.sub(
        r"'message':\s*str\(e\)", "'message': 'حدث خطأ غير متوقع'", content
    )

    # Pattern 5: Direct error message exposure
    content = re.sub(r"'error':\s*str\(e\)", "'error': 'خطأ في العملية'", content)

    return content


def add_secure_logging(content, file_path):
    """
    إضافة secure logging للأخطاء
    """
    # إضافة import للـ logging إذا لم يكن موجوداً
    if "import logging" not in content:
        # البحث عن مكان مناسب لإضافة import
        lines = content.split("\n")
        import_added = False

        for i, line in enumerate(lines):
            if line.strip().startswith("from django.") and not import_added:
                lines.insert(i, "import logging")
                import_added = True
                break

        if not import_added and len(lines) > 10:
            # إضافة في بداية الملف بعد التعليقات
            for i, line in enumerate(lines):
                if (
                    not line.strip().startswith("#")
                    and not line.strip().startswith('"""')
                    and line.strip()
                ):
                    lines.insert(i, "import logging")
                    break

        content = "\n".join(lines)

    # إضافة logger definition
    if "logger = logging.getLogger(__name__)" not in content:
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "import logging" in line:
                lines.insert(i + 1, "logger = logging.getLogger(__name__)")
                break
        content = "\n".join(lines)

    # استبدال exception handling blocks
    exception_pattern = r'except\s+Exception\s+as\s+e:\s*\n(\s*)return\s+JsonResponse\(\{\s*\n\s*[\'"]success[\'"]\s*:\s*False,\s*\n\s*[\'"]message[\'"]\s*:\s*[\'"]حدث خطأ غير متوقع[\'"]'

    def replace_exception_block(match):
        indent = match.group(1)
        return f"""except Exception as e:
{indent}logger.error(f'Error in {os.path.basename(file_path)}: {{str(e)}}', exc_info=True)
{indent}return JsonResponse({{
{indent}    'success': False,
{indent}    'message': 'حدث خطأ غير متوقع'"""

    content = re.sub(
        exception_pattern, replace_exception_block, content, flags=re.MULTILINE
    )

    return content


def process_file(file_path):
    """
    معالجة ملف واحد
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        # تطبيق الإصلاحات
        content = fix_exception_patterns(original_content)
        content = add_secure_logging(content, file_path)

        # كتابة الملف إذا تغير
        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ Fixed: {file_path}")
            return True
        else:
            print(f"⏭️  No changes needed: {file_path}")
            return False

    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        return False


def main():
    """
    معالجة جميع الملفات المحددة
    """
    # الملفات المراد إصلاحها
    files_to_process = [
        "pricing/views.py",
        "financial/views.py",
        "supplier/views_pricing.py",
        "product/views.py",
    ]

    base_dir = os.path.dirname(os.path.abspath(__file__))
    fixed_count = 0

    print("🔧 بدء إصلاح مشاكل Information exposure through exceptions...")
    print("=" * 60)

    for file_path in files_to_process:
        full_path = os.path.join(base_dir, file_path)
        if os.path.exists(full_path):
            if process_file(full_path):
                fixed_count += 1
        else:
            print(f"⚠️  File not found: {file_path}")

    print("=" * 60)
    print(f"✨ تم إصلاح {fixed_count} ملف بنجاح!")

    # البحث عن ملفات إضافية قد تحتوي على نفس المشاكل
    print("\n🔍 البحث عن ملفات إضافية...")

    for pattern in ["*/views.py", "*/views_*.py"]:
        for file_path in glob.glob(
            os.path.join(base_dir, "**", pattern), recursive=True
        ):
            if file_path not in [os.path.join(base_dir, f) for f in files_to_process]:
                # فحص سريع للملف
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # البحث عن patterns خطيرة
                    dangerous_patterns = [
                        r"str\(e\)",
                        r"f\'[^\']*\{e\}",
                        r"f\'[^\']*\{str\(e\)\}",
                    ]

                    for pattern in dangerous_patterns:
                        if re.search(pattern, content):
                            print(
                                f"⚠️  Found potential issue in: {os.path.relpath(file_path, base_dir)}"
                            )
                            break

                except Exception:
                    pass


if __name__ == "__main__":
    main()
