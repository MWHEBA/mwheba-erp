/**
 * Main JavaScript File for MWHEBA ERP System
 * 
 * Contains all custom scripts for the ERP system
 * 
 * @author MWHEBA ERP Team
 * @version 1.0.0
 */

$(document).ready(function() {
    // تهيئة السلايد بار
    initSidebar();
    
    // تهيئة التوسترات
    initTooltips();
    
    // تهيئة حوارات تأكيد الحذف
    initDeleteConfirmations();
    
    // تهيئة التحقق من الفورم
    initFormValidations();
    
    // تهيئة الفورم الديناميكية
    initDynamicForms();
    
    // تهيئة التبويبات المحفوظة
    initSavedTabs();
    
    // تهيئة النوافذ المنبثقة
    initModals();
    
    // تهيئة الفلاتر
    initFilters();
    
    // إعادة تعيين القائمة النشطة عند تغيير الصفحة
    window.addEventListener('popstate', function() {
        // تأخير قصير لضمان اكتمال التغييرات في DOM
        setTimeout(highlightActiveMenu, 100);
    });
    
    // للاستجابة للتحديثات عبر AJAX
    document.addEventListener('PageLoadComplete', function() {
        // تحديث القائمة النشطة بعد تحميل المحتوى
        highlightActiveMenu();
    });
    
    // تعليم إشعار واحد كمقروء
    $(document).on('click', '.btn-mark-read', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        const $button = $(this);
        const $notification = $button.closest('.notification-item');
        const notificationId = $button.data('id');
        const url = $button.data('url');
        
        // تنفيذ طلب AJAX لتحديث حالة الإشعار
        $.ajax({
            url: url,
            type: 'POST',
            data: {
                'csrfmiddlewaretoken': $('meta[name="csrf-token"]').attr('content')
            },
            success: function(response) {
                if (response.success) {
                    // إزالة فئة غير مقروء وتحديث العداد
                    $notification.removeClass('unread');
                    $button.fadeOut(200);
                    
                    // تحديث عداد الإشعارات
                    updateNotificationCounter();
                    
                    // إذا كان الرد يحتوي على رابط للتوجيه، انتقل إليه
                    if (response.redirect_url) {
                        window.location.href = response.redirect_url;
                    }
                }
            },
            error: function() {
                // عرض رسالة خطأ
                showNotification('حدث خطأ أثناء تحديث الإشعار', 'error');
            }
        });
    });
    
    // تعليم كل الإشعارات كمقروءة
    $(document).on('click', '.mark-all-read', function(e) {
        e.preventDefault();
        
        const $button = $(this);
        const url = $button.data('url');
        
        // تعطيل الزر أثناء المعالجة
        $button.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i>');
        
        // تنفيذ طلب AJAX لتحديث جميع الإشعارات
        $.ajax({
            url: url,
            type: 'POST',
            data: {
                'csrfmiddlewaretoken': $('meta[name="csrf-token"]').attr('content')
            },
            success: function(response) {
                if (response.success) {
                    // إزالة فئة غير مقروء من كل الإشعارات
                    $('.notification-item.unread').removeClass('unread');
                    $('.btn-mark-read').fadeOut(200);
                    
                    // تحديث العداد
                    $('.badge-counter').addClass('d-none').text('0');
                    
                    // إخفاء الزر
                    $button.closest('.dropdown-header').find('.badge').fadeOut(200);
                    $button.fadeOut(200);
                    
                    // عرض رسالة نجاح
                    showNotification('تم تعليم جميع الإشعارات كمقروءة', 'success');
                }
            },
            error: function() {
                // استعادة الزر وعرض رسالة خطأ
                $button.prop('disabled', false).html('<i class="fas fa-check-double"></i><span class="d-none d-md-inline-block">تعليم الكل كمقروء</span>');
                showNotification('حدث خطأ أثناء تحديث الإشعارات', 'error');
            }
        });
    });
    
    // إيقاف انتشار النقر عند النقر على زر الإشعارات نفسه
    $(document).on('click', '.notification-btn', function(e) {
        // منع الانتقال إلى الرابط عند النقر على الزر
        e.stopPropagation();
    });
    
    // تحديث عدد الإشعارات غير المقروءة
    function updateNotificationCounter() {
        const unreadCount = $('.notification-item.unread').length;
        const $badge = $('.badge-counter');
        
        if (unreadCount > 0) {
            $badge.removeClass('d-none').text(unreadCount);
        } else {
            $badge.addClass('d-none').text('0');
            // إخفاء زر تعليم الكل كمقروء
            $('.mark-all-read').fadeOut(200);
        }
    }
    
    // عرض رسالة نوتيفيكيشن
    function showNotification(message, type = 'info') {
        // التحقق من وجود توست بوتستراب
        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            // إنشاء عنصر التوست ديناميكيًا
            const toastId = 'notification-toast-' + new Date().getTime();
            const toastHtml = `
                <div id="${toastId}" class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
                    <div class="d-flex">
                        <div class="toast-body">
                            ${message}
                        </div>
                        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="إغلاق"></button>
                    </div>
                </div>
            `;
            
            // إضافة التوست إلى الصفحة
            if ($('#toast-container').length === 0) {
                $('body').append('<div id="toast-container" class="toast-container position-fixed bottom-0 end-0 p-3"></div>');
            }
            
            $('#toast-container').append(toastHtml);
            
            // عرض التوست
            const toastElement = document.getElementById(toastId);
            const toast = new bootstrap.Toast(toastElement, {
                delay: 3000,
                animation: true
            });
            
            toast.show();
            
            // إزالة التوست بعد إخفائه
            $(toastElement).on('hidden.bs.toast', function() {
                $(this).remove();
            });
        } else {
            // استخدام تنبيه عادي إذا لم يكن التوست متاحًا
            console.log(message);
        }
    }

    // تنفيذ حركات انتقالية عند فتح وإغلاق القائمة
    $('#quickActionsDropdown').on('show.bs.dropdown', function() {
        setTimeout(function() {
            $('.quick-action-item').each(function(index) {
                $(this).css({
                    'opacity': 0,
                    'transform': 'translateY(10px)'
                }).animate({
                    'opacity': 1,
                    'transform': 'translateY(0)'
                }, 100 + (index * 30));
            });
        }, 100);
    });

    // تثبيت مواضع القوائم المنسدلة عند تهيئة Bootstrap
    $('.dropdown').on('show.bs.dropdown', function() {
        // التأكد من أن القائمة المنسدلة تظهر في المكان الصحيح من البداية
        $(this).find('.dropdown-menu').css({
            'position': 'absolute',
            'top': '100%',
            'transform': 'none'
        });
    });
    
    // معالجة خاصة لقائمة المستخدم بسبب مشكلتها
    $('#userDropdown').on('show.bs.dropdown', function() {
        setTimeout(function() {
            $('.user-dropdown').css({
                'position': 'absolute',
                'top': '100%',
                'transform': 'none',
                'margin-top': '0.5rem'
            });
        }, 0);
    });
});

