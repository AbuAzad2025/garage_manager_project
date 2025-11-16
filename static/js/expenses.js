document.addEventListener('DOMContentLoaded', function () {
  "use strict";

  const style = document.createElement('style');
  style.textContent = `
    .dataTables_wrapper .dataTables_scrollBody{overflow-x:auto !important;overflow-y:hidden}
    table.table-sticky th:last-child,table.table-sticky td:last-child{
      position:sticky;right:0;background:var(--bs-body-bg,#fff);z-index:3;box-shadow:-4px 0 6px rgba(0,0,0,.06)
    }
  `;
  document.head.appendChild(style);

  const $one = (sel, ctx) => (ctx || document).querySelector(sel);
  const $all = (sel, ctx) => Array.from((ctx || document).querySelectorAll(sel));
  let expensesAjaxSeq = 0;

  function setDisabled(el, disabled) {
    if (!el) return;
    const isSelect2 = el.classList && el.classList.contains('select2-hidden-accessible');
    el.disabled = !!disabled;
    if (isSelect2 && window.jQuery) jQuery(el).trigger('change.select2');
    if (disabled) el.setAttribute('disabled', 'disabled'); else el.removeAttribute('disabled');
  }

  function clearFieldValues(container) {
    if (!container) return;
    $all('input, select, textarea', container).forEach(inp => {
      if (inp.type === 'hidden') { inp.value = ''; return; }
      if (inp.tagName === 'SELECT') {
        inp.selectedIndex = -1;
        if (window.jQuery && jQuery.fn && jQuery.fn.select2) jQuery(inp).val(null).trigger('change');
      } else if ('value' in inp) {
        inp.value = '';
      }
    });
  }

  const methodSel   = $one('#payment_method');
  const detailsWrap = $one('#methodDetails');

  const pStart = $one('#period_start');
  const pEnd   = $one('#period_end');

  function normalizeResults(data) {
    let items = [];
    if (Array.isArray(data)) items = data;
    else if (data && Array.isArray(data.results)) items = data.results;
    else if (data && Array.isArray(data.items)) items = data.items;
    return items.map(it => ({
      id: it.id ?? it.value ?? it.pk ?? it.ID,
      text: it.text ?? it.name ?? it.label ?? it.title ?? String(it.id ?? '')
    })).filter(x => x.id != null);
  }

  function prefillAjaxSelect(el) {
    const endpoint = el.dataset.endpoint || el.getAttribute('data-endpoint');
    if (!endpoint) return;
    const val = (el.value || '').trim();
    if (!val) return;
    const hasText = el.selectedOptions && el.selectedOptions[0] && el.selectedOptions[0].text && el.selectedOptions[0].text.trim();
    if (hasText) return;
    fetch(`${endpoint}?id=${encodeURIComponent(val)}`, { headers: { 'Accept': 'application/json' } })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const items = normalizeResults(data || {});
        if (!items.length) return;
        const it = items[0];
        const opt = new Option(it.text, it.id, true, true);
        el.appendChild(opt);
        if (window.jQuery && jQuery.fn && jQuery.fn.select2) jQuery(el).trigger('change');
      })
      .catch(() => {});
  }

  function initAjaxSelect(el) {
    if (!(window.jQuery && $.fn && $.fn.select2) || !el) return;
    const $el = jQuery(el);
    if ($el.data('select2')) return;

    const endpoint = el.dataset.endpoint || el.getAttribute('data-endpoint');
    const placeholder = el.dataset.placeholder || el.getAttribute('data-placeholder') || 'اختر...';
    const minimumInputLength = parseInt(el.dataset.minlen || el.getAttribute('data-minlen') || '1', 10);

    const opt = {
      dir: 'rtl',
      width: '100%',
      allowClear: true,
      placeholder,
      language: {
        inputTooShort: () => `اكتب ${minimumInputLength} حرف على الأقل`,
        searching: () => 'جارِ البحث...',
        noResults: () => 'لا توجد نتائج'
      }
    };

    if (endpoint) {
      opt.ajax = {
        url: endpoint,
        dataType: 'json',
        delay: 250,
        cache: true,
        data: params => ({ q: params.term || '', page: params.page || 1 }),
        processResults: data => ({ results: normalizeResults(data) })
      };
      opt.minimumInputLength = minimumInputLength;
    }

    $el.select2(opt);
    prefillAjaxSelect(el);
  }

  function initAllAjaxSelects() {
    $all('.ajax-select').forEach(initAjaxSelect);
  }

  // ✅ تم إزالة الكود القديم المتعارض - الآن القالب يتحكم في إظهار/إخفاء الحقول

  const METHOD_FIELDS = {
    cash:   [],
    cheque: ['check_number', 'check_bank', 'check_due_date'],
    bank:   ['bank_transfer_ref', 'bank_name', 'account_number', 'account_holder'],
    card:   ['card_number', 'card_holder', 'card_expiry'],
    online: ['online_gateway', 'online_ref'],
    other:  []
  };

  const DETAIL_FIELD_DEFS = {
    check_number: { label: 'رقم الشيك', type: 'text' },
    check_bank: { label: 'اسم البنك', type: 'text' },
    check_due_date: { label: 'تاريخ الاستحقاق', type: 'date' },
    bank_transfer_ref: { label: 'مرجع الحوالة', type: 'text' },
    bank_name: { label: 'اسم البنك', type: 'text' },
    account_number: { label: 'رقم الحساب', type: 'text' },
    account_holder: { label: 'صاحب الحساب', type: 'text' },
    card_number: { label: 'رقم البطاقة', type: 'text' },
    card_holder: { label: 'حامل البطاقة', type: 'text' },
    card_expiry: { label: 'انتهاء البطاقة', type: 'text', placeholder: 'MM/YY' },
    online_gateway: { label: 'بوابة الدفع', type: 'text' },
    online_ref: { label: 'مرجع العملية', type: 'text' },
  };

  function applyMethodDetails(method) {
    if (!detailsWrap) return;
    const need = new Set(METHOD_FIELDS[method] || []);
    let anyShown = false;

    $all('[data-field]', detailsWrap).forEach(box => {
      const fname = box.dataset.field || box.getAttribute('data-field');
      const show = need.has(fname);
      const inp = $one('input, select, textarea', box);
      box.style.display = show ? '' : 'none';
      setDisabled(inp, !show);
      if (!show && inp && 'value' in inp) inp.value = '';
      if (show) anyShown = true;
    });

    detailsWrap.style.display = anyShown ? '' : 'none';
  }

  if (methodSel) {
    applyMethodDetails((methodSel.value || '').toLowerCase());
    methodSel.addEventListener('change', () => applyMethodDetails((methodSel.value || '').toLowerCase()));
  }

  function validatePeriod() {
    if (!pStart || !pEnd) return true;
    if (!pStart.value || !pEnd.value) return true;
    const s = new Date(pStart.value);
    const e = new Date(pEnd.value);
    const ok = !(e < s);
    pStart.classList.toggle('is-invalid', !ok);
    pEnd.classList.toggle('is-invalid', !ok);
    return ok;
  }
  if (pStart) pStart.addEventListener('change', validatePeriod);
  if (pEnd)   pEnd.addEventListener('change', validatePeriod);

  initAllAjaxSelects();
  validatePeriod();

  const expenseForm = document.getElementById('expenseForm');
  const partialSection = document.getElementById('partialPaymentsSection');
  const partialManager = partialSection ? createPartialPaymentsManager(partialSection) : null;

  if (expenseForm && partialManager) {
    expenseForm.addEventListener('submit', function (e) {
      if (!partialManager.preparePayload()) {
        e.preventDefault();
        e.stopPropagation();
        return false;
      }
      return true;
    });
  }

  const addStickyClass = id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('table-sticky');
  };
  ['expenses-table','types-table','employees-table'].forEach(addStickyClass);

  if (window.jQuery && $.fn && $.fn.DataTable) {
    const hasButtons = $.fn.dataTable && $.fn.dataTable.Buttons;
    const langUrl = "/static/datatables/Arabic.json";

    function initDT(tableEl, extraOpts) {
      if (!tableEl || $.fn.DataTable.isDataTable(tableEl)) return;
      
      // تحقق من البنية
      const $tbl = $(tableEl);
      if (!$tbl.find('thead').length || !$tbl.find('tbody').length) {
        return;
      }
      
      // تحقق من وجود بيانات فعلية
      const dataRows = $tbl.find('tbody tr').not(':has(td[colspan])');
      if (dataRows.length === 0) {
        return; // لا نهيئ DataTables للجداول الفارغة
      }
      
      // تحقق من تطابق الأعمدة
      const headerCols = $tbl.find('thead tr:first th, thead tr:first td').length;
      const bodyCols = dataRows.first().find('td').length;
      
      if (headerCols !== bodyCols) {

        return;
      }
      
      try {
        const cols = tableEl.tHead ? tableEl.tHead.rows[0].cells.length : 0;
        const lastCol = cols ? cols - 1 : null;
        const baseOpts = {
          language: { 
            url: langUrl,
            emptyTable: "لا توجد بيانات",
            info: "عرض _START_ إلى _END_ من أصل _TOTAL_",
            search: "بحث:",
            paginate: { first: "الأول", last: "الأخير", next: "التالي", previous: "السابق" }
          },
          ordering: true,
          info: true,
          autoWidth: false,
          responsive: false,
          stateSave: true,
          pageLength: 25,
          scrollX: true,
          scrollCollapse: true,
          initComplete: function() {
            if (typeof window.onExpensesTableReady === "function") {
              window.onExpensesTableReady(this.api());
            }
          }
        };
        if (lastCol !== null) baseOpts.columnDefs = [{ orderable: false, targets: [lastCol], width: 180, className: 'text-nowrap' }];
        baseOpts.dom = hasButtons ? "Bfrtip" : "frtip";
        if (hasButtons) baseOpts.buttons = ["excelHtml5", "print"];
        const api = $(tableEl).DataTable(Object.assign({}, baseOpts, extraOpts || {}));
        $(window).on('resize', () => api.columns.adjust());
        document.addEventListener('shown.bs.tab', () => api.columns.adjust());
        document.addEventListener('shown.bs.collapse', () => api.columns.adjust());
      } catch (e) {

      }
    }

    const runExpensesTableInit = () => initDT(document.getElementById('expenses-table'));
    window.__initExpensesDataTable = runExpensesTableInit;
    runExpensesTableInit();
    initDT(document.getElementById('types-table'));
    initDT(document.getElementById('employees-table'));
  }

  function initExpensesAjax() {
    const tableWrapper = document.getElementById('expenses-table-wrapper');
    const searchInput = document.getElementById('expenses-search');
    const searchSummary = document.getElementById('expenses-search-summary');
    let summaryWrapper = document.getElementById('expenses-summary-wrapper');
    const paginationWrapper = document.getElementById('expenses-pagination');
    if (!tableWrapper) return false;

    const loadingTpl = '<div class="text-center py-4 text-muted"><div class="spinner-border spinner-border-sm me-2"></div>جارِ التحميل…</div>';

    function fetchAndUpdate(targetUrl) {
      const baseUrl = targetUrl instanceof URL ? targetUrl : new URL(targetUrl, window.location.origin);
      baseUrl.searchParams.delete('ajax');
      const previousTable = tableWrapper.innerHTML;
      const requestId = ++expensesAjaxSeq;
      tableWrapper.innerHTML = loadingTpl;

      const fetchUrl = new URL(baseUrl.toString(), window.location.origin);
      fetchUrl.searchParams.set('ajax', '1');

      return fetch(fetchUrl.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }
      })
        .then(function (res) {
          if (!res.ok) throw res;
          return res.json();
        })
        .then(function (data) {
          if (requestId !== expensesAjaxSeq) return;

          if (typeof data.table_html === 'string') {
            tableWrapper.innerHTML = data.table_html;
          } else {
            tableWrapper.innerHTML = previousTable;
          }

          if (typeof data.summary_html === 'string' && document.getElementById('expenses-summary-wrapper')) {
            const currentSummary = document.getElementById('expenses-summary-wrapper');
            currentSummary.outerHTML = data.summary_html;
            summaryWrapper = document.getElementById('expenses-summary-wrapper');
          } else {
            summaryWrapper = document.getElementById('expenses-summary-wrapper');
          }

          if (paginationWrapper && data.pagination) {
            paginationWrapper.innerHTML = buildPaginationUi(data.pagination);
          }

          if (searchSummary && typeof data.total_filtered === 'number') {
            searchSummary.textContent = 'إجمالي النتائج: ' + data.total_filtered;
          }

          if (window.ExpensesUI && typeof window.ExpensesUI.refreshUI === 'function') {
            window.ExpensesUI.refreshUI();
          } else {
            if (typeof window.__initExpensesDataTable === 'function') window.__initExpensesDataTable();
            if (typeof window.enableTableSorting === 'function') window.enableTableSorting('#expenses-table');
          }

          const finalUrl = new URL(baseUrl.toString(), window.location.origin);
          finalUrl.searchParams.delete('ajax');
          const qs = finalUrl.searchParams.toString();
          window.history.replaceState({}, '', finalUrl.pathname + (qs ? '?' + qs : ''));
        })
        .catch(function (err) {
          if (requestId !== expensesAjaxSeq) return;
          console.error(err);
          if (err && typeof err.text === 'function') {
            err.text().then(function (raw) {
              try {
                const parsed = JSON.parse(raw);
                if (parsed && parsed.error && typeof window.showNotification === 'function') {
                  window.showNotification(parsed.error, 'danger');
                }
              } catch (parseErr) {
                console.error("Failed to parse error payload", parseErr);
              }
            }).catch(function () {});
          }
          tableWrapper.innerHTML = previousTable;
          summaryWrapper = document.getElementById('expenses-summary-wrapper');
          if (window.ExpensesUI && typeof window.ExpensesUI.refreshUI === 'function') {
            window.ExpensesUI.refreshUI();
          } else {
            if (typeof window.__initExpensesDataTable === 'function') window.__initExpensesDataTable();
            if (typeof window.enableTableSorting === 'function') window.enableTableSorting('#expenses-table');
          }
        });
    }

    function buildPaginationUi(meta) {
      if (!meta || !meta.pages || meta.pages <= 1) return '';
      const parts = [];
      parts.push('<nav aria-label="التنقل بين صفحات المصاريف"><ul class="pagination justify-content-center flex-wrap mb-0">');
      const prevDisabled = meta.has_prev ? '' : ' disabled';
      const prevUrl = meta.prev_url || '#';
      const prevPage = meta.prev_page || '';
      parts.push(`<li class="page-item${prevDisabled}"><a class="page-link" href="${prevUrl}" data-expenses-page="true" data-page="${prevPage}">السابق</a></li>`);
      if (meta.show_first_gap) {
        parts.push(`<li class="page-item"><a class="page-link" href="${meta.first_url}" data-expenses-page="true" data-page="1">1</a></li>`);
        parts.push('<li class="page-item disabled"><span class="page-link">…</span></li>');
      }
      (meta.window || []).forEach(function (item) {
        const active = item.current ? ' active' : '';
        parts.push(`<li class="page-item${active}"><a class="page-link" href="${item.url}" data-expenses-page="true" data-page="${item.page}">${item.page}</a></li>`);
      });
      if (meta.show_last_gap) {
        parts.push('<li class="page-item disabled"><span class="page-link">…</span></li>');
        parts.push(`<li class="page-item"><a class="page-link" href="${meta.last_url}" data-expenses-page="true" data-page="${meta.last_page}">${meta.last_page}</a></li>`);
      }
      const nextDisabled = meta.has_next ? '' : ' disabled';
      const nextUrl = meta.next_url || '#';
      const nextPage = meta.next_page || '';
      parts.push(`<li class="page-item${nextDisabled}"><a class="page-link" href="${nextUrl}" data-expenses-page="true" data-page="${nextPage}">التالي</a></li>`);
      parts.push('</ul></nav>');
      return parts.join('');
    }

    function buildPageUrl(pageValue) {
      const nextUrl = new URL(window.location.href);
      if (pageValue && Number(pageValue) > 1) {
        nextUrl.searchParams.set('page', pageValue);
      } else {
        nextUrl.searchParams.delete('page');
      }
      nextUrl.searchParams.delete('ajax');
      return nextUrl.toString();
    }

    function handlePaginationClick(event) {
      const link = event.target.closest('a[data-expenses-page]');
      if (!link) return;
      const parent = link.parentElement;
      if (parent && parent.classList.contains('disabled')) {
        event.preventDefault();
        return;
      }
      const targetUrl = link.getAttribute('href') || buildPageUrl(link.dataset.page);
      if (!targetUrl || targetUrl === '#') {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      fetchAndUpdate(targetUrl);
    }

    if (paginationWrapper) {
      paginationWrapper.addEventListener('click', handlePaginationClick);
    }

    function triggerSearch() {
      const nextUrl = new URL(window.location.href);
      const term = searchInput ? searchInput.value.trim() : '';
      if (term) {
        nextUrl.searchParams.set('q', term);
      } else {
        nextUrl.searchParams.delete('q');
        nextUrl.searchParams.delete('search');
      }
      nextUrl.searchParams.delete('page');
      fetchAndUpdate(nextUrl);
    }

    if (searchInput) {
      const debouncedSearch = typeof debounce === 'function' ? debounce(triggerSearch, 300) : triggerSearch;
      searchInput.addEventListener('input', function () { debouncedSearch(); }, { passive: true });
    }

    window.addEventListener('popstate', function () {
      const current = new URL(window.location.href);
      if (searchInput) {
        const term = current.searchParams.get('q') || current.searchParams.get('search') || '';
        if (searchInput.value !== term) searchInput.value = term;
      }
      fetchAndUpdate(current);
    });

    return true;
  }

  if (typeof window !== 'undefined' && typeof window.enableTableSorting === 'function') {
    window.enableTableSorting('#expenses-table');
  }

  initExpensesAjax();

  window.ExpensesUI = {
    refreshUI: () => {
      initAllAjaxSelects();
      validatePeriod();
      if (typeof window.__initExpensesDataTable === 'function') {
        window.__initExpensesDataTable();
      }
      if (typeof window.enableTableSorting === 'function') {
        window.enableTableSorting('#expenses-table');
      }
    }
  };

  function createPartialPaymentsManager(section) {
    const tableBody = section.querySelector('#partialPaymentsBody');
    const emptyRow = section.querySelector('#partialEmptyRow');
    const addBtn = section.querySelector('#addPartialPaymentRow');
    const payloadInput = document.getElementById('partial_payments_payload');
    const summaryPaid = document.getElementById('partialNewPaidLabel');
    const summaryRemaining = document.getElementById('partialRemainingLabel');
    const summaryTotal = document.getElementById('partialTotalAmountLabel');
    const summaryExisting = document.getElementById('partialExistingPaidLabel');
    const summaryExtraNote = document.getElementById('partialMixedCurrencyNote');
    const generalSection = document.getElementById('generalPaymentSection');
    const amountInput = document.getElementById('amount');
    const baseCurrencySelect = document.getElementById('currency');
    const methodOptions = JSON.parse(section.dataset.methodOptions || '[]');
    const currencyOptions = JSON.parse(section.dataset.currencyOptions || '[]');
    let baseCurrency = (section.dataset.baseCurrency || 'ILS').toUpperCase();
    const datasetBaseAmount = parseFloat(section.dataset.baseAmount || '0') || 0;
    const defaultDate = section.dataset.defaultDate || '';
    const existingPaid = parseFloat(section.dataset.existingPaid || '0');
    const currencyList = currencyOptions.length ? currencyOptions : [{ code: baseCurrency, label: baseCurrency }];
    const rows = new Map();

    function currentBaseCurrency() {
      const selectVal = baseCurrencySelect ? baseCurrencySelect.value : null;
      return (selectVal || baseCurrency || 'ILS').toUpperCase();
    }

    function currentBaseAmount() {
      const live = parseFloat(amountInput?.value || '');
      if (!Number.isNaN(live) && live > 0) {
        return live;
      }
      return datasetBaseAmount;
    }

    function ensureEmptyState() {
      const hasRows = rows.size > 0;
      if (emptyRow) {
        emptyRow.style.display = hasRows ? 'none' : '';
      }
      if (generalSection) {
        generalSection.classList.toggle('d-none', hasRows);
      }
    }

    function wrapCell(content) {
      const td = document.createElement('td');
      td.appendChild(content);
      return td;
    }

    function buildMethodSelect(value) {
      const select = document.createElement('select');
      select.className = 'form-select form-select-sm';
      methodOptions.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.value;
        option.textContent = opt.label;
        if (opt.value === value) option.selected = true;
        select.appendChild(option);
      });
      return select;
    }

    function buildCurrencySelect(value) {
      const select = document.createElement('select');
      select.className = 'form-select form-select-sm';
      currencyList.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.code;
        option.textContent = opt.label || opt.code;
        if (opt.code === value) option.selected = true;
        select.appendChild(option);
      });
      return select;
    }

    function toggleDetails(rowId) {
      const rowState = rows.get(rowId);
      if (!rowState) return;
      rowState.detailsRow.classList.toggle('d-none');
    }

    function applyMethodDetails(rowId, method) {
      const rowState = rows.get(rowId);
      if (!rowState) return;
      const need = new Set(METHOD_FIELDS[method] || []);
      Object.entries(rowState.detailInputs).forEach(([field, meta]) => {
        const show = need.has(field);
        meta.wrapper.style.display = show ? '' : 'none';
        meta.wrapper.dataset.active = show ? '1' : '0';
        if (!show) meta.input.value = '';
      });
    }

    function addRow(initial = {}) {
      if (!tableBody) return;
      const rowId = `pp-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const row = document.createElement('tr');
      row.className = 'partial-payment-row';
      row.dataset.rowId = rowId;

      const dateInput = document.createElement('input');
      dateInput.type = 'date';
      dateInput.className = 'form-control form-control-sm';
      dateInput.value = initial.date || defaultDate || '';

      const amountInputEl = document.createElement('input');
      amountInputEl.type = 'number';
      amountInputEl.step = '0.01';
      amountInputEl.min = '0';
      amountInputEl.className = 'form-control form-control-sm text-end';
      amountInputEl.value = initial.amount || '';

      const currencySelect = buildCurrencySelect((initial && initial.currency) || baseCurrency);
      const methodSelect = buildMethodSelect(initial.method || (methodOptions[0] && methodOptions[0].value) || 'cash');

      const referenceInput = document.createElement('input');
      referenceInput.type = 'text';
      referenceInput.className = 'form-control form-control-sm';
      referenceInput.placeholder = 'مرجع';
      referenceInput.value = initial.reference || '';

      const notesInput = document.createElement('input');
      notesInput.type = 'text';
      notesInput.className = 'form-control form-control-sm';
      notesInput.placeholder = 'ملاحظات';
      notesInput.value = initial.notes || '';

      const tools = document.createElement('div');
      tools.className = 'btn-group btn-group-sm';

      const detailsBtn = document.createElement('button');
      detailsBtn.type = 'button';
      detailsBtn.className = 'btn btn-outline-info';
      detailsBtn.innerHTML = '<i class="fas fa-sliders-h"></i>';
      detailsBtn.addEventListener('click', () => toggleDetails(rowId));

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn btn-outline-danger';
      removeBtn.innerHTML = '<i class="fas fa-trash"></i>';
      removeBtn.addEventListener('click', () => {
        const state = rows.get(rowId);
        if (state) {
          state.rowEl.remove();
          state.detailsRow.remove();
          rows.delete(rowId);
          ensureEmptyState();
          updateSummary();
        }
      });

      tools.appendChild(detailsBtn);
      tools.appendChild(removeBtn);

      row.appendChild(wrapCell(dateInput));
      row.appendChild(wrapCell(amountInputEl));
      row.appendChild(wrapCell(currencySelect));
      row.appendChild(wrapCell(methodSelect));
      row.appendChild(wrapCell(referenceInput));
      row.appendChild(wrapCell(notesInput));
      const actionCell = document.createElement('td');
      actionCell.className = 'text-center';
      actionCell.appendChild(tools);
      row.appendChild(actionCell);

      const detailsRow = document.createElement('tr');
      detailsRow.className = 'partial-details-row d-none';
      const detailsCell = document.createElement('td');
      detailsCell.colSpan = 7;
      const detailsContainer = document.createElement('div');
      detailsContainer.className = 'row g-2';
      detailsCell.appendChild(detailsContainer);
      detailsRow.appendChild(detailsCell);

      const detailInputs = {};
      Object.entries(DETAIL_FIELD_DEFS).forEach(([field, meta]) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'col-md-4 detail-field';
        wrapper.dataset.detailField = field;
        wrapper.dataset.active = '0';
        wrapper.style.display = 'none';
        const label = document.createElement('label');
        label.className = 'form-label small mb-1';
        label.textContent = meta.label;
        const input = document.createElement('input');
        input.type = meta.type || 'text';
        input.className = 'form-control form-control-sm';
        if (meta.placeholder) input.placeholder = meta.placeholder;
        wrapper.appendChild(label);
        wrapper.appendChild(input);
        detailsContainer.appendChild(wrapper);
        detailInputs[field] = { wrapper, input };
      });

      tableBody.appendChild(row);
      tableBody.appendChild(detailsRow);
      rows.set(rowId, {
        rowEl: row,
        detailsRow,
        inputs: {
          date: dateInput,
          amount: amountInputEl,
          currency: currencySelect,
          method: methodSelect,
          reference: referenceInput,
          notes: notesInput,
        },
        detailInputs,
      });

      [dateInput, amountInputEl, currencySelect, methodSelect, referenceInput, notesInput].forEach(el => {
        el.addEventListener('input', updateSummary, { passive: true });
        el.addEventListener('change', () => {
          if (el === methodSelect) applyMethodDetails(rowId, methodSelect.value);
          updateSummary();
        }, { passive: true });
      });

      applyMethodDetails(rowId, methodSelect.value);
      ensureEmptyState();
      updateSummary();
    }

    function collectRows() {
      const data = [];
      rows.forEach((state) => {
        const amount = parseFloat(state.inputs.amount.value || '0');
        if (Number.isNaN(amount) || amount <= 0) {
          return;
        }
        const entry = {
          date: (state.inputs.date.value || '').trim(),
          amount: state.inputs.amount.value,
          currency: (state.inputs.currency.value || baseCurrency).toUpperCase(),
          method: (state.inputs.method.value || 'cash').trim(),
          reference: (state.inputs.reference.value || '').trim(),
          notes: (state.inputs.notes.value || '').trim(),
        };
        const details = {};
        Object.entries(state.detailInputs).forEach(([field, meta]) => {
          if (meta.wrapper.dataset.active === '1') {
            const val = meta.input.value;
            if (val) details[field] = val;
          }
        });
        entry.details = details;
        data.push(entry);
      });
      return data;
    }

    function updateSummary() {
      const totals = {};
      rows.forEach((state) => {
        const amount = parseFloat(state.inputs.amount.value || '0');
        if (Number.isNaN(amount) || amount <= 0) return;
        const currency = (state.inputs.currency.value || baseCurrency).toUpperCase();
        totals[currency] = (totals[currency] || 0) + amount;
      });
      const baseCur = currentBaseCurrency();
      const baseAmt = currentBaseAmount();
      const basePaid = totals[baseCur] || 0;
      if (summaryTotal) summaryTotal.textContent = `${baseAmt.toFixed(2)} ${baseCur}`;
      if (summaryExisting) summaryExisting.textContent = `${existingPaid.toFixed(2)} ${baseCur}`;
      if (summaryPaid) summaryPaid.textContent = `${basePaid.toFixed(2)} ${baseCur}`;
      const remaining = baseAmt - existingPaid - basePaid;
      if (summaryRemaining) {
        summaryRemaining.textContent = `${remaining.toFixed(2)} ${baseCur}`;
        summaryRemaining.classList.toggle('text-danger', remaining < -0.01);
      }

      delete totals[baseCur];
      const others = Object.entries(totals).filter(([, val]) => val > 0.0001);
      if (summaryExtraNote) {
        if (others.length) {
          const txt = others.map(([cur, val]) => `${val.toFixed(2)} ${cur}`).join(' + ');
          summaryExtraNote.textContent = `مدفوع بعملات أخرى: ${txt}`;
          summaryExtraNote.classList.remove('d-none');
        } else {
          summaryExtraNote.classList.add('d-none');
        }
      }
    }

    if (addBtn) {
      addBtn.addEventListener('click', () => addRow());
    }

    ensureEmptyState();
    updateSummary();
    if (amountInput) {
      amountInput.addEventListener('input', updateSummary, { passive: true });
    }
    if (baseCurrencySelect) {
      baseCurrencySelect.addEventListener('change', () => {
        baseCurrency = currentBaseCurrency();
        updateSummary();
      });
    }

    return {
      preparePayload() {
        if (!payloadInput) return true;
        const rowData = collectRows();
        const baseCur = currentBaseCurrency();
        const baseAmt = currentBaseAmount();
        payloadInput.value = rowData.length ? JSON.stringify(rowData) : '';
        const baseSum = rowData
          .filter((entry) => entry.currency === baseCur)
          .reduce((acc, entry) => acc + (parseFloat(entry.amount || '0') || 0), 0);
        if (existingPaid + baseSum - baseAmt > 0.01) {
          alert('الدفعات الجزئية تتجاوز المبلغ الكلي للمصروف بهذه العملة.');
          return false;
        }
        return true;
      },
    };
  }
});
