/**
 * نظام التسعير المحسن - إعدادات النظام
 * Printing Pricing System - Configuration
 */

window.PrintingPricing = window.PrintingPricing || {};

PrintingPricing.Config = {
    // API Endpoints
    API: {
        BASE_URL: '/printing-pricing/api/',
        ENDPOINTS: {
            CALCULATE_COST: 'calculate-cost/',
            MATERIAL_PRICE: 'get-material-price/',
            SERVICE_PRICE: 'get-service-price/',
            VALIDATE_ORDER: 'validate-order/',
            ORDER_SUMMARY: 'order-summary/',
            ORDERS: 'orders/',
            MATERIALS: 'materials/',
            SERVICES: 'services/',
            CALCULATIONS: 'calculations/'
        }
    },

    // UI Settings
    UI: {
        ANIMATION_DURATION: 300,
        DEBOUNCE_DELAY: 500,
        TOAST_DURATION: 5000,
        MODAL_BACKDROP: true,
        RTL_SUPPORT: true
    },

    // Form Settings
    FORMS: {
        AUTO_SAVE: true,
        AUTO_SAVE_INTERVAL: 30000, // 30 seconds
        VALIDATION_ON_BLUR: true,
        SHOW_PROGRESS: true,
        CONFIRM_NAVIGATION: true
    },

    // Calculation Settings
    CALCULATIONS: {
        AUTO_CALCULATE: true,
        PRECISION: 2,
        CURRENCY: 'EGP',
        TAX_RATE: 0.14, // 14% VAT
        DISCOUNT_TYPES: ['percentage', 'fixed'],
        ROUNDING_METHOD: 'round' // 'round', 'ceil', 'floor'
    },

    // Validation Rules
    VALIDATION: {
        MIN_QUANTITY: 1,
        MAX_QUANTITY: 999999,
        MIN_PRICE: 0.01,
        MAX_PRICE: 999999.99,
        REQUIRED_FIELDS: ['customer', 'title', 'quantity', 'order_type']
    },

    // Messages
    MESSAGES: {
        SUCCESS: {
            ORDER_CREATED: 'تم إنشاء الطلب بنجاح',
            ORDER_UPDATED: 'تم تحديث الطلب بنجاح',
            ORDER_DELETED: 'تم حذف الطلب بنجاح',
            CALCULATION_COMPLETE: 'تم حساب التكلفة بنجاح',
            DATA_SAVED: 'تم حفظ البيانات بنجاح'
        },
        ERROR: {
            NETWORK_ERROR: 'خطأ في الاتصال بالخادم',
            VALIDATION_ERROR: 'يرجى تصحيح الأخطاء المحددة',
            CALCULATION_ERROR: 'خطأ في حساب التكلفة',
            SAVE_ERROR: 'خطأ في حفظ البيانات',
            LOAD_ERROR: 'خطأ في تحميل البيانات'
        },
        WARNING: {
            UNSAVED_CHANGES: 'لديك تغييرات غير محفوظة. هل تريد المتابعة؟',
            DELETE_CONFIRM: 'هل أنت متأكد من حذف هذا العنصر؟',
            CALCULATION_PENDING: 'جاري حساب التكلفة...'
        },
        INFO: {
            AUTO_SAVE: 'تم الحفظ التلقائي',
            LOADING: 'جاري التحميل...',
            PROCESSING: 'جاري المعالجة...'
        }
    },

    // Status Mappings
    STATUS: {
        DRAFT: 'draft',
        PENDING: 'pending',
        APPROVED: 'approved',
        REJECTED: 'rejected',
        COMPLETED: 'completed',
        CANCELLED: 'cancelled'
    },

    // Order Types
    ORDER_TYPES: {
        BOOK: 'book',
        MAGAZINE: 'magazine',
        BROCHURE: 'brochure',
        FLYER: 'flyer',
        POSTER: 'poster',
        BUSINESS_CARD: 'business_card',
        ENVELOPE: 'envelope',
        LETTERHEAD: 'letterhead',
        INVOICE: 'invoice',
        CATALOG: 'catalog',
        CALENDAR: 'calendar',
        NOTEBOOK: 'notebook',
        FOLDER: 'folder',
        BOX: 'box',
        LABEL: 'label',
        STICKER: 'sticker',
        BANNER: 'banner',
        OTHER: 'other'
    },

    // Material Types
    MATERIAL_TYPES: {
        PAPER: 'paper',
        CARDBOARD: 'cardboard',
        PLASTIC: 'plastic',
        FABRIC: 'fabric',
        METAL: 'metal',
        WOOD: 'wood',
        OTHER: 'other'
    },

    // Service Categories
    SERVICE_CATEGORIES: {
        PRINTING: 'printing',
        FINISHING: 'finishing',
        BINDING: 'binding',
        CUTTING: 'cutting',
        FOLDING: 'folding',
        LAMINATION: 'lamination',
        COATING: 'coating',
        PACKAGING: 'packaging',
        DELIVERY: 'delivery',
        OTHER: 'other'
    },

    // CSS Classes
    CSS_CLASSES: {
        LOADING: 'pp-loading',
        ERROR: 'pp-error',
        SUCCESS: 'pp-success',
        WARNING: 'pp-warning',
        INFO: 'pp-info',
        HIDDEN: 'pp-hidden',
        VISIBLE: 'pp-visible',
        DISABLED: 'pp-disabled',
        ACTIVE: 'pp-active',
        SELECTED: 'pp-selected'
    },

    // Local Storage Keys
    STORAGE_KEYS: {
        DRAFT_ORDER: 'pp_draft_order',
        USER_PREFERENCES: 'pp_user_preferences',
        RECENT_SEARCHES: 'pp_recent_searches',
        FORM_DATA: 'pp_form_data'
    },

    // Debug Settings
    DEBUG: {
        ENABLED: false, // Set to true in development
        LOG_LEVEL: 'info', // 'debug', 'info', 'warn', 'error'
        LOG_API_CALLS: false,
        LOG_CALCULATIONS: false
    }
};

// Freeze the configuration to prevent modifications
Object.freeze(PrintingPricing.Config);

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PrintingPricing.Config;
}