/**
 * تهيئة التوسترات
 */
function initTooltips() {
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

/**
 * تهيئة حوارات تأكيد الحذف
 */
function initDeleteConfirmations() {
    $(document).on("click", ".btn-delete", function(e) {
        e.preventDefault();
        const url = $(this).attr("href");
        const title = $(this).data("title") || "هل أنت متأكد من الحذف؟";
        const message = $(this).data("message") || "لن تتمكن من استعادة هذا العنصر بعد الحذف!";
        
        confirmAction(message, title, function() {
            window.location.href = url;
        });
    });
}

/**
 * تهيئة التحقق من الفورم 
 */
function initFormValidations() {
    // التحقق من صحة النماذج
    const forms = document.querySelectorAll('.needs-validation');
    
    if (forms.length > 0) {
        forms.forEach(form => {
            form.addEventListener('submit', function(event) {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                    
                    // عرض رسالة خطأ
                    notify('يرجى التحقق من البيانات المدخلة', 'error');
                }
                
                form.classList.add('was-validated');
            }, false);
        });
    }
}

/**
 * تهيئة الفورم الديناميكية
 */
function initDynamicForms() {
    // إضافة صف جديد في نماذج البيانات المتعددة
    $(document).on("click", ".add-form-row", function() {
        const formsetName = $(this).data("formset");
        const formsetContainer = $("#" + formsetName + "-container");
        const totalForms = $("#id_" + formsetName + "-TOTAL_FORMS");
        const formNum = parseInt(totalForms.val());
        
        // نسخ النموذج الأخير
        const newForm = formsetContainer.find(".formset-row:last").clone(true);
        
        // تحديث المعرفات والأسماء
        newForm.find(":input").each(function() {
            const name = $(this).attr("name").replace("-" + (formNum - 1) + "-", "-" + formNum + "-");
            const id = "id_" + name;
            
            $(this).attr({"name": name, "id": id}).val("").removeAttr("checked");
        });
        
        // تحديث عناوين الحقول
        newForm.find("label").each(function() {
            const newFor = $(this).attr("for").replace("-" + (formNum - 1) + "-", "-" + formNum + "-");
            $(this).attr("for", newFor);
        });
        
        // إضافة النموذج الجديد
        formsetContainer.append(newForm);
        
        // تحديث العدد الإجمالي للنماذج
        totalForms.val(formNum + 1);
    });
    
    // حذف صف من نماذج البيانات المتعددة
    $(document).on("click", ".remove-form-row", function() {
        const formsetName = $(this).data("formset");
        const totalForms = $("#id_" + formsetName + "-TOTAL_FORMS");
        
        // حذف الصف فقط إذا كان هناك أكثر من صف واحد
        if (parseInt(totalForms.val()) > 1) {
            $(this).closest(".formset-row").remove();
            
            // تحديث عدد النماذج
            totalForms.val(parseInt(totalForms.val()) - 1);
            
            // إعادة ترقيم النماذج
            $(".formset-row").each(function(i) {
                $(this).find(":input").each(function() {
                    if ($(this).attr("name")) {
                        const name = $(this).attr("name").replace(/-\d+-/, "-" + i + "-");
                        const id = "id_" + name;
                        
                        $(this).attr({"name": name, "id": id});
                    }
                });
                
                $(this).find("label").each(function() {
                    if ($(this).attr("for")) {
                        const newFor = $(this).attr("for").replace(/-\d+-/, "-" + i + "-");
                        $(this).attr("for", newFor);
                    }
                });
            });
        } else {
            // إذا كان هناك صف واحد فقط، فقم بإعادة تعيين قيمه
            $(this).closest(".formset-row").find(":input").val("").prop("checked", false);
        }
    });
}

