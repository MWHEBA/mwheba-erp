/**
 * نظام إعدادات الإشعارات - MWHEBA ERP
 * يوفر وظائف تفاعلية لصفحة إعدادات الإشعارات
 */

(function() {
    'use strict';

    // ==================== دوال مساعدة ====================

    /**
     * إظهار/إخفاء حقل بناءً على حالة checkbox
     */
    function toggleField(checkboxId, fieldClass) {
        const checkbox = document.getElementById(checkboxId);
        const field = document.querySelector(`.${fieldClass}`);
        
        if (!checkbox || !field) return;
        
        checkbox.addEventListener('change', function() {
            if (this.checked) {
                field.style.display = 'block';
                field.style.animation = 'slideDown 0.3s ease';
            } else {
                field.style.display = 'none';
            }
        });
    }

    /**
     * التحقق من صحة النموذج قبل الإرسال
     */
    function validateForm() {
        const form = document.getElementById('notification-settings-form');
        if (!form) return true;
        
        // التحقق من تفعيل طريقة إشعار واحدة على الأقل
        const notifyInApp = document.getElementById('id_notify_in_app');
        const notifyEmail = document.getElementById('id_notify_email');
        const notifySms = document.getElementById('id_notify_sms');
        
        if (!notifyInApp.checked && !notifyEmail.checked && !notifySms.checked) {
            alert('يجب تفعيل طريقة إشعار واحدة على الأقل');
            return false;
        }
        
        // التحقق من البريد الإلكتروني إذا تم تفعيله
        if (notifyEmail.checked) {
            const emailField = document.getElementById('id_email_for_notifications');
            if (!emailField.value.trim()) {
                alert('يجب إدخال البريد الإلكتروني لتفعيل إشعارات البريد');
                emailField.focus();
                return false;
            }
        }
        
        // التحقق من رقم الهاتف إذا تم تفعيله
        if (notifySms.checked) {
            const phoneField = document.getElementById('id_phone_for_notifications');
            if (!phoneField.value.trim()) {
                alert('يجب إدخال رقم الهاتف لتفعيل إشعارات SMS');
                phoneField.focus();
                return false;
            }
        }
        
        // التحقق من أوقات عدم الإزعاج
        const enableDnd = document.getElementById('id_enable_do_not_disturb');
        if (enableDnd.checked) {
            const dndStart = document.getElementById('id_do_not_disturb_start');
            const dndEnd = document.getElementById('id_do_not_disturb_end');
            
            if (!dndStart.value || !dndEnd.value) {
                alert('يجب تحديد أوقات بداية ونهاية عدم الإزعاج');
                return false;
            }
        }
        
        return true;
    }

    /**
     * إضافة حالة loading للزر عند الإرسال
     */
    function handleFormSubmit() {
        const form = document.getElementById('notification-settings-form');
        if (!form) return;
        
        form.addEventListener('submit', function(e) {
            if (!validateForm()) {
                e.preventDefault();
                return false;
            }
            
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.classList.add('loading');
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> جاري الحفظ...';
            }
        });
    }

    /**
     * تهيئة tooltips
     */
    function initializeTooltips() {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }

    /**
     * إضافة تأثيرات على البطاقات
     */
    function initializeCardEffects() {
        const cards = document.querySelectorAll('.card');
        
        cards.forEach(card => {
            card.addEventListener('mouseenter', function() {
                this.style.transform = 'translateY(-2px)';
            });
            
            card.addEventListener('mouseleave', function() {
                this.style.transform = 'translateY(0)';
            });
        });
    }

    /**
     * تهيئة عدادات الإحصائيات بتأثير متحرك
     */
    function animateStats() {
        const statNumbers = document.querySelectorAll('.stat-item strong');
        
        statNumbers.forEach(stat => {
            const finalValue = parseInt(stat.textContent);
            if (isNaN(finalValue)) return;
            
            let currentValue = 0;
            const increment = finalValue / 30;
            const duration = 1000;
            const stepTime = duration / 30;
            
            const counter = setInterval(() => {
                currentValue += increment;
                if (currentValue >= finalValue) {
                    stat.textContent = finalValue;
                    clearInterval(counter);
                } else {
                    stat.textContent = Math.floor(currentValue);
                }
            }, stepTime);
        });
    }

    /**
     * تهيئة progress bars بتأثير متحرك
     */
    function animateProgressBars() {
        const progressBars = document.querySelectorAll('.progress-bar');
        
        progressBars.forEach(bar => {
            const width = bar.style.width;
            bar.style.width = '0%';
            
            setTimeout(() => {
                bar.style.width = width;
            }, 100);
        });
    }

    /**
     * حفظ الإعدادات تلقائياً (اختياري)
     */
    function enableAutoSave() {
        const form = document.getElementById('notification-settings-form');
        if (!form) return;
        
        const inputs = form.querySelectorAll('input, select');
        let saveTimeout;
        
        inputs.forEach(input => {
            input.addEventListener('change', function() {
                clearTimeout(saveTimeout);
                
                // عرض مؤشر الحفظ التلقائي
                const indicator = document.createElement('div');
                indicator.className = 'auto-save-indicator';
                indicator.innerHTML = '<i class="fas fa-check-circle text-success"></i> تم الحفظ تلقائياً';
                indicator.style.cssText = 'position: fixed; top: 20px; left: 20px; background: white; padding: 10px 20px; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); z-index: 9999;';
                
                // إضافة المؤشر وإزالته بعد 2 ثانية
                // ملاحظة: الحفظ التلقائي معطل افتراضياً، يمكن تفعيله لاحقاً
                // document.body.appendChild(indicator);
                // setTimeout(() => indicator.remove(), 2000);
            });
        });
    }

    /**
     * تأكيد قبل مغادرة الصفحة مع تغييرات غير محفوظة
     */
    function confirmUnsavedChanges() {
        const form = document.getElementById('notification-settings-form');
        if (!form) return;
        
        let formChanged = false;
        const inputs = form.querySelectorAll('input, select');
        
        inputs.forEach(input => {
            input.addEventListener('change', function() {
                formChanged = true;
            });
        });
        
        form.addEventListener('submit', function() {
            formChanged = false;
        });
        
        window.addEventListener('beforeunload', function(e) {
            if (formChanged) {
                e.preventDefault();
                e.returnValue = 'لديك تغييرات غير محفوظة. هل تريد المغادرة؟';
                return e.returnValue;
            }
        });
    }

    // ==================== التهيئة ====================

    /**
     * تهيئة جميع الوظائف
     */
    function initialize() {
        // تهيئة إظهار/إخفاء الحقول المشروطة
        toggleField('id_notify_email', 'email-field');
        toggleField('id_notify_sms', 'sms-field');
        toggleField('id_send_daily_summary', 'daily-summary-field');
        toggleField('id_enable_do_not_disturb', 'dnd-fields');
        toggleField('id_auto_delete_read_notifications', 'auto-delete-field');
        toggleField('id_auto_archive_old_notifications', 'auto-archive-field');
        
        // تهيئة معالج إرسال النموذج
        handleFormSubmit();
        
        // تهيئة tooltips
        if (typeof bootstrap !== 'undefined') {
            initializeTooltips();
        }
        
        // تهيئة تأثيرات البطاقات
        initializeCardEffects();
        
        // تحريك الإحصائيات
        animateStats();
        animateProgressBars();
        
        // تفعيل تأكيد التغييرات غير المحفوظة
        confirmUnsavedChanges();
        
        console.log('✅ تم تهيئة صفحة إعدادات الإشعارات بنجاح');
    }

    // تهيئة عند تحميل DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        initialize();
    }

})();
