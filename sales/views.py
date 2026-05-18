from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseNotAllowed
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count, F
from .models import Invoice, Product, Customer, StockTransaction, Supplier, RestockInvoice, RestockItem, ReadyMix, ReadyMixIngredient

def print_nota(request, nomor_faktur):
    invoice = get_object_or_404(Invoice, nomor_faktur=nomor_faktur)
    
    # 1. Calculate the initial Subtotal
    subtotal = sum(item.subtotal for item in invoice.items.all())
    
    # 2. Calculate the Discount amount
    diskon_nominal = int(subtotal * (invoice.diskon_persen / 100))
    
    # 3. Calculate value after discount
    setelah_diskon = subtotal - diskon_nominal
    
    # 4. Calculate PPN amount
    ppn_nominal = int(setelah_diskon * (invoice.ppn_persen / 100))
    
    # 5. Calculate Final Grand Total
    grand_total = setelah_diskon + ppn_nominal
    
    context = {
        'invoice': invoice,
        'items': invoice.items.all(),
        'subtotal': subtotal,
        'diskon_nominal': diskon_nominal,
        'ppn_nominal': ppn_nominal,
        'grand_total': grand_total,
    }
    
    return render(request, 'sales/nota.html', context)


def get_product_price(request, kode_barang):
    try:
        # Find the product in the database
        product = Product.objects.get(kode_barang=kode_barang)
        # Send the price back to the browser
        return JsonResponse({'harga': product.harga_jual})
    except Product.DoesNotExist:
        # If something goes wrong, send 0
        return JsonResponse({'harga': 0})
    

def get_customer_tempo(request, kode_cust):
    try:
        customer = Customer.objects.get(kode_cust=kode_cust)
        return JsonResponse({'tempo_hari': customer.tempo_hari})
    except Customer.DoesNotExist:
        return JsonResponse({'tempo_hari': 0})


# --- NEW: PRODUCT LEDGER & DETAILS VIEW ---
def product_detail(request, kode_barang):
    # 1. Get the specific paint product
    product = get_object_or_404(Product, kode_barang=kode_barang)
    
    # 2. Get filter parameters
    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')
    
    # Default to current month/year if not provided
    from datetime import datetime
    current = datetime.now()
    if not selected_month:
        selected_month = str(current.month)
    if not selected_year:
        selected_year = str(current.year)
    
    # 3. Get the RAW history (every single transaction, newest first) - filtered
    raw_history = product.transactions.filter(
        created_at__year=selected_year,
        created_at__month=selected_month
    ).order_by('-created_at')
    
    # 4. Handle the "Group By" feature from the URL (e.g., ?group_by=customer)
    group_by = request.GET.get('group_by', 'none')
    
    grouped_data = None
    
    if group_by == 'type':
        # Groups by IN vs OUT
        grouped_data = raw_history.values('transaction_type').annotate(
            total_qty=Sum('qty'),
            transaction_count=Count('id')
        ).order_by('transaction_type')
        
    elif group_by == 'customer':
        # Groups by Customer Name (excluding 'IN' transactions)
        grouped_data = raw_history.filter(transaction_type='OUT').values(
            'customer__nama_cust' 
        ).annotate(
            total_qty=Sum('qty'),
            transaction_count=Count('id')
        ).order_by('-total_qty') 

    # 5. Calculate quick stats for the top of the page
    total_in = raw_history.filter(transaction_type='IN').aggregate(Sum('qty'))['qty__sum'] or 0
    total_out = raw_history.filter(transaction_type='OUT').aggregate(Sum('qty'))['qty__sum'] or 0
    current_stock = product.stok_saat_ini

    # 6. Send it all to the template
    from datetime import datetime
    current_year = datetime.now().year
    context = {
        'product': product,
        'raw_history': raw_history,
        'grouped_data': grouped_data,
        'group_by': group_by,
        'total_in': total_in,
        'total_out': total_out,
        'current_stock': current_stock,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months': [f"{i:02d}" for i in range(1, 13)],
        'years': [str(y) for y in range(current_year - 2, current_year + 5)],
    }
    
    return render(request, 'sales/product_detail.html', context)


# --- NEW: RESTOCK INVOICE CREATION ---
from django.shortcuts import render, redirect
from django.contrib import messages

@staff_member_required
def create_restock(request):
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        nomor_faktur = request.POST.get('nomor_faktur')
        tanggal = request.POST.get('tanggal') 
        tanggal_jatuh_tempo = request.POST.get('tanggal_jatuh_tempo')
        catatan = request.POST.get('catatan')
        
        supplier = Supplier.objects.get(id=supplier_id)
        
        invoice = RestockInvoice.objects.create(
            supplier=supplier,
            nomor_faktur=nomor_faktur,
            tanggal=tanggal, 
            tanggal_jatuh_tempo=tanggal_jatuh_tempo,
            catatan=catatan
        )

        kodes = request.POST.getlist('kode_barang[]')
        qtys = request.POST.getlist('qty[]')
        hargas = request.POST.getlist('harga_beli[]')
        
        total_hutang = 0
        
        for i in range(len(kodes)):
            product = Product.objects.get(kode_barang=kodes[i])
            qty = int(qtys[i])
            
            # Safely handle empty harga_beli fields (since we made them optional)
            harga_str = hargas[i]
            harga_beli = int(harga_str) if harga_str.strip() else 0
            
            subtotal = qty * harga_beli
            
            RestockItem.objects.create(
                restock_invoice=invoice,
                product=product,
                qty=qty,
                harga_beli=harga_beli,
                subtotal=subtotal
            )
            total_hutang += subtotal
            
        # Catch the PPN % from the form (default to 0 if left blank)
        ppn_persen = int(request.POST.get('ppn_persen', 0)) 
        ppn_nominal = int(total_hutang * (ppn_persen / 100.0))
        
        invoice.subtotal = total_hutang
        invoice.ppn_persen = ppn_persen
        invoice.grand_total = total_hutang + ppn_nominal
        invoice.save()
        
        return redirect('create_restock')

    # =========================================================
    # THE MISSING PART: What to do when just visiting the page
    # =========================================================
    suppliers = Supplier.objects.all()
    products = Product.objects.all()
    
    context = {
        'suppliers': suppliers,
        'products': products
    }
    
    # Note: Make sure the path matches where your HTML file is!
    # I used 'sales/create_restock.html' assuming you put it in your sales templates folder.
    return render(request, 'sales/create_restock.html', context)

