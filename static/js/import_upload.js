document.addEventListener('DOMContentLoaded',function(){
  var f=document.querySelector('#upload-form input[type="file"]');
  if(!f)return;
  f.addEventListener('change',function(){
    var v=(f.value||'').toLowerCase();
    if(!v.endsWith('.csv')&&!v.endsWith('.xlsx')&&!v.endsWith('.xls')){
      alert('الرجاء اختيار ملف بصيغة CSV أو XLSX');
      f.value='';
    }
  });
});
