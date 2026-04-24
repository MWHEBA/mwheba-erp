"""
إطار عمل اختبارات الأداء المتقدم
Performance Testing Framework

يوفر أدوات شاملة لقياس الأداء ومراقبة الموارد
"""
import time
import psutil
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from contextlib import contextmanager
from django.test import TestCase, Client
from django.db import connection
from django.core.management import call_command
from django.conf import settings
import pytest
import json
import os
from datetime import datetime
import statistics


@dataclass
class PerformanceMetrics:
    """مقاييس الأداء"""
    operation_name: str
    response_time_ms: float
    memory_usage_mb: float
    cpu_usage_percent: float
    database_queries_count: int
    database_time_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    additional_data: Dict[str, Any] = field(default_factory=dict)
    
    def is_within_limits(self, limits: 'PerformanceLimits') -> bool:
        """التحقق من الحدود المسموحة"""
        return (
            self.response_time_ms <= limits.max_response_time_ms and
            self.memory_usage_mb <= limits.max_memory_mb and
            self.cpu_usage_percent <= limits.max_cpu_percent
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            'operation_name': self.operation_name,
            'response_time_ms': self.response_time_ms,
            'memory_usage_mb': self.memory_usage_mb,
            'cpu_usage_percent': self.cpu_usage_percent,
            'database_queries_count': self.database_queries_count,
            'database_time_ms': self.database_time_ms,
            'timestamp': self.timestamp.isoformat(),
            'additional_data': self.additional_data
        }


@dataclass
class PerformanceLimits:
    """حدود الأداء المسموحة"""
    max_response_time_ms: float = 2000.0  # 2 ثانية
    max_memory_mb: float = 1024.0  # 1024 MB - زيادة الحد للبيئة الاختبارية
    max_cpu_percent: float = 80.0  # 80%
    max_database_queries: int = 50  # 50 استعلام
    max_database_time_ms: float = 1000.0  # 1 ثانية


class ResourceMonitor:
    """مراقب الموارد"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.monitoring = False
        self.metrics = []
        self.monitor_thread = None
    
    def start_monitoring(self, interval: float = 0.1):
        """بدء مراقبة الموارد"""
        self.monitoring = True
        self.metrics = []
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, 
            args=(interval,)
        )
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """إيقاف مراقبة الموارد"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
    
    def _monitor_loop(self, interval: float):
        """حلقة مراقبة الموارد"""
        while self.monitoring:
            try:
                memory_info = self.process.memory_info()
                cpu_percent = self.process.cpu_percent()
                
                self.metrics.append({
                    'timestamp': time.time(),
                    'memory_mb': memory_info.rss / 1024 / 1024,
                    'cpu_percent': cpu_percent
                })
                
                time.sleep(interval)
            except Exception:
                break
    
    def get_peak_memory(self) -> float:
        """الحصول على ذروة استهلاك الذاكرة"""
        if not self.metrics:
            return 0.0
        return max(metric['memory_mb'] for metric in self.metrics)
    
    def get_average_cpu(self) -> float:
        """الحصول على متوسط استهلاك المعالج"""
        if not self.metrics:
            return 0.0
        cpu_values = [metric['cpu_percent'] for metric in self.metrics]
        return statistics.mean(cpu_values)


class DatabaseQueryMonitor:
    """مراقب استعلامات قاعدة البيانات"""
    
    def __init__(self):
        self.queries_count = 0
        self.total_time = 0.0
        self.queries = []
    
    def __enter__(self):
        """بدء مراقبة الاستعلامات"""
        self.initial_queries = len(connection.queries)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """انتهاء مراقبة الاستعلامات"""
        final_queries = connection.queries[self.initial_queries:]
        self.queries_count = len(final_queries)
        self.total_time = sum(float(query['time']) for query in final_queries)
        self.queries = final_queries


