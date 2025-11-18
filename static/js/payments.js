let smartSearchInitialized = false;

function initializeSmartSearchOnce() {
  if (!smartSearchInitialized) {
    smartSearchInitialized = true;
    setTimeout(function() {
      initSmartSearch();
    }, 100);
  }
}

document.addEventListener('DOMContentLoaded', function() {
  'use strict';
  
  initializeSmartSearchOnce();
  
  const filterSelectors = ['#filterEntity', '#filterStatus', '#filterDirection', '#filterMethod', '#startDate', '#endDate', '#filterCurrency'];
  const searchInput = document.querySelector('#payments-search');
  const ENTITY_ENUM = { customer:'CUSTOMER', supplier:'SUPPLIER', partner:'PARTNER', sale:'SALE', service:'SERVICE', expense:'EXPENSE', loan:'LOAN', preorder:'PREORDER', shipment:'SHIPMENT' };
  function inferEntityContext() {
    const path = location.pathname.replace(/\/+$/, '');
    const m = path.match(/^\/vendors\/(suppliers|partners)\/(\d+)\/payments$/i);
    if (m) return { entity_type: m[1].toLowerCase()==='suppliers' ? 'SUPPLIER' : 'PARTNER', entity_id: m[2] };
    const qs = new URLSearchParams(location.search);
    const et = (qs.get('entity_type') || '').toLowerCase();
    const ei = qs.get('entity_id') || '';
    return { entity_type: ENTITY_ENUM[et] || '', entity_id: ei || '' };
  }
  const ctx = inferEntityContext();
  const entSel = document.querySelector('#filterEntity');
  if (entSel && ctx.entity_type) { entSel.value = ctx.entity_type; entSel.disabled = true; }
  function injectStatementButtons() {
    if (!ctx.entity_type || !ctx.entity_id) return;
    const filtersRow = document.querySelector('.row.mb-4.g-2.align-items-end') || document.querySelector('.row.mb-4');
    if (!filtersRow || document.getElementById('btnExportCsv')) return;
    const wrap = document.createElement('div');
    wrap.className = 'col-auto d-flex gap-2 no-print';
    wrap.innerHTML = '<button id="btnExportCsv" class="btn btn-outline-success"><i class="fas fa-file-csv me-1"></i> تصدير CSV</button>';
    filtersRow.appendChild(wrap);
    document.getElementById('btnExportCsv').addEventListener('click', exportCsv);
  }
  injectStatementButtons();
  if (typeof window !== 'undefined' && typeof window.enableTableSorting === 'function') {
    window.enableTableSorting('#paymentsTable');
  }
  function debounce(fn, ms) { let t; return function () { clearTimeout(t); t = setTimeout(() => fn.apply(this, arguments), ms); }; }
  const debouncedReload = debounce(function () { updateUrlQuery(); loadPayments(1); }, 250);
  
  const applyFilters = function() {
    updateUrlQuery();
    loadPayments(1);
    if (btnApplyFilters) {
      btnApplyFilters.classList.remove('btn-warning');
      btnApplyFilters.classList.add('btn-success');
      btnApplyFilters.innerHTML = '<i class="fas fa-filter me-1"></i> تطبيق';
    }
  };
  
  const resetFilters = function() {
    const qs = new URLSearchParams(location.search);
    const entityType = qs.get('entity_type') || '';
    const entityId = qs.get('entity_id') || '';
    
    const filterEntity = document.querySelector('#filterEntity');
    const filterStatus = document.querySelector('#filterStatus');
    const filterDirection = document.querySelector('#filterDirection');
    const filterMethod = document.querySelector('#filterMethod');
    const startDate = document.querySelector('#startDate');
    const endDate = document.querySelector('#endDate');
    const filterCurrency = document.querySelector('#filterCurrency');
    
    if (filterEntity) filterEntity.value = entityType;
    if (filterStatus) filterStatus.value = '';
    if (filterDirection) filterDirection.value = '';
    if (filterMethod) filterMethod.value = '';
    if (startDate) startDate.value = '';
    if (endDate) endDate.value = '';
    if (filterCurrency) filterCurrency.value = '';
    if (searchInput) searchInput.value = '';
    
    if (btnApplyFilters) {
      btnApplyFilters.classList.remove('btn-warning');
      btnApplyFilters.classList.add('btn-success');
      btnApplyFilters.innerHTML = '<i class="fas fa-filter me-1"></i> تطبيق';
    }
    
    const params = new URLSearchParams();
    if (entityType) params.append('entity_type', entityType);
    if (entityId) params.append('entity_id', entityId);
    history.replaceState(null, '', location.pathname + (params.toString() ? ('?' + params.toString()) : ''));
    loadPayments(1);
  };
  
  const btnApplyFilters = document.getElementById('btnApplyFilters');
  if (btnApplyFilters) {
    btnApplyFilters.addEventListener('click', applyFilters);
  }
  
  const btnResetFilters = document.getElementById('btnResetFilters');
  if (btnResetFilters) {
    btnResetFilters.addEventListener('click', resetFilters);
  }
  
  filterSelectors.forEach(function (sel) {
    const el = document.querySelector(sel);
    if (!el) return;
    el.addEventListener('change', function() {
      if (btnApplyFilters) {
        btnApplyFilters.classList.add('btn-warning');
        btnApplyFilters.innerHTML = '<i class="fas fa-filter me-1"></i> تطبيق <span class="badge bg-light text-dark ms-1">تغييرات</span>';
      }
    }, { passive: true });
    if (el.tagName === 'INPUT') {
      el.addEventListener('input', function() {
        if (btnApplyFilters) {
          btnApplyFilters.classList.add('btn-warning');
          btnApplyFilters.innerHTML = '<i class="fas fa-filter me-1"></i> تطبيق <span class="badge bg-light text-dark ms-1">تغييرات</span>';
        }
      }, { passive: true });
    }
  });
  if (searchInput) {
    searchInput.addEventListener('input', function() {
      if (btnApplyFilters) {
        btnApplyFilters.classList.add('btn-warning');
        btnApplyFilters.innerHTML = '<i class="fas fa-filter me-1"></i> تطبيق <span class="badge bg-light text-dark ms-1">تغييرات</span>';
      }
    }, { passive: true });
  }
  // ✅ الدوال نُقلت إلى common-utils.js (normalizeEntity, normalizeMethod, normDir, validDates)
  function currentFilters(page = 1) {
    const urlParams = new URLSearchParams(window.location.search);
    const raw = {
      entity_type: normalizeEntity(document.querySelector('#filterEntity')?.value || ctx.entity_type || ''),
      status: document.querySelector('#filterStatus')?.value || '',
      direction: normDir(document.querySelector('#filterDirection')?.value || ''),
      method: normalizeMethod(document.querySelector('#filterMethod')?.value || ''),
      start_date: document.querySelector('#startDate')?.value || '',
      end_date: document.querySelector('#endDate')?.value || '',
      currency: (document.querySelector('#filterCurrency')?.value || '').toUpperCase(),
      q: (searchInput && searchInput.value) ? searchInput.value.trim() : '',
      sort: urlParams.get('sort') || 'date',
      order: urlParams.get('order') || 'desc',
      page
    };
    const v = validDates(raw.start_date, raw.end_date);
    raw.start_date = v.start; raw.end_date = v.end;
    if (ctx.entity_id) raw.entity_id = ctx.entity_id;
    return raw;
  }
  function syncFiltersFromUrl() {
    const qs = new URLSearchParams(location.search);
    const setVal = (sel, v) => { const el = document.querySelector(sel); if (el && v != null) el.value = v; };
    setVal('#filterEntity', qs.get('entity_type'));
    setVal('#filterStatus', qs.get('status'));
    setVal('#filterDirection', qs.get('direction'));
    setVal('#filterMethod', qs.get('method'));
    setVal('#startDate', qs.get('start_date'));
    setVal('#endDate', qs.get('end_date'));
    setVal('#filterCurrency', qs.get('currency'));
    setVal('#payments-search', qs.get('q'));
  }
  function updateUrlQuery() {
    const raw = currentFilters();
    const params = new URLSearchParams();
    Object.entries(raw).forEach(function ([k, v]) { if (v && k !== 'page') params.append(k, v); });
    history.replaceState(null, '', location.pathname + (params.toString() ? ('?' + params.toString()) : ''));
  }
  let _abortCtrl = null;
  let _lastList = [];
  function loadPayments(page = 1) {
    const raw = currentFilters(page);
    const params = new URLSearchParams();
    Object.entries(raw).forEach(function ([k, v]) { if (v) params.append(k, v); });
    params.append('format', 'json'); // إضافة format=json لإرجاع JSON
    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController();
    setLoading(true);
    fetch('/payments/?' + params.toString(), { headers: { 'Accept': 'application/json' }, signal: _abortCtrl.signal })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (data) {
        const list = Array.isArray(data.payments) ? data.payments : [];
        _currentPageSum = {
          sum: data.totals?.page_sum || 0,
          sumILS: data.totals?.page_sum_ils || 0
        };
        _lastList = list.slice();
        renderPaymentsTable(_lastList);
        renderPagination(Number(data.total_pages || 1), Number(data.current_page || 1));
        renderTotals(data.totals || null);
        const searchSummaryEl = document.getElementById('payments-search-summary');
        if (searchSummaryEl) searchSummaryEl.textContent = 'إجمالي النتائج: ' + (data.total_items || 0);
        const totalCountEl = document.getElementById('payments-total-count');
        if (totalCountEl) totalCountEl.textContent = data.total_items || 0;
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        _lastList = [];
        renderPaymentsTable([]);
        renderPagination(1, 1);
        renderTotals(null);
        const searchSummaryEl = document.getElementById('payments-search-summary');
        if (searchSummaryEl) searchSummaryEl.textContent = 'إجمالي النتائج: 0';
        const totalCountEl = document.getElementById('payments-total-count');
        if (totalCountEl) totalCountEl.textContent = '0';
      })
      .finally(function () { setLoading(false); });
  }
  function setLoading(is) {
    const tbody = document.querySelector('#paymentsTable tbody');
    if (!tbody) return;
    if (is) tbody.innerHTML = '<tr><td colspan="13" class="text-center text-muted py-4"><div class="spinner-border spinner-border-sm me-2"></div>جارِ التحميل…</td></tr>';
  }
  // ✅ جميع دوال العرض نُقلت إلى common-utils.js:
  // badgeForDirection, badgeForStatus, toNumber, fmtAmount, deriveEntityLabel, 
  // normalizeEntity, normalizeMethod, normDir, validDates
  let _currentPageSum = {sum: 0, sumILS: 0}; // ✅ سيتم ملؤها من الباكند
  
  function renderPaymentsTable(list) {
    const tbody = document.querySelector('#paymentsTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!list.length) {
      const message = 'لا توجد بيانات';
      const tr = document.createElement('tr');
      tr.innerHTML = '<td colspan="13" class="text-center text-muted py-4">' + message + '</td>';
      tbody.appendChild(tr);
      return;
    }
    const sanitize = function (v) {
      if (v == null) return '';
      return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    };
    const sorted = list.slice().sort(function (a, b) {
      const db = b.payment_date ? Date.parse(b.payment_date) : 0;
      const da = a.payment_date ? Date.parse(a.payment_date) : 0;
      if (!Number.isNaN(db) && !Number.isNaN(da) && db !== da) return db - da;
      const bi = b.id || 0;
      const ai = a.id || 0;
      return bi - ai;
    });
    let sumAmount = 0;
    let sumAmountIls = 0;
    sorted.forEach(function (p) {
      const splitsHtml = (p.splits || []).map(function (s) {
        const splitCurrency = (s.currency || p.currency || '').toUpperCase();
        const convertedCurrency = (p.currency || '').toUpperCase();
        let text = String((s.method || '')).toUpperCase() + ': ' + fmtAmount(s.amount) + ' ' + splitCurrency;
        if (splitCurrency && convertedCurrency && splitCurrency !== convertedCurrency && s.converted_amount != null) {
          text += '<span class="text-light text-opacity-75 ms-1">≈ ' + fmtAmount(s.converted_amount) + ' ' + convertedCurrency + '</span>';
        }
        return '<span class="badge bg-secondary me-1 text-light">' + text + '</span>';
      }).join(' ');
      const dateOnly = (p.payment_date || '').split('T')[0] || '';
      const actions =
        '<div class="btn-group btn-group-sm" role="group">' +
          '<a href="/payments/' + p.id + '" class="btn btn-info">عرض</a>' +
          '<button type="button" class="btn btn-warning btn-archive" data-id="' + p.id + '" title="أرشفة الدفعة">أرشفة</button>' +
          '<button type="button" class="btn btn-danger btn-del" data-id="' + p.id + '">حذف عادي</button>' +
          '<a href="/hard-delete/payment/' + p.id + '" class="btn btn-outline-danger" title="حذف قوي" onclick="return confirm(\'حذف قوي - سيتم حذف جميع البيانات المرتبطة!\')">حذف قوي</a>' +
        '</div>';
      const tr = document.createElement('tr');
      // ✅ استخدام amountInILS من الباكند (سيتم إضافته لاحقاً)
      let amountInILS = p.amount_in_ils || p.total_amount; // fallback للبيانات القديمة
      let fxRateDisplay = '-';
      
      if (p.currency && p.currency !== 'ILS') {
        if (p.fx_rate_used && parseFloat(p.fx_rate_used) > 0) {
          fxRateDisplay = FXUtils.formatFxRate(parseFloat(p.fx_rate_used), p.fx_rate_source);
        } else {
          fxRateDisplay = FXUtils.formatFxRate(1, 'default');
        }
      }
      const amountNumeric = Number(p.total_amount || 0);
      if (!Number.isNaN(amountNumeric)) sumAmount += amountNumeric;
      const amountIlsNumeric = Number(amountInILS || 0);
      if (!Number.isNaN(amountIlsNumeric)) sumAmountIls += amountIlsNumeric;
      
      // إنشاء عمود التفاصيل المحسّن
      const entityDetails = deriveEntityLabel(p);
      let notesHtml = '';
      if (p.is_manual_check) {
        notesHtml += '<div class="mt-1"><span class="badge bg-warning text-dark"><i class="fas fa-file-invoice"></i> شيك يدوي';
        if (p.check_number) {
          notesHtml += ' - رقم: ' + sanitize(p.check_number);
        }
        notesHtml += '</span></div>';
      }
      if (p.notes && p.notes.trim()) {
        notesHtml += '<div class="mt-1"><small class="text-muted"><i class="fas fa-sticky-note"></i> ' + p.notes.substring(0, 80) + (p.notes.length > 80 ? '...' : '') + '</small></div>';
      }
      var delivererText = p.deliverer_name && p.deliverer_name.trim() ? sanitize(p.deliverer_name.trim()) : '-';
      var receiverText = p.receiver_name && p.receiver_name.trim() ? sanitize(p.receiver_name.trim()) : '-';
      
      tr.innerHTML =
        '<td class="text-center" data-sort-value="' + (p.id || 0) + '"><strong>' + p.id + '</strong></td>' +
        '<td data-sort-value="' + (p.payment_date || '') + '">' + dateOnly + '</td>' +
        '<td class="text-end" data-sort-value="' + (amountNumeric || 0) + '"><strong>' + fmtAmount(p.total_amount) + '</strong></td>' +
        '<td class="text-center"><span class="badge badge-secondary">' + (p.currency || '') + '</span></td>' +
        '<td class="text-center"><small>' + fxRateDisplay + '</small></td>' +
        '<td class="text-end" data-sort-value="' + (amountIlsNumeric || 0) + '"><strong style="color: #0056b3;">' + fmtAmount(amountInILS) + ' ₪</strong></td>' +
        '<td>' + (p.is_manual_check ? '<span class="badge bg-warning text-dark"><i class="fas fa-file-invoice"></i> شيك يدوي</span>' : (splitsHtml || '<span class="badge badge-info">' + (p.method || '') + '</span>')) + '</td>' +
        '<td class="text-center">' + badgeForDirection(p.direction) + '</td>' +
        '<td class="text-center">' + badgeForStatus(p.status) + '</td>' +
        '<td>' + delivererText + '</td>' +
        '<td>' + receiverText + '</td>' +
        '<td>' + entityDetails + notesHtml + '</td>' +
        '<td>' + actions + '</td>';
      tbody.appendChild(tr);
    });
    const totalsSource = _currentPageSum || { sum: sumAmount, sumILS: sumAmountIls };
    const totalsLabel = 'إجمالي الصفحة';
    const totalRow = document.createElement('tr');
    totalRow.dataset.sortFixed = 'true';
    totalRow.innerHTML = '<td></td><td class="text-end fw-bold">' + totalsLabel + '</td><td class="fw-bold">' + fmtAmount(totalsSource.sum) + '</td><td></td><td></td><td class="fw-bold" style="color: #0056b3;">' + fmtAmount(totalsSource.sumILS) + ' ₪</td><td colspan="7"></td>';
    tbody.appendChild(totalRow);
  }
  // Event listener لحذف الدفعات
  document.addEventListener('click', async function (e) {
    const btn = e.target.closest('.btn-del');
    if (!btn) return;
    const id = btn.dataset.id;
    if (!id) return;
    if (!confirm('هل أنت متأكد من حذف سند الدفع #' + id + '؟')) return;
    const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || document.getElementById('csrf_token')?.value || '';
    try {
      const r = await fetch('/payments/' + id, {
        method: 'DELETE',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
        },
        body: new URLSearchParams({ csrf_token: csrf }).toString()
      });
      const j = await r.json().catch(() => ({}));
      if (r.ok && (j.status === 'success' || j.ok)) {
        loadPayments();
      } else {
        alert('تعذر الحذف: ' + (j.message || 'خطأ غير معروف'));
      }
    } catch (err) {
      alert('خطأ في الاتصال بالخادم.');
    }
  });

  // Event listener لأرشفة الدفعات
  document.addEventListener('click', async function (e) {
    const btn = e.target.closest('.btn-archive');
    if (!btn) return;
    const id = btn.dataset.id;
    if (!id) return;
    
    const reason = prompt('أدخل سبب أرشفة هذه الدفعة:');
    if (!reason) return;
    
    if (!confirm('هل أنت متأكد من أرشفة سند الدفع #' + id + '؟')) return;
    
    const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || document.getElementById('csrf_token')?.value || '';
    try {
      const r = await fetch('/payments/archive/' + id, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
        },
        body: new URLSearchParams({ 
          csrf_token: csrf,
          reason: reason
        }).toString()
      });
      const j = await r.json().catch(() => ({}));
      if (r.ok && (j.status === 'success' || j.ok)) {
        loadPayments();
        alert('تم أرشفة سند الدفع بنجاح');
      } else {
        alert('تعذر الأرشفة: ' + (j.message || 'خطأ غير معروف'));
      }
    } catch (err) {
      alert('خطأ في الاتصال بالخادم.');
    }
  });
  function renderPagination(totalPages, currentPage) {
    const ul = document.querySelector('#pagination');
    if (!ul) return;
    ul.innerHTML = '';
    totalPages = Math.max(1, totalPages || 1);
    currentPage = Math.min(Math.max(1, currentPage || 1), totalPages);
    function add(page, label, disabled, active, isEllipsis=false) {
      const li = document.createElement('li');
      li.className = 'page-item ' + (disabled ? 'disabled' : '') + ' ' + (active ? 'active' : '');
      li.innerHTML = '<a class="page-link' + (isEllipsis ? '' : '" data-page="' + page + '"') + '" href="#" ' + (isEllipsis ? 'tabindex="-1" aria-disabled="true"' : '') + '>' + label + '</a>';
      ul.appendChild(li);
    }
    add(currentPage - 1, 'السابق', currentPage <= 1, false);
    const windowSize = 2;
    const first = 1, last = totalPages;
    let start = Math.max(first, currentPage - windowSize);
    let end = Math.min(last, currentPage + windowSize);
    if (start > first) { add(first, '1', false, first === currentPage); if (start > first + 1) add(currentPage, '…', true, false, true); }
    for (let i = start; i <= end; i++) add(i, String(i), false, i === currentPage);
    if (end < last) { if (end < last - 1) add(currentPage, '…', true, false, true); add(last, String(last), false, last === currentPage); }
    add(currentPage + 1, 'التالي', currentPage >= totalPages, false);
    ul.querySelectorAll('.page-link[data-page]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        const page = parseInt(a.dataset.page, 10);
        if (!isNaN(page)) loadPayments(page);
      }, { passive: false });
    });
  }
  function renderTotals(totals) {
    const safe = totals || { total_incoming: 0, total_outgoing: 0, net_total: 0, grand_total: 0, total_paid: 0 };
    const incomingEl = document.getElementById('payments-total-incoming');
    if (incomingEl) incomingEl.textContent = fmtAmount(safe.total_incoming || 0);
    const outgoingEl = document.getElementById('payments-total-outgoing');
    if (outgoingEl) outgoingEl.textContent = fmtAmount(safe.total_outgoing || 0);
    const netEl = document.getElementById('payments-net-total');
    if (netEl) netEl.textContent = fmtAmount(safe.net_total || 0);
    const grandEl = document.getElementById('payments-grand-total');
    if (grandEl) grandEl.textContent = fmtAmount(safe.grand_total || 0);
  }
  function exportCsv() {
    try {
      const headers = Array.from(document.querySelectorAll('#paymentsTable thead th')).map(function (th) { return th.textContent.trim(); }).slice(0, 8);
      const rows = _lastList.map(function (p) {
        const dateOnly = (p.payment_date || '').split('T')[0] || '';
        const method = (p.splits && p.splits.length) ? p.splits.map(function (s) { return String((s.method || '')).toUpperCase() + ': ' + fmtAmount(s.amount); }).join(' | ') : (p.method || '');
        return [String(p.id || ''), dateOnly, fmtAmount(p.total_amount), String(p.currency || ''), method, (p.direction || ''), (AR_STATUS[p.status] || p.status || ''), String(deriveEntityLabel(p) || '')];
      });
      const csv = [headers].concat(rows).map(function (r) { return r.map(function (cell) { return '"' + String(cell).replace(/"/g, '""') + '"'; }).join(','); }).join('\n');
      const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const now = new Date();
      const ymd = '' + now.getFullYear() + String(now.getMonth() + 1).padStart(2, '0') + String(now.getDate()).padStart(2, '0');
      a.href = url;
      a.download = 'statement_' + (ctx.entity_type || 'ALL').toLowerCase() + '_' + (ctx.entity_id || 'all') + '_' + ymd + '.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('تعذر إنشاء CSV.');
    }
  }
  syncFiltersFromUrl();
  updateUrlQuery();
  loadPayments();
  window.addEventListener('popstate', function () { syncFiltersFromUrl(); loadPayments(1); });
});

// وظائف البحث الذكي - محسنة للأداء
function initSmartSearch() {
  // البحث عن جميع حقول البحث في الحقول الديناميكية
  const searchInputs = document.querySelectorAll('input[placeholder*="اكتب"], input[placeholder*="البحث"]');
  
  searchInputs.forEach(input => {
    // تحديد نوع الجهة من الـ placeholder أو الـ name
    let entityType = 'customer'; // افتراضي
    
    if (input.placeholder.includes('مورد') || input.placeholder.includes('تاجر')) {
      entityType = 'supplier';
    } else if (input.placeholder.includes('شريك')) {
      entityType = 'partner';
    } else if (input.placeholder.includes('عميل')) {
      entityType = 'customer';
    }
    
    if (!entityType) return;
    
    // تجنب إضافة event listeners متعددة
    if (input.hasAttribute('data-smart-search-initialized')) return;
    input.setAttribute('data-smart-search-initialized', 'true');
    
    let searchTimeout;
    let currentResults = [];
    let selectedIndex = -1;
    
    // إنشاء قائمة النتائج مرة واحدة فقط
    let resultsList = input.parentNode.querySelector('.smart-search-results');
    if (!resultsList) {
      resultsList = document.createElement('div');
      resultsList.className = 'smart-search-results position-absolute w-100 bg-white border shadow-lg rounded';
      resultsList.style.display = 'none';
      resultsList.style.zIndex = '1000';
      resultsList.style.maxHeight = '300px';
      resultsList.style.overflowY = 'auto';
      
      input.parentNode.style.position = 'relative';
      input.parentNode.appendChild(resultsList);
    }
    
    // وظيفة البحث
    function performSearch(query) {
      if (query.length < 1) {
        hideResults();
        return;
      }
      
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        fetch(`/payments/search-entities?type=${entityType}&q=${encodeURIComponent(query)}`)
          .then(response => response.json())
          .then(data => {
            currentResults = data;
            selectedIndex = -1;
            showResults(data);
          })
          .catch(error => {

            hideResults();
          });
      }, 300);
    }
    
    // عرض النتائج
    function showResults(results) {
      if (results.length === 0) {
        hideResults();
        return;
      }
      
      resultsList.innerHTML = results.map((result, index) => `
        <div class="smart-search-item p-2 border-bottom cursor-pointer" data-index="${index}">
          <div class="fw-bold">${result.display}</div>
          ${result.phone ? `<small class="text-muted">${result.phone}</small>` : ''}
        </div>
      `).join('');
      
      resultsList.style.display = 'block';
      
      // إضافة مستمعي الأحداث
      resultsList.querySelectorAll('.smart-search-item').forEach((item, index) => {
        item.addEventListener('click', () => selectResult(index));
        item.addEventListener('mouseenter', () => highlightItem(index));
      });
    }
    
    // إخفاء النتائج
    function hideResults() {
      resultsList.style.display = 'none';
      currentResults = [];
      selectedIndex = -1;
    }
    
    // تحديد نتيجة
    function selectResult(index) {
      if (index >= 0 && index < currentResults.length) {
        const result = currentResults[index];
        input.value = result.display;
        
        // تعيين معرف الجهة
        const entityIdField = input.parentNode.querySelector('input[type="hidden"]');
        if (entityIdField) {
          entityIdField.value = result.id;
        }
        
        hideResults();
      }
    }
    
    // تمييز عنصر
    function highlightItem(index) {
      resultsList.querySelectorAll('.smart-search-item').forEach((item, i) => {
        item.classList.toggle('bg-light', i === index);
      });
      selectedIndex = index;
    }
    
    // مستمعي الأحداث
    input.addEventListener('input', (e) => {
      performSearch(e.target.value);
    });
    
    input.addEventListener('focus', (e) => {
      if (currentResults.length > 0) {
        showResults(currentResults);
      }
    });
    
    input.addEventListener('blur', (e) => {
      // تأخير إخفاء النتائج للسماح بالنقر
      setTimeout(() => hideResults(), 200);
    });
    
    // التنقل بلوحة المفاتيح
    input.addEventListener('keydown', (e) => {
      if (resultsList.style.display === 'none') return;
      
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          selectedIndex = Math.min(selectedIndex + 1, currentResults.length - 1);
          highlightItem(selectedIndex);
          break;
        case 'ArrowUp':
          e.preventDefault();
          selectedIndex = Math.max(selectedIndex - 1, -1);
          if (selectedIndex >= 0) {
            highlightItem(selectedIndex);
          } else {
            resultsList.querySelectorAll('.smart-search-item').forEach(item => {
              item.classList.remove('bg-light');
            });
          }
          break;
        case 'Enter':
          e.preventDefault();
          if (selectedIndex >= 0) {
            selectResult(selectedIndex);
          }
          break;
        case 'Escape':
          e.preventDefault();
          hideResults();
          break;
      }
    });
  });
}

