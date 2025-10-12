/**
 * pricing-calculator.js - دالات حساب التكلفة والتسعير
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة حسابات التسعير
PricingSystem.Pricing = {
    /**
     * تهيئة وحدة التسعير
     */
    init: function() {
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        } else {
            // استخدام الطريقة التقليدية
            this.setupTraditionalEventHandlers();
        }
    },
    
    /**
     * تسجيل معالجات الأحداث مع ناقل الأحداث
     */
    registerEventHandlers: function() {
        // الاستماع لأحداث تحديث التسعير
        PricingSystem.EventBus.on('pricing:update', (data) => {
            this.calculateCost();
        });
        
        // الاستماع لتغييرات حقول التسعير
        PricingSystem.EventBus.on('field:id_profit_margin:changed', (data) => {
            this.updateSellingPriceFromProfitMargin();
        });
        
        PricingSystem.EventBus.on('field:id_sale_price:changed', (data) => {
            this.updateProfitMarginFromSellingPrice();
        });
        
        // الاستماع لتغييرات حقول التصميم
        PricingSystem.EventBus.on('field:id_design_price:changed', (data) => {
            this.updateDesignCost();
        });
        
        PricingSystem.EventBus.on('field:id_internal_design_price:changed', (data) => {
            this.updateDesignCost();
        });
        
        // الاستماع لتغييرات حقول ضريبة القيمة المضافة
        PricingSystem.EventBus.on('field:id_vat_rate:changed', (data) => {
            this.updateFinalPrice();
        });
        
        // الاستماع لتغييرات الكمية لتحديث سعر الوحدة
        PricingSystem.EventBus.on('field:id_quantity:changed', (data) => {
            // تحديث سعر الوحدة عند تغيير الكمية
            const sellingPriceInput = document.getElementById('id_sale_price');
            if (sellingPriceInput) {
                const sellingPrice = parseFloat(sellingPriceInput.value) || 0;
                this.calculateUnitPrice(sellingPrice);
            }
        });
    },
    
    /**
     * إعداد معالجات الأحداث التقليدية (بدون ناقل الأحداث)
     */
    setupTraditionalEventHandlers: function() {
        // إضافة معالج حدث لتغيير نسبة الربح
        const profitMarginInput = document.getElementById('id_profit_margin');
        if (profitMarginInput) {
            profitMarginInput.addEventListener('input', this.updateSellingPriceFromProfitMargin.bind(this));
            profitMarginInput.addEventListener('change', this.updateSellingPriceFromProfitMargin.bind(this));
        }
        
        // إضافة معالج حدث لتغيير سعر البيع
        const sellingPriceInput = document.getElementById('id_sale_price');
        if (sellingPriceInput) {
            sellingPriceInput.addEventListener('input', this.updateProfitMarginFromSellingPrice.bind(this));
            sellingPriceInput.addEventListener('change', this.updateProfitMarginFromSellingPrice.bind(this));
        }
        
        // إضافة معالجات أحداث لحقول التصميم
        const designPriceInput = document.getElementById('id_design_price');
        if (designPriceInput) {
            designPriceInput.addEventListener('input', this.updateDesignCost.bind(this));
            designPriceInput.addEventListener('change', this.updateDesignCost.bind(this));
        }
        
        const internalDesignPriceInput = document.getElementById('id_internal_design_price');
        if (internalDesignPriceInput) {
            internalDesignPriceInput.addEventListener('input', this.updateDesignCost.bind(this));
            internalDesignPriceInput.addEventListener('change', this.updateDesignCost.bind(this));
        }
        
        // إضافة معالج حدث لتغيير معدل ضريبة القيمة المضافة
        const vatRateInput = document.getElementById('id_vat_rate');
        if (vatRateInput) {
            vatRateInput.addEventListener('input', this.updateFinalPrice.bind(this));
            vatRateInput.addEventListener('change', this.updateFinalPrice.bind(this));
        }
        
        // إضافة معالج حدث لتغيير الكمية لتحديث سعر الوحدة
        const quantityInput = document.getElementById('id_quantity');
        if (quantityInput) {
            quantityInput.addEventListener('input', () => {
                const sellingPriceInput = document.getElementById('id_sale_price');
                if (sellingPriceInput) {
                    const sellingPrice = parseFloat(sellingPriceInput.value) || 0;
                    this.calculateUnitPrice(sellingPrice);
                }
            });
            quantityInput.addEventListener('change', () => {
                const sellingPriceInput = document.getElementById('id_sale_price');
                if (sellingPriceInput) {
                    const sellingPrice = parseFloat(sellingPriceInput.value) || 0;
                    this.calculateUnitPrice(sellingPrice);
                }
            });
        }
    },
    
    /**
     * حساب التكلفة الإجمالية للمنتج
     */
    calculateCost: function() {
        try {
            // الحصول على جميع عناصر التكلفة
            const designCostInput = document.getElementById('id_design_price_summary');
            const paperCostInput = document.getElementById('id_material_cost');
            const platesCostInput = document.getElementById('id_plates_cost');
            const internalPlatesCostInput = document.getElementById('id_internal_plates_cost_summary');
            const pressCostInput = document.getElementById('id_press_cost_summary');
            const internalPressCostInput = document.getElementById('id_internal_press_cost_summary');
            const finishingCostInput = document.getElementById('id_finishing_cost');
            
            // الحصول على حقول الإخراج
            const totalCostInput = document.getElementById('total_cost');
            const profitMarginInput = document.getElementById('id_profit_margin');
            const profitAmountInput = document.getElementById('profit_amount');
            const salePriceInput = document.getElementById('id_sale_price');
            const pricePerPieceInput = document.getElementById('unit_price');
            
            // التحقق من وجود الحقول الضرورية
            if (!totalCostInput || !profitMarginInput || !profitAmountInput) {
                console.error('لا يمكن العثور على حقول التسعير المطلوبة');
                return;
            }
            
            // حساب إجمالي التكلفة
            let totalCost = 0;
            
            // إضافة تكلفة التصميم
            if (designCostInput && designCostInput.value) {
                totalCost += parseFloat(designCostInput.value) || 0;
            }
            
            // إضافة تكلفة الورق
            if (paperCostInput && paperCostInput.value) {
                totalCost += parseFloat(paperCostInput.value) || 0;
            }
            
            // إضافة تكلفة الزنكات (الغلاف)
            if (platesCostInput && platesCostInput.value) {
                totalCost += parseFloat(platesCostInput.value) || 0;
            }
            
            // إضافة تكلفة الزنكات (المحتوى الداخلي)
            if (internalPlatesCostInput && internalPlatesCostInput.value) {
                totalCost += parseFloat(internalPlatesCostInput.value) || 0;
            }
            
            // إضافة تكلفة الطباعة (الغلاف)
            if (pressCostInput && pressCostInput.value) {
                totalCost += parseFloat(pressCostInput.value) || 0;
            }
            
            // إضافة تكلفة الطباعة (المحتوى الداخلي)
            if (internalPressCostInput && internalPressCostInput.value) {
                totalCost += parseFloat(internalPressCostInput.value) || 0;
            }
            
            // إضافة تكلفة خدمات ما بعد الطباعة
            if (finishingCostInput && finishingCostInput.value) {
                totalCost += parseFloat(finishingCostInput.value) || 0;
            }
            
            // تحديث حقل إجمالي التكلفة
            totalCostInput.value = totalCost.toFixed(2);
            
            // حساب مبلغ الربح
            const profitMargin = parseFloat(profitMarginInput.value) || 0;
            const profitAmount = (totalCost * profitMargin) / 100;
            
            // تحديث حقل مبلغ الربح
            profitAmountInput.value = profitAmount.toFixed(2);
            
            // حساب السعر النهائي
            const finalPrice = totalCost + profitAmount;
            
            // تحديث سعر البيع
            if (salePriceInput) {
                salePriceInput.value = finalPrice.toFixed(2);
            }
            
            // حساب سعر الوحدة
            this.calculateUnitPrice(finalPrice);
            
            // تحديث ضريبة القيمة المضافة والسعر النهائي
            this.updateFinalPrice();
            
            // إطلاق حدث تحديث التكلفة الإجمالية عبر ناقل الأحداث
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.emit('cost:updated', { totalCost: totalCost });
            }
        } catch (error) {
            console.error('خطأ في حساب التكلفة:', error);
        }
    },
    
    /**
     * حساب سعر الوحدة
     * @param {number} finalPrice - السعر النهائي
     */
    calculateUnitPrice: function(finalPrice) {
        const quantityInput = document.getElementById('id_quantity');
        const unitPriceInput = document.getElementById('unit_price');
        
        if (!quantityInput || !unitPriceInput) {
            return;
        }
        
        const quantity = parseInt(quantityInput.value) || 1;
        
        // حساب سعر الوحدة
        const unitPrice = finalPrice / quantity;
        
        // تحديث حقل سعر الوحدة
        unitPriceInput.value = unitPrice.toFixed(2);
        
        // إطلاق حدث تحديث سعر الوحدة عبر ناقل الأحداث
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.fieldChanged('unit_price', unitPrice.toFixed(2), true);
        }
    },
    
    /**
     * الحصول على تكلفة التصميم
     * @returns {number} تكلفة التصميم
     */
    getDesignCost: function() {
        const designPriceSummary = document.getElementById('id_design_price_summary');
        return designPriceSummary ? parseFloat(designPriceSummary.value) || 0 : 0;
    },
    
    /**
     * الحصول على تكلفة الورق
     * @returns {number} تكلفة الورق
     */
    getPaperCost: function() {
        const paperCostSummary = document.getElementById('id_material_cost');
        return paperCostSummary ? parseFloat(paperCostSummary.value) || 0 : 0;
    },
    
    /**
     * الحصول على تكلفة الطباعة
     * @returns {number} تكلفة الطباعة
     */
    getPrintingCost: function() {
        const printingCostSummary = document.getElementById('id_printing_cost');
        return printingCostSummary ? parseFloat(printingCostSummary.value) || 0 : 0;
    },
    
    /**
     * الحصول على تكلفة ألواح الطباعة
     * @returns {number} تكلفة ألواح الطباعة
     */
    getPlatesCost: function() {
        const platesCostSummary = document.getElementById('id_plates_cost');
        return platesCostSummary ? parseFloat(platesCostSummary.value) || 0 : 0;
    },
    
    /**
     * الحصول على تكلفة خدمات ما بعد الطباعة
     * @returns {number} تكلفة خدمات ما بعد الطباعة
     */
    getFinishingCost: function() {
        const finishingCostSummary = document.getElementById('id_finishing_cost');
        return finishingCostSummary ? parseFloat(finishingCostSummary.value) || 0 : 0;
    },
    
    /**
     * تحديث تكلفة التصميم
     */
    updateDesignCost: function() {
        const designPriceInput = document.getElementById('id_design_price');
        const internalDesignPriceInput = document.getElementById('id_internal_design_price');
        const designPriceSummaryInput = document.getElementById('id_design_price_summary');
        
        if (!designPriceInput || !designPriceSummaryInput) {
            return;
        }
        
        // حساب إجمالي تكلفة التصميم (الغلاف + المحتوى الداخلي)
        const coverDesignCost = parseFloat(designPriceInput.value) || 0;
        const internalDesignCost = parseFloat(internalDesignPriceInput?.value) || 0;
        const totalDesignCost = coverDesignCost + internalDesignCost;
        
        // تحديث حقل إجمالي تكلفة التصميم في قسم التسعير
        designPriceSummaryInput.value = totalDesignCost.toFixed(2);
        
        // إطلاق حدث تغيير تكلفة التصميم عبر ناقل الأحداث
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.fieldChanged('id_design_price_summary', totalDesignCost.toFixed(2), true);
        } else {
            // تحديث إجمالي التكلفة
            this.calculateCost();
        }
    },
    
    /**
     * تحديث نسبة الربح تلقائيًا بناءً على سعر البيع المدخل
     */
    updateProfitMarginFromSellingPrice: function() {
        const totalCostInput = document.getElementById('total_cost');
        const sellingPriceInput = document.getElementById('id_sale_price');
        const profitMarginInput = document.getElementById('id_profit_margin');
        const profitAmountInput = document.getElementById('profit_amount');
        
        if (!totalCostInput || !sellingPriceInput || !profitMarginInput || !profitAmountInput) {
            return;
        }
        
        const totalCost = parseFloat(totalCostInput.value) || 0;
        const sellingPrice = parseFloat(sellingPriceInput.value) || 0;
        
        if (totalCost <= 0 || sellingPrice <= 0) {
            return;
        }
        
        // حساب نسبة الربح
        const profitMargin = ((sellingPrice - totalCost) / totalCost) * 100;
        
        // حساب مبلغ الربح
        const profitAmount = sellingPrice - totalCost;
        
        // تحديث حقول نسبة الربح ومبلغ الربح
        profitMarginInput.value = profitMargin.toFixed(2);
        profitAmountInput.value = profitAmount.toFixed(2);
        
        // إطلاق حدث تغيير نسبة الربح عبر ناقل الأحداث
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.fieldChanged('id_profit_margin', profitMargin.toFixed(2), false);
            PricingSystem.EventBus.fieldChanged('profit_amount', profitAmount.toFixed(2), false);
        }
        
        // حساب سعر الوحدة
        this.calculateUnitPrice(sellingPrice);
        
        // تحديث ضريبة القيمة المضافة والسعر النهائي
        this.updateFinalPrice();
    },
    
    /**
     * تحديث سعر البيع تلقائيًا بناءً على نسبة الربح المدخلة
     */
    updateSellingPriceFromProfitMargin: function() {
        const totalCostInput = document.getElementById('total_cost');
        const profitMarginInput = document.getElementById('id_profit_margin');
        const sellingPriceInput = document.getElementById('id_sale_price');
        const profitAmountInput = document.getElementById('profit_amount');
        
        if (!totalCostInput || !profitMarginInput || !sellingPriceInput || !profitAmountInput) {
            return;
        }
        
        const totalCost = parseFloat(totalCostInput.value) || 0;
        const profitMargin = parseFloat(profitMarginInput.value) || 0;
        
        if (totalCost <= 0) {
            return;
        }
        
        // حساب سعر البيع
        const sellingPrice = totalCost * (1 + profitMargin / 100);
        
        // حساب مبلغ الربح
        const profitAmount = sellingPrice - totalCost;
        
        // تحديث حقول سعر البيع ومبلغ الربح
        sellingPriceInput.value = sellingPrice.toFixed(2);
        profitAmountInput.value = profitAmount.toFixed(2);
        
        // إطلاق حدث تغيير سعر البيع عبر ناقل الأحداث
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.fieldChanged('id_sale_price', sellingPrice.toFixed(2), false);
            PricingSystem.EventBus.fieldChanged('profit_amount', profitAmount.toFixed(2), false);
        }
        
        // حساب سعر الوحدة
        this.calculateUnitPrice(sellingPrice);
        
        // تحديث ضريبة القيمة المضافة والسعر النهائي
        this.updateFinalPrice();
    },
    
    /**
     * دالة لتحديث مبلغ الربح عند تغيير نسبة الربح
     */
    updateProfitAmount: function() {
        const totalCostInput = document.getElementById('total_cost');
        const profitMarginInput = document.getElementById('id_profit_margin');
        const profitAmountInput = document.getElementById('profit_amount');
        
        if (!totalCostInput || !profitMarginInput || !profitAmountInput) {
            return;
        }
        
        const totalCost = parseFloat(totalCostInput.value) || 0;
        const profitMargin = parseFloat(profitMarginInput.value) || 0;
        
        // حساب مبلغ الربح
        const profitAmount = (totalCost * profitMargin) / 100;
        
        // تحديث حقل مبلغ الربح
        profitAmountInput.value = profitAmount.toFixed(2);
        
        // إطلاق حدث تغيير مبلغ الربح عبر ناقل الأحداث
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.fieldChanged('profit_amount', profitAmount.toFixed(2), false);
        }
        
        // تحديث السعر النهائي
        this.updateFinalPrice();
    },
    
    /**
     * دالة لتحديث نسبة الربح عند تغيير مبلغ الربح
     */
    updateProfitMargin: function() {
        const totalCostInput = document.getElementById('total_cost');
        const profitMarginInput = document.getElementById('id_profit_margin');
        const profitAmountInput = document.getElementById('profit_amount');
        
        if (!totalCostInput || !profitMarginInput || !profitAmountInput) {
            return;
        }
        
        const totalCost = parseFloat(totalCostInput.value) || 0;
        const profitAmount = parseFloat(profitAmountInput.value) || 0;
        
        // تجنب القسمة على صفر
        if (totalCost === 0) {
            profitMarginInput.value = '0.00';
            return;
        }
        
        // حساب نسبة الربح
        const profitMargin = (profitAmount / totalCost) * 100;
        
        // تحديث حقل نسبة الربح
        profitMarginInput.value = profitMargin.toFixed(2);
        
        // إطلاق حدث تغيير نسبة الربح عبر ناقل الأحداث
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.fieldChanged('id_profit_margin', profitMargin.toFixed(2), false);
        }
        
        // تحديث السعر النهائي
        this.updateFinalPrice();
    },
    
    /**
     * دالة لتحديث السعر النهائي
     */
    updateFinalPrice: function() {
        const totalCostInput = document.getElementById('total_cost');
        const profitAmountInput = document.getElementById('profit_amount');
        const finalPriceInput = document.getElementById('id_final_price');
        const pricePerPieceInput = document.getElementById('unit_price');
        const vatRateInput = document.getElementById('id_vat_rate');
        const vatAmountInput = document.getElementById('id_vat_amount');
        const finalPriceWithVatInput = document.getElementById('id_final_price_with_vat');
        const sellingPriceInput = document.getElementById('id_sale_price');
        
        if (!totalCostInput || !profitAmountInput || !sellingPriceInput) {
            return;
        }
        
        const totalCost = parseFloat(totalCostInput.value) || 0;
        const profitAmount = parseFloat(profitAmountInput.value) || 0;
        
        // حساب السعر النهائي
        const finalPrice = totalCost + profitAmount;
        
        // تحديث حقل سعر البيع
        sellingPriceInput.value = finalPrice.toFixed(2);
        
        // تحديث حقل السعر النهائي إذا كان موجودًا
        if (finalPriceInput) {
            finalPriceInput.value = finalPrice.toFixed(2);
        }
        
        // حساب السعر للقطعة الواحدة
        if (pricePerPieceInput) {
            const quantityInput = document.getElementById('id_quantity');
            if (quantityInput && quantityInput.value) {
                const quantity = parseInt(quantityInput.value) || 1;
                const pricePerPiece = finalPrice / quantity;
                pricePerPieceInput.value = pricePerPiece.toFixed(2);
                
                // إطلاق حدث تغيير سعر الوحدة عبر ناقل الأحداث
                if (PricingSystem.EventBus) {
                    PricingSystem.EventBus.fieldChanged('unit_price', pricePerPiece.toFixed(2), false);
                }
            }
        }
        
        // حساب ضريبة القيمة المضافة
        if (vatRateInput && vatAmountInput && finalPriceWithVatInput) {
            const vatRate = parseFloat(vatRateInput.value) || 0;
            const vatAmount = (finalPrice * vatRate) / 100;
            const finalPriceWithVat = finalPrice + vatAmount;
            
            // تحديث حقول ضريبة القيمة المضافة
            vatAmountInput.value = vatAmount.toFixed(2);
            finalPriceWithVatInput.value = finalPriceWithVat.toFixed(2);
            
            // إطلاق أحداث تغيير ضريبة القيمة المضافة عبر ناقل الأحداث
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.fieldChanged('id_vat_amount', vatAmount.toFixed(2), false);
                PricingSystem.EventBus.fieldChanged('id_final_price_with_vat', finalPriceWithVat.toFixed(2), false);
            }
        }
    }
};