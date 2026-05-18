window.addEventListener('load', function() {
    (function($) {
        
        // --- Calculate Live Grand Total ---
        function calculateGrandTotal() {
            var grandTotal = 0;
            $('input[name*="subtotal"]').each(function() {
                var val = parseFloat($(this).val()) || 0;
                grandTotal += val;
            });
            
            if ($('#dynamic-grand-total').length === 0) {
                $('.inline-group').append('<div style="background-color:#f8f9fa; text-align:right; padding:15px; font-size:18px; border:1px solid #ddd; margin-top:10px;"><strong>Live Grand Total: Rp <span id="dynamic-grand-total">0</span></strong></div>');
            }
            $('#dynamic-grand-total').text(grandTotal.toLocaleString('id-ID'));
        }

        // --- 1. The Instant Math Logic ---
        // Fuzzy search: Looks for ANY box containing 'qty', 'quantity', 'jumlah', or 'harga'
        $(document).on('keyup change', 'input[name*="qty"], input[name*="quantity"], input[name*="jumlah"], input[name*="harga"]', function() {
            var row = $(this).closest('tr');
            
            var qtyBox = row.find('input[name*="qty"], input[name*="quantity"], input[name*="jumlah"]');
            var priceBox = row.find('input[name*="harga"]');
            var subtotalBox = row.find('input[name*="subtotal"]');
            
            var qty = parseFloat(qtyBox.val()) || 0;
            var price = parseFloat(priceBox.val()) || 0;
            
            subtotalBox.val(qty * price);
            calculateGrandTotal(); 
        });

        // --- 2. Fetch Price When Product is Selected ---
        $(document).on('change select2:select', 'select[name*="product"]', function(e) {
            if (e.type === 'change' && $(this).hasClass('select2-hidden-accessible')) return;

            var row = $(this).closest('tr');
            var productCode = $(this).val(); 
            
            if (productCode) {
                fetch('/api/get-price/' + productCode + '/')
                    .then(response => response.json())
                    .then(data => {
                        var priceBox = row.find('input[name*="harga"]');
                        var qtyBox = row.find('input[name*="qty"], input[name*="quantity"], input[name*="jumlah"]');
                        
                        if (priceBox.length > 0) {
                            priceBox.val(data.harga);
                            qtyBox.trigger('change'); 
                        } else {
                            // --- NEW X-RAY SNAPSHOT ---
                            console.error("ERROR: JavaScript cannot find the text box!");
                            console.log("Here is the exact HTML code JavaScript sees for this row:");
                            console.log(row.html()); 
                        }
                    });
            }
        });

        function updateDueDate() {
            var custCode = $('select[name="customer"]').val();
            var invoiceDateStr = $('input[name="tanggal"]').val();

            if (custCode && invoiceDateStr) {
                fetch('/api/get-tempo/' + custCode + '/')
                    .then(response => response.json())
                    .then(data => {
                        var tempo = data.tempo_hari;
                        if (tempo > 0) {
                            // Turn the text into a real Date object
                            var invoiceDate = new Date(invoiceDateStr);
                            
                            // Add the customer's days to it
                            invoiceDate.setDate(invoiceDate.getDate() + tempo);

                            // Format it back to YYYY-MM-DD for the Django box
                            var yyyy = invoiceDate.getFullYear();
                            var mm = String(invoiceDate.getMonth() + 1).padStart(2, '0');
                            var dd = String(invoiceDate.getDate()).padStart(2, '0');

                            // Drop it into the Due Date box
                            $('input[name="tanggal_jatuh_tempo"]').val(yyyy + '-' + mm + '-' + dd);
                        }
                    });
            }
        }

        // Listen for changes on the Customer Dropdown OR the Invoice Date box
        $(document).on('change select2:select', 'select[name="customer"], input[name="tanggal"]', function(e) {
             if (e.type === 'change' && $(this).hasClass('select2-hidden-accessible')) return;
             updateDueDate();
        });

        // --- 3. The Green "Save and Print" Button ---
        if ($('.submit-row').length > 0) {
            var printBtn = $('<input type="submit" value="Save and Print" name="_save_and_print" class="default" style="background-color: #28a745; margin-left: 10px; float: right;">');
            $('.submit-row').append(printBtn);
        }

    })(django.jQuery);
});