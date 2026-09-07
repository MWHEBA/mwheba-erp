/**
 * MWHEBA ERP - Printing Pricing Master Engine (Enterprise ES6 Architecture)
 * 3-Tier Decoupled Printing Suite: Foundation Core + Sheet Production Line + Master Orchestrator
 * Version: 3.0.0
 *
 * ============================================================================
 * ARCHITECTURAL MODULES MAP (خارطة الموديولات المعمارية الموحدة):
 * ============================================================================
 * 1. Shared Foundation Library (المكتبة الأساسية المشتركة):
 *    -> static/js/printing_pricing/modules/pricing_core.js
 *       ├── PricingMath (Pure Math, Sheets, CTP Spoilage, Signatures, Imposition)
 *       ├── PricingApiClient (Unified Network Service & Cache)
 *       └── PricingExport (Universal Clipboard & WhatsApp Formatter)
 *
 * 2. Commercial Sheet-Fed Production Line (خط إنتاج طباعة الشيت المتكامل):
 *    -> static/js/printing_pricing/modules/pricing_sheet_printing.js
 *       └── PricingSheetPrintingSubsystem (Paper, Offset Presses, CTP Plates, Digital, Preferred Suppliers)
 *
 * 3. Master Job Orchestrator & Mediator (المحرك المعياري والمنسق العام للطلب - هذا الملف):
 *    -> OrderFormUIController
 *       ├── [Sec 1] Constructor & Initialization (init, date, select2)
 *       ├── [Sec 2] Delegated DOM Event Bus (bindDelegatedEvents)
 *       ├── [Sec 3] Product Anatomy & Dimensions (handleAnatomySwitch, applySize)
 *       ├── [Sec 4] Step Gates & Navigation Control (isStep1Complete, updateGatesState)
 *       ├── [Sec 5] Live Pricing Engine & Calculations (recalculate, callLiveCalculateAPI)
 *       ├── [Sec 6] Montage & Imposition UI Controls (handleMontageInputChange)
 *       ├── [Sec 7] Export Stubs & Submit Sanitization (generateWhatsAppQuote, sanitize)
 *       ├── [Sec 8] Shortcuts & Lifecycle Guards (bindKeyboardShortcuts, beforeunload)
 *       └── [Sec 9] Sheet Printing & Materials Subsystem Delegation (Delegated to Subsystem)
 * ============================================================================
 */

// ============================================================================
// كلاس التحكم بالواجهة والأحداث (UI & Event Orchestrator)
// ============================================================================
class OrderFormUIController {
  // السجل المركزي الموحد والشامل لكافة بنود التسعير المباشرة في النموذج
  static PRICING_REGISTRY = [
    { id: '#id_paper_sheet_price', rawId: 'id_paper_sheet_price', supplier_sel: '#id_paper_supplier', supplierRawId: 'id_paper_supplier', machine_sel: null, service_id_sel: '#id_paper_service_id', badge_id: '#paper_price_staleness_badge', date_id: '#paper_price_date_display', default_label: 'ورق الغلاف', unit: 'فرخ', service_type: 'paper', section: 'cover_paper', is_inner: false },
    { id: '#id_press_rate', rawId: 'id_press_rate', supplier_sel: '#id_cover_offset_supplier', supplierRawId: 'id_cover_offset_supplier', machine_sel: '#id_cover_press_machine', service_id_sel: '#id_cover_press_service_id', badge_id: '#press_rate_staleness_badge', date_id: null, default_label: 'طباعة أوفست الغلاف', unit: 'تراج', service_type: 'offset', section: 'cover_offset', is_inner: false },
    { id: '#id_plate_price', rawId: 'id_plate_price', supplier_sel: '#id_cover_ctp_supplier', supplierRawId: 'id_cover_ctp_supplier', machine_sel: null, service_id_sel: '#id_cover_ctp_service_id', badge_id: '#plate_price_staleness_badge', date_id: null, default_label: 'زنكات CTP الغلاف', unit: 'زنكة', service_type: 'ctp', section: 'cover_ctp', is_inner: false },
    { id: '#id_digital_sheet_price', rawId: 'id_digital_sheet_price', supplier_sel: '#id_cover_digital_supplier', supplierRawId: 'id_cover_digital_supplier', machine_sel: '#id_cover_digital_machine', service_id_sel: '#id_cover_digital_service_id', badge_id: '#digital_price_staleness_badge', date_id: null, default_label: 'طبعة ديجيتال الغلاف', unit: 'طبعة', service_type: 'digital', section: 'cover_digital', is_inner: false },
    { id: '#id_inner_sheet_price', rawId: 'id_inner_sheet_price', supplier_sel: '#id_inner_paper_supplier', supplierRawId: 'id_inner_paper_supplier', machine_sel: null, service_id_sel: '#id_inner_paper_service_id', badge_id: '#inner_paper_price_staleness_badge', date_id: '#inner_paper_price_date_display', default_label: 'ورق الداخلي', unit: 'فرخ', service_type: 'paper', section: 'inner_paper', is_inner: true },
    { id: '#id_inner_press_rate', rawId: 'id_inner_press_rate', supplier_sel: '#id_inner_offset_supplier', supplierRawId: 'id_inner_offset_supplier', machine_sel: '#id_inner_press_machine', service_id_sel: '#id_inner_press_service_id', badge_id: '#inner_press_rate_staleness_badge', date_id: null, default_label: 'طباعة أوفست الداخلي', unit: 'تراج', service_type: 'offset', section: 'inner_offset', is_inner: true },
    { id: '#id_inner_plate_price', rawId: 'id_inner_plate_price', supplier_sel: '#id_inner_ctp_supplier', supplierRawId: 'id_inner_ctp_supplier', machine_sel: null, service_id_sel: '#id_inner_ctp_service_id', badge_id: '#inner_plate_price_staleness_badge', date_id: null, default_label: 'زنكات CTP الداخلي', unit: 'زنكة', service_type: 'ctp', section: 'inner_ctp', is_inner: true },
    { id: '#id_digital_inner_color_price', rawId: 'id_digital_inner_color_price', supplier_sel: '#id_inner_digital_supplier', supplierRawId: 'id_inner_digital_supplier', machine_sel: '#id_inner_digital_machine', service_id_sel: '#id_inner_digital_service_id', badge_id: '#inner_digital_badge', date_id: null, default_label: 'طبعة ألوان ديجيتال الداخلي', unit: 'طبعة', service_type: 'digital', section: 'inner_digital', is_inner: true },
    { id: '#id_digital_inner_bw_price', rawId: 'id_digital_inner_bw_price', supplier_sel: '#id_inner_digital_supplier', supplierRawId: 'id_inner_digital_supplier', machine_sel: '#id_inner_digital_machine', service_id_sel: '#id_inner_digital_service_id', badge_id: '#inner_digital_badge', date_id: null, default_label: 'طبعة أسود ديجيتال الداخلي', unit: 'طبعة', service_type: 'digital', section: 'inner_digital', is_inner: true }
  ];

  constructor(config = {}) {
    this.config = Object.assign({
      currencySymbol: window.ORDER_CONFIG?.currencySymbol || window.SYSTEM_CURRENCY_SYMBOL || '',
      urls: {
        pressesApi: '/api/printing/presses/',
        paperStocksApi: '/api/printing/paper-stocks/'
      },
      i18n: {
        pulls: 'سحبة',
        tirage: 'تراج',
        archivedPlates: 'زنكات موجودة مسبقاً',
        newPlates: 'زنكات جديدة',
        piece: 'قطعة',
        sheet: 'شيت',
        sqm: 'م²',
        signature: 'ملزمة',
        signaturesEq: 'يعادل',
        step2Cover: 'تفاصيل الغلاف الخارجي',
        step2Print: 'تفاصيل الطباعة',
        step2Folder: 'تفاصيل الفولدر والعلبة',
        step2Invoice: 'تفاصيل غلاف الدفاتر',
        step2Giveaways: 'تفاصيل الهدايا الدعائية',
        step3Inner: 'تفاصيل الداخلي والتجليد'
      }
    }, config);

    this.debounceTimer = null;
    this.isDirty = false;
    this.isUserInteracting = false;
    this.isRestoringDraft = false;
    this.maxMontage = null;
    this.isManualMontage = false;
    this.currentPieceName = '';
    this.marginMode = 'percent'; // 'percent' أو 'fixed'
    this.lastKnownTotalCost = 0;
    this.isSyncingFields = false;
    this.api = window.PricingApiClient ? new window.PricingApiClient(this.config) : null;
    this.sheetPrinting = (typeof window !== "undefined" && window.PricingSheetPrintingSubsystem)
      ? new window.PricingSheetPrintingSubsystem(this)
      : null;
  }

  /**
   * تهيئة المنظومة
   */
  init() {
    this.initDefaultDate();
    this.initSelect2();
    this.bindDelegatedEvents();
    if (this.sheetPrinting) {
      this.sheetPrinting.bindSupplierWatchers();
      this.sheetPrinting.bindPaperCardWatchers();
    } else {
      this.bindSupplierWatchers();
      this.bindPaperCardWatchers();
    }
    this.bindKeyboardShortcuts();
    this.bindLifecycleGuards();
    this.bindStepNavigation();
    this.bindCommercialCommitGuards();
    this.bindQuickQuotePreset();
    this.initBaselinePrices();

    $(document).one('mousedown keydown touchstart', () => {
      this.isUserInteracting = true;
    });

    // تشغيل الحالة الأولية
    const anatomySelect = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type') || document.getElementById('id_product_type');
    if (anatomySelect) {
      const initOpt = anatomySelect.options?.[anatomySelect.selectedIndex];
      const initArchetype = initOpt?.dataset?.archetype || anatomySelect.dataset?.archetype || anatomySelect.value || 'flyer';
      this.handleAnatomySwitch(initArchetype);
    }
    this.applySelectedProductSize();
    this.updatePrintingTypeUI();
    this.updateCoverPlatesUI();
    this.updateInnerPlatesUI();
    this.initPieceSizesMasterList();
    const initSheetOpt = $('#id_sheet_size option:selected');
    if (initSheetOpt.length) {
      this.updatePieceSizesForSheet(
        $('#id_sheet_size').val(),
        initSheetOpt.data('id') || '',
        initSheetOpt.data('width') || '',
        initSheetOpt.data('height') || ''
      );
    }
    this.updateResolvedPackCapacity(true);
    this.updateResolvedInnerPackCapacity(true);
    if (this.config && this.config.isEdit) {
      this.currentPieceName = this.getCleanPieceName();
      const initMontageVal = parseInt($('#id_montage_count').val(), 10);
      if (!isNaN(initMontageVal) && initMontageVal > 0) {
        this.isManualMontage = true;
      }
    } else {
      this.isManualMontage = false;
      this.currentPieceName = '';
      // بدء الشاشة بحسابات مفعلة وتفريد تلقائي
      setTimeout(() => {
        this.debouncedRecalculate();
      }, 50);
    }

    // التهيئة الصامتة الأولية للتكلفة الإجمالية من الـ DOM لمنع التصفير في وضع التعديل (Edit Mode Hydration)
    const initialCostText = ($('#total_cost_display').text() || '').replace(/[^\d.]/g, '');
    const parsedInitialCost = parseFloat(initialCostText) || 0;
    if (parsedInitialCost > 0) {
      this.lastKnownTotalCost = parsedInitialCost;
    } else {
      const mat = parseFloat($('#id_material_cost').val()) || 0;
      const prt = parseFloat($('#id_printing_cost').val()) || 0;
      const fin = parseFloat($('#id_finishing_cost').val()) || 0;
      if (mat + prt + fin > 0) {
        this.lastKnownTotalCost = mat + prt + fin;
      }
    }

    this.updateMontageWaitingState();
    this.checkDesignZeroFeeAlert();
    this.updateGatesState();

    // فحص الأسعار المحفوظة مسبقاً في وضع التعديل وتفعيل شارة السعر المخصص للأسعار الحرة بدون مورد (Edit Mode Hydration)
    const isEditMode = Boolean(this.config && this.config.isEdit);

    OrderFormUIController.PRICING_REGISTRY.forEach(item => {
      const pInput = document.getElementById(item.rawId);
      const sVal = document.getElementById(item.supplierRawId)?.value;
      if (!pInput) return;
      const val = PricingMath.parseSafeNumber(pInput.value, 0);

      if (val > 0 && !sVal) {
        pInput.dataset.manual = 'true';
        pInput.classList.add('border-primary');
        if (item.badge_id) {
          this.renderManualPriceBadge($(item.badge_id), item.date_id ? $(item.date_id) : null);
        }
      }
    });

    // حماية هالك الورق في وضع التعديل من مسح أول استدعاء تلقائي للحساب الحي
    if (isEditMode) {
      const wasteEl = document.getElementById('id_cover_waste_sheets');
      if (wasteEl && PricingMath.parseSafeNumber(wasteEl.value, -1) >= 0) {
        wasteEl.dataset.manual = 'true';
      }
    }

    // جلب حداثة وتاريخ سعر الورق تلقائياً مع حماية السعر المحفوظ في وضع التعديل
    if ($('#id_paper_supplier').val() && $('#id_paper_type').val()) {
      const existingPaperPrice = PricingMath.parseSafeNumber($('#id_paper_sheet_price').val(), 0);
      this.fetchLivePaperPrice({ preserveSavedPrice: isEditMode && existingPaperPrice > 0 }, false);
    }
    if ($('#id_inner_paper_supplier').val() && $('#id_inner_paper_type').val()) {
      const existingInnerPrice = PricingMath.parseSafeNumber($('#id_inner_sheet_price').val(), 0);
      this.fetchLivePaperPrice({ preserveSavedPrice: isEditMode && existingInnerPrice > 0 }, true);
    }

    this.updateSupplierDependentSections();
    this.updateMarginUI();
    this.recalculate();
  }

  /**
   * التنسيق المالي مع مسافة BiDi غير قابلة للكسر والتنسيق الذكي للأرقام الصحيحة بدون فواصل
   */
  formatMoney(amount, forceDecimals = false) {
    if (amount === undefined || amount === null || isNaN(amount)) {
      return `0\u00A0${this.config.currencySymbol}`.trim();
    }
    const num = Number(amount);
    const isWhole = (Math.abs(num - Math.round(num)) < 0.00001);
    const hasDecimals = !isWhole && ((num % 1 !== 0) || forceDecimals);
    const formatted = num.toLocaleString('en-US', {
      minimumFractionDigits: hasDecimals ? 2 : 0,
      maximumFractionDigits: 2
    });
    return this.config.currencySymbol ? `${formatted}\u00A0${this.config.currencySymbol}` : formatted;
  }

  /**
   * تنسيق الرقم فقط بدون رمز العملة (للعناصر التي بجانبها وسم small للعملة)
   */
  formatNumber(amount, forceDecimals = false) {
    if (amount === undefined || amount === null || isNaN(amount)) {
      return '0';
    }
    const num = Number(amount);
    const isWhole = (Math.abs(num - Math.round(num)) < 0.00001);
    const hasDecimals = !isWhole && ((num % 1 !== 0) || forceDecimals);
    return num.toLocaleString('en-US', {
      minimumFractionDigits: hasDecimals ? 2 : 0,
      maximumFractionDigits: 2
    });
  }

  /**
   * تحديث نص العنصر فقط إذا تغيرت القيمة لمنع إعادة الرسم غير الضروري وتجنب Layout Thrashing
   */
  updateTextSafely(idOrEl, newText) {
    const el = typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
    if (el && el.textContent !== String(newText)) {
      el.textContent = String(newText);
    }
  }

  /**
   * تاريخ اليوم الافتراضي
   */
  initDefaultDate() {
    const orderDateInput = document.getElementById('id_order_date');
    if (orderDateInput && !orderDateInput.value) {
      orderDateInput.value = new Date().toISOString().split('T')[0];
    }
  }

  /**
   * تهيئة Select2
   */
  initSelect2() {
    if (typeof $.fn !== 'undefined' && typeof $.fn.select2 !== 'undefined') {
      $('.select2-filter').select2({
        width: '100%',
        dir: 'rtl',
        language: 'ar'
      });

      // إعادة تهيئة القوائم عند فتح الأكورديون
      $(document).on('shown.bs.collapse', '.collapse', function () {
        $(this).find('.select2-filter').each(function () {
          if ($(this).data('select2')) {
            $(this).select2('destroy');
          }
          $(this).select2({ width: '100%', dir: 'rtl', language: 'ar' });
        });
      });
    }
  }