/**
 * تهيئة التبويبات المحفوظة
 */
function initSavedTabs() {
    // حفظ التبويب النشط في التخزين المحلي
    $('a[data-bs-toggle="tab"]').on('shown.bs.tab', function (e) {
        const tabId = $(e.target).attr('href');
        const tabContainer = $(e.target).closest('.tabs-container');
        const containerId = tabContainer.attr('id') || 'default-tabs';
        
        localStorage.setItem('activeTab-' + containerId, tabId);
    });
    
    // استعادة التبويب النشط
    $('.tabs-container').each(function() {
        const containerId = $(this).attr('id') || 'default-tabs';
        const activeTab = localStorage.getItem('activeTab-' + containerId);
        
        if (activeTab) {
            try {
                const tab = new bootstrap.Tab($(this).find('a[href="' + activeTab + '"]')[0]);
                tab.show();
            } catch (e) {
                // في حالة حدوث خطأ، لا تفعل شيئًا
            }
        }
    });
}

/**
 * تهيئة النوافذ المنبثقة
 */
function initModals() {
    // تحميل المحتوى عبر AJAX للنوافذ المنبثقة
    $(document).on('click', '[data-bs-toggle="ajax-modal"]', function(e) {
        e.preventDefault();
        
        const url = $(this).attr('href') || $(this).data('url');
        const target = $(this).data('bs-target');
        const modal = $(target);
        
        if (!url || !modal.length) return;
        
        // عرض شاشة التحميل
        modal.find('.modal-content').html('<div class="text-center my-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">جاري التحميل...</span></div><p class="mt-2">جاري التحميل...</p></div>');
        
        // فتح النافذة المنبثقة
        const bsModal = new bootstrap.Modal(modal[0]);
        bsModal.show();
        
        // تحميل المحتوى
        $.get(url, function(data) {
            modal.find('.modal-content').html(data);
            
            // تهيئة عناصر النموذج داخل النافذة المنبثقة
            modal.find('select.select2').select2({
                dropdownParent: modal
            });
            
            // تفعيل التحقق من صحة النموذج
            initFormValidations();
        }).fail(function() {
            modal.find('.modal-content').html('<div class="modal-header"><h5 class="modal-title">خطأ</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="إغلاق"></button></div><div class="modal-body"><div class="alert alert-danger">حدث خطأ أثناء تحميل المحتوى</div></div>');
        });
    });
    
    // تنظيف النافذة المنبثقة بعد إغلاقها
    $(document).on('hidden.bs.modal', '.modal', function() {
        if ($(this).hasClass('clear-on-close')) {
            $(this).find('.modal-body').html('');
        }
    });
}

