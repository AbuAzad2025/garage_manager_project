/* File: static/js/sales.js */
;(() => {
  'use strict';

  const qs=(s,el=document)=>el.querySelector(s);
  const qsa=(s,el=document)=>[...el.querySelectorAll(s)];
  const on=(el,ev,cb)=>el&&el.addEventListener(ev,cb);
  const toNum=v=>{const n=parseFloat((v||'').toString().replace(/[^\d.-]/g,''));return isNaN(n)?0:n};

  function loadScriptOnce(src){return new Promise(res=>{if(document.querySelector(`script[src="${src}"]`))return res();const s=document.createElement('script');s.src=src;s.onload=res;document.head.appendChild(s);});}
  function loadCssOnce(href){if(!document.querySelector(`link[href="${href}"]`)){const l=document.createElement('link');l.rel='stylesheet';l.href=href;document.head.appendChild(l);}}

  // تأكيد عام للنماذج الحساسة (لو وضعت data-confirm على الفورم)
  qsa('form[data-confirm]').forEach(f=>on(f,'submit',e=>{if(!confirm(f.dataset.confirm))e.preventDefault()}));

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
    (window.jQuery && window.jQuery.fn && window.jQuery.fn.select2)
      || (loadCssOnce('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css'),
          loadScriptOnce('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js')
            .then(()=>initSelect2()));
    if(window.jQuery && window.jQuery.fn && window.jQuery.fn.select2) initSelect2();
    function initSelect2(){
      const $ = window.$;
      const $cust = $('#saleForm select[name="customer_id"]');
      if($cust.length && $cust.hasClass('select2')){
        $cust.select2({ theme:'bootstrap-5', width:'100%', language:'ar' });
      }
    }

    // Sortable (اختياري)
    (window.Sortable ? Promise.resolve()
                     : loadScriptOnce('https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js'))
      .then(()=>{
        const cont = qs('#saleLines');
        if(cont && window.Sortable){
          new window.Sortable(cont,{handle:'.drag-handle',animation:150,ghostClass:'sortable-ghost'});
        }
      });

    const wrap = qs('#saleLines');
    const addBtn = qs('#addLine');
    let dirty=false;

    function currentMaxIndex(){
      let max=-1;
      qsa('.sale-line',wrap).forEach(row=>{
        if(row.dataset.index && !isNaN(+row.dataset.index)){ max=Math.max(max,+row.dataset.index); return; }
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
      qsa('input[type="number"],input[type="text"]',row).forEach(el=>el.value='');
      qsa('select',row).forEach(s=>{s.selectedIndex=0;s.dispatchEvent(new Event('change'));});
    }
    function addLine(){
      const rows = qsa('.sale-line',wrap);
      if(!rows.length){ alert('لا يوجد قالب بند لنسخه (min_entries=1 مطلوب بالـWTForms).'); return; }
      const clone = rows[rows.length-1].cloneNode(true);
      clearRow(clone);
      renumberRow(clone, currentMaxIndex()+1);
      bindRow(clone);
      wrap.appendChild(clone);
      dirty=true; recalc();
    }
    function removeLine(row){
      const rows = qsa('.sale-line',wrap);
      if(rows.length<=1){ alert('يجب ترك بند واحد على الأقل.'); return; }
      row.remove(); // إعادة ترقيم للحفاظ على الأسماء متسلسلة
      qsa('.sale-line',wrap).forEach((r,i)=>renumberRow(r,i));
      dirty=true; recalc();
    }
    function bindRow(row){
      const nums = qsa('.quantity-input,.price-input,.discount-input,.tax-input',row);
      nums.forEach(el=>{ on(el,'input',recalc); on(el,'change',recalc); });
      const rm = row.querySelector('.remove-line');
      if(rm) on(rm,'click',()=>removeLine(row));
      qsa('input,select,textarea',row).forEach(el=> on(el,'change',()=>{dirty=true;}));
    }
    function bindAll(){ qsa('.sale-line',wrap).forEach(bindRow); }
    function recalc(){
      let sub=0;
      qsa('.sale-line',wrap).forEach(row=>{
        const q=toNum(qs('[name$="-quantity"]',row)?.value);
        const p=toNum(qs('[name$="-unit_price"]',row)?.value);
        let d=toNum(qs('[name$="-discount_rate"]',row)?.value); if(d<0)d=0; if(d>100)d=100;
        sub += q*p*(1-d/100);
      });
      let t=toNum(qs('#taxRate')?.value); if(t<0)t=0; if(t>100)t=100;
      const s=toNum(qs('#shippingCost')?.value);
      const tax=sub*(t/100);
      const tot=sub+tax+s;
      const set=(sel,val)=>{const el=qs(sel); if(el) el.textContent=Number(val).toFixed(2);};
      set('#subtotal',sub); set('#taxAmount',tax); set('#shippingCostDisplay',s); set('#totalAmount',tot);
    }

    if(addBtn) on(addBtn,'click',addLine);
    bi
