/**
 * مراقب الاتصال - Connection Monitor
 * يراقب حالة الاتصال ويعرض تنبيهات للمستخدم
 */

class ConnectionMonitor {
    constructor() {
        this.isOnline = navigator.onLine;
        this.retryAttempts = 0;
        this.maxRetryAttempts = 3;
        this.retryDelay = 2000;
        this.init();
    }

    init() {
        this.createStatusIndicator();
        this.bindEvents();
        this.startPeriodicCheck();
    }

    bindEvents() {
        // مراقبة أحداث الاتصال
        window.addEventListener('online', () => this.handleOnline());
        window.addEventListener('offline', () => this.handleOffline());
        
        // مراقبة تغيير visibility للصفحة
        document.addEventListener('visibilitychange', () => this.handleVisibilityChange());
    }

    createStatusIndicator() {
        // إنشاء مؤشر حالة الاتصال
        const indicator = document.createElement('div');
        indicator.id = 'connection-indicator';
        indicator.className = 'connection-indicator position-fixed';
        indicator.style.cssText = `
            top: 10px;
            left: 10px;
            z-index: 10000;
            padding: 8px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.3s ease;
            display: none;
        `;
        
        document.body.appendChild(indicator);
        this.updateIndicator();
    }

    updateIndicator() {
        const indicator = document.getElementById('connection-indicator');
        if (!indicator) return;

        if (this.isOnline) {
            indicator.innerHTML = '<i class="fas fa-wifi me-1"></i>متصل';
            indicator.className = 'connection-indicator position-fixed bg-success text-white';
            indicator.style.display = 'none'; // إخفاء عند الاتصال الطبيعي
        } else {
            indicator.innerHTML = '<i class="fas fa-wifi-slash me-1"></i>غير متصل';
            indicator.className = 'connection-indicator position-fixed bg-danger text-white';
            indicator.style.display = 'block';
        }
    }

    handleOnline() {
        this.isOnline = true;
        this.retryAttempts = 0;
        this.updateIndicator();
        
        // إظهار رسالة استعادة الاتصال
        this.showNotification('تم استعادة الاتصال بالإنترنت', 'success', 3000);
        
        // إعادة تحميل البيانات المعلقة
        this.retryPendingRequests();
    }

    handleOffline() {
        this.isOnline = false;
        this.updateIndicator();
        
        // إظهار رسالة انقطاع الاتصال
        this.showNotification('انقطع الاتصال بالإنترنت', 'warning', 0); // 0 = لا يختفي تلقائياً
    }

    handleVisibilityChange() {
        if (!document.hidden && !this.isOnline) {
            // عند العودة للصفحة، تحقق من الاتصال
            this.checkConnection();
        }
    }

    async checkConnection() {
        try {
            // محاولة الوصول لملف صغير من الخادم
            const response = await fetch('/static/js/connection-test.txt?' + Date.now(), {
                method: 'HEAD',
                cache: 'no-cache'
            });
            
            const wasOffline = !this.isOnline;
            this.isOnline = response.ok;
            
            if (wasOffline && this.isOnline) {
                this.handleOnline();
            } else if (!wasOffline && !this.isOnline) {
                this.handleOffline();
            }
            
            this.updateIndicator();
        } catch (error) {
            if (this.isOnline) {
                this.handleOffline();
            }
        }
    }

    startPeriodicCheck() {
        // فحص دوري كل 30 ثانية
        setInterval(() => {
            if (!navigator.onLine || !this.isOnline) {
                this.checkConnection();
            }
        }, 30000);
    }

    async retryPendingRequests() {
        // إعادة محاولة الطلبات المعلقة
        const event = new CustomEvent('connectionRestored');
        document.dispatchEvent(event);
    }

    showNotification(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'success' ? 'success' : type === 'warning' ? 'warning' : 'info'} alert-dismissible fade show position-fixed`;
        notification.style.cssText = `
            top: 60px;
            left: 10px;
            z-index: 9999;
            min-width: 300px;
            max-width: 400px;
        `;
        
        notification.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(notification);
        
        // إزالة تلقائية
        if (duration > 0) {
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, duration);
        }
        
        // إزالة عند النقر على الإغلاق
        notification.addEventListener('closed.bs.alert', () => {
            notification.remove();
        });
    }

    // دالة للتحقق من الاتصال قبل إرسال طلب
    async ensureConnection() {
        if (!navigator.onLine) {
            throw new Error('لا يوجد اتصال بالإنترنت');
        }
        
        if (!this.isOnline) {
            await this.checkConnection();
            if (!this.isOnline) {
                throw new Error('لا يمكن الوصول للخادم');
            }
        }
        
        return true;
    }

    // دالة لإعادة المحاولة مع تأخير
    async retryWithDelay(requestFn, maxAttempts = 3) {
        let lastError;
        
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                await this.ensureConnection();
                return await requestFn();
            } catch (error) {
                lastError = error;
                console.warn(`محاولة ${attempt} فشلت:`, error.message);
                
                if (attempt < maxAttempts) {
                    const delay = this.retryDelay * attempt;
                    await new Promise(resolve => setTimeout(resolve, delay));
                }
            }
        }
        
        throw lastError;
    }

    // دالة للحصول على حالة الاتصال
    getConnectionStatus() {
        return {
            isOnline: this.isOnline,
            navigatorOnline: navigator.onLine,
            retryAttempts: this.retryAttempts
        };
    }
}

// إنشاء ملف اختبار الاتصال إذا لم يكن موجوداً
function createConnectionTestFile() {
    // هذا الملف سيتم إنشاؤه من الخادم
    // أو يمكن استخدام endpoint خاص للاختبار
}

// تهيئة مراقب الاتصال
document.addEventListener('DOMContentLoaded', function() {
    window.connectionMonitor = new ConnectionMonitor();
    
    // إضافة دوال مساعدة عامة
    window.checkConnection = () => window.connectionMonitor.checkConnection();
    window.retryWithConnection = (fn, attempts) => window.connectionMonitor.retryWithDelay(fn, attempts);
});

// تصدير للاستخدام في ملفات أخرى
window.ConnectionMonitor = ConnectionMonitor;