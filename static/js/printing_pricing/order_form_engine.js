/**
 * MWHEBA ERP - Printing Pricing Master Engine (Enterprise ES6 Architecture)
 * Two-Tier Decoupled Pricing Engine: Pure Math Logic + Resilient UI Controller
 * Version: 2.1.8
 */

// ============================================================================
// 1. طبقة الحسابات الرياضية الصرفة (Pure Math Functions)
// ============================================================================
const PricingMath = {
  /**
   * تحويل وتطهير الأرقام العربية المشرقية والفواصل
   */
  parseSafeNumber(val, fallback = 0) {
    if (val === undefined || val === null || val === '') return fallback;
    if (typeof val === 'number') return isNaN(val) ? fallback : val;
    let s = String(val).trim();
    // تحويل الأرقام العربية ٠-٩ إلى 0-9
    s = s.replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
    // تحويل الفواصل العربية والإنجليزية
    s = s.replace(/,/g, '.');
    const parsed = parseFloat(s);
    return isNaN(parsed) ? fallback : parsed;
  },

  /**
   * حساب استغلال الفرخ والمونتاج الهندسي مع خصم 2.0 سم (بنسة الماكينة 1.5 سم + طهارة المقص 0.5 سم)
   * وصمام أمان عند تجاوز مقاس المطبوع لمساحة الفرخ
   */
  calcImposition(sheetW, sheetH, openW, openH) {
    // خصم 1.5 سم للبنسة و 0.5 سم لطهارة المقص
    const netW = Math.max(0, sheetW - 2.0);
    const netH = Math.max(0, sheetH - 2.0);
    const safeW = Math.max(0.1, openW);
    const safeH = Math.max(0.1, openH);

    // الوضع الطبيعي
    const cutsNormalW = Math.floor(netW / safeW);
    const cutsNormalH = Math.floor(netH / safeH);
    const normalTotal = cutsNormalW * cutsNormalH;

    // وضع التدوير 90 درجة
    const cutsRotW = Math.floor(netW / safeH);
    const cutsRotH = Math.floor(netH / safeW);
    const rotTotal = cutsRotW * cutsRotH;

    const bestCuts = Math.max(normalTotal, rotTotal);
    const isOverflow = bestCuts <= 0;
    const isRotated = rotTotal > normalTotal;

    return {
      cutsPerSheet: isOverflow ? 0 : bestCuts,
      cutsW: isOverflow ? 0 : (isRotated ? cutsRotW : cutsNormalW),
      cutsH: isOverflow ? 0 : (isRotated ? cutsRotH : cutsNormalH),
      isRotated: isRotated,
      isOverflow: isOverflow
    };
  },

  /**
   * حساب الفروخ الصافية والفاقد وتجهيز الماكينة مع معالجة التصفير عند التجاوز
   */
  calcGrossSheets(qty, cutsPerSheet, wasteRate, minMakeReady = 20) {
    if (cutsPerSheet <= 0) {
      return {
        netSheets: 0,
        grossSheets: 0,
        wasteSheets: 0
      };
    }
    const safeCuts = Math.max(1, cutsPerSheet);
    const netSheets = Math.ceil(qty / safeCuts);
    let gross = Math.ceil(netSheets * (1 + wasteRate));
    if (gross - netSheets < minMakeReady) {
      gross = netSheets + minMakeReady;
    }
    return {
      netSheets: netSheets,
      grossSheets: gross,
      wasteSheets: gross - netSheets
    };
  },

  /**
   * حساب سماكة الكعب الفيزيائي بالمليمتر
   */
  calcSpineMm(pages, paperWeight, bindingType, isHardcover = false) {
    if (bindingType === 'staple' || bindingType === 'wire_o') {
      return 0.0;
    }
    const sheets = Math.ceil(pages / 2);
    let rawSpine = sheets * (paperWeight / 1000) * 1.15;
    if (isHardcover) {
      rawSpine += 4.0; // 4mm شاسيه كرتون وتجليد فاخر
    }
    return Math.round(rawSpine * 10) / 10;
  },

  /**
   * حساب الملازم
   */
  calcSignatures(pages, w, h) {
    const sigCapacity = (w <= 15.5 && h <= 22.0) ? 32 : 16;
    const totalSignatures = Math.max(1, Math.ceil(pages / sigCapacity));
    return {
      signaturesCount: totalSignatures,
      sigCapacity: sigCapacity
    };
  },

  /**
   * حساب السحبات وعدد التراج (ألف سحبة)
   */
  calcPullsAndTirage(grossSheets, sidesMultiplier = 1) {
    const pulls = Math.ceil(grossSheets * sidesMultiplier);
    const tirages = Math.max(1, Math.ceil(pulls / 1000));
    return {
      pulls: pulls,
      tirages: tirages
    };
  },

  /**
   * حساب السعر النهائي المحاسبي بهامش الربح وفق نموذج التكلفة الإضافية (Markup)
   * مع حماية الهامش وتقريبه للأعلى (Math.ceil) للمطابقة التامة مع الباك إند
   */
  calcFinalPrice(totalCost, profitMargin) {
    // تحديد الهامش بين 0% و 500% كحد أقصى آمن
    const safeMargin = Math.min(5.0, Math.max(0, profitMargin));
    const rawPrice = totalCost * (1 + safeMargin);
    // جبر الإجمالي النهائي دائمًا للأعلى لمطابقة الباك إند
    return Math.ceil(rawPrice);
  }
};

