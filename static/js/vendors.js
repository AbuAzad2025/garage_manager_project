(function () {
  function fmt(n) {
    return Number(n || 0).toFixed(2);
  }

  function directionBadge(dir) {
    if (dir === 'IN') return '<span class="badge bg-success">وارد</span>';
    if (dir === 'OUT') return '<span class="badge bg-danger">صادر</span>';
    return '<span class="badge bg-secondary">—</span>';
  }

  function openSettlementModal(payload) {
    const modalEl = document.getElementById('settlementModal');
    if (!modalEl) return;

    const bsModal = window.bootstrap ? new bootstrap.Modal(modalEl) : null;
    const dom = {
      name:         document.getElementById('stlName'),
      balance:      document.getElementById('stlBalance'),
      amount:       document.getElementById('stlAmount'),
      currency:     document.getElementById('stlCurrency'),
      method:       document.getElementById('stlMethod'),
      direction:    document.getElementById('stlDirectionBadge'),
      entityId:     document.getElementById('stlEntityId'),
      entityType:   document.getElementById('stlEntityType'),
      confirm:      document.getElementById('stlConfirm'),
      print:        document.getElementById('stlPrint')
    };

    const balance = Number(payload.balance || 0);
    const amount = Math.abs(balance);
    const dir = balance > 0 ? 'OUT' : (balance < 0 ? 'IN' : 'OUT');

    dom.name.textContent = payload.name || '';
    dom.balance.innerHTML = fmt(balance) + ' ' + (payload.currency || '');
    dom.amount.value = fmt(amount);
    dom.currency.value = (payload.currency || 'ILS').toUpperCase();
    dom.entityId.value = payload.id || '';
    dom.entityType.value = (payload.entityType || '').toUpperCase();
    dom.direction.innerHTML = directionBadge(dir);
    dom.confirm.disabled = (amount <= 0);

    dom.confirm.onclick = function () {
      const base = document.getElementById('vendors-config')?.dataset?.payUrl || '/payments/create';
      const amountVal = Math.max(0, Number(dom.amount.value || 0));
      if (!amountVal) return;
      const params = new URLSearchParams({
        entity_type: dom.entityType.value,
        entity_id: dom.entityId.value,
        direction: dir,
        total_amount: fmt(amountVal),
        currency: dom.currency.value,
        method: (dom.method.value || 'cash').toLowerCase(),
        reference: dom.entityType.value === 'SUPPLIER' ? 'SupplierSettle' : 'Settlement'
      });
      window.location.href = base + '?' + params.toString();
    };

    dom.print.onclick = function () {
      const w = window.open('', 'printWin');
      const now = new Date().toLocaleString();
      const methodText = dom.method.options[dom.method.selectedIndex].text;
      const dirText = dir === 'IN' ? 'وارد' : 'صادر';
      const html = `
        <html dir="rtl"><head><meta charset="utf-8"><title>كشف تسوية</title>
        <style>body{font-family:sans-serif;padding:20px} .row{margin:6px 0} .h{color:#666}</style>
        </head><body>
        <h3>كشف تسوية مختصر</h3>
        <div class="row"><span class="h">الجهة:</span> ${payload.name || ''}</div>
        <div class="row"><span class="h">النوع:</span> ${dom.entityType.value === 'PARTNER' ? 'شريك' : 'مورد'}</div>
        <div class="row"><span class="h">الرصيد الحالي:</span> ${fmt(payload.balance)} ${payload.currency || ''}</div>
        <div class="row"><span class="h">المبلغ للتسوية:</span> ${fmt(dom.amount.value)} ${dom.currency.value}</div>
        <div class="row"><span class="h">الاتجاه:</span> ${dirText}</div>
        <div class="row"><span class="h">الطريقة:</span> ${methodText}</div>
        <hr><small>${now}</small>
        <script>window.onload=function(){window.print();setTimeout(function(){window.close()},300)}</script>
        </body></html>`;
      w.document.write(html);
      w.document.close();
    };

    if (bsModal) bsModal.show();
    else modalEl.style.display = 'block';
  }

  function attachSettleButtons() {
    document.querySelectorAll('.btn-settle').forEach(function (btn) {
      btn.addEventListener('click', function () {
        openSettlementModal({
          entityType: btn.dataset.entityType,
          id: btn.dataset.id,
          name: btn.dataset.name,
          balance: Number(btn.dataset.balance || 0),
          currency: btn.dataset.currency || 'ILS'
        });
      });
    });
  }

  function wireSimpleSearch(inputId, tableId, selectors) {
    const input = document.getElementById(inputId);
    const table = document.getElementById(tableId);
    if (!input || !table) return;
    input.addEventListener('input', function () {
      const q = input.value.trim().toLowerCase();
      Array.from(table.tBodies[0].rows).forEach(function (row) {
        const haystack = selectors.map(sel => (row.querySelector(sel)?.textContent || '').toLowerCase()).join(' ');
        row.style.display = haystack.includes(q) ? '' : 'none';
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireSimpleSearch('partnerSearch', 'partnersTable', ['.partner-name', '.partner-phone']);
    wireSimpleSearch('supplierSearch', 'suppliersTable', ['.supplier-name', '.supplier-phone']);
    attachSettleButtons();
  });
})();
