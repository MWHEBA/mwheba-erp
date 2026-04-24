/**
 * jQuery Safe Loader
 * محمل آمن لـ jQuery
 */

(function() {
    'use strict';

    // التحقق من تحميل jQuery
    function checkJQuery() {
        return typeof $ !== 'undefined' && typeof jQuery !== 'undefined';
    }

    // قائمة انتظار للوظائف التي تحتاج jQuery
    const jQueryQueue = [];
    let jQueryReady = false;

    // دالة إضافة وظيفة لقائمة انتظار jQuery
    window.onJQueryReady = function(callback) {
        if (jQueryReady && checkJQuery()) {
            callback();
        } else {
            jQueryQueue.push(callback);
        }
    };

    // دالة معالجة قائمة انتظار jQuery
    function processJQueryQueue() {
        if (!checkJQuery()) {
            return;
        }

        jQueryReady = true;
        
        while (jQueryQueue.length > 0) {
            const callback = jQueryQueue.shift();
            try {
                callback();
            } catch (error) {
                console.error('Error in jQuery callback:', error);
            }
        }
    }

    // مراقبة تحميل jQuery
    function waitForJQuery() {
        if (checkJQuery()) {
            processJQueryQueue();
        } else {
            setTimeout(waitForJQuery, 50);
        }
    }

    // بدء المراقبة
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', waitForJQuery);
    } else {
        waitForJQuery();
    }

    // دالة آمنة لاستخدام jQuery
    window.safeJQuery = function(callback) {
        if (checkJQuery()) {
            return callback($);
        } else {
            console.warn('jQuery not available');
            return null;
        }
    };

    // دالة آمنة لتنفيذ كود jQuery
    window.safeJQueryExec = function(code) {
        try {
            if (checkJQuery()) {
                return eval(code);
            } else {
                console.warn('jQuery not available for code execution');
                return null;
            }
        } catch (error) {
            console.error('Error executing jQuery code:', error);
            return null;
        }
    };


})();