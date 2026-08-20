/**
 * Unified Product Picker & Fast Barcode Scanner Component Engine
 * MWHEBA ERP System
 */
(function(window, $) {
    'use strict';

    var ProductPicker = {
        options: {
            type: 'sale', // 'sale', 'purchase', or 'quotation'
            priceField: 'selling_price',
            currencySymbol: 'ج.م',
            getWarehouseId: function() { return $('#id_warehouse').val() || ''; },
            getInvoiceId: function() { return '0'; },
            onProductSelect: null // function($row, product, matchType) {}
        },
        _activePickerRow: null,
        _activeCategory: 'all',
        _activeType: 'all',
        _searchTerm: '',
        _lookupTimeout: null,
        _modalSearchTimeout: null,

        init: function(userOptions) {
            this.options = $.extend({}, this.options, userOptions);
            var savedShowAll = localStorage.getItem('mwheba_picker_show_all');
            if (savedShowAll !== null) {
                this.syncShowAllState(savedShowAll === 'true');
            }
            this.syncCurrencyLock();
            this.bindEvents();
            this.bindItemsContainer();
            this.bindPreSubmitSanitation();
            this.loadInitialStock();
        },

        syncCurrencyLock: function() {
            var hasRowsWithProducts = false;
            $('#items-container .product-id-input').each(function() {
                if ($(this).val()) {
                    hasRowsWithProducts = true;
                    return false;
                }
            });
            
            var $currSelect = $('#id_currency');
            if ($currSelect.length) {
                if (hasRowsWithProducts) {
                    $currSelect.data('is-locked-by-items', true);
                } else {
                    $currSelect.data('is-locked-by-items', false);
                }
            }
        },

        syncShowAllState: function(isChecked) {
            $('.show-all-products-toggle, #show-all-products, #modal-show-all-products, #page-show-all-products').prop('checked', isChecked);
            localStorage.setItem('mwheba_picker_show_all', isChecked ? 'true' : 'false');
        },

        resolveProductPrice: function(p) {
            if (!p) return 0;
            var currencyCode = $('#id_currency').val() || 'EGP';
            var rate = parseFloat($('#id_exchange_rate').val()) || 1.0;
            var isPurchase = (this.options.type === 'purchase');
            var priceType = isPurchase ? 'cost' : 'selling';

            var basePrice = isPurchase ? (p.cost_price !== undefined ? p.cost_price : (p.price || 0)) : (p.selling_price !== undefined ? p.selling_price : (p.price || 0));

            if (!currencyCode || currencyCode === 'EGP') {
                return basePrice;
            }

            if (p.currency_prices && p.currency_prices[currencyCode]) {
                var explicitVal = p.currency_prices[currencyCode][priceType];
                if (explicitVal !== null && explicitVal !== undefined && parseFloat(explicitVal) > 0) {
                    return parseFloat(explicitVal);
                }
            }

            if (rate > 0) {
                var converted = basePrice / rate;
                return parseFloat(converted.toFixed(4));
            }

            return basePrice;
        },

        renderRow: function(itemData, customOptions) {
            itemData = itemData || {};
            var opts = $.extend({}, this.options, customOptions || {});
            var self = this;
            
            var isSalesRepOnly = $('#django-sales-form-data').data('is-sales-rep-only') === true;
            var priceReadonly = (isSalesRepOnly && opts.type === 'sale') ? 'readonly' : '';
            var currencySymbol = opts.currencySymbol || 'ج.م';
            var isPurchase = (opts.type === 'purchase');
            var isServiceType = (opts.allowedItemTypes === 'services');
            
            var labelProductText = isServiceType ? 'الخدمة' : (isPurchase ? 'المنتج / الخدمة' : 'المنتج / الخدمة');
            var priceFieldName = isPurchase ? 'unit_cost[]' : 'unit_price[]';

            var productId = itemData.id || itemData.product_id || '';
            var productCode = itemData.code || itemData.sku || '';
            var unitPrice = (itemData.price !== undefined && itemData.price !== null) ? itemData.price : (itemData.unit_price || itemData.unit_cost || 0);
            var qty = itemData.quantity || 1;
            var itemDisc = itemData.discount || 0;

            var productName = itemData.name || (productId ? 'منتج #' + productId : 'اختر المنتج / الخدمة');
            var productStock = itemData.stock || 0;
            var productPrice = unitPrice;
            var isService = itemData.is_service === true || itemData.is_service === "true";

            if (window._allProducts && productId) {
                var found = window._allProducts.find(function(p) { return String(p.id) === String(productId); });
                if (found) {
                    productName = found.name;
                    productStock = found.stock;
                    var resolvedP = self.resolveProductPrice(found);
                    productPrice = resolvedP;
                    if (!itemData.price && !itemData.unit_price && !itemData.unit_cost) {
                        unitPrice = resolvedP;
                    }
                    isService = found.is_service === true || found.is_service === "true";
                    if (!productCode && (found.code || found.sku)) {
                        productCode = found.code || found.sku;
                    }
                }
            }

            var itemTotal = itemData.total !== undefined ? itemData.total : ((qty * unitPrice) - itemDisc);

            var removeBtn = (opts.showRemoveButton !== false)
                ? '<a href="javascript:void(0)" class="remove-item" title="إزالة البند"><i class="fas fa-times-circle"></i></a>'
                : '';

            var $row = $('<div class="item-row row g-2 align-items-center">' +
                '<div class="col-12 col-md-2">' +
                    '<label class="form-label form-label-sm product-code-label">الكود / الباركود</label>' +
                    '<input type="text" class="form-control form-control-sm product-code-input" placeholder="الكود / الباركود" value="' + productCode + '">' +
                '</div>' +
                '<div class="col-12 col-md-3">' +
                    '<div class="product-header-row d-flex align-items-center mb-2">' +
                        '<label class="form-label form-label-sm product-label product-header required-field mb-0">' + labelProductText + '</label>' +
                        '<span class="stock-info"></span>' +
                    '</div>' +
                    '<button type="button" class="product-picker-btn"><span class="' + (productId ? 'selected-text' : 'placeholder-text') + '">' + productName + '</span><i class="fas fa-th-large text-muted small"></i></button>' +
                    '<input type="hidden" name="product[]" class="product-id-input" value="' + productId + '" data-price="' + productPrice + '" data-stock="' + productStock + '" data-is-service="' + isService + '" required>' +
                '</div>' +
                '<div class="col-6 col-md-1"><label class="form-label form-label-sm required-field">الكمية</label><input type="number" name="quantity[]" class="form-control form-control-sm quantity" min="1" step="1" value="' + qty + '" required></div>' +
                '<div class="col-6 col-md-2"><label class="form-label form-label-sm required-field">' + (isPurchase ? 'سعر التكلفة' : 'سعر الوحدة') + '</label><input type="text" inputmode="decimal" name="' + priceFieldName + '" class="form-control form-control-sm unit-price" value="' + unitPrice + '" required ' + priceReadonly + '></div>' +
                '<div class="col-6 col-md-2"><label class="form-label form-label-sm">الخصم</label><input type="number" name="discount[]" class="form-control form-control-sm item-discount" min="0" value="' + itemDisc + '"></div>' +
                '<div class="col-6 col-md-2"><label class="form-label form-label-sm">الإجمالي</label><div class="input-group input-group-sm"><input type="text" class="form-control form-control-sm item-total" value="' + itemTotal + '" readonly><span class="input-group-text px-1">' + currencySymbol + '</span></div></div>' +
                removeBtn +
            '</div>');

            if (productId && typeof this.renderStockState === 'function') {
                this.renderStockState($row, {
                    stock: productStock,
                    is_service: isService,
                    quantity: qty
                }, isPurchase ? 'purchase' : 'sale');
            }

            return $row;
        },

        renderItems: function(container, items, customOptions) {
            var $container = $(container);
            $container.empty();
            if (!items || !Array.isArray(items)) return;

            var self = this;
            items.forEach(function(item, index) {
                var opts = $.extend({}, customOptions, { showRemoveButton: index > 0 });
                var $row = self.renderRow(item, opts);
                $container.append($row);
            });

            if (typeof window.bindEventHandlers === 'function') {
                window.bindEventHandlers();
            }
            if (typeof window.calculateTotals === 'function') {
                window.calculateTotals();
            }
        },

        // إطار عمل موحد لإدارة جدول البنود (إضافة، حذف، استنساخ وتطهير صفوف)
        bindItemsContainer: function() {
            var self = this;

            // إضافة بند جديد عند النقر على #add-item
            $(document).off('click.productPickerAdd', '#add-item').on('click.productPickerAdd', '#add-item', function(e) {
                e.preventDefault();
                var $container = $('#items-container');
                var $lastRow = $container.find('.item-row:last-child');
                
                // حماية من التكرار الفارغ: إذا كان الصف الأخير فارغاً، يتم توجيه مؤشر الكتابة إليه
                if ($lastRow.length) {
                    var lastProductId = $lastRow.find('.product-id-input').val();
                    var lastCode = $lastRow.find('.product-code-input').val();
                    if (!lastProductId && (!lastCode || lastCode.trim() === '')) {
                        $lastRow.find('.product-code-input').focus();
                        return;
                    }
                }

                var $newRow = self.renderRow({}, { showRemoveButton: true });

                // دعم تحديث Django Formset TOTAL_FORMS إن وجد
                var $totalForms = $('#id_items-TOTAL_FORMS, input[name$="-TOTAL_FORMS"]');
                if ($totalForms.length) {
                    var count = $container.find('.item-row').length;
                    $totalForms.val(count + 1);
                }

                $container.append($newRow);

                if (typeof window.bindEventHandlers === 'function') {
                    window.bindEventHandlers();
                }

                if (typeof window.calculateTotals === 'function') {
                    window.calculateTotals();
                }

                if (typeof self.options.onRowAdded === 'function') {
                    self.options.onRowAdded($newRow);
                }

                self.syncCurrencyLock();

                setTimeout(function() {
                    $newRow.find('.product-code-input').focus();
                }, 100);
            });

            // إزالة بند عند النقر على .remove-item
            $(document).off('click.productPickerRemove', '.remove-item').on('click.productPickerRemove', '.remove-item', function(e) {
                e.preventDefault();
                var $container = $('#items-container');
                if ($container.find('.item-row').length > 1) {
                    var $row = $(this).closest('.item-row');
                    $row.remove();

                    // تحديث TOTAL_FORMS لـ Django Formset
                    var $totalForms = $('#id_items-TOTAL_FORMS, input[name$="-TOTAL_FORMS"]');
                    if ($totalForms.length) {
                        $totalForms.val($container.find('.item-row').length);
                    }

                    if (typeof window.calculateTotals === 'function') {
                        window.calculateTotals();
                    }

                    self.syncCurrencyLock();

                    if (typeof self.options.onRowRemoved === 'function') {
                        self.options.onRowRemoved();
                    }
                } else {
                    if (typeof toastr !== 'undefined') {
                        toastr.warning('يجب الإبقاء على بند واحد على الأقل في الفاتورة');
                    }
                }
            });

            // تفاعل شارة المخزون فورياً مع أي تغيير في حقل الكمية عبر كافة النماذج
            $(document).off('input.productPickerQty change.productPickerQty keyup.productPickerQty', '#items-container .quantity, .item-row .quantity, input[name^="quantity"]').on('input.productPickerQty change.productPickerQty keyup.productPickerQty', '#items-container .quantity, .item-row .quantity, input[name^="quantity"]', function() {
                var $row = $(this).closest('.item-row');
                var $idInput = $row.find('.product-id-input');
                var productId = $idInput.val();
                if (!productId) return;

                var isService = $idInput.attr('data-is-service') === 'true' || 
                                $idInput.attr('data-is-service') === true || 
                                $idInput.data('is-service') === true;
                var stock = parseInt($idInput.attr('data-stock') !== undefined ? $idInput.attr('data-stock') : ($idInput.data('stock') || 0));
                if (isNaN(stock)) stock = 0;
                var qty = parseFloat($(this).val()) || 0;

                self.renderStockState($row, {
                    stock: stock,
                    is_service: isService,
                    quantity: qty
                }, self.options.type);
            });
        },

        // تنظيف وتخليص جدول البنود من الصفوف الفارغة الأخيرة تلقائياً
        sanitizeTrailingEmptyRows: function() {
            var $container = $('#items-container');
            if (!$container.length) return;
            
            var $rows = $container.find('.item-row');
            while ($rows.length > 1) {
                var $lastRow = $rows.last();
                var lastProductId = $lastRow.find('.product-id-input').val();
                var lastCode = $lastRow.find('.product-code-input').val();
                if (!lastProductId && (!lastCode || lastCode.trim() === '')) {
                    $lastRow.remove();
                    $rows = $container.find('.item-row');
                } else {
                    break;
                }
            }

            // تحديث TOTAL_FORMS لـ Django Formset
            var $totalForms = $('#id_items-TOTAL_FORMS, input[name$="-TOTAL_FORMS"]');
            if ($totalForms.length) {
                $totalForms.val($container.find('.item-row').length);
            }

            if (typeof window.calculateTotals === 'function') {
                window.calculateTotals();
            }
        },

        bindPreSubmitSanitation: function() {
            var self = this;

            // تنفيذ التنظيف وتأكيد إرسال قيمة العملة حتى لو كانت معطلة بالواجهة
            $(document).off('click.productPickerSanitizeSubmit', 'button[type="submit"], input[type="submit"]').on('click.productPickerSanitizeSubmit', 'button[type="submit"], input[type="submit"]', function() {
                self.sanitizeTrailingEmptyRows();
                $('#id_currency').prop('disabled', false);
            });

            $(document).off('submit.productPickerSanitizeForm', 'form:has(#items-container)').on('submit.productPickerSanitizeForm', 'form:has(#items-container)', function() {
                self.sanitizeTrailingEmptyRows();
                $('#id_currency').prop('disabled', false);
            });
        },

        bindEvents: function() {
            var self = this;

            // 1. فتح المودال عند النقر على زر اختيار المنتج
            $(document).off('click.productPicker', '.product-picker-btn').on('click.productPicker', '.product-picker-btn', function() {
                self._activePickerRow = $(this).closest('.item-row');
                self._activeCategory = 'all';
                self._activeType = 'all';
                self._searchTerm = '';

                $('#picker-search').val('');
                var typeRadioAll = document.getElementById('type-all');
                if (typeRadioAll) typeRadioAll.checked = true;

                $('#categoryTabs .nav-link').removeClass('active');
                $('#categoryTabs .nav-link[data-category="all"]').addClass('active');

                // استرجاع حالة زر "إظهار كافة المنتجات" الحالية المحفوظة ومزامنتها
                var savedShowAll = localStorage.getItem('mwheba_picker_show_all');
                if (savedShowAll !== null) {
                    self.syncShowAllState(savedShowAll === 'true');
                }

                self.loadModalProducts();
                var modalEl = document.getElementById('productPickerModal');
                if (modalEl) {
                    var modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                    modal.show();
                }
            });

            // 2. الفوكس التلقائي على حقل البحث عند اكتمال ظهور المودال
            $(document).off('shown.bs.modal.productPicker', '#productPickerModal').on('shown.bs.modal.productPicker', '#productPickerModal', function() {
                $('#picker-search').focus().select();
            });

            // 3. التبديل بين التصنيفات داخل المودال
            $(document).off('click.productPicker', '#categoryTabs .nav-link').on('click.productPicker', '#categoryTabs .nav-link', function(e) {
                e.preventDefault();
                $('#categoryTabs .nav-link').removeClass('active');
                $(this).addClass('active');
                self._activeCategory = $(this).data('category');
                self.loadModalProducts();
            });

            // 4. تغيير نوع البند (المنتجات / الخدمات) عبر أزرار الراديو
            $(document).off('change.productPicker', 'input[name="picker-type"]').on('change.productPicker', 'input[name="picker-type"]', function() {
                self._activeType = $(this).val();
                self._activeCategory = 'all';
                $('#categoryTabs .nav-link').removeClass('active');
                $('#categoryTabs .nav-link[data-category="all"]').addClass('active');
                self.loadModalProducts();
            });

            // 5. البحث الفوري داخل المودال
            $(document).off('input.productPicker', '#picker-search').on('input.productPicker', '#picker-search', function() {
                self._searchTerm = $(this).val().trim().toLowerCase();
                self.loadModalProducts();
            });

            // 6. اختيار منتج من شبكة الكروت في المودال
            $(document).off('click.productPicker', '.product-card').on('click.productPicker', '.product-card', function() {
                var $card = $(this);
                if (!self._activePickerRow) return;

                var product = {
                    id: $card.data('id'),
                    name: $card.data('name'),
                    code: $card.data('code') || '',
                    price: $card.data('price'),
                    stock: parseFloat($card.data('stock') || 0),
                    is_service: $card.data('is-service') === true || $card.data('is-service') === "true"
                };

                self.applyProductToRow(self._activePickerRow, product, 'modal');

                var modalEl = document.getElementById('productPickerModal');
                if (modalEl) {
                    var modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }

                var $row = self._activePickerRow;
                self._activePickerRow = null;

                setTimeout(function() {
                    var $qtyInput = $row.find('.quantity');
                    if ($qtyInput.length) $qtyInput.focus().select();
                }, 300);
            });

            // 7. تغيير إعداد إظهار كافة المنتجات ومزامنة المفتاحين (في الشاشة والمودال)
            $(document).off('change.productPicker', '.show-all-products-toggle, #show-all-products, #modal-show-all-products, #page-show-all-products').on('change.productPicker', '.show-all-products-toggle, #show-all-products, #modal-show-all-products, #page-show-all-products', function() {
                var isChecked = $(this).is(':checked');
                self.syncShowAllState(isChecked);
                if ($('#productPickerModal').hasClass('show')) {
                    self.loadModalProducts();
                }
            });

            // 8. ضغط Enter في حقول (الكمية، سعر الوحدة، التكلفة، أو الخصم) يضيف بنداً جديداً فوراً
            $(document).off('keydown.enterAddItem', '#items-container .quantity, #items-container .unit-price, #items-container .unit-cost, #items-container .item-discount')
                .on('keydown.enterAddItem', '#items-container .quantity, #items-container .unit-price, #items-container .unit-cost, #items-container .item-discount', function(e) {
                    if (e.which === 13 || e.key === 'Enter') {
                        e.preventDefault();
                        $('#add-item').trigger('click');
                    }
                });

            // 9. التنقل بالأسهم و Enter و Escape في حقل الكود / الباركود والقائمة المنسدلة
            $(document).off('keydown.enterCodeInput keydown.codeInputNav', '.product-code-input').on('keydown.codeInputNav', '.product-code-input', function(e) {
                var $input = $(this);
                var $dropdown = $input.parent().find('.code-lookup-dropdown');

                // التنقل بالأسهم و Enter/Escape عند وجود قائمة البحث المنسدلة
                if ($dropdown.length > 0) {
                    var $items = $dropdown.find('.code-lookup-item');
                    if ($items.length > 0) {
                        var currentIndex = $items.filter('.active').index();

                        if (e.key === 'ArrowDown' || e.which === 40) {
                            e.preventDefault();
                            var nextIndex = (currentIndex < 0 || currentIndex >= $items.length - 1) ? 0 : currentIndex + 1;
                            $items.removeClass('active');
                            var $nextItem = $items.eq(nextIndex).addClass('active');
                            if ($nextItem.length && $nextItem[0].scrollIntoView) {
                                $nextItem[0].scrollIntoView({ block: 'nearest' });
                            }
                            return;
                        }

                        if (e.key === 'ArrowUp' || e.which === 38) {
                            e.preventDefault();
                            var prevIndex = (currentIndex <= 0) ? $items.length - 1 : currentIndex - 1;
                            $items.removeClass('active');
                            var $prevItem = $items.eq(prevIndex).addClass('active');
                            if ($prevItem.length && $prevItem[0].scrollIntoView) {
                                $prevItem[0].scrollIntoView({ block: 'nearest' });
                            }
                            return;
                        }

                        if (e.key === 'Escape' || e.which === 27) {
                            e.preventDefault();
                            $dropdown.remove();
                            return;
                        }

                        if (e.key === 'Enter' || e.which === 13) {
                            e.preventDefault();
                            e.stopPropagation();
                            var $activeItem = $items.filter('.active');
                            if (!$activeItem.length) {
                                $activeItem = $items.first();
                            }
                            if ($activeItem.length) {
                                $activeItem.trigger('click');
                            } else {
                                $dropdown.remove();
                            }
                            return;
                        }
                    }
                }

                // ضغط Enter في حقل الكود عند عدم وجود القائمة المنسدلة
                if (e.which === 13 || e.key === 'Enter') {
                    e.preventDefault();
                    e.stopPropagation();
                    var query = $input.val().trim();
                    var $row = $input.closest('.item-row');

                    if (query === '') {
                        // كود فارغ -> فتح المودال فوراً بدون إرسال النموذج
                        self._activePickerRow = $row;
                        self._activeCategory = 'all';
                        self._activeType = 'all';
                        self._searchTerm = '';
                        $('#picker-search').val('');
                        self.loadModalProducts();
                        var modalEl = document.getElementById('productPickerModal');
                        if (modalEl) {
                            var modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                            modal.show();
                        }
                    } else {
                        // كود مكتوب -> مطابقة فورية ومباشرة
                        self.performCodeLookup($row, $input, query, false, true);
                    }
                }
            });

            // 8. البحث المباشر في حقل الباركود / الكود بجدول البنود
            $(document).off('input.productPicker', '.product-code-input').on('input.productPicker', '.product-code-input', function() {
                var $input = $(this);
                var query = $input.val().trim();
                var $row = $input.closest('.item-row');

                $input.removeClass('is-valid is-invalid');

                if (query === '') {
                    self.clearRowProductData($row);
                    return;
                }

                clearTimeout(self._lookupTimeout);
                self._lookupTimeout = setTimeout(function() {
                    self.performCodeLookup($row, $input, query);
                }, 300);
            });

            // 9. التحقق عند مغادرة حقل الباركود
            $(document).off('blur.productPicker', '.product-code-input').on('blur.productPicker', '.product-code-input', function() {
                var $input = $(this);
                var query = $input.val().trim();
                var $row = $input.closest('.item-row');

                if (query !== '' && !$input.hasClass('is-valid')) {
                    self.performCodeLookup($row, $input, query, true);
                }
            });

            // 10. تفريغ البنود عند تغيير المخزن
            $(document).off('change.productPicker', '#id_warehouse').on('change.productPicker', '#id_warehouse', function() {
                var firstRow = $('#items-container .item-row:first');
                $('#items-container .item-row:not(:first)').remove();
                self.clearRowProductData(firstRow);
                self.syncCurrencyLock();
                if (typeof window.calculateTotals === 'function') {
                    window.calculateTotals();
                }
            });

            // 11. إغلاق قائمة البحث السريعة المنسدلة عند النقر خارجها
            $(document).off('click.productPickerDismissCodeDropdown').on('click.productPickerDismissCodeDropdown', function(e) {
                if (!$(e.target).closest('.code-lookup-wrapper').length) {
                    $('.code-lookup-dropdown').remove();
                }
            });

            // 12. الاستماع لتغيير العملة وإدارة القفل والتحديث الديناميكي
            $(document).off('change.productPickerCurrency', '#id_currency').on('change.productPickerCurrency', '#id_currency', function() {
                var $curr = $(this);
                var newCurrencyId = $curr.val();
                
                var hasRowsWithProducts = false;
                $('#items-container .product-id-input').each(function() {
                    if ($(this).val()) {
                        hasRowsWithProducts = true;
                        return false;
                    }
                });

                if (hasRowsWithProducts) {
                    var msg = 'لا يمكن تغيير العملة أثناء وجود بنود في الجدول. يرجى مسح كافة البنود أولاً لتمكين تغيير العملة.';
                    if (typeof toastr !== 'undefined') {
                        toastr.warning(msg);
                    } else {
                        alert(msg);
                    }
                    var prevVal = $curr.data('previous-val') || '';
                    if (prevVal) {
                        $curr.val(prevVal).trigger('change.select2');
                    }
                    return false;
                }

                $curr.data('previous-val', newCurrencyId);

                var $opt = $curr.find('option:selected');
                var symbol = $opt.data('symbol') || $opt.data('code') || 'ج.م';
                var isFunctional = $opt.data('is-functional') === true || $opt.data('is-functional') === "true";
                var rate = parseFloat($opt.data('rate')) || 1.0;

                self.options.currencySymbol = symbol;
                $('.item-total').next('.input-group-text').text(symbol);
                $('#id_discount_type option[value="fixed"], select[name="discount_type"] option[value="fixed"]').text(symbol);
                $('#exchange_rate_container').toggleClass('d-none', isFunctional);
                $('#id_exchange_rate').val(rate.toFixed(6));

                if (typeof window.calculateTotals === 'function') {
                    window.calculateTotals();
                }
            });
        },

        // تنفيذ طلب البحث المباشر والقائمة السريعة بالكود / الباركود
        performCodeLookup: function($row, $input, query, isBlur, isExactRequest) {
            var self = this;
            var warehouseId = self.options.getWarehouseId();
            var invoiceId = self.options.getInvoiceId();
            var currencyId = $('#id_currency').val() || '';
            var lookupType = (self.options.type === 'purchase') ? 'purchase' : 'sale';

            // إغلاق أي قائمة سريعة سابقة
            $('.code-lookup-dropdown').remove();

            if (query.length < 2 && !isExactRequest) {
                return;
            }

            $.ajax({
                url: '/products/api/invoice-product-lookup/',
                method: 'GET',
                data: {
                    q: query,
                    exact: isExactRequest ? 'true' : 'false',
                    show_all: 'true',
                    warehouse_id: warehouseId,
                    invoice_id: invoiceId,
                    currency_id: currencyId,
                    type: lookupType
                },
                success: function(response) {
                    var products = response.products || [];

                    if (products.length === 0) {
                        if (isBlur) {
                            $input.addClass('is-invalid');
                            if (typeof toastr !== 'undefined') {
                                toastr.warning('كود المنتج غير صحيح أو غير متوفر في هذا المخزن');
                            }
                        }
                        return;
                    }

                    // في حالة التطابق التام أو الضغط الصريح على Enter (أو نتيجة واحدة مطابقة تماماً)
                    var exactMatch = products.find(function(p) {
                        return (p.code && p.code.toLowerCase() === query.toLowerCase()) ||
                               (p.barcode && p.barcode.toLowerCase() === query.toLowerCase());
                    });

                    if (isExactRequest && exactMatch) {
                        var price = self.resolveProductPrice(exactMatch);
                        var product = {
                            id: exactMatch.id,
                            name: exactMatch.name,
                            code: exactMatch.code || exactMatch.sku || query,
                            price: price,
                            stock: exactMatch.stock,
                            is_service: exactMatch.is_service === true || exactMatch.is_service === "true"
                        };

                        $input.removeClass('is-invalid').addClass('is-valid');
                        self.applyProductToRow($row, product, 'input');
                        return;
                    }

                    // إظهار قائمة البحث السريعة المنسدلة تحت حقل الكود
                    var $parent = $input.parent();
                    if (!$parent.hasClass('code-lookup-wrapper')) {
                        $parent.addClass('code-lookup-wrapper');
                    }

                    var $dropdown = $('<ul class="code-lookup-dropdown"></ul>');
                    products.slice(0, 8).forEach(function(p, idx) {
                        var price = self.resolveProductPrice(p);
                        var displayPrice = typeof smartFloat === 'function' ? smartFloat(price) : price;
                        var activeClass = (idx === 0) ? ' active' : '';
                        var $item = $('<li class="code-lookup-item' + activeClass + '" ' +
                            'data-id="' + p.id + '" ' +
                            'data-name="' + p.name + '" ' +
                            'data-code="' + (p.code || p.sku || '') + '" ' +
                            'data-price="' + price + '" ' +
                            'data-stock="' + p.stock + '" ' +
                            'data-is-service="' + p.is_service + '">' +
                            '<div><span class="code-badge">' + (p.code || p.sku || 'بدون كود') + '</span> <strong class="ms-1">' + p.name + '</strong></div>' +
                            '<span class="badge bg-light text-dark border">' + displayPrice + ' ' + self.options.currencySymbol + '</span>' +
                            '</li>');
                        $dropdown.append($item);
                    });

                    $parent.append($dropdown);

                    // تفعيل العنصر الممر عليه بالماوس لمزامنة الماوس مع لوحة المفاتيح
                    $dropdown.find('.code-lookup-item').on('mouseenter', function() {
                        $dropdown.find('.code-lookup-item').removeClass('active');
                        $(this).addClass('active');
                    });

                    // اختيار عنصر من القائمة السريعة عند النقر
                    $dropdown.find('.code-lookup-item').on('mousedown click', function(e) {
                        e.preventDefault();
                        var $item = $(this);
                        var selectedProduct = {
                            id: $item.data('id'),
                            name: $item.data('name'),
                            code: $item.data('code'),
                            price: $item.data('price'),
                            stock: parseFloat($item.data('stock') || 0),
                            is_service: $item.data('is-service') === true || $item.data('is-service') === "true"
                        };

                        $input.removeClass('is-invalid');
                        self.applyProductToRow($row, selectedProduct, 'input');
                        $dropdown.remove();

                        setTimeout(function() {
                            var $qtyInput = $row.find('.quantity');
                            if ($qtyInput.length) $qtyInput.focus().select();
                        }, 100);
                    });
                }
            });
        },

        // تطبيق المنتج المختار على الصف
        applyProductToRow: function($row, product, matchType) {
            var self = this;
            $row.find('.product-picker-btn').html('<span class="selected-text">' + product.name + '</span><i class="fas fa-th-large text-muted small"></i>');
            var $codeInput = $row.find('.product-code-input');
            $codeInput.val(product.code);
            if (matchType === 'input' || matchType === 'scan') {
                $codeInput.removeClass('is-invalid').addClass('is-valid');
            } else {
                $codeInput.removeClass('is-valid is-invalid');
            }
            
            var $idInput = $row.find('.product-id-input');
            $idInput.val(product.id)
                .attr('data-price', product.price)
                .attr('data-stock', product.stock)
                .attr('data-is-service', product.is_service);

            $row.find('.unit-price').val(product.price !== '' && product.price !== undefined ? (typeof smartFloat === 'function' ? smartFloat(product.price) : product.price) : '');

            var isService = product.is_service === true || product.is_service === 'true' || product.is_service === 1;
            self.renderStockState($row, {
                stock: product.stock,
                is_service: isService,
                quantity: parseFloat($row.find('.quantity').val()) || 1
            }, self.options.type);

            if (typeof self.options.onProductSelect === 'function') {
                self.options.onProductSelect($row, product, matchType);
            } else {
                if (typeof window.calculateRowTotal === 'function') {
                    window.calculateRowTotal($row);
                }
            }
        },

        // مسح بيانات الصف عند تفريغ البند
        clearRowProductData: function($row) {
            $row.find('.product-picker-btn').html('<span class="placeholder-text">اختر المنتج</span><i class="fas fa-th-large text-muted small"></i>');
            $row.find('.product-id-input').val('').removeAttr('data-price data-stock data-is-service');
            $row.find('.product-code-input').removeClass('is-valid is-invalid').val('');
            $row.find('.unit-price').val('');
            this.renderStockState($row, null);
            if (typeof window.calculateRowTotal === 'function') {
                window.calculateRowTotal($row);
            }
        },

        // تنظيف وحجم الصف عند إضافة بند جديد
        resetRow: function($row) {
            this.clearRowProductData($row);
            $row.find('.quantity').val('1');
            $row.find('.item-discount').val('0');
            $row.find('.item-total').val('0');
        },

        // تحميل أجهزة ومحتويات المودال
        loadModalProducts: function() {
            var self = this;
            var warehouseId = self.options.getWarehouseId();
            var invoiceId = self.options.getInvoiceId();
            var showAll = $('#show-all-products').is(':checked');

            clearTimeout(self._modalSearchTimeout);
            self._modalSearchTimeout = setTimeout(function() {
                var $grid = $('#products-grid');
                $grid.html('<div class="no-results text-center py-5 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>جاري البحث...</div>');

                var lookupType = self._activeType;
                if (lookupType === 'all') {
                    lookupType = (self.options.type === 'purchase') ? 'purchase' : 'sale';
                }

                var currencyId = $('#id_currency').val() || '';

                $.ajax({
                    url: '/products/api/invoice-product-lookup/',
                    method: 'GET',
                    data: {
                        q: self._searchTerm,
                        exact: 'false',
                        warehouse_id: warehouseId,
                        invoice_id: invoiceId,
                        currency_id: currencyId,
                        type: lookupType,
                        show_all: showAll
                    },
                    success: function(response) {
                        var rawProducts = response.products || [];
                        var isForeign = response.is_foreign === true;
                        self.updateCategoryTabs(rawProducts);

                        var products = rawProducts;
                        if (self._activeCategory !== 'all') {
                            products = products.filter(function(p) {
                                return String(p.category_id) === String(self._activeCategory);
                            });
                        }

                        $grid.empty();
                        if (products.length === 0) {
                            $grid.html('<div class="no-results text-center py-5 text-muted"><i class="fas fa-box-open fa-2x mb-2 d-block"></i>لا توجد نتائج</div>');
                            return;
                        }

                        products.forEach(function(p) {
                            var price = (self.options.priceField === 'cost_price') ? p.cost_price : p.selling_price;
                            var isService = p.is_service === true || p.is_service === "true" || p.is_service === "True" || p.is_service === 1;
                            var stockClass = (!isService && p.stock <= 0) ? 'out-of-stock' : '';
                            var stockLabel = '';

                            if (isService) {
                                stockLabel = '<span class="product-stock text-success"><i class="fas fa-tools"></i> خدمة</span>';
                            } else {
                                stockLabel = p.stock <= 0
                                    ? '<span class="product-stock low-stock">غير متوفر</span>'
                                    : (p.stock <= 5
                                        ? '<span class="product-stock low-stock">مخزون: ' + p.stock + '</span>'
                                        : '<span class="product-stock">مخزون: ' + p.stock + '</span>');
                            }

                            var priceDisplayHtml = '';
                            if (p.price_source === 'NEW_PRICE' || (price <= 0 && p.price_source !== 'PRODUCT_CURRENCY_PRICE')) {
                                priceDisplayHtml = '<span class="product-price text-warning fw-normal" style="font-size: 0.85rem;">غير معرّف <span class="badge bg-secondary ms-1" style="font-size: 0.65rem;">NEW PRICE</span></span>';
                            } else {
                                var displayPrice = typeof smartFloat === 'function' ? smartFloat(price) : price;
                                var badgeHtml = (isForeign && p.price_source === 'PRODUCT_CURRENCY_PRICE') ? '<span class="badge bg-success ms-1" style="font-size: 0.65rem;">سعر معتمد</span>' : '';
                                priceDisplayHtml = '<span class="product-price">' + displayPrice + ' ' + self.options.currencySymbol + badgeHtml + '</span>';
                            }

                            var codeBadge = p.code ? '<div class="product-code text-muted small font-monospace mb-1" style="font-size: 0.75rem;"><i class="fas fa-barcode me-1 opacity-75"></i>' + p.code + '</div>' : '<div class="product-code text-muted small mb-1" style="font-size: 0.75rem;">&nbsp;</div>';
                            var $card = $('<div class="col-md-3 col-sm-4 col-6">' +
                                '<div class="product-card ' + stockClass + '" data-id="' + p.id + '" data-price="' + price + '" data-stock="' + p.stock + '" data-name="' + p.name + '" data-is-service="' + isService + '" data-code="' + (p.code || '') + '">' +
                                    '<div class="product-name">' + p.name + '</div>' +
                                    codeBadge +
                                    '<div class="product-footer">' +
                                        priceDisplayHtml +
                                        stockLabel +
                                    '</div>' +
                                '</div>' +
                            '</div>');
                            $grid.append($card);
                        });
                    }
                });
            }, 300);
        },

        // تحديث إظهار وتفعيل التبويبات حسب نتائج المنتجات المتاحة
        updateCategoryTabs: function(products) {
            var self = this;
            var $tabs = $('#categoryTabs');
            var catMap = {};
            (products || []).forEach(function(p) {
                if (p.category_id && p.category_name) {
                    catMap[String(p.category_id)] = p.category_name;
                }
            });

            // إضافة التبويبات المفقودة ديناميكياً في حالة عدم وجودها مسبقاً في القالب
            Object.keys(catMap).forEach(function(catId) {
                if ($tabs.find('.nav-link[data-category="' + catId + '"]').length === 0) {
                    var $li = $('<li class="nav-item" role="presentation">' +
                        '<a class="nav-link btn-sm" data-category="' + catId + '" href="javascript:void(0)">' + catMap[catId] + '</a>' +
                    '</li>');
                    $tabs.append($li);
                }
            });

            $tabs.find('.nav-link[data-category]').each(function() {
                var $tab = $(this);
                var catId = String($tab.data('category'));
                if (catId === 'all') {
                    $tab.parent().show();
                    return;
                }
                if (catMap[catId]) {
                    $tab.parent().show();
                } else {
                    $tab.parent().hide();
                    if ($tab.hasClass('active')) {
                        $tab.removeClass('active');
                        $tabs.find('.nav-link[data-category="all"]').addClass('active');
                        self._activeCategory = 'all';
                    }
                }
            });
        },

        // الدالة المركزية لرسم وتحديث رصيد المخزون وحالة البند
        renderStockState: function($row, data, docType) {
            var $stockContainer = $row.find('.stock-info');
            var $headerRow = $row.find('.product-header-row');
            if (!$stockContainer.length) return;

            if (!data) {
                $stockContainer.empty().removeAttr('title');
                $headerRow.removeClass('has-stock-info');
                return;
            }

            var isService = data.is_service === true || data.is_service === 'true' || data.is_service === 1;
            if (isService) {
                $stockContainer.html('<span class="text-success small"><i class="fas fa-tools"></i> خدمة</span>')
                               .attr('title', 'صنف خدمي - لا يتطلب مخزون');
                $headerRow.addClass('has-stock-info');
                return;
            }

            var stock = parseInt(data.stock !== undefined ? data.stock : 0);
            if (isNaN(stock)) stock = 0;
            var qty = parseFloat(data.quantity !== undefined ? data.quantity : ($row.find('.quantity').val() || 0));
            if (isNaN(qty)) qty = 0;

            if (stock <= 0) {
                $stockContainer.html('<span class="stock-warning">لا يوجد مخزون</span>')
                               .attr('title', 'الرصيد المتاح حالياً هو 0');
            } else if (qty > stock) {
                $stockContainer.html('<span class="stock-warning">الكمية أكبر من المخزون المتاح (' + stock + ')</span>')
                               .attr('title', 'الكمية المطلوبة (' + qty + ') أكبر من المخزون المتاح (' + stock + ')');
            } else if (stock <= 5) {
                $stockContainer.html('<span class="stock-warning">المخزون المتاح: ' + stock + ' (منخفض)</span>')
                               .attr('title', 'المخزون المتاح: ' + stock + ' (وصل لحد إعادة الطلب)');
            } else {
                $stockContainer.html('المخزون المتاح: ' + stock)
                               .attr('title', 'المخزون المتاح: ' + stock);
            }
            $headerRow.addClass('has-stock-info');
        },

        // متوافقة مع الاستدعاءات السابقة
        renderStockInfo: function($row, stock) {
            var $idInput = $row.find('.product-id-input');
            var isService = $idInput.attr('data-is-service') === 'true' || 
                            $idInput.attr('data-is-service') === true || 
                            $idInput.data('is-service') === true ||
                            $idInput.data('is-service') === 'true';
            var qty = parseFloat($row.find('.quantity').val()) || 1;
            var docType = this.options ? this.options.type : 'sale';
            this.renderStockState($row, { stock: stock, is_service: isService, quantity: qty }, docType);
        },

        // طلب تجمعي واحد لتحميل أرصدة المخزون للبنود القديمة عند فتح الصفحة
        loadInitialStock: function() {
            var self = this;
            var warehouseId = self.options.getWarehouseId();
            var invoiceId = self.options.getInvoiceId();
            var productIds = [];

            $('#items-container .product-id-input').each(function() {
                var val = $(this).val();
                if (val) productIds.push(val);
            });

            if (productIds.length === 0) return;

            var lookupType = (self.options.type === 'purchase') ? 'purchase' : 'sale';
            $.ajax({
                url: '/products/api/invoice-product-lookup/',
                method: 'GET',
                data: {
                    product_ids: productIds.join(','),
                    warehouse_id: warehouseId,
                    invoice_id: invoiceId,
                    type: lookupType
                },
                success: function(response) {
                    var products = response.products || [];
                    products.forEach(function(p) {
                        var $row = $('#items-container .product-id-input[value="' + p.id + '"]').closest('.item-row');
                        var price = (self.options.priceField === 'cost_price') ? p.cost_price : p.selling_price;
                        $row.find('.product-id-input')
                            .attr('data-price', price)
                            .attr('data-stock', p.stock)
                            .attr('data-is-service', p.is_service);
                        $row.find('.product-code-input').val(p.code);

                        var isService = p.is_service === true || p.is_service === 'true' || p.is_service === 1;
                        self.renderStockState($row, {
                            stock: p.stock,
                            is_service: isService,
                            quantity: parseFloat($row.find('.quantity').val()) || 1
                        }, lookupType);
                    });
                }
            });
        }
    };

    // تصدير دالة renderStockState و renderStockInfo و ProductPicker عالمياً
    window.renderStockState = function($row, data, docType) {
        ProductPicker.renderStockState($row, data, docType);
    };

    window.renderStockInfo = function($row, stock) {
        ProductPicker.renderStockInfo($row, stock);
    };

    window.ProductPicker = ProductPicker;
})(window, jQuery);
