$(function () {
    function updateFields() {
        let table = $('#select-table').val();
        $.getJSON('/reports/api/model_fields', { model: table }, function (data) {
            let dateSelect = $('#select-date-field').empty().append($('<option>', { value: '', text: '—' }));
            (data.date_fields || []).forEach(f => dateSelect.append($('<option>', { value: f, text: f })));

            let colsSelect = $('#select-columns').empty();
            (data.columns || []).forEach(c => colsSelect.append($('<option>', { value: c, text: c })));

            let extra = $('#extra-filters').empty();
            (data.columns || []).forEach(c => {
                extra.append(`<div class="col-md-3 mb-2"><input name="${c}" class="form-control" placeholder="فلترة حسب ${c}"></div>`);
            });
        });
    }

    $('#select-table').change(updateFields);
    updateFields();

    if ($('#report-table').length) {
        $('#report-table').DataTable({
            dom: 'Bfrtip',
            buttons: ['excelHtml5', 'print'],
            paging: true,
            searching: true,
            responsive: true,
            language: { url: '//cdn.datatables.net/plug-ins/1.10.21/i18n/Arabic.json' }
        });
    }
});
