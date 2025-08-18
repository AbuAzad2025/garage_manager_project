// File: static/js/reporting.js
(function () {
  // تحميل الحقول وحقول التاريخ حسب الموديل
  function fetchModelFields(model) {
    if (!model) return;
    fetch(`/reports/api/model_fields?model=${encodeURIComponent(model)}`)
      .then((r) => r.json())
      .then((json) => {
        const selCols = document.getElementById('selected_fields');
        const selDate = document.getElementById('date_field');
        if (!selCols || !selDate) return;

        // columns
        selCols.innerHTML = '';
        (json.columns || []).forEach((c) => {
          const opt = document.createElement('option');
          opt.value = c;
          opt.textContent = c;
          selCols.appendChild(opt);
        });

        // date fields
        const current = selDate.value;
        selDate.innerHTML = '<option value="">—</option>';
        (json.date_fields || []).forEach((d) => {
          const opt = document.createElement('option');
          opt.value = d;
          opt.textContent = d;
          selDate.appendChild(opt);
        });
        // keep previous if exists
        const keep = Array.from(selDate.options).some(o => o.value === current);
        if (keep) selDate.value = current;

        // لو عندك DataTables متوفر، فعّل لاحقاً بعد بناء الجدول
      })
      .catch(() => {});
  }

  // تفعيل Chart.js للكانفسات التي تحمل data-*
  function initCharts() {
    if (typeof Chart === 'undefined') return;
    document.querySelectorAll('canvas.chartjs-chart').forEach(function (el) {
      var ctx = el.getContext('2d');
      var labels = JSON.parse(el.getAttribute('data-labels') || '[]');
      var values = JSON.parse(el.getAttribute('data-values') || '[]');
      var dsLabel = el.getAttribute('data-dataset-label') || '';
      new Chart(ctx, {
        type: el.dataset.type || 'line',
        data: {
          labels: labels,
          datasets: [{
            label: dsLabel,
            data: values,
            borderWidth: 2,
            fill: true
          }]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    const tableSel = document.getElementById('table');
    if (tableSel) {
      fetchModelFields(tableSel.value);
      tableSel.addEventListener('change', function () {
        fetchModelFields(this.value);
      });
    }
    initCharts();
  });
})();
