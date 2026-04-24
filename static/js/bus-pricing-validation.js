/**
 * Bus Pricing Validation JavaScript
 * Handles real-time validation and calculation for bus pricing forms
 */

class BusPricingValidator {
    constructor() {
        this.init();
    }

    init() {
        this.bindEvents();
        this.initializeValidation();
    }

    bindEvents() {
        // Real-time validation on input
        $(document).on('input', '.pricing-field', (e) => {
            this.validateField(e.target);
            this.updatePreview();
        });

        // Validation on blur
        $(document).on('blur', '.pricing-field', (e) => {
            this.validateField(e.target, true);
        });

        // Form submission validation
        $(document).on('submit', '.bus-form', (e) => {
            if (!this.validateForm()) {
                e.preventDefault();
                this.showValidationErrors();
            }
        });
    }

    validateField(field, showFeedback = false) {
        const $field = $(field);
        const value = parseFloat($field.val()) || 0;
        const fieldType = $field.data('field-type');
        
        // Clear previous validation
        $field.removeClass('is-valid is-invalid');
        $field.siblings('.invalid-feedback, .valid-feedback').remove();

        let isValid = true;
        let message = '';

        // Basic validation
        if ($field.prop('required') && value <= 0) {
            isValid = false;
            message = 'هذا الحقل مطلوب ويجب أن يكون أكبر من صفر';
        } else if (value > 0 && value > 10000) {
            isValid = false;
            message = 'القيمة مرتفعة جداً، يرجى التحقق';
        } else if (value > 0 && value < 1) {
            isValid = false;
            message = 'القيمة منخفضة جداً، يرجى التحقق';
        }

        // Cross-field validation
        if (isValid && fieldType === 'half_distance') {
            const fullDistanceValue = parseFloat($('.pricing-field[data-field-type="full_distance"]').val()) || 0;
            if (fullDistanceValue > 0 && value >= fullDistanceValue) {
                isValid = false;
                message = 'تكلفة نصف المسافة يجب أن تكون أقل من تكلفة المسافة الكاملة';
            }
        }

        return isValid;
    }

    validateForm() {
        let isValid = true;
        $('.pricing-field').each((index, field) => {
            if (!this.validateField(field, true)) {
                isValid = false;
            }
        });
        return isValid;
    }

    updatePreview() {
        const fullCost = parseFloat($('.pricing-field[data-field-type="full_distance"]').val()) || 0;
        const halfCost = parseFloat($('.pricing-field[data-field-type="half_distance"]').val()) || 0;

        // Update preview display
        $('#preview-full-cost').text(this.formatCurrency(fullCost));
        $('#preview-half-cost').text(this.formatCurrency(halfCost));

        // Calculate and display savings
        if (fullCost > 0 && halfCost > 0) {
            const savingsPercentage = ((fullCost - halfCost) / fullCost * 100).toFixed(1);
            $('#preview-savings').text(`${savingsPercentage}%`);
            
            // Show preview
            $('#pricing-preview').slideDown();
        } else {
            $('#pricing-preview').slideUp();
        }

        // Update comparison indicators
        this.updateComparisonIndicators(fullCost, halfCost);
    }

    updateComparisonIndicators(fullCost, halfCost) {
        const $indicators = $('.pricing-indicators');
        
        if (fullCost > 0 && halfCost > 0) {
            const ratio = halfCost / fullCost;
            let indicatorClass = '';
            let indicatorText = '';

            if (ratio <= 0.5) {
                indicatorClass = 'text-success';
                indicatorText = 'نسبة توفير ممتازة';
            } else if (ratio <= 0.7) {
                indicatorClass = 'text-info';
                indicatorText = 'نسبة توفير جيدة';
            } else if (ratio <= 0.9) {
                indicatorClass = 'text-warning';
                indicatorText = 'نسبة توفير قليلة';
            } else {
                indicatorClass = 'text-danger';
                indicatorText = 'لا توجد نسبة توفير';
            }

            $indicators.html(`<small class="${indicatorClass}"><i class="fas fa-info-circle me-1"></i>${indicatorText}</small>`);
        } else {
            $indicators.empty();
        }
    }

    initializeValidation() {
        // Initialize validation on page load
        $('.pricing-field').each((index, field) => {
            this.validateField(field);
        });
        this.updatePreview();
    }

    showValidationErrors() {
        // Scroll to first error
        const $firstError = $('.is-invalid').first();
        if ($firstError.length) {
            $('html, body').animate({
                scrollTop: $firstError.offset().top - 100
            }, 500);
        }

        // Show general error message
        this.showNotification('يرجى تصحيح الأخطاء في النموذج قبل الحفظ', 'error');
    }

    formatCurrency(amount) {
        if (amount === 0 || amount === null || amount === undefined) {
            return '0 ج.م';
        }
        return `${parseFloat(amount).toFixed(2)} ج.م`;
    }

    showNotification(message, type = 'info') {
        const alertClass = type === 'success' ? 'alert-success' : 
                          type === 'error' ? 'alert-danger' : 'alert-info';
        
        const notification = $(`
            <div class="alert ${alertClass} alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999; min-width: 300px;">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'} me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `);
        
        $('body').append(notification);
        
        setTimeout(() => {
            notification.alert('close');
        }, 5000);
    }

    // Method to get current pricing data
    getPricingData() {
        return {
            fullDistance: parseFloat($('.pricing-field[data-field-type="full_distance"]').val()) || 0,
            halfDistance: parseFloat($('.pricing-field[data-field-type="half_distance"]').val()) || 0,
            isValid: this.validateForm()
        };
    }

    // Method to set pricing data
    setPricingData(fullDistance, halfDistance) {
        $('.pricing-field[data-field-type="full_distance"]').val(fullDistance).trigger('input');
        $('.pricing-field[data-field-type="half_distance"]').val(halfDistance).trigger('input');
    }
}

// Initialize when document is ready
$(document).ready(function() {
    window.busPricingValidator = new BusPricingValidator();
});

// Export for use in other scripts
window.BusPricingValidator = BusPricingValidator;