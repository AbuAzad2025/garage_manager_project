// File: static/js/shipments.js
document.addEventListener('DOMContentLoaded', function () {
  // ===================== Shipments table (index) =====================
  (function initTable(){
    var tbl = document.getElementById('shipmentsTable');
    if (!tbl || !window.jQuery || !$.fn.DataTable) return;
    $('#shipmentsTable').DataTable({
      processing: true,
      serverSide: true,
      ajax: {
        url: window.location.pathname,
        data: function (d) { d.format = 'json'; }
      },
      columns: [
        { data: null, render: function(data, type, row, meta){ return meta.row + 1; }, orderable: false },
        { data: 'number' },
        { data: 'expected_arrival', render: function(v){ return v ? v.substring(0,10) : ''; } },
        { data: 'status' },
        { data: 'total_value', render: function(v){ return (v||0).toFixed(2); } },
        { data: 'id', orderable: false, render: function(id){
            return '<a href="/shipments/'+id+'" class="btn btn-sm btn-info"><i class="fas fa-eye"></i></a> '+
                   '<a href="/shipments/'+id+'/edit" class="btn btn-sm btn-primary"><i class="fas fa-edit"></i></a>';
          } }
      ],
      order: [[2,'desc']],
      language: { url: "//cdn.datatables.net/plug-ins/1.13.6/i18n/ar.json" }
    });
  })();

  // ===================== Form helpers (create/edit) =====================
  const itemsWrap     = document.getElementById('items-wrapper');
  const addItemBtn    = document.getElementById('add-item');
  const itemTpl       = document.getElementById('item-row-template');

  const partnersWrap  = document.getElementById('partners-wrapper');
  const addPartnerBtn = document.getElementById('add-partner');
  const partnerTpl    = document.getElementById('partner-row-template');

  function reindex(container, prefix){
    if (!container) return;
    const rows = container.querySelectorAll('[name^="'+prefix+'-"]');
    const seen = new Map();
    let idx = -1;
    rows.forEach((el) => {
      const parts = el.name.split('-');
      if (parts.length >= 3) {
        const oldIdx = parts[1];
        if (!seen.has(oldIdx)) {
          idx += 1;
          seen.set(oldIdx, String(idx));
        }
        parts[1] = seen.get(oldIdx);
        el.name = parts.join('-');
      }
      if (el.id) {
        const idParts = el.id.split('-');
        if (idParts.length >= 3 && seen.has(idParts[1])) {
          idParts[1] = seen.get(idParts[1]);
          el.id = idParts.join('-');
        }
      }
    });
    container.dataset.index = String(idx + 1);
  }

  function initSelect2Within(el){
    if (window.jQuery && jQuery.fn.select2){
      jQuery(el).find('.select2').each(function(){
        const $el = jQuery(this);
        const endpoint = this.dataset.endpoint;
        if (endpoint){
          $el.select2({
            width: '100%',
            placeholder: 'اختر...',
            allowClear: true,
            ajax: {
              delay: 250,
              url: endpoint,
              data: params => ({ q: params.term || '', limit: 20 }),
              processResults: (data) => {
                const arr = Array.isArray(data) ? data : (data.results || data.data || []);
                return { results: arr.map(x => ({ id: x.id, text: x.text || x.name || String(x.id) })) };
              }
            }
          });
        } else {
          $el.select2({ width: '100%' });
        }
      });
    }
  }

  // sums
  const itemsCountEl = document.getElementById('items-count');
  const itemsQtyEl   = document.getElementById('items-qty-sum');
  const itemsCostEl  = document.getElementById('items-cost-sum');
  function recalcItems(){
    if (!itemsWrap) return;
    let rows = itemsWrap.querySelectorAll('.shipment-item, .item-row');
    let cnt = 0, qtySum = 0, costSum = 0;
    rows.forEach(r => {
      const qty  = parseFloat((r.querySelector('.item-qty')?.value || r.querySelector('input[name*="quantity"]')?.value) || '0') || 0;
      const cost = parseFloat((r.querySelector('.item-cost')?.value || r.querySelector('input[name*="unit_cost"]')?.value) || '0') || 0;
      if (qty > 0) { cnt += 1; qtySum += qty; costSum += (qty * cost); }
    });
    if (itemsCountEl) itemsCountEl.textContent = String(cnt);
    if (itemsQtyEl)   itemsQtyEl.textContent   = String(qtySum);
    if (itemsCostEl)  itemsCostEl.textContent  = costSum.toFixed(2);
  }

  // add/remove item
  if (addItemBtn && itemTpl && itemsWrap){
    addItemBtn.addEventListener('click', () => {
      const clone = document.importNode(itemTpl.content, true);
      itemsWrap.appendChild(clone);
      reindex(itemsWrap, 'items');
      initSelect2Within(itemsWrap.lastElementChild);
      recalcItems();
    });
    itemsWrap.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn-remove-item, .remove-item');
      if (btn){
        const row = btn.closest('.shipment-item, .item-row');
        if (row){ row.remove(); reindex(itemsWrap, 'items'); recalcItems(); }
      }
    });
    // change listeners for recalc
    itemsWrap.addEventListener('input', (e) => {
      if (e.target.matches('.item-qty, .item-cost, input[name*="quantity"], input[name*="unit_cost"]')) {
        recalcItems();
      }
    });
    recalcItems();
  }

  // add/remove partner
  if (addPartnerBtn && partnerTpl && partnersWrap){
    addPartnerBtn.addEventListener('click', () => {
      const clone = document.importNode(partnerTpl.content, true);
      partnersWrap.appendChild(clone);
      reindex(partnersWrap, 'partners');
      initSelect2Within(partnersWrap.lastElementChild);
    });
    partnersWrap.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn-remove-partner, .remove-partner');
      if (btn){
        const row = btn.closest('.shipment-partner, .partner-row');
        if (row){ row.remove(); reindex(partnersWrap, 'partners'); }
      }
    });
  }

  // init select2 for already rendered rows
  initSelect2Within(document);
});
