/**
 * MWHEBA ERP - Printing Pricing Master Engine
 * Module: PricingExport (Quote Generation, WhatsApp Formatting & Universal Clipboard)
 * Version: 2.1.8
 * Responsibilities: Formats interactive WhatsApp quotes, handles clipboard copying with fallback,
 * and user-facing notifications for export actions.
 */

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

// تصدير الكائن للنطاق العام
window.PricingExport = PricingExport;