/**
 * تهيئة الفلاتر
 */
function initFilters() {
    // تحديث الفلاتر عند التغيير
    $(document).on('change', '.filter-on-change', function() {
        $(this).closest('form').submit();
    });
    
    // زر إعادة ضبط الفلاتر
    $(document).on('click', '.reset-filters', function(e) {
        e.preventDefault();
        window.location.href = $(this).attr('href') || window.location.pathname;
    });
}

/**
 * عرض إشعار للمستخدم
 */
function notify(message, type = 'success', title = null) {
    if (!title) {
        if (type === 'success') title = 'تم بنجاح';
        else if (type === 'error') title = 'خطأ';
        else if (type === 'warning') title = 'تحذير';
        else title = 'معلومات';
    }
    
    Swal.fire({
        title: title,
        text: message,
        icon: type,
        toast: true,
        position: 'top-end',
        showConfirmButton: false,
        timer: 3000,
        timerProgressBar: true,
        rtl: true
    });
}

/**
 * تنسيق الأرقام كعملة
 */
function formatCurrency(amount, currency = 'ج.م', decimals = 2) {
    // استخدام دالة formatNumber من ملف number_formatter.js
    if (typeof formatNumber === 'function') {
        return formatNumber(amount) + ' ' + currency;
    }
    
    // الطريقة الاحتياطية في حالة عدم توفر دالة formatNumber
    if (isNaN(amount)) return '0.00 ' + currency;
    return parseFloat(amount).toFixed(decimals).replace(/\d(?=(\d{3})+\.)/g, '$&,') + ' ' + currency;
}

/**
 * تنسيق التاريخ
 */
function formatDate(dateString, format = 'yyyy-mm-dd') {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    
    if (format === 'yyyy-mm-dd') {
        return `${year}-${month}-${day}`;
    } else if (format === 'dd/mm/yyyy') {
        return `${day}/${month}/${year}`;
    } else if (format === 'mm/dd/yyyy') {
        return `${month}/${day}/${year}`;
    }
    
    return `${year}-${month}-${day}`;
}

/**
 * تحويل حجم الملف إلى تنسيق مقروء
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 بايت';
    
    const k = 1024;
    const sizes = ['بايت', 'كيلوبايت', 'ميجابايت', 'جيجابايت', 'تيرابايت'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * وظائف التنبيهات والتأكيدات
 */

/**
 * عرض رسالة تنبيه باستخدام SweetAlert2
 * @param {string} message - نص الرسالة
 * @param {string} type - نوع التنبيه (success, error, warning, info)
 * @param {string} title - عنوان التنبيه (اختياري)
 * @param {number} timer - وقت إخفاء التنبيه بالمللي ثانية (اختياري، الافتراضي 3000)
 */
function showAlert(message, type = 'info', title = '', timer = 3000) {
    const Toast = Swal.mixin({
        toast: true,
        position: 'top-end',
        showConfirmButton: false,
        timer: timer,
        timerProgressBar: true,
        didOpen: (toast) => {
            toast.addEventListener('mouseenter', Swal.stopTimer);
            toast.addEventListener('mouseleave', Swal.resumeTimer);
        }
    });
    
    Toast.fire({
        icon: type,
        title: title || message,
        text: title ? message : '',
    });
}