  /**
   * ربط كافة الأحداث عبر Document-Level Event Delegation
   */
  bindDelegatedEvents() {
    const self = this;

    // صمام أمان حظر بكرة الماوس على حقول الأرقام لمنع التغيير العرضي أثناء السكرول
    $(document).on('wheel', 'input[type=number]', function () {
      $(this).trigger('blur');
    });

    // 1. مراقبة تغيير نوع المطبوع
    $(document).on('change', '#id_product_type, #id_order_type, #id_job_anatomy_type', function () {
      if (self.isSyncingFields) return;
      const selectEl = this;
      const archetype = selectEl.options?.[selectEl.selectedIndex]?.dataset?.archetype || selectEl.dataset?.archetype || selectEl.value || 'flyer';
      self.handleAnatomySwitch(archetype);
      self.debouncedRecalculate(50);
    });

    // 2. مراقبة مقاس المطبوع
    $(document).on('change', '#id_product_size', function () {
      if (self.isSyncingFields) return;
      self.applySelectedProductSize();
      self.debouncedRecalculate(50);
    });

    // 2.5 مراقبة خدمة التصميم والتجهيز الفني
    $(document).on('change', 'input[name="design_service_choice"]', function () {
      const val = this.value;
      const select = $('#id_design_service_type');
      if (select.val() !== val) {
        select.val(val).trigger('change');
      }
    });

    $(document).on('change', '#id_design_service_type', function () {
      const val = this.value;
      $(`input[name="design_service_choice"][value="${val}"]`).prop('checked', true);
      const feeInput = document.getElementById('id_design_fee');
      if (val === 'CUSTOMER_READY') {
        if (feeInput) {
          feeInput.value = '0';
          feeInput.readOnly = true;
          feeInput.style.backgroundColor = 'var(--gray-100)';
          feeInput.style.cursor = 'not-allowed';
        }
      } else {
        if (feeInput) {
          feeInput.readOnly = false;
          feeInput.style.backgroundColor = '';
          feeInput.style.cursor = 'text';
          feeInput.focus();
          feeInput.select();
        }
      }
      self.debouncedRecalculate(50);
    });

    $(document).on('input change', '#id_design_fee', function (e) {
      if (e.type === 'change' && this.value && this.value.includes('.')) {
        const parsed = parseFloat(this.value);
        if (!isNaN(parsed)) {
          this.value = Math.round(parsed);
        }
      }
      self.debouncedRecalculate(100);
    });

    // 3. التبديل بين العميل المسجل والعميل النقدي
    $(document).on('change', '#id_is_cash_customer', function () {
      const isCash = this.checked;
      const regWrap = document.getElementById('wrapper_registered_customer');
      const cashWrap = document.getElementById('wrapper_cash_customer');
      const custSelect = $('#id_customer');
      const custNameInput = document.getElementById('id_customer_name');
      const labelText = document.getElementById('text_customer_label');

      if (isCash) {
        if (regWrap) regWrap.classList.add('d-none');
        if (cashWrap) cashWrap.classList.remove('d-none');
        if (labelText) labelText.textContent = 'اسم العميل النقدي';
        custSelect.val('').trigger('change');
        if (custNameInput) {
          custNameInput.focus();
          custNameInput.required = true;
        }
      } else {
        if (cashWrap) cashWrap.classList.add('d-none');
        if (regWrap) regWrap.classList.remove('d-none');
        if (labelText) labelText.textContent = 'العميل';
        if (custNameInput) {
          custNameInput.value = '';
          custNameInput.required = false;
        }
      }
    });

    // مزامنة اسم العميل عند اختيار عميل مسجل والانتقال التلقائي لوصف الطلب
    $(document).on('change', '#id_customer', function () {
      const selected = this.options[this.selectedIndex];
      const custNameInput = document.getElementById('id_customer_name');
      if (selected && selected.value && custNameInput) {
        custNameInput.value = selected.dataset.name || selected.text.trim();
      }
      self.updateGatesState();

      // نقل التركيز فورياً لوصف الطلب عند اختيار عميل
      if (selected && selected.value) {
        setTimeout(() => {
          const titleInput = document.getElementById('id_title');
          if (titleInput) {
            titleInput.focus();
            titleInput.select();
          }
        }, 60);
      }
    });

    // الضغط على Enter في اسم العميل النقدي ينقل لوصف الطلب
    $(document).on('keydown', '#id_customer_name', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        const titleInput = document.getElementById('id_title');
        if (titleInput) {
          titleInput.focus();
          titleInput.select();
        }
      }
    });

    // الضغط على Enter في وصف الطلب ينقر أوتوماتيك على زر المتابعة
    $(document).on('keydown', '#id_title', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        $('#btn_proceed_to_step2').trigger('click');
      }
    });

    // مراقبة حقول البوابات الفنية والتجارية لتحديث شارات الحالة فورياً
    $(document).on('input change', '#id_is_cash_customer, #id_customer, #id_customer_name, #id_title, #id_order_date, #id_quantity, #id_product_size, #id_width, #id_height, #id_product_type', function () {
      self.updateGatesState();
    });

    // 4. اتجاه الطباعة والمقاس المقفول وجهة الفتح
    $(document).on('change', 'input[name="print_orientation"]', function () {
      const sizeSelect = document.getElementById('id_product_size');
      const widthInput = document.getElementById('id_width');
      const heightInput = document.getElementById('id_height');

      if (sizeSelect && sizeSelect.value !== 'custom') {
        self.applySelectedProductSize();
      } else {
        if (widthInput && heightInput) {
          const oldW = widthInput.value;
          const oldH = heightInput.value;
          widthInput.value = oldH;
          heightInput.value = oldW;
        }
        self.updateOpenDimensionsDisplay();
        self.debouncedRecalculate();
      }
    });

    $(document).on('change', '#id_is_closed_size', function () {
      this.dataset.manual = '1';
      self.updateOpenDimensionsDisplay();
      self.debouncedRecalculate();
    });

    $(document).on('change', 'input[name="open_direction"]', function () {
      self.updateOpenDimensionsDisplay();
      self.debouncedRecalculate();
    });

    // 6. مدخلات الأبعاد المخصصة والكشف التلقائي عن الاتجاه
    $(document).on('input', '#id_width, #id_height, #id_custom_size_width, #id_custom_size_height', function () {
      const widthEl = document.getElementById('id_width');
      const heightEl = document.getElementById('id_height');
      const sizeSelect = document.getElementById('id_product_size');

      if (sizeSelect && sizeSelect.value === 'custom') {
        const w = PricingMath.parseSafeNumber(widthEl?.value);
        const h = PricingMath.parseSafeNumber(heightEl?.value);
        if (w > 0 && h > 0) {
          if (w > h) {
            const landRadio = document.getElementById('orient_landscape');
            if (landRadio && !landRadio.checked) landRadio.checked = true;
          } else if (h > w) {
            const portRadio = document.getElementById('orient_portrait');
            if (portRadio && !portRadio.checked) portRadio.checked = true;
          }
        }
      }
      self.updateOpenDimensionsDisplay();
      self.updateMontageWaitingState();
      self.debouncedRecalculate();
    });

    // 7. مراقبة تغيير تقنيات الطباعة والأوجه والألوان (Selects / Radios / Checkboxes)
    $(document).on('change', '#id_cover_printing_type, #id_inner_printing_type, #id_print_sides_mode_offset, #id_print_sides_mode_standard, #id_inner_print_sides_mode, #id_inner_color_mode, #id_digital_color_mode, #id_has_white_ink, #id_paper_type, #id_inner_paper_type, #id_binding_type, #id_lamination, #id_finishing, #id_die_cutting, #id_press_bed_size, #id_inner_press_bed_size', function () {
      self.isDirty = true;

      // المزامنة التبادلية للأوجه
      if (this.id === 'id_print_sides_mode_standard') {
        const offsetSel = document.getElementById('id_print_sides_mode_offset');
        if (offsetSel) offsetSel.value = this.value;
      } else if (this.id === 'id_print_sides_mode_offset') {
        const stdSel = document.getElementById('id_print_sides_mode_standard');
        if (stdSel) stdSel.value = this.value === 'work_sheet' ? 'work_sheet' : 'single';
      }

      // مزامنة مقاس السلندر/الزنك مع مواصفات زنك المورد المختار فقط دون فرض أسعار عشوائية
      if (this.id === 'id_press_bed_size') {
        const ctpSupp = $('#id_cover_ctp_supplier').val();
        if (ctpSupp) {
          $('#id_cover_ctp_supplier').trigger('change');
        }
      }
      if (this.id === 'id_inner_press_bed_size') {
        const innerCtpSupp = $('#id_inner_ctp_supplier').val();
        if (innerCtpSupp) {
          $('#id_inner_ctp_supplier').trigger('change');
        }
      }

      self.updatePrintingTypeUI();
      if (['id_print_sides_mode_offset', 'id_print_sides_mode_standard', 'id_cover_printing_type'].includes(this.id)) {
        self.updateCoverPlatesUI();
      }
      if (['id_inner_print_sides_mode', 'id_inner_printing_type', 'id_inner_color_mode'].includes(this.id)) {
        self.updateInnerPlatesUI();
      }
      self.updateOpenDimensionsDisplay();
      self.debouncedRecalculate(50);
    });

    // 7.1 مراقبة حقول الأرقام والإدخال (Inputs) بحدث input فقط لمنع الازدواجية عند الـ blur
    $(document).on('input', '#id_quantity, #id_profit_margin, #id_extra_cost, #id_giveaway_item_cost, #id_paper_weight, #id_inner_paper_weight, #id_pages_count, #id_colors_front, #id_colors_back, #id_spot_colors_front, #id_spot_colors_back, #id_screen_colors_count, #id_inner_colors_single, #id_inner_spot_colors_single, #id_inner_spot_colors, #id_digital_inner_color_pages, #id_digital_inner_bw_pages, #id_color_signatures_count, #id_bw_signatures_count, #id_ncr_sets_count, #id_ncr_book_capacity, #id_ncr_serial_start, #id_banner_sqm_price', function () {
      self.isDirty = true;
      self.updatePrintingTypeUI();
      if (['id_colors_front', 'id_colors_back', 'id_spot_colors_front', 'id_spot_colors_back'].includes(this.id)) {
        self.updateCoverPlatesUI();
      }
      if (['id_inner_colors_single', 'id_inner_spot_colors_single', 'id_inner_spot_colors', 'id_pages_count', 'id_color_signatures_count', 'id_bw_signatures_count'].includes(this.id)) {
        self.updateInnerPlatesUI();
      }
      self.updateOpenDimensionsDisplay();
      if (this.id === 'id_quantity') {
        self.updateMontageWaitingState();
      }
      self.debouncedRecalculate(250);
    });

    // 8. زنكات CTP
    $(document).on('change', '#id_is_plates_archived', function () {
      self.updateCoverPlatesUI();
      self.debouncedRecalculate();
    });

    $(document).on('change', '#id_is_inner_plates_archived', function () {
      self.updateInnerPlatesUI();
      self.debouncedRecalculate();
    });

    $(document).on('input', '#id_cover_waste_sheets, #id_plate_count_front, #id_plate_count_back, #id_plate_count, #id_inner_plates_count_total', function () {
      this.dataset.manual = "true";
      $(this).addClass('border-primary');
      if (this.id === 'id_plate_count_front' || this.id === 'id_plate_count_back') {
        self.updateCoverPlatesUI();
      } else if (this.id === 'id_inner_plates_count_total') {
        self.updateInnerPlatesUI();
      }
      self.debouncedRecalculate();
    });

    // 8.2 مراقبة والتحكم في حقل المونتاج الذكي (سقف هندسي وتعديل للأقل فقط)
    $(document).on('input change', '#id_montage_count', function (e) {
      self.handleMontageInputChange(e.type === 'change');
    });



    $(document).on('click', '#btn_montage_minus', function (e) {
      e.preventDefault();
      const input = $('#id_montage_count');
      let val = parseInt(input.val(), 10) || 1;
      if (val > 1) {
        input.val(val - 1).trigger('change');
      }
    });

    $(document).on('click', '#btn_montage_plus', function (e) {
      e.preventDefault();
      const input = $('#id_montage_count');
      let val = parseInt(input.val(), 10) || 1;
      const max = self.maxMontage || parseInt(input.attr('max'), 10) || val;
      if (val < max) {
        input.val(val + 1).trigger('change');
      }
    });

    $(document).on('click', '.montage-value-display', function (e) {
      if (e.target.id !== 'id_montage_count') {
        $('#id_montage_count').focus().select();
      }
    });

    // 8.05 مراقبة حقول أستوديو التصميم (نوع الخدمة، الأتعاب)
    $(document).on('change input', '#id_design_service_type, #id_design_fee', function () {
      self.checkDesignZeroFeeAlert();
      self.updateFinancialsLocally();
      self.debouncedRecalculate();
    });

    // 8.1 مراقبة أزرار شريط التشطيبات السريعة (Multi-Finishing Pill Badges)
    $(document).on('click', '.finishing-pill-btn', function (e) {
      e.preventDefault();
      const targetId = this.dataset.target;
      const targetBox = document.getElementById(targetId);
      if (!targetBox) return;

      const isOpening = targetBox.classList.contains('d-none');
      if (isOpening) {
        targetBox.classList.remove('d-none');
        this.classList.remove('btn-outline-secondary');
        this.classList.add('btn-primary', 'active');
      } else {
        targetBox.classList.add('d-none');
        this.classList.remove('btn-primary', 'active');
        this.classList.add('btn-outline-secondary');
      }

      // مزامنة الحقول المخفية للباك إند
      if (targetId === 'box_settings_spot_uv') {
        const flag = document.getElementById('id_has_spot_uv');
        if (flag) flag.value = isOpening ? '1' : '0';
      } else if (targetId === 'box_settings_die_cut') {
        const flag = document.getElementById('id_has_die_cutting');
        const dieInput = document.getElementById('id_die_cutting');
        if (flag) flag.value = isOpening ? '1' : '0';
        if (dieInput) dieInput.value = isOpening ? 'die_cut_custom' : 'straight_cut';
      } else if (targetId === 'box_settings_foil') {
        const flag = document.getElementById('id_has_foil');
        if (flag) flag.value = isOpening ? '1' : '0';
      } else if (targetId === 'box_settings_emboss') {
        const flag = document.getElementById('id_has_emboss');
        if (flag) flag.value = isOpening ? '1' : '0';
      } else if (targetId === 'box_settings_crease') {
        const flag = document.getElementById('id_has_creasing');
        if (flag) flag.value = isOpening ? '1' : '0';
      }

      // تحديث الحقل التجميعي finishing للتوافق مع الموديل القديم
      const activeFinishes = [];
      if (document.getElementById('id_has_spot_uv')?.value === '1') activeFinishes.push('spot_uv');
      if (document.getElementById('id_has_foil')?.value === '1') activeFinishes.push('gold_foiling');
      if (document.getElementById('id_has_emboss')?.value === '1') activeFinishes.push('embossing');
      const legacyFinInput = document.getElementById('id_finishing');
      if (legacyFinInput) legacyFinInput.value = activeFinishes.length > 0 ? activeFinishes[0] : 'none';

      self.debouncedRecalculate();
    });

    // زر إغلاق شريط التشطيب المصغر
    $(document).on('click', '.btn-close-finishing', function (e) {
      e.preventDefault();
      const targetId = this.dataset.target;
      const btnId = this.dataset.btn;
      const targetBox = document.getElementById(targetId);
      const pillBtn = document.getElementById(btnId);
      if (targetBox) targetBox.classList.add('d-none');
      if (pillBtn) {
        pillBtn.classList.remove('btn-primary', 'active');
        pillBtn.classList.add('btn-outline-secondary');
      }

      if (targetId === 'box_settings_spot_uv') document.getElementById('id_has_spot_uv').value = '0';
      if (targetId === 'box_settings_die_cut') {
        document.getElementById('id_has_die_cutting').value = '0';
        const dieInput = document.getElementById('id_die_cutting');
        if (dieInput) dieInput.value = 'straight_cut';
      }
      if (targetId === 'box_settings_foil') document.getElementById('id_has_foil').value = '0';
      if (targetId === 'box_settings_emboss') document.getElementById('id_has_emboss').value = '0';
      if (targetId === 'box_settings_crease') document.getElementById('id_has_creasing').value = '0';

      self.debouncedRecalculate();
    });

    // مراقبة مدخلات التشطيبات والسلوفان التفصيلية
    $(document).on('change input', '#id_lamination_sides, #id_lamination_face_price, #id_spot_uv_tirage_price, input[name="spot_uv_screen_mode"], #id_spot_uv_override_price, #id_die_cut_tirage_price, input[name="die_tooling_mode"], #id_die_cut_override_price, #id_foil_color, input[name="foil_cliche_mode"], #id_foil_override_price, input[name="emboss_cliche_mode"], #id_emboss_override_price, #id_creasing_lines_count, #id_creasing_override_price', function () {
      self.debouncedRecalculate();
    });

    // مراقبة مدخلات التسعير المباشرة في الشريط الجانبي (هامش الربح والانتقالات) - لحظية 0ms
    $(document).on('input change', '#id_profit_margin', function () {
      self.updateFinancialsLocally();
    });

    $(document).on('click', '#btn_margin_toggle', function (e) {
      e.preventDefault();
      const nextMode = self.marginMode === 'fixed' ? 'percent' : 'fixed';
      self.setMarginMode(nextMode);
    });

    $(document).on('keydown', '#btn_margin_toggle', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        $(this).trigger('click');
      }
    });

    $(document).on('change', '#id_margin_type', function () {
      const mode = $(this).val() === 'fixed' ? 'fixed' : 'percent';
      self.setMarginMode(mode);
    });

    $(document).on('input change', '#id_extra_cost', function () {
      self.updateFinancialsLocally();
    });

    // أزرار استعادة الحساب التلقائي للزنكات
    $(document).on('click', '#btn_reset_cover_plates', function (e) {
      e.preventDefault();
      const pFront = document.getElementById('id_plate_count_front');
      const pBack = document.getElementById('id_plate_count_back');
      const pTotal = document.getElementById('id_plate_count');
      if (pFront) { delete pFront.dataset.manual; $(pFront).removeClass('border-primary'); }
      if (pBack) { delete pBack.dataset.manual; $(pBack).removeClass('border-primary'); }
      if (pTotal) { delete pTotal.dataset.manual; }
      self.updateCoverPlatesUI();
      self.debouncedRecalculate();
      self.showNotification('تمت إعادة حساب زنكات الغلاف بنجاح', 'info');
    });

    $(document).on('click', '#btn_reset_inner_plates', function (e) {
      e.preventDefault();
      const pInner = document.getElementById('id_inner_plates_count_total');
      if (pInner) { delete pInner.dataset.manual; $(pInner).removeClass('border-primary'); }
      self.updateInnerPlatesUI();
      self.debouncedRecalculate();
      self.showNotification('تمت إعادة حساب زنكات ملازم الداخلي بنجاح', 'info');
    });

    // أزرار إعادة حساب أسعار وتكاليف الطباعة (أوفست / ديجيتال)
    $(document).on('click', '#btn_reset_cover_press', function (e) {
      e.preventDefault();
      const pressRateInput = document.getElementById('id_press_rate');
      if (pressRateInput) {
        delete pressRateInput.dataset.manual;
        $(pressRateInput).removeClass('border-primary');
        const selectedOpt = $('#id_cover_press_machine').find('option:selected');
        const optRate = selectedOpt.data('rate');
        if (optRate !== undefined && optRate !== '') {
          pressRateInput.value = optRate;
          $(pressRateInput).attr('data-baseline-price', PricingMath.parseSafeNumber(optRate, 0).toFixed(2));
        }
        self.renderPriceStalenessBadge(
          selectedOpt.data('price-date'),
          selectedOpt.data('price-age'),
          selectedOpt.data('staleness'),
          selectedOpt.data('valid-until'),
          $('#press_rate_staleness_badge'),
          null
        );
      }
      self.debouncedRecalculate();
      self.showNotification('تمت إعادة حساب طباعة الأوفست بنجاح', 'info');
    });

    $(document).on('click', '#btn_reset_inner_press', function (e) {
      e.preventDefault();
      const innerRateInput = document.getElementById('id_inner_press_rate');
      if (innerRateInput) {
        delete innerRateInput.dataset.manual;
        $(innerRateInput).removeClass('border-primary');
        const selectedOpt = $('#id_inner_press_machine').find('option:selected');
        const optRate = selectedOpt.data('rate');
        if (optRate !== undefined && optRate !== '') {
          innerRateInput.value = optRate;
          $(innerRateInput).attr('data-baseline-price', PricingMath.parseSafeNumber(optRate, 0).toFixed(2));
        }
        self.renderPriceStalenessBadge(
          selectedOpt.data('price-date'),
          selectedOpt.data('price-age'),
          selectedOpt.data('staleness'),
          selectedOpt.data('valid-until'),
          $('#inner_press_rate_staleness_badge'),
          null
        );
      }
      self.debouncedRecalculate();
      self.showNotification('تمت إعادة حساب طباعة أوفست الداخلي بنجاح', 'info');
    });

    $(document).on('click', '#btn_reset_cover_digital', function (e) {
      e.preventDefault();
      const digPriceInput = document.getElementById('id_digital_sheet_price');
      if (digPriceInput) {
        delete digPriceInput.dataset.manual;
        $(digPriceInput).removeClass('border-primary');
        const selectedOpt = $('#id_cover_digital_machine').find('option:selected');
        if (selectedOpt.length && selectedOpt.val()) {
          const colorMode = $('#id_digital_color_mode').val() || '4_0';
          const isColor = colorMode.includes('4');
          const priceColor = PricingMath.parseSafeNumber(selectedOpt.data('price-color'), 0);
          const priceBw = PricingMath.parseSafeNumber(selectedOpt.data('price-bw'), 0);
          const restoredPrice = isColor ? (priceColor || '') : (priceBw || '');
          digPriceInput.value = restoredPrice;
          if (restoredPrice !== '') {
            $(digPriceInput).attr('data-baseline-price', PricingMath.parseSafeNumber(restoredPrice, 0).toFixed(2));
          }
          self.renderPriceStalenessBadge(
            selectedOpt.data('price-date'),
            selectedOpt.data('price-age'),
            selectedOpt.data('staleness'),
            selectedOpt.data('valid-until'),
            $('#digital_price_staleness_badge'),
            null
          );
        }
      }
      self.debouncedRecalculate();
      self.showNotification('تمت إعادة حساب طباعة الديجيتال بنجاح', 'info');
    });

    // 10. زر النسخ السريع من الغلاف للداخلي
    $(document).on('click', '#btn_copy_cover_press_to_inner', function () {
      self.copyCoverPressToInner();
    });

    // 10.1 زر التطبيق السريع للموردين المعتمدين
    $(document).on('click', '#btn_apply_preferred_suppliers', function (e) {
      e.preventDefault();
      self.applyPreferredSuppliers();
    });

    // 11. زر نسخ الواتساب
    $(document).on('click', '#btn_copy_whatsapp, #btn_copy_quote_whatsapp', function (e) {
      e.preventDefault();
      self.generateWhatsAppQuote();
    });

    // 12. زر الحفظ كمسودة
    $(document).on('click', '#btn_save_draft', function (e) {
      e.preventDefault();
      const form = document.getElementById('order-form') || document.getElementById('orderForm');
      if (form) {
        let statusInput = document.getElementById('id_status');
        if (!statusInput) {
          statusInput = document.createElement('input');
          statusInput.type = 'hidden';
          statusInput.name = 'status';
          statusInput.id = 'id_status';
          form.appendChild(statusInput);
        }
        statusInput.value = 'draft';
        self.isDirty = false;
        $('#btn_save_order').trigger('click');
      }
    });

    // 14. التحقق قبل إرسال النموذج وتوسيع الأكورديونات المطوية
    const form = document.getElementById('order-form') || document.getElementById('orderForm');
    if (form) {
      form.addEventListener('submit', function (e) {
        self.sanitizePayloadOnSubmit();

        if (!form.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
          self.isSyncPromptHandled = false;
          self.validateAndUnfoldCollapsedSections(form);
        } else {
          self.isDirty = false;
          // منع النقر المزدوج
          const submitBtn = document.getElementById('btn_save_order');
          if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>جاري الحفظ والتسجيل...';
          }
        }
        form.classList.add('was-validated');
      });
    }
  }

  /**
   * استدعاء الحسابات مع Debounce ذكي (250ms للكتابة / 50ms للقوائم)
   */
  debouncedRecalculate(delay = 250) {
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => {
      requestAnimationFrame(() => {
        this.recalculate();
      });
    }, delay);
  }

  /**
   * التبديل بين نماذج المطبوعات وعناوين الخطوات
   */
  handleAnatomySwitch(type) {
    const cardStep3 = document.getElementById('card_step3_inner');
    const innerBook = document.getElementById('inner_book_section');
    const innerFolder = document.getElementById('inner_folder_section');
    const innerNcr = document.getElementById('inner_ncr_section');
    const closedContainer = document.getElementById('closed_size_container');
    const closedSwitch = document.getElementById('id_is_closed_size');

    // التحكم في ظهور سويتش المقاس المقفول
    if (['catalog', 'book', 'magazine', 'book_catalog', 'folder', 'folder_packaging', 'box', 'brochure'].includes(type)) {
      if (closedContainer) closedContainer.classList.remove('d-none');
      if (closedSwitch && !closedSwitch.dataset.manual) {
        closedSwitch.checked = true;
      }
    } else {
      if (closedContainer) closedContainer.classList.add('d-none');
      if (closedSwitch && !closedSwitch.dataset.manual) {
        closedSwitch.checked = false;
      }
    }

    const step3Header = document.getElementById('step3_header_title');
    if (step3Header) step3Header.textContent = `3. ${this.config.i18n.step3Inner}`;

    const headerTitle = document.getElementById('step2_header_title');

    this.currentArchetype = type;

    if (type === 'flyer' || type === 'single_sheet' || type === 'brochure' || type === 'business_card') {
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Print}`;
    } else if (type === 'catalog' || type === 'book' || type === 'magazine' || type === 'book_catalog') {
      if (innerBook) innerBook.classList.remove('d-none');
      if (innerFolder) innerFolder.classList.add('d-none');
      if (innerNcr) innerNcr.classList.add('d-none');
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Cover}`;
    } else if (type === 'folder' || type === 'box' || type === 'folder_packaging') {
      if (innerBook) innerBook.classList.add('d-none');
      if (innerFolder) innerFolder.classList.remove('d-none');
      if (innerNcr) innerNcr.classList.add('d-none');
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Folder}`;
    } else if (type === 'invoice' || type === 'receipt' || type === 'ncr') {
      if (innerBook) innerBook.classList.add('d-none');
      if (innerFolder) innerFolder.classList.add('d-none');
      if (innerNcr) innerNcr.classList.remove('d-none');
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Invoice}`;

      const innerPrintSelect = document.getElementById('id_inner_printing_type');
      if (innerPrintSelect) {
        innerPrintSelect.value = 'offset';
        $(innerPrintSelect).trigger('change');
      }
    }

    this.updatePrintingTypeUI();
    this.updateOpenDimensionsDisplay();
    this.updateGatesState();

    const orderTypeEl = document.getElementById('id_order_type');
    if (orderTypeEl) {
      orderTypeEl.value = type;
    }
  }



  /**
   * تطبيق مقاس المطبوع المختار والقفل الذكي
   */
  applySelectedProductSize() {
    const sizeSelect = document.getElementById('id_product_size');
    if (!sizeSelect) return;

    const widthInput = document.getElementById('id_width');
    const heightInput = document.getElementById('id_height');
    const selectedOpt = sizeSelect.options[sizeSelect.selectedIndex];
    const isCustom = !selectedOpt || selectedOpt.value === 'custom';
    const isLandscape = document.getElementById('orient_landscape')?.checked || false;

    if (isCustom) {
      if (widthInput) {
        widthInput.readOnly = false;
        widthInput.style.backgroundColor = 'var(--bg-card, #ffffff)';
        widthInput.style.cursor = 'text';
      }
      if (heightInput) {
        heightInput.readOnly = false;
        heightInput.style.backgroundColor = 'var(--bg-card, #ffffff)';
        heightInput.style.cursor = 'text';
      }
    } else {
      const rawW = PricingMath.parseSafeNumber(selectedOpt.dataset.width, 21);
      const rawH = PricingMath.parseSafeNumber(selectedOpt.dataset.height, 29.7);

      let finalW = isLandscape ? Math.max(rawW, rawH) : Math.min(rawW, rawH);
      let finalH = isLandscape ? Math.min(rawW, rawH) : Math.max(rawW, rawH);

      if (widthInput) {
        widthInput.value = finalW;
        widthInput.readOnly = true;
        widthInput.style.backgroundColor = 'var(--bg-light, #f8f9fa)';
        widthInput.style.cursor = 'not-allowed';
      }
      if (heightInput) {
        heightInput.value = finalH;
        heightInput.readOnly = true;
        heightInput.style.backgroundColor = 'var(--bg-light, #f8f9fa)';
        heightInput.style.cursor = 'not-allowed';
      }
    }
    this.updateOpenDimensionsDisplay();
  }

  /**
   * تحديث الأبعاد المفتوحة وعرض الكعب وحاسبة NCR
   */
  updateOpenDimensionsDisplay() {
    const isClosed = document.getElementById('id_is_closed_size')?.checked || false;
    const w = PricingMath.parseSafeNumber(document.getElementById('id_width')?.value, 21);
    const h = PricingMath.parseSafeNumber(document.getElementById('id_height')?.value, 29.7);
    const selectEl = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type') || document.getElementById('id_product_type');
    const type = selectEl?.options?.[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.dataset?.archetype || selectEl?.value || 'flyer';
    const openDir = document.querySelector('input[name="open_direction"]:checked')?.value || 'right';

    // تغيير مسميات الحقول
    const labelW = document.getElementById('label_width');
    const labelH = document.getElementById('label_height');
    if (labelW) labelW.textContent = isClosed ? 'العرض المقفول (سم)' : 'العرض (سم)';
    if (labelH) labelH.textContent = isClosed ? 'الارتفاع المقفول (سم)' : 'الارتفاع (سم)';

    const openDirGroup = document.getElementById('open_direction_toggle_group');
    if (openDirGroup) {
      openDirGroup.classList.toggle('d-none', !isClosed);
    }

    let multiplier = (type === 'brochure' || type === 'brochures') ? 3 : 2;
    let spineMm = 0;
    const bindingType = document.getElementById('id_binding_type')?.value || 'staple';
    const isHardcover = bindingType === 'hardcover';

    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      const pages = PricingMath.parseSafeNumber(document.getElementById('id_pages_count')?.value, 32);
      const innerSides = document.getElementById('id_inner_print_sides_mode')?.value || 'work_sheet';
      const innerPaperWeight = PricingMath.parseSafeNumber(document.getElementById('id_inner_paper_weight')?.value, 135);

      const sigInfo = PricingMath.calcSignatures(pages, w, h);
      const sigHint = document.getElementById('signatures_count_hint');
      if (sigHint) {
        if (innerSides === 'single') {
          sigHint.textContent = `${pages} ورقة وجه واحد (بلوك)`;
        } else {
          sigHint.textContent = `${this.config.i18n.signaturesEq} ${sigInfo.signaturesCount} ${this.config.i18n.signature} (${sigInfo.sigCapacity} صفحة/ملزمة)`;
        }
      }

      spineMm = PricingMath.calcSpineMm(pages, innerPaperWeight, bindingType, isHardcover);
      const spineDisplay = document.getElementById('spine_thickness_display');
      if (spineDisplay) spineDisplay.textContent = `${spineMm.toFixed(1)} مم`;

      // صمامات الأمان للتجليد
      const warnBox = document.getElementById('binding_feasibility_warning');
      const warnText = document.getElementById('binding_warning_text');
      if (warnBox && warnText) {
        if (bindingType === 'staple' && pages % 4 !== 0) {
          warnBox.classList.remove('d-none');
          warnText.textContent = 'تنبيه: عدد الصفحات يجب أن يقبل القسمة على 4 في التجليد الدبوس لضمان طي الملازم.';
        } else if (bindingType === 'staple' && pages > 64 && innerPaperWeight >= 135) {
          warnBox.classList.remove('d-none');
          warnText.textContent = 'تنبيه: عدد الصفحات كبير للتجليد الدبوس، يُنصح باختيار غراء حراري PUR لمنع نفخ الكتالوج.';
        } else if (bindingType === 'perfect_binding' && spineMm < 3.0) {
          warnBox.classList.remove('d-none');
          warnText.textContent = 'تنبيه: سمك الكعب أقل من 3 مم، يُفضل اختيار دبوس فرنسي سرج لضمان تماسك الصفحات.';
        } else {
          warnBox.classList.add('d-none');
        }
      }
    }

    // حساب مقاس الغلاف المفتوح
    let openW = w;
    let openH = h;
    if (isClosed) {
      if (openDir === 'top') {
        openW = w;
        openH = (h * multiplier) + (spineMm / 10);
      } else {
        if (isHardcover) {
          openW = (w * 2) + (spineMm / 10) + 4.6;
          openH = h + 3.6;
        } else {
          openW = (w * multiplier) + (spineMm / 10);
          openH = h;
        }
      }
    }

    const openText = document.getElementById('open_dims_text');
    if (openText) {
      openText.textContent = `${openW.toFixed(1).replace(/\.0$/, '')} × ${openH.toFixed(1).replace(/\.0$/, '')} سم`;
    }

    // حساب نهاية ترقيم دفاتر NCR
    const ncrStart = PricingMath.parseSafeNumber(document.getElementById('id_ncr_serial_start')?.value, 1001);
    const ncrCap = PricingMath.parseSafeNumber(document.getElementById('id_ncr_book_capacity')?.value, 50);
    const orderQty = PricingMath.parseSafeNumber(document.getElementById('id_quantity')?.value, 1);
    const ncrEnd = ncrStart + (ncrCap * orderQty) - 1;
    const ncrEndDisplay = document.getElementById('ncr_serial_end_display');
    if (ncrEndDisplay) ncrEndDisplay.textContent = ncrEnd.toLocaleString('en-US');

    // تحذير مقاس شيت الديجيتال
    const digitalWarning = document.getElementById('digital_sheet_size_warning');
    const coverType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    if (digitalWarning) {
      digitalWarning.classList.toggle('d-none', !(openW > 48.7 && coverType === 'digital'));
    }
  }

  /**
   * التوزيع الشبكي المتناسق والصمامات الذكية
   */
  updatePrintingTypeUI() {
    const coverType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    const innerType = document.getElementById('id_inner_printing_type')?.value || 'offset';
    const offsetSides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';
    const paperType = document.getElementById('id_paper_type')?.value || 'couche';
    const paperWeight = PricingMath.parseSafeNumber(document.getElementById('id_paper_weight')?.value, 300);
    const qty = PricingMath.parseSafeNumber(document.getElementById('id_quantity')?.value, 1000);

    const containerOffsetSides = document.getElementById('container_offset_sides');
    const containerStdSides = document.getElementById('container_standard_sides');
    if (containerOffsetSides) containerOffsetSides.classList.toggle('d-none', coverType !== 'offset');
    if (containerStdSides) containerStdSides.classList.toggle('d-none', coverType === 'offset' || coverType === 'none');

    // التوزيع الشبكي 3+3+3+3=12 vs 3+3+6=12
    const colCoverType = document.getElementById('col_cover_type_wrapper');
    const colSides = document.getElementById('col_print_sides_wrapper');
    const colFrontColors = document.getElementById('col_front_colors_wrapper');
    const colBackColors = document.getElementById('col_back_colors_or_sqm_wrapper');

    const contOffsetFront = document.getElementById('container_offset_front_colors');
    const contDigitalColor = document.getElementById('container_digital_color_mode');
    const contBannerColor = document.getElementById('container_banner_color_mode');
    const contScreenColor = document.getElementById('container_screen_colors');
    const contOffsetBack = document.getElementById('container_offset_back_colors');
    const contBannerSqm = document.getElementById('container_banner_sqm_input');

    const labelFront = document.getElementById('label_front_colors');
    const labelBack = document.getElementById('label_back_colors');

    if (coverType === 'none') {
      if (colCoverType) colCoverType.className = 'col-md-12';
      if (colSides) colSides.classList.add('d-none');
      if (colFrontColors) colFrontColors.classList.add('d-none');
      if (colBackColors) colBackColors.classList.add('d-none');
    } else if (coverType === 'digital_banner') {
      if (colCoverType) colCoverType.className = 'col-md-3';
      if (colSides) { colSides.className = 'col-md-3'; colSides.classList.remove('d-none'); }
      if (colFrontColors) { colFrontColors.className = 'col-md-3'; colFrontColors.classList.remove('d-none'); }
      if (colBackColors) { colBackColors.className = 'col-md-3'; colBackColors.classList.remove('d-none'); }

      if (contOffsetFront) contOffsetFront.classList.add('d-none');
      if (contDigitalColor) contDigitalColor.classList.add('d-none');
      if (contBannerColor) contBannerColor.classList.remove('d-none');
      if (contScreenColor) contScreenColor.classList.add('d-none');
      if (contOffsetBack) contOffsetBack.classList.add('d-none');
      if (contBannerSqm) contBannerSqm.classList.remove('d-none');
    } else if (coverType === 'offset') {
      if (offsetSides === 'work_sheet') {
        if (colCoverType) colCoverType.className = 'col-md-3';
        if (colSides) { colSides.className = 'col-md-3'; colSides.classList.remove('d-none'); }
        if (colFrontColors) { colFrontColors.className = 'col-md-3'; colFrontColors.classList.remove('d-none'); }
        if (colBackColors) { colBackColors.className = 'col-md-3'; colBackColors.classList.remove('d-none'); }

        if (contOffsetFront) contOffsetFront.classList.remove('d-none');
        if (contDigitalColor) contDigitalColor.classList.add('d-none');
        if (contBannerColor) contBannerColor.classList.add('d-none');
        if (contScreenColor) contScreenColor.classList.add('d-none');
        if (contOffsetBack) contOffsetBack.classList.remove('d-none');
        if (contBannerSqm) contBannerSqm.classList.add('d-none');

        if (labelFront) labelFront.textContent = 'ألوان الوجه';
        if (labelBack) labelBack.textContent = 'ألوان الظهر';
      } else {
        if (colCoverType) colCoverType.className = 'col-md-3';
        if (colSides) { colSides.className = 'col-md-3'; colSides.classList.remove('d-none'); }
        if (colFrontColors) { colFrontColors.className = 'col-md-6'; colFrontColors.classList.remove('d-none'); }
        if (colBackColors) colBackColors.classList.add('d-none');

        if (contOffsetFront) contOffsetFront.classList.remove('d-none');
        if (contDigitalColor) contDigitalColor.classList.add('d-none');
        if (contBannerColor) contBannerColor.classList.add('d-none');
        if (contScreenColor) contScreenColor.classList.add('d-none');
        if (contOffsetBack) contOffsetBack.classList.add('d-none');
        if (contBannerSqm) contBannerSqm.classList.add('d-none');

        if (labelFront) labelFront.textContent = 'ألوان التصميم';
      }
    } else {
      if (colCoverType) colCoverType.className = 'col-md-3';
      if (colSides) { colSides.className = 'col-md-3'; colSides.classList.remove('d-none'); }
      if (colFrontColors) { colFrontColors.className = 'col-md-6'; colFrontColors.classList.remove('d-none'); }
      if (colBackColors) colBackColors.classList.add('d-none');

      if (contOffsetFront) contOffsetFront.classList.add('d-none');
      if (contDigitalColor) contDigitalColor.classList.toggle('d-none', coverType !== 'digital');
      if (contBannerColor) contBannerColor.classList.add('d-none');
      if (contScreenColor) contScreenColor.classList.toggle('d-none', coverType !== 'screen');
      if (contOffsetBack) contOffsetBack.classList.add('d-none');
      if (contBannerSqm) contBannerSqm.classList.add('d-none');
    }

    // كروت تفاصيل الماكينات
    const coverOffsetFields = document.getElementById('cover_offset_fields');
    const coverDigitalFields = document.getElementById('cover_digital_fields');
    const coverBannerFields = document.getElementById('cover_banner_fields');
    const coverScreenFields = document.getElementById('cover_screen_fields');

    if (coverOffsetFields) coverOffsetFields.classList.toggle('d-none', coverType !== 'offset');
    if (coverDigitalFields) coverDigitalFields.classList.toggle('d-none', coverType !== 'digital');
    if (coverBannerFields) coverBannerFields.classList.toggle('d-none', coverType !== 'digital_banner');
    if (coverScreenFields) coverScreenFields.classList.toggle('d-none', coverType !== 'screen');

    // الصمامات الذكية الأربعة (مع فحص data-code والنص العربي لعدم الاعتماد على الـ ID فقط)
    const paperSelect = document.getElementById('id_paper_type');
    const selectedPaperOpt = paperSelect?.options[paperSelect?.selectedIndex];
    const paperCode = (selectedPaperOpt?.dataset?.code || selectedPaperOpt?.value || '').toLowerCase();
    const paperText = (selectedPaperOpt?.text || '').toLowerCase();

    const isSticker = paperCode.includes('sticker') || paperCode.includes('vinyl') || paperText.includes('ستيكر') || paperText.includes('لاصق');
    const stickerBadge = document.getElementById('sticker_guard_badge');
    if (stickerBadge) stickerBadge.classList.toggle('d-none', !isSticker);

    const isDuplex = paperCode.includes('duplex') || paperText.includes('دوبلكس');
    const duplexWarning = document.getElementById('duplex_greyback_warning');
    if (duplexWarning) duplexWarning.classList.toggle('d-none', !isDuplex);

    const gsmWarning = document.getElementById('digital_gsm_warning');
    if (gsmWarning) gsmWarning.classList.toggle('d-none', !(coverType === 'digital' && paperWeight > 350));

    const microWarning = document.getElementById('micro_qty_offset_warning');
    if (microWarning) microWarning.classList.toggle('d-none', !(coverType === 'offset' && qty <= 300));

    // حقول الداخلي
    const innerSides = document.getElementById('id_inner_print_sides_mode')?.value || 'work_sheet';
    const contInnerOffset = document.getElementById('container_inner_color_mode_offset');
    const contInnerSingle = document.getElementById('container_inner_color_mode_single');
    const contInnerDigital = document.getElementById('container_inner_color_mode_digital');
    const innerOffsetFields = document.getElementById('inner_offset_fields');

    if (innerType === 'offset') {
      if (contInnerDigital) contInnerDigital.classList.add('d-none');
      if (innerSides === 'single') {
        if (contInnerSingle) contInnerSingle.classList.remove('d-none');
        if (contInnerOffset) contInnerOffset.classList.add('d-none');
        if (innerOffsetFields) innerOffsetFields.classList.add('d-none');
      } else {
        if (contInnerSingle) contInnerSingle.classList.add('d-none');
        if (contInnerOffset) contInnerOffset.classList.remove('d-none');
        const innerColorMode = document.getElementById('id_inner_color_mode')?.value || 'all_color';
        if (innerOffsetFields) innerOffsetFields.classList.toggle('d-none', innerColorMode !== 'mixed');
      }
    } else if (innerType === 'digital') {
      if (contInnerSingle) contInnerSingle.classList.add('d-none');
      if (contInnerOffset) contInnerOffset.classList.add('d-none');
      if (contInnerDigital) contInnerDigital.classList.remove('d-none');
      if (innerOffsetFields) innerOffsetFields.classList.add('d-none');
    }
  }

  /**
   * التحديث المالي اللحظي الشامل في المتصفح حصراً (0ms Local Financial Reactivity)
   * يحسب الإجمالي النهائي وسعر القطعة وصافي الربح/النسبة ويزامن الحقول المخفية للباك إند
   */
  updateFinancialsLocally() {
    const qty = PricingMath.parseSafeNumber(document.getElementById('id_quantity')?.value, 1000);
    const safeQty = Math.max(1, qty);
    const extraCost = PricingMath.parseSafeNumber(document.getElementById('id_extra_cost')?.value, 0);
    const totalCost = (this.lastKnownTotalCost || 0) + extraCost;

    // أتعاب التصميم والتجهيز الفني بدون كسور
    const designType = document.getElementById('id_design_service_type')?.value || 'CUSTOMER_READY';
    const rawDesignFee = (designType !== 'CUSTOMER_READY')
      ? PricingMath.parseSafeNumber(document.getElementById('id_design_fee')?.value, 0)
      : 0;
    const designFee = Math.round(rawDesignFee);

    const profitMarginInput = document.getElementById('id_profit_margin');
    let marginPct = 30;
    let fixedProfit = 0;
    let productionTotal = 0;

    if (this.marginMode === 'fixed') {
      if (profitMarginInput) {
        const raw = profitMarginInput.value.trim();
        fixedProfit = raw === '' ? 0 : PricingMath.parseSafeNumber(raw, 0);
      }
      productionTotal = Math.ceil(totalCost + fixedProfit);
      marginPct = totalCost > 0 ? ((fixedProfit / totalCost) * 100) : 0;
    } else {
      if (profitMarginInput) {
        const raw = profitMarginInput.value.trim();
        marginPct = raw === '' ? 0 : PricingMath.parseSafeNumber(raw, 30);
      }
      fixedProfit = totalCost > 0 ? (totalCost * (marginPct / 100)) : 0;
      productionTotal = PricingMath.calcFinalPrice(totalCost, marginPct / 100);
    }

    const pureUnitPrice = productionTotal / safeQty;
    const grandTotal = productionTotal + designFee;

    // تحديث شاشات العرض المالية بالسايدبار
    const costLogEl = document.getElementById('cost_logistics_display');
    if (costLogEl) this.updateTextSafely(costLogEl, this.formatMoney(extraCost));

    const costDesignEl = document.getElementById('cost_design_display');
    if (costDesignEl) this.updateTextSafely(costDesignEl, `${designFee} ${this.currencySymbol}`);

    const sidebarDesignFeeEl = document.getElementById('sidebar_design_fee_display');
    if (sidebarDesignFeeEl) this.updateTextSafely(sidebarDesignFeeEl, designFee.toString());

    const rowDesignBreakdown = document.getElementById('row_cost_design_breakdown');
    const rowSidebarDesign = document.getElementById('row_sidebar_design_fee');
    if (designFee > 0) {
      if (rowDesignBreakdown) rowDesignBreakdown.classList.remove('d-none');
      if (rowSidebarDesign) rowSidebarDesign.classList.remove('d-none');
    } else {
      if (rowDesignBreakdown) rowDesignBreakdown.classList.add('d-none');
      if (rowSidebarDesign) rowSidebarDesign.classList.add('d-none');
    }

    const totalCostEl = document.getElementById('total_cost_display');
    if (totalCostEl) this.updateTextSafely(totalCostEl, this.formatMoney(totalCost));

    const unitPriceEl = document.getElementById('unit_price_display');
    if (unitPriceEl) this.updateTextSafely(unitPriceEl, this.formatNumber(pureUnitPrice));

    const finalTotalEl = document.getElementById('final_total_display');
    if (finalTotalEl) this.updateTextSafely(finalTotalEl, this.formatNumber(grandTotal));

    // تحديث المؤشر وشريط تقدم هامش الربح
    this.updateMarginUI(marginPct);

    // مزامنة الحقول المخفية للباك إند بدقة رقمين عشريين
    const designCostHidden = document.getElementById('id_design_cost');
    if (designCostHidden) designCostHidden.value = designFee.toFixed(2);

    const finalPriceHidden = document.getElementById('id_final_price');
    if (finalPriceHidden) finalPriceHidden.value = grandTotal.toFixed(2);

    const salePriceHidden = document.getElementById('id_sale_price');
    if (salePriceHidden) salePriceHidden.value = grandTotal.toFixed(2);

    const rawHidden = document.getElementById('id_profit_margin_raw');
    if (rawHidden) rawHidden.value = marginPct.toFixed(2);
  }

  /**
   * تحديث شريط ونسبة هامش الربح لحظياً (0ms Direct Reactivity)
   * يدعم النمطين المزدوجين: النسبة المئوية (%) أو المبلغ المقطوع (ج.م)
   */
  updateMarginUI(customVal = null) {
    let marginPct = 30;
    const marginInput = document.getElementById('id_profit_margin');
    const rawHidden = document.getElementById('id_profit_margin_raw');

    let fixedAmount = 0;
    const totalCost = this.lastKnownTotalCost || 0;

    if (this.marginMode === 'fixed') {
      // نمط المبلغ المقطوع بالجنيه (المستخدم أدخل مبلغاً مباشراً)
      if (marginInput) {
        const raw = marginInput.value.trim();
        fixedAmount = raw === '' ? 0 : PricingMath.parseSafeNumber(raw, 0);
      }
      if (totalCost > 0) {
        marginPct = parseFloat(((fixedAmount / totalCost) * 100).toFixed(2));
      } else {
        marginPct = 0;
      }
      // مزامنة النسبة المئوية للحقل المخفي المرسل للداتابيز والـ SSOT
      if (rawHidden) {
        rawHidden.value = marginPct.toFixed(2);
      }
    } else {
      // نمط النسبة المئوية المباشرة (%) (المستخدم أدخل نسبة مئوية)
      if (customVal !== null && !isNaN(customVal)) {
        marginPct = parseFloat(Number(customVal).toFixed(2));
      } else if (marginInput) {
        const raw = marginInput.value.trim();
        marginPct = raw === '' ? 0 : parseFloat(PricingMath.parseSafeNumber(raw, 30).toFixed(2));
      }
      fixedAmount = totalCost > 0 ? (totalCost * (marginPct / 100)) : 0;
      if (rawHidden) {
        rawHidden.value = marginPct.toFixed(2);
      }
    }

    const marginDisplay = document.getElementById('margin_percentage_display');
    const marginLabel = document.getElementById('margin_indicator_label');
    const marginBar = document.getElementById('margin_progress_bar');

    if (this.marginMode === 'fixed') {
      // المستخدم أدخل مبلغاً -> المؤشر يتحول لنسبة مئوية (%)
      if (marginLabel) {
        marginLabel.textContent = (this.config.i18n && this.config.i18n.achievedMarginRate) ? this.config.i18n.achievedMarginRate : 'النسبة المحققة:';
      }
      if (marginDisplay) {
        // إظهار الكسور إن وجدت فقط (مثل 30.5%) وبدون علامة عشرية إطلاقاً طالما رقم صحيح (30%)
        const formattedMargin = (marginPct % 1 === 0) ? marginPct.toFixed(0) : (marginPct % 0.1 === 0 ? marginPct.toFixed(1) : marginPct.toFixed(2));
        this.updateTextSafely(marginDisplay, `${formattedMargin}%`);
      }
    } else {
      // المستخدم أدخل نسبة مئوية -> المؤشر يتحول لصافي ربح بالجنيه (ج.م)
      if (marginLabel) {
        marginLabel.textContent = (this.config.i18n && this.config.i18n.netProfit) ? this.config.i18n.netProfit : 'صافي الربح:';
      }
      if (marginDisplay) {
        this.updateTextSafely(marginDisplay, this.formatMoney(fixedAmount));
      }
    }

    if (marginBar) {
      marginBar.style.transition = 'width 0.05s linear';
      marginBar.style.width = `${Math.min(100, Math.max(0, marginPct))}%`;
      marginBar.className = marginPct < 15
        ? 'progress-bar bg-danger'
        : (marginPct < 25 ? 'progress-bar bg-primary' : 'progress-bar bg-success');
    }
  }

  /**
   * التبديل بين نمط النسبة المئوية (%) والمبلغ المقطوع (ج.م)
   */
  setMarginMode(mode) {
    if (this.marginMode === mode) return;
    this.marginMode = mode;

    const selectEl = document.getElementById('id_margin_type');
    if (selectEl) {
      selectEl.value = (mode === 'fixed' ? 'fixed' : 'percentage');
    }
    const btnPercent = document.getElementById('btn_margin_mode_percent');
    const btnFixed = document.getElementById('btn_margin_mode_fixed');
    const badge = document.getElementById('margin_unit_badge');
    const input = document.getElementById('id_profit_margin');
    const label = document.getElementById('margin_input_label');
    const totalCost = this.lastKnownTotalCost || 0;

    if (mode === 'fixed') {
      if (btnPercent) btnPercent.classList.remove('active');
      if (btnFixed) btnFixed.classList.add('active');
      if (badge) badge.textContent = this.config.currencySymbol || 'ج.م';

      if (input) {
        // تحويل النسبة الحالية إلى مبلغ نقدي
        const currentPct = PricingMath.parseSafeNumber(input.value, 30);
        const fixedProfit = Math.round(totalCost * (currentPct / 100));
        input.value = fixedProfit;
        input.placeholder = fixedProfit > 0 ? fixedProfit : '0';
        input.removeAttribute('max'); // المبلغ يمكن أن يكون أي رقم
        input.setAttribute('step', '1');
      }
    } else {
      if (btnFixed) btnFixed.classList.remove('active');
      if (btnPercent) btnPercent.classList.add('active');
      if (badge) badge.textContent = '%';

      if (input) {
        // تحويل المبلغ النقدي إلى نسبة مئوية
        const currentFixed = PricingMath.parseSafeNumber(input.value, 0);
        let pct = 30;
        if (totalCost > 0) {
          pct = parseFloat(((currentFixed / totalCost) * 100).toFixed(2));
        }
        input.value = (pct % 1 === 0) ? pct.toFixed(0) : pct.toString();
        input.placeholder = '30';
        input.setAttribute('max', '500');
        input.setAttribute('step', '1');
      }
    }

    this.updateFinancialsLocally();
  }


  // ============================================================================
  // تفويض خط إنتاج طباعة الشيت والخامات (Sheet Printing & Materials Subsystem Delegation)
  // ============================================================================
  get isPaperCascadeUpdating() {
    return this.sheetPrinting ? this.sheetPrinting.isPaperCascadeUpdating : false;
  }
  set isPaperCascadeUpdating(val) {
    if (this.sheetPrinting) this.sheetPrinting.isPaperCascadeUpdating = val;
  }
  get isManualSheetsActive() {
    return this.sheetPrinting ? this.sheetPrinting.isManualSheetsActive : false;
  }
  set isManualSheetsActive(val) {
    if (this.sheetPrinting) this.sheetPrinting.isManualSheetsActive = val;
  }
  get manualGrossSheets() {
    return this.sheetPrinting ? this.sheetPrinting.manualGrossSheets : null;
  }
  set manualGrossSheets(val) {
    if (this.sheetPrinting) this.sheetPrinting.manualGrossSheets = val;
  }

  bindSupplierWatchers() {
    return this.sheetPrinting ? this.sheetPrinting.bindSupplierWatchers() : null;
  }
  bindPaperCardWatchers() {
    return this.sheetPrinting ? this.sheetPrinting.bindPaperCardWatchers() : null;
  }
  syncSelect2Options($select, options, selectedValue) {
    return this.sheetPrinting ? this.sheetPrinting.syncSelect2Options($select, options, selectedValue) : null;
  }
  updatePaperTypesForSupplier(supplierId, targetSelectId = '#id_paper_type') {
    return this.sheetPrinting ? this.sheetPrinting.updatePaperTypesForSupplier(supplierId, targetSelectId) : null;
  }
  updateSuppliersForPaperType(paperTypeId, targetSelectId = '#id_paper_supplier', userDriven = false) {
    return this.sheetPrinting ? this.sheetPrinting.updateSuppliersForPaperType(paperTypeId, targetSelectId, userDriven) : null;
  }
  handlePaperTypeChange(userDriven = false) {
    return this.sheetPrinting ? this.sheetPrinting.handlePaperTypeChange(userDriven) : null;
  }
  handlePaperSupplierChange(userDriven = false, isSupplierDirectChange = false) {
    return this.sheetPrinting ? this.sheetPrinting.handlePaperSupplierChange(userDriven, isSupplierDirectChange) : null;
  }
  initPieceSizesMasterList() {
    return this.sheetPrinting ? this.sheetPrinting.initPieceSizesMasterList() : null;
  }
  updatePieceSizesForSheet(sheetSize, sheetSizeId, sheetW, sheetH) {
    return this.sheetPrinting ? this.sheetPrinting.updatePieceSizesForSheet(sheetSize, sheetSizeId, sheetW, sheetH) : null;
  }
  handleSheetSizeChange(userDriven = false) {
    return this.sheetPrinting ? this.sheetPrinting.handleSheetSizeChange(userDriven) : null;
  }
  handlePaperWeightChange(userDriven = false) {
    return this.sheetPrinting ? this.sheetPrinting.handlePaperWeightChange(userDriven) : null;
  }
  fetchAvailablePaperOrigins(userDriven = false) {
    return this.sheetPrinting ? this.sheetPrinting.fetchAvailablePaperOrigins(userDriven) : null;
  }
  fetchLivePaperPrice(options = {}, isInner = false) {
    return this.sheetPrinting ? this.sheetPrinting.fetchLivePaperPrice(options, isInner) : null;
  }
  toggleManualGrossSheets() {
    return this.sheetPrinting ? this.sheetPrinting.toggleManualGrossSheets() : null;
  }
  resetPaperCascade() {
    return this.sheetPrinting ? this.sheetPrinting.resetPaperCascade() : null;
  }
  updateResolvedPackCapacity(isInitial = false, source = null) {
    return this.sheetPrinting ? this.sheetPrinting.updateResolvedPackCapacity(isInitial, source) : null;
  }
  updateResolvedInnerPackCapacity(isInitial = false, source = null) {
    return this.sheetPrinting ? this.sheetPrinting.updateResolvedInnerPackCapacity(isInitial, source) : null;
  }
  updateConvertedSheetPrice() {
    return this.sheetPrinting ? this.sheetPrinting.updateConvertedSheetPrice() : null;
  }
  copyCoverPaperToInner() {
    return this.sheetPrinting ? this.sheetPrinting.copyCoverPaperToInner() : null;
  }
  updateCoverPlatesUI() {
    return this.sheetPrinting ? this.sheetPrinting.updateCoverPlatesUI() : null;
  }
  updateInnerPlatesUI() {
    return this.sheetPrinting ? this.sheetPrinting.updateInnerPlatesUI() : null;
  }
  copyCoverPressToInner() {
    return this.sheetPrinting ? this.sheetPrinting.copyCoverPressToInner() : null;
  }
  applyPreferredSuppliers() {
    return this.sheetPrinting ? this.sheetPrinting.applyPreferredSuppliers() : null;
  }

  /**
   * عرض شارة صلاحية وحداثة السعر مع تاريخ التحديث والإنذار اللوني (Fresh / Expiring Soon / Stale)
   */
  renderPriceStalenessBadge(updatedAt, ageDays, status, validUntil, $badgeEl, $dateEl) {
    if (!$badgeEl || !$badgeEl.length) return;

    if (!updatedAt && !status) {
      $badgeEl.addClass('d-none').empty();
      if ($dateEl && $dateEl.length) $dateEl.addClass('d-none').empty();
      return;
    }

    let badgeClass = '';
    let iconClass = '';
    let labelText = '';

    switch (status) {
      case 'fresh':
        badgeClass = 'bg-success-subtle text-success border border-success-subtle';
        iconClass = 'fas fa-check-circle me-1';
        labelText = 'سعر حديث';
        break;
      case 'expiring_soon':
        badgeClass = 'bg-warning-subtle text-warning border border-warning-subtle';
        iconClass = 'fas fa-clock me-1';
        labelText = 'يوشك على الانتهاء';
        break;
      case 'stale':
        badgeClass = 'bg-danger-subtle text-danger border border-danger-subtle';
        iconClass = 'fas fa-exclamation-triangle me-1';
        labelText = 'سعر قديم / منتهي';
        break;
      case 'legacy_unconfirmed':
      default:
        badgeClass = 'bg-secondary-subtle text-secondary border border-secondary-subtle';
        iconClass = 'fas fa-history me-1';
        labelText = 'سعر سابق';
        break;
    }

    let tooltip = '';
    if (ageDays !== undefined && ageDays !== null && ageDays !== '') {
      tooltip = `محدث منذ ${ageDays} يوم`;
    }
    if (validUntil) {
      tooltip += ` (صالح حتى ${validUntil})`;
    }

    $badgeEl
      .removeClass('d-none bg-success-subtle text-success border-success-subtle bg-warning-subtle text-warning border-warning-subtle bg-danger-subtle text-danger border-danger-subtle bg-secondary-subtle text-secondary border-secondary-subtle bg-info-subtle text-info border-info-subtle')
      .addClass(badgeClass)
      .attr('title', tooltip)
      .html(`<i class="${iconClass}"></i>${labelText}`);

    if ($dateEl && $dateEl.length) {
      if (updatedAt) {
        $dateEl
          .removeClass('d-none')
          .html(`<i class="far fa-calendar-alt me-1"></i><span>${updatedAt}</span>${ageDays !== undefined && ageDays !== null && ageDays !== '' ? ` <span class="text-muted">(${ageDays} يوم)</span>` : ''}`);
      } else {
        $dateEl.addClass('d-none').empty();
      }
    }
  }

  /**
   * شارة السعر المعدل يدوياً لهذا الطلب
   */
  renderManualPriceBadge($badgeEl, $dateEl) {
    if (!$badgeEl || !$badgeEl.length) return;
    $badgeEl
      .removeClass('d-none bg-success-subtle text-success border-success-subtle bg-warning-subtle text-warning border-warning-subtle bg-danger-subtle text-danger border-danger-subtle bg-secondary-subtle text-secondary border-secondary-subtle')
      .addClass('bg-info-subtle text-info border border-info-subtle')
      .attr('title', 'تم تعديل السعر يدوياً لهذا الطلب')
      .html('<i class="fas fa-pen me-1"></i>سعر مخصص');
    if ($dateEl && $dateEl.length) {
      $dateEl.addClass('d-none').empty();
    }
  }

  /**
   * تفريغ شارة السعر وتاريخه
   */
  clearPriceStalenessBadge($badgeEl, $dateEl) {
    if ($badgeEl && $badgeEl.length) $badgeEl.addClass('d-none').empty();
    if ($dateEl && $dateEl.length) $dateEl.addClass('d-none').empty();
  }



  /**
   * المساعد الشامل لرسائل التنبيه والتوستر
   */
  showNotification(message, type = 'info') {
    if (typeof window.showNotification === 'function') {
      window.showNotification(message, type);
    } else if (typeof window.showToastr === 'function') {
      window.showToastr(message, type);
    } else if (typeof toastr !== 'undefined' && typeof toastr[type] === 'function') {
      toastr[type](message);
    } else {
      console.log(`[Notification ${type}]: ${message}`);
    }
  }

  /**
   * 1. التحقق من اكتمال كافة الحقول الإلزامية في الخطوة 1 (بيانات الطلب والعميل ومقاس المطبوع)
   * تشترط:
   *  - العميل (المسجل أو النقدي)
   *  - وصف الطلب
   *  - تاريخ التسعير
   *  - نوع المطبوع
   *  - الكمية المطلوبة (> 0)
   *  - مقاس المطبوع (> 0)
   */
  isStep1Complete() {
    const isCash = document.getElementById('id_is_cash_customer')?.checked || false;
    let hasCustomer = false;
    let missingField = null;
    let missingName = '';

    if (isCash) {
      const cashInput = document.getElementById('id_customer_name');
      hasCustomer = Boolean(cashInput && cashInput.value.trim() !== '');
      if (!hasCustomer) {
        missingField = cashInput;
        missingName = 'اسم العميل النقدي';
      }
    } else {
      const custSelect = document.getElementById('id_customer');
      hasCustomer = Boolean(custSelect && custSelect.value !== '');
      if (!hasCustomer) {
        missingField = custSelect;
        missingName = 'العميل';
      }
    }

    const titleInput = document.getElementById('id_title');
    const hasTitle = Boolean(titleInput && titleInput.value.trim() !== '');
    if (!missingField && !hasTitle) {
      missingField = titleInput;
      missingName = 'وصف الطلب';
    }

    const dateInput = document.getElementById('id_order_date');
    const hasDate = Boolean(dateInput && dateInput.value.trim() !== '');
    if (!missingField && !hasDate) {
      missingField = dateInput;
      missingName = 'تاريخ التسعير';
    }

    const productTypeSelect = document.getElementById('id_product_type') || document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    const hasProductType = Boolean(productTypeSelect && productTypeSelect.value !== '');
    if (!missingField && !hasProductType) {
      missingField = productTypeSelect;
      missingName = 'نوع المطبوع';
    }

    const qty = PricingMath.parseSafeNumber(document.getElementById('id_quantity')?.value, 0);
    const hasQty = qty > 0;
    if (!missingField && !hasQty) {
      missingField = document.getElementById('id_quantity');
      missingName = 'الكمية المطلوبة';
    }

    const w = PricingMath.parseSafeNumber(document.getElementById('id_width')?.value, 0);
    const h = PricingMath.parseSafeNumber(document.getElementById('id_height')?.value, 0);
    const hasDimensions = (w > 0 && h > 0);
    if (!missingField && !hasDimensions) {
      missingField = document.getElementById('id_width') || document.getElementById('id_product_size');
      missingName = 'مقاس المطبوع';
    }

    const isComplete = (hasCustomer && hasTitle && hasDate && hasQty && hasDimensions && hasProductType);
    return { isComplete, missingField, missingName };
  }

  /**
   * تحديث ومزامنة حالة انتظار المونتاج الذكي (Montage Waiting State & Studio Activation)
   */
  updateMontageWaitingState() {
    const widthEl = document.getElementById('id_width');
    const heightEl = document.getElementById('id_height');
    const qtyEl = document.getElementById('id_quantity');

    const w = PricingMath.parseSafeNumber(widthEl?.value, 0);
    const h = PricingMath.parseSafeNumber(heightEl?.value, 0);
    const q = PricingMath.parseSafeNumber(qtyEl?.value, 0);

    const overlay = document.getElementById('montage_waiting_overlay');
    const statusBadge = document.getElementById('montage_status_indicator');
    const isReady = (w >= 3 && h >= 3 && q >= 1);

    if (isReady) {
      if (overlay) {
        overlay.classList.add('d-none');
      }
      if (statusBadge) {
        statusBadge.className = 'badge bg-success-subtle text-success border border-success-subtle small';
        statusBadge.innerHTML = '<i class="fas fa-check-circle me-1"></i>جاهز ومفعل للحساب';
      }
      // إعادة ضبط مقاس Select2 لمنع انكماش القائمة عند إزالة الـ Overlay
      const $pieceSelect = $('#id_piece_size');
      if ($pieceSelect.length && $pieceSelect.hasClass('select2-hidden-accessible')) {
        $pieceSelect.select2({ width: '100%', dir: 'rtl' });
      }
    } else {
      if (overlay) {
        overlay.classList.remove('d-none');
      }
      if (statusBadge) {
        statusBadge.className = 'badge bg-secondary-subtle text-secondary border border-secondary-subtle small';
        statusBadge.innerHTML = '<i class="fas fa-clock me-1"></i>بانتظار المقاس والكمية';
      }
    }

    // تنبيه أبعاد المطبوع الكبيرة
    const oversizedAlert = document.getElementById('oversized_montage_alert');
    if (oversizedAlert) {
      if ((w > 100 || h > 100) || (w > 70 && h > 70)) {
        oversizedAlert.classList.remove('d-none');
      } else {
        oversizedAlert.classList.add('d-none');
      }
    }
  }

  /**
   * فحص وتنبيه أتعاب التصميم الصفرية في حال اختيار تصميم جديد
   */
  checkDesignZeroFeeAlert() {
    const sType = $('#id_design_service_type').val();
    const feeVal = parseFloat($('#id_design_fee').val()) || 0;
    const alertEl = $('#design_zero_fee_alert');
    if (!alertEl.length) return;

    if (sType === 'NEW_CONCEPT' && feeVal === 0) {
      alertEl.removeClass('d-none');
    } else {
      alertEl.addClass('d-none');
    }
  }

  /**
   * 2. مزامنة وتحديث حالة إظهار وإخفاء الأقسام (الخطوة 2 و 3) في الواجهة
   */
  updateGatesState() {
    this.updateMontageWaitingState();
    const gateStatus = this.isStep1Complete();
    const isDone = gateStatus.isComplete;

    const cardStep2 = document.getElementById('card_step2_cover');
    const cardStep3 = document.getElementById('card_step3_inner');
    const btnProceed = document.getElementById('btn_proceed_to_step2');
    const techSummaryText = document.getElementById('step1_technical_summary');
    const badge = document.getElementById('step1_status_badge');
    const badgeText = document.getElementById('step1_status_badge_text');
    const sidebarAlert = document.getElementById('sidebar_commit_gate_alert');
    const sidebarText = document.getElementById('sidebar_commit_status_text');

    // استنتاج نوع المطبوع الحالي
    const selectEl = document.getElementById('id_product_type') || document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    const type = this.currentArchetype || selectEl?.options?.[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.dataset?.archetype || selectEl?.value || 'flyer';
    const typeNeedsInner = ['catalog', 'book', 'magazine', 'book_catalog', 'folder', 'box', 'folder_packaging', 'invoice', 'receipt', 'ncr'].includes(type);

    // صمام الحماية: منع أي إعادة رسم للـ DOM والأيقونات طالما لم تتغير حالة البوابة
    const gateSignature = `${isDone}_${type}_${gateStatus.missingName || ''}`;
    if (this._lastGateSignature === gateSignature) {
      return;
    }
    this._lastGateSignature = gateSignature;

    if (isDone) {
      // 1. إظهار الخطوة 2 بالكامل
      if (cardStep2) {
        const wasHidden2 = cardStep2.classList.contains('d-none');
        cardStep2.classList.remove('d-none');
        if (wasHidden2) {
          this.reinitSelect2InContainer(cardStep2);
        }
      }

      // 2. إظهار الخطوة 3 فقط إذا كان نوع المطبوع يتطلب ذلك
      if (cardStep3) {
        if (typeNeedsInner) {
          const wasHidden3 = cardStep3.classList.contains('d-none');
          cardStep3.classList.remove('d-none');
          if (wasHidden3) {
            this.reinitSelect2InContainer(cardStep3);
          }
        } else {
          cardStep3.classList.add('d-none');
        }
      }

      // 3. تحديث شارة الخطوة 1
      if (badge) {
        badge.className = 'badge bg-success-subtle text-success border border-success-subtle px-2 py-1 small';
        badge.innerHTML = '<i class="fas fa-check-circle me-1"></i>بيانات مكتملة';
      }

      // 4. تحديث زر المتابعة
      if (btnProceed) {
        btnProceed.disabled = false;
        btnProceed.className = 'btn btn-primary px-4 fw-bold shadow-sm';
        btnProceed.innerHTML = '<span>المتابعة لمواصفات الطباعة والخامات</span><i class="fas fa-chevron-down ms-2"></i>';
      }

      // 5. تحديث ملخص الخطوة 1
      if (techSummaryText) {
        techSummaryText.innerHTML = '<i class="fas fa-check-circle text-success me-1"></i>بيانات الطلب والعميل مكتملة وجاهزة لتخصيص الخامات';
      }

      // 6. تحديث شريط السايدبار
      if (sidebarAlert && sidebarText) {
        sidebarAlert.className = 'alert alert-success-subtle border border-success-subtle py-2 px-3 mb-2 small text-center text-success';
        sidebarText.innerHTML = '<i class="fas fa-check-double text-success me-1"></i>البيانات مكتملة — جاهز للاعتماد وأمر الشغل';
      }
    } else {
      // الخطوة 1 غير مكتملة: إخفاء الخطوتين 2 و 3 تماماً!
      if (cardStep2) {
        cardStep2.classList.add('d-none');
      }
      if (cardStep3) {
        cardStep3.classList.add('d-none');
      }

      // تحديث شارة الخطوة 1
      if (badge) {
        badge.className = 'badge bg-warning-subtle text-warning border border-warning-subtle px-2 py-1 small';
        badge.innerHTML = `<i class="fas fa-exclamation-circle me-1"></i>مطلوب: ${gateStatus.missingName || 'بيانات الطلب والعميل'}`;
      }

      // تحديث زر المتابعة ليكون منبهاً وموجهاً
      if (btnProceed) {
        btnProceed.disabled = false;
        btnProceed.className = 'btn btn-outline-secondary px-4 fw-bold';
        btnProceed.innerHTML = '<i class="fas fa-lock me-2 text-warning"></i><span>أكمل بيانات الطلب لإظهار الأقسام</span>';
      }

      // تحديث ملخص الخطوة 1
      if (techSummaryText) {
        techSummaryText.innerHTML = `<i class="fas fa-exclamation-circle text-warning me-1"></i>يرجى ملء [${gateStatus.missingName || 'الحقول المطلوبة'}] لإظهار مواصفات الطباعة والخامات`;
      }

      // تحديث شريط السايدبار
      if (sidebarAlert && sidebarText) {
        sidebarAlert.className = 'alert alert-light border border-secondary-subtle py-2 px-3 mb-2 small text-center text-muted';
        sidebarText.innerHTML = '<i class="fas fa-lock text-warning me-1"></i>بانتظار استكمال بيانات الطلب والعميل لإظهار الأقسام والتسعير';
      }

      // تفريغ شاشات الحسابات
      this.clearLiveCalculateDisplays();
    }
  }

  /**
   * إدارة وتحديث حالة خمول/تنشيط الأقسام المعتمدة على الموردين (Zero-Leak Gating Architecture)
   * تضمن عدم ظهور تكاليف يتيمة أو أسعار عشوائية عندما لا يتم اختيار المورد
   */
  updateSupplierDependentSections() {
    // 1. الغلاف - كارت تسعير الورق
    const paperSupplier = $('#id_paper_supplier').val();
    const paperSource = $('input[name="paper_source"]:checked').val() || 'purchase';
    const paperPriceInput = document.getElementById('id_paper_sheet_price');
    const hasPaperManual = Boolean(paperPriceInput && paperPriceInput.dataset.manual === 'true');
    const isPaperActive = (paperSource === 'customer_supplied') || (paperSource === 'warehouse') || Boolean(paperSupplier) || hasPaperManual;
    const $coverPaperWrapper = $('#cover_paper_pricing_fields_wrapper');
    if ($coverPaperWrapper.length) {
      if (isPaperActive) {
        $coverPaperWrapper.removeClass('is-dormant').addClass('is-active');
      } else {
        $coverPaperWrapper.addClass('is-dormant').removeClass('is-active');
      }
    }

    // 2. الغلاف - مطبعة أوفست
    const coverPressSup = $('#id_cover_offset_supplier').val();
    const coverPressRateInput = document.getElementById('id_press_rate');
    const hasCoverPressManual = Boolean(coverPressRateInput && coverPressRateInput.dataset.manual === 'true');
    const isCoverPressActive = Boolean(coverPressSup) || hasCoverPressManual;
    const $coverPressWrapper = $('#cover_offset_press_fields_wrapper');
    if ($coverPressWrapper.length) {
      if (isCoverPressActive) {
        $coverPressWrapper.removeClass('is-dormant').addClass('is-active');
      } else {
        $coverPressWrapper.addClass('is-dormant').removeClass('is-active');
      }
    }

    // 3. الغلاف - فصل زنكات CTP
    const coverCtpSup = $('#id_cover_ctp_supplier').val();
    const coverPlatePriceInput = document.getElementById('id_plate_price');
    const hasCoverCtpManual = Boolean(coverPlatePriceInput && coverPlatePriceInput.dataset.manual === 'true');
    const isCoverPlatesArchived = document.getElementById('id_is_plates_archived')?.checked || document.getElementById('id_plates_option')?.value === 'archived';
    const isCoverCtpActive = (!isCoverPlatesArchived && (Boolean(coverCtpSup) || hasCoverCtpManual));
    const $coverCtpWrapper = $('#cover_ctp_pricing_wrapper');
    if ($coverCtpWrapper.length) {
      if (isCoverCtpActive) {
        $coverCtpWrapper.removeClass('is-dormant').addClass('is-active');
      } else {
        $coverCtpWrapper.addClass('is-dormant').removeClass('is-active');
      }
    }

    // 4. الغلاف - مركز ديجيتال
    const coverDigitalSup = $('#id_cover_digital_supplier').val();
    const coverDigitalPriceInput = document.getElementById('id_digital_sheet_price');
    const hasCoverDigitalManual = Boolean(coverDigitalPriceInput && coverDigitalPriceInput.dataset.manual === 'true');
    const isCoverDigitalActive = Boolean(coverDigitalSup) || hasCoverDigitalManual;
    const $coverDigitalWrapper = $('#cover_digital_fields_wrapper');
    if ($coverDigitalWrapper.length) {
      if (isCoverDigitalActive) {
        $coverDigitalWrapper.removeClass('is-dormant').addClass('is-active');
      } else {
        $coverDigitalWrapper.addClass('is-dormant').removeClass('is-active');
      }
    }

    // 5. الداخلي - كارت تسعير الورق
    const innerPaperSup = $('#id_inner_paper_supplier').val();
    const effectiveInnerPaperSup = innerPaperSup || paperSupplier;
    const innerPaperPriceInput = document.getElementById('id_inner_sheet_price');
    const hasInnerPaperManual = Boolean(innerPaperPriceInput && innerPaperPriceInput.dataset.manual === 'true');
    const isInnerPaperActive = (paperSource === 'customer_supplied') || (paperSource === 'warehouse') || Boolean(effectiveInnerPaperSup) || hasInnerPaperManual;
    const $innerPaperWrapper = $('#inner_paper_pricing_fields_wrapper');
    if ($innerPaperWrapper.length) {
      if (isInnerPaperActive) {
        $innerPaperWrapper.removeClass('is-dormant').addClass('is-active');
      } else {
        $innerPaperWrapper.addClass('is-dormant').removeClass('is-active');
      }
    }

    // 6. الداخلي - مطبعة أوفست
    const innerPressSup = $('#id_inner_offset_supplier').val();
    const innerPressRateInput = document.getElementById('id_inner_press_rate');
    const hasInnerPressManual = Boolean(innerPressRateInput && innerPressRateInput.dataset.manual === 'true');
    const isInnerPressActive = Boolean(innerPressSup) || hasInnerPressManual;
    const $innerPressWrapper = $('#inner_offset_press_fields_wrapper');
    if ($innerPressWrapper.length) {
      if (isInnerPressActive) {
        $innerPressWrapper.removeClass('is-dormant').addClass('is-active');
      } else {
        $innerPressWrapper.addClass('is-dormant').removeClass('is-active');
      }
    }

    // 7. الداخلي - فصل زنكات CTP
    const innerCtpSup = $('#id_inner_ctp_supplier').val();
    const innerPlatePriceInput = document.getElementById('id_inner_plate_price');
    const hasInnerCtpManual = Boolean(innerPlatePriceInput && innerPlatePriceInput.dataset.manual === 'true');
    const isInnerPlatesArchived = document.getElementById('id_is_inner_plates_archived')?.checked || document.getElementById('id_inner_plates_option')?.value === 'archived';
    const isInnerCtpActive = (!isInnerPlatesArchived && (Boolean(innerCtpSup) || hasInnerCtpManual));
    const $innerCtpWrapper = $('#inner_ctp_pricing_wrapper');
    if ($innerCtpWrapper.length) {
      if (isInnerCtpActive) {
        $innerCtpWrapper.removeClass('is-dormant').addClass('is-active');
      } else {
        $innerCtpWrapper.addClass('is-dormant').removeClass('is-active');
      }
    }

    // 8. الداخلي - مركز ديجيتال
    const innerDigitalSup = $('#id_inner_digital_supplier').val();
    const innerColorPriceInput = document.getElementById('id_digital_inner_color_price');
    const innerBwPriceInput = document.getElementById('id_digital_inner_bw_price');
    const hasInnerDigitalManual = (innerColorPriceInput && innerColorPriceInput.dataset.manual === 'true') ||
                                  (innerBwPriceInput && innerBwPriceInput.dataset.manual === 'true');
    const isInnerDigitalActive = Boolean(innerDigitalSup) || hasInnerDigitalManual;
    const $innerDigitalFields = $('#inner_digital_fields');
    if ($innerDigitalFields.length) {
      if (isInnerDigitalActive) {
        $innerDigitalFields.removeClass('is-dormant').addClass('is-active');
      } else {
        $innerDigitalFields.addClass('is-dormant').removeClass('is-active');
      }
    }
  }

  /**
   * إعادة تهيئة مكتبات select2 داخل الحاوية عند إظهارها
   */
  reinitSelect2InContainer(container) {
    if (typeof $.fn !== 'undefined' && typeof $.fn.select2 !== 'undefined') {
      $(container).find('.select2-filter').each(function () {
        if ($(this).data('select2')) {
          $(this).select2('destroy');
        }
        $(this).select2({ width: '100%', dir: 'rtl', language: 'ar' });
      });
    }
  }

  /**
   * تفريغ شاشات الحسابات اللحظية عند عدم استيفاء المعطيات الفنية
   */
  clearLiveCalculateDisplays(force = false) {
    if (!force && this.lastKnownTotalCost > 0) {
      // تثبيت الحالة: الحفاظ على استقرار الأرقام المحسوبة ومنع مسحها لشرطات أثناء التعديل اللحظي
      return;
    }
    const sym = this.config.currencySymbol || '';
    $('#cost_paper_display').text(`-- ${sym}`);
    $('#cost_printing_display').text(`-- ${sym}`);
    $('#cost_finishing_display').text(`-- ${sym}`);
    $('#cost_binding_display').text(`-- ${sym}`);
    $('#total_cost_display').text(`-- ${sym}`);
    $('#unit_price_display').text('--');
    $('#final_total_display').text('--');
    $('#step2_cost_badge').text(`-- ${sym}`);
    $('#step3_cost_badge').text(`-- ${sym}`);

    // تصفير المونتاج وإظهار علامة الانتظار (-) حتى تكتمل بيانات الحساب
    if (!this.isManualMontage) {
      $('#id_montage_count').val('').attr('placeholder', '-');
      $('#id_montage_piece_name').text('/ --');
      $('#press_montage_ref_val').text('- / --');
      $('#parent_yield_val').text('-- قطعة');
      $('#btn_montage_minus').prop('disabled', true);
      $('#btn_montage_plus').prop('disabled', true);
      $('#manual_montage_indicator').addClass('d-none');
    }
  }

  /**
   * 4. ربط زر التوجيه والانتقال بين الخطوات
   */
  bindStepNavigation() {
    const self = this;
    $(document).on('click', '#btn_proceed_to_step2', function (e) {
      e.preventDefault();
      const status = self.isStep1Complete();
      if (!status.isComplete) {
        self.showNotification(`يرجى إكمال [${status.missingName}] أولاً لإظهار تفاصيل الورق والطباعة`, 'warning');
        if (status.missingField) {
          const $field = $(status.missingField);
          if ($field.hasClass('select2-hidden-accessible')) {
            $field.select2('open');
          } else {
            $field.focus();
          }
          $field.addClass('is-invalid');
          setTimeout(() => $field.removeClass('is-invalid'), 3000);
          status.missingField.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
      }

      // عمل Smooth Scroll أنيق لرأس الخطوة الثانية مع تعويض الشريط العلوي لظهور العنوان بالكامل
      const step2Card = document.getElementById('card_step2_cover');
      if (step2Card) {
        const yOffset = -90; // مسافة أمان تضمن ظهور رأس القسم وشارة التكلفة بالكامل أسفل الشريط العلوي
        const y = step2Card.getBoundingClientRect().top + window.pageYOffset + yOffset;
        window.scrollTo({
          top: Math.max(0, y),
          behavior: 'smooth'
        });
      }
    });
  }

  /**
   * 5. حراسة الحفظ عبر البوابة التجارية الصارمة + فحص مزامنة أسعار الموردين (Option B)
   */
  bindCommercialCommitGuards() {
    const self = this;

    const guardSubmit = function (e) {
      const status = self.isStep1Complete();
      if (!status.isComplete) {
        e.preventDefault();
        e.stopPropagation();

        self.showNotification(`لا يمكن حفظ أمر الشغل: يرجى استكمال [${status.missingName}] أولاً`, 'error');

        if (status.missingField) {
          const $field = $(status.missingField);
          if ($field.hasClass('select2-hidden-accessible')) {
            $field.select2('open');
          } else {
            $field.focus();
          }
          $field.addClass('is-invalid');
          setTimeout(() => $field.removeClass('is-invalid'), 4000);

          status.missingField.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        self.isSyncPromptHandled = false;
        return false;
      }

      // إذا تم تأكيد/تجاوز فحص الأسعار مسبقاً، نسمح باستكمال الحفظ مباشرة
      if (self.isSyncPromptHandled) {
        return true;
      }

      // فحص وجود أي تعديل على أسعار الوحدة الصافية للموردين
      const changedPrices = self.detectChangedSupplierPrices();
      if (changedPrices.length > 0 && typeof Swal !== 'undefined') {
        e.preventDefault();
        e.stopPropagation();

        self.promptSupplierPriceSync(changedPrices, () => {
          self.isSyncPromptHandled = true;
          const targetForm = document.getElementById('order-form') || document.getElementById('orderForm');
          if (targetForm) {
            self.sanitizePayloadOnSubmit();
            if (targetForm.requestSubmit) {
              targetForm.requestSubmit();
            } else {
              targetForm.submit();
            }
          }
        });
        return false;
      }

      return true;
    };

    $(document).on('click', '#btn_save_order', guardSubmit);
    $(document).on('submit', '#order-form, #orderForm', guardSubmit);
  }

  /**
   * تهيئة وتثبيت الأسعار المرجعية للموردين عند فتح الشاشة
   */
  initBaselinePrices() {
    OrderFormUIController.PRICING_REGISTRY.forEach(f => {
      const $el = $(f.id);
      if (!$el.length) return;
      const $supp = $(f.supplier_sel);
      const val = PricingMath.parseSafeNumber($el.val(), 0);
      const suppId = $supp.length ? $supp.val() : null;
      if (suppId && val > 0) {
        if (!$el.attr('data-baseline-price')) {
          $el.attr('data-baseline-price', val.toFixed(2));
          $el.attr('data-supplier-id', suppId);
          $el.attr('data-item-label', f.default_label);
          $el.attr('data-unit-label', f.unit);
          const svcId = f.service_id_sel ? $(f.service_id_sel).val() : null;
          if (svcId) $el.attr('data-service-id', svcId);
        }
      }
    });
  }

  /**
   * فحص ورصد أي تعديلات على أسعار الوحدة الصافية للموردين (خام أو خدمات)
   */
  detectChangedSupplierPrices() {
    const changed = [];
    const hasInner = $('#card_step3_inner').length && !$('#card_step3_inner').hasClass('d-none');
    const coverType = $('#id_cover_printing_type').val() || 'offset';
    const innerType = $('#id_inner_printing_type').val() || 'offset';
    const paperSource = $('input[name="paper_source"]:checked').val() || 'purchase';
    const isCoverPlatesArchived = document.getElementById('id_is_plates_archived')?.checked || document.getElementById('id_plates_option')?.value === 'archived';
    const isInnerPlatesArchived = document.getElementById('id_is_inner_plates_archived')?.checked || document.getElementById('id_inner_plates_option')?.value === 'archived';

    OrderFormUIController.PRICING_REGISTRY.forEach(f => {
      // 1. استبعاد حقول الداخلي كلياً للأصناف المفردة (فلاير، كروت، علب)
      if (f.is_inner && !hasInner) return;

      // 2. استبعاد ورق المخزن أو خامة العميل
      if (f.service_type === 'paper' && (paperSource === 'warehouse' || paperSource === 'customer_supplied')) return;

      // 3. استبعاد زنكات الأرشيف
      if (f.service_type === 'ctp') {
        if (!f.is_inner && isCoverPlatesArchived) return;
        if (f.is_inner && isInnerPlatesArchived) return;
      }

      // 4. استبعاد ما لا يتطابق مع نوع الطباعة
      if (!f.is_inner) {
        if (coverType === 'offset' && f.service_type === 'digital') return;
        if (coverType === 'digital' && (f.service_type === 'offset' || f.service_type === 'ctp')) return;
        if (coverType === 'none') return;
      } else {
        if (innerType === 'offset' && f.service_type === 'digital') return;
        if (innerType === 'digital' && (f.service_type === 'offset' || f.service_type === 'ctp')) return;
      }

      const $el = $(f.id);
      if (!$el.length) return;
      const $supp = $(f.supplier_sel);
      const suppId = $el.attr('data-supplier-id') || ($supp.length ? $supp.val() : null);
      if (!suppId) return;

      const currentVal = PricingMath.parseSafeNumber($el.val(), 0);
      const baselineVal = PricingMath.parseSafeNumber($el.attr('data-baseline-price'), 0);

      if (baselineVal > 0 && currentVal > 0 && Math.abs(currentVal - baselineVal) >= 0.01) {
        const suppName = ($supp.find('option:selected').text() || 'المورد').replace(/⭐.*$/, '').trim();
        const itemLabel = $el.attr('data-item-label') || f.default_label;
        const unitLabel = $el.attr('data-unit-label') || f.unit;
        const svcId = $el.attr('data-service-id') || (f.service_id_sel ? $(f.service_id_sel).val() : null) || null;
        const formula = $el.attr('data-formula') || null;

        // فصل مواصفات الداخلي عن الغلاف بدقة تامة
        let sheetSize = '';
        let gsm = '';
        let paperTypeId = null;
        let bedSize = null;

        if (f.is_inner) {
          sheetSize = $('#id_inner_sheet_size').val() || '';
          gsm = $('#id_inner_paper_weight').val() || '';
          paperTypeId = $('#id_inner_paper_type').val() || null;
          if (f.machine_sel) {
            bedSize = $(f.machine_sel).find('option:selected').data('bed') || $('#id_inner_press_bed_size').val() || null;
          }
        } else {
          sheetSize = $('#id_sheet_size').val() || '';
          gsm = $('#id_paper_weight').val() || '';
          paperTypeId = $('#id_paper_type').val() || null;
          if (f.machine_sel) {
            bedSize = $(f.machine_sel).find('option:selected').data('bed') || null;
          }
        }

        changed.push({
          field_id: f.id,
          service_id: svcId,
          supplier_id: suppId,
          supplier_name: suppName,
          item_label: itemLabel,
          unit_label: unitLabel,
          original_price: baselineVal,
          new_price: currentVal,
          service_type: f.service_type,
          pricing_formula: formula,
          gsm: gsm,
          sheet_size: sheetSize,
          paper_type_id: paperTypeId,
          bed_size: bedSize,
          is_inner: f.is_inner
        });
      }
    });

    return changed;
  }

  /**
   * عرض نافذة تأكيد SweetAlert المجمعة (الخيار ب) لتحديث الأسعار المرجعية
   */
  promptSupplierPriceSync(changedPrices, onComplete) {
    const sym = this.config.currencySymbol || 'ج.م';
    let itemsHtml = '<div class="text-end my-3" style="max-height: 250px; overflow-y: auto;">';
    changedPrices.forEach((cp, idx) => {
      itemsHtml += `
        <div class="form-check p-2 mb-2 border rounded bg-light d-flex align-items-center justify-content-between" dir="rtl">
          <label class="form-check-label small mb-0 fw-bold text-dark cursor-pointer flex-grow-1 text-end pe-2" for="sync_chk_${idx}">
            <span class="d-block text-primary">${cp.supplier_name} — ${cp.item_label}</span>
            <span class="text-muted fw-normal">
              من <strong>${cp.original_price.toFixed(2)}</strong> إلى <strong class="text-success">${cp.new_price.toFixed(2)}</strong> ${sym} / ${cp.unit_label}
            </span>
          </label>
          <input class="form-check-input ms-0 me-2" type="checkbox" id="sync_chk_${idx}" data-idx="${idx}" checked style="cursor: pointer; width: 1.25em; height: 1.25em;">
        </div>
      `;
    });
    itemsHtml += '</div>';

    Swal.fire({
      title: 'تحديث الأسعار المرجعية للموردين',
      html: `
        <p class="text-muted small mb-1">تم تعديل أسعار بعض خدمات أو خامات الموردين في هذا الطلب.</p>
        <p class="fw-bold text-dark mb-2">هل ترغب في تحديث الأسعار المرجعية للموردين المحددين في النظام بتاريخ اليوم؟</p>
        ${itemsHtml}
      `,
      icon: 'question',
      showCancelButton: true,
      showDenyButton: true,
      confirmButtonText: '<i class="fas fa-check-circle me-1"></i> نعم، حدّث الأسعار المحددة',
      denyButtonText: '<i class="fas fa-arrow-left me-1"></i> لا، استمر بتسعير هذا الطلب فقط',
      cancelButtonText: 'إلغاء والتراجع',
      confirmButtonColor: 'var(--bs-primary, #0d6efd)',
      denyButtonColor: 'var(--bs-secondary, #6c757d)',
      cancelButtonColor: 'var(--bs-gray-500, #adb5bd)',
      customClass: {
        popup: 'shadow-lg border-0',
        confirmButton: 'btn btn-primary px-3 py-2 fw-bold',
        denyButton: 'btn btn-outline-secondary px-3 py-2',
        cancelButton: 'btn btn-light px-3 py-2 text-muted'
      },
      buttonsStyling: false,
      reverseButtons: true
    }).then((result) => {
      if (result.isConfirmed) {
        const selectedUpdates = [];
        changedPrices.forEach((cp, idx) => {
          const chk = document.getElementById(`sync_chk_${idx}`);
          if (chk && chk.checked) {
            let width = null;
            let height = null;
            if (cp.sheet_size) {
              const dims = cp.sheet_size.toLowerCase().split('x');
              if (dims.length === 2) {
                width = parseFloat(dims[0]) || null;
                height = parseFloat(dims[1]) || null;
              }
            }
            selectedUpdates.push({
              service_id: cp.service_id,
              supplier_id: cp.supplier_id,
              service_type: cp.service_type,
              new_unit_price: cp.new_price,
              paper_type_id: cp.paper_type_id || null,
              bed_size: cp.bed_size || null,
              gsm: cp.gsm || null,
              width: width,
              height: height
            });
          }
        });

        if (selectedUpdates.length > 0) {
          const syncPayload = {
            order_number: $('#id_order_number').val() || '',
            updates: selectedUpdates
          };
          const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

          if (!this.api) {
            onComplete();
            return;
          }

          this.api.syncOrderUnitPrices(syncPayload, csrfToken)
            .then(resData => {
              if (resData && resData.success) {
                if (window.showNotification) {
                  window.showNotification(resData.message || 'تم تحديث أسعار الموردين بنجاح', 'success');
                }
              }
              onComplete();
            })
            .catch(err => {
              console.error('Error syncing unit prices:', err);
              onComplete();
            });
        } else {
          onComplete();
        }
      } else if (result.isDenied) {
        onComplete();
      }
    });
  }

  /**
   * 6. مساعد التسعير السريع للعميل النقدي
   */
  bindQuickQuotePreset() {
    const self = this;
    $(document).on('click', '#btn_quick_quote_fill', function (e) {
      e.preventDefault();
      const cashSwitch = document.getElementById('id_is_cash_customer');
      if (cashSwitch && !cashSwitch.checked) {
        cashSwitch.checked = true;
        $(cashSwitch).trigger('change');
      }

      const custNameInput = document.getElementById('id_customer_name');
      if (custNameInput && !custNameInput.value.trim()) {
        custNameInput.value = 'عميل استفسار سريع';
      }

      const titleInput = document.getElementById('id_title');
      const productTypeSelect = document.getElementById('id_product_type') || document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
      const selectedTypeName = productTypeSelect?.options?.[productTypeSelect.selectedIndex]?.text?.trim() || productTypeSelect?.value || 'مطبوعات';

      if (titleInput && !titleInput.value.trim()) {
        titleInput.value = `تسعير مبدئي - ${selectedTypeName}`;
      }

      self.updateGatesState();
      self.debouncedRecalculate();
      self.showNotification('تم ملء بيانات الاستفسار السريع وإظهار الأقسام بنجاح', 'success');
    });
  }

  /**
   * استدعاء محرك الحسابات اللحظي الموحد عبر API (Single Source of Truth)
   */
  callLiveCalculateAPI() {
    if (!this.isStep1Complete().isComplete) {
      this.clearLiveCalculateDisplays();
      return;
    }

    // صمام الأمان الميداني: منع الإرسال لو كانت الكمية أو المقاسات ممسوحة أو صفر
    const rawQty = document.getElementById('id_quantity')?.value;
    const rawW = document.getElementById('id_width')?.value;
    const rawH = document.getElementById('id_height')?.value;
    if (!rawQty || PricingMath.parseSafeNumber(rawQty) <= 0 || !rawW || PricingMath.parseSafeNumber(rawW) <= 0 || !rawH || PricingMath.parseSafeNumber(rawH) <= 0) {
      return;
    }

    if (this._abortController) {
      this._abortController.abort();
    }
    this._abortController = new AbortController();

    const form = document.getElementById('orderForm') || document.getElementById('order-form') || document.querySelector('form');
    if (!form) return;

    const formData = new FormData(form);

    // التحقق من الحقول المباشرة لتطابقها مع الباك إند
    const wasteEl = document.getElementById('id_cover_waste_sheets');
    if (wasteEl && wasteEl.value) {
      formData.set('waste_sheets', wasteEl.value);
    }
    const sidesEl = document.getElementById('id_print_sides_mode_offset') || document.getElementById('id_print_sides_mode_standard');
    if (sidesEl && sidesEl.value) {
      formData.set('print_sides_mode', sidesEl.value);
    }
    const coverPrintingType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    const sidesMode = sidesEl?.value || 'single';
    if (coverPrintingType === 'offset') {
      const pFront = parseInt($('#id_plate_count_front').val(), 10) || 4;
      const pBack = (sidesMode === 'work_sheet') ? (parseInt($('#id_plate_count_back').val(), 10) || 0) : 0;
      const pTotal = pFront + pBack;
      formData.set('plate_count_front', pFront);
      formData.set('plate_count_back', pBack);
      formData.set('zinc_plates_count', pTotal);
      formData.set('plates_total', pTotal);
    }
    const pieceSizeSelect = $('#id_piece_size');
    const selectedPieceOpt = pieceSizeSelect.find('option:selected');
    const pieceVal = pieceSizeSelect.val();

    if (pieceVal && pieceVal !== 'auto') {
      formData.set('piece_size', pieceVal);
      const optName = selectedPieceOpt.data('name') || selectedPieceOpt.text() || '';
      const optCuts = selectedPieceOpt.data('cuts');
      const optW = selectedPieceOpt.data('width');
      const optH = selectedPieceOpt.data('height');

      if (optW && optH) {
        formData.set('piece_width', optW);
        formData.set('piece_height', optH);
      }
      if (optCuts) {
        formData.set('machine_cuts', optCuts);
      }
      formData.set('piece_size_name', this.getCleanPieceName());
    } else {
      const pressBedEl = document.getElementById('id_press_bed_size') || document.getElementById('id_cover_press_machine');
      const bedVal = (pressBedEl && pressBedEl.value) ? pressBedEl.value : '35x50';
      formData.set('piece_size', bedVal);
      formData.set('piece_size_name', this.getCleanPieceName());
    }

    const montageEl = document.getElementById('id_montage_count');
    if (montageEl && montageEl.value && this.isManualMontage) {
      formData.set('montage_count', montageEl.value);
    } else {
      formData.delete('montage_count');
    }

    // مزامنة هامش الربح المحسوب بالـ % في حال كان وضع الإدخال مبلغاً مقطوعاً
    const rawHidden = document.getElementById('id_profit_margin_raw');
    if (rawHidden && rawHidden.value) {
      formData.set('profit_margin', rawHidden.value);
    }

    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

    if (!this.api) return;

    this.api.calculateLive(formData, csrfToken)
      .then(data => {
        if (data && data.success) {
          this.lastServerPayload = data;
          this.applyCalculationResults(data);
          const saveBtn = document.getElementById('btn_save_order');
          if (saveBtn) {
            saveBtn.classList.remove('btn-secondary');
            saveBtn.classList.add('btn-primary');
          }
        } else if (data && data.error_code === 'DIMENSIONS_EXCEED_SHEET') {
          $('#dimension_overflow_alert').removeClass('d-none');
          $('#id_width, #id_height').addClass('is-invalid');
        }
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.warn('Live calculate API error:', err);
        }
      });
  }

  /**
   * تطبيق مخرجات محرك الحسابات المركزي على عناصر الشاشة والسايدبار
   */
  applyCalculationResults(data) {
    if (!data) return;

    requestAnimationFrame(() => {
      // 1. المونتاج واستغلال الفرخ ومزامنة الحقول الفيزيائية المخفية
      if (data.montage) {
        if (data.montage.press_sheet_w) $('#id_piece_width').val(data.montage.press_sheet_w);
        if (data.montage.press_sheet_h) $('#id_piece_height').val(data.montage.press_sheet_h);
        if (data.montage.machine_cuts) $('#id_machine_cuts').val(data.montage.machine_cuts);

        const maxMontage = data.montage.max_cuts_per_sheet || data.montage.cuts_per_sheet;
        this.maxMontage = maxMontage;
        const pieceName = data.montage.piece_size_name || this.getCleanPieceName();
        this.currentPieceName = pieceName;

        const montageInput = $('#id_montage_count');
        let currentVal = parseInt(montageInput.val(), 10);

        // Auto-clamp لو السقف نزل عن الرقم اليدوي
        if (isNaN(currentVal) || currentVal > maxMontage) {
          currentVal = maxMontage;
          this.isManualMontage = false;
        } else if (this.isManualMontage) {
          currentVal = Math.min(currentVal, maxMontage);
        } else {
          currentVal = data.montage.cuts_per_sheet;
        }

        if (!montageInput.is(':focus')) {
          montageInput.val(currentVal);
        }
        montageInput.attr('max', maxMontage);
        this.updateTextSafely('id_montage_piece_name', `/ ${pieceName}`);

        if (currentVal < maxMontage) {
          $('#manual_montage_indicator').removeClass('d-none');
          $('#btn_montage_plus').prop('disabled', false);
        } else {
          $('#manual_montage_indicator').addClass('d-none');
          $('#btn_montage_plus').prop('disabled', true);
        }

        if (currentVal <= 1) {
          $('#btn_montage_minus').prop('disabled', true);
        } else {
          $('#btn_montage_minus').prop('disabled', false);
        }

        this.updateTextSafely('parent_yield_val', `${data.montage.parent_sheet_yield} قطع`);
        const montageText = `${currentVal} / ${pieceName}`;
        this.updateTextSafely('press_montage_ref_val', montageText);
        this.updateTextSafely('insp_montage_summary', `المونتاج: ${montageText} (${data.montage.machine_cuts} قطعات/فرخ)`);
        this.updateTextSafely('pieces_per_sheet_display', `${data.montage.cuts_per_sheet} قطع`);
      }

      // 2. أفرخ الورق والهالك
      if (data.paper) {
        this.updateTextSafely('display_cover_gross_sheets', `${data.paper.gross_press_sheets.toLocaleString()} فرخ`);
        this.updateTextSafely('display_cover_net_sheets', data.paper.net_press_sheets.toLocaleString());
        this.updateTextSafely('display_cover_waste_sheets', (data.paper.waste_sheets || 0).toLocaleString());
        this.updateTextSafely('display_cover_reams_breakdown', `${data.paper.packs_count} رزمة`);
        this.updateTextSafely('cover_paper_cost_display', this.formatMoney(data.paper.total_cost));
        this.updateTextSafely('cost_paper_display', this.formatMoney(data.paper.total_cost));
        if ($('#id_cover_waste_sheets').length && 
            !$('#id_cover_waste_sheets').is(':focus') && 
            !document.getElementById('id_cover_waste_sheets')?.dataset?.manual) {
          $('#id_cover_waste_sheets').val(data.paper.waste_sheets);
        }
        const finTirages = Math.max(1, Math.ceil((data.paper.gross_press_sheets || 0) / 1000));
        this.updateTextSafely('spot_uv_tirage_badge', `${finTirages} تراج`);
        this.updateTextSafely('die_cut_tirage_badge', `${finTirages} تراج`);
      }

      // 3. وزن الورق بالكيلوجرام
      if (data.weight) {
        this.updateTextSafely('display_cover_weight_kg', `${data.weight.total_kg} كجم`);
      }

      // 4. سحبات وتكلفة الماكينة (مع فتحة الماكينة)
      if (data.printing) {
        this.updateTextSafely('display_machine_pulls_count', `${data.printing.press_pulls.toLocaleString()} سحبة`);
        let tirageLabel = `(${data.printing.tirages} تراج)`;
        let detailedPulls = `${data.printing.press_pulls.toLocaleString()} سحبة (${data.printing.tirages} تراج)`;
        if (data.printing.tirages_front !== undefined && data.printing.tirages_back > 0) {
          tirageLabel = `(${data.printing.tirages} تراج: ${data.printing.tirages_front} وجه + ${data.printing.tirages_back} ظهر)`;
          detailedPulls = `${data.printing.press_pulls.toLocaleString()} سحبة (${data.printing.tirages} تراج: ${data.printing.tirages_front} وجه + ${data.printing.tirages_back} ظهر)`;
        }
        this.updateTextSafely('display_machine_tirages', tirageLabel);
        this.updateTextSafely('cover_press_cost_display', this.formatMoney(data.printing.applied_press_cost));
        const pullsText = document.getElementById('press_pulls_count');
        if (pullsText) {
          this.updateTextSafely(pullsText, detailedPulls);
        }
      }

      // 5. الزنكات وتوفير الطبع والقلب
      if (data.plates) {
        this.updateTextSafely('cover_ctp_cost_display', this.formatMoney(data.plates.total_cost));
        const currentSides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';
        const isOffset = (document.getElementById('id_cover_printing_type')?.value || 'offset') === 'offset';

        if (currentSides === 'work_turn' || data.plates.is_work_turn_savings) {
          $('#id_plate_count_back').val(0).prop('disabled', true);
          $('#work_turn_advisor_alert').removeClass('d-none');
        } else if (currentSides === 'work_sheet' && isOffset) {
          $('#id_plate_count_back').prop('disabled', false);
          $('#work_turn_advisor_alert').addClass('d-none');
          if (!$('#id_plate_count_back').is(':focus') && !document.getElementById('id_plate_count_back')?.dataset?.manual) {
            $('#id_plate_count_back').val(data.plates.plates_back);
          }
        } else {
          // single أو غير أوفست
          $('#id_plate_count_back').val(0).prop('disabled', true);
          $('#work_turn_advisor_alert').addClass('d-none');
        }

        if (!$('#id_plate_count_front').is(':focus') && !document.getElementById('id_plate_count_front')?.dataset?.manual) {
          $('#id_plate_count_front').val(data.plates.plates_front);
        }
        if (!$('#id_plate_count').is(':focus')) {
          $('#id_plate_count').val(data.plates.total_plates);
        }
        if ($('#id_plates_total').length) {
          $('#id_plates_total').val(data.plates.total_plates);
        }
      }

      // 6. التشطيبات وخدمات ما بعد الطباعة
      if (data.finishing) {
        this.updateTextSafely('cost_finishing_display', this.formatMoney(data.finishing.total_cost));
        if (data.finishing.details) {
          if (data.finishing.details.lamination !== undefined) {
            this.updateTextSafely('display_lamination_cost', this.formatMoney(data.finishing.details.lamination));
          }
          if (data.finishing.details.die_cutting !== undefined) {
            this.updateTextSafely('display_die_cutting_cost', this.formatMoney(data.finishing.details.die_cutting));
          }
          if (data.finishing.details.spot_uv !== undefined) {
            this.updateTextSafely('display_spot_uv_cost', this.formatMoney(data.finishing.details.spot_uv));
          }
          if (data.finishing.details.foil !== undefined) {
            this.updateTextSafely('display_foil_cost', this.formatMoney(data.finishing.details.foil));
          }
          if (data.finishing.details.emboss !== undefined) {
            this.updateTextSafely('display_emboss_cost', this.formatMoney(data.finishing.details.emboss));
          }
          if (data.finishing.details.creasing !== undefined) {
            this.updateTextSafely('display_creasing_cost', this.formatMoney(data.finishing.details.creasing));
          }
        }
      }

      // 7. التجليد والتقفيل
      if (data.binding) {
        this.updateTextSafely('cost_binding_display', this.formatMoney(data.binding.total_cost));
      }

      // 8. اللوجستيات
      if (data.logistics) {
        this.updateTextSafely('cost_logistics_display', this.formatMoney(data.logistics.delivery_cost || data.logistics.total_cost));
      }

      // 8.5 ملازم الداخلي
      if (data.inner) {
        if (data.inner.inner_pulls !== undefined && data.inner.inner_tirages !== undefined) {
          const sigs = data.inner.signatures_count || 1;
          const sigT = data.inner.sig_tirage || 1;
          this.updateTextSafely('inner_press_pulls_count', `${data.inner.inner_pulls.toLocaleString()} سحبة (${data.inner.inner_tirages} تراج لـ ${sigs} ملازم - ${sigT} تراج/ملزمة)`);
        }
        if (data.inner.inner_press_cost !== undefined) {
          this.updateTextSafely('inner_press_cost_display', this.formatMoney(data.inner.inner_press_cost));
        }
      }

      // 9. السايدبار المالي المركزي والحقول المخفية
      if (data.totals) {
        if (data.currency_symbol) {
          this.config.currencySymbol = data.currency_symbol;
        }
        const printingSum = (data.printing?.total_cost || 0) + (data.plates?.total_cost || 0) + (data.inner?.inner_press_cost || 0) + (data.inner?.inner_plates_cost || 0);
        this.updateTextSafely('cost_printing_display', this.formatMoney(printingSum));
        this.updateTextSafely('total_cost_display', this.formatMoney(data.totals.total_production_cost));
        this.lastKnownTotalCost = data.totals.total_production_cost;

        // مزامنة تكاليف الباك إند
        $('#id_material_cost').val(data.totals.materials_cost);
        $('#id_printing_cost').val(printingSum.toFixed(2));
        $('#id_finishing_cost').val(data.finishing.total_cost);

        // تطبيق الهامش النشط في يد المستخدم محلياً فوراً على التكلفة الجديدة المعتمدة
        this.updateFinancialsLocally();
      }
    });
  }

  /**
   * المحرك الحسابي الرئيسي الشامل (Master Recalculate Engine - Clean State Dispatcher)
   */
  recalculate() {
    const step1Status = this.isStep1Complete();
    this.updateGatesState();
    if (!step1Status.isComplete) {
      this.clearLiveCalculateDisplays();
      return;
    }

    const selectEl = document.getElementById('id_product_type') || document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    const type = selectEl?.options?.[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.dataset?.archetype || selectEl?.value || 'flyer';
    const openDir = document.querySelector('input[name="open_direction"]:checked')?.value || 'right';
    const isClosed = document.getElementById('id_is_closed_size')?.checked || false;
    const w = PricingMath.parseSafeNumber(document.getElementById('id_width')?.value, 21);
    const h = PricingMath.parseSafeNumber(document.getElementById('id_height')?.value, 29.7);
    const pages = PricingMath.parseSafeNumber(document.getElementById('id_pages_count')?.value, 32);
    const innerPaperWeight = PricingMath.parseSafeNumber(document.getElementById('id_inner_paper_weight')?.value, 135);
    const bindingType = document.getElementById('id_binding_type')?.value || 'staple';
    const isHardcover = bindingType === 'hardcover';

    let multiplier = (type === 'brochure' || type === 'brochures') ? 3 : 2;
    let spineMm = 0;
    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      spineMm = PricingMath.calcSpineMm(pages, innerPaperWeight, bindingType, isHardcover);
    }
    const spineDisplay = document.getElementById('spine_thickness_display');
    if (spineDisplay) {
      this.updateTextSafely(spineDisplay, `${spineMm.toFixed(1)} مم`);
    }

    // حساب المقاس المفتوح للمعاينة الهندسية ومستشار الهدر
    let openW = w;
    let openH = h;
    if (isClosed) {
      if (openDir === 'right' || openDir === 'left') {
        openW = (w * multiplier) + (spineMm / 10);
      } else {
        openH = (h * multiplier) + (spineMm / 10);
      }
    }

    // استدعاء محرك الحسابات المركزي في السيرفر (Single Source of Truth)
    this.callLiveCalculateAPI();
  }

  /**
   * تنظيف واشتقاق مسمى مقاس القطع بسوق المطابع المصرية
   */
  getCleanPieceName() {
    const pieceOpt = $('#id_piece_size option:selected');
    let name = pieceOpt.data('name') || pieceOpt.text() || '';
    if (name && !name.includes('تلقائي') && pieceOpt.val() !== 'auto') {
      name = name.replace(/\(.*?\)/g, '').trim();
      if (name.endsWith(' فرخ') && !name.includes('جاير')) {
        name = name.replace(/ فرخ$/, '').trim();
      }
      if (name === 'فرخ كامل') name = 'فرخ';
      return name;
    }

    // اشتقاق المسمى تلقائياً من مقاس الفرخ والماكينة
    const sheetOpt = $('#id_sheet_size option:selected');
    const sheetText = (sheetOpt.val() || sheetOpt.text() || '').toLowerCase();
    const isTabaGayer = sheetText.includes('60x85') || sheetText.includes('85x60') || sheetText.includes('طبع جاير');
    const isGayer = sheetText.includes('66x88') || sheetText.includes('88x66') || sheetText.includes('جاير');

    let machineCuts = PricingMath.parseSafeNumber(pieceOpt.data('cuts'), 0);
    if (machineCuts <= 0) {
      const pressBed = $('#id_cover_press_machine').val() || $('#id_press_bed_size').val() || '35x50';
      if (pressBed === '50x70') machineCuts = 2;
      else if (pressBed === '70x100') machineCuts = 1;
      else machineCuts = 4; // الافتراضي ربع فرخ
    }

    if (machineCuts === 4) {
      if (isTabaGayer) return 'ربع طبع جاير';
      if (isGayer) return 'ربع جاير';
      return 'ربع';
    } else if (machineCuts === 2) {
      if (isTabaGayer) return 'نصف طبع جاير';
      if (isGayer) return 'نصف جاير';
      return 'نصف';
    } else if (machineCuts === 1) {
      if (isTabaGayer) return 'فرخ طبع جاير';
      if (isGayer) return 'فرخ جاير';
      return 'فرخ';
    } else if (machineCuts === 8) {
      return 'ثمن';
    }
    return `${machineCuts} قطعات`;
  }

  /**
   * معالجة تغيير حقل المونتاج اليدوي مع الكبح الصارم للسقف الأقصى
   */
  handleMontageInputChange(isCommit) {
    const input = $('#id_montage_count');
    let val = parseInt(input.val(), 10);
    const max = this.maxMontage || 1;

    if (isNaN(val)) {
      if (isCommit) {
        val = this.isManualMontage ? 1 : max;
        input.val(val);
      } else {
        return;
      }
    }

    if (val > max) {
      val = max;
      input.val(val);
      this.showNotification(`سقف المونتاج المتاح هندسياً هو ${max} قطع ولا يمكن تجاوزه`, 'warning');
    } else if (val < 1) {
      val = 1;
      input.val(val);
      this.showNotification('الحد الأدنى للمونتاج هو قطعة واحدة في الشيت', 'warning');
    }

    this.isManualMontage = (val < max);
    if (val < max) {
      $('#manual_montage_indicator').removeClass('d-none');
      $('#btn_montage_plus').prop('disabled', false);
    } else {
      $('#manual_montage_indicator').addClass('d-none');
      $('#btn_montage_plus').prop('disabled', true);
    }

    if (val <= 1) {
      $('#btn_montage_minus').prop('disabled', true);
    } else {
      $('#btn_montage_minus').prop('disabled', false);
    }

    const pieceName = this.currentPieceName || this.getCleanPieceName();
    $('#press_montage_ref_val').text(`${val} / ${pieceName}`);

    if (isCommit) {
      this.debouncedRecalculate();
    }
  }

  /**
   * استعادة المونتاج الأقصى التلقائي (السقف الهندسي)
   */
  resetMontageToMax() {
    this.isManualMontage = false;
    const max = this.maxMontage || 1;
    $('#id_montage_count').val(max);
    $('#manual_montage_indicator').addClass('d-none');
    $('#btn_montage_plus').prop('disabled', true);
    $('#btn_montage_minus').prop('disabled', max <= 1);
    const pieceName = this.currentPieceName || this.getCleanPieceName();
    $('#press_montage_ref_val').text(`${max} / ${pieceName}`);
    this.debouncedRecalculate();
  }



  /**
   * توليد ونسخ رسالة عرض السعر للواتساب (Universal Clipboard)
   * تم فصلها معمارياً إلى: static/js/printing_pricing/modules/pricing_export.js
   */
  generateWhatsAppQuote() {
    if (window.PricingExport) {
      window.PricingExport.generateWhatsAppQuote(this);
    }
  }

  /**
   * نسخ للنص بالحافظة مع Fallback للشبكات الداخلية HTTP
   */
  copyToClipboard(text) {
    if (window.PricingExport) {
      window.PricingExport.copyToClipboard(text, this);
    }
  }

  /**
   * Fallback للنسخ عبر textarea مؤقتة
   */
  fallbackCopyText(text) {
    if (window.PricingExport) {
      window.PricingExport.fallbackCopyText(text, (msg, type) => this.showNotification(msg, type));
    }
  }

  /**
   * كشف الحقول غير الصالحة وتوسيع الأكورديون الحاضن لها
   */
  validateAndUnfoldCollapsedSections(form) {
    const firstInvalid = form.querySelector(':invalid');
    if (firstInvalid) {
      const collapsedParent = firstInvalid.closest('.collapse');
      if (collapsedParent && !collapsedParent.classList.contains('show')) {
        if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
          const bsCollapse = new bootstrap.Collapse(collapsedParent, { toggle: true });
        } else {
          $(collapsedParent).collapse('show');
        }
      }
      setTimeout(() => {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 200);
    }
  }

  /**
   * تنظيف وتطهير الحقول غير النشطة قبل الـ POST
   */
  sanitizePayloadOnSubmit() {
    const coverType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    const offsetSides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';

    if (coverType === 'offset') {
      if (offsetSides !== 'work_sheet') {
        const backC = document.getElementById('id_colors_back');
        if (backC) backC.value = '0';
        const backSpot = document.getElementById('id_spot_colors_back');
        if (backSpot) backSpot.value = '0';
        const backPlate = document.getElementById('id_plate_count_back');
        if (backPlate) {
          backPlate.disabled = false;
          backPlate.value = '0';
        }
      } else {
        const backPlate = document.getElementById('id_plate_count_back');
        if (backPlate) backPlate.disabled = false;
      }
    } else if (coverType === 'none') {
      ['id_colors_front', 'id_colors_back', 'id_spot_colors_front', 'id_spot_colors_back'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '0';
      });
    }
  }

  /**
   * اختصارات لوحة المفاتيح (Ctrl+S / Cmd+S)
   */
  bindKeyboardShortcuts() {
    const self = this;
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        const form = document.getElementById('order-form');
        if (form) {
          const submitBtn = document.getElementById('btn_save_order');
          if (submitBtn) submitBtn.click();
        }
      }
    });
  }

  /**
   * دورة حياة المتصفح (BFCache Restore & Unsaved Changes Guard)
   */
  bindLifecycleGuards() {
    const self = this;

    // استعادة الحسابات من الـ BFCache عند الرجوع
    window.addEventListener('pageshow', function (event) {
      self.recalculate();
    });

    // كتم الـ Debounce أثناء نوم التابة
    document.addEventListener('visibilitychange', function () {
      if (document.hidden && self.debounceTimer) {
        clearTimeout(self.debounceTimer);
      }
    });

    // تحذير الخروج بدون حفظ وتنظيف الطلبات المعلقة
    window.addEventListener('beforeunload', function (e) {
      if (self._abortController) {
        self._abortController.abort();
      }
      if (self.isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
  }
}

// تصدير الكائن للنطاق العام
window.OrderFormUIController = OrderFormUIController;
window.PRICING_REGISTRY = OrderFormUIController.PRICING_REGISTRY;
