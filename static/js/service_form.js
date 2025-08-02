$(document).ready(function () {
    // ✅ Select2 للعميل
    $('#customerSelect').select2({ theme: 'bootstrap-5', allowClear: true });

    // ✅ إضافة قطعة ديناميكيًا
    $('#addPartBtn, #add-part').on('click', function () {
        let newPart = `
        <div class="row g-2 align-items-end mb-2 part-line">
            <div class="col-md-4"><select class="form-select" name="part_id"></select></div>
            <div class="col-md-3"><select class="form-select" name="warehouse_id"></select></div>
            <div class="col-md-2"><input type="number" min="1" class="form-control" name="quantity"></div>
            <div class="col-md-2"><input type="number" step="0.01" class="form-control" name="unit_price"></div>
            <div class="col-auto"><button type="button" class="btn btn-outline-danger remove-part">&times;</button></div>
        </div>`;
        $('#parts-list').append(newPart);
    });

    $(document).on('click', '.remove-part', function () {
        $(this).closest('.part-line').remove();
    });

    // ✅ إضافة مهمة ديناميكيًا
    $('#addTaskBtn, #add-task').on('click', function () {
        let newTask = `
        <div class="row g-2 align-items-end mb-2 task-line">
            <div class="col-md-6"><input type="text" class="form-control" name="task_desc"></div>
            <div class="col-md-2"><input type="number" min="1" class="form-control" name="task_qty"></div>
            <div class="col-md-2"><input type="number" step="0.01" class="form-control" name="task_price"></div>
            <div class="col-auto"><button type="button" class="btn btn-outline-danger remove-task">&times;</button></div>
        </div>`;
        $('#tasks-list').append(newTask);
    });

    $(document).on('click', '.remove-task', function () {
        $(this).closest('.task-line').remove();
    });
});