// إعادة تشغيل البحث عند تغيير نوع الجهة فقط
document.addEventListener('change', function(e) {
  if (e.target && e.target.name === 'entity_type') {
    smartSearchInitialized = false; // إعادة تعيين للسماح بإعادة التشغيل
    setTimeout(function() {
      initializeSmartSearchOnce();
    }, 200);
  }
});

// تم نقل استدعاء البحث الذكي إلى initializeSmartSearchOnce() في بداية الملف

// معالج أحداث أرشفة الدفعات
document.addEventListener('click', async function (e) {
  const btn = e.target.closest('.btn-archive');
  if (!btn) return;
  
  const id = btn.dataset.id;
  if (!id) return;
  
  const reason = prompt('أدخل سبب أرشفة هذه الدفعة:');
  if (!reason) return;
  
  try {
    const response = await fetch(`/payments/archive/${id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': document.getElementById('csrf_token').value
      },
      body: `reason=${encodeURIComponent(reason)}`
    });
    
    if (response.ok) {
      alert('تم أرشفة الدفعة بنجاح');
      loadPayments(1); // إعادة تحميل الجدول
    } else {
      alert('خطأ في أرشفة الدفعة');
    }
  } catch (error) {

    alert('خطأ في أرشفة الدفعة');
  }
});