/**
 * عرض نافذة تأكيد مع خيارات نعم/لا
 * @param {string} message - نص السؤال
 * @param {string} title - عنوان النافذة
 * @param {Function} callback - دالة ترجع المستدعاة عند النقر على زر "نعم"
 * @param {string} confirmButtonText - نص زر التأكيد (اختياري، الافتراضي "نعم")
 * @param {string} cancelButtonText - نص زر الإلغاء (اختياري، الافتراضي "لا")
 */
function confirmAction(message, title, callback, confirmButtonText = 'نعم', cancelButtonText = 'لا') {
    Swal.fire({
        title: title,
        text: message,
        icon: 'question',
        showCancelButton: true,
        confirmButtonColor: '#3085d6',
        cancelButtonColor: '#d33',
        confirmButtonText: confirmButtonText,
        cancelButtonText: cancelButtonText,
        focusConfirm: false,
        focusCancel: true,
    }).then((result) => {
        if (result.isConfirmed && typeof callback === 'function') {
            callback();
        }
    });
}

/**
 * عرض نافذة تنبيه للنجاح مع زر موافق
 * @param {string} message - نص الرسالة
 * @param {string} title - عنوان النافذة (اختياري)
 * @param {Function} callback - دالة ترجع المستدعاة بعد إغلاق النافذة (اختياري)
 */
function successAlert(message, title = 'تمت العملية بنجاح', callback = null) {
    Swal.fire({
        icon: 'success',
        title: title,
        text: message,
        confirmButtonText: 'موافق'
    }).then(() => {
        if (typeof callback === 'function') {
            callback();
        }
    });
}

/**
 * عرض نافذة تنبيه للخطأ مع زر موافق
 * @param {string} message - نص رسالة الخطأ
 * @param {string} title - عنوان النافذة (اختياري)
 */
function errorAlert(message, title = 'حدث خطأ') {
    Swal.fire({
        icon: 'error',
        title: title,
        text: message,
        confirmButtonText: 'موافق'
    });
}

/**
 * إعادة ضبط كل حالات القوائم الفرعية
 */
function resetAllSubmenuStates() {
    // إغلاق جميع القوائم الفرعية المفتوحة حاليًا
    const openSubmenus = document.querySelectorAll('.submenu.show');
    openSubmenus.forEach(submenu => {
        // إغلاق القائمة
        submenu.classList.remove('show');
        submenu.style.height = '0';
        submenu.style.opacity = '0';
        
        // تحديث حالة الزر
        const submenuLink = document.querySelector(`a[href="#${submenu.id}"]`);
        if (submenuLink) {
            submenuLink.setAttribute('aria-expanded', 'false');
            submenuLink.classList.add('collapsed');
        }
    });
}

/**
 * تمييز الروابط النشطة في القائمة الجانبية بشكل تلقائي
 */
function highlightActiveMenu() {
    // الحصول على مسار URL الحالي
    const currentPath = window.location.pathname;
    
    // البحث عن جميع الروابط في القائمة
    const sidebarLinks = document.querySelectorAll('.sidebar-link, .submenu-link');
    
    // تحديد الروابط المطابقة
    let exactMatch = null;
    let partialMatches = [];
    
    sidebarLinks.forEach(link => {
        // إزالة class 'active' من جميع الروابط أولاً
        link.classList.remove('active');
        
        // الحصول على مسار الرابط
        const href = link.getAttribute('href');
        
        // تخطي الروابط الداخلية (مثل #collapseExample)
        if (href && !href.startsWith('#')) {
            try {
                // تحويل الرابط إلى مسار
                const linkPath = new URL(href, window.location.origin).pathname;
                
                // التطابق التام
                if (linkPath === currentPath) {
                    exactMatch = link;
                } 
                // التطابق الجزئي (إذا كان المسار الحالي يبدأ بمسار الرابط)
                else if (currentPath.startsWith(linkPath) && linkPath !== '/') {
                    partialMatches.push({
                        link: link,
                        path: linkPath
                    });
                }
            } catch (e) {
                // تجاهل أي أخطاء في تحليل الرابط
                console.error('خطأ في تحليل الرابط:', href, e);
            }
        }
    });
    
    // تطبيق class 'active' على الرابط المناسب
    if (exactMatch) {
        // إذا وجد تطابق تام، نستخدمه
        markAsActive(exactMatch);
    } else if (partialMatches.length > 0) {
        // إذا وجدت تطابقات جزئية، نستخدم أطول تطابق
        // (هذا يضمن تحديد الرابط الأكثر تحديدًا)
        partialMatches.sort((a, b) => b.path.length - a.path.length);
        markAsActive(partialMatches[0].link);
    }
}

