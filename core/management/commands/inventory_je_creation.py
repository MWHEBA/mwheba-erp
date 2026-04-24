"""
Phase -1.2: Journal Entry Creation Points Inventory
Ripgrep/AST scan لكل نقاط:
- JournalEntry.objects.create
- JournalEntry(...)
- create_*_journal_*
- أي service بيعمل JE مباشرة
"""

import os
import ast
import json
import re
import subprocess
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.apps import apps


class JournalEntryCreationInventory:
    def __init__(self):
        self.creation_points = []
        self.patterns = [
            # Direct JournalEntry creation patterns
            r'JournalEntry\.objects\.create',
            r'JournalEntry\.objects\.get_or_create',
            r'JournalEntry\.objects\.bulk_create',
            r'JournalEntry\(',
            
            # Service/function patterns
            r'create_.*journal.*entry',
            r'create_.*je\b',
            r'generate_.*journal',
            r'post_.*journal',
            r'create_accounting_entry',
            r'create_financial_entry',
            
            # Model save patterns that might create JEs
            r'\.save\(\).*journal',
            r'journal.*\.save\(\)',
            
            # Signal patterns
            r'journal.*signal',
            r'accounting.*signal',
        ]
        
        self.risk_indicators = {
            'direct_creation': ['JournalEntry.objects.create', 'JournalEntry('],
            'bulk_operations': ['bulk_create', 'bulk_update'],
            'signal_based': ['post_save', 'pre_save', 'signal'],
            'service_methods': ['create_journal', 'generate_journal', 'post_journal'],
            'manual_construction': ['JournalEntry(', 'JournalEntryLine('],
            'transaction_unsafe': ['save()', 'create()', 'update()']
        }
    
    def scan_with_ripgrep(self):
        """استخدام ripgrep للبحث السريع"""
        print("🔍 Scanning with ripgrep for JE creation patterns...")
        
        rg_patterns = [
            'JournalEntry\.objects\.create',
            'JournalEntry\.objects\.get_or_create',
            'JournalEntry\(',
            'create.*journal.*entry',
            'generate.*journal',
            'post.*journal'
        ]
        
        for pattern in rg_patterns:
            try:
                # تشغيل ripgrep
                cmd = [
                    'rg', 
                    '--type', 'py',
                    '--line-number',
                    '--with-filename',
                    '--no-heading',
                    pattern,
                    '.'
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
                
                if result.returncode == 0:
                    self._parse_ripgrep_output(result.stdout, pattern)
                    
            except FileNotFoundError:
                print("⚠️  ripgrep not found, falling back to manual search...")
                self._manual_search_pattern(pattern)
            except Exception as e:
                print(f"⚠️  Error with ripgrep: {e}")
                self._manual_search_pattern(pattern)
    
    def _parse_ripgrep_output(self, output, pattern):
        """تحليل مخرجات ripgrep"""
        for line in output.strip().split('\n'):
            if not line:
                continue
                
            parts = line.split(':', 2)
            if len(parts) >= 3:
                file_path = parts[0]
                line_number = parts[1]
                code_line = parts[2]
                
                self.creation_points.append({
                    'file': file_path,
                    'line': int(line_number),
                    'code': code_line.strip(),
                    'pattern': pattern,
                    'method': 'ripgrep'
                })
    
    def _manual_search_pattern(self, pattern):
        """البحث اليدوي كبديل لـ ripgrep"""
        print(f"🔍 Manual search for pattern: {pattern}")
        
        for app_config in apps.get_app_configs():
            app_path = app_config.path
            
            for root, dirs, files in os.walk(app_path):
                # تجاهل مجلدات معينة
                dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'migrations']]
                
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        self._search_in_file(file_path, pattern)
    
    def _search_in_file(self, file_path, pattern):
        """البحث في ملف واحد"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    self.creation_points.append({
                        'file': file_path.replace(os.getcwd(), ''),
                        'line': line_num,
                        'code': line.strip(),
                        'pattern': pattern,
                        'method': 'manual'
                    })
                    
        except Exception as e:
            print(f"⚠️  Error reading {file_path}: {e}")
    
    def ast_analysis(self):
        """تحليل AST للحصول على معلومات أكثر تفصيلاً"""
        print("🔍 Performing AST analysis for detailed context...")
        
        enhanced_points = []
        
        for point in self.creation_points:
            try:
                enhanced_point = self._analyze_creation_point(point)
                enhanced_points.append(enhanced_point)
            except Exception as e:
                print(f"⚠️  AST analysis failed for {point['file']}:{point['line']}: {e}")
                enhanced_points.append(point)
        
        self.creation_points = enhanced_points
    
    def _analyze_creation_point(self, point):
        """تحليل نقطة إنشاء واحدة بـ AST"""
        file_path = point['file']
        if file_path.startswith('/'):
            full_path = file_path
        else:
            full_path = os.path.join(os.getcwd(), file_path.lstrip('/'))
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            # البحث عن الدالة التي تحتوي على هذا السطر
            function_info = self._find_containing_function(tree, point['line'])
            
            # حساب مستوى الخطر
            risk_score = self._calculate_creation_risk(point, content, function_info)
            
            # استخراج السياق
            context = self._extract_context(content, point['line'])
            
            enhanced_point = point.copy()
            enhanced_point.update({
                'function_name': function_info.get('name', 'unknown'),
                'function_type': function_info.get('type', 'unknown'),
                'class_name': function_info.get('class', None),
                'risk_score': risk_score,
                'context_lines': context,
                'risk_factors': self._identify_risk_factors(point, content),
                'is_in_transaction': self._check_transaction_context(content, point['line']),
                'has_error_handling': self._check_error_handling(content, point['line'])
            })
            
            return enhanced_point
            
        except Exception as e:
            print(f"⚠️  Enhanced analysis failed for {point['file']}: {e}")
            return point
    
    def _find_containing_function(self, tree, target_line):
        """البحث عن الدالة التي تحتوي على السطر المحدد"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                    if node.lineno <= target_line <= (node.end_lineno or node.lineno):
                        # البحث عن الكلاس المحتوي
                        class_name = None
                        for parent in ast.walk(tree):
                            if isinstance(parent, ast.ClassDef):
                                if (hasattr(parent, 'lineno') and hasattr(parent, 'end_lineno') and
                                    parent.lineno <= node.lineno <= (parent.end_lineno or parent.lineno)):
                                    class_name = parent.name
                                    break
                        
                        return {
                            'name': node.name,
                            'type': 'method' if class_name else 'function',
                            'class': class_name,
                            'line_start': node.lineno,
                            'line_end': getattr(node, 'end_lineno', node.lineno)
                        }
        
        return {'name': 'unknown', 'type': 'unknown', 'class': None}
    
    def _calculate_creation_risk(self, point, content, function_info):
        """حساب مستوى خطر نقطة الإنشاء"""
        risk_score = 0
        
        # خطر أساسي حسب نوع الإنشاء
        if 'JournalEntry.objects.create' in point['code']:
            risk_score += 3  # إنشاء مباشر
        elif 'JournalEntry(' in point['code']:
            risk_score += 2  # إنشاء manual
        elif 'bulk_create' in point['code']:
            risk_score += 4  # عمليات bulk خطيرة
        
        # خطر السياق
        function_content = self._get_function_content(content, function_info)
        
        # فحص مؤشرات الخطر
        for risk_type, indicators in self.risk_indicators.items():
            for indicator in indicators:
                if indicator in function_content:
                    if risk_type == 'bulk_operations':
                        risk_score += 2
                    elif risk_type == 'transaction_unsafe':
                        risk_score += 1
                    elif risk_type == 'signal_based':
                        risk_score += 3  # signals خطيرة
                    else:
                        risk_score += 1
        
        # تقليل الخطر للممارسات الجيدة
        if 'transaction.atomic' in function_content:
            risk_score -= 1
        if 'try:' in function_content and 'except' in function_content:
            risk_score -= 1
        if 'logger' in function_content or 'log' in function_content:
            risk_score -= 1
        
        return max(0, min(risk_score, 10))  # بين 0 و 10
    
    def _get_function_content(self, content, function_info):
        """استخراج محتوى الدالة"""
        if function_info['name'] == 'unknown':
            return ""
        
        lines = content.split('\n')
        start_line = function_info.get('line_start', 1) - 1
        end_line = function_info.get('line_end', len(lines))
        
        return '\n'.join(lines[start_line:end_line])
    
    def _extract_context(self, content, target_line):
        """استخراج السياق حول السطر المحدد"""
        lines = content.split('\n')
        start = max(0, target_line - 3)
        end = min(len(lines), target_line + 2)
        
        context = []
        for i in range(start, end):
            prefix = ">>> " if i == target_line - 1 else "    "
            context.append(f"{prefix}{i+1:3d}: {lines[i]}")
        
        return context
    
    def _identify_risk_factors(self, point, content):
        """تحديد عوامل الخطر"""
        risk_factors = []
        
        for risk_type, indicators in self.risk_indicators.items():
            for indicator in indicators:
                if indicator in point['code'] or indicator in content:
                    risk_factors.append(risk_type)
                    break
        
        return list(set(risk_factors))
    
    def _check_transaction_context(self, content, target_line):
        """فحص ما إذا كان الكود داخل transaction"""
        lines = content.split('\n')
        
        # البحث للخلف عن transaction.atomic
        for i in range(target_line - 1, max(0, target_line - 20), -1):
            if 'transaction.atomic' in lines[i]:
                return True
            if '@transaction.atomic' in lines[i]:
                return True
        
        return False
    
    def _check_error_handling(self, content, target_line):
        """فحص وجود معالجة الأخطاء"""
        lines = content.split('\n')
        
        # البحث في نطاق محدود
        start = max(0, target_line - 10)
        end = min(len(lines), target_line + 10)
        
        for i in range(start, end):
            if 'try:' in lines[i] or 'except' in lines[i]:
                return True
        
        return False
    
    def generate_report(self):
        """توليد التقرير النهائي"""
        print("📊 Generating JE creation inventory report...")
        
        # تجميع الإحصائيات
        total_points = len(self.creation_points)
        high_risk_points = [p for p in self.creation_points if p.get('risk_score', 0) >= 7]
        medium_risk_points = [p for p in self.creation_points if 4 <= p.get('risk_score', 0) < 7]
        low_risk_points = [p for p in self.creation_points if p.get('risk_score', 0) < 4]
        
        # تجميع حسب الملفات
        files_summary = defaultdict(list)
        for point in self.creation_points:
            files_summary[point['file']].append(point)
        
        # تجميع حسب الأنماط
        patterns_summary = defaultdict(int)
        for point in self.creation_points:
            patterns_summary[point['pattern']] += 1
        
        # إنشاء التقرير
        report = {
            'inventory_summary': {
                'total_creation_points': total_points,
                'high_risk_points': len(high_risk_points),
                'medium_risk_points': len(medium_risk_points),
                'low_risk_points': len(low_risk_points),
                'affected_files': len(files_summary),
                'most_common_pattern': max(patterns_summary.items(), key=lambda x: x[1])[0] if patterns_summary else None
            },
            'risk_distribution': {
                'high_risk': [self._format_point_summary(p) for p in high_risk_points],
                'medium_risk': [self._format_point_summary(p) for p in medium_risk_points],
                'low_risk': [self._format_point_summary(p) for p in low_risk_points]
            },
            'files_summary': {
                file: {
                    'creation_points': len(points),
                    'max_risk_score': max(p.get('risk_score', 0) for p in points),
                    'patterns': list(set(p['pattern'] for p in points))
                }
                for file, points in files_summary.items()
            },
            'patterns_summary': dict(patterns_summary),
            'detailed_inventory': [
                self._format_detailed_point(p) for p in self.creation_points
            ]
        }
        
        return report
    
    def _format_point_summary(self, point):
        """تنسيق ملخص نقطة الإنشاء"""
        return {
            'file': point['file'],
            'line': point['line'],
            'function': point.get('function_name', 'unknown'),
            'risk_score': point.get('risk_score', 0),
            'pattern': point['pattern']
        }
    
    def _format_detailed_point(self, point):
        """تنسيق تفاصيل نقطة الإنشاء"""
        return {
            'location': {
                'file': point['file'],
                'line': point['line'],
                'function': point.get('function_name', 'unknown'),
                'class': point.get('class_name'),
                'function_type': point.get('function_type', 'unknown')
            },
            'code_analysis': {
                'code_line': point['code'],
                'pattern_matched': point['pattern'],
                'risk_score': point.get('risk_score', 0),
                'risk_factors': point.get('risk_factors', []),
                'is_in_transaction': point.get('is_in_transaction', False),
                'has_error_handling': point.get('has_error_handling', False)
            },
            'context': point.get('context_lines', [])
        }


