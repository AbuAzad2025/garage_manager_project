// File: static/js/app.reports.js
$(document).ready(function() {
    // ✅ تحميل الحقول عند تغيير الجدول
    function updateFields() {
        var table = $('#select-table').val();
        $.getJSON('/reports/api/model_fields', { model: table }, function(data) {
            var dateSelect = $('#select-date-field').empty()
                .append($('<option>', { value: '', text: '—' }));
            data.date_fields.forEach(f => dateSelect.append($('<option>', { value: f, text: f })));

            var colsSelect = $('#select-columns').empty();
            data.columns.forEach(c => colsSelect.append($('<option>', { value: c, text: c })));

            var extra = $('#extra-filters').empty();
            data.columns.forEach(c => {
                extra.append(`
                  <div class="col-md-3 mb-2">
                    <input name="${c}" class="form-control" placeholder="فلترة حسب ${c}">
                  </div>`);
            });
        });
    }

    $('#select-table').change(updateFields);
    if($('#select-table').length) updateFields();

    // ✅ تفعيل DataTables
    if ($('#report-table').length) {
        $('#report-table').DataTable({
            dom: 'Bfrtip',
            buttons: ['excelHtml5','print'],
            paging: true,
            searching: true,
            responsive: true,
            language: { url:'//cdn.datatables.net/plug-ins/1.10.21/i18n/Arabic.json' }
        });
    }

    // ✅ تفعيل Chart.js للـDashboard
    $('canvas.chartjs-chart').each(function(){
        var ctx = this.getContext('2d');
        new Chart(ctx, {
            type: $(this).data('type'),
            data: {
                labels: JSON.parse($(this).attr('data-labels')),
                datasets: [{
                    label: $(this).data('dataset-label'),
                    data: JSON.parse($(this).attr('data-values')),
                    borderWidth: 2,
                    backgroundColor: 'rgba(54, 162, 235, 0.3)',
                    borderColor: '#007bff',
                    fill: true
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    });
});