class PerformanceTestSuite:
    """مجموعة اختبارات الأداء"""
    
    def __init__(self, limits: Optional[PerformanceLimits] = None):
        self.limits = limits or PerformanceLimits()
        self.resource_monitor = ResourceMonitor()
        self.results = []
    
    @contextmanager
    def measure_performance(self, operation_name: str):
        """قياس أداء عملية"""
        # بدء المراقبة
        self.resource_monitor.start_monitoring()
        
        # مراقبة قاعدة البيانات
        with DatabaseQueryMonitor() as db_monitor:
            start_time = time.time()
            
            try:
                yield
            finally:
                # حساب الوقت
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                # إيقاف مراقبة الموارد
                self.resource_monitor.stop_monitoring()
                
                # جمع المقاييس
                metrics = PerformanceMetrics(
                    operation_name=operation_name,
                    response_time_ms=response_time_ms,
                    memory_usage_mb=self.resource_monitor.get_peak_memory(),
                    cpu_usage_percent=self.resource_monitor.get_average_cpu(),
                    database_queries_count=db_monitor.queries_count,
                    database_time_ms=db_monitor.total_time * 1000
                )
                
                self.results.append(metrics)
    
    def test_response_time(self, operation: Callable, operation_name: str, 
                          max_time_ms: float = None) -> PerformanceMetrics:
        """اختبار وقت الاستجابة"""
        max_time = max_time_ms or self.limits.max_response_time_ms
        
        with self.measure_performance(operation_name):
            operation()
        
        metrics = self.results[-1]
        assert metrics.response_time_ms <= max_time, (
            f"وقت الاستجابة {metrics.response_time_ms:.2f}ms "
            f"يتجاوز الحد المسموح {max_time}ms"
        )
        
        return metrics
    
    def test_memory_usage(self, operation: Callable, operation_name: str,
                         max_memory_mb: float = None) -> PerformanceMetrics:
        """اختبار استهلاك الذاكرة"""
        max_memory = max_memory_mb or self.limits.max_memory_mb
        
        with self.measure_performance(operation_name):
            operation()
        
        metrics = self.results[-1]
        assert metrics.memory_usage_mb <= max_memory, (
            f"استهلاك الذاكرة {metrics.memory_usage_mb:.2f}MB "
            f"يتجاوز الحد المسموح {max_memory}MB"
        )
        
        return metrics
    
    def test_database_performance(self, operation: Callable, operation_name: str,
                                 max_queries: int = None, 
                                 max_time_ms: float = None) -> PerformanceMetrics:
        """اختبار أداء قاعدة البيانات"""
        max_q = max_queries or self.limits.max_database_queries
        max_t = max_time_ms or self.limits.max_database_time_ms
        
        with self.measure_performance(operation_name):
            operation()
        
        metrics = self.results[-1]
        
        assert metrics.database_queries_count <= max_q, (
            f"عدد الاستعلامات {metrics.database_queries_count} "
            f"يتجاوز الحد المسموح {max_q}"
        )
        
        assert metrics.database_time_ms <= max_t, (
            f"وقت قاعدة البيانات {metrics.database_time_ms:.2f}ms "
            f"يتجاوز الحد المسموح {max_t}ms"
        )
        
        return metrics
    
    def generate_report(self, output_file: str = None) -> Dict[str, Any]:
        """إنشاء تقرير الأداء"""
        if not self.results:
            return {"error": "لا توجد نتائج للتقرير"}
        
        # حساب الإحصائيات
        response_times = [r.response_time_ms for r in self.results]
        memory_usage = [r.memory_usage_mb for r in self.results]
        cpu_usage = [r.cpu_usage_percent for r in self.results]
        db_queries = [r.database_queries_count for r in self.results]
        db_times = [r.database_time_ms for r in self.results]
        
        report = {
            "summary": {
                "total_tests": len(self.results),
                "passed_tests": sum(1 for r in self.results if r.is_within_limits(self.limits)),
                "failed_tests": sum(1 for r in self.results if not r.is_within_limits(self.limits))
            },
            "response_time_stats": {
                "min_ms": min(response_times),
                "max_ms": max(response_times),
                "avg_ms": statistics.mean(response_times),
                "median_ms": statistics.median(response_times)
            },
            "memory_stats": {
                "min_mb": min(memory_usage),
                "max_mb": max(memory_usage),
                "avg_mb": statistics.mean(memory_usage),
                "median_mb": statistics.median(memory_usage)
            },
            "cpu_stats": {
                "min_percent": min(cpu_usage),
                "max_percent": max(cpu_usage),
                "avg_percent": statistics.mean(cpu_usage),
                "median_percent": statistics.median(cpu_usage)
            },
            "database_stats": {
                "min_queries": min(db_queries),
                "max_queries": max(db_queries),
                "avg_queries": statistics.mean(db_queries),
                "total_db_time_ms": sum(db_times)
            },
            "limits": {
                "max_response_time_ms": self.limits.max_response_time_ms,
                "max_memory_mb": self.limits.max_memory_mb,
                "max_cpu_percent": self.limits.max_cpu_percent,
                "max_database_queries": self.limits.max_database_queries,
                "max_database_time_ms": self.limits.max_database_time_ms
            },
            "detailed_results": [r.to_dict() for r in self.results],
            "timestamp": datetime.now().isoformat()
        }
        
        # حفظ التقرير
        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        
        return report