class Command(BaseCommand):
    help = 'Phase -1.2: Inventory all JournalEntry creation points in the codebase'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output-format',
            choices=['markdown', 'json', 'both'],
            default='both',
            help='Output format for the report'
        )
        parser.add_argument(
            '--output-dir',
            default='reports',
            help='Directory to save reports'
        )
        parser.add_argument(
            '--include-low-risk',
            action='store_true',
            help='Include low-risk creation points in detailed output'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting JournalEntry Creation Inventory (Phase -1.2)')
        )
        
        # إنشاء مجلد التقارير
        output_dir = options['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        
        # تشغيل التحليل
        inventory = JournalEntryCreationInventory()
        inventory.scan_with_ripgrep()
        inventory.ast_analysis()
        report = inventory.generate_report()
        
        # حفظ التقارير
        if options['output_format'] in ['json', 'both']:
            json_path = os.path.join(output_dir, 'je_creation_inventory.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self.stdout.write(f"📄 JSON report saved: {json_path}")
        
        if options['output_format'] in ['markdown', 'both']:
            md_path = os.path.join(output_dir, 'je_creation_inventory.md')
            self._generate_markdown_report(report, md_path, options['include_low_risk'])
            self.stdout.write(f"📄 Markdown report saved: {md_path}")
        
        # عرض ملخص في الكونسول
        self._display_summary(report)
        
        self.stdout.write(
            self.style.SUCCESS('✅ JournalEntry Creation Inventory completed successfully')
        )
    
    def _generate_markdown_report(self, report, file_path, include_low_risk):
        """توليد تقرير Markdown"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# JournalEntry Creation Points Inventory\n\n")
            f.write(f"**Generated:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # ملخص الجرد
            summary = report['inventory_summary']
            f.write("## Inventory Summary\n\n")
            f.write(f"- **Total Creation Points:** {summary['total_creation_points']}\n")
            f.write(f"- **High Risk Points (≥7):** {summary['high_risk_points']}\n")
            f.write(f"- **Medium Risk Points (4-6):** {summary['medium_risk_points']}\n")
            f.write(f"- **Low Risk Points (<4):** {summary['low_risk_points']}\n")
            f.write(f"- **Affected Files:** {summary['affected_files']}\n")
            f.write(f"- **Most Common Pattern:** `{summary['most_common_pattern']}`\n\n")
            
            # توزيع المخاطر
            f.write("## Risk Distribution\n\n")
            
            # النقاط عالية الخطر
            if report['risk_distribution']['high_risk']:
                f.write("### 🔴 High Risk Points (≥7)\n\n")
                f.write("| File | Line | Function | Risk | Pattern |\n")
                f.write("|------|------|----------|------|----------|\n")
                for point in report['risk_distribution']['high_risk']:
                    f.write(f"| {point['file']} | {point['line']} | {point['function']} | {point['risk_score']} | {point['pattern']} |\n")
                f.write("\n")
            
            # النقاط متوسطة الخطر
            if report['risk_distribution']['medium_risk']:
                f.write("### 🟡 Medium Risk Points (4-6)\n\n")
                f.write("| File | Line | Function | Risk | Pattern |\n")
                f.write("|------|------|----------|------|----------|\n")
                for point in report['risk_distribution']['medium_risk']:
                    f.write(f"| {point['file']} | {point['line']} | {point['function']} | {point['risk_score']} | {point['pattern']} |\n")
                f.write("\n")
            
            # النقاط منخفضة الخطر (اختياري)
            if include_low_risk and report['risk_distribution']['low_risk']:
                f.write("### 🟢 Low Risk Points (<4)\n\n")
                f.write("| File | Line | Function | Risk | Pattern |\n")
                f.write("|------|------|----------|------|----------|\n")
                for point in report['risk_distribution']['low_risk']:
                    f.write(f"| {point['file']} | {point['line']} | {point['function']} | {point['risk_score']} | {point['pattern']} |\n")
                f.write("\n")
            
            # ملخص الملفات
            f.write("## Files Summary\n\n")
            f.write("| File | Creation Points | Max Risk | Patterns |\n")
            f.write("|------|-----------------|----------|----------|\n")
            for file, info in report['files_summary'].items():
                patterns = ', '.join(info['patterns'][:3])  # أول 3 patterns
                if len(info['patterns']) > 3:
                    patterns += "..."
                f.write(f"| {file} | {info['creation_points']} | {info['max_risk_score']} | {patterns} |\n")
            
            # ملخص الأنماط
            f.write("\n## Patterns Summary\n\n")
            f.write("| Pattern | Count |\n")
            f.write("|---------|-------|\n")
            for pattern, count in sorted(report['patterns_summary'].items(), key=lambda x: x[1], reverse=True):
                f.write(f"| `{pattern}` | {count} |\n")
            
            # التفاصيل الكاملة للنقاط عالية الخطر
            high_risk_detailed = [p for p in report['detailed_inventory'] if p['code_analysis']['risk_score'] >= 7]
            if high_risk_detailed:
                f.write("\n## Detailed Analysis - High Risk Points\n\n")
                for i, point in enumerate(high_risk_detailed, 1):
                    loc = point['location']
                    analysis = point['code_analysis']
                    
                    f.write(f"### {i}. {loc['file']}:{loc['line']}\n\n")
                    f.write(f"**Function:** `{loc['function']}` ({loc['function_type']})\n")
                    if loc['class']:
                        f.write(f"**Class:** `{loc['class']}`\n")
                    f.write(f"**Risk Score:** {analysis['risk_score']}/10\n")
                    f.write(f"**Pattern:** `{analysis['pattern_matched']}`\n")
                    f.write(f"**Risk Factors:** {', '.join(analysis['risk_factors'])}\n")
                    f.write(f"**In Transaction:** {'✅' if analysis['is_in_transaction'] else '❌'}\n")
                    f.write(f"**Error Handling:** {'✅' if analysis['has_error_handling'] else '❌'}\n\n")
                    
                    f.write("**Code Context:**\n```python\n")
                    for context_line in point['context']:
                        f.write(f"{context_line}\n")
                    f.write("```\n\n")
    
    def _display_summary(self, report):
        """عرض ملخص في الكونسول"""
        summary = report['inventory_summary']
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.WARNING("📊 JOURNAL ENTRY CREATION INVENTORY SUMMARY"))
        self.stdout.write("="*60)
        
        self.stdout.write(f"Total Creation Points: {summary['total_creation_points']}")
        self.stdout.write(f"High Risk Points (≥7): {summary['high_risk_points']}")
        self.stdout.write(f"Medium Risk Points (4-6): {summary['medium_risk_points']}")
        self.stdout.write(f"Low Risk Points (<4): {summary['low_risk_points']}")
        self.stdout.write(f"Affected Files: {summary['affected_files']}")
        
        if summary['most_common_pattern']:
            self.stdout.write(f"Most Common Pattern: {summary['most_common_pattern']}")
        
        # عرض أخطر النقاط
        high_risk = report['risk_distribution']['high_risk']
        if high_risk:
            self.stdout.write(f"\n🔴 TOP HIGH RISK POINTS:")
            for point in high_risk[:5]:  # أول 5
                self.stdout.write(f"   {point['file']}:{point['line']} - {point['function']} (Risk: {point['risk_score']})")
        
        self.stdout.write("="*60 + "\n")