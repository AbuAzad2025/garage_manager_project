<script>
(function(){
  const input = document.getElementById('barcode');
  const help  = document.getElementById('barcodeHelp');
  if (!input) return;

  let timer = null;
  let controller = null;

  input.addEventListener('input', () => {
    let v = input.value.replace(/\D+/g,'');
    if (v.length > 13) v = v.slice(0,13);
    input.value = v;
    input.classList.remove('is-invalid','is-valid');
    if (timer) clearTimeout(timer);
    if (v.length >= 12) timer = setTimeout(() => check(v), 300);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const form = input.closest('form');
      const focusables = form ? form.querySelectorAll('input,select,textarea,button') : [];
      for (let i=0;i<focusables.length;i++){
        if (focusables[i] === input && focusables[i+1]) { focusables[i+1].focus(); break; }
      }
    }
  });

  async function check(code){
    try{
      if (controller) controller.abort();
      controller = new AbortController();
      const res = await fetch(`/api/barcode/validate?code=${encodeURIComponent(code)}`, {
        headers: {'X-Requested-With':'XMLHttpRequest'},
        signal: controller.signal
      });
      const r = await res.json();
      if (code !== input.value) return;
      if (!r.valid) {
        input.classList.add('is-invalid');
        help.textContent = 'باركود غير صالح';
        return;
      }
      if (r.normalized && r.normalized !== input.value) input.value = r.normalized;
      if (r.exists) {
        input.classList.add('is-invalid');
        help.textContent = 'الباركود مستخدم بالفعل';
      } else {
        input.classList.add('is-valid');
        help.textContent = 'الباركود صالح';
      }
    } catch(e){
      if (e.name === 'AbortError') return;
      help.textContent = 'تعذر التحقق الآن، سيتم الفحص عند الحفظ';
    }
  }
})();
</script>
