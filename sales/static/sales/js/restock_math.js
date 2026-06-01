// restock_math.js

function formatRupiah(number) {
    return new Intl.NumberFormat('id-ID').format(number);
}

function calculateTempo() {
    const tanggalInput = document.getElementById('tanggal').value;
    if (tanggalInput) {
        const date = new Date(tanggalInput);
        date.setDate(date.getDate() + 60); 
        const formattedDate = date.toISOString().split('T')[0]; 
        document.getElementById('tanggal_jatuh_tempo').value = formattedDate;
    }
}

function addRow() {
    const template = document.getElementById('row-template');
    const tbody = document.getElementById('items-body');
    
    // Copy the invisible template
    const clone = template.content.cloneNode(true);
    
    // Paste it into the table
    tbody.appendChild(clone);
    
    // --- TURN THE NEW DROPDOWN INTO A SEARCH BAR ---
    const newRow = tbody.lastElementChild;
    const $select = $(newRow).find('.select2-product');

    $select.select2({
        placeholder: "-- Cari / Pilih Barang --",
        width: '100%'
    });

    // --- AUTO-FILL harga_beli WHEN A PRODUCT IS SELECTED ---
    $select.on('change', function () {
        const kodeBarang = $(this).val();
        if (!kodeBarang) return;

        fetch(`/api/get-price/${encodeURIComponent(kodeBarang)}/`)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                const hargaInput = newRow.querySelector('input[name="harga_beli[]"]');
                if (hargaInput && data.harga_beli !== undefined) {
                    hargaInput.value = data.harga_beli;
                    // Recalculate this row's subtotal immediately
                    calculateRow(hargaInput);
                    // Visual flash to show it was filled
                    hargaInput.style.transition = 'background-color 0.3s';
                    hargaInput.style.backgroundColor = '#d4edda';
                    setTimeout(function () { hargaInput.style.backgroundColor = ''; }, 800);
                }
            })
            .catch(function (err) {
                console.warn('restock_math.js: Failed to fetch harga_beli', err);
            });
    });
}

function removeRow(button) {
    button.closest('tr').remove();
    calculateGrandTotal(); 
}

function calculateRow(inputElement) {
    const row = inputElement.closest('tr');
    const qty = parseFloat(row.querySelector('input[name="qty[]"]').value) || 0;
    const harga = parseFloat(row.querySelector('input[name="harga_beli[]"]').value) || 0;
    
    const subtotal = qty * harga;
    row.querySelector('.subtotal-text').innerText = 'Rp ' + formatRupiah(subtotal);
    row.dataset.subtotal = subtotal; 
    
    calculateGrandTotal();
}

function calculateGrandTotal() {
    const rows = document.querySelectorAll('#items-body tr');
    let subTotal = 0;
    
    rows.forEach(row => {
        subTotal += parseFloat(row.dataset.subtotal) || 0;
    });
    
    const ppnPersen = parseFloat(document.getElementById('ppn_persen').value) || 0;
    const ppnNominal = subTotal * (ppnPersen / 100);
    const grandTotal = subTotal + ppnNominal;
    
    document.getElementById('subtotal-display').innerText = 'Rp ' + formatRupiah(subTotal);
    document.getElementById('grand-total-display').innerText = 'Rp ' + formatRupiah(grandTotal);
}

// --- UPDATED: We use jQuery's ready() function instead of window.onload ---
$(document).ready(function() {
    
    // 1. Also add a Search Bar to the Supplier dropdown at the top!
    $('#supplier').select2({
        placeholder: "-- Cari / Pilih Supplier --",
        width: '100%'
    });

    // 2. Set the default dates
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('tanggal').value = today;
    calculateTempo(); 
    
    // 3. Add the first blank row (this will trigger Select2 automatically!)
    addRow(); 
});