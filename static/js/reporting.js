// File: static/js/reporting.js

(function () {
  'use strict';

  // قائمة الحقول المستثناة من الفلاتر LIKE
  const EXCLUDE_LIKE_KEYS = new Set([
    "csrf_token", "table", "date_field", "start_date", "end_date", "selected_fields"
  ]);

  // اختصارات للوصول للعناصر
  const $ = (sel, root = document) => root.querySelector(sel);
  const $all = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const safeJSON = (s, fallback = null) => {
    try {
      return JSON.parse(s || "");
    } catch {
      return fallback;
    }
  };

  // ترجمة اسم الحقل إذا كان متاحًا في FIELD_LABELS
  function translateField(name) {
    return (window.FIELD_LABELS && window.FIELD_LABELS[name]) || name;
  }

  // جلب الحقول الخاصة بالموديل المحدد من API
  function fetchModelFields(model) {
    if (!model) return Promise.resolve({ columns: [], date_fields: [] });

    return fetch(`/reports/api/model_fields?model=${encodeURIComponent(model)}`)
      .then(r => r.ok ? r.json() : { columns: [], date_fields: [] })
      .catch(() => ({ columns: [], date_fields: [] }));
  }

  // تعبئة خيارات الـ <select> بالقيم المحددة
  function fillSelectOptions(selectElement, items, keepSelected = true) {
    if (!selectElement) return;

    const previousSelection = keepSelected
      ? new Set(Array.from(selectElement.selectedOptions).map(opt => opt.value))
      : new Set();

    selectElement.innerHTML = "";

    (items || []).forEach(value => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = translateField(value);
      if (previousSelection.has(value)) option.selected = true;
      selectElement.appendChild(option);
    });
  }

  // بناء فلاتر LIKE ديناميكيًا
  function buildLikeFilters(columns) {
    const wrapper = $("#like_filters");
    if (!wrapper) return;

    const initialValues = safeJSON(wrapper.getAttribute("data-initial-like"), {}) || {};
    wrapper.innerHTML = "";

    const inputs = [];

    (columns || []).forEach(col => {
      if (!col || EXCLUDE_LIKE_KEYS.has(col)) return;

      const div = document.createElement("div");
      div.className = "col-md-3 col-sm-6 mb-3";

      const label = document.createElement("label");
      label.className = "form-label";
      label.textContent = translateField(col);

      const input = document.createElement("input");
      input.type = "text";
      input.className = "form-control";
      input.name = col;
      input.placeholder = `يحتوي… (${translateField(col)})`;
      if (initialValues[col] != null) input.value = String(initialValues[col]);

      div.appendChild(label);
      div.appendChild(input);
      wrapper.appendChild(div);
      inputs.push(input);
    });

    // تفعيل إرسال النموذج عند الضغط على Enter
    inputs.forEach(input => {
      input.addEventListener("keydown", e => {
        if (e.key === "Enter") {
          e.preventDefault();
          const form = $("#report-form");
          if (form) form.requestSubmit();
        }
      });
    });
  }

  // إعداد خيارات الحقول الزمنية في <select>
  function applyDateFieldOptions(dateSelect, dateFields) {
    if (!dateSelect) return;

    const currentValue = dateSelect.value;
    const defaultVal = dateSelect.getAttribute("data-default");

    dateSelect.innerHTML = '<option value="">—</option>';

    (dateFields || []).forEach(field => {
      const option = document.createElement("option");
      option.value = field;
      option.textContent = translateField(field);
      dateSelect.appendChild(option);
    });

    const options = Array.from(dateSelect.options);

    if (defaultVal && !currentValue && options.some(o => o.value === defaultVal)) {
      dateSelect.value = defaultVal;
    } else if (options.some(o => o.value === currentValue)) {
      dateSelect.value = currentValue;
    }
  }

  // تحديث الواجهة عند اختيار موديل معين
  function refreshForModel(model) {
    return fetchModelFields(model).then(({ columns, date_fields }) => {
      fillSelectOptions($("#selected_fields"), columns, true);
      applyDateFieldOptions($("#date_field"), date_fields);
      buildLikeFilters(columns);
    });
  }

  // تهيئة جدول البيانات باستخدام DataTables
  function initDataTable() {
    const table = $("#report-table");

    if (!table || !window.jQuery || !jQuery.fn?.DataTable) return;
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
        paginate: {
          first: "الأول",
          last: "الأخير",
          next: "التالي",
          previous: "السابق"
        }
      }
    });
  }

  // نقطة البداية - عند تحميل الصفحة
  document.addEventListener("DOMContentLoaded", () => {
    const tableSelector = $("#table");
    if (tableSelector) {
      refreshForModel(tableSelector.value);
      tableSelector.addEventListener("change", function () {
        refreshForModel(this.value);
      });
    }
    initDataTable();
  });

})();
