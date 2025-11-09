/**
 * ✅ JWT Auto-Refresh System
 * يقوم بتحديث Access Token تلقائياً قبل انتهاء صلاحيته
 */

class JWTAutoRefresh {
    constructor(options = {}) {
        this.accessToken = options.accessToken || localStorage.getItem('access_token');
        this.refreshToken = options.refreshToken || localStorage.getItem('refresh_token');
        this.refreshUrl = options.refreshUrl || '/api/token/refresh/';
        this.refreshInterval = options.refreshInterval || 12 * 60 * 1000; // 12 دقيقة (قبل انتهاء 15 دقيقة)
        this.onRefreshSuccess = options.onRefreshSuccess || null;
        this.onRefreshError = options.onRefreshError || null;
        this.intervalId = null;
    }

    /**
     * بدء نظام Auto-refresh
     */
    start() {
        if (!this.refreshToken) {
            console.warn('JWT Auto-Refresh: No refresh token found');
            return;
        }

        console.log('JWT Auto-Refresh: Started');
        
        // تحديث فوري عند البدء (إذا كان Token قديم)
        this.checkAndRefresh();
        
        // جدولة التحديث الدوري
        this.intervalId = setInterval(() => {
            this.checkAndRefresh();
        }, this.refreshInterval);
    }

    /**
     * إيقاف نظام Auto-refresh
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log('JWT Auto-Refresh: Stopped');
        }
    }

    /**
     * التحقق وتحديث Token
     */
    async checkAndRefresh() {
        try {
            // التحقق إذا كان Token سينتهي قريباً
            if (this.isTokenExpiringSoon()) {
                console.log('JWT Auto-Refresh: Token expiring soon, refreshing...');
                await this.refresh();
            }
        } catch (error) {
            console.error('JWT Auto-Refresh: Error checking token', error);
        }
    }

    /**
     * التحقق إذا كان Token سينتهي قريباً
     */
    isTokenExpiringSoon() {
        if (!this.accessToken) return true;

        try {
            // فك تشفير JWT Token
            const payload = this.parseJwt(this.accessToken);
            const exp = payload.exp * 1000; // تحويل لـ milliseconds
            const now = Date.now();
            const timeLeft = exp - now;

            // إذا بقي أقل من 3 دقائق
            return timeLeft < 3 * 60 * 1000;
        } catch (error) {
            console.error('JWT Auto-Refresh: Error parsing token', error);
            return true;
        }
    }

    /**
     * تحديث Access Token
     */
    async refresh() {
        try {
            const response = await fetch(this.refreshUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    refresh: this.refreshToken
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            // تحديث Tokens
            this.accessToken = data.access;
            if (data.refresh) {
                this.refreshToken = data.refresh;
            }

            // حفظ في localStorage
            localStorage.setItem('access_token', this.accessToken);
            if (data.refresh) {
                localStorage.setItem('refresh_token', this.refreshToken);
            }

            console.log('JWT Auto-Refresh: Token refreshed successfully');

            // استدعاء callback
            if (this.onRefreshSuccess) {
                this.onRefreshSuccess(data);
            }

            return data;

        } catch (error) {
            console.error('JWT Auto-Refresh: Refresh failed', error);

            // استدعاء callback
            if (this.onRefreshError) {
                this.onRefreshError(error);
            }

            // إذا فشل Refresh، قد يحتاج المستخدم لتسجيل الدخول مرة أخرى
            this.handleRefreshFailure();

            throw error;
        }
    }

    /**
     * معالجة فشل Refresh
     */
    handleRefreshFailure() {
        // حذف Tokens
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        
        // إيقاف Auto-refresh
        this.stop();

        // إعادة توجيه لصفحة Login (اختياري)
        // window.location.href = '/login/';
    }

    /**
     * فك تشفير JWT Token
     */
    parseJwt(token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));

            return JSON.parse(jsonPayload);
        } catch (error) {
            console.error('JWT Auto-Refresh: Error parsing JWT', error);
            return null;
        }
    }

    /**
     * الحصول على Access Token الحالي
     */
    getAccessToken() {
        return this.accessToken;
    }

    /**
     * تحديث Tokens يدوياً
     */
    setTokens(accessToken, refreshToken) {
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
        
        localStorage.setItem('access_token', accessToken);
        localStorage.setItem('refresh_token', refreshToken);
    }
}

// ✅ تصدير للاستخدام العام
window.JWTAutoRefresh = JWTAutoRefresh;

// ✅ إنشاء instance عام (اختياري)
window.jwtAutoRefresh = null;

/**
 * دالة مساعدة لبدء Auto-refresh
 */
function initJWTAutoRefresh(options = {}) {
    if (window.jwtAutoRefresh) {
        window.jwtAutoRefresh.stop();
    }

    window.jwtAutoRefresh = new JWTAutoRefresh({
        ...options,
        onRefreshSuccess: (data) => {
            console.log('✅ Token refreshed successfully');
            if (options.onRefreshSuccess) {
                options.onRefreshSuccess(data);
            }
        },
        onRefreshError: (error) => {
            console.error('❌ Token refresh failed:', error);
            if (options.onRefreshError) {
                options.onRefreshError(error);
            }
        }
    });

    window.jwtAutoRefresh.start();
    return window.jwtAutoRefresh;
}

// ✅ تصدير الدالة المساعدة
window.initJWTAutoRefresh = initJWTAutoRefresh;

/**
 * مثال على الاستخدام:
 * 
 * // في صفحة Login بعد النجاح:
 * localStorage.setItem('access_token', response.access);
 * localStorage.setItem('refresh_token', response.refresh);
 * initJWTAutoRefresh();
 * 
 * // في صفحات أخرى:
 * if (localStorage.getItem('access_token')) {
 *     initJWTAutoRefresh();
 * }
 * 
 * // عند Logout:
 * if (window.jwtAutoRefresh) {
 *     window.jwtAutoRefresh.stop();
 * }
 * localStorage.removeItem('access_token');
 * localStorage.removeItem('refresh_token');
 */
