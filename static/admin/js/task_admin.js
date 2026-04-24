/**
 * Task Administration JavaScript
 * JavaScript لإدارة المهام غير المتزامنة
 */

(function($) {
    'use strict';
    
    // تحديث الإحصائيات تلقائياً
    let statisticsUpdateInterval;
    let activeTasksUpdateInterval;
    
    $(document).ready(function() {
        initializeTaskDashboard();
        initializeTaskActions();
        initializeAutoRefresh();
    });
    
    function initializeTaskDashboard() {
        // تهيئة لوحة تحكم المهام
        if ($('#task-dashboard').length) {
            loadTaskStatistics();
            loadActiveTasksCount();
            loadHealthStatus();
        }
    }
    
    function initializeTaskActions() {
        // أزرار إلغاء المهام
        $(document).on('click', '.revoke-task-btn', function(e) {
            e.preventDefault();
            const taskId = $(this).data('task-id');
            const terminate = $(this).data('terminate') || false;
            
            if (confirm('هل أنت متأكد من إلغاء هذه المهمة؟')) {
                revokeTask(taskId, terminate);
            }
        });
        
        // أزرار إعادة تشغيل المهام
        $(document).on('click', '.retry-task-btn', function(e) {
            e.preventDefault();
            const taskId = $(this).data('task-id');
            
            if (confirm('هل تريد إعادة تشغيل هذه المهمة؟')) {
                retryTask(taskId);
            }
        });
        
        // أزرار تنظيف الطوابير
        $(document).on('click', '.purge-queue-btn', function(e) {
            e.preventDefault();
            const queueName = $(this).data('queue-name');
            
            if (confirm(`هل أنت متأكد من تنظيف طابور "${queueName}"؟ سيتم حذف جميع المهام المنتظرة.`)) {
                purgeQueue(queueName);
            }
        });
        
        // تحديث يدوي للإحصائيات
        $(document).on('click', '#refresh-stats-btn', function(e) {
            e.preventDefault();
            loadTaskStatistics();
            showNotification('تم تحديث الإحصائيات', 'success');
        });
        
        // تبديل التحديث التلقائي
        $(document).on('change', '#auto-refresh-toggle', function() {
            if ($(this).is(':checked')) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
    }
    
    function initializeAutoRefresh() {
        // بدء التحديث التلقائي إذا كان مفعلاً
        if ($('#auto-refresh-toggle').is(':checked')) {
            startAutoRefresh();
        }
    }
    
    function startAutoRefresh() {
        // تحديث الإحصائيات كل 30 ثانية
        statisticsUpdateInterval = setInterval(function() {
            loadTaskStatistics();
        }, 30000);
        
        // تحديث المهام النشطة كل 10 ثواني
        activeTasksUpdateInterval = setInterval(function() {
            loadActiveTasksCount();
        }, 10000);
        
        showNotification('تم تفعيل التحديث التلقائي', 'info');
    }
    
    function stopAutoRefresh() {
        if (statisticsUpdateInterval) {
            clearInterval(statisticsUpdateInterval);
        }
        if (activeTasksUpdateInterval) {
            clearInterval(activeTasksUpdateInterval);
        }
        
        showNotification('تم إيقاف التحديث التلقائي', 'info');
    }
    
    function loadTaskStatistics() {
        $.ajax({
            url: '/admin/tasks/statistics/',
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            success: function(data) {
                updateStatisticsDisplay(data);
            },
            error: function(xhr, status, error) {
                console.error('خطأ في تحميل الإحصائيات:', error);
                showNotification('خطأ في تحميل الإحصائيات', 'error');
            }
        });
    }
    
    function loadActiveTasksCount() {
        $.ajax({
            url: '/admin/tasks/active/',
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            success: function(data) {
                updateActiveTasksCount(data.tasks.length);
            },
            error: function(xhr, status, error) {
                console.error('خطأ في تحميل المهام النشطة:', error);
            }
        });
    }
    
    function loadHealthStatus() {
        $.ajax({
            url: '/admin/tasks/health/',
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            success: function(data) {
                updateHealthStatusDisplay(data);
            },
            error: function(xhr, status, error) {
                console.error('خطأ في تحميل حالة الصحة:', error);
            }
        });
    }
    
    function updateStatisticsDisplay(data) {
        // تحديث عدد العمال
        $('#workers-count').text(data.workers.total);
        $('#active-workers-count').text(data.workers.active);
        
        // تحديث إحصائيات المهام
        $('#active-tasks-count').text(data.tasks.active);
        $('#processed-tasks-count').text(data.tasks.processed_total);
        $('#failed-tasks-count').text(data.tasks.failed_recent);
        
        // تحديث الطوابير
        updateQueuesDisplay(data.queues);
        
        // تحديث وقت آخر تحديث
        $('#last-updated').text(new Date(data.last_updated).toLocaleString('ar-EG'));
    }
    
    function updateActiveTasksCount(count) {
        $('#active-tasks-count').text(count);
        
        // تحديث شارة الإشعار إذا كانت موجودة
        const badge = $('.active-tasks-badge');
        if (badge.length) {
            badge.text(count);
            if (count > 0) {
                badge.removeClass('badge-secondary').addClass('badge-primary');
            } else {
                badge.removeClass('badge-primary').addClass('badge-secondary');
            }
        }
    }
    
    function updateQueuesDisplay(queues) {
        const queuesList = $('#queues-list');
        if (queuesList.length) {
            queuesList.empty();
            
            Object.keys(queues).forEach(function(queueName) {
                const queue = queues[queueName];
                const queueItem = $(`
                    <div class="queue-item">
                        <strong>${queueName}</strong>
                        <span class="queue-workers">${queue.workers} عامل</span>
                        <button class="btn btn-sm btn-warning purge-queue-btn" 
                                data-queue-name="${queueName}">
                            تنظيف
                        </button>
                    </div>
                `);
                queuesList.append(queueItem);
            });
        }
    }
    
    function updateHealthStatusDisplay(healthData) {
        const statusIndicator = $('#health-status-indicator');
        const statusText = $('#health-status-text');
        
        if (statusIndicator.length && statusText.length) {
            // إزالة الفئات السابقة
            statusIndicator.removeClass('status-healthy status-warning status-unhealthy');
            
            // إضافة الفئة الجديدة
            statusIndicator.addClass(`status-${healthData.overall_status}`);
            
            // تحديث النص
            const statusTexts = {
                'healthy': 'سليم',
                'warning': 'تحذير',
                'unhealthy': 'غير سليم'
            };
            statusText.text(statusTexts[healthData.overall_status] || 'غير معروف');
        }
        
        // تحديث تفاصيل الفحوصات
        updateHealthChecksDisplay(healthData.checks);
    }
    
    function updateHealthChecksDisplay(checks) {
        const checksList = $('#health-checks-list');
        if (checksList.length) {
            checksList.empty();
            
            Object.keys(checks).forEach(function(checkName) {
                const check = checks[checkName];
                const statusClass = `status-${check.status}`;
                const statusIcon = getStatusIcon(check.status);
                
                const checkItem = $(`
                    <div class="health-check-item ${statusClass}">
                        <span class="check-icon">${statusIcon}</span>
                        <span class="check-name">${getCheckDisplayName(checkName)}</span>
                        <span class="check-message">${check.message}</span>
                    </div>
                `);
                checksList.append(checkItem);
            });
        }
    }
    
    function getStatusIcon(status) {
        const icons = {
            'healthy': '✅',
            'warning': '⚠️',
            'unhealthy': '❌'
        };
        return icons[status] || '❓';
    }
    
    function getCheckDisplayName(checkName) {
        const displayNames = {
            'celery_connection': 'اتصال Celery',
            'queue_health': 'صحة الطوابير',
            'failure_rate': 'معدل الفشل'
        };
        return displayNames[checkName] || checkName;
    }
    
    function revokeTask(taskId, terminate) {
        $.ajax({
            url: `/admin/tasks/revoke/${taskId}/`,
            method: 'POST',
            data: {
                'terminate': terminate,
                'csrfmiddlewaretoken': $('[name=csrfmiddlewaretoken]').val()
            },
            headers: {
                'Accept': 'application/json'
            },
            success: function(data) {
                if (data.success) {
                    showNotification(data.message, 'success');
                    // إعادة تحميل الصفحة أو تحديث القائمة
                    setTimeout(function() {
                        location.reload();
                    }, 1000);
                } else {
                    showNotification(data.message, 'error');
                }
            },
            error: function(xhr, status, error) {
                showNotification('خطأ في إلغاء المهمة', 'error');
            }
        });
    }
    
    function retryTask(taskId) {
        $.ajax({
            url: `/admin/tasks/retry/${taskId}/`,
            method: 'POST',
            data: {
                'csrfmiddlewaretoken': $('[name=csrfmiddlewaretoken]').val()
            },
            headers: {
                'Accept': 'application/json'
            },
            success: function(data) {
                if (data.success) {
                    showNotification(data.message, 'success');
                    setTimeout(function() {
                        location.reload();
                    }, 1000);
                } else {
                    showNotification(data.message, 'error');
                }
            },
            error: function(xhr, status, error) {
                showNotification('خطأ في إعادة تشغيل المهمة', 'error');
            }
        });
    }
    
    function purgeQueue(queueName) {
        $.ajax({
            url: `/admin/tasks/purge/${queueName}/`,
            method: 'POST',
            data: {
                'csrfmiddlewaretoken': $('[name=csrfmiddlewaretoken]').val()
            },
            headers: {
                'Accept': 'application/json'
            },
            success: function(data) {
                if (data.success) {
                    showNotification(data.message, 'success');
                    loadTaskStatistics(); // تحديث الإحصائيات
                } else {
                    showNotification(data.message, 'error');
                }
            },
            error: function(xhr, status, error) {
                showNotification('خطأ في تنظيف الطابور', 'error');
            }
        });
    }
    
    function showNotification(message, type = 'info') {
    if (typeof toastr !== 'undefined') {
        if (type === 'success') toastr.success(message);
        else if (type === 'error' || type === 'danger') toastr.error(message);
        else if (type === 'warning') toastr.warning(message);
        else toastr.info(message);
    }
} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                </button>
            </div>
        `);
        
        // إضافة الإشعار للصفحة
        let container = $('#notifications-container');
        if (!container.length) {
            container = $('<div id="notifications-container" style="position: fixed; top: 20px; right: 20px; z-index: 9999; max-width: 400px;"></div>');
            $('body').append(container);
        }
        
        container.append(notification);
        
        // إزالة الإشعار تلقائياً بعد 5 ثواني
        setTimeout(function() {
            notification.fadeOut(function() {
                $(this).remove();
            });
        }, 5000);
    }
    
    // دالة لعرض تفاصيل سجل التدقيق
    window.showDetails = function(logId) {
        // يمكن تطوير هذه الدالة لعرض تفاصيل أكثر في نافذة منبثقة
        alert('عرض تفاصيل السجل رقم: ' + logId);
    };
    
    // تنظيف الموارد عند مغادرة الصفحة
    $(window).on('beforeunload', function() {
        stopAutoRefresh();
    });
    
})(django.jQuery || jQuery);