/**
 * تمييز الرابط كنشط وفتح القائمة الفرعية التي يوجد بها إن وجدت
 * @param {Element} link - عنصر الرابط ليتم تمييزه
 */
function markAsActive(link) {
    // إضافة class 'active' للرابط
    link.classList.add('active');
    
    // إذا كان الرابط داخل قائمة فرعية، نفتح القائمة الفرعية
    const parentSubmenu = link.closest('.submenu');
    if (parentSubmenu) {
        // تمييز رابط القائمة الفرعية أيضًا
        const parentLink = document.querySelector(`a[href="#${parentSubmenu.id}"]`);
        if (parentLink) {
            parentLink.classList.add('active');
            
            // فتح القائمة الفرعية التي بها الرابط النشط
            if (!parentSubmenu.classList.contains('show')) {
                parentSubmenu.classList.add('show');
                parentSubmenu.style.height = 'auto';
                parentSubmenu.style.opacity = '1';
                parentSubmenu.style.transform = 'translateY(0)';
                
                // تحديث حالة رابط القائمة الفرعية
                parentLink.setAttribute('aria-expanded', 'true');
                parentLink.classList.remove('collapsed');
            }
        }
    }
}

/**
 * تهيئة السلايد بار
 */
function initSidebar() {
    const body = document.body;
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const mobileSidebarToggle = document.getElementById('mobile-sidebar-toggle');
    const sidebar = document.querySelector('.sidebar-wrapper');
    
    // التحقق من حجم الشاشة المبدئي وضبط الإعدادات
    checkScreenSize();
    
    // تبديل حالة القائمة الجانبية عند الضغط على الزر
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function(e) {
            e.preventDefault();
            body.classList.toggle('sidebar-collapsed');
        });
    }
    
    // تبديل حالة القائمة الجانبية في الأجهزة المحمولة
    if (mobileSidebarToggle) {
        mobileSidebarToggle.addEventListener('click', function(e) {
            e.preventDefault();
            body.classList.toggle('mobile-sidebar-visible');
        });
    }
    
    // إغلاق القائمة الجانبية عند النقر خارجها في الشاشات الصغيرة
    document.addEventListener('click', function(e) {
        if (body.classList.contains('mobile-sidebar-visible') && 
            !sidebar.contains(e.target) && 
            e.target !== mobileSidebarToggle) {
            body.classList.remove('mobile-sidebar-visible');
        }
    });
    
    // ضبط القوائم الفرعية
    setupSubmenus();
    
    // تمييز الروابط النشطة في القائمة الجانبية
    highlightActiveMenu();
    
    // مراقبة تغيير حجم النافذة
    window.addEventListener('resize', checkScreenSize);
}

/**
 * التحقق من حجم الشاشة وتطبيق الإعدادات المناسبة
 */
function checkScreenSize() {
    const body = document.body;
    
    if (window.innerWidth <= 991) {
        // إعادة تعيين حالة القائمة في الشاشات الصغيرة
        body.classList.remove('sidebar-collapsed');
    } else {
        // إزالة حالة القائمة المرئية في الأجهزة المحمولة في الشاشات الكبيرة
        body.classList.remove('mobile-sidebar-visible');
    }
}

/**
 * إعداد القوائم الفرعية في القائمة الجانبية
 */
