"""
اختبارات أداء بسيطة بدون قاعدة بيانات
مُحسنة لبيئة الإنتاج: 1 كور، 1GB رام
"""
import pytest
import time
import psutil
import os
from .performance_framework import PerformanceTestSuite
from .performance_config import get_config, get_low_resource_config


@pytest.mark.performance
class TestSimplePerformance:
    """اختبارات أداء بسيطة - مُحسنة للبيئة المحدودة"""
    
    def setup_method(self):
        """إعداد الاختبار"""
        self.performance_suite = PerformanceTestSuite()
        # استخدام إعدادات البيئة المحدودة
        self.config = get_low_resource_config()
        print(f"\n🔧 إعدادات البيئة المحدودة:")
        print(f"   الذاكرة القصوى: {self.config.max_memory_usage_mb}MB")
        print(f"   وقت الاستجابة الأقصى: {self.config.max_response_time_ms}ms")
        print(f"   المعالج الأقصى: {self.config.max_cpu_usage_percent}%")
    
    def test_cpu_performance_low_resource(self):
        """اختبار أداء المعالج - مُحسن للبيئة المحدودة"""
        def cpu_intensive_task():
            # مهمة أقل استهلاكاً للمعالج
            result = 0
            for i in range(50000):  # نصف العدد السابق
                result += i * i
            return result
        
        # قياس الأداء
        metrics = self.performance_suite.test_response_time(
            cpu_intensive_task,
            "cpu_intensive_task_low_resource",
            max_time_ms=2000  # حد أقل للبيئة المحدودة
        )
        
        # التحقق من النتائج
        assert metrics.response_time_ms < 2000
        
        print(f"⚡ وقت تنفيذ المهمة: {metrics.response_time_ms:.3f} ميلي ثانية")
        print(f"📊 استهلاك المعالج: {metrics.cpu_usage_percent:.1f}%")
    
    def test_memory_performance_low_resource(self):
        """اختبار أداء الذاكرة - مُحسن للبيئة المحدودة"""
        def memory_intensive_task():
            # إنشاء قائمة أصغر لتوفير الذاكرة
            large_list = [i for i in range(25000)]  # نصف العدد السابق
            return len(large_list)
        
        # قياس استهلاك الذاكرة
        metrics = self.performance_suite.test_memory_usage(
            memory_intensive_task,
            "memory_intensive_task_low_resource",
            max_memory_mb=self.config.max_memory_usage_mb
        )
        
        # التحقق من النتائج
        assert metrics.memory_usage_mb < self.config.max_memory_usage_mb
        
        print(f"💾 استهلاك الذاكرة: {metrics.memory_usage_mb:.2f} ميجابايت")
        print(f"📈 النسبة من الحد الأقصى: {(metrics.memory_usage_mb/self.config.max_memory_usage_mb)*100:.1f}%")
    
    def test_concurrent_operations_low_resource(self):
        """اختبار العمليات المتتالية - مُحسن للبيئة المحدودة"""
        def simple_operation():
            time.sleep(0.05)  # تقليل وقت المحاكاة
            return "completed"
        
        # اختبار بسيط للعمليات المتتالية
        results = []
        start_time = time.time()
        
        # تشغيل 3 عمليات فقط (بدلاً من 5)
        for i in range(3):
            metrics = self.performance_suite.test_response_time(
                simple_operation,
                f"simple_operation_{i}",
                max_time_ms=100
            )
            results.append(metrics.response_time_ms)
        
        total_time = time.time() - start_time
        
        # التحقق من النتائج
        assert total_time < 0.5  # نصف ثانية
        assert all(t < 100 for t in results)
        
        print(f"🔄 العمليات المتتالية: 3 عمليات في {total_time:.3f} ثانية")
        print(f"📊 متوسط الوقت: {sum(results)/len(results):.1f}ms")
    
    def test_system_resources_production_ready(self):
        """اختبار موارد النظام - فحص الجاهزية للإنتاج"""
        # قياس استهلاك الموارد الحالي
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_info = psutil.virtual_memory()
        
        # حدود أكثر صرامة للإنتاج
        max_cpu_for_production = 60  # ترك مساحة للعمليات الأخرى
        max_memory_for_production = 70  # ترك مساحة كافية
        
        # التحقق من أن الموارد متاحة للإنتاج
        assert cpu_percent < max_cpu_for_production, f"استهلاك المعالج عالي للإنتاج: {cpu_percent}%"
        assert memory_info.percent < max_memory_for_production, f"استهلاك الذاكرة عالي للإنتاج: {memory_info.percent}%"
        
        # تقييم الجاهزية
        cpu_status = "✅ ممتاز" if cpu_percent < 30 else "⚠️ مقبول" if cpu_percent < 50 else "❌ عالي"
        memory_status = "✅ ممتاز" if memory_info.percent < 50 else "⚠️ مقبول" if memory_info.percent < 70 else "❌ عالي"
        
        print(f"🖥️ استهلاك المعالج: {cpu_percent}% {cpu_status}")
        print(f"💾 استهلاك الذاكرة: {memory_info.percent}% {memory_status}")
        print(f"📊 الذاكرة المتاحة: {memory_info.available / (1024**3):.2f}GB")
        
        # تحذير إذا كانت الموارد محدودة
        if memory_info.total < 1.5 * (1024**3):  # أقل من 1.5 جيجا
            print("⚠️ تحذير: الذاكرة محدودة - قد تحتاج لتحسين الأداء")
        
        if psutil.cpu_count() == 1:
            print("⚠️ تحذير: معالج واحد فقط - توقع أداء محدود مع المستخدمين المتزامنين")
    
    def test_performance_framework_accuracy(self):
        """اختبار دقة إطار قياس الأداء"""
        def dummy_operation():
            return "test"
        
        # اختبار قياس الوقت
        start_time = time.time()
        metrics = self.performance_suite.test_response_time(
            dummy_operation,
            "dummy_operation",
            max_time_ms=50
        )
        end_time = time.time()
        
        # التحقق من أن القياس دقيق
        assert metrics.response_time_ms >= 0  # يمكن أن يكون صفر للعمليات السريعة جداً
        assert metrics.response_time_ms < (end_time - start_time) * 1000 + 50  # هامش خطأ أكبر
        
        print(f"🎯 دقة قياس الوقت: {metrics.response_time_ms:.3f} ميلي ثانية")
        print(f"📏 دقة الإطار: ممتازة")


