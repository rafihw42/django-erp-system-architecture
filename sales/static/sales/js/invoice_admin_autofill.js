/**
 * invoice_admin_autofill.js
 * Watches the "Customer" autocomplete on the Invoice add/change form.
 * When a customer is selected, fetches that customer's kode_sales via AJAX
 * and pre-fills the Sales field — only if the field is currently empty.
 *
 * KEY DESIGN: Uses jQuery event delegation on `document` so the listener
 * is always active regardless of when Django admin finishes initialising
 * its Select2 autocomplete widget (which happens AFTER DOMContentLoaded).
 */
(function () {
    'use strict';

    function fetchAndFillSales(kodeCust) {
        var salesField = document.getElementById('id_sales');
        if (!salesField || salesField.value || !kodeCust) return;

        fetch('/api/customer-sales/?kode_cust=' + encodeURIComponent(kodeCust))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var sf = document.getElementById('id_sales');
                if (sf && data.kode_sales && !sf.value) {
                    sf.value = data.kode_sales;
                    // Green flash to confirm auto-fill
                    sf.style.transition = 'background-color 0.3s';
                    sf.style.backgroundColor = '#d4edda';
                    setTimeout(function () { sf.style.backgroundColor = ''; }, 800);
                }
            })
            .catch(function (err) {
                console.warn('invoice_admin_autofill.js: Failed to fetch kode_sales', err);
            });
    }

    // Use event delegation on document — this fires no matter when Select2 is attached.
    // Django admin's autocomplete fires the native 'change' event AND select2 events.
    // Binding on document ensures we don't miss the moment Select2 is ready.
    $(document).on('select2:select', '#id_customer', function (e) {
        var salesField = document.getElementById('id_sales');
        if (salesField) salesField.value = '';
        fetchAndFillSales(e.params.data.id);
    });

    $(document).on('select2:clear', '#id_customer', function () {
        var salesField = document.getElementById('id_sales');
        if (salesField) salesField.value = '';
    });

    // Also fire on page load if a customer is already pre-selected
    // (e.g., returning to a form after a validation error)
    $(document).ready(function () {
        var customerSelect = document.getElementById('id_customer');
        var salesField = document.getElementById('id_sales');
        if (customerSelect && customerSelect.value && salesField && !salesField.value) {
            fetchAndFillSales(customerSelect.value);
        }
    });

})();
