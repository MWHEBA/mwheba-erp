/**
 * نظام إدارة الإشعارات - Corporate ERP
 * يوفر وظائف تفاعلية للإشعارات في الهيدر والصفحات
 */

(function() {
    'use strict';

    // ==================== المتغيرات العامة ====================
    const NOTIFICATION_CHECK_INTERVAL = 120000; // فحص كل دقيقتين (تقليل الضغط على السيرفر)
    let notificationCheckTimer = null;
    let lastFetchTime = 0;
    const MIN_FETCH_INTERVAL = 30000; // الحد الأدنى بين الطلبات: 30 ثانية
    let consecutiveErrors = 0;        // عداد الأخطاء المتتالية
    const MAX_CONSECUTIVE_ERRORS = 3; // إيقاف الـ polling بعد 3 أخطاء متتالية

    // ==================== دوال مساعدة ====================

    /**
     * الحصول على CSRF Token
     */
    function getCSRFToken() {
        // محاولة الحصول على CSRF token من meta tag أولاً
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        if (csrfMeta) {
            return csrfMeta.getAttribute('content');
        }
        
        // محاولة الحصول عليه من input مخفي
        const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrfInput) {
            return csrfInput.value;
        }
        
        // محاولة الحصول عليه من cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        
        // تسجيل صامت - لا نريد إزعاج console
        return '';
    }

    /**
     * عرض رسالة Toast
     */
    function showToast(message, type = 'info') {
        if (typeof toastr !== 'undefined') {
            toastr[type](message);
        } else {
        }
    }

    /**
     * تحديث عداد الإشعارات
     */
    function updateNotificationBadge(count) {
        const badge = document.querySelector('.notification-badge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count > 99 ? '99+' : count;
                badge.classList.remove('d-none');
            } else {
                badge.classList.add('d-none');
            }
        }

        // تحديث عنوان الصفحة
        const baseTitle = document.title.replace(/^\(\d+\)\s*/, '');
        document.title = count > 0 ? `(${count}) ${baseTitle}` : baseTitle;
    }

    /**
     * تحديث قائمة الإشعارات في الهيدر
     */
    function updateNotificationsList(notifications) {
        const notificationList = document.querySelector('.notification-list');
        if (!notificationList) return;

        if (!notifications || notifications.length === 0) {
            notificationList.innerHTML = `
                <div class="dropdown-item text-center py-5">
                    <div class="empty-notifications">
                        <i class="far fa-bell-slash fa-3x text-muted mb-3"></i>
                        <p class="text-muted mb-0">لا توجد إشعارات جديدة</p>
                    </div>
                </div>
            `;
            return;
        }

        // تقسيم الإشعارات لمقروءة وغير مقروءة
        const unreadNotifications = notifications.filter(n => !n.read);
        const readNotifications = notifications.filter(n => n.read);

        let html = '';

        // الإشعارات غير المقروءة
        if (unreadNotifications.length > 0) {
            html += `
                <div class="notification-category">
                    <div class="notification-category-title">
                        <span>جديدة</span>
                    </div>
            `;

            unreadNotifications.forEach(notification => {
                html += createNotificationItem(notification, true);
            });

            html += '</div>';
        }

        // الإشعارات المقروءة
        if (readNotifications.length > 0) {
            html += `
                <div class="notification-category">
                    <div class="notification-category-title">
                        <span>سابقة</span>
                    </div>
            `;

            readNotifications.forEach(notification => {
                html += createNotificationItem(notification, false);
            });

            html += '</div>';
        }

        notificationList.innerHTML = html;
    }

    /**
     * إنشاء عنصر إشعار HTML
     */
    function createNotificationItem(notification, isUnread) {
        const iconClass = getNotificationIcon(notification.notification_type);
        const bgClass = isUnread ? `bg-${notification.notification_type}` : 'bg-light text-' + notification.notification_type;
        const unreadClass = isUnread ? 'unread' : '';
        
        return `
            <a href="${notification.link || '#'}" class="notification-item ${unreadClass}" data-id="${notification.id}">
                <div class="notification-icon ${bgClass}">
                    <i class="fas ${iconClass}"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">${notification.title}</div>
                    <div class="notification-text">${notification.message}</div>
                    <div class="notification-time">
                        <i class="far fa-clock me-1"></i>
                        ${formatTimeAgo(notification.created_at)}
                    </div>
                </div>
                ${isUnread ? `
                    <button type="button" class="btn-mark-read" data-id="${notification.id}">
                        <i class="fas fa-check"></i>
                    </button>
                ` : ''}
            </a>
        `;
    }

    /**
     * الحصول على أيقونة الإشعار حسب النوع
     * ✅ مصدر موحد - متزامن مع core/notification_icons.py
     */
    function getNotificationIcon(type) {
        const icons = {
            // أنواع عامة
            'info': 'fa-info',
            'success': 'fa-check',
            'warning': 'fa-exclamation-triangle',
            'danger': 'fa-times',
            
            // المخزون والمنتجات
            'inventory_alert': 'fa-box',
            'product_expiry': 'fa-calendar-times',
            'stock_transfer': 'fa-exchange-alt',
            
            // المبيعات
            'new_sale': 'fa-shopping-cart',
            'sale_payment': 'fa-money-bill-wave',
            'sale_return': 'fa-undo-alt',
            
            // المشتريات
            'new_purchase': 'fa-shopping-bag',
            'purchase_payment': 'fa-hand-holding-usd',
            'purchase_return': 'fa-reply',
            
            // المالية
            'payment_received': 'fa-money-bill-wave',  // دفعة مستلمة
            'payment_made': 'fa-credit-card',  // دفعة مسددة ✅
            'new_invoice': 'fa-file-invoice',  // فاتورة جديدة ✅
            
            // الموارد البشرية
            'hr_leave_request': 'fa-calendar-check',
            'hr_attendance': 'fa-user-clock',
            'hr_payroll': 'fa-wallet',
            'hr_contract': 'fa-file-contract',  // عقد موظف (عام)
            
            // إشعارات العقود (محددة)
            'contract_created': 'fa-file-contract',  // عقد جديد ✅
            'contract_activated': 'fa-check-circle',  // تفعيل عقد ✅
            'contract_terminated': 'fa-ban',  // إنهاء عقد ✅
            'probation_ending': 'fa-clock',  // انتهاء فترة تجربة ✅
            'contract_expiring_soon': 'fa-calendar-exclamation',  // عقد سينتهي قريباً ✅
            'contract_expiring_urgent': 'fa-exclamation-triangle',  // عقد سينتهي عاجل ✅
            
            // أخرى
            'return_request': 'fa-undo',
            'system_alert': 'fa-exclamation-circle'
        };
        return icons[type] || 'fa-bell';
    }

    /**
     * تنسيق الوقت (منذ كم)
     */
    function formatTimeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);

        if (seconds < 60) return 'الآن';
        if (seconds < 3600) return `منذ ${Math.floor(seconds / 60)} دقيقة`;
        if (seconds < 86400) return `منذ ${Math.floor(seconds / 3600)} ساعة`;
        if (seconds < 604800) return `منذ ${Math.floor(seconds / 86400)} يوم`;
        return date.toLocaleDateString('en-GB');
    }

    // ==================== دوال API ====================

    /**
     * جلب عدد الإشعارات غير المقروءة
     */
    async function fetchNotificationsCount() {
        // التحقق من حالة الاتصال
        if (navigator.onLine === false) {
            return;
        }

        // منع الطلبات المتكررة (throttling)
        const now = Date.now();
        if (now - lastFetchTime < MIN_FETCH_INTERVAL) {
            return;
        }
        lastFetchTime = now;

        try {
            const response = await fetch('/api/notifications/count/', {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json'
                }
            });
            
            // معالجة أخطاء rate limiting
            if (response.status === 429) {
                updateNotificationBadge(0);
                return;
            }
            
            // معالجة أخطاء الخادم - إيقاف الـ polling بعد أخطاء متكررة
            if (response.status === 500) {
                consecutiveErrors++;
                if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                    stopNotificationPolling();
                }
                updateNotificationBadge(0);
                return;
            }
            
            // Session انتهت - إيقاف الـ polling نهائياً
            if (response.status === 401 || response.status === 302) {
                stopNotificationPolling();
                updateNotificationBadge(0);
                return;
            }
            
            if (response.status === 404) {
                stopNotificationPolling(); // الـ endpoint مش موجود - لا فائدة من الاستمرار
                updateNotificationBadge(0);
                return;
            }
            
            if (response.status === 403) {
                updateNotificationBadge(0);
                return;
            }
            
            if (!response.ok) {
                consecutiveErrors++;
                updateNotificationBadge(0);
                return;
            }
            
            // طلب ناجح - إعادة تعيين عداد الأخطاء
            consecutiveErrors = 0;
            
            const data = await response.json();
            
            if (data.success) {
                updateNotificationBadge(data.count);
            } else {
                // إذا كان المستخدم غير مسجل دخول، لا نعرض خطأ
                if (data.message && !data.message.includes('تسجيل الدخول')) {
                    console.warn('تحذير الإشعارات:', data.message);
                }
                updateNotificationBadge(0);
            }
        } catch (error) {
            // تسجيل صامت للأخطاء - لا نريد إزعاج المستخدم أو console
            // معالجة صامتة لجميع أنواع الأخطاء
            updateNotificationBadge(0);
        }
    }

    /**
     * تعليم إشعار كمقروء
     */
    async function markNotificationAsRead(notificationId) {
        try {
            const response = await fetch(`/api/notifications/mark-read/${notificationId}/`, {
                method: 'POST',
                credentials: 'same-origin', // تضمين cookies للمصادقة
                headers: {
                    'X-CSRFToken': getCSRFToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                // تحديث العداد
                fetchNotificationsCount();
                
                // إزالة فئة unread من العنصر
                const notificationItem = document.querySelector(`.notification-item[data-id="${notificationId}"]`);
                if (notificationItem) {
                    notificationItem.classList.remove('unread');
                    const markReadBtn = notificationItem.querySelector('.btn-mark-read');
                    if (markReadBtn) {
                        markReadBtn.remove();
                    }
                }

                return true;
            } else {
                showToast(data.message || 'فشل تعليم الإشعار كمقروء', 'error');
                return false;
            }
        } catch (error) {
            console.error('خطأ في تعليم الإشعار:', error);
            showToast('حدث خطأ أثناء تعليم الإشعار', 'error');
            return false;
        }
    }

    /**
     * تعليم جميع الإشعارات كمقروءة
     */
    async function markAllNotificationsAsRead() {
        try {
            const response = await fetch('/api/notifications/mark-all-read/', {
                method: 'POST',
                credentials: 'same-origin', // تضمين cookies للمصادقة
                headers: {
                    'X-CSRFToken': getCSRFToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                showToast('تم تعليم جميع الإشعارات كمقروءة', 'success');
                
                // تحديث العداد
                updateNotificationBadge(0);
                
                // إزالة فئة unread من جميع العناصر
                document.querySelectorAll('.notification-item.unread').forEach(item => {
                    item.classList.remove('unread');
                    const markReadBtn = item.querySelector('.btn-mark-read');
                    if (markReadBtn) {
                        markReadBtn.remove();
                    }
                });

                // إخفاء زر "تعليم الكل كمقروء"
                const markAllBtn = document.querySelector('.mark-all-read');
                if (markAllBtn) {
                    markAllBtn.style.display = 'none';
                }

                return true;
            } else {
                showToast(data.message || 'فشل تعليم الإشعارات', 'error');
                return false;
            }
        } catch (error) {
            console.error('خطأ في تعليم جميع الإشعارات:', error);
            showToast('حدث خطأ أثناء تعليم الإشعارات', 'error');
            return false;
        }
    }

    // ==================== معالجات الأحداث ====================

    /**
     * تهيئة معالجات الأحداث
     */
    function initializeEventHandlers() {
        // معالج النقر على الإشعار نفسه
        document.addEventListener('click', function(e) {
            const notificationItem = e.target.closest('.notification-item');
            if (notificationItem && notificationItem.classList.contains('unread')) {
                const notificationId = notificationItem.getAttribute('data-id');
                const notificationUrl = notificationItem.getAttribute('href');
                
                if (notificationId) {
                    e.preventDefault();
                    
                    // تعليم الإشعار كمقروء
                    markNotificationAsRead(notificationId).then(success => {
                        if (success) {
                            // إخفاء الإشعار من القائمة
                            notificationItem.style.opacity = '0';
                            notificationItem.style.transform = 'translateX(20px)';
                            
                            setTimeout(() => {
                                notificationItem.remove();
                                
                                // التحقق من وجود إشعارات متبقية
                                const remainingNotifications = document.querySelectorAll('.notification-item');
                                if (remainingNotifications.length === 0) {
                                    const notificationList = document.querySelector('.notification-list');
                                    if (notificationList) {
                                        notificationList.innerHTML = `
                                            <div class="dropdown-item text-center py-5">
                                                <div class="empty-notifications">
                                                    <i class="far fa-bell-slash fa-3x text-muted mb-3"></i>
                                                    <p class="text-muted mb-0">لا توجد إشعارات جديدة</p>
                                                </div>
                                            </div>
                                        `;
                                    }
                                }
                                
                                // الانتقال للرابط إذا كان موجود
                                if (notificationUrl && notificationUrl !== '#') {
                                    window.location.href = notificationUrl;
                                }
                            }, 300);
                        }
                    });
                }
            }
        });
        
        // معالج زر تعليم إشعار واحد كمقروء
        document.addEventListener('click', function(e) {
            const markReadBtn = e.target.closest('.btn-mark-read');
            if (markReadBtn) {
                e.preventDefault();
                e.stopPropagation();
                
                const notificationId = markReadBtn.getAttribute('data-id');
                if (notificationId) {
                    markNotificationAsRead(notificationId);
                }
            }
        });

        // معالج زر تعليم جميع الإشعارات كمقروءة
        const markAllBtn = document.querySelector('.mark-all-read');
        if (markAllBtn) {
            markAllBtn.addEventListener('click', function(e) {
                e.preventDefault();
                markAllNotificationsAsRead();
            });
        }

        // معالج نموذج تعليم الكل كمقروء (في صفحة الإشعارات)
        const markAllForm = document.getElementById('mark_all_read_form');
        if (markAllForm) {
            markAllForm.addEventListener('submit', function(e) {
                e.preventDefault();
                markAllNotificationsAsRead().then(success => {
                    if (success) {
                        // إعادة تحميل الصفحة بعد ثانية
                        setTimeout(() => {
                            window.location.reload();
                        }, 1000);
                    }
                });
            });
        }
    }

    /**
     * بدء فحص الإشعارات الدوري
     */
    function startNotificationPolling() {
        // التحقق من وجود المستخدم مسجل دخول
        const userElement = document.querySelector('[data-user-authenticated]');
        const isAuthenticated = userElement && userElement.dataset.userAuthenticated === 'true';
        
        if (!isAuthenticated) {
            return;
        }

        // فحص فوري عند التحميل (بعد 2 ثانية)
        setTimeout(fetchNotificationsCount, 2000);

        // فحص دوري كل دقيقتين
        notificationCheckTimer = setInterval(() => {
            if (navigator.onLine !== false) {
                fetchNotificationsCount();
            }
        }, NOTIFICATION_CHECK_INTERVAL);
    }

    /**
     * إيقاف فحص الإشعارات الدوري
     */
    function stopNotificationPolling() {
        if (notificationCheckTimer) {
            clearInterval(notificationCheckTimer);
            notificationCheckTimer = null;
        }
    }

    // ==================== التهيئة ====================

    /**
     * تهيئة نظام الإشعارات
     */
    function initialize() {
        // تهيئة معالجات الأحداث
        initializeEventHandlers();

        // بدء الفحص الدوري
        startNotificationPolling();

        // إيقاف الفحص عند إغلاق الصفحة
        window.addEventListener('beforeunload', stopNotificationPolling);

        // معالجة تغيير حالة الاتصال
        window.addEventListener('online', function() {
            console.info('تم استعادة الاتصال بالإنترنت، استئناف فحص الإشعارات');
            // فحص فوري عند استعادة الاتصال
            setTimeout(fetchNotificationsCount, 1000);
        });

        window.addEventListener('offline', function() {
            console.warn('انقطع الاتصال بالإنترنت، تم إيقاف فحص الإشعارات مؤقتاً');
        });
    }

    // تهيئة عند تحميل DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        initialize();
    }

    // تصدير الدوال للاستخدام الخارجي
    window.NotificationSystem = {
        markAsRead: markNotificationAsRead,
        markAllAsRead: markAllNotificationsAsRead,
        fetchCount: fetchNotificationsCount,
        startPolling: startNotificationPolling,
        stopPolling: stopNotificationPolling
    };

})();
