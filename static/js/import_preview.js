(function(){
  var rows=window.__IMPORT_ROWS__||[];
  var table=document.getElementById('previewTable');
  var extra=document.getElementById('extraTable');
  var searchBox=document.getElementById('searchBox');
  var filter=document.getElementById('quickFilter');
  var btnSave=document.getElementById('btnSave');
  var btnCommit=document.getElementById('btnCommit');
  var saveField=document.getElementById('rows_json_save');
  var commitField=document.getElementById('rows_json_commit');
  var token=document.getElementById('token')?document.getElementById('token').value:'';
  var btnCompact=document.getElementById('btnToggleCompact');

  function collect(){
    var map={};
    Array.from(table.tBodies[0].rows).forEach(function(tr){
      var idx=parseInt(tr.getAttribute('data-rownum'),10);
      map[idx]=map[idx]||{};
      tr.querySelectorAll('.cell').forEach(function(inp){
        var f=inp.getAttribute('data-field');
        var v=inp.value;
        map[idx][f]=v;
      });
    });
    Array.from(extra.tBodies[0].rows).forEach(function(tr){
      var idx=parseInt(tr.getAttribute('data-rownum'),10);
      map[idx]=map[idx]||{};
      tr.querySelectorAll('.cell').forEach(function(inp){
        var f=inp.getAttribute('data-field');
        var v=inp.value;
        map[idx][f]=v;
      });
    });
    var out=rows.map(function(r){
      var idx=r.rownum;
      var merged=Object.assign({},r.data||{},map[idx]||{});
      return { rownum: idx, data: merged, match: r.match||{}, soft_warnings: r.soft_warnings||[] };
    });
    return out;
  }

  function applyFilters(){
    var q=(searchBox.value||'').trim().toLowerCase();
    var mode=filter.value;
    var body=table.tBodies[0];
    Array.from(body.rows).forEach(function(tr){
      var rn=tr.getAttribute('data-rownum');
      var extraRow=extra.querySelector('tr[data-rownum="'+rn+'"]');
      var txt=Array.from(tr.querySelectorAll('input')).map(function(i){return i.value.toLowerCase();}).join(' ');
      var okSearch=!q||txt.indexOf(q)>=0;
      var cls=tr.className;
      var okFilter=true;
      if(mode==='missing') okFilter=cls.indexOf('row-missing')>=0;
      else if(mode==='warnings') okFilter=cls.indexOf('row-warning')>=0;
      else if(mode==='new') okFilter=cls.indexOf('row-new')>=0;
      else if(mode==='matched') okFilter=cls.indexOf('row-matched')>=0;
      var show=okSearch&&okFilter;
      tr.style.display=show?'':'none';
      if(extraRow) extraRow.style.display=show?'':'none';
    });
  }

  function validateInline(){
    Array.from(table.tBodies[0].rows).forEach(function(tr){
      var name=tr.querySelector('input[data-field="name"]');
      if(name){
        if(!name.value.trim()) tr.classList.add('row-missing'); else tr.classList.remove('row-missing');
      }
    });
  }

  if(searchBox) searchBox.addEventListener('input',applyFilters);
  if(filter) filter.addEventListener('change',applyFilters);
  if(btnCompact) btnCompact.addEventListener('click',function(){
    document.body.classList.toggle('compact');
  });

  function prepare(fieldEl){
    var data=collect();
    var json=JSON.stringify({normalized:data});
    fieldEl.value=json;
  }

  if(btnSave){
    btnSave.addEventListener('click',function(){
      validateInline();
      prepare(saveField);
      document.getElementById('saveForm').submit();
    });
  }
  if(btnCommit){
    btnCommit.addEventListener('click',function(){
      validateInline();
      prepare(commitField);
      document.getElementById('commitForm').submit();
    });
  }

  applyFilters();
})();
