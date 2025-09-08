/* static/js/shipments.js */
document.addEventListener('DOMContentLoaded', function () {
  const $ = window.jQuery;

  function fmt2(n){ return (Number(n||0)).toFixed(2); }

  function reindex(container, prefix){
    if (!container) return;
    const all = container.querySelectorAll('[id^="'+prefix+'-"], [name^="'+prefix+'-"], label[for^="'+prefix+'-"]');
    const seen = new Map();
    let next = -1;
    all.forEach(function(el){
      const isLabel = el.tagName.toLowerCase()==='label';
      const attr = isLabel ? 'for' : (el.name ? 'name' : (el.id ? 'id' : null));
      if (!attr) return;
      const val = el.getAttribute(attr);
      const parts = val.split('-');
      if (parts.length < 3) return;
      const oldIdx = parts[1];
      if (!seen.has(oldIdx)){ next += 1; seen.set(oldIdx, String(next)); }
      parts[1] = seen.get(oldIdx);
      const updated = parts.join('-');
      el.setAttribute(attr, updated);
      if (!isLabel && attr==='name'){
        if (el.id){
          const idParts = el.id.split('-');
          if (idParts.length >= 3){ idParts[1] = parts[1]; el.id = idParts.join('-'); }
        }
      }
    });
    container.dataset.index = String(next + 1);
  }

  function initAjaxSelect2(root){
    if (!($ && $.fn.select2)) return;
    $(root).find('.select2-ajax').each(function(){
      const $el = $(this);
      if ($el.data('select2')) return;
      const url = $el.data('url');
      const placeholder = $el.data('placeholder') || 'اختر...';
      $el.select2({
        width:'100%',
        theme:'bootstrap4',
        placeholder: placeholder,
        ajax: {
          delay: 250,
          url: url,
          data: function(params){
            return { q: params.term || '', limit: 20 };
          },
          processResults: function(data){
            if (Array.isArray(data)) return { results: data };
            if (data.results) return { results: data.results };
            return { results: [] };
          },
          cache: true
        }
      });
    });
  }

  const itemsWrap = document.getElementById('items-wrapper');
  const addItemBtn = document.getElementById('add-item');
  const itemTpl = document.getElementById('item-row-template');

  const partnersWrap = document.getElementById('partners-wrapper');
  const addPartnerBtn = document.getElementById('add-partner');
  const partnerTpl = document.getElementById('partner-row-template');

  const itemsCountEl = document.getElementById('items-count');
  const itemsQtyEl   = document.getElementById('items-qty-sum');
  const itemsCostEl  = document.getElementById('items-cost-sum');

  const fldValueBefore = document.getElementById('value_before') || document.querySelector('[name="value_before"]');
  const fldTotalValue  = document.getElementById('total_value') || document.querySelector('[name="total_value"]');
  const fldShipping = document.getElementById('shipping_cost') || document.querySelector('[name="shipping_cost"]');
  const fldCustoms  = document.getElementById('customs') || document.querySelector('[name="customs"]');
  const fldVat      = document.getElementById('vat') || document.querySelector('[name="vat"]');
  const fldIns      = document.getElementById('insurance') || document.querySelector('[name="insurance"]');
  const fldDest     = document.getElementById('destination_id') || document.querySelector('[name="destination_id"]');

  function recalcItems(){
    if (!itemsWrap) return;
    const rows = itemsWrap.querySelectorAll('.shipment-item');
    let cnt=0, qty=0, total=0;
    rows.forEach(r=>{
      const q = parseFloat(r.querySelector('.item-qty')?.value||'0')||0;
      const c = parseFloat(r.querySelector('.item-cost')?.value||'0')||0;
      if (q>0){ cnt+=1; qty+=q; total+=q*c; }
    });
    if (itemsCountEl) itemsCountEl.textContent = String(cnt);
    if (itemsQtyEl) itemsQtyEl.textContent = String(qty);
    if (itemsCostEl) itemsCostEl.textContent = fmt2(total);
    if (fldValueBefore) fldValueBefore.value = fmt2(total);
    const extras = (parseFloat(fldShipping?.value||0)||0) + (parseFloat(fldCustoms?.value||0)||0) + (parseFloat(fldVat?.value||0)||0) + (parseFloat(fldIns?.value||0)||0);
    if (fldTotalValue) fldTotalValue.value = fmt2(total + extras);
  }

  function recalcTotalOnExtras(){
    const itemsTotal = parseFloat(itemsCostEl?.textContent||fldValueBefore?.value||0)||0;
    const extras = (parseFloat(fldShipping?.value||0)||0) + (parseFloat(fldCustoms?.value||0)||0) + (parseFloat(fldVat?.value||0)||0) + (parseFloat(fldIns?.value||0)||0);
    if (fldTotalValue) fldTotalValue.value = fmt2(itemsTotal + extras);
  }

  function setDefaultWarehouseForRow(row){
    const destVal = fldDest && ($(fldDest).val() || fldDest.value);
    const $w = $(row).find('[name$="-warehouse_id"]');
    if (destVal && $w.length){
      const opt = new Option($(fldDest).find('option:selected').text()||'المخزن', destVal, true, true);
      $w.append(opt).trigger('change');
    }
  }

  function addItemRow(prefill){
    if (!(itemTpl && itemsWrap)) return;
    const frag = document.importNode(itemTpl.content, true);
    itemsWrap.appendChild(frag);
    reindex(itemsWrap, 'items');
    initAjaxSelect2(itemsWrap);
    const last = itemsWrap.querySelector('.shipment-item:last-child');
    if (prefill && last){
      if (prefill.product){
        const $p = $(last).find('[name$="-product_id"]');
        const opt = new Option(prefill.product.text, prefill.product.id, true, true);
        $p.append(opt).trigger('change');
      }
      setDefaultWarehouseForRow(last);
      if (prefill.qty){ last.querySelector('.item-qty').value = prefill.qty; }
      if (prefill.cost != null){ last.querySelector('.item-cost').value = prefill.cost; }
    }
    recalcItems();
  }

  function addPartnerRow(){
    if (!(partnerTpl && partnersWrap)) return;
    const frag = document.importNode(partnerTpl.content, true);
    partnersWrap.appendChild(frag);
    reindex(partnersWrap, 'partners');
    initAjaxSelect2(partnersWrap);
  }

  if (addItemBtn) addItemBtn.addEventListener('click', function(){ addItemRow(); });
  if (itemsWrap){
    itemsWrap.addEventListener('click', function(e){
      const btn = e.target.closest('.btn-remove-item');
      if (btn){
        const row = btn.closest('.shipment-item');
        row?.remove();
        reindex(itemsWrap, 'items');
        recalcItems();
      }
    });
    itemsWrap.addEventListener('input', function(e){
      if (e.target.matches('.item-qty, .item-cost')) recalcItems();
    });
  }

  if (addPartnerBtn) addPartnerBtn.addEventListener('click', addPartnerRow);
  if (partnersWrap){
    partnersWrap.addEventListener('click', function(e){
      const btn = e.target.closest('.btn-remove-partner');
      if (btn){
        const row = btn.closest('.shipment-partner');
        row?.remove();
        reindex(partnersWrap, 'partners');
      }
    });
  }

  if (fldShipping) fldShipping.addEventListener('input', recalcTotalOnExtras);
  if (fldCustoms)  fldCustoms.addEventListener('input', recalcTotalOnExtras);
  if (fldVat)      fldVat.addEventListener('input', recalcTotalOnExtras);
  if (fldIns)      fldIns.addEventListener('input', recalcTotalOnExtras);
  if (fldDest){
    $(fldDest).on('change', function(){
      document.querySelectorAll('#items-wrapper .shipment-item').forEach(setDefaultWarehouseForRow);
    });
  }

  const barcodeInput = document.getElementById('barcode-input');
  if (barcodeInput){
    barcodeInput.addEventListener('keydown', function(e){
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const code = (barcodeInput.value || '').trim();
      if (!code) return;
      fetch(`/api/products/barcode/${encodeURIComponent(code)}`).then(r=>{
        if (!r.ok) throw new Error('nf');
        return r.json();
      }).then(p=>{
        addItemRow({ product: { id: p.id, text: p.name }, qty: 1, cost: '' });
        barcodeInput.value = '';
      }).catch(()=>{});
    });
  }

  initAjaxSelect2(document);
  recalcItems();

  if (window.flatpickr){
    const now = new Date();
    const opts = {enableTime:true, time_24hr:true, dateFormat:"Y-m-d H:i", altInput:true, altFormat:"d-m-Y H:i", locale: (window.flatpickr.l10ns && window.flatpickr.l10ns.ar) || undefined};
    const sd = document.getElementById('shipment_date') || document.querySelector('[name="shipment_date"]');
    const ea = document.getElementById('expected_arrival') || document.querySelector('[name="expected_arrival"]');
    const aa = document.getElementById('actual_arrival') || document.querySelector('[name="actual_arrival"]');
    if (sd) flatpickr(sd, Object.assign({}, opts, {defaultDate: sd.value || now}));
    if (ea) flatpickr(ea, Object.assign({}, opts, {defaultDate: ea.value || new Date(now.getTime()+14*24*60*60*1000)}));
    if (aa) flatpickr(aa, Object.assign({}, opts));
    document.querySelectorAll('.dt').forEach(function(el){
      flatpickr(el, {dateFormat:"Y-m-d", altInput:true, altFormat:"d-m-Y", locale: (window.flatpickr.l10ns && window.flatpickr.l10ns.ar) || undefined});
    });
  }

  if ($('#shipmentsTable').length){
    $('#shipmentsTable').DataTable({
      ajax: '/shipments/data',
      serverSide: true,
      processing: true,
      columns: [
        { data: 'id' },
        { data: 'number' },
        { data: 'destination' },
        { data: 'expected_arrival' },
        { data: 'status' },
        { data: 'total_value', className: 'text-end', render: d=> fmt2(d) },
        { data: 'id', className: 'text-center', render: d=> `
          <a href="/shipments/${d}" class="btn btn-sm btn-primary">عرض</a>
          <a href="/shipments/${d}/edit" class="btn btn-sm btn-warning">تعديل</a>
          <form method="POST" action="/shipments/${d}/delete" style="display:inline" onsubmit="return confirm('هل أنت متأكد من الحذف؟');">
            <button type="submit" class="btn btn-sm btn-danger">حذف</button>
          </form>` }
      ]
    });
  }
});