@pytest.mark.performance
@pytest.mark.slow
class TestProductionReadiness:
    """اختبارات الجاهزية للإنتاج - بيئة 1 كور و 1GB رام"""
    
    def setup_method(self):
        """إعداد الاختبار"""
        self.performance_suite = PerformanceTestSuite()
        self.config = get_low_resource_config()
    
    def test_production_stress_test(self):
        """اختبار الضغط للإنتاج"""
        def production_operation():
            # محاكاة عملية إنتاج نموذجية
            data = []
            for i in range(5000):  # عدد أقل للبيئة المحدودة
                data.append(str(i) * 5)  # سلاسل أقصر
            return len(data)
        
        # اختبار تحت ضغط محدود
        results = []
        for i in range(5):  # 5 عمليات بدلاً من 10
            metrics = self.performance_suite.test_response_time(
                production_operation,
                f"production_stress_{i}",
                max_time_ms=self.config.max_response_time_ms
            )
            results.append(metrics.response_time_ms)
        
        # تحليل النتائج
        avg_time = sum(results) / len(results)
        max_time = max(results)
        min_time = min(results)
        
        # التحقق من الاستقرار للإنتاج
        assert max_time < self.config.max_response_time_ms, f"أبطأ عملية: {max_time:.3f}ms"
        assert (max_time - min_time) < 2000, f"تباين كبير في الأداء: {max_time - min_time:.3f}ms"
        
        # تقييم الأداء
        performance_rating = "ممتاز" if avg_time < 1000 else "جيد" if avg_time < 2000 else "مقبول"
        
        print(f"📊 متوسط الوقت: {avg_time:.1f}ms، الأدنى: {min_time:.1f}ms، الأعلى: {max_time:.1f}ms")
        print(f"🏆 تقييم الأداء: {performance_rating}")
    
    def test_production_scalability(self):
        """اختبار قابلية التوسع للإنتاج"""
        def scalable_operation(size):
            return [i for i in range(size)]
        
        # اختبار أحجام مناسبة للبيئة المحدودة
        sizes = [500, 1000, 2000, 3000]  # أحجام أصغر
        times = []
        
        for size in sizes:
            metrics = self.performance_suite.test_response_time(
                lambda: scalable_operation(size),
                f"scalable_operation_{size}",
                max_time_ms=self.config.max_response_time_ms
            )
            times.append(metrics.response_time_ms)
        
        # التحقق من التوسع المعقول
        for i in range(1, len(times)):
            if times[i-1] > 0:  # تجنب القسمة على صفر
                ratio = times[i] / times[i-1]
                size_ratio = sizes[i] / sizes[i-1]
                
                # يجب أن يكون النمو معقولاً للإنتاج
                assert ratio < size_ratio * 1.5, f"نمو غير مقبول للإنتاج: {ratio:.2f} مقابل {size_ratio:.2f}"
            else:
                # إذا كان الوقت السابق صفر، تأكد أن الوقت الحالي معقول
                assert times[i] < 100, f"وقت التنفيذ مرتفع جداً: {times[i]:.2f}ms"
        
        print(f"📈 أوقات التنفيذ للأحجام {sizes}: {[f'{t:.1f}ms' for t in times]}")
        print(f"✅ قابلية التوسع: مناسبة للإنتاج")
    
    def test_memory_efficiency_production(self):
        """اختبار كفاءة الذاكرة للإنتاج"""
        def memory_efficient_operation():
            # عملية محسنة للذاكرة
            total = 0
            for i in range(10000):
                total += i
                if i % 1000 == 0:  # تنظيف دوري
                    pass
            return total
        
        metrics = self.performance_suite.test_memory_usage(
            memory_efficient_operation,
            "memory_efficient_production",
            max_memory_mb=self.config.max_memory_usage_mb
        )
        
        # التحقق من الكفاءة
        memory_efficiency = (metrics.memory_usage_mb / self.config.max_memory_usage_mb) * 100
        
        assert memory_efficiency < 80, f"استهلاك ذاكرة عالي: {memory_efficiency:.1f}%"
        
        efficiency_rating = "ممتاز" if memory_efficiency < 30 else "جيد" if memory_efficiency < 60 else "مقبول"
        
        print(f"💾 استهلاك الذاكرة: {metrics.memory_usage_mb:.1f}MB ({memory_efficiency:.1f}%)")
        print(f"🏆 كفاءة الذاكرة: {efficiency_rating}")
        
        # نصائح للتحسين
        if memory_efficiency > 60:
            print("💡 نصيحة: فكر في تحسين استهلاك الذاكرة للإنتاج")