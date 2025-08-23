// File: static/js/charts.js
(function () {
  'use strict';

  // ==== حِماية: لازم يكون Chart.js محمّل قبل هذا الملف ====
  if (typeof window.Chart === 'undefined') {
    console.error('[charts.js] Chart.js is not loaded. Include it before charts.js');
    return;
  }

  // ==== إعدادات عامة افتراضية ====
  const isRTL = (document.dir || document.documentElement.getAttribute('dir') || '').toLowerCase() === 'rtl';
  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1)); // cap to 2 for perf

  // ألوان من CSS variables لو متوفرة، وإلا باليت افتراضي
  const fallbackPalette = [
    '#0d6efd', '#198754', '#dc3545', '#fd7e14', '#20c997',
    '#6f42c1', '#0dcaf0', '#6610f2', '#6c757d', '#198754'
  ];
  function varColor(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  const palette = [
    varColor('--bs-primary', fallbackPalette[0]),
    varColor('--bs-success', fallbackPalette[1]),
    varColor('--bs-danger',  fallbackPalette[2]),
    varColor('--bs-warning', fallbackPalette[3]),
    varColor('--bs-teal',    fallbackPalette[4]),
    varColor('--bs-purple',  fallbackPalette[5]),
    varColor('--bs-info',    fallbackPalette[6]),
    varColor('--bs-indigo',  fallbackPalette[7]),
    varColor('--bs-secondary', fallbackPalette[8]),
    varColor('--bs-green',   fallbackPalette[9]),
  ];
  const getColor = (i, custom) => (custom && custom[i]) || palette[i % palette.length];

  // فورماتر أرقام/عملة/وحدة
  function formatValue(v, opts) {
    const n = Number(v);
    if (!isFinite(n)) return String(v);
    const {
      currency = null,   // مثال: "JOD" أو "USD"
      unit = null,       // مثال: "كم" أو "pcs"
      digits = 2,        // من 0 إلى 6
      locale = undefined // اتركها فاضية عشان تاخذ من المتصفح
    } = opts || {};
    try {
      if (currency) {
        return new Intl.NumberFormat(locale, { style: 'currency', currency, maximumFractionDigits: digits }).format(n);
      }
      const s = new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(n);
      return unit ? `${s} ${unit}` : s;
    } catch {
      const s = n.toFixed(Math.max(0, Math.min(6, digits)));
      return unit ? `${s} ${unit}` : s;
    }
  }

  // قراءة خصائص JSON من data-*
  function parseJsonAttr(el, name, fallback) {
    const raw = el.getAttribute(name);
    if (!raw) return fallback;
    try { return JSON.parse(raw); } catch { return fallback; }
  }

  // يبني datasets من data-datasets أو من data-values مع data-label
  function buildDatasets(el) {
    const dsFromAttr = parseJsonAttr(el, 'data-datasets', null);
    const colors = parseJsonAttr(el, 'data-colors', null);
    const smooth = (el.getAttribute('data-smooth') || '0') === '1';
    const fill = (el.getAttribute('data-fill') || '0') === '1';

    if (Array.isArray(dsFromAttr)) {
      return dsFromAttr.map((d, i) => ({
        label: d.label || `Dataset ${i + 1}`,
        data: Array.isArray(d.data) ? d.data : [],
        borderWidth: 2,
        tension: smooth ? 0.35 : 0,
        fill: !!(d.fill ?? fill),
        borderColor: d.borderColor || getColor(i, colors),
        backgroundColor: d.backgroundColor || getColor(i, colors) + '33'
      }));
    }

    const values = parseJsonAttr(el, 'data-values', []);
    const label = el.getAttribute('data-label') || '';
    return [{
      label,
      data: Array.isArray(values) ? values : [],
      borderWidth: 2,
      tension: smooth ? 0.35 : 0,
      fill: fill,
      borderColor: getColor(0, colors),
      backgroundColor: (getColor(0, colors)) + '33'
    }];
  }

  // تكوين الخيارات
  function buildOptions(el) {
    const currency = el.getAttribute('data-currency') || null;
    const unit = el.getAttribute('data-unit') || null;
    const digits = parseInt(el.getAttribute('data-digits') || '2', 10);
    const stacked = (el.getAttribute('data-stacked') || '0') === '1';

    const commonTicks = {
      callback: (val) => formatValue(val, { currency, unit, digits }),
      maxTicksLimit: 8
    };

    return {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: dpr,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, rtl: isRTL, labels: { usePointStyle: true } },
        tooltip: {
          enabled: true,
          rtl: isRTL,
          callbacks: {
            label: (ctx) => {
              const v = ctx.parsed.y ?? ctx.parsed;
              const title = ctx.dataset.label ? `${ctx.dataset.label}: ` : '';
              return title + formatValue(v, { currency, unit, digits });
            }
          }
        }
      },
      scales: {
        x: { stacked, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true } },
        y: { stacked, beginAtZero: true, ticks: commonTicks }
      }
    };
  }

  // يبني الكونفيج النهائي
  function buildConfig(el) {
    const type = el.getAttribute('data-chart-type') || el.getAttribute('data-type') || 'line';
    const labels = parseJsonAttr(el, 'data-labels', []);
    const datasets = buildDatasets(el);
    return {
      type,
      data: { labels, datasets },
      options: buildOptions(el)
    };
  }

  // تهيئة/تدمير
  function initCanvas(el) {
    const ctx = el.getContext('2d');
    if (!ctx) return;
    if (el._chartjsInstance) {
      try { el._chartjsInstance.destroy(); } catch {}
      el._chartjsInstance = null;
    }
    const cfg = buildConfig(el);
    el._chartjsInstance = new window.Chart(ctx, cfg);
  }
  function destroyCanvas(el) {
    if (el && el._chartjsInstance) {
      try { el._chartjsInstance.destroy(); } catch {}
      el._chartjsInstance = null;
    }
  }

  // Lazy init عند الظهور
  let observer = null;
  function observeAndInit(el) {
    if (!('IntersectionObserver' in window)) {
      initCanvas(el);
      return;
    }
    if (!observer) {
      observer = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            initCanvas(e.target);
            observer.unobserve(e.target);
          }
        });
      }, { rootMargin: '100px' });
    }
    observer.observe(el);
  }

  // API عام
  const AppCharts = {
    init(root) {
      const scope = root instanceof Element ? root : document;
      scope.querySelectorAll('canvas.chartjs-chart').forEach((el) => observeAndInit(el));
    },
    refresh(root) {
      const scope = root instanceof Element ? root : document;
      scope.querySelectorAll('canvas.chartjs-chart').forEach((el) => initCanvas(el));
    },
    destroy(root) {
      const scope = root instanceof Element ? root : document;
      scope.querySelectorAll('canvas.chartjs-chart').forEach((el) => destroyCanvas(el));
    }
  };
  window.AppCharts = AppCharts;

  // جاهزية DOM
  document.addEventListener('DOMContentLoaded', function () {
    AppCharts.init(document);
  });
})();
