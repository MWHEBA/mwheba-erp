/**
 * Unified Product Select2 Initialization
 * يهيئ select2 على أي .product-select في الصفحة
 * يدعم الصفوف الديناميكية (addRow)
 */

window.ProductSelect2 = {

    /**
     * تهيئة select2 على عنصر واحد
     * @param {jQuery} $el - عنصر الـ select
     * @param {jQuery|null} $dropdownParent - الـ parent للـ dropdown (للمودالات)
     */
    init: function($el, $dropdownParent) {
        if ($el.hasClass('select2-hidden-accessible')) return; // مهيأ مسبقاً

        var options = {
            theme: 'bootstrap-5',
            placeholder: $el.find('option[value=""]').text() || '--- اختر المنتج ---',
            allowClear: true,
            width: '100%',
            language: {
                noResults: function() { return 'لا توجد نتائج'; },
                searching: function() { return 'جاري البحث...'; }
            }
        };

        if ($dropdownParent && $dropdownParent.length) {
            options.dropdownParent = $dropdownParent;
        }

        $el.select2(options);
    },

    /**
     * تهيئة جميع .product-select في الصفحة أو داخل container معين
     * @param {jQuery|null} $container - container للبحث فيه (اختياري)
     * @param {jQuery|null} $dropdownParent - الـ parent للـ dropdown (للمودالات)
     */
    initAll: function($container, $dropdownParent) {
        var self = this;
        var $scope = $container || $(document);
        $scope.find('.product-select').each(function() {
            self.init($(this), $dropdownParent);
        });
    },

    /**
     * تهيئة صف جديد بعد addRow
     * يُستدعى بعد إضافة صف جديد في الـ formset
     * @param {jQuery} $row - الصف الجديد
     */
    initRow: function($row) {
        this.initAll($row);
    }
};