// ============================================================================
// 2. كلاس التحكم بالواجهة والأحداث (UI & Event Orchestrator)
// ============================================================================
class OrderFormUIController {
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
    this.currentTrimSuggestion = null;
    this.isPaperCascadeUpdating = false;
    this.isUserInteracting = false;
    this.isRestoringDraft = false;
    this.isManualSheetsActive = false;
    this.manualGrossSheets = null;
    this.activePaperAbort = null;
    this.activeOriginAbort = null;
    this.isSyncingOrigin = false;
    this.maxMontage = null;
    this.isManualMontage = false;
    this.currentPieceName = '';
    this.marginMode = 'percent'; // 'percent' أو 'fixed'
    this.lastKnownTotalCost = 0;
    this.isSyncingFields = false;
  }

  /**
   * تهيئة المنظومة
   */
  init() {
    this.initDefaultDate();
    this.initSelect2();
    this.bindDelegatedEvents();
    this.bindSupplierWatchers();
    this.bindPaperCardWatchers();
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
      const initOpt = anatomySelect.options[anatomySelect.selectedIndex];
      const initArchetype = initOpt?.dataset?.archetype || anatomySelect.value || 'flyer';
      this.handleAnatomySwitch(initArchetype);
    }
    this.applySelectedProductSize();
    this.updatePrintingTypeUI();
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
      $('#id_montage_count').val('').attr('placeholder', '-');
      $('#id_montage_piece_name').text('/ --');
      $('#press_montage_ref_val').text('- / --');
      $('#parent_yield_val').text('-- قطعة');
      $('#btn_montage_minus').prop('disabled', true);
      $('#btn_montage_plus').prop('disabled', true);
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

    this.updateGatesState();
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
      const archetype = selectEl.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl.value;
      self.handleAnatomySwitch(archetype);
      self.debouncedRecalculate(50);
    });

    // 2. مراقبة مقاس المطبوع
    $(document).on('change', '#id_product_size', function () {
      if (self.isSyncingFields) return;
      self.applySelectedProductSize();
      self.debouncedRecalculate(50);
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
        if (stdSel) stdSel.value = this.value === 'work_sheet' ? 'double' : 'single';
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
      self.updateOpenDimensionsDisplay();
      self.debouncedRecalculate(50);
    });

    // 7.1 مراقبة حقول الأرقام والإدخال (Inputs) بحدث input فقط لمنع الازدواجية عند الـ blur
    $(document).on('input', '#id_quantity, #id_profit_margin, #id_extra_cost, #id_giveaway_item_cost, #id_paper_weight, #id_inner_paper_weight, #id_pages_count, #id_colors_front, #id_colors_back, #id_spot_colors_front, #id_spot_colors_back, #id_screen_colors_count, #id_inner_colors_single, #id_inner_spot_colors_single, #id_inner_spot_colors, #id_digital_inner_color_pages, #id_digital_inner_bw_pages, #id_color_signatures_count, #id_bw_signatures_count, #id_ncr_sets_count, #id_ncr_book_capacity, #id_ncr_serial_start, #id_banner_sqm_price', function () {
      self.isDirty = true;
      self.updatePrintingTypeUI();
      self.updateOpenDimensionsDisplay();
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

    $(document).on('input', '#id_cover_waste_sheets, #id_plate_count_front, #id_plate_count_back, #id_plate_count, #id_inner_plates_count_total, #id_plate_price, #id_inner_plate_price, #id_press_rate, #id_inner_press_rate, #id_digital_sheet_price, #id_digital_inner_color_price, #id_digital_inner_bw_price', function () {
      this.dataset.manual = "true";
      $(this).addClass('border-primary');
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
        }
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
        }
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
          const priceColor = parseFloat(selectedOpt.data('price-color')) || 0;
          const priceBw = parseFloat(selectedOpt.data('price-bw')) || 0;
          digPriceInput.value = isColor ? (priceColor || '') : (priceBw || '');
        }
      }
      self.debouncedRecalculate();
      self.showNotification('تمت إعادة حساب طباعة الديجيتال بنجاح', 'info');
    });

    // 9. AJAX الموردين والماكينات
    this.bindSupplierWatchers();

    // 10. زر النسخ السريع من الغلاف للداخلي
    $(document).on('click', '#btn_copy_cover_press_to_inner', function () {
      self.copyCoverPressToInner();
    });

    $(document).on('click', '#btn_copy_cover_paper_to_inner', function () {
      self.copyCoverPaperToInner();
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

    // 12. زر مستشار تقليل الهدر
    $(document).on('click', '#btn_apply_trim_suggestion', function (e) {
      e.preventDefault();
      if (self.currentTrimSuggestion && typeof self.currentTrimSuggestion.action === 'function') {
        self.currentTrimSuggestion.action();
        self.showNotification('تم تطبيق المقترح الذكي وتقليل الهدر بنجاح! 🚀', 'success');
      }
    });

    // 13. زر الحفظ كمسودة
    $(document).on('click', '#btn_save_draft', function (e) {
      e.preventDefault();
      const form = document.getElementById('order-form');
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
        form.submit();
      }
    });

    // 14. التحقق قبل إرسال النموذج وتوسيع الأكورديونات المطوية
    const form = document.getElementById('order-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        self.sanitizePayloadOnSubmit();

        if (!form.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
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
    const selectEl = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    const type = selectEl?.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.value || 'flyer';
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

    const profitMarginInput = document.getElementById('id_profit_margin');
    let marginPct = 30;
    let fixedProfit = 0;
    let grandTotal = 0;

    if (this.marginMode === 'fixed') {
      if (profitMarginInput) {
        const raw = profitMarginInput.value.trim();
        fixedProfit = raw === '' ? 0 : PricingMath.parseSafeNumber(raw, 0);
      }
      grandTotal = Math.ceil(totalCost + fixedProfit);
      marginPct = totalCost > 0 ? ((fixedProfit / totalCost) * 100) : 0;
    } else {
      if (profitMarginInput) {
        const raw = profitMarginInput.value.trim();
        marginPct = raw === '' ? 0 : PricingMath.parseSafeNumber(raw, 30);
      }
      fixedProfit = totalCost > 0 ? (totalCost * (marginPct / 100)) : 0;
      grandTotal = PricingMath.calcFinalPrice(totalCost, marginPct / 100);
    }

    const unitPrice = grandTotal / safeQty;

    // تحديث شاشات العرض المالية بالسايدبار
    const costLogEl = document.getElementById('cost_logistics_display');
    if (costLogEl) this.updateTextSafely(costLogEl, this.formatMoney(extraCost));

    const totalCostEl = document.getElementById('total_cost_display');
    if (totalCostEl && totalCost > 0) this.updateTextSafely(totalCostEl, this.formatMoney(totalCost));

    const unitPriceEl = document.getElementById('unit_price_display');
    if (unitPriceEl) this.updateTextSafely(unitPriceEl, this.formatNumber(unitPrice));

    const finalTotalEl = document.getElementById('final_total_display');
    if (finalTotalEl) this.updateTextSafely(finalTotalEl, this.formatNumber(grandTotal));

    // تحديث المؤشر وشريط تقدم هامش الربح
    this.updateMarginUI(marginPct);

    // مزامنة الحقول المخفية للباك إند بدقة 4 أرقام عشرية لمنع انحراف الجنيه بالتقريب
    const finalPriceHidden = document.getElementById('id_final_price');
    if (finalPriceHidden) finalPriceHidden.value = grandTotal.toFixed(2);

    const salePriceHidden = document.getElementById('id_sale_price');
    if (salePriceHidden) salePriceHidden.value = grandTotal.toFixed(2);

    const rawHidden = document.getElementById('id_profit_margin_raw');
    if (rawHidden) rawHidden.value = marginPct.toFixed(4);
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
        marginPct = parseFloat(((fixedAmount / totalCost) * 100).toFixed(4));
      } else {
        marginPct = 0;
      }
      // مزامنة النسبة المئوية للحقل المخفي المرسل للداتابيز والـ SSOT
      if (rawHidden) {
        rawHidden.value = marginPct.toFixed(4);
      }
    } else {
      // نمط النسبة المئوية المباشرة (%) (المستخدم أدخل نسبة مئوية)
      if (customVal !== null && !isNaN(customVal)) {
        marginPct = parseFloat(Number(customVal).toFixed(4));
      } else if (marginInput) {
        const raw = marginInput.value.trim();
        marginPct = raw === '' ? 0 : parseFloat(PricingMath.parseSafeNumber(raw, 30).toFixed(4));
      }
      fixedAmount = totalCost > 0 ? (totalCost * (marginPct / 100)) : 0;
      if (rawHidden) {
        rawHidden.value = marginPct.toFixed(4);
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

  /**
   * زنكات CTP للغلاف
   */
  updateCoverPlatesUI() {
    const coverPrintingType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    const offsetSides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';
    const archivedCheckbox = document.getElementById('id_is_plates_archived');
    const isArchived = archivedCheckbox ? archivedCheckbox.checked : (document.getElementById('id_plates_option')?.value === 'archived');
    
    const platesOptionInput = document.getElementById('id_plates_option');
    if (platesOptionInput) platesOptionInput.value = isArchived ? 'archived' : 'new';

    const frontColorsInput = document.getElementById('id_colors_front');
    const spotFrontInput = document.getElementById('id_spot_colors_front');
    const backColorsInput = document.getElementById('id_colors_back');
    const spotBackInput = document.getElementById('id_spot_colors_back');

    let frontColors = PricingMath.parseSafeNumber(frontColorsInput?.value, 4);
    let spotFront = PricingMath.parseSafeNumber(spotFrontInput?.value, 0);
    let backColors = 0;
    let spotBack = 0;

    const plateFrontInput = document.getElementById('id_plate_count_front');
    const plateBackInput = document.getElementById('id_plate_count_back');
    const plateTotalInput = document.getElementById('id_plate_count');
    const platePriceInput = document.getElementById('id_plate_price');
    const ctpCostDisplay = document.getElementById('cover_ctp_cost_display');
    const ctpBadge = document.getElementById('cover_ctp_summary_badge');

    if (offsetSides === 'work_sheet') {
      backColors = PricingMath.parseSafeNumber(backColorsInput?.value, 4);
      spotBack = PricingMath.parseSafeNumber(spotBackInput?.value, 0);
      if (plateBackInput) {
        plateBackInput.disabled = false;
        if (!plateBackInput.dataset.manual) plateBackInput.value = (backColors + spotBack);
      }
    } else {
      if (plateBackInput) {
        plateBackInput.value = 0;
        plateBackInput.disabled = true;
      }
    }

    const calculatedFront = frontColors + spotFront;
    if (plateFrontInput && !plateFrontInput.dataset.manual) {
      plateFrontInput.value = calculatedFront;
    }

    const curFront = PricingMath.parseSafeNumber(plateFrontInput?.value, calculatedFront);
    const curBack = PricingMath.parseSafeNumber(plateBackInput?.value, (offsetSides === 'work_sheet' ? (backColors + spotBack) : 0));
    const totalPlates = curFront + curBack;

    if (plateTotalInput) {
      plateTotalInput.value = totalPlates;
    }

    const actualPlates = totalPlates;
    const unitPrice = PricingMath.parseSafeNumber(platePriceInput?.value, 0);
    const setPrice = PricingMath.parseSafeNumber(platePriceInput?.dataset?.setPrice || $(platePriceInput).attr('data-set-price'), 0);

    let totalCost = 0;
    if (!isArchived && actualPlates > 0) {
      if (setPrice > 0 && unitPrice > 0) {
        const fullSets = Math.floor(actualPlates / 4);
        const remPlates = actualPlates % 4;
        const costUnit = actualPlates * unitPrice;
        const costSetRem = (fullSets * setPrice) + (remPlates * unitPrice);
        const costNextSet = (fullSets + (remPlates > 0 ? 1 : 0)) * setPrice;
        totalCost = Math.min(costUnit, costSetRem, costNextSet);
      } else if (setPrice > 0) {
        const totalSets = Math.ceil(actualPlates / 4);
        totalCost = totalSets * setPrice;
      } else {
        totalCost = actualPlates * unitPrice;
      }
    }

    if (coverPrintingType !== 'offset') {
      totalCost = 0;
    }

    const platesTotalInput = document.getElementById('id_plates_total');
    if (platesTotalInput) platesTotalInput.value = actualPlates;

    const ctpSetBadge = document.getElementById('cover_ctp_set_badge');
    if (ctpSetBadge) {
      if (!isArchived && setPrice > 0 && actualPlates >= 4 && coverPrintingType === 'offset') {
        ctpSetBadge.classList.remove('d-none');
      } else {
        ctpSetBadge.classList.add('d-none');
      }
    }

    if (ctpCostDisplay) ctpCostDisplay.textContent = this.formatMoney(totalCost);
    if (ctpBadge) {
      ctpBadge.textContent = isArchived ? `${this.config.i18n.archivedPlates} (0 ${this.config.currencySymbol})` : this.config.i18n.newPlates;
      ctpBadge.className = isArchived
        ? 'badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1'
        : 'badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1';
    }

    return { totalPlates: actualPlates, totalCost: totalCost, isArchived: isArchived };
  }

  /**
   * زنكات CTP للداخلي
   */
  updateInnerPlatesUI() {
    const selectEl = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    const type = selectEl?.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.value || 'flyer';
    const innerPrintingType = document.getElementById('id_inner_printing_type')?.value || 'offset';
    const innerSides = document.getElementById('id_inner_print_sides_mode')?.value || 'work_sheet';
    const innerArchivedCheckbox = document.getElementById('id_is_inner_plates_archived');
    const isArchived = innerArchivedCheckbox ? innerArchivedCheckbox.checked : (document.getElementById('id_inner_plates_option')?.value === 'archived');

    const innerPlatesOptionInput = document.getElementById('id_inner_plates_option');
    if (innerPlatesOptionInput) innerPlatesOptionInput.value = isArchived ? 'archived' : 'new';

    const spotColors = PricingMath.parseSafeNumber(document.getElementById('id_inner_spot_colors')?.value, 0);
    const innerPriceInput = document.getElementById('id_inner_plate_price');
    const innerTotalInput = document.getElementById('id_inner_plates_count_total');
    const innerCostDisplay = document.getElementById('inner_ctp_cost_display');
    const innerBadge = document.getElementById('inner_ctp_summary_badge');

    const w = PricingMath.parseSafeNumber(document.getElementById('id_width')?.value, 21);
    const h = PricingMath.parseSafeNumber(document.getElementById('id_height')?.value, 29.7);
    const pages = PricingMath.parseSafeNumber(document.getElementById('id_pages_count')?.value, 32);
    const totalSignatures = PricingMath.calcSignatures(pages, w, h).signaturesCount;

    let innerPlates = 0;
    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      if (innerPrintingType === 'offset') {
        if (innerSides === 'single') {
          const singleColors = PricingMath.parseSafeNumber(document.getElementById('id_inner_colors_single')?.value, 4);
          innerPlates = singleColors + spotColors;
        } else {
          const innerColorMode = document.getElementById('id_inner_color_mode')?.value || 'all_color';
          let colorSigs = totalSignatures;
          let bwSigs = 0;
          if (innerColorMode === 'all_bw') {
            colorSigs = 0;
            bwSigs = totalSignatures;
          } else if (innerColorMode === 'mixed') {
            colorSigs = PricingMath.parseSafeNumber(document.getElementById('id_color_signatures_count')?.value, 0);
            bwSigs = PricingMath.parseSafeNumber(document.getElementById('id_bw_signatures_count')?.value, 0);
          }
          innerPlates = (colorSigs * 8) + (bwSigs * 2) + (spotColors * totalSignatures);
        }
      }
    } else if (type === 'invoice' || type === 'receipt' || type === 'ncr') {
      innerPlates = 2; // زنكة للأصل + زنكة للصور
    }

    if (innerTotalInput && !innerTotalInput.dataset.manual) {
      innerTotalInput.value = innerPlates;
    }

    const actualInnerPlates = PricingMath.parseSafeNumber(innerTotalInput?.value, innerPlates);
    const unitPrice = PricingMath.parseSafeNumber(innerPriceInput?.value, 0);
    const setPrice = PricingMath.parseSafeNumber(innerPriceInput?.dataset?.setPrice || $(innerPriceInput).attr('data-set-price'), 0);

    let totalCost = 0;
    if (!isArchived && actualInnerPlates > 0) {
      if (setPrice > 0 && unitPrice > 0) {
        const fullSets = Math.floor(actualInnerPlates / 4);
        const remPlates = actualInnerPlates % 4;
        const costUnit = actualInnerPlates * unitPrice;
        const costSetRem = (fullSets * setPrice) + (remPlates * unitPrice);
        const costNextSet = (fullSets + (remPlates > 0 ? 1 : 0)) * setPrice;
        totalCost = Math.min(costUnit, costSetRem, costNextSet);
      } else if (setPrice > 0) {
        const totalSets = Math.ceil(actualInnerPlates / 4);
        totalCost = totalSets * setPrice;
      } else {
        totalCost = actualInnerPlates * unitPrice;
      }
    }

    if (innerPrintingType !== 'offset') {
      totalCost = 0;
    }

    const innerCtpSetBadge = document.getElementById('inner_ctp_set_badge');
    if (innerCtpSetBadge) {
      if (!isArchived && setPrice > 0 && actualInnerPlates >= 4 && innerPrintingType === 'offset') {
        innerCtpSetBadge.classList.remove('d-none');
      } else {
        innerCtpSetBadge.classList.add('d-none');
      }
    }

    if (innerCostDisplay) innerCostDisplay.textContent = this.formatMoney(totalCost);
    if (innerBadge) {
      innerBadge.textContent = isArchived ? `${this.config.i18n.archivedPlates} (0 ${this.config.currencySymbol})` : this.config.i18n.newPlates;
      innerBadge.className = isArchived
        ? 'badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1'
        : 'badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1';
    }

    return { totalPlates: actualInnerPlates, totalCost: totalCost, isArchived: isArchived };
  }

  /**
   * ربط مراقبي الموردين والماكينات عبر AJAX مع الـ Fallbacks
   */
  bindSupplierWatchers() {
    const self = this;

    // 1. مطبعة أوفست الغلاف — تحميل ماكينات ومواصفات المورد الفعلي
    $(document).on('change', '#id_cover_offset_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_cover_press_machine');
      const pressRateInput = $('#id_press_rate');

      if (!supplierId) {
        machineSelect.html('<option value="">-- اختر مطبعة الأوفست أولاً --</option>');
        pressRateInput.val('');
        $('#id_cover_press_service_id').val('');
        self.debouncedRecalculate();
      } else {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=offset`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              const bedSize = p.bed_size || '50x70';
              const stdBed = p.standard_bed_size || bedSize;
              optionsHtml += `<option value="${p.id}" data-bed="${bedSize}" data-std-bed="${stdBed}" data-rate="${p.price_per_1000 || 0}" data-floor="${p.setup_cost || 0}" data-service-id="${p.service_id}" data-set-price="${p.set_price || 0}" data-set-included-tirages="${p.set_included_tirages || 1}" ${isSel}>${p.name}</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            pressRateInput.val(first.price_per_1000 || '');
            $('#id_cover_press_service_id').val(first.service_id || '');
            const targetBed = first.standard_bed_size || first.bed_size;
            if (targetBed) $('#id_press_bed_size').val(targetBed).trigger('change');
          } else {
            machineSelect.html('<option value="">-- لا توجد ماكينات مسجلة لهذا المورد --</option>');
            pressRateInput.val('');
            $('#id_cover_press_service_id').val('');
          }
          self.debouncedRecalculate();
        }).fail(() => {
          machineSelect.html('<option value="">-- فشل جلب ماكينات المورد --</option>');
          pressRateInput.val('');
          $('#id_cover_press_service_id').val('');
          self.debouncedRecalculate();
        });
      }
    });

    // تغيير ماكينة أوفست الغلاف (المزامنة الدقيقة لسعر التراج ومقاس السرير المعتمد للمورد)
    $(document).on('change', '#id_cover_press_machine', function () {
      if (self.isSyncingFields) return;
      const selectedOpt = $(this).find('option:selected');
      const optRate = selectedOpt.data('rate');
      const optBed = selectedOpt.data('std-bed') || selectedOpt.data('bed');
      const svcId = selectedOpt.data('service-id');
      if (svcId) $('#id_cover_press_service_id').val(svcId);
      if (optRate !== undefined) $('#id_press_rate').val(optRate);

      self.isSyncingFields = true;
      if (optBed) $('#id_press_bed_size').val(optBed).trigger('change');

      const machineVal = $(this).val();
      const pieceSelect = $('#id_piece_size');
      if (machineVal === '50x70' || optBed === '50x70') {
        const opt = pieceSelect.find('option[data-cuts="2"]');
        if (opt.length && pieceSelect.val() !== opt.val()) pieceSelect.val(opt.val()).trigger('change.select2');
      } else if (machineVal === '35x50' || optBed === '35x50') {
        const opt = pieceSelect.find('option[data-cuts="4"]');
        if (opt.length && pieceSelect.val() !== opt.val()) pieceSelect.val(opt.val()).trigger('change.select2');
      } else if (machineVal === '70x100' || optBed === '70x100') {
        const opt = pieceSelect.find('option[data-cuts="1"]');
        if (opt.length && pieceSelect.val() !== opt.val()) pieceSelect.val(opt.val()).trigger('change.select2');
      }
      self.isSyncingFields = false;
      self.debouncedRecalculate(50);
    });

    // 2. مكتب فصل زنكات الغلاف CTP — السعر يتحدد فقط من مواصفات زنك المورد للمقاس المطلوب
    $(document).on('change', '#id_cover_ctp_supplier', function () {
      const supplierId = this.value;
      const bedSize = $('#id_press_bed_size').val() || '50x70';
      const platePriceInput = $('#id_plate_price');

      if (supplierId) {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=ctp`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let matched = data.presses.find(p => (p.standard_bed_size === bedSize || p.bed_size === bedSize)) || data.presses[0];
            if (matched) {
              platePriceInput.val(matched.price_per_1000 || '');
              platePriceInput.attr('data-set-price', matched.set_price || 0);
              $('#id_cover_ctp_service_id').val(matched.service_id || '');
            } else {
              platePriceInput.val('').removeAttr('data-set-price');
              $('#id_cover_ctp_service_id').val('');
            }
          } else {
            platePriceInput.val('').removeAttr('data-set-price');
            $('#id_cover_ctp_service_id').val('');
          }
          self.debouncedRecalculate();
        }).fail(() => {
          platePriceInput.val('').removeAttr('data-set-price');
          $('#id_cover_ctp_service_id').val('');
          self.debouncedRecalculate();
        });
      } else {
        platePriceInput.val('').removeAttr('data-set-price');
        $('#id_cover_ctp_service_id').val('');
        self.debouncedRecalculate();
      }
    });

    // 3. مركز ديجيتال الغلاف — جلب ماكينات المورد الحقيقية وتحديث السعر حسب مواصفات الماكينة ونمط الألوان
    $(document).on('change', '#id_cover_digital_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_cover_digital_machine');
      const clickPriceInput = $('#id_digital_sheet_price');

      if (!supplierId) {
        machineSelect.html('<option value="">-- اختر مركز الديجيتال أولاً --</option>');
        clickPriceInput.val('');
        $('#id_cover_digital_service_id').val('');
        self.debouncedRecalculate();
      } else {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=digital`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              const colorP = p.price_per_page_color || p.price_per_1000 || 0;
              const bwP = p.price_per_page_bw || 0;
              optionsHtml += `<option value="${p.id}" data-price-color="${colorP}" data-price-bw="${bwP}" data-service-id="${p.service_id}" ${isSel}>${p.name} (${self.formatMoney(colorP)})</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            const colorMode = $('#id_digital_color_mode').val() || '4_0';
            const isColor = colorMode.includes('4');
            const unitPrice = isColor ? (first.price_per_page_color || first.price_per_1000) : (first.price_per_page_bw || 0);
            clickPriceInput.val(unitPrice || '');
            $('#id_cover_digital_service_id').val(first.service_id || '');
          } else {
            machineSelect.html('<option value="">-- لا توجد ماكينات ديجيتال مسجلة لهذا المورد --</option>');
            clickPriceInput.val('');
            $('#id_cover_digital_service_id').val('');
          }
          self.debouncedRecalculate();
        }).fail(() => {
          machineSelect.html('<option value="">-- فشل جلب ماكينات المورد --</option>');
          clickPriceInput.val('');
          $('#id_cover_digital_service_id').val('');
          self.debouncedRecalculate();
        });
      }
    });

    // تغيير ماكينة ديجيتال الغلاف أو نمط الألوان (تحديث السعر المعتمد لطبعة الشيت لحظياً)
    $(document).on('change', '#id_cover_digital_machine, #id_digital_color_mode', function () {
      const selectedOpt = $('#id_cover_digital_machine').find('option:selected');
      if (selectedOpt.length && selectedOpt.val()) {
        const colorMode = $('#id_digital_color_mode').val() || '4_0';
        const isColor = colorMode.includes('4');
        const priceColor = parseFloat(selectedOpt.data('price-color')) || 0;
        const priceBw = parseFloat(selectedOpt.data('price-bw')) || 0;
        const svcId = selectedOpt.data('service-id');
        if (svcId) $('#id_cover_digital_service_id').val(svcId);
        $('#id_digital_sheet_price').val(isColor ? (priceColor || '') : (priceBw || ''));
        self.debouncedRecalculate();
      }
    });

    // 4. مطبعة أوفست الداخلي — تحميل ماكينات ومواصفات المورد الفعلي
    $(document).on('change', '#id_inner_offset_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_inner_press_machine');
      const pressRateInput = $('#id_inner_press_rate');

      if (!supplierId) {
        machineSelect.html('<option value="">-- اختر مطبعة الأوفست أولاً --</option>');
        pressRateInput.val('');
        $('#id_inner_press_service_id').val('');
        self.debouncedRecalculate();
      } else {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=offset`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              const bedSize = p.bed_size || '50x70';
              const stdBed = p.standard_bed_size || bedSize;
              optionsHtml += `<option value="${p.id}" data-bed="${bedSize}" data-std-bed="${stdBed}" data-rate="${p.price_per_1000 || 0}" data-floor="${p.setup_cost || 0}" data-service-id="${p.service_id}" data-set-price="${p.set_price || 0}" data-set-included-tirages="${p.set_included_tirages || 1}" ${isSel}>${p.name}</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            pressRateInput.val(first.price_per_1000 || '');
            $('#id_inner_press_service_id').val(first.service_id || '');
            const targetBed = first.standard_bed_size || first.bed_size;
            if (targetBed) $('#id_inner_press_bed_size').val(targetBed).trigger('change');
          } else {
            machineSelect.html('<option value="">-- لا توجد ماكينات مسجلة لهذا المورد --</option>');
            pressRateInput.val('');
            $('#id_inner_press_service_id').val('');
          }
          self.debouncedRecalculate();
        }).fail(() => {
          machineSelect.html('<option value="">-- فشل جلب ماكينات المورد --</option>');
          pressRateInput.val('');
          $('#id_inner_press_service_id').val('');
          self.debouncedRecalculate();
        });
      }
    });

    $(document).on('change', '#id_inner_press_machine', function () {
      const selectedOpt = $(this).find('option:selected');
      const optRate = selectedOpt.data('rate');
      const optBed = selectedOpt.data('std-bed') || selectedOpt.data('bed');
      const svcId = selectedOpt.data('service-id');
      if (svcId) $('#id_inner_press_service_id').val(svcId);
      if (optRate !== undefined) $('#id_inner_press_rate').val(optRate);
      if (optBed) $('#id_inner_press_bed_size').val(optBed).trigger('change');

      const machineVal = $(this).val();
      const innerPieceSelect = $('#id_inner_piece_size');
      if (innerPieceSelect.length) {
        if (machineVal === '50x70' || optBed === '50x70') {
          const opt = innerPieceSelect.find('option[data-cuts="2"]');
          if (opt.length) innerPieceSelect.val(opt.val()).trigger('change.select2');
        } else if (machineVal === '35x50' || optBed === '35x50') {
          const opt = innerPieceSelect.find('option[data-cuts="4"]');
          if (opt.length) innerPieceSelect.val(opt.val()).trigger('change.select2');
        } else if (machineVal === '70x100' || optBed === '70x100') {
          const opt = innerPieceSelect.find('option[data-cuts="1"]');
          if (opt.length) innerPieceSelect.val(opt.val()).trigger('change.select2');
        }
      }
      self.debouncedRecalculate();
    });

    // 5. مكتب فصل زنكات الداخلي CTP
    $(document).on('change', '#id_inner_ctp_supplier', function () {
      const supplierId = this.value;
      const bedSize = $('#id_inner_press_bed_size').val() || '50x70';
      const platePriceInput = $('#id_inner_plate_price');

      if (supplierId) {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=ctp`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let matched = data.presses.find(p => (p.standard_bed_size === bedSize || p.bed_size === bedSize)) || data.presses[0];
            if (matched) {
              platePriceInput.val(matched.price_per_1000 || '');
              platePriceInput.attr('data-set-price', matched.set_price || 0);
              $('#id_inner_ctp_service_id').val(matched.service_id || '');
            } else {
              platePriceInput.val('').removeAttr('data-set-price');
              $('#id_cover_ctp_service_id').val('');
            }
          } else {
            platePriceInput.val('').removeAttr('data-set-price');
            $('#id_inner_ctp_service_id').val('');
          }
          self.debouncedRecalculate();
        }).fail(() => {
          platePriceInput.val('').removeAttr('data-set-price');
          $('#id_inner_ctp_service_id').val('');
          self.debouncedRecalculate();
        });
      } else {
        platePriceInput.val('').removeAttr('data-set-price');
        $('#id_inner_ctp_service_id').val('');
        self.debouncedRecalculate();
      }
    });

    // 6. مركز ديجيتال الداخلي — جلب ماكينات المورد وتحديث أسعار طبعات الألوان والأسود بناءً على ماكينة المورد
    $(document).on('change', '#id_inner_digital_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_inner_digital_machine');
      const colorPriceInput = $('#id_digital_inner_color_price');
      const bwPriceInput = $('#id_digital_inner_bw_price');

      if (!supplierId) {
        machineSelect.html('<option value="">-- اختر مركز الديجيتال أولاً --</option>');
        colorPriceInput.val('');
        bwPriceInput.val('');
        $('#id_inner_digital_service_id').val('');
        self.debouncedRecalculate();
      } else {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=digital`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              const colorP = p.price_per_page_color || p.price_per_1000 || 0;
              const bwP = p.price_per_page_bw || 0;
              optionsHtml += `<option value="${p.id}" data-price-color="${colorP}" data-price-bw="${bwP}" data-service-id="${p.service_id}" ${isSel}>${p.name}</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            colorPriceInput.val(first.price_per_page_color || first.price_per_1000 || '');
            bwPriceInput.val(first.price_per_page_bw || '');
            $('#id_inner_digital_service_id').val(first.service_id || '');
          } else {
            machineSelect.html('<option value="">-- لا توجد ماكينات ديجيتال مسجلة لهذا المورد --</option>');
            colorPriceInput.val('');
            bwPriceInput.val('');
            $('#id_inner_digital_service_id').val('');
          }
          self.debouncedRecalculate();
        }).fail(() => {
          machineSelect.html('<option value="">-- فشل جلب ماكينات المورد --</option>');
          colorPriceInput.val('');
          bwPriceInput.val('');
          $('#id_inner_digital_service_id').val('');
          self.debouncedRecalculate();
        });
      }
    });

    $(document).on('change', '#id_inner_digital_machine', function () {
      const selectedOpt = $(this).find('option:selected');
      if (selectedOpt.length && selectedOpt.val()) {
        const priceColor = parseFloat(selectedOpt.data('price-color')) || 0;
        const priceBw = parseFloat(selectedOpt.data('price-bw')) || 0;
        const svcId = selectedOpt.data('service-id');
        if (svcId) $('#id_inner_digital_service_id').val(svcId);
        $('#id_digital_inner_color_price').val(priceColor || '');
        $('#id_digital_inner_bw_price').val(priceBw || '');
        self.debouncedRecalculate();
      }
    });

    // سنترة خيارات القوائم المنسدلة عند فتح select2 للحقول المحددة بـ text-center
    $(document).on('select2:open', function (e) {
      if ($(e.target).hasClass('text-center')) {
        $('.select2-dropdown .select2-results__option').css({
          'text-align': 'center',
          'text-align-last': 'center'
        });
      }
    });
  }

  /**
   * ربط مراقبي كارت الورق المؤسسي ومحول الأسعار والمثلث الذهبي
   */
  bindPaperCardWatchers() {
    const self = this;

    // 1. اتجاه ألياف الورق (طولي LG / عرضي SG)
    $(document).on('click', '#btn_toggle_grain', function () {
      const current = $(this).attr('data-grain') || 'LG';
      const next = (current === 'LG') ? 'SG' : 'LG';
      $(this).attr('data-grain', next);
      $('#id_grain_direction').val(next);
      $('#grain_direction_label').text(next === 'LG' ? 'LG طولي' : 'SG عرضي');
      self.showNotification(`تم تبديل اتجاه ألياف الورق إلى: ${next === 'LG' ? 'طولي (Long Grain)' : 'عرضي (Short Grain)'}`, 'info');
    });

    // 2. مصدر الورق (شراء مباشر / من المخزن / توريد العميل)
    $(document).on('change', 'input[name="paper_source"]', function () {
      const source = this.value;
      const priceInput = $('#id_paper_sheet_price');
      if (source === 'customer_supplied') {
        priceInput.prop('disabled', true).addClass('bg-light text-muted');
        $('#paper_price_mode_label').text('خامة توريد العميل');
        self.showNotification(`تم تحديد خامة توريد العميل: سيتم احتساب تكلفة الورق كـ 0.00 ${self.config.currencySymbol} كشغل مصنعية مع استمرار حساب الأفرخ لإذن الاستلام`, 'info');
      } else {
        priceInput.prop('disabled', false).removeClass('bg-light text-muted');
        $('#paper_price_mode_label').text('سعر الفرخ');
      }
      self.debouncedRecalculate();
    });

    // 3. طريقة تسعير الورق ومحول الوحدات (بالفرخ / بالرزمة / بالطن)
    $(document).on('change', 'input[name="price_input_mode"]', function () {
      const mode = this.value;
      if (mode === 'sheet') {
        $('#input_wrapper_ream').addClass('d-none');
        $('#input_wrapper_ton').addClass('d-none');
      } else if (mode === 'ream') {
        $('#input_wrapper_ream').removeClass('d-none');
        $('#input_wrapper_ton').addClass('d-none');
      } else if (mode === 'ton') {
        $('#input_wrapper_ton').removeClass('d-none');
        $('#input_wrapper_ream').addClass('d-none');
      }
      self.updateConvertedSheetPrice();
    });

    // حساب السعر المحول لحظياً عند كتابة سعر الرزمة أو الطن بالعملة الوظيفية
    $(document).on('input', '#input_ream_price, #input_ton_price', function () {
      self.updateConvertedSheetPrice();
    });

    // تطبيق السعر المحول في حقل سعر الفرخ
    $(document).on('click', '#btn_apply_converted_price', function () {
      const converted = parseFloat($('#calc_converted_sheet_display').data('converted-price')) || 0;
      if (converted > 0) {
        $('#id_paper_sheet_price').val(converted.toFixed(2));
        $('#paper_unit_converter_collapse').collapse('hide');
        self.recalculate();
        self.showNotification(`تم تطبيق سعر الفرخ المحول: ${converted.toFixed(2)} ${self.config.currencySymbol}`, 'success');
      }
    });

    // 4. المثلث الذهبي الميكانيكي (المزامنة الثنائية بين تفصيل الفرخ والماكينة وزنك CTP)

    $(document).on('change', '#id_piece_size', function () {
      if (self.isSyncingFields) return;
      self.isManualMontage = false; // تصفير التعديل اليدوي لاحتساب السقف الجديد لمقاس القطع المختار
      const selected = $(this).find('option:selected');
      const cuts = PricingMath.parseSafeNumber(selected.data('cuts'), 0);
      const machineSelect = $('#id_cover_press_machine');
      const plateSelect = $('#id_press_bed_size');

      self.isSyncingFields = true;
      if (cuts === 2) {
        if (plateSelect.length && plateSelect.find('option[value="50x70"]').length && plateSelect.val() !== '50x70') {
          plateSelect.val('50x70').trigger('change.select2');
        }
        if (machineSelect.find('option[value="50x70"]').length && machineSelect.val() !== '50x70') {
          machineSelect.val('50x70').trigger('change.select2');
        }
      } else if (cuts === 4) {
        if (plateSelect.length && plateSelect.find('option[value="35x50"]').length && plateSelect.val() !== '35x50') {
          plateSelect.val('35x50').trigger('change.select2');
        }
        if (machineSelect.find('option[value="35x50"]').length && machineSelect.val() !== '35x50') {
          machineSelect.val('35x50').trigger('change.select2');
        }
      } else if (cuts === 1) {
        if (plateSelect.length && plateSelect.find('option[value="70x100"]').length && plateSelect.val() !== '70x100') {
          plateSelect.val('70x100').trigger('change.select2');
        }
        if (machineSelect.find('option[value="70x100"]').length && machineSelect.val() !== '70x100') {
          machineSelect.val('70x100').trigger('change.select2');
        }
      }
      self.isSyncingFields = false;

      self.currentPieceName = self.getCleanPieceName();
      self.debouncedRecalculate(50);
    });



    // 6. منظومة تدفق كارت الورق الذكية المتتالية (Smart Cascading Without Circular Loop)
    $(document).on('change', '#id_paper_type', function (e) {
      if (self.isPaperCascadeUpdating) return;
      self.handlePaperTypeChange(true);
    });

    $(document).on('change', '#id_paper_supplier', function (e) {
      if (self.isPaperCascadeUpdating) return;
      self.handlePaperSupplierChange(true);
    });

    $(document).on('change', '#id_sheet_size', function (e) {
      if (self.isPaperCascadeUpdating) return;
      self.handleSheetSizeChange(true);
    });

    $(document).on('change', '#id_paper_weight', function (e) {
      if (self.isPaperCascadeUpdating) return;
      self.handlePaperWeightChange(true);
    });

    $(document).on('change', '#id_paper_origin', function () {
      if (self.isPaperCascadeUpdating || self.isSyncingOrigin) return;
      self.fetchLivePaperPrice();
      self.debouncedRecalculate(50);
    });

    // تبديل وضع عدد الأفرخ (يدوي / تلقائي) - الحقل السابع
    $(document).on('click', '#btn_toggle_manual_sheets', function () {
      self.toggleManualGrossSheets();
    });

    $(document).on('input', '#id_manual_gross_sheets', function () {
      self.manualGrossSheets = PricingMath.parseSafeNumber($(this).val(), 0);
      self.debouncedRecalculate(250);
    });

    // تحديث سعة رزمة الداخلي عند تغيير ورق أو جراماج الداخلي
    $(document).on('change', '#id_inner_paper_type', function () {
      self.updateResolvedInnerPackCapacity(false, 'type');
      self.debouncedRecalculate(50);
    });

    $(document).on('change', '#id_inner_paper_weight', function () {
      self.updateResolvedInnerPackCapacity(false, 'weight');
      self.debouncedRecalculate(50);
    });

    $(document).on('change', '#id_inner_paper_supplier, #id_inner_sheet_size', function () {
      self.debouncedRecalculate(50);
    });



    // 7. نسخ خامة ومورد ومقاس الغلاف إلى الداخلي
    $(document).on('click', '#btn_copy_cover_paper_to_inner', function () {
      const coverSup = $('#id_paper_supplier').val();
      const coverType = $('#id_paper_type').val();
      const coverSheetSize = $('#id_sheet_size').val();
      const coverWeight = $('#id_paper_weight').val();
      const coverPrice = $('#id_paper_sheet_price').val();

      if (coverSup) $('#id_inner_paper_supplier').val(coverSup).trigger('change');
      if (coverType) $('#id_inner_paper_type').val(coverType).trigger('change');
      if (coverSheetSize) $('#id_inner_sheet_size').val(coverSheetSize).trigger('change');
      if (coverWeight) $('#id_inner_paper_weight').val(coverWeight).trigger('change');
      if (coverPrice) $('#id_inner_sheet_price').val(coverPrice);

      self.recalculate();
      self.showNotification('تم نسخ خامة ومقاس ومورد الغلاف إلى كارت الداخلي بنجاح', 'success');
    });

    $(document).on('input', '#id_paper_sheet_price, #id_inner_sheet_price', function () {
      self.debouncedRecalculate();
    });
  }

  /**
   * دالة مساعدة لتحديث خيارات Select2 بأمان دون تدمير الـ DOM وتجنب الحلقات الدائرية
   */
  syncSelect2Options($select, options, selectedValue) {
    if (!$select || !$select.length) return;
    const currentVal = (selectedValue !== undefined && selectedValue !== null) ? selectedValue : $select.val();
    $select.empty();
    options.forEach(opt => {
      const isSel = (String(opt.value) === String(currentVal));
      const newOpt = new Option(opt.text, opt.value, isSel, isSel);
      if (opt.data) {
        Object.entries(opt.data).forEach(([k, v]) => $(newOpt).attr(`data-${k}`, v));
      }
      $select.append(newOpt);
    });
    $select.trigger('change.select2');
  }

  /**
   * الحقل 1: معالجة تغيير نوع الورق وجلب الموردين المتاح لديهم هذه الخامة
   */
  handlePaperTypeChange(userDriven = false) {
    if (this.isPaperCascadeUpdating) return;
    const self = this;
    const paperTypeId = $('#id_paper_type').val();

    if (!paperTypeId) {
      this.resetPaperCascade();
      return;
    }

    if (this.config.urls && this.config.urls.paperSuppliersApi) {
      if (this.activePaperAbort) this.activePaperAbort.abort();
      this.activePaperAbort = new AbortController();

      const url = `${this.config.urls.paperSuppliersApi}?paper_type_id=${encodeURIComponent(paperTypeId)}`;
      fetch(url, { signal: this.activePaperAbort.signal })
        .then(res => {
          if (res.status === 401 || res.status === 403) {
            self.showNotification('انتهت جلسة تسجيل الدخول، يرجى تسجيل الدخول مجدداً', 'warning');
            return null;
          }
          return res.json();
        })
        .then(data => {
          if (!data || !data.success) return;
          const suppliers = data.suppliers || [];
          const $supSelect = $('#id_paper_supplier');
          const currentSupVal = $supSelect.val();

          const opts = [{ value: '', text: '-- اختر تاجر الورق المعتمد --' }];
          suppliers.forEach(s => {
            const label = s.is_available_for_paper ? `★ ${s.name} (يوفر الخامة)` : s.name;
            opts.push({ value: s.id, text: label, data: { available: s.is_available_for_paper ? '1' : '0' } });
          });

          // الاحتفاظ بالمورد الحالي إن وجد، وإلا اختيار أول مورد يوفر الخامة
          const retainsCurrent = suppliers.some(s => String(s.id) === String(currentSupVal));
          let targetSup = '';
          if (retainsCurrent) {
            targetSup = currentSupVal;
          } else if (userDriven && suppliers.length > 0) {
            const firstAvail = suppliers.find(s => s.is_available_for_paper);
            if (firstAvail) targetSup = firstAvail.id;
          }

          self.isPaperCascadeUpdating = true;
          self.syncSelect2Options($supSelect, opts, targetSup);
          self.isPaperCascadeUpdating = false;

          if (targetSup) {
            self.handlePaperSupplierChange(userDriven);
          }
        })
        .catch(err => {
          if (err.name !== 'AbortError') console.warn('Error fetching paper suppliers:', err);
        });
    }

    this.updateResolvedPackCapacity(false, 'type');
    this.debouncedRecalculate();
  }

  /**
   * الحقل 2: معالجة اختيار مورد الورق وجلب مقاسات الفرخ المتوفرة لديه
   */
  handlePaperSupplierChange(userDriven = false) {
    if (this.isPaperCascadeUpdating) return;
    const self = this;
    const supplierId = $('#id_paper_supplier').val();
    const paperTypeId = $('#id_paper_type').val();
    const paperSource = $('input[name="paper_source"]:checked').val() || 'purchase';

    // فحص أمر الشراء اليتيم (Orphaned PO Guard)
    if (paperSource === 'purchase' && !supplierId) {
      $('#paper_supplier_note').html('<span class="text-warning"><i class="fas fa-exclamation-circle me-1"></i>تنبيه: يلزم تحديد المورد لتوليد أمر الشراء (PO) آلياً</span>');
    } else {
      $('#paper_supplier_note').text('ترشيح التجار الموفرين للخامة المحددة أولاً');
    }

    if (!supplierId && paperSource === 'purchase') {
      const $sheetSelect = $('#id_sheet_size');
      const $weightSelect = $('#id_paper_weight');
      const $originSelect = $('#id_paper_origin');
      self.isPaperCascadeUpdating = true;
      self.syncSelect2Options($sheetSelect, [{ value: '', text: '-- يلزم ملء المورد والورق أولاً --' }], '');
      self.syncSelect2Options($weightSelect, [{ value: '', text: '-- يلزم ملء المورد والورق أولاً --' }], '');
      self.syncSelect2Options($originSelect, [{ value: '', text: '-- يتحدد تلقائياً حسب خامة المورد --' }], '');
      self.isPaperCascadeUpdating = false;
      $('#id_paper_sheet_price').val('0.00');
      $('#paper_origin_note').text('يتزامن تلقائياً مع بلد منشأ خامة المورد');
      self.recalculate();
      return;
    }

    // جلب مقاسات الفرخ بناءً على المورد والورق
    if (this.config.urls && this.config.urls.paperSheetTypesApi) {
      if (this.activePaperAbort) this.activePaperAbort.abort();
      this.activePaperAbort = new AbortController();

      const url = `${this.config.urls.paperSheetTypesApi}?supplier_id=${encodeURIComponent(supplierId || '')}&paper_type_id=${encodeURIComponent(paperTypeId || '')}&paper_source=${encodeURIComponent(paperSource)}`;
      fetch(url, { signal: this.activePaperAbort.signal })
        .then(res => {
          if (res.status === 401 || res.status === 403) {
            self.showNotification('انتهت جلسة تسجيل الدخول، يرجى تسجيل الدخول مجدداً', 'warning');
            return null;
          }
          return res.json();
        })
        .then(data => {
          if (!data || !data.success) return;
          const sheetTypes = data.sheet_types || [];
          const $sheetSelect = $('#id_sheet_size');
          const currentSheetVal = $sheetSelect.val();

          if (sheetTypes.length === 0) {
            self.isPaperCascadeUpdating = true;
            self.syncSelect2Options($sheetSelect, [{ value: '', text: '-- لا توجد مقاسات مسجلة لهذا المورد --' }], '');
            self.isPaperCascadeUpdating = false;
            return;
          }

          const opts = [];
          sheetTypes.forEach(st => {
            opts.push({
              value: st.sheet_size || st.sheet_type,
              text: st.display_name || st.sheet_size,
              data: {
                width: st.width || 70,
                height: st.height || 100,
                id: st.id || ''
              }
            });
          });

          const retainsCurrent = sheetTypes.some(st => (st.sheet_size === currentSheetVal || st.sheet_type === currentSheetVal));
          const targetSheet = retainsCurrent ? currentSheetVal : (sheetTypes[0].sheet_size || sheetTypes[0].sheet_type);

          self.isPaperCascadeUpdating = true;
          self.syncSelect2Options($sheetSelect, opts, targetSheet);
          self.isPaperCascadeUpdating = false;

          if (targetSheet) {
            self.handleSheetSizeChange(userDriven);
          }
        })
        .catch(err => {
          if (err.name !== 'AbortError') console.warn('Error fetching sheet sizes:', err);
        });
    }

    this.debouncedRecalculate();
  }

  /**
   * تهيئة القائمة الأم لمقاسات القطع من الـ DOM
   */
  initPieceSizesMasterList() {
    if (this.masterPieceSizes && this.masterPieceSizes.length > 0) return;
    const $pieceSelect = $('#id_piece_size');
    if (!$pieceSelect.length) return;
    this.masterPieceSizes = [];
    $pieceSelect.find('option').each((idx, el) => {
      const $el = $(el);
      const val = $el.val();
      if (val === 'auto') return;
      this.masterPieceSizes.push({
        value: val,
        text: $el.text().trim(),
        name: $el.data('name') || '',
        cuts: $el.data('cuts') || 1,
        width: parseFloat($el.data('width')) || 0,
        height: parseFloat($el.data('height')) || 0,
        paperType: String($el.data('paper-type') || ''),
        paperWidth: parseFloat($el.data('paper-width')) || 0,
        paperHeight: parseFloat($el.data('paper-height')) || 0,
      });
    });
  }

  /**
   * فلترة وتحديث خيارات مقاس القطع لتناسب حصراً مقاس الفرخ المختار
   */
  updatePieceSizesForSheet(sheetSize, sheetSizeId, sheetW, sheetH) {
    const self = this;
    const $pieceSelect = $('#id_piece_size');
    if (!$pieceSelect.length) return;

    this.initPieceSizesMasterList();

    const currentPieceVal = $pieceSelect.val();
    const sheetIdStr = String(sheetSizeId || '');
    const sW = parseFloat(sheetW) || 0;
    const sH = parseFloat(sheetH) || 0;
    const minSW = (sW > 0 && sH > 0) ? Math.min(sW, sH) : 0;
    const maxSW = (sW > 0 && sH > 0) ? Math.max(sW, sH) : 0;

    let matched = [];
    if (this.masterPieceSizes && this.masterPieceSizes.length > 0) {
      matched = this.masterPieceSizes.filter(item => {
        // إذا كان مقاس قطع عام
        if (!item.paperType && !item.paperWidth && !item.paperHeight) return true;
        // تطابق بالـ ID المباشر لمقاس الورق
        if (sheetIdStr && item.paperType === sheetIdStr) return true;
        // تطابق بالأبعاد الهندسية المتبادلة
        if (minSW > 0 && maxSW > 0 && item.paperWidth > 0 && item.paperHeight > 0) {
          const itemMin = Math.min(item.paperWidth, item.paperHeight);
          const itemMax = Math.max(item.paperWidth, item.paperHeight);
          if (Math.abs(itemMin - minSW) < 1.0 && Math.abs(itemMax - maxSW) < 1.0) return true;
        }
        return false;
      });
    }

    const opts = [
      {
        value: 'auto',
        text: 'تلقائي (حسب المونتاج الحر)',
        data: { cuts: 'auto' }
      }
    ];

    matched.forEach(item => {
      opts.push({
        value: item.value,
        text: item.text,
        data: {
          name: item.name,
          cuts: item.cuts,
          width: item.width,
          height: item.height,
          'paper-type': item.paperType,
          'paper-width': item.paperWidth,
          'paper-height': item.paperHeight
        }
      });
    });

    const retainsCurrent = matched.some(m => String(m.value) === String(currentPieceVal));
    const targetPiece = (currentPieceVal === 'auto' || retainsCurrent) ? currentPieceVal : 'auto';

    self.syncSelect2Options($pieceSelect, opts, targetPiece);

    // التحقق من توافر API مقاسات القطع لجلب أي مقاسات مضافة حديثاً في قاعدة البيانات
    if (this.config.urls && this.config.urls.pieceSizesApi) {
      const url = `${this.config.urls.pieceSizesApi}?sheet_size_id=${encodeURIComponent(sheetSizeId || '')}&paper_sheet_type=${encodeURIComponent(sheetSize || '')}`;
      fetch(url)
        .then(res => res.json())
        .then(data => {
          if (data && data.success && data.piece_sizes && data.piece_sizes.length > 0) {
            const apiOpts = [
              {
                value: 'auto',
                text: 'تلقائي (حسب المونتاج الحر)',
                data: { cuts: 'auto' }
              }
            ];
            data.piece_sizes.forEach(ps => {
              apiOpts.push({
                value: ps.id,
                text: ps.display_name,
                data: {
                  name: ps.name,
                  cuts: ps.pieces_per_sheet || 1,
                  width: ps.width,
                  height: ps.height,
                  'paper-type': ps.paper_type_id || ''
                }
              });
            });
            const stillValid = data.piece_sizes.some(p => String(p.id) === String($pieceSelect.val()));
            const nextTarget = (stillValid || $pieceSelect.val() === 'auto') ? $pieceSelect.val() : 'auto';
            self.syncSelect2Options($pieceSelect, apiOpts, nextTarget);
          }
        })
        .catch(e => { /* fallback to matched client list */ });
    }
  }

  /**
   * الحقل 3: معالجة مقاس الفرخ وجلب الأوزان المتاحة واقتراح مقاس القطع
   */
  handleSheetSizeChange(userDriven = false) {
    if (this.isPaperCascadeUpdating) return;
    const self = this;
    const supplierId = $('#id_paper_supplier').val();
    const paperTypeId = $('#id_paper_type').val();
    const sheetSize = $('#id_sheet_size').val();
    const sheetOpt = $('#id_sheet_size option:selected');
    const sheetSizeId = sheetOpt.data('id') || '';
    const sheetW = sheetOpt.data('width') || '';
    const sheetH = sheetOpt.data('height') || '';

    // تحديث مقاسات القطع المتماشية مع مقاس الفرخ
    this.updatePieceSizesForSheet(sheetSize, sheetSizeId, sheetW, sheetH);

    // مزامنة مقاس القطع التلقائية مع ماكينة الأوفست
    const pressMachine = $('#id_cover_press_machine').val();
    const $pieceSelect = $('#id_piece_size');
    if (sheetSize && pressMachine && $pieceSelect.length) {
      if (pressMachine === '50x70' && (sheetSize.includes('70') && sheetSize.includes('100'))) {
        $pieceSelect.val('50x70').trigger('change.select2');
      } else if (pressMachine === '35x50' && (sheetSize.includes('70') && sheetSize.includes('100'))) {
        $pieceSelect.val('35x50').trigger('change.select2');
      }
    }

    // جلب الأوزان المتاحة حسب الخامة والمورد ومقاس الفرخ
    if (this.config.urls && this.config.urls.paperWeightsApi) {
      if (this.activePaperAbort) this.activePaperAbort.abort();
      this.activePaperAbort = new AbortController();

      const url = `${this.config.urls.paperWeightsApi}?supplier_id=${encodeURIComponent(supplierId || '')}&paper_type_id=${encodeURIComponent(paperTypeId || '')}&sheet_size=${encodeURIComponent(sheetSize || '')}`;
      fetch(url, { signal: this.activePaperAbort.signal })
        .then(res => res.json())
        .then(data => {
          if (!data || !data.success) return;
          const weights = data.weights || [];
          if (weights.length > 0) {
            const $weightSelect = $('#id_paper_weight');
            const currentWeightVal = $weightSelect.val();

            const opts = [];
            weights.forEach(w => {
              const label = w.is_available_with_supplier ? `★ ${w.display_name}` : w.display_name;
              opts.push({
                value: w.value || w.gsm,
                text: label,
                data: {
                  'sheets-per-pack': w.sheets_per_pack || 250,
                  available: w.is_available_with_supplier ? '1' : '0'
                }
              });
            });

            const retainsCurrent = weights.some(w => String(w.value || w.gsm) === String(currentWeightVal));
            const targetWeight = retainsCurrent ? currentWeightVal : (weights[0].value || weights[0].gsm);

            self.isPaperCascadeUpdating = true;
            self.syncSelect2Options($weightSelect, opts, targetWeight);
            self.isPaperCascadeUpdating = false;

            if (targetWeight) {
              self.handlePaperWeightChange(userDriven);
            }
          }
        })
        .catch(err => {
          if (err.name !== 'AbortError') console.warn('Error fetching paper weights:', err);
        });
    }

    this.debouncedRecalculate();
  }

  /**
   * الحقل 4: معالجة جرام الورق وجلب بلاد المنشأ المتاحة فعلياً
   */
  handlePaperWeightChange(userDriven = false) {
    if (this.isPaperCascadeUpdating) return;
    this.updateResolvedPackCapacity(false, 'weight');
    this.fetchAvailablePaperOrigins(userDriven);
    this.debouncedRecalculate();
  }

  /**
   * الحقل 6: جلب بلاد المنشأ المتاحة فقط بناءً على كافة متغيرات الورق
   * (المورد، نوع الورق، مقاس الفرخ، الجراماج)
   */
  fetchAvailablePaperOrigins(userDriven = false) {
    const self = this;
    const supplierId = $('#id_paper_supplier').val();
    const paperTypeId = $('#id_paper_type').val();
    const sheetSize = $('#id_sheet_size').val();
    const weight = $('#id_paper_weight').val();
    const paperSource = $('input[name="paper_source"]:checked').val() || 'purchase';
    const $originSelect = $('#id_paper_origin');
    if (!$originSelect.length) return;

    const currentOrigin = $originSelect.val();

    if (!this.config.urls || !this.config.urls.paperOriginsApi) {
      this.fetchLivePaperPrice();
      return;
    }

    if (this.activeOriginAbort) this.activeOriginAbort.abort();
    this.activeOriginAbort = new AbortController();

    const requestedSupplierId = supplierId;
    const requestedPaperTypeId = paperTypeId;
    const requestedSheetSize = sheetSize;
    const requestedWeight = weight;

    const params = new URLSearchParams();
    if (supplierId) params.append('supplier_id', supplierId);
    if (paperTypeId) params.append('paper_type_id', paperTypeId);
    if (sheetSize) params.append('sheet_size', sheetSize);
    if (weight) params.append('weight', weight);
    if (paperSource) params.append('paper_source', paperSource);

    const url = `${this.config.urls.paperOriginsApi}?${params.toString()}`;

    fetch(url, { signal: this.activeOriginAbort.signal })
      .then(res => {
        if (res.status === 401 || res.status === 403) {
          self.showNotification('انتهت جلسة تسجيل الدخول، يرجى تسجيل الدخول مجدداً', 'warning');
          return null;
        }
        return res.json();
      })
      .then(data => {
        // حماية سباق الردود المتأخرة (Race Condition Guard)
        if ($('#id_paper_supplier').val() !== requestedSupplierId ||
            $('#id_paper_type').val() !== requestedPaperTypeId ||
            $('#id_sheet_size').val() !== requestedSheetSize ||
            $('#id_paper_weight').val() !== requestedWeight) {
          return;
        }

        if (!data || !data.success) {
          self.fetchLivePaperPrice();
          return;
        }

        const origins = data.origins || [];
        const $note = $('#paper_origin_note');

        if (origins.length > 0) {
          const opts = [];
          origins.forEach(orig => {
            const origVal = orig.value || orig.name;
            opts.push({
              value: origVal,
              text: orig.display_name || orig.name,
              data: {
                code: orig.code || '',
                id: orig.id || ''
              }
            });
          });

          // إذا توفر منشأ يطابق المختار حالياً يُحتفظ به، وإلا يُختار أول منشأ متاح آلياً
          const retainsCurrent = origins.some(o => (o.value || o.name) === currentOrigin);
          const targetOrigin = retainsCurrent ? currentOrigin : (origins[0].value || origins[0].name);

          self.isSyncingOrigin = true;
          self.syncSelect2Options($originSelect, opts, targetOrigin);
          self.isSyncingOrigin = false;
        } else {
          // لا تتوفر أي مناشئ مسجلة لهذه المواصفة لدى التاجر
          self.isSyncingOrigin = true;
          self.syncSelect2Options($originSelect, [{ value: '', text: '-- لا يتوفر منشأ مسجل لهذه المواصفة --' }], '');
          self.isSyncingOrigin = false;

          if ($note.length) {
            $note.html('<span class="text-danger"><i class="fas fa-times-circle me-1"></i>لا يتوفر منشأ مسجل لدى التاجر لهذه المواصفة</span>');
          }

          // تصفير سعر الفرخ لعدم احتساب سعر وهمي
          $('#id_paper_sheet_price').val('0.00');
          self.recalculate();
          return;
        }

        // استدعاء السعر المباشر بالمنشأ المتاح المستقر
        self.fetchLivePaperPrice();
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.warn('Error fetching paper origins:', err);
          self.fetchLivePaperPrice();
        }
      });
  }

  /**
   * استعلام السعر المباشر ومزامنة بلد المنشأ آلياً
   */
  fetchLivePaperPrice() {
    const self = this;
    const supplierId = $('#id_paper_supplier').val();
    const paperTypeId = $('#id_paper_type').val();
    const sheetSize = $('#id_sheet_size').val();
    const weight = $('#id_paper_weight').val();
    const origin = $('#id_paper_origin').val();
    const paperSource = $('input[name="paper_source"]:checked').val() || 'purchase';

    if (paperSource === 'customer_supplied') {
      $('#id_paper_sheet_price').val('0.00');
      this.recalculate();
      return;
    }

    if (!supplierId || !paperTypeId || !sheetSize || !weight) return;

    if (this.config.urls && this.config.urls.paperPriceApi) {
      if (this.activePaperAbort) this.activePaperAbort.abort();
      this.activePaperAbort = new AbortController();

      const url = `${this.config.urls.paperPriceApi}?supplier_id=${encodeURIComponent(supplierId)}&paper_type_id=${encodeURIComponent(paperTypeId)}&sheet_size=${encodeURIComponent(sheetSize)}&weight=${encodeURIComponent(weight)}&origin=${encodeURIComponent(origin || '')}`;
      fetch(url, { signal: this.activePaperAbort.signal })
        .then(res => res.json())
        .then(data => {
            const sheetPrice = parseFloat(data.price) || 0.0;
            const $paperInput = $('#id_paper_sheet_price');
            $paperInput.val(sheetPrice.toFixed(2));
            $paperInput.attr('data-baseline-price', sheetPrice.toFixed(2));
            $paperInput.attr('data-service-id', data.service_id || '');
            $paperInput.attr('data-supplier-id', supplierId);
            $paperInput.attr('data-formula', data.pricing_formula || '');
            const ptName = $('#id_paper_type option:selected').text().trim() || 'ورق';
            $paperInput.attr('data-item-label', `${ptName} (${sheetSize} - ${weight} جم)`);
            $paperInput.attr('data-unit-label', 'فرخ');

            // مزامنة بلد المنشأ تلقائياً مع خامة المورد المسجلة لمنع تضارب الجودة
            if (data.origin) {
              const $originSelect = $('#id_paper_origin');
              let matchedOrigin = null;
              $originSelect.find('option').each(function () {
                if ($(this).val().toLowerCase().includes(data.origin.toLowerCase()) || $(this).text().includes(data.origin)) {
                  matchedOrigin = $(this).val();
                }
              });
              if (matchedOrigin && matchedOrigin !== $originSelect.val()) {
                self.isSyncingOrigin = true;
                $originSelect.val(matchedOrigin).trigger('change.select2');
                self.isSyncingOrigin = false;
              }
            }

            self.recalculate();
        })
        .catch(err => {
          if (err.name !== 'AbortError') console.warn('Error fetching paper price:', err);
        });
    }
  }

  /**
   * تبديل وضع حساب عدد الأفرخ (يدوي / تلقائي) - الحقل 7
   */
  toggleManualGrossSheets() {
    this.isManualSheetsActive = !this.isManualSheetsActive;
    const $boxAuto = $('#box_auto_sheets_display');
    const $boxManual = $('#box_manual_sheets_input');
    const $toggleBtnText = $('#toggle_manual_sheets_text');

    if (this.isManualSheetsActive) {
      $boxAuto.addClass('d-none');
      $boxManual.removeClass('d-none');
      $toggleBtnText.text('حساب تلقائي');
      const curGross = parseInt($('#display_cover_gross_sheets').text()) || 0;
      $('#id_manual_gross_sheets').val(curGross).focus();
      this.manualGrossSheets = curGross;
    } else {
      $boxManual.addClass('d-none');
      $boxAuto.removeClass('d-none');
      $toggleBtnText.text('تعديل يدوي');
      this.manualGrossSheets = null;
    }
    this.recalculate();
  }

  /**
   * تفريغ وإعادة تصفير كارت الورق عند مسح نوع الخامة أو المورد
   */
  resetPaperCascade() {
    $('#id_paper_sheet_price').val('0.00');
    $('#display_cover_gross_sheets').text('0 فرخ');
    $('#display_cover_reams_breakdown').text('0 رزمة');
    $('#display_cover_net_sheets').text('0');
    $('#display_cover_waste_sheets').text('0');
    $('#display_cover_weight_kg').text('0.0 كجم');
    $('#cover_paper_cost_display').text(this.formatMoney(0));
    const $originSelect = $('#id_paper_origin');
    if ($originSelect.length) {
      this.isSyncingOrigin = true;
      this.syncSelect2Options($originSelect, [{ value: '', text: '-- يتحدد تلقائياً حسب خامة المورد --' }], '');
      this.isSyncingOrigin = false;
    }
    $('#paper_origin_note').text('يتزامن تلقائياً مع بلد منشأ خامة المورد');
    this.recalculate();
  }

  /**
   * استنتاج وحسم سعة الرزمة المعتمدة ديناميكياً من الإعدادات
   */
  updateResolvedPackCapacity(isInitial = false, source = null) {
    const hiddenInput = $('#id_sheets_per_pack');
    const initialSavedVal = hiddenInput.data('initial');

    if (isInitial && initialSavedVal && PricingMath.parseSafeNumber(initialSavedVal, 0) > 0) {
      const savedCap = PricingMath.parseSafeNumber(initialSavedVal, 250);
      hiddenInput.val(savedCap);
      $('#val_sheets_per_pack').text(savedCap);
      $('#pack_addon_sheets').text(savedCap);
      this.updateConvertedSheetPrice();
      return;
    }

    const paperTypeOpt = $('#id_paper_type option:selected');
    const paperWeightOpt = $('#id_paper_weight option:selected');

    const overridePack = PricingMath.parseSafeNumber(paperTypeOpt.data('override-pack'), 0);
    const weightPack = PricingMath.parseSafeNumber(paperWeightOpt.data('sheets-per-pack'), 0);

    let resolvedCapacity = 250;
    if (source === 'weight') {
      // عند التغيير المباشر لجراماج الورق، الأولوية لسعة رزمة الجراماج
      resolvedCapacity = weightPack > 0 ? weightPack : (overridePack > 0 ? overridePack : 250);
    } else if (source === 'type') {
      // عند تغيير نوع الخامة، إذا كانت الخامة استثنائية (مثل ستيكر أو دوبلكس) تُعتمد سعتها، وإلا سعة الجراماج
      resolvedCapacity = overridePack > 0 ? overridePack : (weightPack > 0 ? weightPack : 250);
    } else {
      // التهيئة الافتراضية العامة
      if (weightPack > 0) {
        resolvedCapacity = weightPack;
      } else if (overridePack > 0) {
        resolvedCapacity = overridePack;
      }
    }

    hiddenInput.val(resolvedCapacity);
    $('#val_sheets_per_pack').text(resolvedCapacity);
    $('#pack_addon_sheets').text(resolvedCapacity);
    this.updateConvertedSheetPrice();
  }

  /**
   * استنتاج وحسم سعة رزم ورق الداخلي ديناميكياً
   */
  updateResolvedInnerPackCapacity(isInitial = false, source = null) {
    const hiddenInput = $('#id_inner_sheets_per_pack');
    if (!hiddenInput.length) return;

    const paperTypeOpt = $('#id_inner_paper_type option:selected');
    const paperWeightOpt = $('#id_inner_paper_weight option:selected');

    const overridePack = PricingMath.parseSafeNumber(paperTypeOpt.data('override-pack'), 0);
    const weightPack = PricingMath.parseSafeNumber(paperWeightOpt.data('sheets-per-pack'), 0);

    let resolvedCapacity = 500;
    if (source === 'weight') {
      resolvedCapacity = weightPack > 0 ? weightPack : (overridePack > 0 ? overridePack : 500);
    } else if (source === 'type') {
      resolvedCapacity = overridePack > 0 ? overridePack : (weightPack > 0 ? weightPack : 500);
    } else {
      if (weightPack > 0) {
        resolvedCapacity = weightPack;
      } else if (overridePack > 0) {
        resolvedCapacity = overridePack;
      }
    }

    hiddenInput.val(resolvedCapacity);
  }

  /**
   * حساب السعر المحول للفرخ من الرزمة أو الطن
   */
  updateConvertedSheetPrice() {
    const mode = $('input[name="price_input_mode"]:checked').val() || 'sheet';
    const display = $('#calc_converted_sheet_display');
    let converted = 0;

    if (mode === 'ream') {
      const reamPrice = parseFloat($('#input_ream_price').val()) || 0;
      const packCapacity = Math.max(1, PricingMath.parseSafeNumber($('#id_sheets_per_pack').val(), 250));
      converted = packCapacity > 0 ? (reamPrice / packCapacity) : 0;
    } else if (mode === 'ton') {
      const tonPrice = parseFloat($('#input_ton_price').val()) || 0;
      const sheetOpt = $('#id_sheet_size option:selected');
      const sw = PricingMath.parseSafeNumber(sheetOpt.data('width'), 100) / 100;
      const sh = PricingMath.parseSafeNumber(sheetOpt.data('height'), 70) / 100;
      const gsm = PricingMath.parseSafeNumber($('#id_paper_weight').val(), 300);
      const sheetWeightTon = (sw * sh * gsm) / 1000000;
      converted = tonPrice * sheetWeightTon;
    } else {
      converted = parseFloat($('#id_paper_sheet_price').val()) || 0;
    }

    display.data('converted-price', converted);
    display.text(`${converted.toFixed(2)} ${this.config.currencySymbol}`);
  }

  /**
   * النسخ السريع الآمن من الغلاف للداخلي
   */
  copyCoverPressToInner() {
    const coverSupplier = $('#id_cover_offset_supplier').val();
    const coverMachine = $('#id_cover_press_machine').val();
    const coverRate = $('#id_press_rate').val();
    const coverCtpSupp = $('#id_cover_ctp_supplier').val();
    const coverBed = $('#id_press_bed_size').val();
    const coverPlatePrice = $('#id_plate_price').val();

    if (coverSupplier) $('#id_inner_offset_supplier').val(coverSupplier).trigger('change');
    if (coverRate) $('#id_inner_press_rate').val(coverRate);
    if (coverCtpSupp) $('#id_inner_ctp_supplier').val(coverCtpSupp).trigger('change');
    if (coverBed) $('#id_inner_press_bed_size').val(coverBed);
    if (coverPlatePrice) $('#id_inner_plate_price').val(coverPlatePrice);

    this.debouncedRecalculate();
    this.showNotification('تم نسخ مطبعة ومقاس وإعدادات الغلاف إلى صفحات الداخلي بنجاح', 'success');
  }

  /**
   * النسخ السريع لخامة ومورد ورق الغلاف إلى ورق الداخلي
   */
  copyCoverPaperToInner() {
    const coverPaperSupp = $('#id_paper_supplier').val();
    const coverPaperType = $('#id_paper_type').val();
    const coverPaperWeight = $('#id_paper_weight').val();
    const coverSheetPrice = $('#id_paper_sheet_price').val();

    if (coverPaperSupp) $('#id_inner_paper_supplier').val(coverPaperSupp).trigger('change');
    if (coverPaperType) $('#id_inner_paper_type').val(coverPaperType).trigger('change');
    if (coverPaperWeight) $('#id_inner_paper_weight').val(coverPaperWeight).trigger('change');
    if (coverSheetPrice) $('#id_inner_sheet_price').val(coverSheetPrice);

    this.debouncedRecalculate();
    this.showNotification('تم نسخ خامة ومورد وسعر ورق الغلاف إلى ورق الداخلي بنجاح', 'success');
  }

  /**
   * التطبيق السريع لكافة الموردين المعتمدين المتوافقين بنقرة واحدة
   */
  applyPreferredSuppliers() {
    // 1. مطبعة الأوفست المعتمدة
    const $offset = $('#id_cover_offset_supplier');
    const $optOffset = $offset.find('option[data-preferred="true"]').first();
    if ($optOffset.length && $offset.val() !== $optOffset.val()) {
      $offset.val($optOffset.val()).trigger('change');
    }

    // 2. مكتب فصل زنكات CTP المعتمد
    const $ctp = $('#id_cover_ctp_supplier');
    const $optCtp = $ctp.find('option[data-preferred="true"]').first();
    if ($optCtp.length && $ctp.val() !== $optCtp.val()) {
      $ctp.val($optCtp.val()).trigger('change');
    }

    // 3. تاجر الورق المعتمد
    const $paper = $('#id_paper_supplier');
    const $optPaper = $paper.find('option[data-preferred="true"]').first();
    if ($optPaper.length && $paper.val() !== $optPaper.val()) {
      $paper.val($optPaper.val()).trigger('change');
    }

    // 4. مركز الديجيتال المعتمد
    const $digital = $('#id_cover_digital_supplier');
    const $optDig = $digital.find('option[data-preferred="true"]').first();
    if ($optDig.length && $digital.val() !== $optDig.val()) {
      $digital.val($optDig.val()).trigger('change');
    }

    // موردو الداخلي
    const $inOffset = $('#id_inner_offset_supplier');
    const $optInOffset = $inOffset.find('option[data-preferred="true"]').first();
    if ($optInOffset.length && $inOffset.val() !== $optInOffset.val()) {
      $inOffset.val($optInOffset.val()).trigger('change');
    }

    const $inCtp = $('#id_inner_ctp_supplier');
    const $optInCtp = $inCtp.find('option[data-preferred="true"]').first();
    if ($optInCtp.length && $inCtp.val() !== $optInCtp.val()) {
      $inCtp.val($optInCtp.val()).trigger('change');
    }

    const $inPaper = $('#id_inner_paper_supplier');
    const $optInPaper = $inPaper.find('option[data-preferred="true"]').first();
    if ($optInPaper.length && $inPaper.val() !== $optInPaper.val()) {
      $inPaper.val($optInPaper.val()).trigger('change');
    }

    const $inDig = $('#id_inner_digital_supplier');
    const $optInDig = $inDig.find('option[data-preferred="true"]').first();
    if ($optInDig.length && $inDig.val() !== $optInDig.val()) {
      $inDig.val($optInDig.val()).trigger('change');
    }

    this.showNotification('تم تطبيق حزمة الموردين المعتمدين وجاري جلب أسعار مواصفات الشغلانة', 'success');
    this.debouncedRecalculate();
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
   * 1. التحقق من اكتمال كافة الحقول الإلزامية في الخطوة 1 (بيانات الطلب والعميل ومقاس الشغلانة)
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
   * 2. مزامنة وتحديث حالة إظهار وإخفاء الأقسام (الخطوة 2 و 3) في الواجهة
   */
  updateGatesState() {
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
    const type = this.currentArchetype || selectEl?.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.value || 'flyer';
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
    $('#unit_price_display').text(`-- ${sym}`);
    $('#final_total_display').text(`-- ${sym}`);
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
            targetForm.submit();
          }
        });
        return false;
      }

      return true;
    };

    $(document).on('click', '#btn_save_order', guardSubmit);
    $(document).on('click', '#btn_save_draft', guardSubmit);
    $(document).on('submit', '#order-form, #orderForm', guardSubmit);
  }

  /**
   * تهيئة وتثبيت الأسعار المرجعية للموردين عند فتح الشاشة
   */
  initBaselinePrices() {
    const fields = [
      { id: '#id_paper_sheet_price', supplier_sel: '#id_paper_supplier', service_id_sel: '#id_paper_service_id', default_label: 'ورق الغلاف', unit: 'فرخ', service_type: 'paper' },
      { id: '#id_press_rate', supplier_sel: '#id_cover_offset_supplier', service_id_sel: '#id_cover_press_service_id', default_label: 'طباعة أوفست الغلاف', unit: 'تراج', service_type: 'offset' },
      { id: '#id_plate_price', supplier_sel: '#id_cover_ctp_supplier', service_id_sel: '#id_cover_ctp_service_id', default_label: 'زنكات CTP الغلاف', unit: 'زنكة', service_type: 'ctp' },
      { id: '#id_digital_sheet_price', supplier_sel: '#id_cover_digital_supplier', service_id_sel: '#id_cover_digital_service_id', default_label: 'طبعة ديجيتال الغلاف', unit: 'طبعة', service_type: 'digital' },
      { id: '#id_inner_sheet_price', supplier_sel: '#id_inner_paper_supplier', service_id_sel: '#id_inner_paper_service_id', default_label: 'ورق الداخلي', unit: 'فرخ', service_type: 'paper' },
      { id: '#id_inner_press_rate', supplier_sel: '#id_inner_offset_supplier', service_id_sel: '#id_inner_press_service_id', default_label: 'طباعة أوفست الداخلي', unit: 'تراج', service_type: 'offset' },
      { id: '#id_inner_plate_price', supplier_sel: '#id_inner_ctp_supplier', service_id_sel: '#id_inner_ctp_service_id', default_label: 'زنكات CTP الداخلي', unit: 'زنكة', service_type: 'ctp' },
      { id: '#id_inner_digital_sheet_price', supplier_sel: '#id_inner_digital_supplier', service_id_sel: '#id_inner_digital_service_id', default_label: 'طبعة ديجيتال الداخلي', unit: 'طبعة', service_type: 'digital' }
    ];

    fields.forEach(f => {
      const $el = $(f.id);
      if (!$el.length) return;
      const $supp = $(f.supplier_sel);
      const val = parseFloat($el.val());
      const suppId = $supp.length ? $supp.val() : null;
      if (suppId && !isNaN(val) && val > 0) {
        if (!$el.attr('data-baseline-price')) {
          $el.attr('data-baseline-price', val.toFixed(2));
          $el.attr('data-supplier-id', suppId);
          $el.attr('data-item-label', f.default_label);
          $el.attr('data-unit-label', f.unit);
          const svcId = $(f.service_id_sel).val();
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
    const fields = [
      { id: '#id_paper_sheet_price', supplier_sel: '#id_paper_supplier', default_label: 'ورق الغلاف', unit: 'فرخ', service_type: 'paper' },
      { id: '#id_press_rate', supplier_sel: '#id_cover_offset_supplier', default_label: 'طباعة أوفست الغلاف', unit: 'تراج', service_type: 'offset' },
      { id: '#id_plate_price', supplier_sel: '#id_cover_ctp_supplier', default_label: 'زنكات CTP الغلاف', unit: 'زنكة', service_type: 'ctp' },
      { id: '#id_digital_sheet_price', supplier_sel: '#id_cover_digital_supplier', default_label: 'طبعة ديجيتال الغلاف', unit: 'طبعة', service_type: 'digital' },
      { id: '#id_inner_sheet_price', supplier_sel: '#id_inner_paper_supplier', default_label: 'ورق الداخلي', unit: 'فرخ', service_type: 'paper' },
      { id: '#id_inner_press_rate', supplier_sel: '#id_inner_offset_supplier', default_label: 'طباعة أوفست الداخلي', unit: 'تراج', service_type: 'offset' },
      { id: '#id_inner_plate_price', supplier_sel: '#id_inner_ctp_supplier', default_label: 'زنكات CTP الداخلي', unit: 'زنكة', service_type: 'ctp' },
      { id: '#id_inner_digital_sheet_price', supplier_sel: '#id_inner_digital_supplier', default_label: 'طبعة ديجيتال الداخلي', unit: 'طبعة', service_type: 'digital' }
    ];

    fields.forEach(f => {
      const $el = $(f.id);
      if (!$el.length) return;
      const $supp = $(f.supplier_sel);
      const suppId = $el.attr('data-supplier-id') || ($supp.length ? $supp.val() : null);
      if (!suppId) return;

      const currentVal = parseFloat($el.val());
      const baselineVal = parseFloat($el.attr('data-baseline-price'));

      if (!isNaN(baselineVal) && !isNaN(currentVal) && baselineVal > 0 && currentVal > 0 && Math.abs(currentVal - baselineVal) >= 0.01) {
        const suppName = ($supp.find('option:selected').text() || 'المورد').replace(/⭐.*$/, '').trim();
        const itemLabel = $el.attr('data-item-label') || f.default_label;
        const unitLabel = $el.attr('data-unit-label') || f.unit;
        const svcId = $el.attr('data-service-id') || null;
        const formula = $el.attr('data-formula') || null;

        const sheetSize = $('#id_sheet_size').val() || '';
        const gsm = $('#id_paper_weight').val() || '';

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
          sheet_size: sheetSize
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
              paper_type_id: $('#id_paper_type').val() || null,
              gsm: cp.gsm || null,
              width: width,
              height: height
            });
          }
        });

        if (selectedUpdates.length > 0) {
          const syncUrl = this.config.urls?.syncOrderUnitPricesApi || '/printing-pricing/api/sync-order-unit-prices/';
          const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

          fetch(syncUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
              order_number: $('#id_order_number').val() || '',
              updates: selectedUpdates
            })
          })
          .then(res => res.json())
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
      const selectedTypeName = productTypeSelect?.options[productTypeSelect.selectedIndex]?.text?.trim() || 'مطبوعات';

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

    fetch('/printing-pricing/api/live-calculate/', {
      method: 'POST',
      body: formData,
      signal: this._abortController.signal,
      headers: {
        'X-CSRFToken': csrfToken
      }
    })
    .then(res => res.json())
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
      // 1. المونتاج واستغلال الفرخ
      if (data.montage) {
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
        if ($('#id_cover_waste_sheets').length && !$('#id_cover_waste_sheets').is(':focus')) {
          $('#id_cover_waste_sheets').val(data.paper.waste_sheets);
        }
      }

      // 3. وزن الورق بالكيلوجرام
      if (data.weight) {
        this.updateTextSafely('display_cover_weight_kg', `${data.weight.total_kg} كجم`);
      }

      // 4. سحبات وتكلفة الماكينة (مع فتحة الماكينة)
      if (data.printing) {
        this.updateTextSafely('display_machine_pulls_count', `${data.printing.press_pulls.toLocaleString()} سحبة`);
        this.updateTextSafely('display_machine_tirages', `(${data.printing.tirages} تراج)`);
        this.updateTextSafely('cover_press_cost_display', this.formatMoney(data.printing.applied_press_cost));
        const pullsText = document.getElementById('press_pulls_count');
        if (pullsText) {
          this.updateTextSafely(pullsText, `${data.printing.press_pulls.toLocaleString()} سحبة (${data.printing.tirages} تراج)`);
        }
      }

      // 5. الزنكات وتوفير الطبع والقلب
      if (data.plates) {
        this.updateTextSafely('cover_ctp_cost_display', this.formatMoney(data.plates.total_cost));
        if (data.plates.is_work_turn_savings) {
          $('#id_plate_count_back').val(0).prop('disabled', true);
          $('#work_turn_advisor_alert').removeClass('d-none');
        } else {
          $('#id_plate_count_back').prop('disabled', false);
          $('#work_turn_advisor_alert').addClass('d-none');
        }
        if (!$('#id_plate_count').is(':focus')) {
          $('#id_plate_count').val(data.plates.total_plates);
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

      // 9. السايدبار المالي المركزي والحقول المخفية
      if (data.totals) {
        if (data.currency_symbol) {
          this.config.currencySymbol = data.currency_symbol;
        }
        this.updateTextSafely('cost_printing_display', this.formatMoney(data.printing.total_cost + data.plates.total_cost));
        this.updateTextSafely('total_cost_display', this.formatMoney(data.totals.total_production_cost));
        this.lastKnownTotalCost = data.totals.total_production_cost;

        // مزامنة تكاليف الباك إند
        $('#id_material_cost').val(data.totals.materials_cost);
        $('#id_printing_cost').val((data.printing.total_cost + data.plates.total_cost).toFixed(2));
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
    const type = selectEl?.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.value || 'flyer';
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

    // مستشار تقليل الهدر الفوري
    this.updateTrimAdvisor(openW, openH);

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
   * مستشار تقليل الهدر الذكي
   */
  updateTrimAdvisor(openW, openH) {
    const curImp = PricingMath.calcImposition(100.0, 70.0, openW, openH);
    const testW = openW - 0.5;
    const testH = openH - 0.5;
    const altImp = PricingMath.calcImposition(100.0, 70.0, testW, testH);

    const trimBanner = document.getElementById('trim_advisor_banner');
    const trimText = document.getElementById('trim_advisor_text');

    if (altImp.cutsPerSheet > curImp.cutsPerSheet && testW > 5 && testH > 5) {
      if (trimBanner) trimBanner.classList.remove('d-none');
      if (trimText) {
        trimText.textContent = `وفر في الورق: تقليل المقاس بمقدار 0.5 سم فقط يرفع عائد الفرخ من ${curImp.cutsPerSheet} إلى ${altImp.cutsPerSheet} قطعة!`;
      }
      this.currentTrimSuggestion = {
        action: () => {
          const widthInput = document.getElementById('id_width');
          const heightInput = document.getElementById('id_height');
          if (widthInput) widthInput.value = testW.toFixed(1);
          if (heightInput) heightInput.value = testH.toFixed(1);
          this.updateOpenDimensionsDisplay();
          this.debouncedRecalculate();
        }
      };
    } else {
      if (trimBanner) trimBanner.classList.add('d-none');
      this.currentTrimSuggestion = null;
    }
  }

  /**
   * توليد ونسخ رسالة عرض السعر للواتساب (Universal Clipboard)
   */
  generateWhatsAppQuote() {
    const title = document.getElementById('id_title')?.value || 'مطبوعات فاخرة';
    const qty = document.getElementById('id_quantity')?.value || '1000';
    const total = document.getElementById('final_total_display')?.textContent || `0.00 ${this.config.currencySymbol}`;
    const unit = document.getElementById('unit_price_display')?.textContent || `0.00 ${this.config.currencySymbol}`;
    const isClosed = document.getElementById('id_is_closed_size')?.checked || false;
    const openDimsText = document.getElementById('open_dims_text')?.textContent || '';
    const sizeSelect = document.getElementById('id_product_size');
    const sizeName = sizeSelect?.options[sizeSelect.selectedIndex]?.text || '';
    const widthVal = document.getElementById('id_width')?.value;
    const heightVal = document.getElementById('id_height')?.value;
    const orientRadio = document.querySelector('input[name="print_orientation"]:checked');
    const orientLabel = orientRadio?.value === 'landscape' ? 'عرضي' : 'طولي';
    const openDirRadio = document.querySelector('input[name="open_direction"]:checked');
    const openDirLabel = openDirRadio?.value === 'top' ? 'فتح من أعلى' : (openDirRadio?.value === 'left' ? 'فتح إنجليزي (يسار)' : 'فتح عربي (يمين)');

    let sizeText = sizeSelect?.value === 'custom'
      ? `مقاس مخصص (${widthVal}×${heightVal} سم)`
      : `${sizeName}`;

    if (isClosed) {
      sizeText += ` (مقفول) [مفتوح: ${openDimsText}] - ${orientLabel} (${openDirLabel})`;
    } else {
      sizeText += ` - ${orientLabel}`;
    }

    const coverType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    let printMethodText = 'أوفست فاخر 4 ألوان';
    if (coverType === 'offset') {
      const sides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';
      const sidesLabel = sides === 'work_turn' ? 'طبع وقلب' : (sides === 'work_sheet' ? 'وجهين' : 'وجه واحد');
      const frontC = parseInt(document.getElementById('id_colors_front')?.value || '4', 10);
      const spotF = parseInt(document.getElementById('id_spot_colors_front')?.value || '0', 10);

      if (sides === 'work_sheet') {
        const backC = parseInt(document.getElementById('id_colors_back')?.value || '4', 10);
        const spotB = parseInt(document.getElementById('id_spot_colors_back')?.value || '0', 10);
        const totalSpot = spotF + spotB;
        printMethodText = `أوفست وجهين (${frontC}+${backC})` + (totalSpot > 0 ? ` + ${totalSpot} لون مخصوص` : '');
      } else {
        printMethodText = `أوفست ${sidesLabel} (${frontC} لون)` + (spotF > 0 ? ` + ${spotF} لون مخصوص` : '');
      }
    } else if (coverType === 'digital') {
      const clickMode = document.getElementById('id_digital_color_mode')?.value || '4_0';
      const clickLabel = clickMode === '4_4' ? 'وجهين ألوان (4/4)' : (clickMode === '4_1' ? 'وجه ألوان + ظهر أسود (4/1)' : (clickMode === '1_0' ? 'وجه واحد أسود' : 'وجه واحد ألوان'));
      printMethodText = `ديجيتال ليزر عالي الدقة ${clickLabel}`;
    } else if (coverType === 'digital_banner') {
      printMethodText = 'طباعة خامات كبيرة بالمتر المربع';
    } else if (coverType === 'screen') {
      printMethodText = 'سلك سكرين شابلونات يدوية فاخرة';
    } else if (coverType === 'none') {
      printMethodText = 'بدون طباعة (خامة جاهزة سادة)';
    }

    const paper = document.getElementById('id_paper_type')?.options[document.getElementById('id_paper_type')?.selectedIndex]?.text || '';
    const weight = document.getElementById('id_paper_weight')?.value || '300';
    const lam = document.getElementById('id_lamination')?.options[document.getElementById('id_lamination')?.selectedIndex]?.text || '';

    const text = `🌟 *عرض سعر طباعة معتمد - MWHEBA ERP* 🌟\n\n` +
      `📋 *الصنف:* ${title}\n` +
      `📐 *المقاس:* ${sizeText}\n` +
      `🔢 *الكمية:* ${Number(qty).toLocaleString()} قطعة/نسخة\n` +
      `📄 *المواصفات:* ورق ${paper} ${weight} جم | ${lam}\n` +
      `💰 *سعر القطعة:* ${unit}\n` +
      `💵 *إجمالي السعر:* ${total}\n` +
      `📌 *ملاحظة:* الأسعار صافية غير شاملة ضريبة القيمة المضافة (14%).\n` +
      `⏳ *الصلاحية:* صالح لمدة 5 أيام من تاريخه.\n\n` +
      `_شكراً لتعاملكم معنا، يسعدنا تأكيد طلبكم!_`;

    this.copyToClipboard(text);
  }

  /**
   * نسخ للنص بالحافظة مع Fallback للشبكات الداخلية HTTP
   */
  copyToClipboard(text) {
    const self = this;
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(() => {
        self.showNotification('تم نسخ ملخص عرض السعر للواتساب بنجاح 📲', 'success');
      }).catch(() => {
        self.fallbackCopyText(text);
      });
    } else {
      this.fallbackCopyText(text);
    }
  }

  /**
   * Fallback للنسخ عبر textarea مؤقتة
   */
  fallbackCopyText(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      this.showNotification('تم نسخ ملخص عرض السعر للواتساب بنجاح 📲', 'success');
    } catch (err) {
      this.showNotification('تعذر النسخ التلقائي، يرجى التحديد والنسخ يدوياً', 'warning');
    }
    document.body.removeChild(textArea);
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
window.PricingMath = PricingMath;
window.OrderFormUIController = OrderFormUIController;
