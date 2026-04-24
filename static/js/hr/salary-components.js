/**
 * إدارة مكونات الراتب (المستحقات والاستقطاعات)
 */

class SalaryComponentManager {
    constructor() {
        // حساب آخر counter من الصفوف الموجودة
        this.earningsCounter = this.getMaxCounter('#earnings-body');
        this.deductionsCounter = this.getMaxCounter('#deductions-body');
        this.variables = {
            'basic': 'الراتب الأساسي',
            'total_earnings': 'إجمالي المستحقات',
            'total_deductions': 'إجمالي الاستقطاعات'
        };
        this.init();
    }
    
    getMaxCounter(tbody) {
        let maxCounter = 0;
        $(tbody).find('tr').each(function() {
            const dataId = parseInt($(this).attr('data-id')) || 0;
            if (dataId > maxCounter) {
                maxCounter = dataId;
            }
        });
        return maxCounter;
    }
    
    init() {
        // إزالة event listeners القديمة أولاً لمنع التكرار
        $('#add-earning').off('click.salaryManager');
        $('#add-deduction').off('click.salaryManager');
        
        // إضافة مستحق
        $('#add-earning').on('click.salaryManager', () => this.addRow('earning'));
        
        // إضافة استقطاع
        $('#add-deduction').on('click.salaryManager', () => this.addRow('deduction'));
        
        // حذف صف (مع namespace لمنع التكرار)
        $(document).off('click.salaryManager', '.remove-component-row');
        $(document).on('click.salaryManager', '.remove-component-row', function() {
            $(this).closest('tr').fadeOut(300, function() {
                $(this).remove();
            });
        });
        
        // تفعيل Sortable
        this.initSortable();
        
        // حساب الإجمالي عند تغيير المبالغ
        $(document).off('input.salaryManager', '.component-amount');
        $(document).on('input.salaryManager', '.component-amount', () => this.calculateTotals());
        
        // حساب من الصيغة
        $(document).off('blur.salaryManager', '.component-formula');
        $(document).on('blur.salaryManager', '.component-formula', (e) => this.calculateFromFormula(e.target));
        
        // قفل/فتح حقل المبلغ حسب الصيغة
        $(document).off('input.salaryManager', '.component-formula');
        $(document).on('input.salaryManager', '.component-formula', (e) => this.toggleAmountField(e.target));
        
        // تحميل القوالب عند فتح المودال
        $('#earningTemplatesModal').off('show.bs.modal.salaryManager');
        $('#deductionTemplatesModal').off('show.bs.modal.salaryManager');
        $('#earningTemplatesModal').on('show.bs.modal.salaryManager', () => this.loadTemplates('earning'));
        $('#deductionTemplatesModal').on('show.bs.modal.salaryManager', () => this.loadTemplates('deduction'));
        
        // إضافة قالب عند النقر
        $(document).off('click.salaryManager', '.template-item');
        $(document).on('click.salaryManager', '.template-item', (e) => this.addFromTemplate(e));
        
        // Validation والـ Preview للصيغة
        $(document).off('input.salaryManagerValidation', '.component-formula');
        $(document).on('input.salaryManagerValidation', '.component-formula', (e) => this.validateAndPreviewFormula(e.target));
    }
    
    validateAndPreviewFormula(input) {
        const formula = $(input).val().trim();
        const wrapper = $(input).closest('.formula-input-wrapper');
        
        // إزالة الرسائل القديمة
        wrapper.find('.formula-preview, .formula-error').remove();
        
        if (!formula) return;
        
        try {
            // استبدال المتغيرات بقيم تجريبية للتحقق
            const basicSalary = parseFloat($('#id_basic_salary').val().replace(/,/g, '')) || 5000;
            let testFormula = formula
                .replace(/basic/g, basicSalary)
                .replace(/total_earnings/g, '10000')
                .replace(/total_deductions/g, '1000');
            
            // محاولة تقييم الصيغة
            const result = eval(testFormula);
            
            if (!isNaN(result) && isFinite(result)) {
                // صيغة صحيحة - عرض Preview
                const preview = this.getFormulaPreview(formula);
                const previewHtml = `
                    <small class="formula-preview text-success d-block mt-1">
                        <i class="fas fa-check-circle me-1"></i>
                        ${preview} = ${this.formatNumber(result)}
                    </small>
                `;
                $(input).after(previewHtml);
            }
        } catch (e) {
            // صيغة خاطئة - عرض خطأ
            const errorHtml = `
                <small class="formula-error text-danger d-block mt-1">
                    <i class="fas fa-exclamation-circle me-1"></i>
                    صيغة غير صحيحة
                </small>
            `;
            $(input).after(errorHtml);
        }
    }
    
