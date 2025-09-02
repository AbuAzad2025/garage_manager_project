document.addEventListener('DOMContentLoaded', function () {
  const $ = window.jQuery;

  function fmtCurrency(v) {
    const n = Number(v || 0);
    return n.toFixed(2);
  }

  function statusBadge(st) {
    const map = { DRAFT: 'secondary', IN_TRANSIT: 'warning', ARRIVED: 'success', CANCELLED: 'dark' };
    const cls = map[st] || 'info';
    return '<span class="badge bg-' + cls + '">' + (st || '-') + '</span>';
  }

  function rowClass(st) {
    if (st === 'ARRIVED') return 'table-success';
    if (st === 'CANCELLED') return 'table-secondary';
    if (st === 'IN_TRANSIT') return 'table-warning';
    return '';
  }

  (function initTable(){
    const tbl = document.getElementById('shipmentsTable');
    if (!tbl || !window.jQuery || !$.fn.DataTable) return;

    const dt = $('#shipmentsTable').DataTable({
      processing: true,
      serverSide: true,
      stateSave: true,
      ajax: {
        url: '/shipments/data',
        type: 'GET',
        data: function (d) {
          const f = document.getElementById('shipmentsFilters');
          if (f) {
            d.status = f.querySelector('#fStatus')?.value || '';
            d.from   = f.querySelector('#fFrom')?.value || '';
            d.to     = f.querySelector('#fTo')?.value || '';
            d.destination = f.querySelector('#fDestination')?.value || '';
            d.search_extra = f.querySelector('#fSearch')?.value || '';
          }
        }
      },
      columns: [
        { data: null, orderable: false, searchable: false, render: function(data, type, row, meta){ return meta.row + meta.settings._iDisplayStart + 1; } },
        { data: 'number' },
        { data: 'destination', defaultContent: '-' },
        { data: 'expected_arrival', render: function(v){ return v ? String(v).slice(0,10) : '-'; } },
        { data: 'status', render: function(v){ return statusBadge(v); } },
        { data: 'total_value', render: function(v){ return fmtCurrency(v); }, className: 'text-end' },
        { data: 'id', orderable: false, searchable: false, className: 'text-center',
          render: function(id){
            return '<a href="/shipments/'+id+'" class="btn btn-sm btn-outline-info" title="عرض"><i class="fa fa-eye"></i></a> '+
                   '<a href="/shipments/'+id+'/edit" class="btn btn-sm btn-outline-secondary" title="تعديل"><i class="fa fa-pencil-alt"></i></a>';
          }
        }
      ],
      createdRow: function (row, data) { const cls = rowClass(data.status); if (cls) row.classList.add(cls); },
      order: [[3,'desc']],
      language: { url: "https://cdn.datatables.net/plug-ins/1.13.6/i18n/ar.json" },
      autoWidth: false,
      responsive: true,
      lengthMenu: [10,25,50,100],
      dom: 'Bfrtip',
      buttons: [
        { extend: 'csv', text: 'CSV' },
        { extend: 'excel', text: 'Excel' },
        { extend: 'print', text: 'طباعة' }
      ]
    });

    const filters = document.getElementById('shipmentsFilters');
    if (filters) filters.addEventListener('input', function(){ dt.ajax.reload(); });
  })();

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
    rows.forEach(function(el){
      const parts = el.name.split('-');
      if (parts.length >= 3) {
        const oldIdx = parts[1];
        if (!seen.has(oldIdx)) { idx += 1; seen.set(oldIdx, String(idx)); }
        parts[1] = seen.get(oldIdx);
        el.name = parts.join('-');
      }
      if (el.id) {
        const idParts = el.id.split('-');
        if (idParts.length >= 3 && seen.has(idParts[1])) { idParts[1] = seen.get(idParts[1]); el.id = idParts.join('-'); }
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
          $el.val(null).trigger('change');
          $el.select2({
            width: '100%',
            placeholder: 'اختر...',
            allowClear: true,
            ajax: {
              delay: 250,
              url: endpoint,
              data: function(params){ return { q: params.term || '', limit: 20 }; },
              processResults: function(data){
                const arr = Array.isArray(data) ? data : (data.results || data.data || []);
                return { results: arr.map(function(x){ return { id: x.id, text: x.text || x.name || String(x.id) }; }) };
              }
            }
          });
        } else {
          $el.select2({ width: '100%' });
        }
      });
    }
  }

  const itemsCountEl = document.getElementById('items-count');
  const itemsQtyEl   = document.getElementById('items-qty-sum');
  const itemsCostEl  = document.getElementById('items-cost-sum');

  function recalcItems(){
    if (!itemsWrap) return;
    const rows = itemsWrap.querySelectorAll('.shipment-item, .item-row');
    let cnt = 0, qtySum = 0, costSum = 0;
    rows.forEach(function(r){
      const qty  = parseFloat((r.querySelector('.item-qty')?.value || r.querySelector('input[name*="quantity"]')?.value) || '0') || 0;
      const cost = parseFloat((r.querySelector('.item-cost')?.value || r.querySelector('input[name*="unit_cost"]')?.value) || '0') || 0;
      if (qty > 0) { cnt += 1; qtySum += qty; costSum += (qty * cost); }
    });
    if (itemsCountEl) itemsCountEl.textContent = String(cnt);
    if (itemsQtyEl)   itemsQtyEl.textContent   = String(qtySum);
    if (itemsCostEl)  itemsCostEl.textContent  = Number(costSum).toFixed(2);
  }

  if (addItemBtn && itemTpl && itemsWrap){
    addItemBtn.addEventListener('click', function(){
      const clone = document.importNode(itemTpl.content, true);
      itemsWrap.appendChild(clone);
      reindex(itemsWrap, 'items');
      initSelect2Within(itemsWrap.lastElementChild);
      recalcItems();
    });
    itemsWrap.addEventListener('click', function(e){
      const btn = e.target.closest('.btn-remove-item, .remove-item');
      if (btn){
        const row = btn.closest('.shipment-item, .item-row');
        if (row){ row.remove(); reindex(itemsWrap, 'items'); recalcItems(); }
      }
    });
    itemsWrap.addEventListener('input', function(e){
      if (e.target.matches('.item-qty, .item-cost, input[name*="quantity"], input[name*="unit_cost"]')) { recalcItems(); }
    });
    recalcItems();
  }

  if (addPartnerBtn && partnerTpl && partnersWrap){
    addPartnerBtn.addEventListener('click', function(){
      const clone = document.importNode(partnerTpl.content, true);
      partnersWrap.appendChild(clone);
      reindex(partnersWrap, 'partners');
      initSelect2Within(partnersWrap.lastElementChild);
    });
    partnersWrap.addEventListener('click', function(e){
      const btn = e.target.closest('.btn-remove-partner, .remove-partner');
      if (btn){
        const row = btn.closest('.shipment-partner, .partner-row');
        if (row){ row.remove(); reindex(partnersWrap, 'partners'); }
      }
    });
  }

  initSelect2Within(document);
});
