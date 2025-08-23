// File: static/js/reporting.js
(function () {
  'use strict';

  const EXCLUDE_LIKE_KEYS = new Set([
    "csrf_token", "table", "date_field", "start_date", "end_date", "selected_fields"
  ]);

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
  function safeJSON(s, fallback = null) { try { return JSON.parse(s || ""); } catch { return fallback; } }

  // 🔹 ترجمة أسماء الحقول عبر FIELD_LABELS
  function translateField(name) {
    if (window.FIELD_LABELS && window.FIELD_LABELS[name]) {
      return window.FIELD_LABELS[name];
    }
    return name;
  }

  function fetchModelFields(model) {
    if (!model) return Promise.resolve({ columns: [], date_fields: [] });
    return fetch(`/reports/api/model_fields?model=${encodeURIComponent(model)}`)
      .then(r => r.ok ? r.json() : { columns: [], date_fields: [] })
      .catch(() => ({ columns: [], date_fields: [] }));
  }

  function fillSelectOptions(sel, items, keepSelected = true) {
    if (!sel) return;
    const prev = keepSelected ? new Set(Array.from(sel.selectedOptions).map(o => o.value)) : new Set();
    sel.innerHTML = "";
    (items || []).forEach(v => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = translateField(v); // تعريب
      if (prev.has(v)) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function buildLikeFilters(columns) {
    const wrap = $("#like_filters");
    if (!wrap) return;
    const initialLike = safeJSON(wrap.getAttribute("data-initial-like"), {}) || {};
    wrap.innerHTML = "";

    const inputs = [];
    (columns || []).forEach(col => {
      if (!col || EXCLUDE_LIKE_KEYS.has(col)) return;
      const div = document.createElement("div");
      div.className = "col-md-3 col-sm-6 mb-3";

      const label = document.createElement("label");
      label.className = "form-label";
      label.textContent = translateField(col); // تعريب

      const input = document.createElement("input");
      input.type = "text";
      input.className = "form-control";
      input.name = col;
      input.placeholder = `يحتوي… (${translateField(col)})`; // تعريب
      if (initialLike[col] != null) input.value = String(initialLike[col]);

      div.appendChild(label);
      div.appendChild(input);
      wrap.appendChild(div);
      inputs.push(input);
    });

    inputs.forEach(inp => {
      inp.addEventListener("keydown", e => {
        if (e.key === "Enter") {
          e.preventDefault();
          const form = $("#report-form");
          if (form) form.requestSubmit();
        }
      });
    });
  }

  function applyDateFieldOptions(dateSel, dateFields) {
    if (!dateSel) return;
    const current = dateSel.value;
    dateSel.innerHTML = '<option value="">—</option>';
    (dateFields || []).forEach(d => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = translateField(d); // تعريب
      dateSel.appendChild(opt);
    });
    const want = dateSel.getAttribute("data-default");
    if (want && !current) {
      if (Array.from(dateSel.options).some(o => o.value === want)) dateSel.value = want;
    } else if (Array.from(dateSel.options).some(o => o.value === current)) {
      dateSel.value = current;
    }
  }

  function refreshForModel(model) {
    return fetchModelFields(model).then(({ columns, date_fields }) => {
      fillSelectOptions($("#selected_fields"), columns, true);
      applyDateFieldOptions($("#date_field"), date_fields);
      buildLikeFilters(columns);
    });
  }

  function initDataTable() {
    const table = $("#report-table");
    if (!table || !window.jQuery || !jQuery.fn || !jQuery.fn.DataTable) return;
    if (jQuery.fn.dataTable.isDataTable(table)) return;
    jQuery(table).DataTable({
      pageLength: 25,
      order: [],
      language: {
        emptyTable: "لا توجد بيانات",
        info: "إظهار _START_ إلى _END_ من أصل _TOTAL_ مدخل",
        infoEmpty: "إظهار 0 إلى 0 من أصل 0",
        lengthMenu: "إظهار _MENU_ سطر",
        loadingRecords: "جارٍ التحميل...",
        processing: "جارٍ المعالجة...",
        search: "بحث:",
        zeroRecords: "لا نتائج مطابقة",
        paginate: { first: "الأول", last: "الأخير", next: "التالي", previous: "السابق" }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const tableSel = $("#table");
    if (tableSel) {
      refreshForModel(tableSel.value);
      tableSel.addEventListener("change", function () { refreshForModel(this.value); });
    }
    initDataTable();
  });
})();
