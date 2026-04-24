#!/usr/bin/env python3
"""
مولد التقارير الشاملة لنظام الاختبارات المتقدم
"""
import os
import sys
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

def parse_junit_xml(xml_file):
    """تحليل ملف XML لنتائج الاختبارات"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        return {
            'name': root.get('name', 'Unknown'),
            'tests': int(root.get('tests', 0)),
            'failures': int(root.get('failures', 0)),
            'errors': int(root.get('errors', 0)),
            'skipped': int(root.get('skipped', 0)),
            'time': float(root.get('time', 0)),
            'success_rate': 0 if int(root.get('tests', 0)) == 0 else 
                          (int(root.get('tests', 0)) - int(root.get('failures', 0)) - int(root.get('errors', 0))) / int(root.get('tests', 0)) * 100
        }
    except Exception as e:
        print(f"خطأ في تحليل {xml_file}: {e}")
        return None

def parse_coverage_xml(xml_file):
    """تحليل ملف تغطية الكود"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        coverage = root.get('line-rate', '0')
        return {
            'line_coverage': float(coverage) * 100,
            'branch_coverage': float(root.get('branch-rate', '0')) * 100
        }
    except Exception as e:
        print(f"خطأ في تحليل التغطية {xml_file}: {e}")
        return {'line_coverage': 0, 'branch_coverage': 0}

def parse_benchmark_json(json_file):
    """تحليل نتائج اختبارات الأداء"""
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        benchmarks = data.get('benchmarks', [])
        if not benchmarks:
            return None
        
        total_time = sum(b.get('stats', {}).get('mean', 0) for b in benchmarks)
        avg_time = total_time / len(benchmarks) if benchmarks else 0
        
        return {
            'total_benchmarks': len(benchmarks),
            'average_time': avg_time,
            'total_time': total_time,
            'fastest': min(b.get('stats', {}).get('mean', float('inf')) for b in benchmarks),
            'slowest': max(b.get('stats', {}).get('mean', 0) for b in benchmarks)
        }
    except Exception as e:
        print(f"خطأ في تحليل الأداء {json_file}: {e}")
        return None

def parse_security_json(json_file):
    """تحليل نتائج اختبارات الأمان"""
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        if 'results' in data:  # Bandit format
            issues = data['results']
            return {
                'total_issues': len(issues),
                'high_severity': len([i for i in issues if i.get('issue_severity') == 'HIGH']),
                'medium_severity': len([i for i in issues if i.get('issue_severity') == 'MEDIUM']),
                'low_severity': len([i for i in issues if i.get('issue_severity') == 'LOW'])
            }
        elif 'vulnerabilities' in data:  # Safety format
            vulns = data['vulnerabilities']
            return {
                'total_vulnerabilities': len(vulns),
                'packages_affected': len(set(v.get('package_name', '') for v in vulns))
            }
    except Exception as e:
        print(f"خطأ في تحليل الأمان {json_file}: {e}")
        return None