function setupSubmenus() {
    const sidebarLinks = document.querySelectorAll('.sidebar-link[data-bs-toggle="collapse"]');
    
    sidebarLinks.forEach(link => {
        // استخدام Bootstrap Collapse API للتعامل مع القوائم الفرعية بشكل أفضل
        link.addEventListener('click', function(e) {
            const submenuId = this.getAttribute('href');
            
            // في القائمة المصغرة ومع الشاشات الكبيرة، منع السلوك الافتراضي
            if (document.body.classList.contains('sidebar-collapsed') && window.innerWidth > 991) {
                e.preventDefault();
                showSubmenu(submenuId.substring(1)); // إزالة # من المعرف
                return;
            }
            
            // حفظ حالة القائمة الفرعية
            const submenu = document.querySelector(submenuId);
            if (submenu) {
                // ضبط ارتفاع القائمة الفرعية ديناميكيًا لتحسين الأداء
                if (submenu.classList.contains('show')) {
                    // عند إغلاق القائمة، ضبط الارتفاع على الحجم الحالي قبل الإغلاق
                    submenu.style.height = submenu.scrollHeight + 'px';
                    // ضروري لتطبيق الانتقال بشكل سلس
                    setTimeout(() => {
                        submenu.style.height = '0';
                        submenu.style.opacity = '0';
                        submenu.style.transform = 'translateY(-10px)';
                    }, 10);
                } else {
                    // عند فتح القائمة، ضبط الارتفاع على auto بعد انتهاء الانتقال
                    submenu.style.height = submenu.scrollHeight + 'px';
                    submenu.style.opacity = '1';
                    submenu.style.transform = 'translateY(0)';
                    setTimeout(() => {
                        submenu.style.height = 'auto';
                    }, 300);
                }
            }
        });
        
        // التعامل مع تحرك الماوس فوق العناصر في وضع القائمة المصغرة
        if (window.innerWidth > 991) {
            const submenuId = link.getAttribute('href');
            const submenu = document.querySelector(submenuId);
            const parentItem = link.parentElement;
            
            if (submenu && parentItem) {
                parentItem.addEventListener('mouseenter', function() {
                    if (document.body.classList.contains('sidebar-collapsed')) {
                        showSubmenu(submenuId.substring(1));
                    }
                });
                
                parentItem.addEventListener('mouseleave', function() {
                    if (document.body.classList.contains('sidebar-collapsed')) {
                        hideSubmenu(submenuId.substring(1));
                    }
                });
            }
        }
    });
}

/**
 * عرض القائمة الفرعية بطريقة أكثر كفاءة
 */
function showSubmenu(submenuId) {
    const submenu = document.getElementById(submenuId);
    if (submenu) {
        submenu.classList.add('show');
        submenu.style.opacity = '1';
        submenu.style.transform = 'translateY(0)';
        submenu.style.height = 'auto';
        
        // تحديث حالة الزر المرتبط بهذه القائمة
        const submenuLink = document.querySelector(`a[href="#${submenuId}"]`);
        if (submenuLink) {
            submenuLink.setAttribute('aria-expanded', 'true');
            submenuLink.classList.remove('collapsed');
        }
    }
}

/**
 * إخفاء القائمة الفرعية بطريقة أكثر كفاءة
 */
function hideSubmenu(submenuId) {
    const submenu = document.getElementById(submenuId);
    if (submenu) {
        submenu.classList.remove('show');
        submenu.style.opacity = '0';
        submenu.style.transform = 'translateY(-5px)';
        submenu.style.height = '0';
        
        // تحديث حالة الزر المرتبط بهذه القائمة
        const submenuLink = document.querySelector(`a[href="#${submenuId}"]`);
        if (submenuLink) {
            submenuLink.setAttribute('aria-expanded', 'false');
            submenuLink.classList.add('collapsed');
        }
    }
}

/**
 * تهيئة القوائم المنسدلة 
 */
function initDropdowns() {
    const dropdownElements = document.querySelectorAll('.dropdown-toggle');
    
    dropdownElements.forEach(dropdown => {
        dropdown.addEventListener('click', function(e) {
            e.stopPropagation();
            const dropdownMenu = this.nextElementSibling;
            
            if (dropdownMenu && dropdownMenu.classList.contains('show')) {
                dropdownMenu.classList.remove('show');
            } else if (dropdownMenu) {
                const allDropdowns = document.querySelectorAll('.dropdown-menu.show');
                allDropdowns.forEach(menu => menu.classList.remove('show'));
                dropdownMenu.classList.add('show');
            }
        });
    });
    
    // إغلاق القوائم المنسدلة عند النقر خارجها
    document.addEventListener('click', function() {
        const allDropdowns = document.querySelectorAll('.dropdown-menu.show');
        allDropdowns.forEach(menu => menu.classList.remove('show'));
    });
} 