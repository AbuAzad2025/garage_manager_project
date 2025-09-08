/* global FIELD_LABELS */
(function () {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const safeJSON = (s, fallback = null) => { try { return JSON.parse(s || ""); } catch { return fallback; } };
  const t = (k) => (window.FIELD_LABELS && FIELD_LABELS[k]) || k;

  const STORAGE_KEY = 'dynamic_report_state.v2';
  const saveState = () => {
    const f = $('#report-form');
    if (!f) return;
    const sel = (name) => $(`[name="${name}"]`, f);
    const state = {
      table: sel('table')?.value || '',
      date_field: sel('date_field')?.value || '',
      start_date: sel('start_date')?.value || '',
      end_date: sel('end_date')?.value || '',
      limit: sel('limit')?.value || '',
      selected_fields: Array.from($('#selected_fields')?.selectedOptions || []).map(o => o.value),
      like_filters: collectLikeFilters()
    };
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch {}
  };
  const loadState = () => {
    try { return safeJSON(localStorage.getItem(STORAGE_KEY), null) || null; } catch { return null; }
  };

  let dt;
  function initDataTable() {
    const table = $('#report-table');
    if (!table || !window.jQuery || !jQuery.fn?.DataTable) return;
    if (jQuery.fn.dataTable.isDataTable(table)) {
      dt = jQuery(table).DataTable();
      return;
    }
    dt = jQuery(table).DataTable({
      pageLength: 50,
      order: [],
      autoWidth: false,
      language: {
        emptyTable: "لا توجد بيانات",
        info: "إظهار _START_ إلى _END_ من أصل _TOTAL_",
        infoEmpty: "إظهار 0 إلى 0 من أصل 0",
        lengthMenu: "إظهار _MENU_",
        loadingRecords: "جارٍ التحميل...",
        processing: "جارٍ المعالجة...",
        search: "بحث:",
        zeroRecords: "لا نتائج مطابقة",
        paginate: { first: "الأول", last: "الأخير", next: "التالي", previous: "السابق" }
      }
    });
  }
  function renderTable(headers, rows) {
    const thead = $('#thead-dynamic');
    const tbody = $('#tbody-dynamic');
    const noData = $('#no-data');

    if (!Array.isArray(headers)) headers = [];
    if (!Array.isArray(rows)) rows = [];

    thead.innerHTML = '';
    const trh = document.createElement('tr');
    headers.forEach(h => {
      const th = document.createElement('th');
      th.textContent = t(h);
      trh.appendChild(th);
    });
    thead.appendChild(trh);

    tbody.innerHTML = '';
    rows.forEach(obj => {
      const tr = document.createElement('tr');
      headers.forEach(h => {
        const td = document.createElement('td');
        let v = obj[h];
        if (typeof v === 'number' && isFinite(v)) {
          td.classList.add('text-end');
          v = Number(v).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
        } else if (v == null || v === '') {
          v = '—';
        }
        td.textContent = v;
        td.classList.add('text-nowrap');
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });

    if (dt) {
      dt.clear();
      dt.rows.add(jQuery(tbody).find('tr'));
      dt.draw();
    } else {
      initDataTable();
    }

    $('#result-count').textContent = rows.length || 0;
    noData.classList.toggle('d-none', rows.length > 0);
  }

  function translateField(name) { return t(name); }
  async function fetchModelFields(model) {
    if (!model) return { columns: [], date_fields: [] };
    const r = await fetch(`/reports/api/model_fields?model=${encodeURIComponent(model)}`);
    if (!r.ok) return { columns: [], date_fields: [] };
    return r.json();
  }

  function fillSelectOptions(select, items, keepSelected = true) {
    if (!select) return;
    const prev = keepSelected ? new Set(Array.from(select.selectedOptions).map(o => o.value)) : new Set();
    select.innerHTML = '';
    (items || []).forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = translateField(v);
      if (prev.has(v)) opt.selected = true;
      select.appendChild(opt);
    });
    const pre = safeJSON(select.getAttribute('data-selected'), []);
    if (pre?.length) {
      $$('#selected_fields option').forEach(o => o.selected = pre.includes(o.value));
      select.removeAttribute('data-selected');
    }
  }
  function applyDateFieldOptions(select, dateFields) {
    if (!select) return;
    const current = select.getAttribute('data-selected') || select.value || '';
    const def = select.getAttribute('data-default') || '';
    select.innerHTML = '<option value="">—</option>';
    (dateFields || []).forEach(df => {
      const opt = document.createElement('option');
      opt.value = df;
      opt.textContent = translateField(df);
      select.appendChild(opt);
    });
    if (current && $(`option[value="${CSS.escape(current)}"]`, select)) {
      select.value = current;
    } else if (def && $(`option[value="${CSS.escape(def)}"]`, select)) {
      select.value = def;
    }
    select.setAttribute('data-selected', select.value || '');
  }

  const LIKE_HINTS = ['name','number','code','sku','email','phone','notes','desc','reference','tracking'];
  function isLikelyTextField(c) {
    const lc = (c || '').toLowerCase();
    return LIKE_HINTS.some(k => lc.includes(k));
  }
  function buildLikeFilters(columns) {
    const wrap = $('#like_filters');
    if (!wrap) return;
    const initial = safeJSON(wrap.getAttribute('data-initial-like'), {}) || {};
    wrap.innerHTML = '';
    const textCols = (columns || []).filter(isLikelyTextField).slice(0, 12);
    textCols.forEach(col => {
      const div = document.createElement('div');
      div.className = 'col-lg-3 col-md-4 col-sm-6';
      const label = document.createElement('label');
      label.className = 'form-label';
      label.textContent = translateField(col);
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'form-control';
      input.name = col;
      input.placeholder = `يحتوي… (${translateField(col)})`;
      if (initial[col] != null) input.value = String(initial[col]);
      div.appendChild(label);
      div.appendChild(input);
      wrap.appendChild(div);
      input.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
          e.preventDefault();
          $('#report-form')?.requestSubmit();
        }
      });
    });
  }
  function collectLikeFilters() {
    const obj = {};
    $$('#like_filters input[name]').forEach(inp => {
      const val = inp.value?.trim();
      if (val) obj[inp.name] = val;
    });
    return obj;
  }

  function showLoading(v) { $('#loading-overlay')?.classList.toggle('d-none', !v); }

  async function runDynamicReport() {
    const form = $('#report-form');
    if (!form) return;
    const fd = new FormData(form);
    const payload = {
      table: fd.get('table') || '',
      date_field: fd.get('date_field') || '',
      start_date: fd.get('start_date') || '',
      end_date: fd.get('end_date') || '',
      limit: Number(fd.get('limit') || 1000),
      columns: Array.from($('#selected_fields')?.selectedOptions || []).map(o => o.value),
      like_filters: collectLikeFilters(),
      aggregates: { count: ['id'] }
    };
    const csrf = form.querySelector('input[name="csrf_token"]')?.value || '';
    showLoading(true);
    try {
      const r = await fetch('/reports/api/dynamic', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRFToken': csrf } : {})
        },
        body: JSON.stringify(payload)
      });
      if (!r.ok) throw new Error('فشل الاتصال بالسيرفر');
      const data = await r.json();
      const rows = Array.isArray(data.data) ? data.data : [];
      const headers = rows.length ? Object.keys(rows[0]) : (payload.columns || []);
      const limited = rows.slice(0, payload.limit || 1000);
      renderTable(headers, limited);
      renderSummary(data.summary || {});
      saveState();
    } catch (e) {
      alert("حدث خطأ أثناء جلب التقرير: " + e.message);
      console.error(e);
    } finally {
      showLoading(false);
    }
  }

  function renderSummary(summary) {
    const host = $('#summary-cards');
    if (!host) return;
    host.innerHTML = '';
    const entries = Object.entries(summary || {});
    if (!entries.length) {
      host.classList.add('d-none');
      return;
    }
    entries.forEach(([k, v]) => {
      const col = document.createElement('div');
      col.className = 'col-xl-2 col-lg-3 col-md-4 col-sm-6';
      col.innerHTML = `
        <div class="card text-center h-100 shadow-sm summary-card">
          <div class="card-body">
            <div class="text-muted small">${t(k)}</div>
            <div class="fs-4 fw-bold">${formatVal(v)}</div>
          </div>
        </div>`;
      host.appendChild(col);
    });
    host.classList.remove('d-none');
  }
  function formatVal(v) {
    if (typeof v === 'number' && isFinite(v)) {
      return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    return v ?? '—';
  }

  async function refreshForModel(model) {
    const { columns, date_fields } = await fetchModelFields(model);
    fillSelectOptions($('#selected_fields'), columns, true);
    applyDateFieldOptions($('#date_field'), date_fields);
    buildLikeFilters(columns);
  }

  function setupPrint() {
    $('#btn-print')?.addEventListener('click', () => window.print());
  }

  document.addEventListener('DOMContentLoaded', async () => {
    initDataTable();
    setupPrint();
    const state = loadState();
    const f = $('#report-form');
    if (state && f) {
      f.table.value = state.table || f.table.value;
      await refreshForModel(f.table.value);
      $('#date_field').value = state.date_field || $('#date_field').value;
      f.start_date.value = state.start_date || f.start_date.value;
      f.end_date.value = state.end_date || f.end_date.value;
      f.limit.value = state.limit || f.limit.value;
      const sel = $('#selected_fields');
      if (sel && Array.isArray(state.selected_fields) && state.selected_fields.length) {
        $$('#selected_fields option').forEach(o => { o.selected = state.selected_fields.includes(o.value); });
      }
      const wrap = $('#like_filters');
      if (wrap) {
        const iv = state.like_filters || {};
        Object.keys(iv).forEach(k => {
          const inp = $(`#like_filters input[name="${CSS.escape(k)}"]`);
          if (inp) inp.value = iv[k];
        });
      }
    } else {
      await refreshForModel($('#table')?.value || window.__selectedTable || '');
    }
    $('#table')?.addEventListener('change', async function () {
      await refreshForModel(this.value);
      saveState();
    });
    $('#report-form')?.addEventListener('submit', (e) => {
      const isCSV = e.submitter && e.submitter.getAttribute('formaction')?.includes('/export/dynamic.csv');
      if (!isCSV) {
        e.preventDefault();
        runDynamicReport();
      } else {
        saveState();
      }
    });
    if (window.__initialData) {
      renderTable(window.__initialHeaders || [], window.__initialData || []);
      renderSummary(window.__initialSummary || {});
    }
  });
})();
