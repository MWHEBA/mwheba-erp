/**
 * 🔒 Global CSRF Auto-Sync & Recovery Handler
 * MWHEBA ERP System
 * 
 * هذا الملف يتكفل بحل مشاكل CSRF verification failed جذرياً عبر:
 * 1. المزامنة اللحظية لرمز CSRF من الكوكيز إلى جميع حقول النماذج قبل الإرسال لمنع عدم تطابق الـ Tabs المفتوحة.
 * 2. تزويد جميع طلبات jQuery AJAX و Fetch بالـ X-CSRFToken تلقائياً.
 * 3. التقاط أخطاء الـ 403 CSRF ومعالجتها في الخلفية بسلاسة دون مقاطعة المستخدم.
 */

(function() {
    'use strict';

    /**
     * استخراج قيمة الـ Cookie بأمان
     */
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * الحصول على أحدث رمز CSRF متاح (من الكوكي أولاً، ثم الميتا تاج)
     */
    function getFreshCsrfToken() {
        const tokenFromCookie = getCookie('csrftoken');
        if (tokenFromCookie) return tokenFromCookie;
        
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag && metaTag.content) return metaTag.content;
        
        const existingInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (existingInput && existingInput.value) return existingInput.value;
        
        return '';
    }

    /**
     * ✅ 1. المزامنة التلقائية لجميع نماذج الـ HTML قبل الإرسال (Form Submit)
     * تضمن هذه الخطوة أنه حتى لو تم تسجيل الدخول في تبويب آخر أو تجديد الرمز،
     * فإن النموذج الحالي يرسل دائماً أحدث رمز صالح في الكوكيز.
     */
    document.addEventListener('submit', function(event) {
        const form = event.target;
        if (form && form.tagName === 'FORM') {
            const method = (form.getAttribute('method') || 'GET').toUpperCase();
            if (method === 'POST') {
                const freshToken = getFreshCsrfToken();
                if (freshToken) {
                    let csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
                    if (csrfInput) {
                        csrfInput.value = freshToken;
                    } else {
                        csrfInput = document.createElement('input');
                        csrfInput.type = 'hidden';
                        csrfInput.name = 'csrfmiddlewaretoken';
                        csrfInput.value = freshToken;
                        form.appendChild(csrfInput);
                    }
                }
            }
        }
    }, true); // useCapture = true لتشغيلها قبل أي معالج submit آخر

    /**
     * ✅ 2. إعداد jQuery AJAX التلقائي
     */
    function setupJQueryAjax() {
        if (window.jQuery) {
            const $ = window.jQuery;
            
            function isCsrfSafe(method) {
                return (/^(GET|HEAD|OPTIONS|TRACE)$/i.test(method));
            }

            $.ajaxPrefilter(function(options, originalOptions, jqXHR) {
                if (!isCsrfSafe(options.type) && !options.crossDomain) {
                    const token = getFreshCsrfToken();
                    if (token) {
                        jqXHR.setRequestHeader('X-CSRFToken', token);
                    }
                }
            });

            // معالجة استجابات خطأ CSRF
            $(document).ajaxError(function(event, jqXHR, ajaxSettings, thrownError) {
                if (jqXHR.status === 403) {
                    try {
                        const response = jqXHR.responseJSON || JSON.parse(jqXHR.responseText);
                        if (response && response.code === 'CSRF_FAILURE') {
                            if (response.csrf_token) {
                                document.cookie = 'csrftoken=' + response.csrf_token + '; path=/; SameSite=Lax';
                            }
                            if (window.showToastr) {
                                window.showToastr('تم تحديث رمز الأمان، يرجى إعادة المحاولة.', 'info');
                            }
                        }
                    } catch (e) {
                        // ليس JSON
                    }
                }
            });
        }
    }

    /**
     * ✅ 3. اعتراض وتحديث دالة fetch الأصلية لدعم CSRF تلقائياً
     */
    if (window.fetch) {
        const originalFetch = window.fetch;
        window.fetch = function(input, init) {
            init = init || {};
            const method = (init.method || 'GET').toUpperCase();
            const isSafe = /^(GET|HEAD|OPTIONS|TRACE)$/i.test(method);
            
            if (!isSafe) {
                const token = getFreshCsrfToken();
                if (token) {
                    if (!init.headers) {
                        init.headers = { 'X-CSRFToken': token };
                    } else if (init.headers instanceof Headers) {
                        if (!init.headers.has('X-CSRFToken')) {
                            init.headers.append('X-CSRFToken', token);
                        }
                    } else if (Array.isArray(init.headers)) {
                        if (!init.headers.some(function(h) { return h[0].toLowerCase() === 'x-csrftoken'; })) {
                            init.headers.push(['X-CSRFToken', token]);
                        }
                    } else if (typeof init.headers === 'object') {
                        if (!init.headers['X-CSRFToken']) {
                            init.headers['X-CSRFToken'] = token;
                        }
                    }
                }
            }
            return originalFetch.apply(this, [input, init]);
        };
    }

    // تشغيل عند تحميل DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupJQueryAjax);
    } else {
        setupJQueryAjax();
    }

    // تصدير الدوال للاستخدام العام إذا دعت الحاجة
    window.getCookie = window.getCookie || getCookie;
    window.getFreshCsrfToken = getFreshCsrfToken;
})();