@staff_member_required
def delete_stock_transaction(request, tx_id):
    if request.method == 'POST':
        transaction = get_object_or_404(StockTransaction, id=tx_id)
        product = transaction.product

        # 1. Delete the history row FIRST
        transaction.delete()

        # 2. THE MAGIC: Tell the product to recalculate itself based on what is left!
        product.update_stock_from_history()

        return redirect('product_detail', kode_barang=product.kode_barang)
    
    # --- FIX #8: Return proper error instead of None for non-POST requests ---
    return HttpResponseNotAllowed(['POST'])
    
def print_surat_jalan(request, nomor_faktur):
    from .models import Invoice, InvoiceItem
    invoice = get_object_or_404(Invoice, nomor_faktur=nomor_faktur)
    items = InvoiceItem.objects.filter(invoice=invoice)
    
    item_count = items.count()
    # Calculate how many empty rows we need to reach 12
    empty_row_count = max(0, 15 - item_count) 
    # Create a dummy list for Django to loop through (e.g., [0, 1, 2, 3, 4...])
    empty_rows = range(empty_row_count)
    
    context = {
        'invoice': invoice,
        'items': items,
        'empty_rows': empty_rows, # Pass the blank rows to the template!
    }
    return render(request, 'sales/surat_jalan.html', context)


# --- READY MIX ---
@staff_member_required
def create_readymix(request):
    if request.method == 'POST':
        from django.db import transaction as db_transaction

        tanggal = request.POST.get('tanggal')
        output_kode = request.POST.get('output_product')
        output_qty = int(request.POST.get('output_qty', 0))
        catatan = request.POST.get('catatan', '')

        ingredient_kodes = request.POST.getlist('ingredient_product[]')
        ingredient_qtys = request.POST.getlist('ingredient_qty[]')

        # Validate: at least 1 ingredient
        if not ingredient_kodes or not any(k.strip() for k in ingredient_kodes):
            messages.error(request, 'Harus ada minimal 1 bahan!')
            return redirect('create_readymix')

        # Validate: output qty must be positive
        if output_qty <= 0:
            messages.error(request, 'Jumlah hasil harus lebih dari 0!')
            return redirect('create_readymix')

        # Validate stock availability for each ingredient
        for i in range(len(ingredient_kodes)):
            kode = ingredient_kodes[i].strip()
            if not kode:
                continue
            qty = int(ingredient_qtys[i])
            product = Product.objects.get(kode_barang=kode)
            if product.stok_saat_ini < qty:
                messages.error(
                    request,
                    f'Stok {product.nama_barang} tidak cukup! '
                    f'Tersedia: {product.stok_saat_ini}, Diminta: {qty}'
                )
                return redirect('create_readymix')

        # All validations passed — process the mix inside a transaction
        with db_transaction.atomic():
            output_product = Product.objects.get(kode_barang=output_kode)

            ready_mix = ReadyMix.objects.create(
                tanggal=tanggal,
                output_product=output_product,
                output_qty=output_qty,
                catatan=catatan
            )

            # Build ingredient summary for the reference text
            ingredient_names = []

            # Deduct each ingredient
            for i in range(len(ingredient_kodes)):
                kode = ingredient_kodes[i].strip()
                if not kode:
                    continue
                qty = int(ingredient_qtys[i])
                ingredient = Product.objects.get(kode_barang=kode)

                ReadyMixIngredient.objects.create(
                    ready_mix=ready_mix,
                    product=ingredient,
                    qty=qty
                )

                # Deduct stock atomically
                Product.objects.filter(pk=ingredient.pk).update(
                    stok_saat_ini=F('stok_saat_ini') - qty
                )

                # Log the OUT transaction
                StockTransaction.objects.create(
                    product=ingredient,
                    transaction_type='OUT',
                    qty=qty,
                    reference=f"Ready Mix → {output_product.nama_barang}"
                )

                ingredient_names.append(f"{ingredient.nama_barang} ×{qty}")

            # Add output product stock
            Product.objects.filter(pk=output_product.pk).update(
                stok_saat_ini=F('stok_saat_ini') + output_qty
            )

            # Log the IN transaction
            bahan_text = ", ".join(ingredient_names)
            StockTransaction.objects.create(
                product=output_product,
                transaction_type='IN',
                qty=output_qty,
                reference=f"Ready Mix dari: {bahan_text}"
            )

        messages.success(request, f'✅ Ready Mix berhasil! {output_product.nama_barang} ×{output_qty} ditambahkan ke stok.')
        return redirect('create_readymix')

    # GET — render the form
    products = Product.objects.all().order_by('nama_barang')
    context = {
        'products': products
    }
    return render(request, 'sales/create_readymix.html', context)