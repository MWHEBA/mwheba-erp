/**
 * ملف JavaScript للتعامل مع نموذج ماكينة الطباعة الأوفست
 */
document.addEventListener('DOMContentLoaded', function() {
    // سعر كسر التراج
    const enablePartialPriceCheckbox = document.getElementById('enable_partial_price');
    const partialPriceContainer = document.getElementById('partial_price_container');
    
    if (enablePartialPriceCheckbox && partialPriceContainer) {
        enablePartialPriceCheckbox.addEventListener('change', function() {
            partialPriceContainer.style.display = this.checked ? 'block' : 'none';
            if (!this.checked) {
                document.getElementById('id_partial_price').value = '';
            }
        });
        
        // تهيئة الحالة الأولية
        partialPriceContainer.style.display = enablePartialPriceCheckbox.checked ? 'block' : 'none';
    }
    
    // مصاريف تجهيز ثابتة
    const enableSetupCostCheckbox = document.getElementById('enable_setup_cost');
    const setupCostContainer = document.getElementById('setup_cost_container');
    
    if (enableSetupCostCheckbox && setupCostContainer) {
        enableSetupCostCheckbox.addEventListener('change', function() {
            setupCostContainer.style.display = this.checked ? 'block' : 'none';
            if (!this.checked) {
                document.getElementById('id_setup_cost').value = '';
            }
        });
        
        // تهيئة الحالة الأولية
        setupCostContainer.style.display = enableSetupCostCheckbox.checked ? 'block' : 'none';
    }
}); 