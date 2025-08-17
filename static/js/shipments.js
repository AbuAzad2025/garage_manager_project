// File: static/js/shipments.js
document.addEventListener('DOMContentLoaded', function () {
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

  function replaceIndex(html, namePrefix, idx){
    return html.replaceAll(namePrefix + '-__prefix__-', namePrefix + '-' + idx + '-');
  }

  function addItemRow(){
    if (!window.__shipmentEmptyItem) return;
    var idx = document.querySelectorAll('#itemsContainer .item-entry').length;
    var tpl = document.getElementById('item-template').innerHTML;
    var product = replaceIndex(window.__shipmentEmptyItem.product, 'items', idx);
    var warehouse = replaceIndex(window.__shipmentEmptyItem.warehouse, 'items', idx);
    var quantity = replaceIndex(window.__shipmentEmptyItem.quantity, 'items', idx);
    var unit_cost = replaceIndex(window.__shipmentEmptyItem.unit_cost, 'items', idx);
    var declared_value = replaceIndex(window.__shipmentEmptyItem.declared_value, 'items', idx);
    tpl = tpl.replace('__product__', product)
             .replace('__warehouse__', warehouse)
             .replace('__quantity__', quantity)
             .replace('__unit_cost__', unit_cost)
             .replace('__declared_value__', declared_value);
    var wrap = document.createElement('div');
    wrap.innerHTML = tpl.trim();
    document.getElementById('itemsContainer').appendChild(wrap.firstChild);
  }

  function addPartnerRow(){
    if (!window.__shipmentEmptyPartner) return;
    var idx = document.querySelectorAll('#partnersContainer .partner-entry').length;
    var tpl = document.getElementById('partner-template').innerHTML;
    var map = window.__shipmentEmptyPartner;
    var html = tpl.replace('__partner_id__',  replaceIndex(map.partner_id, 'partner_links', idx))
                  .replace('__share_percentage__', replaceIndex(map.share_percentage, 'partner_links', idx))
                  .replace('__share_amount__', replaceIndex(map.share_amount, 'partner_links', idx))
                  .replace('__unit_price_before_tax__', replaceIndex(map.unit_price_before_tax, 'partner_links', idx))
                  .replace('__expiry_date__', replaceIndex(map.expiry_date, 'partner_links', idx))
                  .replace('__identity_number__', replaceIndex(map.identity_number, 'partner_links', idx))
                  .replace('__phone_number__', replaceIndex(map.phone_number, 'partner_links', idx))
                  .replace('__address__', replaceIndex(map.address, 'partner_links', idx))
                  .replace('__notes__', replaceIndex(map.notes, 'partner_links', idx));
    var wrap = document.createElement('div');
    wrap.innerHTML = html.trim();
    document.getElementById('partnersContainer').appendChild(wrap.firstChild);
  }

  var addItemBtn = document.getElementById('addItem');
  if (addItemBtn) addItemBtn.addEventListener('click', function(e){ e.preventDefault(); addItemRow(); });

  var addPartnerBtn = document.getElementById('addPartner');
  if (addPartnerBtn) addPartnerBtn.addEventListener('click', function(e){ e.preventDefault(); addPartnerRow(); });

  document.addEventListener('click', function(e){
    if (e.target.classList.contains('remove-item')) {
      var row = e.target.closest('.item-entry');
      if (row && document.querySelectorAll('#itemsContainer .item-entry').length > 1) row.remove();
    }
    if (e.target.classList.contains('remove-partner')) {
      var row2 = e.target.closest('.partner-entry');
      if (row2 && document.querySelectorAll('#partnersContainer .partner-entry').length > 1) row2.remove();
    }
  });
});