    getFormulaPreview(formula) {
        // تحويل الصيغة لعربي مقروء
        let preview = formula
            .replace(/basic/g, 'الراتب الأساسي')
            .replace(/total_earnings/g, 'إجمالي المستحقات')
            .replace(/total_deductions/g, 'إجمالي الاستقطاعات')
            .replace(/\*/g, ' × ')
            .replace(/\+/g, ' + ')
            .replace(/\-/g, ' − ')
            .replace(/\//g, ' ÷ ');
        return preview;
    }
    
    addRow(type) {
        const counter = type === 'earning' ? ++this.earningsCounter : ++this.deductionsCounter;
        const tbody = type === 'earning' ? '#earnings-body' : '#deductions-body';
        const prefix = type === 'earning' ? 'earning' : 'deduction';
        
        const row = `
            <tr data-id="${counter}" data-type="${type}">
                <td class="text-center drag-handle" style="cursor: move;">
                    <i class="fas fa-grip-vertical text-muted"></i>
                </td>
                <td>
                    <input type="text" 
                           class="form-control form-control-sm" 
                           name="${prefix}_name_${counter}" 
                           placeholder="اسم البند" 
                           required>
                    <input type="hidden" name="${prefix}_id_${counter}" value="">
                    <input type="hidden" name="${prefix}_type_${counter}" value="${type}">
                    <input type="hidden" name="${prefix}_order_${counter}" value="${counter}" class="order-input">
                </td>
                <td>
                    <div class="formula-input-wrapper">
                        <button type="button" class="formula-variables-btn" title="إضافة متغير">
                            <i class="fas fa-tag"></i>
                        </button>
                        <input type="text" 
                               class="form-control form-control-sm component-formula" 
                               name="${prefix}_formula_${counter}" 
                               placeholder="مثال: basic * 0.25"
                               data-counter="${counter}"
                               data-type="${type}">
                        <div class="variables-dropdown" style="display: none;">
                            <div class="variables-list">
                                <div class="variable-item" data-value="basic">
                                    <strong>basic</strong>
                                    <small>الراتب الأساسي</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </td>
                <td>
                    <input type="text" 
                           class="form-control form-control-sm component-amount smart-float" 
                           name="${prefix}_amount_${counter}" 
                           placeholder="0.00" 
                           required>
                </td>
                <td class="text-center">
                    <button type="button" class="btn btn-sm btn-danger remove-component-row">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
        
        $(tbody).append(row);
        this.updateOrder(tbody);
    }
    
    initSortable() {
        const self = this;
        
        $('#earnings-body, #deductions-body').sortable({
            handle: '.drag-handle',
            items: 'tr:not(.basic-row)',
            placeholder: 'sortable-placeholder',
            axis: 'y',
            cursor: 'move',
            update: function(event, ui) {
                self.updateOrder(this);
            }
        });
    }
    
    updateOrder(tbody) {
        $(tbody).find('tr').each((index, row) => {
            $(row).find('.order-input').val(index);
        });
    }
    
    toggleAmountField(input) {
        const formula = $(input).val().trim();
        const counter = $(input).data('counter');
        const type = $(input).data('type');
        const prefix = type === 'earning' ? 'earning' : 'deduction';
        const amountField = $(`input[name="${prefix}_amount_${counter}"]`);
        
        if (formula) {
            // إذا كانت هناك صيغة، قفل حقل المبلغ
            amountField.prop('readonly', true)
                .css('background-color', '#e9ecef')
                .attr('placeholder', 'محسوب تلقائياً');
        } else {
            // إذا لم تكن هناك صيغة، فتح حقل المبلغ
            amountField.prop('readonly', false)
                .css('background-color', '')
                .attr('placeholder', '0.00');
        }
    }
    
    calculateFromFormula(input) {
        const formula = $(input).val().trim();
        if (!formula) {
            // إذا تم مسح الصيغة، فتح حقل المبلغ
            this.toggleAmountField(input);
            return;
        }
        
        // تحويل القيمة من smart-float (إزالة الفواصل)
        const basicSalaryStr = $('#id_basic_salary').val().replace(/,/g, '');
        const basicSalary = parseFloat(basicSalaryStr) || 0;
        const counter = $(input).data('counter');
        const type = $(input).data('type');
        const prefix = type === 'earning' ? 'earning' : 'deduction';
        
        try {
            // استبدال basic بالراتب الأساسي
            const calculatedFormula = formula.replace(/basic/g, basicSalary);
            const result = eval(calculatedFormula);
            
            if (!isNaN(result) && isFinite(result)) {
                // تنسيق النتيجة حسب نوع الرقم
                let formattedResult;
                if (result === Math.floor(result)) {
                    // رقم صحيح بدون علامة عشرية
                    formattedResult = result.toLocaleString('en-US');
                } else {
                    // رقم بكسور مع رقمين عشريين
                    formattedResult = result.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                }
                $(`input[name="${prefix}_amount_${counter}"]`).val(formattedResult);
                this.calculateTotals();
            }
        } catch (e) {
            console.error('خطأ في الصيغة الحسابية:', e);
        }
    }
    
    calculateTotals() {
        // تحويل القيمة من smart-float (إزالة الفواصل)
        const basicSalaryStr = $('#id_basic_salary').val().replace(/,/g, '');
        const basicSalary = parseFloat(basicSalaryStr) || 0;
        
        // حساب إجمالي المستحقات
        let totalEarnings = basicSalary;
        $('#earnings-body .component-amount').each(function() {
            const valueStr = $(this).val().replace(/,/g, '');
            totalEarnings += parseFloat(valueStr) || 0;
        });
        
        // حساب إجمالي الاستقطاعات
        let totalDeductions = 0;
        $('#deductions-body .component-amount').each(function() {
            const valueStr = $(this).val().replace(/,/g, '');
            totalDeductions += parseFloat(valueStr) || 0;
        });
        
        // الصافي
        const netSalary = totalEarnings - totalDeductions;
        
        // عرض النتائج بتنسيق الأرقام
        $('#total-earnings').text(this.formatNumber(totalEarnings));
        $('#total-deductions').text(this.formatNumber(totalDeductions));
        $('#net-salary').text(this.formatNumber(netSalary));
    }
    
    formatNumber(num) {
        // تنسيق الرقم بالفواصل
        // إذا كان الرقم صحيح، بدون علامة عشرية
        if (num === Math.floor(num)) {
            return num.toLocaleString('en-US');
        } else {
            // إذا كان فيه كسور، نعرض رقمين عشريين
            return num.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
    }
    
    loadTemplates(type) {
        const listId = type === 'earning' ? '#earning-templates-list' : '#deduction-templates-list';
        
        // عرض loader
        $(listId).html(`
            <div class="text-center py-3">
                <div class="spinner-border text-${type === 'earning' ? 'success' : 'danger'}" role="status">
                    <span class="visually-hidden">جاري التحميل...</span>
                </div>
            </div>
        `);
        
        // جلب القوالب
        $.get(`/hr/api/salary-templates/?type=${type}`, (response) => {
            if (response.success && response.templates.length > 0) {
                $(listId).empty();
                response.templates.forEach(template => {
                    const $item = $('<a>', {
                        href: '#',
                        class: 'list-group-item list-group-item-action template-item',
                        'data-type': type
                    }).data('template', template);
                    
                    const content = `
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <h6 class="mb-1">${template.name}</h6>
                                ${template.formula ? 
                                    `<small class="text-muted"><i class="fas fa-calculator me-1"></i>الصيغة: <code>${template.formula}</code></small>` : 
                                    `<small class="text-muted"><i class="fas fa-money-bill me-1"></i>المبلغ: ${template.default_amount} جنيه</small>`
                                }
                                ${template.description ? 
                                    `<br><small class="text-muted">${template.description}</small>` : ''
                                }
                            </div>
                            <i class="fas fa-plus-circle text-${type === 'earning' ? 'success' : 'danger'} fs-4"></i>
                        </div>
                    `;
                    
                    $item.html(content);
                    $(listId).append($item);
                });
            } else {
                $(listId).html(`
                    <div class="text-center py-4 text-muted">
                        <i class="fas fa-inbox fa-3x mb-3"></i>
                        <p>لا توجد قوالب متاحة</p>
                        <small>يمكنك إضافة قوالب من صفحة الإعدادات</small>
                    </div>
                `);
            }
        }).fail(() => {
            $(listId).html(`
                <div class="text-center py-4 text-danger">
                    <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
                    <p>حدث خطأ أثناء تحميل القوالب</p>
                </div>
            `);
        });
    }
    
    addFromTemplate(e) {
        e.preventDefault();
        const template = $(e.currentTarget).data('template');
        const type = $(e.currentTarget).data('type');
        
        // إضافة صف جديد
        const counter = type === 'earning' ? ++this.earningsCounter : ++this.deductionsCounter;
        const tbody = type === 'earning' ? '#earnings-body' : '#deductions-body';
        const prefix = type === 'earning' ? 'earning' : 'deduction';
        
        const row = `
            <tr data-id="${counter}" data-type="${type}">
                <td class="text-center drag-handle" style="cursor: move;">
                    <i class="fas fa-grip-vertical text-muted"></i>
                </td>
                <td>
                    <input type="text" class="form-control form-control-sm" 
                           name="${prefix}_name_${counter}" 
                           value="${template.name}"
                           placeholder="اسم البند" required>
                    <input type="hidden" name="${prefix}_type_${counter}" value="${type}">
                    <input type="hidden" name="${prefix}_order_${counter}" value="${counter}" class="order-input">
                </td>
                <td>
                    <div class="formula-input-wrapper">
                        <button type="button" class="formula-variables-btn" title="إضافة متغير">
                            <i class="fas fa-tag"></i>
                        </button>
                        <input type="text" class="form-control form-control-sm component-formula" 
                               name="${prefix}_formula_${counter}" 
                               value="${template.formula}"
                               placeholder="مثال: basic * 0.25"
                               data-counter="${counter}" data-type="${type}">
                        <div class="variables-dropdown" style="display: none;">
                            <div class="variables-list">
                                <div class="variable-item" data-value="basic">
                                    <strong>basic</strong>
                                    <small>الراتب الأساسي</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </td>
                <td>
                    <input type="text" class="form-control form-control-sm component-amount smart-float" 
                           name="${prefix}_amount_${counter}" 
                           value=""
                           placeholder="0.00" required>
                </td>
                <td class="text-center">
                    <button type="button" class="btn btn-sm btn-danger remove-component-row">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
        
        $(tbody).append(row);
        this.updateOrder(tbody);
        
        // تطبيق قفل/فتح حقل المبلغ
        const formulaInput = $(`input[name="${prefix}_formula_${counter}"]`);
        const amountInput = $(`input[name="${prefix}_amount_${counter}"]`);
        this.toggleAmountField(formulaInput[0]);
        
        // حساب المبلغ من الصيغة إذا وجدت
        if (template.formula) {
            this.calculateFromFormula(formulaInput[0]);
        } else {
            // إذا لم تكن هناك صيغة، تنسيق المبلغ الافتراضي
            const amount = parseFloat(template.default_amount);
            if (!isNaN(amount)) {
                if (amount === Math.floor(amount)) {
                    amountInput.val(amount.toLocaleString('en-US'));
                } else {
                    amountInput.val(amount.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
                }
            }
        }
        
        // إغلاق المودال
        $('.modal').modal('hide');
        
        // حساب الإجماليات
        this.calculateTotals();
    }
}

// تفعيل عند تحميل الصفحة
$(document).ready(function() {
    if ($('#earnings-body').length && !window.salaryManager) {
        window.salaryManager = new SalaryComponentManager();
        
        // حساب الإجمالي عند تغيير الراتب الأساسي
        $('#id_basic_salary').on('input', function() {
            window.salaryManager.calculateTotals();
            
            // إعادة حساب جميع الصيغ عند تغيير الراتب الأساسي
            $('.component-formula').each(function() {
                if ($(this).val().trim()) {
                    window.salaryManager.calculateFromFormula(this);
                }
            });
        });
        
        // تطبيق قفل/فتح الحقول الموجودة عند التحميل
        $('.component-formula').each(function() {
            window.salaryManager.toggleAmountField(this);
        });
        
        // حساب أولي
        window.salaryManager.calculateTotals();
    }
});

// Event handlers عامة للـ formula variables (تعمل في كل الصفحات)
$(document).ready(function() {
    // فتح/إغلاق قائمة المتغيرات
    $(document).on('click', '.formula-variables-btn', function(e) {
        e.preventDefault();
        e.stopPropagation();
        const dropdown = $(this).siblings('.variables-dropdown');
        
        // إغلاق القوائم الأخرى
        $('.variables-dropdown').not(dropdown).hide();
        
        // Toggle
        dropdown.toggle();
    });
    
    // اختيار متغير من القائمة
    $(document).on('click', '.variable-item', function() {
        const value = $(this).data('value');
        const wrapper = $(this).closest('.formula-input-wrapper');
        const formulaInput = wrapper.find('.component-formula');
        const currentValue = formulaInput.val();
        formulaInput.val(currentValue + value);
        formulaInput.focus();
        wrapper.find('.variables-dropdown').hide();
    });
    
    // إغلاق القائمة عند النقر خارجها
    $(document).on('click', function(e) {
        if (!$(e.target).closest('.formula-input-wrapper').length) {
            $('.variables-dropdown').hide();
        }
    });
});
