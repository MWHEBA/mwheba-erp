/**
 * MWHEBA ERP - Printing Pricing Master Engine
 * Module: PricingApiClient (Unified Network & API Client)
 * Version: 2.1.8
 * Responsibilities: Centralized AJAX/Fetch client for all pricing endpoints,
 * managing AbortControllers to prevent race conditions, and error normalization.
 */

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

// تصدير الكائن للنطاق العام
window.PricingApiClient = PricingApiClient;
