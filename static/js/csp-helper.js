/**
 * 🔒 CSP Helper - مساعد Content Security Policy
 * أدوات لتسهيل التعامل مع CSP في التطبيق
 */

(function() {
    'use strict';

    // CSP Helper Object
    window.CSPHelper = {
        
        /**
         * إنشاء script element مع nonce تلقائياً
         * @param {string} code - الكود المراد تنفيذه
         * @param {string} nonce - nonce value (اختياري)
         */
        createScript: function(code, nonce) {
            const script = document.createElement('script');
            
            // الحصول على nonce من meta tag إذا لم يتم تمريره
            if (!nonce) {
                const metaTag = document.querySelector('meta[name="csp-nonce"]');
                nonce = metaTag ? metaTag.getAttribute('content') : null;
            }
            
            if (nonce) {
                script.setAttribute('nonce', nonce);
            }
            
            script.textContent = code;
            return script;
        },

        /**
         * تنفيذ JavaScript code مع CSP compliance
         * @param {string} code - الكود المراد تنفيذه
         * @param {string} nonce - nonce value (اختياري)
         */
        executeScript: function(code, nonce) {
            const script = this.createScript(code, nonce);
            document.head.appendChild(script);
            document.head.removeChild(script);
        },

        /**
         * إنشاء style element مع nonce تلقائياً
         * @param {string} css - CSS المراد إضافته
         * @param {string} nonce - nonce value (اختياري)
         */
        createStyle: function(css, nonce) {
            const style = document.createElement('style');
            
            // الحصول على nonce من meta tag إذا لم يتم تمريره
            if (!nonce) {
                const metaTag = document.querySelector('meta[name="csp-nonce"]');
                nonce = metaTag ? metaTag.getAttribute('content') : null;
            }
            
            if (nonce) {
                style.setAttribute('nonce', nonce);
            }
            
            style.textContent = css;
            return style;
        },

        /**
         * إضافة CSS مع CSP compliance
         * @param {string} css - CSS المراد إضافته
         * @param {string} nonce - nonce value (اختياري)
         */
        addStyle: function(css, nonce) {
            const style = this.createStyle(css, nonce);
            document.head.appendChild(style);
            return style;
        },

        /**
         * فحص CSP violations في console
         */
        checkViolations: function() {
            // مراقبة CSP violations
            document.addEventListener('securitypolicyviolation', function(e) {
                console.group('🚨 CSP Violation Detected');
                console.error('Blocked URI:', e.blockedURI);
                console.error('Violated Directive:', e.violatedDirective);
                console.error('Original Policy:', e.originalPolicy);
                console.error('Source File:', e.sourceFile);
                console.error('Line Number:', e.lineNumber);
                console.groupEnd();
                
                // إرسال تقرير للخادم (اختياري)
                if (window.CSPHelper.reportViolation) {
                    window.CSPHelper.reportViolation(e);
                }
            });
        },

        /**
         * إرسال تقرير CSP violation للخادم
         * @param {SecurityPolicyViolationEvent} violation
         */
        reportViolation: function(violation) {
            fetch('/api/csp-report/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    'csp-report': {
                        'blocked-uri': violation.blockedURI,
                        'violated-directive': violation.violatedDirective,
                        'original-policy': violation.originalPolicy,
                        'source-file': violation.sourceFile,
                        'line-number': violation.lineNumber,
                        'timestamp': new Date().toISOString()
                    }
                })
            }).catch(function(error) {
                console.error('Failed to report CSP violation:', error);
            });
        },

        /**
         * الحصول على CSRF token
         */
        getCSRFToken: function() {
            const token = document.querySelector('meta[name="csrf-token"]');
            return token ? token.getAttribute('content') : '';
        },

        /**
         * فحص ما إذا كان المتصفح يدعم CSP
         */
        isCSPSupported: function() {
            return 'SecurityPolicyViolationEvent' in window;
        },

        /**
         * إضافة nonce لجميع inline scripts الموجودة (للتطوير فقط)
         */
        addNonceToExistingScripts: function() {
            if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
                console.warn('addNonceToExistingScripts should only be used in development');
                return;
            }

            const metaTag = document.querySelector('meta[name="csp-nonce"]');
            const nonce = metaTag ? metaTag.getAttribute('content') : null;
            
            if (!nonce) {
                console.warn('No nonce found in meta tag');
                return;
            }

            const inlineScripts = document.querySelectorAll('script:not([src]):not([nonce])');
            inlineScripts.forEach(function(script) {
                script.setAttribute('nonce', nonce);
            });
        },

        /**
         * معلومات CSP للتطوير
         */
        getCSPInfo: function() {
            const info = {
                supported: this.isCSPSupported(),
                nonce: null,
                violations: []
            };

            // الحصول على nonce
            const metaTag = document.querySelector('meta[name="csp-nonce"]');
            if (metaTag) {
                info.nonce = metaTag.getAttribute('content');
            }

            return info;
        }
    };

    // تهيئة CSP Helper عند تحميل الصفحة
    document.addEventListener('DOMContentLoaded', function() {
        // فحص CSP violations
        CSPHelper.checkViolations();
        
        // إضافة nonce للـ meta tag إذا كان متوفراً في request
        if (window.cspNonce) {
            let metaTag = document.querySelector('meta[name="csp-nonce"]');
            if (!metaTag) {
                metaTag = document.createElement('meta');
                metaTag.setAttribute('name', 'csp-nonce');
                document.head.appendChild(metaTag);
            }
            metaTag.setAttribute('content', window.cspNonce);
        }

        // في وضع التطوير، اعرض معلومات CSP
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        }
    });

})();