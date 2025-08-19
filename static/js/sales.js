/* File: static/js/sales.js */
(() => {
  'use strict';

  const qs=(s,el=document)=>el.querySelector(s);
  const qsa=(s,el=document)=>Array.from(el.querySelectorAll(s));
  const on=(el,ev,cb)=>el&&el.addEventListener(ev,cb,{passive:false});
  const toNum=v=>{const n=parseFloat((v??'').toString().replace(/[^\d.-]/g,''));return Number.isFinite(n)?n:0;};

  function loadScriptOnce(src){
    return new Promise(res=>{
      if(document.querySelector(`script[src="${src}"]`)) return res();
      const s=document.createElement('script'); s.src=src; s.onload=res; document.head.appendChild(s);
    });
  }
  function loadCssOnce(href){
    if(!document.querySelector(`link[href="${href}"]`)){
      const l=document.createElement('link'); l.rel='stylesheet'; l.href=href; document.head.appendChild(l);
    }
  }
  function loadJQueryOnce(){
    return new Promise(res=>{
      if(window.jQuery) return res();
      const s=document.createElement('script');
      s.src='https://cdn.jsdelivr.net/npm/jquery@3.6.4/dist/jquery.min.js';
      s.onload=()=>res();
      document.head.appendChild(s);
    });
  }

  // ============ صفحة القائمة ============
  (function initList(){
    const form = qs('#filterForm');
    if(!form) return;
    on(form,'submit', e=>{
      e.preventDefault();
      const params = new URLSearchParams(new FormData(form));
      const action = form.getAttribute('action') || window.location.pathname;
      window.location = action + '?' + params.toString();
    });
    const resetBtn = form.querySelector('button[type="reset"]');
    if(resetBtn) on(resetBtn,'click',e=>{
      e.preventDefault();
      const action = form.getAttribute('action') || window.location.pathname;
      window.location = action;
    });
  })();

  // ============ صفحة النموذج ============
  (function initForm(){
    const form = qs('#saleForm');
    if(!form) return;

    // تحميل Select2 (و jQuery عند الحاجة)
    const wantsSelect2 = !!document.querySelector('#saleForm .select2');
    const select2Ready = wantsSelect2
      ? loadJQueryOnce()
          .then(()=>loadCssOnce('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css'))
          .then(()=>loadCssOnce('https://cdn.jsdelivr.net/npm/@ttskch/select2-bootstrap4-theme@1.5.2/dist/select2-bootstrap4.min.css'))
          .then(()=>loadScriptOnce('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js'))
      : Promise.resolve();

    // Sortable (للسحب وإعادة الترتيب)
    loadScriptOnce('https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js').then(()=>{
      const cont = qs('#saleLines');
      if(cont && window.Sortable){
        new window.Sortable(cont,{handle:'.drag-handle',animation:150,ghostClass:'sortable-ghost'});
      }
    });

    const wrap = qs('#saleLines');
    const addBtn = qs('#addLine');

    function currentMaxIndex(){
      let max=-1;
      qsa('.sale-line',wrap).forEach(row=>{
        if(row.dataset.index && !Number.isNaN(+row.dataset.index)){ max=Math.max(max,+row.dataset.index); return; }
        const any = row.querySelector('input,select,textarea');
        const m = any && (any.name||'').match(/lines-(\d+)-/);
        if(m) max=Math.max(max,+m[1]);
      });
      return Math.max(max,-1);
    }
    function renumberRow(row, i){
      row.dataset.index=i;
      qsa('input,select,textarea',row).forEach(el=>{
        if(el.name) el.name = el.name.replace(/lines-\d+-/,'lines-'+i+'-');
        if(el.id)   el.id   = el.id.replace(/lines-\d+-/,'lines-'+i+'-');
      });
    }
    function clearRow(row){
      qsa('input[type="number"],input[type="text"]',row).forEach(el=>{ el.value=''; });
      qsa('select',row).forEach(s=>{
        s.selectedIndex=0;
        s.dispatchEvent(new Event('change'));
      });
      const badge=row.querySelector('.stock-badge'); if(badge) badge.textContent='';
    }
    function addLine(){
      const rows = qsa('.sale-line',wrap);
      if(!rows.length){ alert('لا يوجد قالب بند لنسخه (min_entries=1 مطلوب بالـ WTForms).'); return; }
      const clone = rows[rows.length-1].cloneNode(true);
      clearRow(clone);
      renumberRow(clone, currentMaxIndex()+1);
      wrap.appendChild(clone);
      bindRow(clone);
      recalc();
    }
    function removeLine(row){
      const rows = qsa('.sale-line',wrap);
      if(rows.length<=1){ alert('يجب ترك بند واحد على الأقل.'); return; }
      row.remove();
      qsa('.sale-line',wrap).forEach((r,i)=>renumberRow(r,i));
      recalc();
    }

    function initAjaxSelect($el, {endpoint, placeholder}){
      $el.select2({
        theme: 'bootstrap-5',
        width: '100%',
        language: 'ar',
        allowClear: !!$el.data('allow-clear'),
        placeholder: placeholder || $el.data('placeholder') || '',
        ajax: {
          delay: 200,
          transport: function (params, success, failure) {
            const url = (typeof endpoint === 'function') ? endpoint() : endpoint;
            params.url = url;
            return jQuery.ajax(params).then(success).catch(failure);
          },
          data: params => ({ q: params.term || '', limit: 50 }),
          processResults: data => ({ results: data })
        }
      });
    }

    function bindRow(row){
      // أزرار
      const rm = row.querySelector('.remove-line');
      if(rm) on(rm,'click',()=>removeLine(row));

      // الحقول الرقمية
      const nums = qsa('.quantity-input,.price-input,.discount-input,.tax-input',row);
      nums.forEach(el=>{ on(el,'input',recalc); on(el,'change',recalc); });

      // Select2 داخل السطر
      select2Ready.then(()=>{
        if(!(window.jQuery && window.jQuery.fn && window.jQuery.fn.select2)) return;
        const $ = window.jQuery;
        const $wh = $(row).find('select.warehouse-select');
        const $pd = $(row).find('select.product-select');

        if ($wh.length) {
          initAjaxSelect($wh, {
            endpoint: () => $wh.data('endpoint') || '/api/warehouses',
            placeholder: $wh.data('placeholder') || 'اختر المستودع'
          });
        }

        const initProducts = () => {
          if (!$pd.length) return;
          const wid = $wh.val();
          const endpoint = wid ? `/api/warehouses/${wid}/products`
                               : ($pd.data('endpoint') || '/api/products');
          try { $pd.select2('destroy'); } catch(_){}
          initAjaxSelect($pd, {
            endpoint: () => endpoint,
            placeholder: $pd.data('placeholder') || 'اختر الصنف'
          });

          // عند اختيار الصنف: عَبّي السعر وأظهر المتاح
          $pd.on('select2:select', (e) => {
            const data = e.params?.data || {};
            const priceInp = row.querySelector('input[name$="-unit_price"]');
            if (priceInp && !priceInp.value && typeof data.price !== 'undefined') {
              const p = toNum(data.price);
              if (p>0) { priceInp.value = p.toFixed(2); recalc(); }
            }
            updateAvailability();
          });
        };

        initProducts();

        if ($wh.length) {
          $wh.on('change', () => {
            if ($pd.length) { $pd.val(null).trigger('change'); }
            initProducts();
            updateAvailability();
          });
        }

        const updateAvailability = async () => {
          const badge = row.querySelector('.stock-badge');
          if (!badge) return;
          const pid = toNum($pd.val());
          const wid = toNum($wh.val());
          if (!(pid && wid)) { badge.textContent=''; return; }
          try{
            const res = await fetch(`/api/products/${pid}/info?warehouse_id=${wid}`, {headers:{'Accept':'application/json'}});
            const data = await res.json();
            const avail = Number.isFinite(+data.available)? +data.available : null;
            badge.textContent = (avail===null?'':'متاح: '+avail);
          }catch(_){ badge.textContent=''; }
        };
      });
    }

    function bindAll(){ qsa('.sale-line',wrap).forEach(bindRow); }

    function recalc(){
      // مجموع صافي البنود (بدون ضريبة السطر لتجنب الازدواج؛ الضريبة العامة فقط)
      let sub=0;
      qsa('.sale-line',wrap).forEach(row=>{
        const q=toNum(qs('[name$="-quantity"]',row)?.value);
        const p=toNum(qs('[name$="-unit_price"]',row)?.value);
        let d=toNum(qs('[name$="-discount_rate"]',row)?.value); d=Math.max(0,Math.min(100,d));
        sub += q*p*(1-d/100);
      });
      let globalTax = toNum(qs('#taxRate')?.value); globalTax=Math.max(0,Math.min(100,globalTax));
      const shipping = toNum(qs('#shippingCost')?.value);
      const taxAmt = sub*(globalTax/100);
      const total = sub + taxAmt + shipping;

      const set=(sel,val)=>{
        const el=qs(sel); if(!el) return;
        const curr = (qs('select[name="currency"]')?.value) || '';
        el.textContent = Number(val).toFixed(2) + (curr?` ${curr}`:'');
      };
      set('#subtotal', sub);
      set('#taxAmount', taxAmt);
      set('#shippingCostDisplay', shipping);
      set('#totalAmount', total);
    }

    // تهيئة Select2 العامة للحقول العلوية: العميل/البائع
    select2Ready.then(()=>{
      if(!(window.jQuery && window.jQuery.fn && window.jQuery.fn.select2)) return;
      const $ = window.jQuery;
      $('#saleForm select.ajax-select').each(function(){
        const $el = $(this);
        if ($el.closest('.sale-line').length) return; // خطوط الفاتورة تُهيّأ في bindRow
        const endpoint = $el.data('endpoint');
        if(!endpoint) return;
        initAjaxSelect($el, { endpoint, placeholder: $el.data('placeholder') || '' });
      });
    });

    bindAll();
    if (addBtn) on(addBtn,'click',addLine);

    const taxRate = qs('#taxRate');      if (taxRate)   on(taxRate,'input',recalc);
    const shipping= qs('#shippingCost'); if (shipping)  on(shipping,'input',recalc);
    const currency= qs('select[name="currency"]'); if (currency) on(currency,'change',recalc);

    recalc();
  })();
})();
