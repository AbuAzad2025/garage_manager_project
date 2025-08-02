$(function(){
  // initialize DataTable with server JSON endpoint
  $('#shipmentsTable').DataTable({
    processing: true,
    serverSide: true,
    ajax: {
      url: window.location.pathname,
      data: d => {
        d.format = 'json';
        d.status = $('select[name=status]').val();
        d.search = $('input[name=search]').val();
      }
    },
    columns: [
      { data: null, render: (_,_ ,ctx,row) => row.DT_RowIndex },
      { data: 'number' },
      { data: 'status', render: s => `<span class="badge badge-${s.toLowerCase()}">${s}</span>` },
      { data: 'origin' },
      { data: 'destination' },
      { data: 'expected_arrival' },
      { data: 'total_value' },
      { data: 'id', orderable: false, render: id => `
        <a href="/shipments/${id}" class="btn btn-sm btn-info"><i class="fas fa-eye"></i></a>
        <a href="/shipments/${id}/edit" class="btn btn-sm btn-primary"><i class="fas fa-edit"></i></a>
        ` }
    ],
    order: [[5,'desc']],
    language: { url: "//cdn.datatables.net/plug-ins/1.13.4/i18n/Arabic.json" }
  });

  // on filter form submit, reload table
  $('#filterForm').submit(function(e){
    e.preventDefault();
    $('#shipmentsTable').DataTable().ajax.reload();
  });

  // dynamic partner rows
  $('#addPartner').click(e=>{
    e.preventDefault();
    let tpl = $('.partner-entry:first').clone();
    tpl.find('input,select').val('');
    $('#partnersContainer').append(tpl);
  });
  $(document).on('click','.remove-partner', function(e){
    e.preventDefault();
    if ($('#partnersContainer .partner-entry').length>1) $(this).closest('.partner-entry').remove();
  });

  // dynamic item rows
  $('#addItem').click(e=>{
    e.preventDefault();
    let tpl = $('.item-entry:first').clone();
    tpl.find('input,select').val('');
    $('#itemsContainer').append(tpl);
  });
  $(document).on('click','.remove-item', function(e){
    e.preventDefault();
    if ($('#itemsContainer .item-entry').length>1) $(this).closest('.item-entry').remove();
  });

  // datepickers (using Bootstrap Datepicker)
  $('.datepicker').datepicker({ format:'yyyy-mm-dd', autoclose:true });
});
