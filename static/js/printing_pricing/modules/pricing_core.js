/**
 * MWHEBA ERP - Printing Pricing Core Infrastructure Toolkit
 * Module: pricing_core.js
 * Version: 2.3.0
 *
 * Responsibilities:
 * 1. PricingMath: Pure mathematical computations, geometric imposition,
 *    physical spine calculation, sheet waste rates, tirage, markup. (Zero DOM coupling)
 * 2. PricingApiClient: Centralized network & Fetch client for all pricing endpoints,
 *    managing AbortControllers to prevent race conditions, and error normalization.
 * 3. PricingExport: Formats interactive WhatsApp quotes, handles clipboard copying with fallback,
 *    and user-facing notifications for export actions.
 */

// ============================================================================
// 1. كائن العمليات الحسابية والمونتاج الصرف (PricingMath)
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
   * تسوية ومطابقة النصوص العربية وإزالة الهمزات والتشكيل والتاء المربوطة
   */
  normalizeArabic(text) {
    if (!text) return '';
    return String(text)
      .trim()
      .replace(/[إأآا]/g, 'ا')
      .replace(/ة/g, 'ه')
      .replace(/ى/g, 'ي')
      .replace(/[\u064B-\u065F]/g, '');
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
  calcPullsAndTirage(grossSheets, sidesMultiplier = 1, sidesMode = 'single') {
    if (sidesMode === 'work_sheet') {
      const pulls = Math.ceil(grossSheets * 2);
      const tiragesFront = grossSheets > 0 ? Math.max(1, Math.ceil(grossSheets / 1000)) : 0;
      const tiragesBack = grossSheets > 0 ? Math.max(1, Math.ceil(grossSheets / 1000)) : 0;
      return {
        pulls: pulls,
        tirages: tiragesFront + tiragesBack,
        tiragesFront: tiragesFront,
        tiragesBack: tiragesBack
      };
    }
    const pulls = Math.ceil(grossSheets * sidesMultiplier);
    const tirages = pulls > 0 ? Math.max(1, Math.ceil(pulls / 1000)) : 0;
    return {
      pulls: pulls,
      tirages: tirages,
      tiragesFront: tirages,
      tiragesBack: 0
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
// 2. فئة عميل الشبكة والـ API الموحد (PricingApiClient)
// ============================================================================
class PricingApiClient {
  constructor(config = {}) {
    this.config = config;
    this.abortControllers = new Map();
  }

  /**
   * إدارة وتجديد AbortController لمفتاح معين لمنع سباق الردود المتأخرة
   */
  getAbortSignal(key) {
    if (this.abortControllers.has(key)) {
      try {
        this.abortControllers.get(key).abort();
      } catch (e) {}
    }
    const controller = new AbortController();
    this.abortControllers.set(key, controller);
    return controller.signal;
  }

  /**
   * إلغاء كافة الطلبات المعلقة
   */
  abortAll() {
    this.abortControllers.forEach(controller => {
      try {
        controller.abort();
      } catch (e) {}
    });
    this.abortControllers.clear();
  }

  /**
   * جلب ماكينات ومواصفات المورد (أوفست / CTP / ديجيتال) مع كبح سباق الردود
   */
  async getPresses(supplierId, orderType = 'offset') {
    const pressesApiUrl = this.config.urls?.pressesApi || '/api/printing/presses/';
    const signal = this.getAbortSignal(`presses_${orderType}`);
    const url = `${pressesApiUrl}?supplier_id=${encodeURIComponent(supplierId)}&order_type=${encodeURIComponent(orderType)}`;
    const res = await fetch(url, { signal });
    return res.json();
  }

  /**
   * جلب أنواع الورق المتاحة لمورد معين (يقصر على المتاح فعلياً فقط)
   */
  async getPaperTypes(supplierId, onlyAvailable = true) {
    if (!this.config.urls?.paperTypesApi) return null;
    const params = new URLSearchParams();
    if (supplierId) params.append('supplier_id', supplierId);
    if (onlyAvailable) params.append('only_available', '1');
    const url = `${this.config.urls.paperTypesApi}?${params.toString()}`;
    const res = await fetch(url);
    return res.json();
  }

  /**
   * جلب الموردين المتاح لديهم نوع خامة محدد (يقصر على المتاحين فعلياً فقط)
   */
  async getPaperSuppliers(paperTypeId, onlyAvailable = true) {
    if (!this.config.urls?.paperSuppliersApi) return null;
    const params = new URLSearchParams();
    if (paperTypeId) params.append('paper_type_id', paperTypeId);
    if (onlyAvailable) params.append('only_available', '1');
    const url = `${this.config.urls.paperSuppliersApi}?${params.toString()}`;
    const res = await fetch(url);
    return res.json();
  }

  /**
   * جلب مقاسات الفرخ المتوفرة لمورد معين مع كبح التكرار
   */
  async getSheetSizes(supplierId, paperTypeId = '', paperSource = '') {
    if (!this.config.urls?.paperSheetTypesApi) return null;
    const signal = this.getAbortSignal('paper_sheet_size');
    const params = new URLSearchParams();
    if (supplierId) params.append('supplier_id', supplierId);
    if (paperTypeId) params.append('paper_type_id', paperTypeId);
    if (paperSource) params.append('paper_source', paperSource);
    const url = `${this.config.urls.paperSheetTypesApi}?${params.toString()}`;
    const res = await fetch(url, { signal });
    return res.json();
  }

  /**
   * جلب أوزان الورق المتاحة للفرخ
   */
  async getPaperWeights(supplierId, sheetSize, paperTypeId = '') {
    if (!this.config.urls?.paperWeightsApi) return null;
    const signal = this.getAbortSignal('paper_weight');
    const params = new URLSearchParams();
    if (supplierId) params.append('supplier_id', supplierId);
    if (paperTypeId) params.append('paper_type_id', paperTypeId);
    if (sheetSize) params.append('sheet_size', sheetSize);
    const url = `${this.config.urls.paperWeightsApi}?${params.toString()}`;
    const res = await fetch(url, { signal });
    return res.json();
  }

  /**
   * جلب مقاسات القطع المتوافقة مع الفرخ
   */
  async getPieceSizes(sheetSize, sheetSizeId = '') {
    if (!this.config.urls?.pieceSizesApi) return null;
    const params = new URLSearchParams();
    if (sheetSize) params.append('paper_sheet_type', sheetSize);
    if (sheetSizeId) params.append('sheet_size_id', sheetSizeId);
    const url = `${this.config.urls.pieceSizesApi}?${params.toString()}`;
    const res = await fetch(url);
    return res.json();
  }

  /**
   * جلب مناشئ الورق المتاحة للمواصفة
   */
  async getPaperOrigins(params) {
    if (!this.config.urls?.paperOriginsApi) return null;
    const signal = this.getAbortSignal('paper_origin');
    const cleanParams = new URLSearchParams();
    Object.keys(params || {}).forEach(k => {
      if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
        cleanParams.append(k, params[k]);
      }
    });
    const url = `${this.config.urls.paperOriginsApi}?${cleanParams.toString()}`;
    const res = await fetch(url, { signal });
    return res.json();
  }

  /**
   * جلب السعر المباشر للفرخ
   */
  async getLivePaperPrice(params) {
    if (!this.config.urls?.paperPriceApi) return null;
    const signal = this.getAbortSignal('paper_price');
    const cleanParams = new URLSearchParams();
    Object.keys(params || {}).forEach(k => {
      if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
        cleanParams.append(k, params[k]);
      }
    });
    const url = `${this.config.urls.paperPriceApi}?${cleanParams.toString()}`;
    const res = await fetch(url, { signal });
    return res.json();
  }

  /**
   * مزامنة أسعار الخدمات والورق في الطلب مع أحدث أسعار الموردين
   */
  async syncOrderUnitPrices(payload, csrfToken) {
    if (!this.config.urls?.syncOrderUnitPricesApi) return null;
    const res = await fetch(this.config.urls.syncOrderUnitPricesApi, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken || ''
      },
      body: JSON.stringify(payload)
    });
    return res.json();
  }

  /**
   * استدعاء محرك التسعير اللحظي في الباك إند
   */
  async calculateLive(formData, csrfToken) {
    const signal = this.getAbortSignal('live_calculate');
    const res = await fetch('/printing-pricing/api/live-calculate/', {
      method: 'POST',
      body: formData,
      signal,
      headers: {
        'X-CSRFToken': csrfToken || ''
      }
    });
    return res.json();
  }

  /**
   * تنسيق خيارات أنواع الورق لعناصر Select2
   */
  formatPaperTypeOptions(types) {
    return (types || []).map(t => ({
      value: t.id,
      text: t.name,
      data: {
        code: (t.name || '').toLowerCase(),
        overridePack: t.override_sheets_per_pack || ''
      }
    }));
  }

  /**
   * تنسيق خيارات الموردين لعناصر Select2
   */
  formatSupplierOptions(suppliers) {
    const opts = [{ value: '', text: '-- اختر تاجر الورق --' }];
    if (!suppliers || suppliers.length === 0) {
      opts.push({ value: '', text: '-- لا يتوفر تجار مسجلين لهذه الخامة --' });
      return opts;
    }
    suppliers.forEach(s => {
      const label = s.is_preferred ? `${s.name} ⭐` : s.name;
      opts.push({
        value: s.id,
        text: label,
        data: {
          available: '1',
          preferred: s.is_preferred ? 'true' : 'false',
          phone: s.phone || '',
          contact: s.contact_person || '',
          notes: s.notes || ''
        }
      });
    });
    return opts;
  }

  /**
   * تنسيق خيارات مقاسات الفرخ لعناصر Select2
   */
  formatSheetSizeOptions(sheetTypes) {
    return (sheetTypes || []).map(st => ({
      value: st.sheet_size || st.sheet_type,
      text: st.display_name || st.sheet_size,
      data: {
        width: st.width || 70,
        height: st.height || 100,
        id: st.id || ''
      }
    }));
  }

  /**
   * تنسيق خيارات أوزان الورق لعناصر Select2
   */
  formatWeightOptions(weights) {
    return (weights || []).map(w => ({
      value: w.value || w.gsm,
      text: w.display_name,
      data: {
        'sheets-per-pack': w.sheets_per_pack || 250,
        available: w.is_available_with_supplier ? '1' : '0'
      }
    }));
  }

  /**
   * تنسيق خيارات مناشئ الورق لعناصر Select2
   */
  formatOriginOptions(origins) {
    return (origins || []).map(orig => ({
      value: orig.value || orig.name,
      text: orig.display_name || orig.name,
      data: {
        code: orig.code || '',
        id: orig.id || ''
      }
    }));
  }
}

