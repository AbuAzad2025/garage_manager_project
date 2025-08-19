(function () {
  "use strict";

  function clampQuantity(input) {
    var v = Number(input.value || 0);
    var min = input.hasAttribute("min") ? Number(input.min) : 1;
    var max = input.dataset.max ? Number(input.dataset.max) : (input.hasAttribute("max") ? Number(input.max) : undefined);
    if (!Number.isFinite(v) || v < min) v = min;
    if (Number.isFinite(max) && v > max) v = max;
    input.value = String(v);
    return v;
  }

  function wireQtyButtons(root) {
    (root || document).querySelectorAll(".btn-step").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var dir = Number(btn.dataset.dir || 0);
        var input = btn.parentElement.querySelector(".qty-input");
        if (!input) return;
        var cur = clampQuantity(input);
        input.value = String(cur + dir);
        clampQuantity(input);
      });
    });
    (root || document).querySelectorAll(".qty-input").forEach(function (inp) {
      ["input","change","blur"].forEach(function (ev) {
        inp.addEventListener(ev, function () { clampQuantity(inp); });
      });
    });
  }

  function debounce(fn, t) {
    var id; return function () { clearTimeout(id); var a=arguments, ctx=this; id=setTimeout(function(){fn.apply(ctx,a)}, t||200); };
  }

  function wireCatalogSearch() {
    var search = document.getElementById("search");
    var container = document.getElementById("products-container");
    if (!search || !container) return;
    var cards = Array.prototype.slice.call(container.querySelectorAll(".product-card"));
    var run = function () {
      var q = (search.value || "").trim().toLowerCase();
      cards.forEach(function (c) {
        var name = (c.getAttribute("data-name") || "");
        var desc = (c.getAttribute("data-desc") || "");
        c.style.display = (name.indexOf(q) !== -1 || desc.indexOf(q) !== -1) ? "" : "none";
      });
    };
    search.addEventListener("input", debounce(run, 120));
  }

  function wireCheckoutForm() {
    var form = document.getElementById("payment-form");
    if (!form) return;
    var methodSel = document.getElementById("payment-method");
    var cardFields = document.getElementById("card-fields");
    var cardNumber = form.querySelector('input[name="card_number"]');
    var expiry = form.querySelector('input[name="expiry"]');

    function toggleCardFields() {
      var m = methodSel ? methodSel.value : "card";
      cardFields.style.display = (m === "card") ? "" : "none";
    }

    if (methodSel) {
      methodSel.value = "card";
      Array.prototype.slice.call(methodSel.options).forEach(function(opt){ opt.disabled = opt.value !== "card"; });
      methodSel.addEventListener("change", toggleCardFields);
    }
    toggleCardFields();

    if (cardNumber) {
      cardNumber.addEventListener("input", function () {
        var v = (cardNumber.value || "").replace(/\D/g, "");
        v = v.replace(/(\d{4})(?=\d)/g, "$1 ");
        cardNumber.value = v.substring(0, 19);
      });
    }
    if (expiry) {
      expiry.addEventListener("input", function () {
        var v = (expiry.value || "").replace(/\D/g, "");
        if (v.length > 2) v = v.substring(0, 2) + "/" + v.substring(2, 4);
        expiry.value = v.substring(0, 5);
      });
    }

    form.addEventListener("submit", function () {
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري معالجة الدفع...'; }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireQtyButtons(document);
    wireCatalogSearch();
    wireCheckoutForm();
  });
})();
