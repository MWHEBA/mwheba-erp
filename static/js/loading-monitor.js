/**
 * Loading Monitor
 * مراقب حالة التحميل
 */

(function() {
    'use strict';

    // إعدادات المراقب
    const config = {
        showLoadingStatus: false, // تغيير إلى true لعرض حالة التحميل
        logLibraryStatus: true,
        checkInterval: 1000, // مللي ثانية
        maxCheckTime: 30000 // 30 ثانية
    };

    // حالة المكتبات
    const libraryStatus = {
        jquery: false,
        bootstrap: false,
        select2: false,
        datatables: false,
        sweetalert: false
    };

    // دالة التحقق من حالة المكتبات
    function checkLibraries() {
        const newStatus = {
            jquery: typeof $ !== 'undefined',
            bootstrap: typeof bootstrap !== 'undefined',
            select2: typeof $ !== 'undefined' && $.fn && $.fn.select2,
            datatables: typeof $ !== 'undefined' && $.fn && $.fn.DataTable,
            sweetalert: typeof Swal !== 'undefined'
        };

        // التحقق من التغييرات
        let hasChanges = false;
        for (const [lib, status] of Object.entries(newStatus)) {
            if (libraryStatus[lib] !== status) {
                libraryStatus[lib] = status;
                hasChanges = true;
                
            }
        }

        return {
            status: newStatus,
            hasChanges: hasChanges,
            allLoaded: Object.values(newStatus).every(status => status)
        };
    }

    // دالة عرض حالة التحميل
    function showLoadingStatus() {
        if (!config.showLoadingStatus) return;

        const statusDiv = document.getElementById('loading-status');
        if (!statusDiv) {
            const div = document.createElement('div');
            div.id = 'loading-status';
            div.style.cssText = `
                position: fixed;
                top: 10px;
                right: 10px;
                background: rgba(0,0,0,0.8);
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-family: monospace;
                font-size: 12px;
                z-index: 9999;
                max-width: 300px;
            `;
            document.body.appendChild(div);
        }

        const statusDiv2 = document.getElementById('loading-status');
        let html = '<strong>📊 Library Status:</strong><br>';
        
        for (const [lib, status] of Object.entries(libraryStatus)) {
            const icon = status ? '✅' : '❌';
            html += `${icon} ${lib}<br>`;
        }

        statusDiv2.innerHTML = html;
    }

    // دالة المراقبة الرئيسية
    function startMonitoring() {
        const startTime = Date.now();
        
        function monitor() {
            const result = checkLibraries();
            
            if (config.showLoadingStatus) {
                showLoadingStatus();
            }

            // إذا تم تحميل جميع المكتبات
            if (result.allLoaded) {
                
                // إخفاء مؤشر حالة التحميل
                const statusDiv = document.getElementById('loading-status');
                if (statusDiv) {
                    setTimeout(() => statusDiv.remove(), 2000);
                }
                
                // إطلاق حدث مخصص
                window.dispatchEvent(new CustomEvent('allLibrariesLoaded', {
                    detail: { libraryStatus: libraryStatus }
                }));
                
                return; // إيقاف المراقبة
            }

            // التحقق من انتهاء الوقت المحدد
            if (Date.now() - startTime > config.maxCheckTime) {
                console.warn('⚠️ Library loading timeout reached');
                
                // عرض المكتبات غير المحملة
                const notLoaded = Object.entries(libraryStatus)
                    .filter(([lib, status]) => !status)
                    .map(([lib]) => lib);
                
                if (notLoaded.length > 0) {
                    console.warn('❌ Libraries not loaded:', notLoaded);
                }
                
                return; // إيقاف المراقبة
            }

            // متابعة المراقبة
            setTimeout(monitor, config.checkInterval);
        }

        monitor();
    }

    // دوال مساعدة للمطورين
    window.LoadingMonitor = {
        // الحصول على حالة المكتبات
        getStatus: function() {
            return { ...libraryStatus };
        },
        
        // التحقق من مكتبة معينة
        isLoaded: function(libraryName) {
            return libraryStatus[libraryName] || false;
        },
        
        // انتظار تحميل مكتبة معينة
        waitFor: function(libraryName, callback, timeout = 10000) {
            const startTime = Date.now();
            
            function check() {
                if (libraryStatus[libraryName]) {
                    callback();
                } else if (Date.now() - startTime > timeout) {
                    console.warn(`Timeout waiting for ${libraryName}`);
                } else {
                    setTimeout(check, 100);
                }
            }
            
            check();
        },
        
        // انتظار تحميل جميع المكتبات
        waitForAll: function(callback, timeout = 30000) {
            const startTime = Date.now();
            
            function check() {
                const allLoaded = Object.values(libraryStatus).every(status => status);
                
                if (allLoaded) {
                    callback();
                } else if (Date.now() - startTime > timeout) {
                    console.warn('Timeout waiting for all libraries');
                } else {
                    setTimeout(check, 100);
                }
            }
            
            check();
        },
        
        // تشغيل/إيقاف عرض حالة التحميل
        showStatus: function(show) {
            config.showLoadingStatus = show;
            if (!show) {
                const statusDiv = document.getElementById('loading-status');
                if (statusDiv) statusDiv.remove();
            }
        }
    };

    // بدء المراقبة عند تحميل الصفحة
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startMonitoring);
    } else {
        startMonitoring();
    }


})();