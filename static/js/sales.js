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

    // Select2 (اختياري)
    const wantsSelect2 = !!document.querySelector('#saleForm .select2');
    if (wantsSelect2) {
      loadCssOnce('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css');
      loadCssOnce('https://cdn.jsdelivr.net/npm/@ttskch/select2-bootstrap4-theme@1.5.2/dist/select2-bootstrap4.min.css');
      loadScriptOnce('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js')
        .then(()=>{
          if (window.jQuery && window.jQuery.fn && window.jQuery.fn.select2) {
            const $ = window.jQuery;
            $('#saleForm select.select2').select2({ theme:'bootstrap-5', width:'100%', language:'ar' });
          }
        });
    }

    // Sortable (اختياري للسحب لإعادة الترتيب)
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
      qsa('select',row).forEach(s=>{ s.selectedIndex=0; s.dispatchEvent(new Event('change')); });
    }
    function addLine(){
      const rows = qsa('.sale-line',wrap);
      if(!rows.length){ alert('لا يوجد قالب بند لنسخه (min_entries=1 مطلوب بالـ WTForms).'); return; }
      const clone = rows[rows.length-1].cloneNode(true);
      clearRow(clone);
      renumberRow(clone, currentMaxIndex()+1);
      bindRow(clone);
      wrap.appendChild(clone);
      recalc();
    }
    function removeLine(row){
      const rows = qsa('.sale-line',wrap);
      if(rows.length<=1){ alert('يجب ترك بند واحد على الأقل.'); return; }
      row.remove();
      qsa('.sale-line',wrap).forEach((r,i)=>renumberRow(r,i));
      recalc();
    }

    function bindRow(row){
      const rm = row.querySelector('.remove-line');
      if(rm) on(rm,'click',()=>removeLine(row));
      const nums = qsa('.quantity-input,.price-input,.discount-input,.tax-input',row);
      nums.forEach(el=>{ on(el,'input',recalc); on(el,'change',recalc); });

      // ملء سعر الوحدة تلقائيًا لو كانت الـ <option data-price="...">
      const prodSel = row.querySelector('select[name$="-product_id"]');
      const priceInp = row.querySelector('input[name$="-unit_price"]');
      if (prodSel && priceInp) {
        on(prodSel,'change',()=>{
          const opt = prodSel.options[prodSel.selectedIndex];
          const p = toNum(opt?.dataset?.price || '');
          if (p>0 && !priceInp.value) { priceInp.value = p.toFixed(2); recalc(); }
        });
      }

      // جلب توفر المستودع اختياريًا (لو أردت)
      const whSel = row.querySelector('select[name$="-warehouse_id"]');
      if (prodSel && whSel) {
        const fetchAvail = async () => {
          const pid = toNum(prodSel.value);
          const wid = toNum(whSel.value);
          if (!(pid && wid)) return;
          try {
            const res = await fetch(`/api/products/${pid}/info?warehouse_id=${wid}`, {headers:{'Accept':'application/json'}});
            const data = await res.json();
            const available = Number.isFinite(+data.available) ? +data.available : null;
            const badgeSel = row.querySelector('.stock-badge');
            if (badgeSel) badgeSel.textContent = (available===null?'':'متاح: '+available);
          } catch(_){}
        };
        on(prodSel,'change',fetchAvail);
        on(whSel,'change',fetchAvail);
      }
    }

    function bindAll(){ qsa('.sale-line',wrap).forEach(bindRow); }
    function recalc(){
      let sub=0;
      qsa('.sale-line',wrap).forEach(row=>{
        const q=toNum(qs('[name$="-quantity"]',row)?.value);
        const p=toNum(qs('[name$="-unit_price"]',row)?.value);
        let d=toNum(qs('[name$="-discount_rate"]',row)?.value); d=Math.max(0,Math.min(100,d));
        let t=toNum(qs('[name$="-tax_rate"]',row)?.value); t=Math.max(0,Math.min(100,t));
        const net = q*p*(1-d/100);
        const lineTotal = net*(1+t/100);
        sub += lineTotal;
      });
      // ضريبة عامة + شحن على مستوى الفاتورة
      let globalTax = toNum(qs('#taxRate')?.value); globalTax=Math.max(0,Math.min(100,globalTax));
      const shipping = toNum(qs('#shippingCost')?.value);
      const taxAmt = sub*(globalTax/100);
      const total = sub + taxAmt + shipping;

      const set=(sel,val,suffix='')=>{
        const el=qs(sel); if(!el) return;
        const curr = (qs('select[name="currency"]')?.value) || '';
        el.textContent = Number(val).toFixed(2) + (curr?` ${curr}`:'') + suffix;
      };
      set('#subtotal', sub);
      set('#taxAmount', taxAmt);
      set('#shippingCostDisplay', shipping);
      set('#totalAmount', total);
    }

    bindAll();
    if (addBtn) on(addBtn,'click',addLine);

    const taxRate = qs('#taxRate');      if (taxRate)   on(taxRate,'input',recalc);
    const shipping= qs('#shippingCost'); if (shipping)  on(shipping,'input',recalc);
    const currency= qs('select[name="currency"]'); if (currency) on(currency,'change',recalc);

    recalc();
  })();
})();