// ============================================================================
// 3. كائن تصدير عروض الأسعار والواتساب (PricingExport)
// ============================================================================
const PricingExport = {
  /**
   * توليد ونسخ رسالة عرض السعر للواتساب (Universal Clipboard)
   */
  generateWhatsAppQuote(controller) {
    const config = controller?.config || {};
    const ptEl = document.getElementById('id_product_type') || document.getElementById('id_order_type');
    const title = document.getElementById('id_title')?.value || ptEl?.options?.[ptEl?.selectedIndex]?.text || ptEl?.value || 'مطبوع تجاري';
    const qty = document.getElementById('id_quantity')?.value || '1000';
    const sym = config.currencySymbol || '';
    const rawTotal = document.getElementById('final_total_display')?.textContent?.trim() || '0.00';
    const total = (rawTotal.includes(sym) || !sym) ? rawTotal : `${rawTotal} ${sym}`;
    const rawUnit = document.getElementById('unit_price_display')?.textContent?.trim() || '0.00';
    const unit = (rawUnit.includes(sym) || !sym) ? rawUnit : `${rawUnit} ${sym}`;
    const isClosed = document.getElementById('id_is_closed_size')?.checked || false;
    const openDimsText = document.getElementById('open_dims_text')?.textContent || '';
    const sizeSelect = document.getElementById('id_product_size');
    const sizeName = sizeSelect?.options?.[sizeSelect.selectedIndex]?.text || '';
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

    const paperEl = document.getElementById('id_paper_type');
    const paper = paperEl?.options?.[paperEl.selectedIndex]?.text || '';
    const weight = document.getElementById('id_paper_weight')?.value || '300';
    const lamEl = document.getElementById('id_lamination');
    const lam = lamEl?.options?.[lamEl.selectedIndex]?.text || '';

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

    this.copyToClipboard(text, controller);
  },

  /**
   * نسخ للنص بالحافظة مع Fallback للشبكات الداخلية HTTP
   */
  copyToClipboard(text, controller) {
    const notify = (msg, type) => {
      if (controller && typeof controller.showNotification === 'function') {
        controller.showNotification(msg, type);
      } else if (typeof window.showNotification === 'function') {
        window.showNotification(msg, type);
      } else if (typeof window.showToastr === 'function') {
        window.showToastr(msg, type);
      }
    };

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(() => {
        notify('تم نسخ ملخص عرض السعر للواتساب بنجاح 📲', 'success');
      }).catch(() => {
        this.fallbackCopyText(text, notify);
      });
    } else {
      this.fallbackCopyText(text, notify);
    }
  },

  /**
   * Fallback للنسخ عبر textarea مؤقتة
   */
  fallbackCopyText(text, notifyFn) {
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
      if (typeof notifyFn === 'function') {
        notifyFn('تم نسخ ملخص عرض السعر للواتساب بنجاح 📲', 'success');
      }
    } catch (err) {
      if (typeof notifyFn === 'function') {
        notifyFn('تعذر النسخ التلقائي، يرجى التحديد والنسخ يدوياً', 'warning');
      }
    }
    document.body.removeChild(textArea);
  }
};

// ============================================================================
// تصدير الكائنات عالمياً على النطاق العام (Global Exports)
// ============================================================================
if (typeof window !== 'undefined') {
  window.PricingMath = PricingMath;
  window.PricingApiClient = PricingApiClient;
  window.PricingExport = PricingExport;
}
