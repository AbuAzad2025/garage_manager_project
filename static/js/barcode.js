(function(){
  const input = document.getElementById('barcode');
  const help  = document.getElementById('barcodeHelp');
  if (!input) return;

  input.addEventListener('input', () => {
    let v = input.value.replace(/\D+/g,'');
    if (v.length > 13) v = v.slice(0,13);
    input.value = v;
    input.classList.remove('is-invalid','is-valid');
    if (v.length >= 12) check(v);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const form = input.closest('form');
      const focusables = form.querySelectorAll('input,select,textarea,button');
      for (let i=0;i<focusables.length;i++){
        if (focusables[i] === input && focusables[i+1]) { focusables[i+1].focus(); break; }
      }
    }
  });

  async function check(code){
    try{
      const res = await fetch(`/api/barcode/validate?code=${encodeURIComponent(code)}`, { headers: {'X-Requested-With':'XMLHttpRequest'} });
      const r = await res.json();
      if (!r.valid) {
        input.classList.add('is-invalid');
        help.textContent = 'باركود غير صالح';
        return;
      }
      if (r.normalized && r.normalized !== input.value) {
        input.value = r.normalized;
      }
      if (r.exists) {
        input.classList.add('is-invalid');
        help.textContent = 'الباركود مستخدم بالفعل';
      } else {
        input.classList.add('is-valid');
        help.textContent = 'الباركود صالح';
      }
    } catch {
      help.textContent = 'تعذر التحقق الآن، سيتم الفحص عند الحفظ';
    }
  }
})();
