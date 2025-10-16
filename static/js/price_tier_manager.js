/**
 * نظام إدارة الشرائح السعرية الديناميكية
 * Price Tier Management System
 */

class PriceTierManager {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.tiers = [];
        this.tierCounter = 0;
        this.init();
    }

    init() {
        if (!this.container) {
            console.error('Price Tier Container not found');
            return;
        }
        
        this.render();
        this.attachGlobalEvents();
    }

    // إضافة شريحة جديدة
    addTier(tierData = null) {
        this.tierCounter++;
        
        const tier = tierData || {
            id: this.tierCounter,
            tier_name: '',
            min_quantity: '',
            max_quantity: '',
            price_per_unit: '',
            discount_percentage: 0,
            is_active: true
        };

        // التأكد من وجود ID فريد
        if (!tier.id) {
            tier.id = this.tierCounter;
        }

        this.tiers.push(tier);
        this.render();
        this.validateTiers();
        
        // التركيز على الحقل الأول في الشريحة الجديدة
        setTimeout(() => {
            const newTierElement = this.container.querySelector(`[data-tier-id="${tier.id}"]`);
            if (newTierElement) {
                const firstInput = newTierElement.querySelector('input');
                if (firstInput) firstInput.focus();
            }
        }, 100);

        return tier;
    }

    // حذف شريحة
    removeTier(tierId) {
        const tierIndex = this.tiers.findIndex(tier => tier.id == tierId);
        if (tierIndex > -1) {
            this.tiers.splice(tierIndex, 1);
            this.render();
            this.validateTiers();
        }
    }

    // تحديث بيانات الشريحة
    updateTier(tierId, field, value) {
        const tier = this.tiers.find(t => t.id == tierId);
        if (tier) {
            tier[field] = value;
            
            // تحديث اسم الشريحة تلقائياً
            if (field === 'min_quantity' || field === 'max_quantity') {
                this.updateTierName(tier);
            }
            
            this.validateTiers();
        }
    }

    // تحديث اسم الشريحة تلقائياً
    updateTierName(tier) {
        if (tier.min_quantity && !tier.tier_name) {
            if (tier.max_quantity) {
                tier.tier_name = `${tier.min_quantity} - ${tier.max_quantity}`;
            } else {
                tier.tier_name = `${tier.min_quantity}+`;
            }
            
            // تحديث الحقل في الواجهة
            const tierElement = this.container.querySelector(`[data-tier-id="${tier.id}"]`);
            if (tierElement) {
                const nameInput = tierElement.querySelector('input[name*="tier_name"]');
                if (nameInput) {
                    nameInput.value = tier.tier_name;
                }
            }
        }
    }

    // التحقق من صحة الشرائح
    validateTiers() {
        const errors = [];
        
        // ترتيب الشرائح حسب الحد الأدنى
        this.tiers.sort((a, b) => {
            const minA = parseInt(a.min_quantity) || 0;
            const minB = parseInt(b.min_quantity) || 0;
            return minA - minB;
        });

        // التحقق من التداخل
        for (let i = 0; i < this.tiers.length; i++) {
            const tier = this.tiers[i];
            const minQty = parseInt(tier.min_quantity) || 0;
            const maxQty = parseInt(tier.max_quantity) || null;

            // التحقق من الحد الأدنى
            if (minQty <= 0) {
                errors.push(`الشريحة ${i + 1}: الحد الأدنى يجب أن يكون أكبر من صفر`);
            }

            // التحقق من الحد الأقصى
            if (maxQty && maxQty <= minQty) {
                errors.push(`الشريحة ${i + 1}: الحد الأقصى يجب أن يكون أكبر من الحد الأدنى`);
            }

            // التحقق من السعر
            if (!tier.price_per_unit || parseFloat(tier.price_per_unit) <= 0) {
                errors.push(`الشريحة ${i + 1}: يجب إدخال سعر صحيح`);
            }

            // التحقق من التداخل مع الشريحة التالية
            if (i < this.tiers.length - 1) {
                const nextTier = this.tiers[i + 1];
                const nextMinQty = parseInt(nextTier.min_quantity) || 0;
                
                if (maxQty && maxQty >= nextMinQty) {
                    errors.push(`تداخل بين الشريحة ${i + 1} والشريحة ${i + 2}`);
                }
            }
        }

        this.displayValidationErrors(errors);
        return errors.length === 0;
    }

    // عرض أخطاء التحقق
    displayValidationErrors(errors) {
        let errorContainer = this.container.parentNode.querySelector('.tier-validation-errors');
        
        if (errors.length > 0) {
            if (!errorContainer) {
                errorContainer = document.createElement('div');
                errorContainer.className = 'alert alert-warning tier-validation-errors mt-2';
                this.container.parentNode.appendChild(errorContainer);
            }
            
            errorContainer.innerHTML = `
                <h6><i class="fas fa-exclamation-triangle me-2"></i>تحذيرات الشرائح السعرية:</h6>
                <ul class="mb-0">
                    ${errors.map(error => `<li>${error}</li>`).join('')}
                </ul>
            `;
        } else if (errorContainer) {
            errorContainer.remove();
        }
    }

    // عرض الشرائح
    render() {
        if (this.tiers.length === 0) {
            this.container.innerHTML = this.getEmptyState();
            return;
        }

        const tiersHtml = this.tiers.map(tier => this.createTierHTML(tier)).join('');
        this.container.innerHTML = tiersHtml;
        this.attachTierEvents();
    }

    // حالة فارغة
    getEmptyState() {
        return `
            <div class="text-center text-muted py-4">
                <i class="fas fa-layer-group fa-3x mb-3"></i>
                <h6>لا توجد شرائح سعرية</h6>
                <p class="mb-3">اضغط "إضافة شريحة" لإنشاء شريحة سعرية جديدة</p>
                <button type="button" class="btn btn-primary btn-sm" onclick="priceTierManager.addTier()">
                    <i class="fas fa-plus me-1"></i>إضافة أول شريحة
                </button>
            </div>
        `;
    }

    // إنشاء HTML للشريحة
    createTierHTML(tier) {
        return `
            <div class="price-tier-item" data-tier-id="${tier.id}">
                <div class="tier-header">
                    <span class="tier-number">#${tier.id}</span>
                    <button type="button" class="btn btn-sm btn-danger tier-remove-btn" 
                            onclick="priceTierManager.removeTier(${tier.id})" title="حذف الشريحة">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                
                <div class="row g-3">
                    <div class="col-md-3">
                        <div class="form-floating">
                            <input type="text" class="form-control" name="tier_name_${tier.id}" 
                                   placeholder="اسم الشريحة" value="${tier.tier_name || ''}"
                                   onchange="priceTierManager.updateTier(${tier.id}, 'tier_name', this.value)">
                            <label>اسم الشريحة</label>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="form-floating">
                            <input type="number" class="form-control" name="min_quantity_${tier.id}" 
                                   placeholder="من" min="1" value="${tier.min_quantity || ''}" required
                                   onchange="priceTierManager.updateTier(${tier.id}, 'min_quantity', this.value)">
                            <label>من (كمية) *</label>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="form-floating">
                            <input type="number" class="form-control" name="max_quantity_${tier.id}" 
                                   placeholder="إلى" min="1" value="${tier.max_quantity || ''}"
                                   onchange="priceTierManager.updateTier(${tier.id}, 'max_quantity', this.value)">
                            <label>إلى (كمية)</label>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="form-floating">
                            <input type="number" class="form-control" name="price_per_unit_${tier.id}" 
                                   placeholder="السعر" min="0" value="${tier.price_per_unit || ''}" required
                                   onchange="priceTierManager.updateTier(${tier.id}, 'price_per_unit', this.value)">
                            <label>سعر الوحدة *</label>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="form-floating">
                            <input type="number" class="form-control" name="discount_percentage_${tier.id}" 
                                   placeholder="الخصم" min="0" max="100" value="${tier.discount_percentage || 0}"
                                   onchange="priceTierManager.updateTier(${tier.id}, 'discount_percentage', this.value)">
                            <label>نسبة الخصم (%)</label>
                        </div>
                    </div>
                    <div class="col-md-1">
                        <div class="form-check form-switch mt-3">
                            <input class="form-check-input" type="checkbox" name="is_active_${tier.id}" 
                                   ${tier.is_active ? 'checked' : ''}
                                   onchange="priceTierManager.updateTier(${tier.id}, 'is_active', this.checked)">
                            <label class="form-check-label">نشط</label>
                        </div>
                    </div>
                </div>

                <div class="tier-preview mt-2">
                    <small class="text-muted">
                        ${this.getTierPreview(tier)}
                    </small>
                </div>
            </div>
        `;
    }

    // معاينة الشريحة
    getTierPreview(tier) {
        if (!tier.min_quantity || !tier.price_per_unit) {
            return 'أدخل الحد الأدنى والسعر لرؤية المعاينة';
        }

        const minQty = parseInt(tier.min_quantity);
        const maxQty = tier.max_quantity ? parseInt(tier.max_quantity) : null;
        const price = parseFloat(tier.price_per_unit);
        const discount = parseFloat(tier.discount_percentage) || 0;

        let range = maxQty ? `${minQty} - ${maxQty}` : `${minQty}+`;
        let discountText = discount > 0 ? ` (خصم ${discount}%)` : '';
        
        return `${range} قطعة = ${price.toFixed(2)} ج.م للوحدة${discountText}`;
    }

    // ربط الأحداث
    attachTierEvents() {
        // أحداث خاصة بكل شريحة
        this.container.querySelectorAll('.price-tier-item').forEach(tierElement => {
            const tierId = tierElement.dataset.tierId;
            
            // تحديث المعاينة عند تغيير القيم
            tierElement.querySelectorAll('input').forEach(input => {
                input.addEventListener('input', () => {
                    setTimeout(() => this.updateTierPreview(tierId), 100);
                });
            });
        });
    }

    // تحديث معاينة الشريحة
    updateTierPreview(tierId) {
        const tier = this.tiers.find(t => t.id == tierId);
        const tierElement = this.container.querySelector(`[data-tier-id="${tierId}"]`);
        
        if (tier && tierElement) {
            const previewElement = tierElement.querySelector('.tier-preview small');
            if (previewElement) {
                previewElement.textContent = this.getTierPreview(tier);
            }
        }
    }

    // ربط الأحداث العامة
    attachGlobalEvents() {
        // إضافة شريحة بـ Ctrl+Enter
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter' && document.activeElement.closest('#price-tiers-container')) {
                e.preventDefault();
                this.addTier();
            }
        });
    }

    // الحصول على بيانات الشرائح للحفظ
    getTiersData() {
        return this.tiers.filter(tier => 
            tier.min_quantity && 
            tier.price_per_unit && 
            parseFloat(tier.price_per_unit) > 0
        );
    }

    // تحميل شرائح موجودة
    loadTiers(tiersData) {
        this.tiers = [];
        this.tierCounter = 0;
        
        if (tiersData && tiersData.length > 0) {
            tiersData.forEach(tierData => {
                this.addTier(tierData);
            });
        }
        
        this.render();
    }

    // مسح جميع الشرائح
    clearAll() {
        if (this.tiers.length > 0) {
            if (confirm('هل أنت متأكد من حذف جميع الشرائح السعرية؟')) {
                this.tiers = [];
                this.tierCounter = 0;
                this.render();
            }
        }
    }

    // إضافة شرائح افتراضية
    addDefaultTiers() {
        const defaultTiers = [
            {
                tier_name: '1-20',
                min_quantity: 1,
                max_quantity: 20,
                price_per_unit: '',
                discount_percentage: 0
            },
            {
                tier_name: '21-100',
                min_quantity: 21,
                max_quantity: 100,
                price_per_unit: '',
                discount_percentage: 10
            },
            {
                tier_name: '101+',
                min_quantity: 101,
                max_quantity: null,
                price_per_unit: '',
                discount_percentage: 20
            }
        ];

        defaultTiers.forEach(tierData => {
            this.addTier(tierData);
        });
    }

    // حساب السعر لكمية معينة
    calculatePriceForQuantity(quantity) {
        const applicableTier = this.getApplicableTier(quantity);
        
        if (!applicableTier) {
            return null;
        }

        const basePrice = parseFloat(applicableTier.price_per_unit);
        const discount = parseFloat(applicableTier.discount_percentage) || 0;
        const finalPrice = basePrice * (1 - discount / 100);

        return {
            tier: applicableTier,
            basePrice: basePrice,
            discount: discount,
            finalPrice: finalPrice,
            totalCost: finalPrice * quantity,
            savings: (basePrice - finalPrice) * quantity
        };
    }

    // الحصول على الشريحة المناسبة لكمية معينة
    getApplicableTier(quantity) {
        for (const tier of this.tiers) {
            const minQty = parseInt(tier.min_quantity) || 0;
            const maxQty = tier.max_quantity ? parseInt(tier.max_quantity) : null;
            
            if (quantity >= minQty && (maxQty === null || quantity <= maxQty)) {
                return tier;
            }
        }
        return null;
    }
}

// إنشاء مثيل عام للاستخدام
let priceTierManager = null;

// تهيئة مدير الشرائح السعرية
function initializePriceTierManager(containerId = 'price-tiers-container') {
    priceTierManager = new PriceTierManager(containerId);
    return priceTierManager;
}

// دوال مساعدة للاستخدام في القوالب
function addPriceTier() {
    if (priceTierManager) {
        priceTierManager.addTier();
    }
}

function removePriceTier(tierId) {
    if (priceTierManager) {
        priceTierManager.removeTier(tierId);
    }
}

function clearAllTiers() {
    if (priceTierManager) {
        priceTierManager.clearAll();
    }
}

function addDefaultTiers() {
    if (priceTierManager) {
        priceTierManager.addDefaultTiers();
    }
}

// تصدير للاستخدام كوحدة
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { PriceTierManager, initializePriceTierManager };
}
