/**
 * customer_admin.js
 * Watches the "Wilayah" dropdown on the Customer add/change form.
 * When a region is selected, it calls the Django AJAX endpoint to fetch
 * the next available kode_cust and fills it in the (read-only) field.
 */
(function () {
    'use strict';

    function fetchNextCode(wilayah) {
        if (!wilayah) {
            document.getElementById('id_kode_cust').value = '';
            return;
        }
        var url = '/api/next-customer-code/?wilayah=' + encodeURIComponent(wilayah);
        fetch(url)
            .then(function (response) { return response.json(); })
            .then(function (data) {
                var field = document.getElementById('id_kode_cust');
                if (field) {
                    field.value = data.kode_cust || '';
                    // Visual flash to show the field was updated
                    field.style.transition = 'background-color 0.3s';
                    field.style.backgroundColor = '#d4edda';
                    setTimeout(function () {
                        field.style.backgroundColor = '';
                    }, 800);
                }
            })
            .catch(function (err) {
                console.warn('customer_admin.js: Failed to fetch next code', err);
            });
    }

    function init() {
        var wilayahSelect = document.getElementById('id_wilayah');
        var kodeField = document.getElementById('id_kode_cust');

        if (!wilayahSelect || !kodeField) return;

        // Only auto-fill if this is a NEW customer (kode_cust is still empty)
        var isNewCustomer = !kodeField.value.trim();

        if (isNewCustomer) {
            // Fetch immediately if a region is already selected (e.g., page reloaded with value)
            if (wilayahSelect.value) {
                fetchNextCode(wilayahSelect.value);
            }

            // Re-fetch every time the user changes the region
            wilayahSelect.addEventListener('change', function () {
                fetchNextCode(this.value);
            });
        }
    }

    // Run after the DOM is fully ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
