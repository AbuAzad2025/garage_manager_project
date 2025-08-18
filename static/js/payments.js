// File: static/js/payments.js
document.addEventListener('DOMContentLoaded', function () {
  const filterSelectors = [
    '#filterEntity', '#filterStatus', '#filterDirection',
    '#filterMethod', '#startDate', '#endDate'
  ];

  const ENTITY_ENUM = {
    customer: 'CUSTOMER',
    supplier: 'SUPPLIER',
    partner:  'PARTNER',
    sale:     'SALE',
    service:  'SERVICE',
    expense:  'EXPENSE',
    loan:     'LOAN',
    preorder: 'PREORDER',
    shipment: 'SHIPMENT'
  };

  const AR_STATUS = {
    COMPLETED: 'مكتملة',
    PENDING:   'قيد الانتظار',
    FAILED:    'فاشلة',
    REFUNDED:  'مُرجعة'
  };

  function inferEntityContext() {
    const path = location.pathname.replace(/\/+$/, '');
    const m = path.match(/^\/vendors\/(suppliers|partners)\/(\d+)\/payments$/i);
    if (m) {
      const kind = m[1].toLowerCase() === 'suppliers' ? 'SUPPLIER' : 'PARTNER';
      return { entity_type: kind, entity_id: m[2] };
    }
    const qs = new URLSearchParams(location.search);
    const et = (qs.get('entity_type') || '').toLowerCase();
    const ei = qs.get('entity_id') || '';
    return { entity_type: ENTITY_ENUM[et] || '', entity_id: ei || '' };
  }

  const ctx = inferEntityContext();

  const entSel = document.querySelector('#filterEntity');
  if (entSel && ctx.entity_type) {
    entSel.value = ctx.entity_type;
    entSel.disabled = true;
  }

  function injectStatementButtons() {
    if (!ctx.entity_type || !ctx.entity_id) return;
    const filtersRow = document.querySelector('.row.mb-4.g-2.align-items-end') || document.querySelector('.row.mb-4');
    if (!filtersRow || document.getElementById('btnExportCsv')) return;

    const wrap = document.createElement('div');
    wrap.className = 'col-auto d-flex gap-2';
    wrap.innerHTML = `
      <button id="btnPrint" class="btn btn-outline-secondary">
        <i class="fas fa-print me-1"></i> طباعة كشف
      </button>
      <button id="btnExportCsv" class="btn btn-outline-success">
        <i class="fas fa-file-csv me-1"></i> تصدير CSV
      </button>
    `;
    filtersRow.appendChild(wrap);

    document.getElementById('btnPrint').addEventListener('click', printStatement);
    document.getElementById('btnExportCsv').addEventListener('click', exportCsv);
  }
  injectStatementButtons();

  filterSelectors.forEach(sel => {
    const el = document.querySelector(sel);
    if (el) el.addEventListener('change', () => {
      updateUrlQuery();
      loadPayments(1);
    });
  });

  function normalizeEntity(val) {
    if (!val) return '';
    const k = val.toString().toLowerCase();
    return ENTITY_ENUM[k] || val.toString().toUpperCase();
  }

  function normDir(v) {
    v = (v || '').toUpperCase();
    if (v === 'IN') return 'INCOMING';
    if (v === 'OUT') return 'OUTGOING';
    return v;
  }

  function currentFilters(page = 1) {
    const raw = {
      entity_type: normalizeEntity(document.querySelector('#filterEntity')?.value || ctx.entity_type || ''),
      status:      document.querySelector('#filterStatus')?.value || '',
      direction:   normDir(document.querySelector('#filterDirection')?.value || ''),
      method:      document.querySelector('#filterMethod')?.value || '',
      start_date:  document.querySelector('#startDate')?.value || '',
      end_date:    document.querySelector('#endDate')?.value || '',
      page
    };
    if (ctx.entity_id) raw.entity_id = ctx.entity_id;
    return raw;
  }

  function updateUrlQuery() {
    const raw = currentFilters();
    const params = new URLSearchParams();
    Object.entries(raw).forEach(([k, v]) => {
      if (v && k !== 'page') params.append(k, v);
    });
    history.replaceState(null, '', location.pathname + (params.toString() ? ('?' + params.toString()) : ''));
  }

  function loadPayments(page = 1) {
    const raw = currentFilters(page);
    const params = new URLSearchParams();
    Object.entries(raw).forEach(([k, v]) => { if (v) params.append(k, v); });

    setLoading(true);
    fetch(`/payments/?${params.toString()}`, { headers: { 'Accept': 'application/json' } })
      .then(r => r.json())
      .then(data => {
        const list = data.payments || [];
        renderPaymentsTable(list);
        renderPagination(data.total_pages || 1, data.current_page || 1);
      })
      .catch(() => {
        renderPaymentsTable([]);
        renderPagination(1, 1);
      })
      .finally(() => setLoading(false));
  }

  function setLoading(is) {
    const tbody = document.querySelector('#paymentsTable tbody');
    if (!tbody) return;
    if (is) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="text-center text-muted py-4">
            <div class="spinner-border spinner-border-sm me-2"></div>
            جارِ التحميل…
          </td>
        </tr>`;
    }
  }

  function badgeForDirection(dir) {
    const v = (dir || '').toUpperCase();
    return (v === 'IN' || v === 'INCOMING')
      ? '<span class="badge bg-success">وارد</span>'
      : '<span class="badge bg-danger">صادر</span>';
  }

  function badgeForStatus(st) {
    const cls = st === 'COMPLETED' ? 'bg-success'
      : st === 'PENDING'   ? 'bg-warning text-dark'
      : st === 'FAILED'    ? 'bg-danger'
      : 'bg-secondary';
    const txt = AR_STATUS[st] || st;
    return `<span class="badge ${cls}">${txt}</span>`;
  }

  let _lastList = [];

  function renderPaymentsTable(list) {
    _lastList = list.slice();
    const tbody = document.querySelector('#paymentsTable tbody');
    tbody.innerHTML = '';

    if (!list.length) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="9" class="text-center text-muted py-4">لا توجد بيانات</td>`;
      tbody.appendChild(tr);
      return;
    }

    list.forEach(p => {
      const splitsHtml = (p.splits || []).map(s =>
        `<span class="badge bg-secondary me-1">${(s.method || '').toUpperCase()}: ${Number(s.amount || 0).toFixed(2)} ${p.currency || ''}</span>`
      ).join(' ');

      const dateOnly = (p.payment_date || '').split('T')[0] || '';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${p.id}</td>
        <td>${dateOnly}</td>
        <td>${Number(p.total_amount || 0).toFixed(2)}</td>
        <td>${p.currency || ''}</td>
        <td>${splitsHtml || (p.method || '')}</td>
        <td>${badgeForDirection(p.direction)}</td>
        <td>${badgeForStatus(p.status)}</td>
        <td>${p.entity_display || p.entity_type || ''}</td>
        <td><a href="/payments/${p.id}" class="btn btn-info btn-sm">عرض</a></td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderPagination(totalPages, currentPage) {
    const ul = document.querySelector('#pagination');
    if (!ul) return;
    ul.innerHTML = '';

    const add = (page, label, disabled = false, active = false) => {
      const li = document.createElement('li');
      li.className = `page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}`;
      li.innerHTML = `<a class="page-link" href="#" data-page="${page}">${label}</a>`;
      ul.appendChild(li);
    };

    add(currentPage - 1, 'السابق', currentPage <= 1, false);
    for (let i = 1; i <= totalPages; i++) add(i, i, false, i === currentPage);
    add(currentPage + 1, 'التالي', currentPage >= totalPages, false);

    ul.querySelectorAll('.page-link').forEach(a => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        const page = parseInt(a.dataset.page, 10);
        if (!isNaN(page)) loadPayments(page);
      });
    });
  }

  function printStatement() {
    try {
      const table = document.getElementById('paymentsTable');
      const htmlTable = table.outerHTML;
      const w = window.open('', 'stmt');
      const title = `كشف حساب - ${ctx.entity_type || ''} #${ctx.entity_id || ''}`;
      w.document.write(`
        <html dir="rtl" lang="ar">
          <head>
            <meta charset="utf-8">
            <title>${title}</title>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
            <style>body{padding:24px}h3{margin-bottom:16px}table{font-size:12px}</style>
          </head>
          <body>
            <h3>${title}</h3>
            ${htmlTable}
            <script>window.onload = function(){ window.print(); }</script>
          </body>
        </html>
      `);
      w.document.close();
    } catch (e) {
      console.error(e);
      alert('تعذر الطباعة الآن.');
    }
  }

  function exportCsv() {
    try {
      const table = document.getElementById('paymentsTable');
      const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim());
      const rows = Array.from(table.querySelectorAll('tbody tr'))
        .filter(tr => tr.offsetParent !== null)
        .map(tr => Array.from(tr.children).slice(0, 8).map(td => (td.innerText || '').replace(/\s+/g, ' ').trim()));

      const csv = [headers.slice(0, 8)]
        .concat(rows)
        .map(r => r.map(cell => `"${cell.replace(/"/g, '""')}"`).join(','))
        .join('\n');

      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const now = new Date();
      const ymd = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}`;
      a.href = url;
      a.download = `statement_${(ctx.entity_type || 'ALL').toLowerCase()}_${ctx.entity_id || 'all'}_${ymd}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert('تعذر إنشاء CSV.');
    }
  }

  updateUrlQuery();
  loadPayments();
});