def collect_test_results(reports_dir):
    """جمع جميع نتائج الاختبارات"""
    results = {
        'unit_tests': None,
        'integration_tests': None,
        'property_tests': None,
        'security_tests': None,
        'ui_tests': None,
        'coverage': None,
        'performance': None,
        'security_scan': None,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    reports_path = Path(reports_dir)
    
    # البحث عن ملفات التقارير
    for file_path in reports_path.rglob('*'):
        if file_path.is_file():
            filename = file_path.name.lower()
            
            if 'unit-tests.xml' in filename:
                results['unit_tests'] = parse_junit_xml(file_path)
            elif 'integration-tests.xml' in filename:
                results['integration_tests'] = parse_junit_xml(file_path)
            elif 'property-tests.xml' in filename:
                results['property_tests'] = parse_junit_xml(file_path)
            elif 'security-tests.xml' in filename:
                results['security_tests'] = parse_junit_xml(file_path)
            elif 'ui-tests.xml' in filename:
                results['ui_tests'] = parse_junit_xml(file_path)
            elif 'coverage.xml' in filename:
                results['coverage'] = parse_coverage_xml(file_path)
            elif 'benchmark.json' in filename:
                results['performance'] = parse_benchmark_json(file_path)
            elif 'bandit-report.json' in filename:
                results['security_scan'] = parse_security_json(file_path)
    
    return results

def generate_html_report(results, output_file):
    """إنشاء تقرير HTML شامل"""
    
    template_html = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تقرير الاختبارات الشامل - نظام إدارة الشركة</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            direction: rtl;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
        }
        .header p {
            margin: 10px 0 0 0;
            opacity: 0.9;
        }
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }
        .summary-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            text-align: center;
        }
        .summary-card h3 {
            margin: 0 0 10px 0;
            color: #333;
        }
        .summary-card .number {
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
        }
        .success { color: #28a745; }
        .warning { color: #ffc107; }
        .danger { color: #dc3545; }
        .info { color: #17a2b8; }
        
        .details {
            padding: 30px;
        }
        .test-section {
            margin-bottom: 30px;
            border: 1px solid #ddd;
            border-radius: 8px;
            overflow: hidden;
        }
        .test-section h3 {
            background: #f8f9fa;
            margin: 0;
            padding: 15px 20px;
            border-bottom: 1px solid #ddd;
        }
        .test-content {
            padding: 20px;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-fill {
            height: 100%;
            transition: width 0.3s ease;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }
        .stat-item {
            text-align: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        .stat-item .label {
            font-size: 0.9em;
            color: #666;
        }
        .stat-item .value {
            font-size: 1.2em;
            font-weight: bold;
            margin-top: 5px;
        }
        .footer {
            background: #343a40;
            color: white;
            text-align: center;
            padding: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧪 تقرير الاختبارات الشامل</h1>
            <p>نظام إدارة الشركة - {{ timestamp }}</p>
        </div>
        
        <div class="summary">
            {% if unit_tests %}
            <div class="summary-card">
                <h3>اختبارات الوحدة</h3>
                <div class="number {{ 'success' if unit_tests.success_rate > 90 else 'warning' if unit_tests.success_rate > 70 else 'danger' }}">
                    {{ "%.1f"|format(unit_tests.success_rate) }}%
                </div>
                <p>{{ unit_tests.tests }} اختبار</p>
            </div>
            {% endif %}
            
            {% if integration_tests %}
            <div class="summary-card">
                <h3>اختبارات التكامل</h3>
                <div class="number {{ 'success' if integration_tests.success_rate > 90 else 'warning' if integration_tests.success_rate > 70 else 'danger' }}">
                    {{ "%.1f"|format(integration_tests.success_rate) }}%
                </div>
                <p>{{ integration_tests.tests }} اختبار</p>
            </div>
            {% endif %}
            
            {% if coverage %}
            <div class="summary-card">
                <h3>تغطية الكود</h3>
                <div class="number {{ 'success' if coverage.line_coverage > 85 else 'warning' if coverage.line_coverage > 70 else 'danger' }}">
                    {{ "%.1f"|format(coverage.line_coverage) }}%
                </div>
                <p>تغطية الأسطر</p>
            </div>
            {% endif %}
            
            {% if performance %}
            <div class="summary-card">
                <h3>اختبارات الأداء</h3>
                <div class="number info">{{ performance.total_benchmarks }}</div>
                <p>معيار أداء</p>
            </div>
            {% endif %}
        </div>
        
        <div class="details">
            {% if unit_tests %}
            <div class="test-section">
                <h3>📋 اختبارات الوحدة</h3>
                <div class="test-content">
                    <div class="progress-bar">
                        <div class="progress-fill success" style="width: {{ unit_tests.success_rate }}%"></div>
                    </div>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="label">إجمالي الاختبارات</div>
                            <div class="value">{{ unit_tests.tests }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">نجح</div>
                            <div class="value success">{{ unit_tests.tests - unit_tests.failures - unit_tests.errors }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">فشل</div>
                            <div class="value danger">{{ unit_tests.failures }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">أخطاء</div>
                            <div class="value warning">{{ unit_tests.errors }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">وقت التنفيذ</div>
                            <div class="value">{{ "%.2f"|format(unit_tests.time) }}s</div>
                        </div>
                    </div>
                </div>
            </div>
            {% endif %}
            
            {% if integration_tests %}
            <div class="test-section">
                <h3>🔗 اختبارات التكامل</h3>
                <div class="test-content">
                    <div class="progress-bar">
                        <div class="progress-fill success" style="width: {{ integration_tests.success_rate }}%"></div>
                    </div>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="label">إجمالي الاختبارات</div>
                            <div class="value">{{ integration_tests.tests }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">نجح</div>
                            <div class="value success">{{ integration_tests.tests - integration_tests.failures - integration_tests.errors }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">فشل</div>
                            <div class="value danger">{{ integration_tests.failures }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">وقت التنفيذ</div>
                            <div class="value">{{ "%.2f"|format(integration_tests.time) }}s</div>
                        </div>
                    </div>
                </div>
            </div>
            {% endif %}
            
            {% if property_tests %}
            <div class="test-section">
                <h3>🎯 اختبارات الخصائص</h3>
                <div class="test-content">
                    <div class="progress-bar">
                        <div class="progress-fill success" style="width: {{ property_tests.success_rate }}%"></div>
                    </div>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="label">إجمالي الخصائص</div>
                            <div class="value">{{ property_tests.tests }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">نجح</div>
                            <div class="value success">{{ property_tests.tests - property_tests.failures - property_tests.errors }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">فشل</div>
                            <div class="value danger">{{ property_tests.failures }}</div>
                        </div>
                    </div>
                </div>
            </div>
            {% endif %}
            
            {% if coverage %}
            <div class="test-section">
                <h3>📊 تغطية الكود</h3>
                <div class="test-content">
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="label">تغطية الأسطر</div>
                            <div class="value {{ 'success' if coverage.line_coverage > 85 else 'warning' if coverage.line_coverage > 70 else 'danger' }}">
                                {{ "%.1f"|format(coverage.line_coverage) }}%
                            </div>
                        </div>
                        <div class="stat-item">
                            <div class="label">تغطية الفروع</div>
                            <div class="value {{ 'success' if coverage.branch_coverage > 80 else 'warning' if coverage.branch_coverage > 60 else 'danger' }}">
                                {{ "%.1f"|format(coverage.branch_coverage) }}%
                            </div>
                        </div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill {{ 'success' if coverage.line_coverage > 85 else 'warning' if coverage.line_coverage > 70 else 'danger' }}" 
                             style="width: {{ coverage.line_coverage }}%"></div>
                    </div>
                </div>
            </div>
            {% endif %}
            
            {% if performance %}
            <div class="test-section">
                <h3>⚡ اختبارات الأداء</h3>
                <div class="test-content">
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="label">إجمالي المعايير</div>
                            <div class="value">{{ performance.total_benchmarks }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">متوسط الوقت</div>
                            <div class="value">{{ "%.3f"|format(performance.average_time) }}s</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">أسرع اختبار</div>
                            <div class="value success">{{ "%.3f"|format(performance.fastest) }}s</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">أبطأ اختبار</div>
                            <div class="value warning">{{ "%.3f"|format(performance.slowest) }}s</div>
                        </div>
                    </div>
                </div>
            </div>
            {% endif %}
            
            {% if security_scan %}
            <div class="test-section">
                <h3>🔒 فحص الأمان</h3>
                <div class="test-content">
                    <div class="stats-grid">
                        {% if security_scan.total_issues is defined %}
                        <div class="stat-item">
                            <div class="label">إجمالي المشاكل</div>
                            <div class="value {{ 'success' if security_scan.total_issues == 0 else 'danger' }}">
                                {{ security_scan.total_issues }}
                            </div>
                        </div>
                        <div class="stat-item">
                            <div class="label">عالية الخطورة</div>
                            <div class="value danger">{{ security_scan.high_severity or 0 }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">متوسطة الخطورة</div>
                            <div class="value warning">{{ security_scan.medium_severity or 0 }}</div>
                        </div>
                        <div class="stat-item">
                            <div class="label">منخفضة الخطورة</div>
                            <div class="value info">{{ security_scan.low_severity or 0 }}</div>
                        </div>
                        {% endif %}
                        
                        {% if security_scan.total_vulnerabilities is defined %}
                        <div class="stat-item">
                            <div class="label">الثغرات المعروفة</div>
                            <div class="value {{ 'success' if security_scan.total_vulnerabilities == 0 else 'danger' }}">
                                {{ security_scan.total_vulnerabilities }}
                            </div>
                        </div>
                        <div class="stat-item">
                            <div class="label">المكتبات المتأثرة</div>
                            <div class="value">{{ security_scan.packages_affected or 0 }}</div>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
            {% endif %}
        </div>
        
        <div class="footer">
            <p>تم إنشاء هذا التقرير تلقائياً بواسطة نظام الاختبارات المتقدم</p>
            <p>{{ timestamp }}</p>
        </div>
    </div>
</body>
</html>
    """
    
    template = Template(template_html)
    html_content = template.render(**results)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ تم إنشاء التقرير الشامل: {output_file}")

def main():
    if len(sys.argv) != 3:
        print("الاستخدام: python generate_test_report.py <مجلد_التقارير> <ملف_الإخراج>")
        sys.exit(1)
    
    reports_dir = sys.argv[1]
    output_file = sys.argv[2]
    
    if not os.path.exists(reports_dir):
        print(f"❌ مجلد التقارير غير موجود: {reports_dir}")
        sys.exit(1)
    
    print("🔍 جمع نتائج الاختبارات...")
    results = collect_test_results(reports_dir)
    
    print("📊 إنشاء التقرير الشامل...")
    generate_html_report(results, output_file)
    
    # طباعة ملخص النتائج
    print("\n📋 ملخص النتائج:")
    if results['unit_tests']:
        print(f"   اختبارات الوحدة: {results['unit_tests']['success_rate']:.1f}% ({results['unit_tests']['tests']} اختبار)")
    if results['integration_tests']:
        print(f"   اختبارات التكامل: {results['integration_tests']['success_rate']:.1f}% ({results['integration_tests']['tests']} اختبار)")
    if results['coverage']:
        print(f"   تغطية الكود: {results['coverage']['line_coverage']:.1f}%")
    if results['performance']:
        print(f"   اختبارات الأداء: {results['performance']['total_benchmarks']} معيار")
    
    print(f"\n✅ التقرير الشامل جاهز: {output_file}")

if __name__ == '__main__':
    main()