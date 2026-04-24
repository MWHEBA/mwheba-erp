/**
 * Financial Category Suggestion
 * اقتراح التصنيف المالي بناءً على آخر اختيار للمورد
 */

(function() {
    'use strict';

    // تخزين آخر تصنيف لكل مورد في localStorage
    const STORAGE_KEY = 'vendor_last_category';

    function getVendorLastCategory(vendorId) {
        try {
            const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            return data[vendorId] || null;
        } catch (e) {
            return null;
        }
    }

    function setVendorLastCategory(vendorId, categoryId) {
        try {
            const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            data[vendorId] = categoryId;
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (e) {
            console.error('Failed to save category suggestion:', e);
        }
    }

    function initCategorySuggestion() {
        const supplierSelect = document.getElementById('id_supplier');
        const vendorSelect = document.getElementById('id_vendor');
        const categorySelect = document.getElementById('id_financial_category');

        if (!categorySelect) return;

        const vendorField = supplierSelect || vendorSelect;
        if (!vendorField) return;

        // عند تغيير المورد، اقترح آخر تصنيف
        vendorField.addEventListener('change', function() {
            // لو في وضع النسخ، لا تـoverride التصنيف
            if (window._disableCategorySuggestion) return;

            const vendorId = this.value;
            if (!vendorId) return;

            const lastCategory = getVendorLastCategory(vendorId);
            if (lastCategory && categorySelect.querySelector(`option[value="${lastCategory}"]`)) {
                categorySelect.value = lastCategory;
                // trigger change event for any listeners
                categorySelect.dispatchEvent(new Event('change'));
            }
        });

        // عند حفظ النموذج، احفظ الاختيار
        const form = categorySelect.closest('form');
        if (form) {
            form.addEventListener('submit', function() {
                const vendorId = vendorField.value;
                const categoryId = categorySelect.value;
                if (vendorId && categoryId) {
                    setVendorLastCategory(vendorId, categoryId);
                }
            });
        }
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCategorySuggestion);
    } else {
        initCategorySuggestion();
    }
})();