class LoadGenerator:
    """مولد الحمولة للاختبارات"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.clients = []
        self.results = []
    
    def create_clients(self, count: int) -> List[Client]:
        """إنشاء عملاء للاختبار"""
        self.clients = [Client() for _ in range(count)]
        return self.clients
    
    def simulate_concurrent_users(self, user_count: int, duration: int,
                                 operations: List[Callable]) -> List[Dict]:
        """محاكاة مستخدمين متزامنين"""
        self.results = []
        threads = []
        
        def user_simulation(user_id: int):
            """محاكاة مستخدم واحد"""
            client = Client()
            start_time = time.time()
            operation_count = 0
            
            while time.time() - start_time < duration:
                for operation in operations:
                    try:
                        operation_start = time.time()
                        operation(client)
                        operation_time = (time.time() - operation_start) * 1000
                        
                        self.results.append({
                            'user_id': user_id,
                            'operation_count': operation_count,
                            'response_time_ms': operation_time,
                            'timestamp': time.time()
                        })
                        
                        operation_count += 1
                    except Exception as e:
                        self.results.append({
                            'user_id': user_id,
                            'operation_count': operation_count,
                            'error': str(e),
                            'timestamp': time.time()
                        })
                
                # فترة راحة قصيرة
                time.sleep(0.1)
        
        # إنشاء وتشغيل الخيوط
        for i in range(user_count):
            thread = threading.Thread(target=user_simulation, args=(i,))
            threads.append(thread)
            thread.start()
        
        # انتظار انتهاء جميع الخيوط
        for thread in threads:
            thread.join()
        
        return self.results
    
    def analyze_load_test_results(self) -> Dict[str, Any]:
        """تحليل نتائج اختبار الحمولة"""
        if not self.results:
            return {"error": "لا توجد نتائج للتحليل"}
        
        # فصل النتائج الناجحة والفاشلة
        successful_results = [r for r in self.results if 'error' not in r]
        failed_results = [r for r in self.results if 'error' in r]
        
        if successful_results:
            response_times = [r['response_time_ms'] for r in successful_results]
            
            analysis = {
                "total_operations": len(self.results),
                "successful_operations": len(successful_results),
                "failed_operations": len(failed_results),
                "success_rate": len(successful_results) / len(self.results) * 100,
                "response_time_stats": {
                    "min_ms": min(response_times),
                    "max_ms": max(response_times),
                    "avg_ms": statistics.mean(response_times),
                    "median_ms": statistics.median(response_times),
                    "p95_ms": sorted(response_times)[int(len(response_times) * 0.95)],
                    "p99_ms": sorted(response_times)[int(len(response_times) * 0.99)]
                },
                "errors": [r['error'] for r in failed_results]
            }
        else:
            analysis = {
                "total_operations": len(self.results),
                "successful_operations": 0,
                "failed_operations": len(failed_results),
                "success_rate": 0,
                "errors": [r['error'] for r in failed_results]
            }
        
        return analysis


# Decorators للاختبارات
def performance_test(max_response_time_ms: float = 2000, 
                    max_memory_mb: float = 512,
                    max_cpu_percent: float = 80):
    """ديكوريتر لاختبارات الأداء"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            limits = PerformanceLimits(
                max_response_time_ms=max_response_time_ms,
                max_memory_mb=max_memory_mb,
                max_cpu_percent=max_cpu_percent
            )
            
            suite = PerformanceTestSuite(limits)
            
            with suite.measure_performance(func.__name__):
                result = func(*args, **kwargs)
            
            # التحقق من الحدود
            metrics = suite.results[-1]
            assert metrics.is_within_limits(limits), (
                f"اختبار الأداء فشل: {func.__name__}\n"
                f"وقت الاستجابة: {metrics.response_time_ms:.2f}ms "
                f"(الحد الأقصى: {max_response_time_ms}ms)\n"
                f"استهلاك الذاكرة: {metrics.memory_usage_mb:.2f}MB "
                f"(الحد الأقصى: {max_memory_mb}MB)\n"
                f"استهلاك المعالج: {metrics.cpu_usage_percent:.2f}% "
                f"(الحد الأقصى: {max_cpu_percent}%)"
            )
            
            return result
        return wrapper
    return decorator


def benchmark_test(iterations: int = 10):
    """ديكوريتر لاختبارات المعايير"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            times = []
            
            for _ in range(iterations):
                start_time = time.time()
                func(*args, **kwargs)
                end_time = time.time()
                times.append((end_time - start_time) * 1000)
            
            # إحصائيات الأداء
            avg_time = statistics.mean(times)
            min_time = min(times)
            max_time = max(times)
            median_time = statistics.median(times)
            
            print(f"\n📊 نتائج اختبار المعايير: {func.__name__}")
            print(f"   التكرارات: {iterations}")
            print(f"   متوسط الوقت: {avg_time:.2f}ms")
            print(f"   أسرع وقت: {min_time:.2f}ms")
            print(f"   أبطأ وقت: {max_time:.2f}ms")
            print(f"   الوسيط: {median_time:.2f}ms")
            
            return {
                'avg_time_ms': avg_time,
                'min_time_ms': min_time,
                'max_time_ms': max_time,
                'median_time_ms': median_time,
                'all_times_ms': times
            }
        return wrapper
    return decorator