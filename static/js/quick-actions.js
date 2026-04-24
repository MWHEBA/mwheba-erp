/**
 * Quick Actions JavaScript
 * تحسين تفاعل أزرار الإجراءات السريعة
 */

document.addEventListener('DOMContentLoaded', function() {
    // العثور على زر الإجراءات السريعة
    const quickActionBtn = document.getElementById('quickActionsDropdown');
    const quickActionsDropdown = document.querySelector('.quick-actions-dropdown');
    
    if (quickActionBtn && quickActionsDropdown) {
        // إضافة تأثير الحركة عند فتح القائمة
        quickActionBtn.addEventListener('shown.bs.dropdown', function() {
            quickActionsDropdown.classList.add('show');
        });
        
        // إزالة تأثير الحركة عند إغلاق القائمة
        quickActionBtn.addEventListener('hidden.bs.dropdown', function() {
            quickActionsDropdown.classList.remove('show');
        });
        
        // تحسين الوصولية - إضافة دعم لوحة المفاتيح
        const quickActionItems = quickActionsDropdown.querySelectorAll('.quick-action-item');
        
        quickActionItems.forEach((item, index) => {
            // إضافة tabindex للتنقل بالكيبورد
            item.setAttribute('tabindex', '0');
            
            // إضافة دعم مفتاح Enter و Space
            item.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    item.click();
                }
            });
            
            // تحسين التنقل بالأسهم
            item.addEventListener('keydown', function(e) {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    const nextItem = quickActionItems[index + 1];
                    if (nextItem) {
                        nextItem.focus();
                    }
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    const prevItem = quickActionItems[index - 1];
                    if (prevItem) {
                        prevItem.focus();
                    }
                }
            });
        });
        
        // إضافة تأثير بصري عند التحويم
        quickActionItems.forEach(item => {
            const icon = item.querySelector('.quick-action-icon');
            
            item.addEventListener('mouseenter', function() {
                if (icon) {
                    icon.style.transform = 'scale(1.05)';
                }
            });
            
            item.addEventListener('mouseleave', function() {
                if (icon) {
                    icon.style.transform = 'scale(1)';
                }
            });
        });
        
        // إغلاق القائمة عند النقر خارجها
        document.addEventListener('click', function(e) {
            if (!quickActionBtn.contains(e.target) && !quickActionsDropdown.contains(e.target)) {
                const dropdown = bootstrap.Dropdown.getInstance(quickActionBtn);
                if (dropdown) {
                    dropdown.hide();
                }
            }
        });
        
        // إضافة تأثير تحميل عند النقر على عنصر
        quickActionItems.forEach(item => {
            item.addEventListener('click', function(e) {
                // إضافة مؤشر تحميل بسيط
                const originalContent = item.innerHTML;
                const loadingIcon = '<i class="fas fa-spinner fa-spin me-2"></i>';
                
                // إضافة أيقونة التحميل
                const titleElement = item.querySelector('.quick-action-title');
                if (titleElement) {
                    titleElement.innerHTML = loadingIcon + titleElement.textContent;
                }
                
                // إزالة أيقونة التحميل بعد فترة قصيرة (في حالة عدم تحويل الصفحة)
                setTimeout(() => {
                    item.innerHTML = originalContent;
                }, 2000);
            });
        });
    }
    
    // تحسين الأداء - تأخير تحميل المحتوى الثقيل
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // يمكن إضافة تحميل محتوى إضافي هنا عند الحاجة
                entry.target.classList.add('loaded');
            }
        });
    });
    
    // مراقبة عناصر الإجراءات السريعة
    const quickActionElements = document.querySelectorAll('.quick-action-item');
    quickActionElements.forEach(el => observer.observe(el));
});

// دالة مساعدة لإضافة إجراءات سريعة جديدة برمجياً
function addQuickAction(category, action) {
    const quickActionsBody = document.querySelector('.quick-actions-body');
    if (!quickActionsBody) return;
    
    let categoryElement = quickActionsBody.querySelector(`[data-category="${category}"]`);
    
    if (!categoryElement) {
        // إنشاء فئة جديدة إذا لم تكن موجودة
        categoryElement = document.createElement('div');
        categoryElement.className = 'quick-actions-category';
        categoryElement.setAttribute('data-category', category);
        
        const categoryHeader = document.createElement('h6');
        categoryHeader.className = 'dropdown-header';
        categoryHeader.innerHTML = `<i class="${action.categoryIcon} me-2"></i><span>${category}</span>`;
        
        categoryElement.appendChild(categoryHeader);
        quickActionsBody.appendChild(categoryElement);
    }
    
    // إضافة العنصر الجديد
    const actionElement = document.createElement('a');
    actionElement.className = 'dropdown-item quick-action-item';
    actionElement.href = action.url || '#';
    actionElement.innerHTML = `
        <div class="quick-action-icon ${action.iconBg}">
            <i class="${action.icon} ${action.iconColor}"></i>
        </div>
        <div class="quick-action-content">
            <div class="quick-action-title">${action.title}</div>
            <div class="quick-action-desc">${action.description}</div>
        </div>
    `;
    
    categoryElement.appendChild(actionElement);
}

// تصدير الدوال للاستخدام العام
window.QuickActions = {
    add: addQuickAction
};