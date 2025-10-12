// إضافة مستمع حدث للزر sidebar-collapse
document.addEventListener('DOMContentLoaded', function() {
    
    // فحص حجم الشاشة لتحديد نوع الجهاز
    function isMobile() {
        return window.innerWidth <= 991;
    }
    
    // زر تصغير الشريط الجانبي (للكمبيوتر فقط) أو إغلاقه (للموبايل)
    const sidebarCollapseBtn = document.getElementById('sidebar-collapse');
    if (sidebarCollapseBtn) {
        // تحديث title الزر حسب نوع الجهاز
        if (isMobile()) {
            sidebarCollapseBtn.setAttribute('title', 'إغلاق القائمة');
        } else {
            sidebarCollapseBtn.setAttribute('title', 'تصغير/توسيع القائمة');
        }
        
        sidebarCollapseBtn.addEventListener('click', function(e) {
            e.preventDefault();
            if (isMobile()) {
                // على الموبايل: إغلاق الشريط الجانبي
                toggleMobileSidebar();
            } else {
                // على الكمبيوتر: تصغير/توسيع الشريط الجانبي
                toggleSidebarCollapse();
            }
        });
    }

    // جعل النقر على أي عنصر في السايدبار المصغر يقوم بتوسيع السايدبار (للكمبيوتر فقط)
    const sidebarLinks = document.querySelectorAll('.sidebar-item > .sidebar-link');
    if (sidebarLinks) {
        sidebarLinks.forEach(link => {
            link.addEventListener('click', function(e) {
                // إذا كان السايدبار مصغرًا والرابط يحتوي على قائمة فرعية وليس موبايل
                if (!isMobile() && document.body.classList.contains('sidebar-collapsed') && this.getAttribute('data-bs-toggle') === 'collapse') {
                    e.preventDefault(); // منع السلوك الافتراضي
                    toggleSidebarCollapse(); // توسيع السايدبار
                }
            });
        });
    }

    // استعادة حالة الشريط الجانبي من localStorage عند تحميل الصفحة (للكمبيوتر فقط)
    if (!isMobile() && localStorage.getItem('sidebar-collapsed') === 'true') {
        document.body.classList.add('sidebar-collapsed');
    } else if (isMobile()) {
        // التأكد من إزالة كلاس التصغير على الموبايل
        document.body.classList.remove('sidebar-collapsed');
    }

    // زر التبديل للهاتف المحمول - داخل الشريط الجانبي
    const sidebarToggleBtn = document.getElementById('sidebar-toggle');
    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener('click', function() {
            if (isMobile()) {
                toggleMobileSidebar();
            }
        });
    }

    // زر التبديل للهاتف المحمول - في الهيدر
    const mobileSidebarBtn = document.querySelector('.mobile-sidebar-btn');
    if (mobileSidebarBtn) {
        mobileSidebarBtn.addEventListener('click', function() {
            if (isMobile()) {
                toggleMobileSidebar();
            }
        });
    }

    // إغلاق الشريط الجانبي عند النقر على الخلفية (للموبايل فقط)
    document.addEventListener('click', function(e) {
        if (isMobile() && document.body.classList.contains('sidebar-toggled')) {
            const sidebar = document.querySelector('.sidebar-wrapper');
            const mobileSidebarBtn = document.querySelector('.mobile-sidebar-btn');
            const sidebarToggleBtn = document.getElementById('sidebar-toggle');
            
            // إذا كان النقر خارج الشريط الجانبي وليس على أزرار التحكم
            if (!sidebar.contains(e.target) && 
                !mobileSidebarBtn.contains(e.target) && 
                (!sidebarToggleBtn || !sidebarToggleBtn.contains(e.target))) {
                document.body.classList.remove('sidebar-toggled');
            }
        }
    });

    // إزالة الكلاسات المتضاربة عند تغيير حجم الشاشة
    window.addEventListener('resize', function() {
        if (isMobile()) {
            // إزالة كلاس التصغير عند الانتقال للموبايل
            document.body.classList.remove('sidebar-collapsed');
            // تحديث title الزر
            if (sidebarCollapseBtn) {
                sidebarCollapseBtn.setAttribute('title', 'إغلاق القائمة');
            }
        } else {
            // إزالة كلاس الموبايل عند الانتقال للكمبيوتر
            document.body.classList.remove('sidebar-toggled');
            // تحديث title الزر واستعادة حالة التصغير
            if (sidebarCollapseBtn) {
                sidebarCollapseBtn.setAttribute('title', 'تصغير/توسيع القائمة');
            }
            if (localStorage.getItem('sidebar-collapsed') === 'true') {
                document.body.classList.add('sidebar-collapsed');
            }
        }
    });

    // فحص دوري لإزالة sidebar-collapsed على الموبايل
    function checkAndFixMobileState() {
        if (isMobile() && document.body.classList.contains('sidebar-collapsed')) {
            document.body.classList.remove('sidebar-collapsed');
        }
    }

    // تشغيل الفحص عند تحميل الصفحة وعند فتح الشريط الجانبي
    checkAndFixMobileState();
    
    // مراقبة تغييرات كلاس sidebar-collapsed والتدخل على الموبايل
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                if (isMobile() && document.body.classList.contains('sidebar-collapsed')) {
                    document.body.classList.remove('sidebar-collapsed');
                }
            }
        });
    });
    
    // بدء مراقبة تغييرات الكلاسات على body
    observer.observe(document.body, {
        attributes: true,
        attributeFilter: ['class']
    });

    // وظيفة لتبديل حالة الشريط الجانبي (للكمبيوتر)
    function toggleSidebarCollapse() {
        document.body.classList.toggle('sidebar-collapsed');
        // حفظ حالة الشريط الجانبي في localStorage
        if (document.body.classList.contains('sidebar-collapsed')) {
            localStorage.setItem('sidebar-collapsed', 'true');
        } else {
            localStorage.setItem('sidebar-collapsed', 'false');
        }
    }
    
    // وظيفة لتبديل الشريط الجانبي (للموبايل)
    function toggleMobileSidebar() {
        // التأكد من إزالة كلاس التصغير قبل فتح الشريط الجانبي
        if (document.body.classList.contains('sidebar-collapsed')) {
            document.body.classList.remove('sidebar-collapsed');
        }
        document.body.classList.toggle('sidebar-toggled');
    }
}); 