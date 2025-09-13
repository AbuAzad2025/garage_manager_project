(function () {
  'use strict';

  if (typeof window.Chart === 'undefined') return;

  const isRTL = (document.dir || document.documentElement.getAttribute('dir') || '').toLowerCase() === 'rtl';
  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  const fallbackPalette = ['#0d6efd','#198754','#dc3545','#fd7e14','#20c997','#6f42c1','#0dcaf0','#6610f2','#6c757d','#198754'];
  const varColor = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  const palette = [
    varColor('--bs-primary', fallbackPalette[0]),
    varColor('--bs-success', fallbackPalette[1]),
    varColor('--bs-danger', fallbackPalette[2]),
    varColor('--bs-warning', fallbackPalette[3]),
    varColor('--bs-teal', fallbackPalette[4]),
    varColor('--bs-purple', fallbackPalette[5]),
    varColor('--bs-info', fallbackPalette[6]),
    varColor('--bs-indigo', fallbackPalette[7]),
    varColor('--bs-secondary', fallbackPalette[8]),
    varColor('--bs-green', fallbackPalette[9])
  ];
  const getColor = (i, custom) => (custom && custom[i]) || palette[i % palette.length];

  function formatValue(v, opts = {}) {
    const n = Number(v);
    if (!isFinite(n)) return String(v);
    const { currency, unit, digits = 2, locale } = opts;
    try {
      if (currency) return new Intl.NumberFormat(locale, { style: 'currency', currency, maximumFractionDigits: digits }).format(n);
      const str = new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(n);
      return unit ? `${str} ${unit}` : str;
    } catch {
      const str = n.toFixed(Math.max(0, Math.min(6, digits)));
      return unit ? `${str} ${unit}` : str;
    }
  }

  const parseJsonAttr = (el, name, fallback) => {
    const raw = el.getAttribute(name);
    try { return raw ? JSON.parse(raw) : fallback; } catch { return fallback; }
  };

  function buildDatasets(el, ctx) {
    const rawDatasets = parseJsonAttr(el, 'data-datasets', null);
    const colors = parseJsonAttr(el, 'data-colors', null);
    const smooth = el.getAttribute('data-smooth') === '1';
    const fill = el.getAttribute('data-fill') === '1';
    if (Array.isArray(rawDatasets)) {
      return rawDatasets.map((d, i) => {
        const gradient = ctx.createLinearGradient(0, 0, 0, el.height);
        gradient.addColorStop(0, getColor(i, colors));
        gradient.addColorStop(1, getColor((i+1), colors));
        return {
          label: d.label || `Dataset ${i + 1}`,
          data: Array.isArray(d.data) ? d.data : [],
          borderWidth: 2,
          tension: smooth ? 0.35 : 0,
          fill: d.fill ?? fill,
          borderColor: d.borderColor || getColor(i, colors),
          backgroundColor: d.backgroundColor || gradient
        };
      });
    }
    const values = parseJsonAttr(el, 'data-values', []);
    const label = el.getAttribute('data-label') || '';
    const gradient = ctx.createLinearGradient(0, 0, 0, el.height);
    gradient.addColorStop(0, getColor(0, colors));
    gradient.addColorStop(1, getColor(1, colors));
    return [{
      label,
      data: Array.isArray(values) ? values : [],
      borderWidth: 2,
      tension: smooth ? 0.35 : 0,
      fill,
      borderColor: getColor(0, colors),
      backgroundColor: gradient
    }];
  }

  function buildOptions(el) {
    const currency = el.getAttribute('data-currency');
    const unit = el.getAttribute('data-unit');
    const digits = parseInt(el.getAttribute('data-digits') || '2', 10);
    const stacked = el.getAttribute('data-stacked') === '1';
    const tickFormat = {
      callback: val => formatValue(val, { currency, unit, digits }),
      maxTicksLimit: 8
    };
    return {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: dpr,
      interaction: { mode: 'index', intersect: false },
      animations: {
        tension: { duration: 1200, easing: 'easeInOutQuad', from: 0.2, to: 0.5, loop: false }
      },
      plugins: {
        legend: { display: true, rtl: isRTL, labels: { usePointStyle: true } },
        tooltip: {
          enabled: true,
          rtl: isRTL,
          callbacks: {
            label: ctx => {
              const v = ctx.parsed.y ?? ctx.parsed;
              const title = ctx.dataset.label ? `${ctx.dataset.label}: ` : '';
              return title + formatValue(v, { currency, unit, digits });
            }
          }
        },
        datalabels: {
          anchor: 'end',
          align: 'top',
          color: '#444',
          font: { weight: 'bold' },
          formatter: val => formatValue(val, { currency, unit, digits })
        }
      },
      scales: {
        x: { stacked, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true } },
        y: { stacked, beginAtZero: true, ticks: tickFormat }
      }
    };
  }

  function buildConfig(el, ctx) {
    const type = el.getAttribute('data-chart-type') || el.getAttribute('data-type') || 'line';
    const labels = parseJsonAttr(el, 'data-labels', []);
    const datasets = buildDatasets(el, ctx);
    return { type, data: { labels, datasets }, options: buildOptions(el), plugins: [ChartDataLabels] };
  }

  function showLoader(el) {
    let loader = el.parentElement.querySelector('.chartjs-loader');
    if (!loader) {
      loader = document.createElement('div');
      loader.className = 'chartjs-loader';
      loader.innerHTML = `<div class="spinner-border text-primary" role="status" style="width:2rem;height:2rem;"><span class="visually-hidden">Loading...</span></div>`;
      loader.style.cssText = `position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:2;`;
      el.parentElement.style.position = 'relative';
      el.parentElement.appendChild(loader);
    }
  }

  function hideLoader(el) {
    const loader = el.parentElement.querySelector('.chartjs-loader');
    if (loader) loader.remove();
  }

  function initCanvas(el) {
    const ctx = el.getContext('2d');
    if (!ctx) return;
    showLoader(el);
    setTimeout(() => {
      if (el._chartjsInstance) { try { el._chartjsInstance.destroy(); } catch {} el._chartjsInstance = null; }
      const config = buildConfig(el, ctx);
      el._chartjsInstance = new Chart(ctx, config);
      hideLoader(el);
    }, 50);
  }

  function destroyCanvas(el) {
    if (el?._chartjsInstance) { try { el._chartjsInstance.destroy(); } catch {} el._chartjsInstance = null; }
  }

  function updateCanvas(el) {
    const chart = el._chartjsInstance;
    if (!chart) { initCanvas(el); return; }
    const ctx = el.getContext('2d');
    const labels = parseJsonAttr(el, 'data-labels', []);
    const datasets = buildDatasets(el, ctx);
    chart.data.labels = labels;
    chart.data.datasets = datasets;
    chart.options = buildOptions(el);
    chart.update();
  }

  let observer = null;
  function observeAndInit(el) {
    if (!('IntersectionObserver' in window)) { initCanvas(el); return; }
    if (!observer) {
      observer = new IntersectionObserver(entries => {
        entries.forEach(entry => { if (entry.isIntersecting) { initCanvas(entry.target); observer.unobserve(entry.target); } });
      }, { rootMargin: '100px' });
    }
    observer.observe(el);
  }

  function attachAutoUpdateButton(el) {
    if (el.getAttribute('data-auto-button') !== '1') return;
    const button = document.createElement('button');
    button.className = 'btn btn-sm btn-outline-primary mt-2';
    button.textContent = 'تحديث الرسم';
    button.addEventListener('click', () => {
      const oldValues = parseJsonAttr(el, 'data-values', []);
      const newValues = oldValues.map(v => v + Math.round(Math.random() * 10));
      el.setAttribute('data-values', JSON.stringify(newValues));
      AppCharts.refresh(el);
    });
    el.parentElement.appendChild(button);
  }

  const AppCharts = {
    init(root = document) {
      const scope = root instanceof Element ? root : document;
      scope.querySelectorAll('canvas.chartjs-chart').forEach(el => { observeAndInit(el); attachAutoUpdateButton(el); });
    },
    refresh(root = document) {
      const scope = root instanceof Element ? root : document;
      scope.querySelectorAll('canvas.chartjs-chart').forEach(updateCanvas);
    },
    destroy(root = document) {
      const scope = root instanceof Element ? root : document;
      scope.querySelectorAll('canvas.chartjs-chart').forEach(destroyCanvas);
    }
  };

  window.AppCharts = AppCharts;
  document.addEventListener('DOMContentLoaded', () => { AppCharts.init(); });
})();
