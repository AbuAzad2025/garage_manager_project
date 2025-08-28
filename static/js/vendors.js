(function () {
  function wireSimpleSearch(inputId, tableId, columnsSelectors) {
    var input = document.getElementById(inputId);
    var table = document.getElementById(tableId);
    if (!input || !table) return;
    input.addEventListener('input', function () {
      var q = (input.value || '').trim().toLowerCase();
      var rows = table.tBodies[0]?.rows || [];
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var hay = '';
        columnsSelectors.forEach(function (sel) {
          var el = row.querySelector(sel);
          if (el) hay += ' ' + (el.textContent || '').toLowerCase();
        });
        row.style.display = hay.indexOf(q) !== -1 ? '' : 'none';
      }
    });
  }

  var modalEl, bsModal;
  var dom = {};

  function initModalRefs() {
    modalEl = document.getElementById('settlementModal');
    if (!modalEl) return false;
    dom.stlName      = document.getElementById('stlName');
    dom.stlBalance   = document.getElementById('stlBalance');
    dom.stlAmount    = document.getElementById('stlAmount');
    dom.stlCurrency  = document.getElementById('stlCurrency');
    dom.stlMethod    = document.getElementById('stlMethod');
    dom.stlDirection = document.getElementById('stlDirectionBadge');
    dom.stlEntityId  = document.getElementById('stlEntityId');
    dom.stlEntityTyp = document.getElementById('stlEntityType');
    dom.stlConfirm   = document.getElementById('stlConfirm');
    dom.stlPrint     = document.getElementById('stlPrint');
    bsModal = window.bootstrap ? new window.bootstrap.Modal(modalEl) : null;
    return true;
  }

  function fmt(n) { return Number(n || 0).toFixed(2); }

  function directionBadge(dir) {
    if (dir === 'IN')  return '<span class="badge bg-success">وارد</span>';
    if (dir === 'OUT') return '<span class="badge bg-danger">صادر</span>';
    return '<span class="badge bg-secondary">—</span>';
  }

  function openSettlementModal(payload) {
    if (!modalEl) return;
    var balance = Number(payload.balance || 0);
    var amount = Math.abs(balance);

    dom.stlName.textContent = payload.name || '';
    dom.stlBalance.innerHTML = fmt(balance) + ' ' + (payload.currency || '');
    dom.stlAmount.value = fmt(amount);
    dom.stlCurrency.value = payload.currency || 'ILS';
    dom.stlEntityId.value = payload.id || '';
    dom.stlEntityTyp.value = payload.entityType || '';

    var dir = balance > 0 ? 'OUT' : (balance < 0 ? 'IN' : '');
    dom.stlDirection.innerHTML = directionBadge(dir);
    dom.stlConfirm.disabled = amount <= 0 || !dir;

    dom.stlConfirm.onclick = function () {
      var base = document.getElementById('vendors-config')?.dataset?.payUrl || '/payments/create';
      var amountVal = Math.max(0, Number(dom.stlAmount.value || 0));
      var methodVal = (dom.stlMethod.value || '').toLowerCase();
      if (!amountVal) return;
      var params = new URLSearchParams({
        entity_type: (payload.entityType || '').toUpperCase(),
        entity_id: String(payload.id || ''),
        direction: dir,
        total_amount: fmt(amountVal),
        currency: dom.stlCurrency.value || 'ILS',
        method: methodVal,
        reference: (payload.entityType === 'partner' ? 'Settlement' : 'Settlement')
      });
      window.location.href = base + '?' + params.toString();
    };

    dom.stlPrint.onclick = function () {
      var w = window.open('', 'printWin');
      var now = new Date().toLocaleString();
      var html = '<html dir="rtl"><head><meta charset="utf-8"><title>كشف مختصر</title><style>body{font-family:sans-serif;padding:20px}.row{margin:6px 0}.h{color:#666}</style></head><body><h3>كشف تسوية مختصر</h3><div class="row"><span class="h">الجهة:</span> '+(payload.name||'')+'</div><div class="row"><span class="h">النوع:</span> '+(payload.entityType==='partner'?'شريك':'مورد')+'</div><div class="row"><span class="h">الرصيد الحالي:</span> '+fmt(payload.balance)+' '+(payload.currency||'')+'</div><div class="row"><span class="h">المبلغ للتسوية:</span> '+fmt(dom.stlAmount.value)+' '+dom.stlCurrency.value+'</div><div class="row"><span class="h">الاتجاه:</span> '+dom.stlDirection.textContent+'</div><div class="row"><span class="h">الطريقة:</span> '+dom.stlMethod.options[dom.stlMethod.selectedIndex].text+'</div><hr><small>'+now+'</small><script>window.onload=function(){window.print();setTimeout(()=>window.close(),300)}</script></body></html>';
      w.document.write(html); w.document.close();
    };

    if (bsModal) bsModal.show();
    else modalEl.style.display = 'block';
  }

  function attachSettleButtons() {
    document.querySelectorAll('.btn-settle').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var payload = {
          entityType: btn.dataset.entityType,
          id:        btn.dataset.id,
          name:      btn.dataset.name,
          balance:   Number(btn.dataset.balance || 0),
          currency:  btn.dataset.currency || 'ILS'
        };
        openSettlementModal(payload);
      });
    });
    document.querySelectorAll('.btn-preview-partner-settlement').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var url = btn.dataset.previewUrl;
        if (!url) return;
        try {
          const res = await fetch(url, {headers: {'Accept':'application/json'}});
          const data = await res.json();
          if (!data.success) { alert(data.error || 'فشل المعاينة'); return; }
          alert('معاينة تسوية '+data.partner.name+'\nالفترة: '+data.from.substring(0,10)+' → '+data.to.substring(0,10)+'\nحصة الشريك: '+data.totals.share.toFixed(2)+' '+data.partner.currency+'\nالصافي: '+data.totals.due.toFixed(2)+' '+data.partner.currency);
        } catch(e) { console.error(e); alert('خطأ بالاتصال'); }
      });
    });
    document.querySelectorAll('.btn-preview-supplier-settlement').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var url = btn.dataset.previewUrl;
        if (!url) return;
        try {
          const res = await fetch(url, {headers: {'Accept':'application/json'}});
          const data = await res.json();
          if (!data.success) { alert(data.error || 'فشل المعاينة'); return; }
          alert('معاينة تسوية '+data.supplier.name+'\nالفترة: '+data.from.substring(0,10)+' → '+data.to.substring(0,10)+'\nإجمالي: '+data.totals.gross.toFixed(2)+' '+data.supplier.currency+'\nالصافي: '+data.totals.due.toFixed(2)+' '+data.supplier.currency);
        } catch(e) { console.error(e); alert('خطأ بالاتصال'); }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireSimpleSearch('partnerSearch',  'partnersTable',  ['.partner-name',  '.partner-phone']);
    wireSimpleSearch('supplierSearch', 'suppliersTable', ['.supplier-name', '.supplier-phone']);
    if (initModalRefs()) attachSettleButtons(); else attachSettleButtons();
  });
})();
