/**
 * حاسبة ساعات العمل للورديات
 * HR Shift Work Hours Calculator
 */

class ShiftCalculator {
    constructor() {
        this.init();
    }

    init() {
        this.bindEvents();
        this.setupUI();
        this.calculateInitial();
    }

    bindEvents() {
        // ربط أحداث تغيير الأوقات
        $('#id_start_time, #id_end_time').on('change blur keyup', () => {
            this.calculateWorkHours();
        });

        // ربط حدث تعديل ساعات العمل يدوياً
        $('#id_work_hours').on('input', () => {
            this.showManualEditMessage();
        });
    }

    setupUI() {
        // إضافة أيقونات للحقول
        this.addTimeIcons();
        
        // إضافة زر إعادة الحساب
        this.addRecalculateButton();
    }

    addTimeIcons() {
        $('#id_start_time, #id_end_time').parent().addClass('position-relative');
        $('#id_start_time, #id_end_time').css('padding-left', '35px');
        
    }

    addRecalculateButton() {
        const recalculateBtn = `
            <button type="button" class="btn btn-outline-info btn-sm mt-2" id="recalculate-btn">
                <i class="fas fa-sync-alt me-1"></i>
                إعادة حساب ساعات العمل
            </button>
        `;
        $('#id_work_hours').parent().append(recalculateBtn);
        
        $('#recalculate-btn').on('click', () => {
            this.handleRecalculate();
        });
    }

    calculateWorkHours() {
        const startTime = $('#id_start_time').val();
        const endTime = $('#id_end_time').val();
        
        if (startTime && endTime) {
            const start = this.timeToMinutes(startTime);
            let end = this.timeToMinutes(endTime);
            
            // التعامل مع الورديات الليلية
            if (end < start) {
                end += 24 * 60; // إضافة 24 ساعة بالدقائق
            }
            
            const diffMinutes = end - start;
            const hours = (diffMinutes / 60).toFixed(2);
            
            // تحديث الحقل
            $('#id_work_hours').val(hours);
            
            // إظهار المعاينة والرسائل
            this.showCalculationPreview(hours, startTime, endTime);
            this.showCalculationInfo(hours);
        } else {
            this.hideCalculationPreview();
            this.removeMessages();
        }
    }

    timeToMinutes(timeStr) {
        const [hours, minutes] = timeStr.split(':').map(Number);
        return hours * 60 + minutes;
    }

    showCalculationPreview(hours, startTime, endTime) {
        $('#preview-hours').text(hours);
        $('#calculation-preview').show();
        
        // إزالة أي معلومات إضافية سابقة
        $('#calculation-preview .mt-2').remove();
        
        // إضافة معلومات للورديات الليلية
        const isOvernight = this.timeToMinutes(endTime) < this.timeToMinutes(startTime);
        if (isOvernight) {
            $('#calculation-preview').append(
                '<div class="mt-2"><small class="text-warning"><i class="fas fa-moon me-1"></i>وردية ليلية (تمتد لليوم التالي)</small></div>'
            );
        }

        // إضافة معلومات إضافية
        this.addCalculationDetails(hours, startTime, endTime);
    }

    addCalculationDetails(hours, startTime, endTime) {
        const details = `
            <div class="mt-2">
                <small class="text-muted d-block">
                    <i class="fas fa-info-circle me-1"></i>
                    من ${startTime} إلى ${endTime}
                </small>
            </div>
        `;
        $('#calculation-preview').append(details);
    }

    hideCalculationPreview() {
        $('#calculation-preview').hide();
    }

    showCalculationInfo(hours) {
        this.removeMessages();
        
        const message = `<small class="text-success calculation-info d-block mt-1">
            <i class="fas fa-check-circle me-1"></i>
            تم حساب ${hours} ساعة عمل تلقائياً
        </small>`;
        
        $('#id_work_hours').after(message);
    }

    showManualEditMessage() {
        this.removeMessages();
        
        const message = `<small class="text-info calculation-info d-block mt-1">
            <i class="fas fa-edit me-1"></i>
            تم تعديل ساعات العمل يدوياً
        </small>`;
        
        $('#id_work_hours').after(message);
    }

    removeMessages() {
        $('.calculation-info').remove();
    }

    handleRecalculate() {
        const $btn = $('#recalculate-btn');
        
        // تعطيل الزر وإظهار حالة التحميل
        $btn.prop('disabled', true)
            .html('<i class="fas fa-spinner fa-spin me-1"></i>جاري الحساب...');
        
        setTimeout(() => {
            this.calculateWorkHours();
            
            // إظهار حالة النجاح
            $btn.prop('disabled', false)
                .removeClass('btn-outline-info')
                .addClass('btn-success')
                .html('<i class="fas fa-check me-1"></i>تم الحساب');
            
            // العودة للحالة الطبيعية
            setTimeout(() => {
                $btn.removeClass('btn-success')
                    .addClass('btn-outline-info')
                    .html('<i class="fas fa-sync-alt me-1"></i>إعادة حساب ساعات العمل');
            }, 2000);
        }, 500);
    }

    calculateInitial() {
        // حساب أولي إذا كانت القيم موجودة
        this.calculateWorkHours();
    }

    // دوال مساعدة للتحقق من صحة البيانات
    validateTimes(startTime, endTime) {
        if (!startTime || !endTime) {
            return { valid: false, message: 'يرجى إدخال أوقات البداية والنهاية' };
        }

        const start = this.timeToMinutes(startTime);
        const end = this.timeToMinutes(endTime);
        
        // التحقق من أن الوردية لا تزيد عن 24 ساعة
        let duration = end - start;
        if (duration < 0) {
            duration += 24 * 60;
        }
        
        if (duration > 24 * 60) {
            return { valid: false, message: 'لا يمكن أن تزيد الوردية عن 24 ساعة' };
        }

        if (duration < 30) {
            return { valid: false, message: 'يجب أن تكون الوردية 30 دقيقة على الأقل' };
        }

        return { valid: true };
    }

    // تنسيق الوقت للعرض
    formatTime(timeStr) {
        const [hours, minutes] = timeStr.split(':');
        const hour12 = hours % 12 || 12;
        const ampm = hours < 12 ? 'ص' : 'م';
        return `${hour12}:${minutes} ${ampm}`;
    }
}

// تهيئة الحاسبة عند تحميل الصفحة
$(document).ready(function() {
    if ($('#id_start_time').length && $('#id_end_time').length) {
        new ShiftCalculator();
    }
});