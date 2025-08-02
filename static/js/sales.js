// ================================
// Sales Module JS
// تحسينات الحسابات والتفاعلات
// ================================

$(document).ready(function () {

  // دالة حساب المجاميع للفواتير
  function calculateSaleTotals() {
    let subtotal = 0;
    let taxRate = parseFloat($('#tax_rate').val()) || 0;
    let shippingCost = parseFloat($('#shipping_cost').val()) || 0;

    $('.sale-line').each(function () {
      const qty = parseFloat($(this).find('.quantity-input').val()) || 0;
      const price = parseFloat($(this).find('.price-input').val()) || 0;
      const discount = parseFloat($(this).find('.discount-input').val()) || 0;

      const totalBeforeTax = qty * price * (1 - discount / 100);
      subtotal += totalBeforeTax;
    });

    const taxAmount = subtotal * (taxRate / 100);
    const total = subtotal + taxAmount + shippingCost;

    $('#subtotal').text(subtotal.toFixed(2));
    $('#taxAmount').text(taxAmount.toFixed(2));
    $('#shippingCost').text(shippingCost.toFixed(2));
    $('#totalAmount').text(total.toFixed(2));
  }

  // إضافة بند جديد
  $('#addLine').click(function () {
    const index = $('.sale-line').length;
    const newLine = `
    <div class="sale-line border rounded p-3 mb-3 sale-line-row">
      <div class="row g-3">
        <div class="col-md-5">
          <select name="lines-${index}-product_id" class="form-select product-select">
            <option value="">اختر صنفاً</option>
            <!-- سيتم ملؤها ديناميكيًا من السيرفر -->
          </select>
        </div>
        <div class="col-md-3">
          <select name="lines-${index}-warehouse_id" class="form-select">
            <option value="">اختر مخزناً</option>
            <!-- سيتم ملؤها ديناميكيًا -->
          </select>
        </div>
        <div class="col-md-2">
          <input type="number" name="lines-${index}-quantity" class="form-control quantity-input" min="1" value="1">
        </div>
        <div class="col-md-2">
          <input type="number" name="lines-${index}-unit_price" class="form-control price-input" min="0" step="0.01" value="0">
        </div>
        <div class="col-md-2">
          <input type="number" name="lines-${index}-discount_rate" class="form-control discount-input" min="0" max="100" value="0">
        </div>
        <div class="col-md-2">
          <input type="number" name="lines-${index}-tax_rate" class="form-control tax-input" min="0" max="100" value="0">
        </div>
        <div class="col-md-12 d-flex justify-content-end mt-2">
          <button type="button" class="btn btn-sm btn-danger remove-line">
            <i class="fas fa-trash me-1"></i> حذف البند
          </button>
        </div>
      </div>
    </div>`;

    $('#saleLines').append(newLine);
    attachEventListeners();
  });

  // إرفاق الأحداث للبنود
  function attachEventListeners() {
    $('.remove-line').off('click').on('click', function () {
      if ($('.sale-line').length > 1) {
        $(this).closest('.sale-line').remove();
        calculateSaleTotals();
      } else {
        alert('يجب أن تحتوي الفاتورة على بند واحد على الأقل');
      }
    });

    $('.quantity-input, .price-input, .discount-input, .tax-input').off('input').on('input', calculateSaleTotals);
    $('#tax_rate, #shipping_cost').off('input').on('input', calculateSaleTotals);
  }

  // تصفية الفواتير عبر AJAX
  $('#filterForm').on('submit', function (e) {
    e.preventDefault();
    const formData = $(this).serialize();
    $.ajax({
      url: $(this).attr('action'),
      type: "GET",
      data: formData,
      success: function (data) {
        $('#salesTable').html($(data).find('#salesTable').html());
        $('.pagination').html($(data).find('.pagination').html());
      }
    });
  });

  // تهيئة Select2
  $('.select2').select2({
    placeholder: "اختر عميلاً",
    allowClear: true,
    language: "ar"
  });

  // تأكيد قبل الحذف
  $('.delete-btn').on('click', function () {
    return confirm('هل أنت متأكد من حذف هذا العنصر؟');
  });

  // التهيئة الأولية
  attachEventListeners();
  calculateSaleTotals();
});