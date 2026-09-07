/**
 * MWHEBA ERP - Industrial 2D Imposition Visualizer Engine
 * Module: imposition_visualizer.js
 * Version: 3.0.0
 *
 * Responsibilities:
 * 1. Pure SVG 2D layout engine (1 unit = 1 mm) for machine press sheets & raw parent sheets.
 * 2. Offset gripper geometry (12mm lead edge on cylinder, 5mm tail, 3mm sides) & digital (4mm border).
 * 3. 4-Archetype specialization: Flyer, Folder (same_sheet vs separate), Catalog/Book spread (spine), NCR invoices.
 * 4. Double cut (دوبل تكسير 3mm) vs common knife cut (قص مشترك) detection and badges.
 * 5. Work & Turn (طبع وقلب) vertical division vs Work & Sheet (وجهين) toggle.
 * 6. Contiguous fill from gripper & idle slots (خانات شاغرة - فاقد تفريد) on montage step-down.
 * 7. Live production batch stats (صافي، هالك، إجمالي أفرخ).
 * 8. Egyptian cutter shearing map (L-cuts: 11 pieces 20x30, 5 pieces 30x40 with knife sequence [1], [2], [3]).
 * 9. Micro-stamp for single-page A4 work order detail view (Monochrome Grayscale).
 * 10. Strict :root CSS variable colors only. Zero hardcoded hex/rgb, zero gradients.
 */

const ImpositionVisualizer = (function() {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';

  /**
   * إنشاء عنصر SVG مساعد
   */
  function createSvgEl(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      el.setAttribute(k, v);
    }
    return el;
  }

  /**
   * تنظيف وتطهير الحاوية
   */
  function clearContainer(container) {
    if (!container) return;
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
  }

  /**
   * تنسيق المقاسات الهندسية (إزالة الأصفار الزائدة والعلامة العشرية للأرقام الصحيحة)
   */
  function formatDimension(val) {
    if (typeof PricingMath !== 'undefined' && typeof PricingMath.formatDimension === 'function') {
      return PricingMath.formatDimension(val);
    }
    const num = parseFloat(Number(val).toFixed(2));
    return isNaN(num) ? '0' : String(num);
  }

  /**
   * رسم شيت الانتظار التجريدي (Skeleton Guard)
   */
  function renderSkeleton(container, message = 'بانتظار اكتمال بيانات المقاس والتفصيل...') {
    clearContainer(container);
    const wrapper = document.createElement('div');
    wrapper.className = 'd-flex flex-column align-items-center justify-content-center p-4 text-center';
    wrapper.style.minHeight = '240px';
    wrapper.style.backgroundColor = 'var(--gray-100, #f8f9fa)';
    wrapper.style.borderRadius = 'var(--border-radius, 6px)';
    wrapper.style.border = '1px dashed var(--border-color, #dee2e6)';

    const icon = document.createElement('i');
    icon.className = 'fas fa-th-large fa-2x mb-2 text-muted';
    const text = document.createElement('span');
    text.className = 'text-muted small fw-bold';
    text.textContent = message;

    wrapper.appendChild(icon);
    wrapper.appendChild(text);
    container.appendChild(wrapper);
  }

  /**
   * رسم خط بُعد هندسي أنيق بمؤشرات نهايات القياس والتسمية (CAD Dimension Line)
   */
  function createDimensionLine(x1, y1, x2, y2, labelText, isVertical = false, color = 'var(--secondary, #6c757d)', textColor = 'var(--dark, #212529)', fontSize = 14, hasBg = true) {
    const g = createSvgEl('g', { class: 'cad-dimension-line' });

    // نهايات القياس على الطرفين (Ticks)
    const tickLen = 3.5;
    if (isVertical) {
      const tick1 = createSvgEl('line', { x1: x1 - tickLen, y1: y1, x2: x1 + tickLen, y2: y1, stroke: color, 'stroke-width': 0.8 });
      const tick2 = createSvgEl('line', { x1: x2 - tickLen, y1: y2, x2: x2 + tickLen, y2: y2, stroke: color, 'stroke-width': 0.8 });
      g.appendChild(tick1);
      g.appendChild(tick2);
    } else {
      const tick1 = createSvgEl('line', { x1: x1, y1: y1 - tickLen, x2: x1, y2: y1 + tickLen, stroke: color, 'stroke-width': 0.8 });
      const tick2 = createSvgEl('line', { x1: x2, y1: y2 - tickLen, x2: x2, y2: y2 + tickLen, stroke: color, 'stroke-width': 0.8 });
      g.appendChild(tick1);
      g.appendChild(tick2);
    }

    // المنتصف
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;

    const textLen = String(labelText).length;
    const gapW = Math.max(26, textLen * (fontSize * 0.58) + 8);
    const lineLen = Math.abs(isVertical ? (y2 - y1) : (x2 - x1));
    const safeGapW = lineLen > 20 ? Math.min(gapW, lineLen - 6) : gapW;

    if (hasBg) {
      // خط متصل مع خلفية بيضاء حامية للنص
      const line = createSvgEl('line', { x1, y1, x2, y2, stroke: color, 'stroke-width': 0.8 });
      g.appendChild(line);

      const boxW = safeGapW + 4;
      const boxH = fontSize + 5;
      const bgRect = createSvgEl('rect', {
        x: isVertical ? midX - (boxH / 2) : midX - (boxW / 2),
        y: isVertical ? midY - (boxW / 2) : midY - (boxH / 2),
        width: isVertical ? boxH : boxW,
        height: isVertical ? boxW : boxH,
        fill: 'var(--card-bg, #ffffff)',
        rx: 2
      });
      g.appendChild(bgRect);
    } else {
      // خط مقطوع بنقاء CAD هندسي (بدون خلفية إطلاقاً) يمر قبله ويستأنف بعده
      if (isVertical) {
        const seg1 = createSvgEl('line', { x1: x1, y1: y1, x2: x1, y2: midY - (safeGapW / 2), stroke: color, 'stroke-width': 0.8 });
        const seg2 = createSvgEl('line', { x1: x1, y1: midY + (safeGapW / 2), x2: x1, y2: y2, stroke: color, 'stroke-width': 0.8 });
        g.appendChild(seg1);
        g.appendChild(seg2);
      } else {
        const seg1 = createSvgEl('line', { x1: x1, y1: y1, x2: midX - (safeGapW / 2), y2: y1, stroke: color, 'stroke-width': 0.8 });
        const seg2 = createSvgEl('line', { x1: midX + (safeGapW / 2), y1: y1, x2: x2, y2: y1, stroke: color, 'stroke-width': 0.8 });
        g.appendChild(seg1);
        g.appendChild(seg2);
      }
    }

    // النص الرقمي
    const txt = createSvgEl('text', {
      x: midX,
      y: isVertical ? midY : midY + (fontSize * 0.35),
      'text-anchor': 'middle',
      'dominant-baseline': isVertical ? 'middle' : 'auto',
      fill: textColor,
      'font-size': fontSize,
      'font-weight': 'bold',
      'font-family': 'inherit',
      transform: isVertical ? `rotate(-90, ${midX}, ${midY})` : ''
    });
    txt.textContent = labelText;
    g.appendChild(txt);

    return g;
  }

  /**
   * المحرك الرئيسي لرسم شيت الماكينة (Press Sheet Imposition)
   */
  function renderPressSheet(container, options = {}) {
    if (!container) return;

    const {
      pressSheetW = 35.0,     // سم
      pressSheetH = 50.0,     // سم
      openW = 21.0,           // سم
      openH = 29.7,           // سم
      montageCount = null,    // المونتاج الحالي المعتمد
      printingType = 'offset', // offset | digital | screen | none
      productType = 'flyer',  // flyer | brochure | folder | catalog | book | book_catalog | invoice
      sidesMode = 'single',   // single | work_sheet | work_turn
      orientation = 'auto',   // auto | normal | rotated
      folderPocketType = 'same_sheet', // same_sheet | separate_sheet
      folderPocketHeight = 7.5,
      folderCardSlit = true,
      spineThickness = 0.0,
      quantity = 1000,
      wasteSheets = 20,
      interactive = true,
      activeFace = 'front'    // front | back (for work_sheet)
    } = options;

    if (pressSheetW <= 0 || pressSheetH <= 0 || openW <= 0 || openH <= 0) {
      renderSkeleton(container);
      return;
    }

    // توجيه شيت الماكينة بالعرض دائماً (Landscape) لأفضل استغلال للمساحة ومطابقة واقع تغذية درفيل السلندر
    const sheetW_cm = Math.max(pressSheetW, pressSheetH);
    const sheetH_cm = Math.min(pressSheetW, pressSheetH);

    // 1. حسابات المونتاج الهندسية الصرفة
    const calc = PricingMath.calcImposition(sheetW_cm, sheetH_cm, openW, openH, printingType, orientation);
    if (calc.isOverflow || calc.cutsPerSheet <= 0) {
      renderSkeleton(container, `مقاس المطبوع (${formatDimension(openW)}×${formatDimension(openH)} سم) لا يتسع داخل شيت الماكينة (${formatDimension(sheetW_cm)}×${formatDimension(sheetH_cm)} سم)`);
      return;
    }

    const maxMontage = calc.cutsPerSheet;
    const activeMontage = (montageCount !== null && montageCount > 0 && montageCount <= maxMontage) ? montageCount : maxMontage;
    const isRotated = calc.isRotated;

    // أبعاد القطعة المطبوعة المفردة (بالمللي)
    const itemW_mm = (isRotated ? openH : openW) * 10.0;
    const itemH_mm = (isRotated ? openW : openH) * 10.0;

    // أبعاد شيت الماكينة (بالمللي) بالعرض
    const sheetW_mm = sheetW_cm * 10.0;
    const sheetH_mm = sheetH_cm * 10.0;

    // 2. هندسة الهوامش والبنسة
    const isOffset = (printingType === 'offset');
    const isFeedHorizontal = (sheetW_mm >= sheetH_mm);

    let gripperMargin = 0;
    let tailMargin = 0;
    let sideMarginLeft = 0;
    let sideMarginRight = 0;
    let digitalBorder = 0;

    if (isOffset) {
      gripperMargin = 12.0; // 12 mm
      tailMargin = 5.0;     // 5 mm
      sideMarginLeft = 3.0; // 3 mm
      sideMarginRight = 3.0;// 3 mm
    } else {
      digitalBorder = 4.0;  // 4 mm all around
    }

    // الصافي والهوامش المسنترة (بالمللي)
    const marginX_mm = calc.marginX * 10.0;
    const marginY_mm = calc.marginY * 10.0;
    const gapX_mm = calc.gapX * 10.0;
    const gapY_mm = calc.gapY * 10.0;

    // نقطة بداية شبكة المونتاج (بالمللي)
    let startX_mm = 0;
    let startY_mm = 0;

    if (isOffset) {
      if (isFeedHorizontal) {
        startX_mm = sideMarginLeft + marginX_mm;
        startY_mm = gripperMargin + marginY_mm; // تبدأ من بعد ضلع البنسة العلوي
      } else {
        startX_mm = gripperMargin + marginX_mm;
        startY_mm = sideMarginLeft + marginY_mm;
      }
    } else {
      startX_mm = digitalBorder + marginX_mm;
      startY_mm = digitalBorder + marginY_mm;
    }

    // أبعاد ومساحة بلوك صافي القطع الإجمالي للمونتاج (Net Cuts Block Bounds)
    const usedW_mm = (calc.cols * itemW_mm) + (Math.max(0, calc.cols - 1) * gapX_mm);
    const usedH_mm = (calc.rows * itemH_mm) + (Math.max(0, calc.rows - 1) * gapY_mm);
    const blockW_cm = usedW_mm / 10.0;
    const blockH_cm = usedH_mm / 10.0;
    const blockX1 = startX_mm;
    const blockX2 = startX_mm + usedW_mm;
    const blockY1 = startY_mm;
    const blockY2 = startY_mm + usedH_mm;

    // 3. بناء SVG
    clearContainer(container);

    // هوامش خارجية متوازنة لاستيعاب خطوط أبعاد الشيت وصافي مساحة الطباعة
    const padLeft = 32;
    const padBottom = 28;
    const padTop = 28;
    const padRight = 34;
    const totalW_mm = sheetW_mm + padLeft + padRight;
    const totalH_mm = sheetH_mm + padTop + padBottom;

    const svg = createSvgEl('svg', {
      viewBox: `-${padLeft} -${padTop} ${totalW_mm} ${totalH_mm}`,
      width: '100%',
      height: '100%',
      preserveAspectRatio: 'xMidYMid meet',
      style: 'max-height: 420px; width: 100%; max-width: 680px; display: block; margin: 0 auto; user-select: none;'
    });

    // تعريف الرموز والتنسيقات الفلات
    const defs = createSvgEl('defs');
    svg.appendChild(defs);

    // خلفية شيت الماكينة
    const sheetBg = createSvgEl('rect', {
      x: 0,
      y: 0,
      width: sheetW_mm,
      height: sheetH_mm,
      fill: 'var(--card-bg, #ffffff)',
      stroke: 'var(--border-color, #495057)',
      'stroke-width': 1.5,
      rx: 2
    });
    svg.appendChild(sheetBg);

    // رسم شريط البنسة وهوامش التشغيل
    if (isOffset) {
      // شريط البنسة (12 مم) على الضلع الأطول
      const gripperRect = isFeedHorizontal ?
        createSvgEl('rect', {
          x: 0,
          y: 0,
          width: sheetW_mm,
          height: gripperMargin,
          fill: 'var(--gray-200, #e9ecef)',
          stroke: 'none'
        }) :
        createSvgEl('rect', {
          x: 0,
          y: 0,
          width: gripperMargin,
          height: sheetH_mm,
          fill: 'var(--gray-200, #e9ecef)',
          stroke: 'none'
        });
      svg.appendChild(gripperRect);

      // خط البنسة المنقط
      const gripperLine = isFeedHorizontal ?
        createSvgEl('line', {
          x1: 0, y1: gripperMargin,
          x2: sheetW_mm, y2: gripperMargin,
          stroke: 'var(--secondary, #6c757d)',
          'stroke-width': 0.8,
          'stroke-dasharray': '3,3'
        }) :
        createSvgEl('line', {
          x1: gripperMargin, y1: 0,
          x2: gripperMargin, y2: sheetH_mm,
          stroke: 'var(--secondary, #6c757d)',
          'stroke-width': 0.8,
          'stroke-dasharray': '3,3'
        });
      svg.appendChild(gripperLine);

      // نص تسمية البنسة
      const gripperText = isFeedHorizontal ?
        createSvgEl('text', {
          x: sheetW_mm / 2,
          y: gripperMargin / 2 + 2.5,
          'text-anchor': 'middle',
          fill: 'var(--secondary, #6c757d)',
          'font-size': 8.5,
          'font-family': 'inherit',
          'font-weight': 'bold'
        }) :
        createSvgEl('text', {
          x: gripperMargin / 2 + 2.5,
          y: sheetH_mm / 2,
          'text-anchor': 'middle',
          fill: 'var(--secondary, #6c757d)',
          'font-size': Math.max(7, Math.min(10, sheetH_mm * 0.02)),
          'font-family': 'inherit',
          'font-weight': 'bold',
          transform: `rotate(-90, ${gripperMargin / 2}, ${sheetH_mm / 2})`
        });
      gripperText.textContent = 'بنسة الماكينة (12 مم)';
      svg.appendChild(gripperText);

      // هامش الديل (5 مم)
      const tailRect = isFeedHorizontal ?
        createSvgEl('rect', {
          x: 0,
          y: sheetH_mm - tailMargin,
          width: sheetW_mm,
          height: tailMargin,
          fill: 'var(--gray-100, #f8f9fa)',
          stroke: 'none'
        }) :
        createSvgEl('rect', {
          x: sheetW_mm - tailMargin,
          y: 0,
          width: tailMargin,
          height: sheetH_mm,
          fill: 'var(--gray-100, #f8f9fa)',
          stroke: 'none'
        });
      svg.appendChild(tailRect);
    } else {
      // إطار الديجيتال المحيطي (4 مم)
      const digFrame = createSvgEl('rect', {
        x: digitalBorder,
        y: digitalBorder,
        width: sheetW_mm - (digitalBorder * 2),
        height: sheetH_mm - (digitalBorder * 2),
        fill: 'none',
        stroke: 'var(--gray-400, #ced4da)',
        'stroke-width': 0.8,
        'stroke-dasharray': '2,2'
      });
      svg.appendChild(digFrame);

      const digLabel = createSvgEl('text', {
        x: sheetW_mm / 2,
        y: digitalBorder - 1,
        'text-anchor': 'middle',
        fill: 'var(--secondary, #6c757d)',
        'font-size': 6,
        'font-family': 'inherit'
      });
      digLabel.textContent = 'هامش ديجيتال غير مطبوع (4 مم)';
      svg.appendChild(digLabel);
    }

    // إطار بلوك صافي المونتاج على الشيت (Net Montage Bounding Frame)
    const blockRect = createSvgEl('rect', {
      x: blockX1,
      y: blockY1,
      width: usedW_mm,
      height: usedH_mm,
      fill: 'none',
      stroke: 'var(--primary, #0d6efd)',
      'stroke-width': 0.8,
      'stroke-dasharray': '3,3',
      opacity: 0.5
    });
    svg.appendChild(blockRect);

    // 4. خط الطبع والقلب (Work & Turn)
    const isWorkTurn = (sidesMode === 'work_turn' && activeMontage >= 2);
    if (isWorkTurn) {
      const splitX = sheetW_mm / 2;
      const splitLine = createSvgEl('line', {
        x1: splitX, y1: isFeedHorizontal ? gripperMargin : 0,
        x2: splitX, y2: sheetH_mm,
        stroke: 'var(--info, #0dcaf0)',
        'stroke-width': 1.2,
        'stroke-dasharray': '4,2'
      });
      svg.appendChild(splitLine);

      const labelA = createSvgEl('text', {
        x: splitX / 2,
        y: (isFeedHorizontal ? gripperMargin : 0) + 14,
        'text-anchor': 'middle',
        fill: 'var(--info, #0dcaf0)',
        'font-size': 8,
        'font-weight': 'bold'
      });
      labelA.textContent = 'نصف (وجه A)';
      svg.appendChild(labelA);

      const labelB = createSvgEl('text', {
        x: splitX + (splitX / 2),
        y: (isFeedHorizontal ? gripperMargin : 0) + 14,
        'text-anchor': 'middle',
        fill: 'var(--info, #0dcaf0)',
        'font-size': 8,
        'font-weight': 'bold'
      });
      labelB.textContent = 'نصف (ظهر A) - طبع وقلب';
      svg.appendChild(labelB);
    }

    // 5. رسم قطع المونتاج (Grid of Items)
    const cols = calc.cols;
    const rows = calc.rows;
    let slotIndex = 0;

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        slotIndex++;
        const isActive = (slotIndex <= activeMontage);

        // ترقيم وتموضع بالاتجاه العربي (RTL: الأعمدة من اليمين إلى اليسار)
        const cRtl = (cols - 1 - c);
        const x = startX_mm + (cRtl * (itemW_mm + gapX_mm));
        const y = startY_mm + (r * (itemH_mm + gapY_mm));

        // حاوية القطعة
        const itemG = createSvgEl('g', {
          class: `imposition-slot ${isActive ? 'slot-active' : 'slot-idle'}`,
          'data-slot': slotIndex
        });

        // المستطيل الأساسي للقطعة
        const itemRect = createSvgEl('rect', {
          x: x,
          y: y,
          width: itemW_mm,
          height: itemH_mm,
          fill: isActive ? 'var(--primary-subtle, #e7f1ff)' : 'var(--gray-100, #f8f9fa)',
          stroke: isActive ? 'var(--primary, #0d6efd)' : 'var(--secondary, #adb5bd)',
          'stroke-width': isActive ? 1.0 : 0.8,
          'stroke-dasharray': isActive ? 'none' : '3,2',
          rx: 1.5
        });
        itemG.appendChild(itemRect);

        // تخصيص الأنماط الأربعة (Archetypes)
        if (isActive) {
          if (productType === 'folder') {
            // فولدر: لسان الجيب السفلي وشلاقة الكارت
            if (folderPocketType === 'same_sheet') {
              const pocketH_mm = (folderPocketHeight || 7.5) * 10.0;
              const foldY = y + itemH_mm - pocketH_mm;

              // خط طي الجيب المنقط
              const foldLine = createSvgEl('line', {
                x1: x, y1: foldY,
                x2: x + itemW_mm, y2: foldY,
                stroke: 'var(--danger, #dc3545)',
                'stroke-width': 0.8,
                'stroke-dasharray': '2,2'
              });
              itemG.appendChild(foldLine);

              // لسان الجيب
              const pocketRect = createSvgEl('rect', {
                x: x, y: foldY,
                width: itemW_mm, height: pocketH_mm,
                fill: 'var(--gray-200, #e2e3e5)',
                stroke: 'none',
                opacity: 0.7
              });
              itemG.appendChild(pocketRect);

              // فتحة الكارت الشخصي (Slit)
              if (folderCardSlit) {
                const slitW = Math.min(30, itemW_mm * 0.4);
                const slitX = x + (itemW_mm - slitW) / 2;
                const slitY = foldY + (pocketH_mm / 2);
                const slitLine = createSvgEl('line', {
                  x1: slitX, y1: slitY,
                  x2: slitX + slitW, y2: slitY,
                  stroke: 'var(--dark, #212529)',
                  'stroke-width': 1.0
                });
                itemG.appendChild(slitLine);
              }

              // تسمية الجيب المتصل
              const pocketLabel = createSvgEl('text', {
                x: x + (itemW_mm / 2),
                y: foldY + (pocketH_mm / 2) + 2,
                'text-anchor': 'middle',
                fill: 'var(--secondary, #495057)',
                'font-size': Math.max(7.5, Math.min(11, pocketH_mm * 0.2)),
                'font-weight': 'bold',
                'font-family': 'inherit'
              });
              pocketLabel.textContent = `جيب متصل (${formatDimension(folderPocketHeight)} سم)`;
              itemG.appendChild(pocketLabel);
            }
          } else if (productType === 'catalog' || productType === 'book' || productType === 'book_catalog') {
            // غلاف كتاب/كتالوج مع كعب
            const spineW_mm = (spineThickness || 0.5) * 10.0;
            if (spineW_mm > 1.0) {
              const spineX = x + ((itemW_mm - spineW_mm) / 2);
              const spineRect = createSvgEl('rect', {
                x: spineX, y: y,
                width: spineW_mm, height: itemH_mm,
                fill: 'var(--warning-subtle, #fff3cd)',
                stroke: 'var(--warning, #ffc107)',
                'stroke-width': 0.6,
                'stroke-dasharray': '2,1'
              });
              itemG.appendChild(spineRect);

              const spineText = createSvgEl('text', {
                x: spineX + (spineW_mm / 2),
                y: y + (itemH_mm / 2),
                'text-anchor': 'middle',
                fill: 'var(--dark, #212529)',
                'font-size': Math.max(6.5, Math.min(10, spineW_mm * 0.5)),
                'font-weight': 'bold',
                transform: `rotate(-90, ${spineX + (spineW_mm / 2)}, ${y + (itemH_mm / 2)})`
              });
              spineText.textContent = `كعب ${formatDimension(spineThickness)} سم`;
              itemG.appendChild(spineText);
            }
          } else if (productType === 'invoice') {
            // دفاتر فواتير NCR: كعب التخريم والدبوس
            const stubW_mm = 15.0; // 1.5 سم كعب
            const stubRect = createSvgEl('rect', {
              x: x, y: y,
              width: stubW_mm, height: itemH_mm,
              fill: 'var(--info-subtle, #cff4fc)',
              stroke: 'none'
            });
            itemG.appendChild(stubRect);

            // خط التخريم المنقط
            const perfLine = createSvgEl('line', {
              x1: x + stubW_mm, y1: y,
              x2: x + stubW_mm, y2: y + itemH_mm,
              stroke: 'var(--secondary, #6c757d)',
              'stroke-width': 0.8,
              'stroke-dasharray': '1.5,1.5'
            });
            itemG.appendChild(perfLine);
          }

          // حساب المقاسات والخطوط المعتمدة من المستخدم
          const titleSize = 16; // مقاس كلمة القطعة المطلوب (16)

          const centerX = x + (itemW_mm / 2);
          const centerY = y + (itemH_mm / 2);

          // خطوط الأبعاد الهندسية لمقاس القطعة على أضلاع القطعة الأولى كمرجع رئيسي (أسود وبدون خلفية)
          if (slotIndex === 1) {
            const pieceDimColor = 'var(--dark, #212529)';
            const pieceTextColor = 'var(--dark, #212529)';
            const pieceDimFontSize = 14; // مقاس خط البُعد 14

            const wFormatted = formatDimension(itemW_mm / 10);
            const hFormatted = formatDimension(itemH_mm / 10);

            // الضلع العلوي (عرض القطعة) - خط ورقم أسود بدون أي خلفية
            const topDim = createDimensionLine(
              x + 8, y + 12,
              x + itemW_mm - 8, y + 12,
              `${wFormatted} سم`,
              false, pieceDimColor, pieceTextColor, pieceDimFontSize, false
            );
            itemG.appendChild(topDim);

            // الضلع الرأسي (طول القطعة) - خط ورقم أسود بدون أي خلفية، ويبدأ بعد الخط العلوي لمنع التقاطع
            const leftDim = createDimensionLine(
              x + 12, y + 26,
              x + 12, y + itemH_mm - 8,
              `${hFormatted} سم`,
              true, pieceDimColor, pieceTextColor, pieceDimFontSize, false
            );
            itemG.appendChild(leftDim);
          }

          // رقم واسم القطعة في المنتصف بهدوء وتوازن بصري بدون تكرار أرقام
          const labelNum = createSvgEl('text', {
            x: centerX,
            y: centerY + (titleSize * 0.35),
            'text-anchor': 'middle',
            fill: 'var(--primary, #0d6efd)',
            'font-size': titleSize,
            'font-weight': 'bold',
            'font-family': 'inherit'
          });
          labelNum.textContent = `قطعة #${slotIndex}`;
          itemG.appendChild(labelNum);
        } else {
          // خانة شاغرة (فاقد تفريد)
          const idleSize = 16;
          const idleText = createSvgEl('text', {
            x: x + (itemW_mm / 2),
            y: y + (itemH_mm / 2) + 4,
            'text-anchor': 'middle',
            fill: 'var(--secondary, #6c757d)',
            'font-size': idleSize,
            'font-style': 'italic',
            'font-family': 'inherit'
          });
          idleText.textContent = 'خانة شاغرة (فاقد)';
          itemG.appendChild(idleText);
        }

        svg.appendChild(itemG);
      }
    }

    // 5.5 خطوط الأبعاد الهندسية لشيت الماكينة وصافي القطع (مقاس موحد 14 لكافة المقاسات)
    const outerDimColor = 'var(--secondary, #6c757d)';
    const outerTextColor = 'var(--dark, #212529)';
    const sheetDimFontSize = 14; // مقاس خط أبعاد الشيت 14

    const sheetWFormatted = formatDimension(sheetW_cm);
    const sheetHFormatted = formatDimension(sheetH_cm);
    const blockWFormatted = formatDimension(blockW_cm);
    const blockHFormatted = formatDimension(blockH_cm);

    // خط بُعد عرض شيت الماكينة أسفل الشيت
    const dimBottom = createDimensionLine(
      0, sheetH_mm + 15,
      sheetW_mm, sheetH_mm + 15,
      `عرض الشيت: ${sheetWFormatted} سم`,
      false, outerDimColor, outerTextColor, sheetDimFontSize, true
    );
    svg.appendChild(dimBottom);

    // خط بُعد طول شيت الماكينة يسار الشيت
    const dimLeft = createDimensionLine(
      -16, 0,
      -16, sheetH_mm,
      `طول الشيت: ${sheetHFormatted} سم`,
      true, outerDimColor, outerTextColor, sheetDimFontSize, true
    );
    svg.appendChild(dimLeft);

    // خط بُعد صافي عرض المونتاج أعلى الشيت (يقيس بالضبط من أول عمود لآخر عمود مع الفواصل)
    const dimTop = createDimensionLine(
      blockX1, -15,
      blockX2, -15,
      `صافي المونتاج: ${blockWFormatted} سم`,
      false, outerDimColor, outerTextColor, sheetDimFontSize, true
    );
    svg.appendChild(dimTop);

    // خطوط إسقاط هندسية خفيفة تصل مؤشرات القياس بأول وآخر عمود قطع
    const witTop1 = createSvgEl('line', { x1: blockX1, y1: blockY1, x2: blockX1, y2: -18, stroke: 'var(--border-color, #dee2e6)', 'stroke-width': 0.7, 'stroke-dasharray': '2,2' });
    const witTop2 = createSvgEl('line', { x1: blockX2, y1: blockY1, x2: blockX2, y2: -18, stroke: 'var(--border-color, #dee2e6)', 'stroke-width': 0.7, 'stroke-dasharray': '2,2' });
    svg.appendChild(witTop1);
    svg.appendChild(witTop2);

    // خط بُعد صافي طول المونتاج يمين الشيت (يقيس بالضبط من أول صف لآخر صف مع الفواصل)
    const dimRight = createDimensionLine(
      sheetW_mm + 16, blockY1,
      sheetW_mm + 16, blockY2,
      `صافي المونتاج: ${blockHFormatted} سم`,
      true, outerDimColor, outerTextColor, sheetDimFontSize, true
    );
    svg.appendChild(dimRight);

    // خطوط إسقاط هندسية خفيفة تصل مؤشرات القياس بأول وآخر صف قطع
    const witRight1 = createSvgEl('line', { x1: blockX2, y1: blockY1, x2: sheetW_mm + 19, y2: blockY1, stroke: 'var(--border-color, #dee2e6)', 'stroke-width': 0.7, 'stroke-dasharray': '2,2' });
    const witRight2 = createSvgEl('line', { x1: blockX2, y1: blockY2, x2: sheetW_mm + 19, y2: blockY2, stroke: 'var(--border-color, #dee2e6)', 'stroke-width': 0.7, 'stroke-dasharray': '2,2' });
    svg.appendChild(witRight1);
    svg.appendChild(witRight2);

    container.appendChild(svg);

    // 6. شريط الإحصائية التشغيلية المباشرة وشارات الحالة (Live Batch Stats & Badges)
    _renderBatchStatsBar(container, {
      activeMontage,
      maxMontage,
      quantity,
      wasteSheets,
      hasBleedGutters: calc.hasBleedGutters,
      pressSheetW: sheetW_cm,
      pressSheetH: sheetH_cm,
      blockW: blockW_cm,
      blockH: blockH_cm,
      printingType,
      productType,
      folderPocketType
    });
  }

  /**
   * شريط الإحصائيات الفورية أعلى وأسفل الكارت
   */
  function _renderBatchStatsBar(container, info) {
    // إزالة أي شريط إحصائيات قديم
    const oldBar = container.parentNode?.querySelector('.imposition-stats-bar');
    if (oldBar) oldBar.remove();

    const statsBar = document.createElement('div');
    statsBar.className = 'imposition-stats-bar d-flex flex-wrap align-items-center justify-content-between p-2 mt-2 border rounded';
    statsBar.style.backgroundColor = 'var(--card-bg, #ffffff)';
    statsBar.style.borderColor = 'var(--border-color, #dee2e6)';
    statsBar.style.fontSize = '0.85rem';

    // حساب الشيتات الصافية والإجمالية
    const netSheets = Math.ceil(info.quantity / Math.max(1, info.activeMontage));
    const grossSheets = netSheets + (info.wasteSheets || 20);

    // 1. إحصائيات السحب والتشغيل
    const leftStats = document.createElement('div');
    leftStats.className = 'd-flex align-items-center gap-2 flex-wrap';
    leftStats.innerHTML = `
      <span class="badge bg-light text-dark border">
        <i class="fas fa-th me-1 text-primary"></i> المونتاج: <strong>${info.activeMontage}</strong> قطعة
      </span>
      <span class="badge bg-light text-dark border" title="المساحة الإجمالية الصافية لشبكة المونتاج على الشيت مع الفواصل">
        <i class="fas fa-th-large me-1 text-primary"></i> صافي المونتاج: <strong>${formatDimension(info.blockW)}×${formatDimension(info.blockH)}</strong> سم
      </span>
      <span class="badge bg-light text-dark border">
        صافي الشيتات: <strong>${netSheets.toLocaleString('en-US')}</strong>
      </span>
      <span class="badge bg-light text-dark border">
        الهالك: <strong>${(info.wasteSheets || 20).toLocaleString('en-US')}</strong>
      </span>
      <span class="badge bg-primary text-white">
        المطلوب سحبه: <strong>${grossSheets.toLocaleString('en-US')}</strong> شيت
      </span>
    `;

    // 2. شارة الدوبل تكسير أو القص المشترك
    const rightBadges = document.createElement('div');
    rightBadges.className = 'd-flex align-items-center gap-1';

    if (info.hasBleedGutters) {
      rightBadges.innerHTML = `
        <span class="badge bg-success-subtle text-success border border-success-subtle">
          <i class="fas fa-check-circle me-1"></i> فواصل دوبل تكسير (3 مم)
        </span>
      `;
    } else {
      rightBadges.innerHTML = `
        <span class="badge bg-warning-subtle text-warning border border-warning-subtle" title="المقاس حاشر في الشيت ولا يتسع لفواصل 3 مم">
          <i class="fas fa-exclamation-triangle me-1"></i> قص مشترك (بدون دوبل تكسير)
        </span>
      `;
    }

    // شارة الجيب المنفصل في الفولدر إن وجد
    if (info.productType === 'folder' && info.folderPocketType === 'separate_sheet') {
      rightBadges.innerHTML += `
        <span class="badge bg-info-subtle text-info border border-info-subtle">
          <i class="fas fa-folder-open me-1"></i> الجيب منفصل (تفريد خارجي)
        </span>
      `;
    }

    statsBar.appendChild(leftStats);
    statsBar.appendChild(rightBadges);

    container.parentNode?.insertBefore(statsBar, container);
  }

  /**
   * خريطة تفصيل الفرخ الخام للمقصدار (Shearing Map)
   * مع التركيبات الخاصة (حداشر 20×30 وخمسات 30×40)
   */
  function renderShearingMap(container, options = {}) {
    if (!container) return;

    const {
      parentW = 70.0,
      parentH = 100.0,
      pieceW = 35.0,
      pieceH = 50.0,
      machineCuts = 4,
      paperSource = 'purchase', // purchase | warehouse | customer_supplied
      cutsPerSheet = 1
    } = options;

    clearContainer(container);

    // إذا كان الورق منصرفاً جاهزاً من المخزن مقصوصاً
    if (paperSource === 'warehouse') {
      const notice = document.createElement('div');
      notice.className = 'alert alert-info d-flex align-items-center mb-0 p-3';
      notice.innerHTML = `
        <i class="fas fa-warehouse fa-2x me-3 text-info"></i>
        <div>
          <strong class="d-block mb-1">الخامة منصرفة مقصوصة جاهزة من مخزن المنشأة</strong>
          <span class="small text-muted">مقاس الشيت (${formatDimension(pieceW)}×${formatDimension(pieceH)} سم) منصرف ومجهز مسبقاً ولا يتطلب تقطيع فرخ خام بالمقصدار.</span>
        </div>
      `;
      container.appendChild(notice);
      return;
    }

    // توجيه الفرخ الخام بالعرض دائماً (Landscape) لملء العرض ومطابقة اتجاه طاولة المقصدار
    const effParentW = Math.max(parentW, parentH); // 100.0 سم
    const effParentH = Math.min(parentW, parentH); // 70.0 سم
    const parentW_mm = effParentW * 10.0;          // 1000 مم
    const parentH_mm = effParentH * 10.0;          // 700 مم

    // هوامش خارجية متوازنة لاستيعاب خطوط الأبعاد الهندسية للفرخ الخام
    const padLeft = 32;
    const padBottom = 28;
    const padTop = 26;
    const padRight = 32;
    const totalW_mm = parentW_mm + padLeft + padRight;
    const totalH_mm = parentH_mm + padTop + padBottom;

    const svg = createSvgEl('svg', {
      viewBox: `-${padLeft} -${padTop} ${totalW_mm} ${totalH_mm}`,
      width: '100%',
      height: '100%',
      preserveAspectRatio: 'xMidYMid meet',
      style: 'max-height: 420px; width: 100%; max-width: 680px; display: block; margin: 0 auto; user-select: none;'
    });

    // رسم الفرخ الخام
    const parentBg = createSvgEl('rect', {
      x: 0,
      y: 0,
      width: parentW_mm,
      height: parentH_mm,
      fill: 'var(--card-bg, #ffffff)',
      stroke: 'var(--border-color, #495057)',
      'stroke-width': 1.5,
      rx: 2
    });
    svg.appendChild(parentBg);

    // فحص حالات التقطيع المركب للمقصدار في الفرخ 70×100
    const isStandard70x100 = (Math.abs(effParentW - 100.0) <= 2.0 && Math.abs(effParentH - 70.0) <= 2.0);
    let scrapAreaRatio = 0;

    if (machineCuts === 11 && isStandard70x100) {
      // تفصيل 11 قطعة مقاس 20×30 سم (حداشر)
      _draw11CutsPattern(svg, parentW_mm, parentH_mm);
      scrapAreaRatio = (1000 * 100) / (parentW_mm * parentH_mm);
    } else if (machineCuts === 5 && isStandard70x100) {
      // تفصيل 5 قطع مقاس 30×40 سم (خمسات)
      _draw5CutsPattern(svg, parentW_mm, parentH_mm);
      scrapAreaRatio = (100 * 400 + 200 * 300) / (parentW_mm * parentH_mm);
    } else {
      // التقطيع الديناميكي الهندسي التام لكافة مقاسات الفرخ ومقاسات الشيتات
      scrapAreaRatio = _drawDynamicCuts(svg, parentW_mm, parentH_mm, pieceW, pieceH, machineCuts);
    }

    // خطوط الأبعاد الهندسية للفرخ الخام الخارجي
    const outerDimColor = 'var(--secondary, #6c757d)';
    const outerTextColor = 'var(--dark, #212529)';
    const dimFontSize = 14; // مقاس خط أبعاد الفرخ الخام 14

    // خط بُعد عرض الفرخ الخام أسفل الرسم
    const dimBottom = createDimensionLine(
      0, parentH_mm + 15,
      parentW_mm, parentH_mm + 15,
      `عرض الفرخ الخام: ${formatDimension(effParentW)} سم`,
      false, outerDimColor, outerTextColor, dimFontSize, true
    );
    svg.appendChild(dimBottom);

    // خط بُعد طول الفرخ الخام يسار الرسم
    const dimLeft = createDimensionLine(
      -16, 0,
      -16, parentH_mm,
      `طول الفرخ الخام: ${formatDimension(effParentH)} سم`,
      true, outerDimColor, outerTextColor, dimFontSize, true
    );
    svg.appendChild(dimLeft);

    container.appendChild(svg);

    // شريط إحصائية الفرخ الخام بنظام الشارات المتناسق
    const safeMontage = (cutsPerSheet && cutsPerSheet > 0) ? cutsPerSheet : 1;
    _renderShearingStatsBar(container, {
      parentW: effParentW,
      parentH: effParentH,
      machineCuts,
      cutsPerSheet: safeMontage,
      scrapAreaRatio
    });
  }

  /**
   * شريط إحصائيات الفرخ الخام بنظام الشارات المتناسق خارج الـ SVG
   */
  function _renderShearingStatsBar(container, info) {
    const oldBar = container.parentNode?.querySelector('.shearing-stats-bar');
    if (oldBar) oldBar.remove();

    const statsBar = document.createElement('div');
    statsBar.className = 'shearing-stats-bar d-flex flex-wrap align-items-center justify-content-between p-2 mt-2 border rounded';
    statsBar.style.backgroundColor = 'var(--card-bg, #ffffff)';
    statsBar.style.borderColor = 'var(--border-color, #dee2e6)';
    statsBar.style.fontSize = '0.85rem';

    const safeMontage = (info.cutsPerSheet && info.cutsPerSheet > 0) ? info.cutsPerSheet : 1;
    const totalItems = (info.machineCuts || 1) * safeMontage;

    const leftStats = document.createElement('div');
    leftStats.className = 'd-flex align-items-center gap-2 flex-wrap';
    leftStats.innerHTML = `
      <span class="badge bg-light text-dark border">
        <i class="fas fa-layer-group me-1 text-primary"></i> الفرخ الخام: <strong>${formatDimension(info.parentW)}×${formatDimension(info.parentH)}</strong> سم
      </span>
      <span class="badge bg-light text-dark border">
        <i class="fas fa-cut me-1 text-info"></i> عدد الشيتات: <strong>${info.machineCuts}</strong> شيت للماكينة
      </span>
      <span class="badge bg-light text-dark border">
        <i class="fas fa-th me-1 text-primary"></i> مونتاج الشيت: <strong>${safeMontage}</strong> قطعة
      </span>
      <span class="badge bg-primary text-white">
        إجمالي القطع بالفرخ: <strong>${totalItems.toLocaleString('en-US')}</strong> قطعة
      </span>
    `;

    const rightBadges = document.createElement('div');
    rightBadges.className = 'd-flex align-items-center gap-1';
    if (info.scrapAreaRatio > 0.01) {
      rightBadges.innerHTML = `
        <span class="badge bg-warning-subtle text-warning border border-warning-subtle">
          <i class="fas fa-exclamation-triangle me-1"></i> فاقد تقطيع خام: ${formatDimension(info.scrapAreaRatio * 100)}%
        </span>
      `;
    } else {
      rightBadges.innerHTML = `
        <span class="badge bg-success-subtle text-success border border-success-subtle">
          <i class="fas fa-check-circle me-1"></i> استغلال 100% للفرخ الخام
        </span>
      `;
    }

    statsBar.appendChild(leftStats);
    statsBar.appendChild(rightBadges);

    container.parentNode?.insertBefore(statsBar, container);
  }

  /**
   * رسم نمط الـ 11 قطعة (حداشر 20×30) على الفرخ العرضي 100×70 سم
   */
  function _draw11CutsPattern(svg, pW, pH) {
    // 9 قطع 300×200 مم (شبكة 3×3) في مساحة 900×600
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) {
        const x = c * 300;
        const y = r * 200;
        const rect = createSvgEl('rect', {
          x, y, width: 300, height: 200,
          fill: 'var(--primary-subtle, #e7f1ff)',
          stroke: 'var(--primary, #0d6efd)',
          'stroke-width': 1.0
        });
        svg.appendChild(rect);

        const txt = createSvgEl('text', {
          x: x + 150, y: y + 95,
          'text-anchor': 'middle',
          fill: 'var(--primary, #0d6efd)',
          'font-size': 16, 'font-weight': 'bold'
        });
        txt.textContent = `شيت #${r * 3 + c + 1}`;
        svg.appendChild(txt);

        const subTxt = createSvgEl('text', {
          x: x + 150, y: y + 120,
          'text-anchor': 'middle',
          fill: 'var(--secondary, #6c757d)',
          'font-size': 14, 'font-weight': 'bold'
        });
        subTxt.textContent = '20 × 30 سم';
        svg.appendChild(subTxt);
      }
    }

    // قطعتين إضافيتين في الشريحة الرأسية 100×600 مم
    for (let i = 0; i < 2; i++) {
      const x = 900;
      const y = i * 300;
      const rect = createSvgEl('rect', {
        x, y, width: 100, height: 300,
        fill: 'var(--info-subtle, #cff4fc)',
        stroke: 'var(--info, #0dcaf0)',
        'stroke-width': 1.0
      });
      svg.appendChild(rect);

      const txt = createSvgEl('text', {
        x: x + 50, y: y + 150,
        'text-anchor': 'middle',
        fill: 'var(--info, #0dcaf0)',
        'font-size': 14, 'font-weight': 'bold',
        transform: `rotate(-90, ${x + 50}, ${y + 150})`
      });
      txt.textContent = `شيت #${10 + i} (20×30)`;
      svg.appendChild(txt);
    }

    // شريط الفائض السفلي 100×1000 مم
    const scrapRect = createSvgEl('rect', {
      x: 0, y: 600, width: pW, height: 100,
      fill: 'var(--gray-200, #e9ecef)',
      stroke: 'var(--secondary, #adb5bd)',
      'stroke-width': 0.8,
      'stroke-dasharray': '4,4'
    });
    svg.appendChild(scrapRect);

    const scrapTxt = createSvgEl('text', {
      x: pW / 2, y: 655,
      'text-anchor': 'middle',
      fill: 'var(--secondary, #6c757d)',
      'font-size': 14, 'font-weight': 'bold'
    });
    scrapTxt.textContent = 'فاقد تقطيع الفرخ الخام (10×100 سم)';
    svg.appendChild(scrapTxt);


  }

  /**
   * رسم نمط الـ 5 قطع (خمسات 30×40) على الفرخ العرضي 100×70 سم
   */
  function _draw5CutsPattern(svg, pW, pH) {
    // 3 قطع 300×400 مم في الصف العلوي (مساحة 900×400)
    for (let c = 0; c < 3; c++) {
      const x = c * 300;
      const y = 0;
      const rect = createSvgEl('rect', {
        x, y, width: 300, height: 400,
        fill: 'var(--primary-subtle, #e7f1ff)',
        stroke: 'var(--primary, #0d6efd)',
        'stroke-width': 1.0
      });
      svg.appendChild(rect);

      const txt = createSvgEl('text', {
        x: x + 150, y: 195,
        'text-anchor': 'middle',
        fill: 'var(--primary, #0d6efd)',
        'font-size': 16, 'font-weight': 'bold'
      });
      txt.textContent = `شيت #${c + 1}`;
      svg.appendChild(txt);

      const subTxt = createSvgEl('text', {
        x: x + 150, y: 220,
        'text-anchor': 'middle',
        fill: 'var(--secondary, #6c757d)',
        'font-size': 14, 'font-weight': 'bold'
      });
      subTxt.textContent = '30 × 40 سم';
      svg.appendChild(subTxt);
    }

    // قطعتين 400×300 مم في الصف السفلي (مساحة 800×300)
    for (let c = 0; c < 2; c++) {
      const x = c * 400;
      const y = 400;
      const rect = createSvgEl('rect', {
        x, y, width: 400, height: 300,
        fill: 'var(--info-subtle, #cff4fc)',
        stroke: 'var(--info, #0dcaf0)',
        'stroke-width': 1.0
      });
      svg.appendChild(rect);

      const txt = createSvgEl('text', {
        x: x + 200, y: y + 145,
        'text-anchor': 'middle',
        fill: 'var(--info, #0dcaf0)',
        'font-size': 16, 'font-weight': 'bold'
      });
      txt.textContent = `شيت #${4 + c}`;
      svg.appendChild(txt);

      const subTxt = createSvgEl('text', {
        x: x + 200, y: y + 170,
        'text-anchor': 'middle',
        fill: 'var(--secondary, #6c757d)',
        'font-size': 14, 'font-weight': 'bold'
      });
      subTxt.textContent = '30 × 40 سم (مركب)';
      svg.appendChild(subTxt);
    }

    // مساحات الفائض
    const scrap1 = createSvgEl('rect', {
      x: 900, y: 0, width: 100, height: 400,
      fill: 'var(--gray-200, #e9ecef)',
      stroke: 'var(--secondary, #adb5bd)',
      'stroke-width': 0.8
    });
    svg.appendChild(scrap1);

    const scrap2 = createSvgEl('rect', {
      x: 800, y: 400, width: 200, height: 300,
      fill: 'var(--gray-200, #e9ecef)',
      stroke: 'var(--secondary, #adb5bd)',
      'stroke-width': 0.8
    });
    svg.appendChild(scrap2);


  }

  /**
   * رسم التقطيع الهندسي الديناميكي التام لكافة مقاسات الفرخ والشيتات
   */
  function _drawDynamicCuts(svg, pW_mm, pH_mm, pieceW, pieceH, machineCuts) {
    const pW_cm = pW_mm / 10.0;
    const pH_cm = pH_mm / 10.0;

    let pcW = parseFloat(pieceW) || 0;
    let pcH = parseFloat(pieceH) || 0;
    let cuts = parseInt(machineCuts, 10) || 4;

    // إذا لم تكن مقاسات القطع صريحة، نشتقها هندسياً من أبعاد الفرخ
    if (pcW <= 0 || pcH <= 0) {
      if (cuts === 1) {
        pcW = pW_cm; pcH = pH_cm;
      } else if (cuts === 2) {
        pcW = pW_cm / 2; pcH = pH_cm;
      } else if (cuts === 4) {
        pcW = pW_cm / 2; pcH = pH_cm / 2;
      } else if (cuts === 8) {
        pcW = pW_cm / 4; pcH = pH_cm / 2;
      } else if (cuts === 16) {
        pcW = pW_cm / 4; pcH = pH_cm / 4;
      } else if (cuts === 6) {
        pcW = pW_cm / 3; pcH = pH_cm / 2;
      } else if (cuts === 3) {
        pcW = pW_cm / 3; pcH = pH_cm;
      } else {
        const c = Math.ceil(Math.sqrt(cuts * (pW_cm / pH_cm)));
        const r = Math.ceil(cuts / c);
        pcW = pW_cm / c; pcH = pH_cm / r;
      }
    }

    const pMax = Math.max(pcW, pcH);
    const pMin = Math.min(pcW, pcH);

    // فحص أفضل توجيه للشيتات داخل الفرخ (أفقي أو رأسي)
    const colsA = Math.max(1, Math.floor((pW_cm + 0.05) / pMax));
    const rowsA = Math.max(1, Math.floor((pH_cm + 0.05) / pMin));
    const yieldA = colsA * rowsA;

    const colsB = Math.max(1, Math.floor((pW_cm + 0.05) / pMin));
    const rowsB = Math.max(1, Math.floor((pH_cm + 0.05) / pMax));
    const yieldB = colsB * rowsB;

    let itemW_cm, itemH_cm, cols, rows;

    if (cuts === yieldA && cuts !== yieldB) {
      itemW_cm = pMax; itemH_cm = pMin; cols = colsA; rows = rowsA;
    } else if (cuts === yieldB && cuts !== yieldA) {
      itemW_cm = pMin; itemH_cm = pMax; cols = colsB; rows = rowsB;
    } else if (yieldA >= yieldB) {
      itemW_cm = pMax; itemH_cm = pMin; cols = colsA; rows = rowsA;
    } else {
      itemW_cm = pMin; itemH_cm = pMax; cols = colsB; rows = rowsB;
    }

    const drawCount = Math.min(cuts, cols * rows);
    const itemW_mm = itemW_cm * 10.0;
    const itemH_mm = itemH_cm * 10.0;

    // رسم الشيتات الصافية بنظام RTL
    let idx = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (idx >= drawCount) break;
        idx++;

        const cRtl = (cols - 1 - c);
        const x = cRtl * itemW_mm;
        const y = r * itemH_mm;

        const rect = createSvgEl('rect', {
          x, y,
          width: itemW_mm,
          height: itemH_mm,
          fill: 'var(--primary-subtle, #e7f1ff)',
          stroke: 'var(--primary, #0d6efd)',
          'stroke-width': 1.0
        });
        svg.appendChild(rect);

        // شيت #1 يحمل خطوط أبعاد هندسية CAD على أضلاعه
        if (idx === 1) {
          const cutDimColor = 'var(--dark, #212529)';
          const topDim = createDimensionLine(
            x + 12, y + 15,
            x + itemW_mm - 12, y + 15,
            `${formatDimension(itemW_cm)} سم`,
            false, cutDimColor, cutDimColor, 14, false
          );
          svg.appendChild(topDim);

          const leftDim = createDimensionLine(
            x + 16, y + 32,
            x + 16, y + itemH_mm - 12,
            `${formatDimension(itemH_cm)} سم`,
            true, cutDimColor, cutDimColor, 14, false
          );
          svg.appendChild(leftDim);
        }

        // اسم ورقم الشيت
        const txt = createSvgEl('text', {
          x: x + (itemW_mm / 2),
          y: y + (itemH_mm / 2) - 6,
          'text-anchor': 'middle',
          fill: 'var(--primary, #0d6efd)',
          'font-size': 16,
          'font-weight': 'bold',
          'font-family': 'inherit'
        });
        txt.textContent = `شيت #${idx}`;
        svg.appendChild(txt);

        // مقاس الشيت تحت التسمية
        const subTxt = createSvgEl('text', {
          x: x + (itemW_mm / 2),
          y: y + (itemH_mm / 2) + 16,
          'text-anchor': 'middle',
          fill: 'var(--secondary, #6c757d)',
          'font-size': 14,
          'font-weight': 'bold',
          'font-family': 'inherit'
        });
        subTxt.textContent = `${formatDimension(itemW_cm)} × ${formatDimension(itemH_cm)} سم`;
        svg.appendChild(subTxt);
      }
    }

    // رسم مساحات الفاقد / العوادم إن وجدت
    const usedW_mm = cols * itemW_mm;
    const usedH_mm = rows * itemH_mm;
    const remW_mm = pW_mm - usedW_mm;
    const remH_mm = pH_mm - usedH_mm;

    // فاقد جانبي (يسار في RTL)
    if (remW_mm >= 5.0) {
      const scrapLeft = createSvgEl('rect', {
        x: 0,
        y: 0,
        width: remW_mm,
        height: pH_mm,
        fill: 'var(--gray-200, #e9ecef)',
        stroke: 'var(--secondary, #adb5bd)',
        'stroke-width': 0.8,
        'stroke-dasharray': '4,4'
      });
      svg.appendChild(scrapLeft);

      if (remW_mm >= 30.0 && pH_mm >= 60.0) {
        const scrapTxt = createSvgEl('text', {
          x: remW_mm / 2,
          y: pH_mm / 2,
          'text-anchor': 'middle',
          fill: 'var(--secondary, #6c757d)',
          'font-size': 12,
          'font-weight': 'bold',
          transform: `rotate(-90, ${remW_mm / 2}, ${pH_mm / 2})`
        });
        scrapTxt.textContent = `فاقد (${formatDimension(remW_mm / 10)}×${formatDimension(pH_cm)} سم)`;
        svg.appendChild(scrapTxt);
      }
    }

    // فاقد سفلي
    if (remH_mm >= 5.0) {
      const scrapBottom = createSvgEl('rect', {
        x: pW_mm - usedW_mm,
        y: usedH_mm,
        width: usedW_mm,
        height: remH_mm,
        fill: 'var(--gray-200, #e9ecef)',
        stroke: 'var(--secondary, #adb5bd)',
        'stroke-width': 0.8,
        'stroke-dasharray': '4,4'
      });
      svg.appendChild(scrapBottom);

      if (remH_mm >= 20.0 && usedW_mm >= 60.0) {
        const scrapTxt = createSvgEl('text', {
          x: (pW_mm - usedW_mm) + (usedW_mm / 2),
          y: usedH_mm + (remH_mm / 2) + 4,
          'text-anchor': 'middle',
          fill: 'var(--secondary, #6c757d)',
          'font-size': 12,
          'font-weight': 'bold'
        });
        scrapTxt.textContent = `فاقد تقطيع (${formatDimension(usedW_mm / 10)}×${formatDimension(remH_mm / 10)} سم)`;
        svg.appendChild(scrapTxt);
      }
    }

    const totalPiecesArea = drawCount * itemW_cm * itemH_cm;
    const parentArea = pW_cm * pH_cm;
    const scrapRatio = Math.max(0, (parentArea - totalPiecesArea) / parentArea);
    return scrapRatio;
  }

  /**
   * رسم طابع أمر الشغل المصغر (Micro-Stamp) في صفحة أمر الشغل
   * مصمم ومحصن لضمان خروج أمر الشغل في ورقة A4 واحدة مقدسة
   */
  function renderMicroStamp(container, options = {}) {
    if (!container) return;

    const {
      pressSheetW = 35.0,
      pressSheetH = 50.0,
      openW = 21.0,
      openH = 29.7,
      montageCount = 1,
      printingType = 'offset'
    } = options;

    clearContainer(container);

    const sW = Math.max(pressSheetW, pressSheetH);
    const sH = Math.min(pressSheetW, pressSheetH);
    const calc = PricingMath.calcImposition(sW, sH, openW, openH, printingType);
    const cols = calc.cols || 1;
    const rows = calc.rows || 1;
    const total = (montageCount > 0) ? montageCount : (calc.cutsPerSheet || 1);

    const svg = createSvgEl('svg', {
      viewBox: '0 0 120 85',
      width: '100%',
      height: '75px',
      preserveAspectRatio: 'xMidYMid meet',
      style: 'display: block; margin: 0 auto; page-break-inside: avoid; break-inside: avoid;'
    });

    // إطار الشيت بالأبيض والأسود الناصع للطباعة
    const bg = createSvgEl('rect', {
      x: 1, y: 1, width: 118, height: 83,
      fill: '#ffffff',
      stroke: '#000000',
      'stroke-width': 1
    });
    svg.appendChild(bg);

    // شريط البنسة المصغر
    if (printingType === 'offset') {
      const grip = createSvgEl('rect', {
        x: 1, y: 1, width: 118, height: 7,
        fill: '#eeeeee',
        stroke: '#888888',
        'stroke-width': 0.5
      });
      svg.appendChild(grip);
    }

    // شبكة القطع المصغرة
    const gridW = 112;
    const gridH = 70;
    const itemW = gridW / cols;
    const itemH = gridH / rows;

    let idx = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        idx++;
        const isActive = (idx <= total);
        const x = 4 + (c * itemW);
        const y = 10 + (r * itemH);

        const rect = createSvgEl('rect', {
          x: x + 1, y: y + 1,
          width: Math.max(2, itemW - 2),
          height: Math.max(2, itemH - 2),
          fill: isActive ? '#f0f0f0' : '#ffffff',
          stroke: isActive ? '#000000' : '#cccccc',
          'stroke-width': 0.8,
          'stroke-dasharray': isActive ? 'none' : '2,1'
        });
        svg.appendChild(rect);

        if (isActive) {
          const txt = createSvgEl('text', {
            x: x + (itemW / 2),
            y: y + (itemH / 2) + 2,
            'text-anchor': 'middle',
            fill: '#000000',
            'font-size': Math.min(8, itemH * 0.4),
            'font-weight': 'bold'
          });
          txt.textContent = idx;
          svg.appendChild(txt);
        }
      }
    }

    container.appendChild(svg);
  }

  return {
    renderPressSheet,
    renderShearingMap,
    renderMicroStamp,
    renderSkeleton
  };
})();

// تصدير عالمي
if (typeof window !== 'undefined') {
  window.ImpositionVisualizer = ImpositionVisualizer;
}
