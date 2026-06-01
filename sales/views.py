from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseNotAllowed
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count, F
from .models import Invoice, Product, Customer, StockTransaction, Supplier, RestockInvoice, RestockItem, ReadyMix, ReadyMixIngredient, ReadyMixOutput

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
    
    items = invoice.items.all()[:13]
    item_count = len(list(items))
    empty_rows = range(max(0, 13 - item_count))

    context = {
        'invoice': invoice,
        'items': items,
        'empty_rows': empty_rows,
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
        # Send the price back to the browser (harga_beli used by restock form)
        return JsonResponse({
            'harga': product.harga_jual,
            'harga_beli': product.harga_beli,
        })
    except Product.DoesNotExist:
        # If something goes wrong, send 0
        return JsonResponse({'harga': 0, 'harga_beli': 0})
    

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
    empty_row_count = max(0, 13 - item_count) 
    # Create a dummy list for Django to loop through (e.g., [0, 1, 2, 3, 4...])
    empty_rows = range(empty_row_count)
    
    context = {
        'invoice': invoice,
        'items': items,
        'empty_rows': empty_rows, # Pass the blank rows to the template!
    }
    return render(request, 'sales/surat_jalan.html', context)


# --- READY MIX / MOVING ---
@staff_member_required
def create_readymix(request):
    if request.method == 'POST':
        from django.db import transaction as db_transaction

        jenis = request.POST.get('jenis', 'Ready Mix')
        tanggal = request.POST.get('tanggal')
        nomor_faktur = request.POST.get('nomor_faktur', '')

        output_kodes = request.POST.getlist('output_product[]')
        output_qtys = request.POST.getlist('output_qty[]')

        ingredient_kodes = request.POST.getlist('ingredient_product[]')
        ingredient_qtys = request.POST.getlist('ingredient_qty[]')

        # Clean and validate output list
        cleaned_outputs = []
        for i in range(len(output_kodes)):
            kode = output_kodes[i].strip()
            if not kode:
                continue
            try:
                qty = int(output_qtys[i])
            except (ValueError, TypeError):
                qty = 0
            if qty <= 0:
                messages.error(request, 'Jumlah hasil produk harus lebih dari 0!')
                return redirect('create_readymix')
            cleaned_outputs.append((kode, qty))

        # Clean and validate input list
        cleaned_ingredients = []
        for i in range(len(ingredient_kodes)):
            kode = ingredient_kodes[i].strip()
            if not kode:
                continue
            try:
                qty = int(ingredient_qtys[i])
            except (ValueError, TypeError):
                qty = 0
            if qty <= 0:
                messages.error(request, 'Jumlah bahan harus lebih dari 0!')
                return redirect('create_readymix')
            cleaned_ingredients.append((kode, qty))

        if not cleaned_outputs:
            messages.error(request, 'Harus ada minimal 1 produk hasil (output)!')
            return redirect('create_readymix')

        if not cleaned_ingredients:
            messages.error(request, 'Harus ada minimal 1 bahan (input)!')
            return redirect('create_readymix')

        # Validate stock availability for each ingredient
        for kode, qty in cleaned_ingredients:
            product = Product.objects.get(kode_barang=kode)
            if product.stok_saat_ini < qty:
                messages.error(
                    request,
                    f'Stok {product.nama_barang} tidak cukup! '
                    f'Tersedia: {product.stok_saat_ini}, Diminta: {qty}'
                )
                return redirect('create_readymix')

        # All validations passed — process inside a transaction
        with db_transaction.atomic():
            ready_mix = ReadyMix.objects.create(
                jenis=jenis,
                tanggal=tanggal,
                nomor_faktur=nomor_faktur
            )

            # Deduct each ingredient (Input)
            ingredient_names = []
            for kode, qty in cleaned_ingredients:
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
                ingredient_names.append(f"{ingredient.nama_barang} ×{qty}")

            # Add each output product (Output)
            output_names = []
            for kode, qty in cleaned_outputs:
                output_product = Product.objects.get(kode_barang=kode)
                ReadyMixOutput.objects.create(
                    ready_mix=ready_mix,
                    product=output_product,
                    qty=qty
                )
                # Add stock atomically
                Product.objects.filter(pk=output_product.pk).update(
                    stok_saat_ini=F('stok_saat_ini') + qty
                )
                output_names.append(f"{output_product.nama_barang} ×{qty}")

            # Build summaries
            outputs_summary_text = ", ".join(output_names)
            ingredients_summary_text = ", ".join(ingredient_names)

            # Log OUT transactions for ingredients
            for kode, qty in cleaned_ingredients:
                ingredient = Product.objects.get(kode_barang=kode)
                StockTransaction.objects.create(
                    product=ingredient,
                    transaction_type='OUT',
                    qty=qty,
                    reference=jenis,
                    readymix=ready_mix
                )

            # Log IN transactions for outputs
            for kode, qty in cleaned_outputs:
                output_product = Product.objects.get(kode_barang=kode)
                StockTransaction.objects.create(
                    product=output_product,
                    transaction_type='IN',
                    qty=qty,
                    reference=jenis,
                    readymix=ready_mix
                )

        messages.success(request, f'✅ Proses {jenis} berhasil! Stok telah diperbarui.')
        return redirect('create_readymix')

    # GET — render the form
    products = Product.objects.all().order_by('nama_barang')
    context = {
        'products': products
    }
    return render(request, 'sales/create_readymix.html', context)


@staff_member_required
def edit_readymix(request, pk):
    from .models import ReadyMix, ReadyMixIngredient, ReadyMixOutput, Product, StockTransaction
    from django.db.models import F
    from django.db import transaction as db_transaction

    ready_mix = get_object_or_404(ReadyMix, pk=pk)

    if request.method == 'POST':
        jenis = request.POST.get('jenis', 'Ready Mix')
        tanggal = request.POST.get('tanggal')
        nomor_faktur = request.POST.get('nomor_faktur', '')

        output_kodes = request.POST.getlist('output_product[]')
        output_qtys = request.POST.getlist('output_qty[]')

        ingredient_kodes = request.POST.getlist('ingredient_product[]')
        ingredient_qtys = request.POST.getlist('ingredient_qty[]')

        # Clean and validate output list
        cleaned_outputs = []
        for i in range(len(output_kodes)):
            kode = output_kodes[i].strip()
            if not kode:
                continue
            try:
                qty = int(output_qtys[i])
            except (ValueError, TypeError):
                qty = 0
            if qty <= 0:
                messages.error(request, 'Jumlah hasil produk harus lebih dari 0!')
                return redirect('edit_readymix', pk=pk)
            cleaned_outputs.append((kode, qty))

        # Clean and validate input list
        cleaned_ingredients = []
        for i in range(len(ingredient_kodes)):
            kode = ingredient_kodes[i].strip()
            if not kode:
                continue
            try:
                qty = int(ingredient_qtys[i])
            except (ValueError, TypeError):
                qty = 0
            if qty <= 0:
                messages.error(request, 'Jumlah bahan harus lebih dari 0!')
                return redirect('edit_readymix', pk=pk)
            cleaned_ingredients.append((kode, qty))

        if not cleaned_outputs:
            messages.error(request, 'Harus ada minimal 1 produk hasil (output)!')
            return redirect('edit_readymix', pk=pk)

        if not cleaned_ingredients:
            messages.error(request, 'Harus ada minimal 1 bahan (input)!')
            return redirect('edit_readymix', pk=pk)

        # Get existing ingredients to calculate stock offsets
        existing_ingredients = {ing.product.kode_barang: ing.qty for ing in ready_mix.ingredients.all()}

        # Validate stock availability for each ingredient (taking into account original transaction quantities)
        for kode, qty in cleaned_ingredients:
            product = Product.objects.get(kode_barang=kode)
            old_qty = existing_ingredients.get(kode, 0)
            max_available = product.stok_saat_ini + old_qty
            if max_available < qty:
                messages.error(
                    request,
                    f'Stok {product.nama_barang} tidak cukup! '
                    f'Tersedia: {product.stok_saat_ini} (Original: {old_qty}), Diminta: {qty}'
                )
                return redirect('edit_readymix', pk=pk)

        # Process inside a transaction
        with db_transaction.atomic():
            # Track all products involved in the original transaction
            affected_products = set()
            for ing in ready_mix.ingredients.all():
                affected_products.add(ing.product)
            for out in ready_mix.outputs.all():
                affected_products.add(out.product)

            # Delete old ingredients, outputs, and stock transactions
            ready_mix.ingredients.all().delete()
            ready_mix.outputs.all().delete()
            ready_mix.stock_transactions.all().delete()

            # Update ready_mix fields
            ready_mix.jenis = jenis
            ready_mix.tanggal = tanggal
            ready_mix.nomor_faktur = nomor_faktur
            ready_mix.save()

            # Deduct each ingredient (Input)
            ingredient_names = []
            for kode, qty in cleaned_ingredients:
                ingredient = Product.objects.get(kode_barang=kode)
                ReadyMixIngredient.objects.create(
                    ready_mix=ready_mix,
                    product=ingredient,
                    qty=qty
                )
                affected_products.add(ingredient)
                ingredient_names.append(f"{ingredient.nama_barang} ×{qty}")

            # Add each output product (Output)
            output_names = []
            for kode, qty in cleaned_outputs:
                output_product = Product.objects.get(kode_barang=kode)
                ReadyMixOutput.objects.create(
                    ready_mix=ready_mix,
                    product=output_product,
                    qty=qty
                )
                affected_products.add(output_product)
                output_names.append(f"{output_product.nama_barang} ×{qty}")

            # Build summaries
            outputs_summary_text = ", ".join(output_names)
            ingredients_summary_text = ", ".join(ingredient_names)

            # Log OUT transactions for ingredients
            for kode, qty in cleaned_ingredients:
                ingredient = Product.objects.get(kode_barang=kode)
                StockTransaction.objects.create(
                    product=ingredient,
                    transaction_type='OUT',
                    qty=qty,
                    reference=jenis,
                    readymix=ready_mix
                )

            # Log IN transactions for outputs
            for kode, qty in cleaned_outputs:
                output_product = Product.objects.get(kode_barang=kode)
                StockTransaction.objects.create(
                    product=output_product,
                    transaction_type='IN',
                    qty=qty,
                    reference=jenis,
                    readymix=ready_mix
                )

            # Recalculate stock for all affected products
            for product in affected_products:
                product.update_stock_from_history()

        messages.success(request, f'✅ Edit {jenis} berhasil! Stok telah diperbarui.')
        return redirect('/admin/sales/readymix/')

    # GET — render the form
    products = Product.objects.all().order_by('nama_barang')
    ingredients = ready_mix.ingredients.all()
    outputs = ready_mix.outputs.all()
    context = {
        'ready_mix': ready_mix,
        'ingredients': ingredients,
        'outputs': outputs,
        'products': products
    }
    return render(request, 'sales/create_readymix.html', context)


@staff_member_required
def print_readymix(request, pk):
    from .models import ReadyMix
    from django.http import Http404
    ready_mix = get_object_or_404(ReadyMix, pk=pk)
    if ready_mix.jenis != 'Ready Mix':
        raise Http404("Faktur hanya tersedia untuk transaksi Ready Mix.")
    
    outputs = list(ready_mix.outputs.all())
    ingredients = list(ready_mix.ingredients.all())
    max_len = max(len(outputs), len(ingredients))
    
    rows = []
    for i in range(max(max_len, 13)):
        out = outputs[i] if i < len(outputs) else None
        ing = ingredients[i] if i < len(ingredients) else None
        rows.append({
            'output': out,
            'ingredient': ing
        })
        
    context = {
        'ready_mix': ready_mix,
        'rows': rows,
    }
    return render(request, 'sales/print_readymix.html', context)


@staff_member_required
def dashboard(request):
    years = Invoice.objects.dates('tanggal', 'year', order='DESC')
    year_list = [y.year for y in years]
    if not year_list:
        import datetime
        year_list = [datetime.date.today().year]
    
    wilayah_list = list(Customer.objects.values_list('wilayah', flat=True).distinct())
    wilayah_list = sorted([w for w in wilayah_list if w])
    
    sales_list = list(Invoice.objects.values_list('sales', flat=True).distinct())
    sales_list = sorted([s for s in sales_list if s])

    context = {
        'years': year_list,
        'wilayah_list': wilayah_list,
        'sales_list': sales_list,
    }
    return render(request, 'sales/dashboard.html', context)

@staff_member_required
def dashboard_data_api(request):
    import datetime
    selected_year = int(request.GET.get('year', datetime.date.today().year))
    filter_wilayah = request.GET.get('wilayah', '').strip()
    filter_sales = request.GET.get('sales', '').strip()

    # 1. Fetch all customers (filtered by wilayah if set)
    customers = Customer.objects.all()
    if filter_wilayah:
        customers = customers.filter(wilayah__iexact=filter_wilayah)

    # Initialize matrix structure for all matching customers
    matrix_dict = {}
    for cust in customers:
        matrix_dict[cust.kode_cust] = {
            'customer_id': cust.kode_cust,
            'customer_name': cust.nama_cust,
            'months': [0.0] * 12,
            'total_ytd': 0.0
        }

    # 2. Fetch invoices and filter
    invoices = Invoice.objects.filter(tanggal__year=selected_year).select_related('customer')
    if filter_wilayah:
        invoices = invoices.filter(customer__wilayah__iexact=filter_wilayah)
    if filter_sales:
        invoices = invoices.filter(sales=filter_sales)

    invoice_pks = [inv.nomor_faktur for inv in invoices]
    
    from collections import defaultdict
    items_by_invoice = defaultdict(list)
    
    from .models import InvoiceItem
    if invoice_pks:
        items = InvoiceItem.objects.filter(invoice_id__in=invoice_pks)
        for item in items:
            items_by_invoice[item.invoice_id].append(item)

    total_revenue_ytd = 0.0
    active_customers = set()
    total_invoices_count = 0
    
    monthly_sales_trend = defaultdict(float)
    
    for inv in invoices:
        inv_items = items_by_invoice[inv.nomor_faktur]
        subtotal = sum(item.subtotal for item in inv_items)
        diskon = subtotal * (inv.diskon_persen / 100.0)
        setelah_diskon = subtotal - diskon
        ppn = setelah_diskon * (inv.ppn_persen / 100.0)
        grand_total = setelah_diskon + ppn
        
        month = inv.tanggal.month
        cust_id = inv.customer_id
        
        if cust_id in matrix_dict:
            matrix_dict[cust_id]['months'][month-1] += grand_total
            matrix_dict[cust_id]['total_ytd'] += grand_total
        
        total_revenue_ytd += grand_total
        active_customers.add(cust_id)
        total_invoices_count += 1
        
        monthly_sales_trend[month] += grand_total

    # Convert dictionary to list and sort by total_ytd descending
    matrix_data = list(matrix_dict.values())
    matrix_data.sort(key=lambda x: (-x['total_ytd'], x['customer_name']))

    # Top customer and chart calculation (only using customers with actual sales)
    actual_sales_customers = [x for x in matrix_data if x['total_ytd'] > 0]
    top_customer_name = "-"
    top_customer_val = 0.0
    if actual_sales_customers:
        top_customer_name = actual_sales_customers[0]['customer_name']
        top_customer_val = actual_sales_customers[0]['total_ytd']

    aov = total_revenue_ytd / total_invoices_count if total_invoices_count > 0 else 0.0

    trend_data = [monthly_sales_trend[m] for m in range(1, 13)]

    top_customers_chart = []
    for row in actual_sales_customers[:5]:
        top_customers_chart.append({
            'name': row['customer_name'],
            'value': row['total_ytd']
        })

    other_total = sum(row['total_ytd'] for row in actual_sales_customers[5:])
    if other_total > 0:
        top_customers_chart.append({
            'name': 'Lainnya',
            'value': other_total
        })

    response_data = {
        'kpis': {
            'total_revenue_ytd': total_revenue_ytd,
            'active_customers': len(active_customers),
            'aov': aov,
            'top_customer_name': top_customer_name,
            'top_customer_val': top_customer_val,
        },
        'trend_data': trend_data,
        'top_customers': top_customers_chart,
        'matrix_table': matrix_data,
    }
    return JsonResponse(response_data)


@staff_member_required
def rekap_yudi(request):
    import datetime
    from collections import defaultdict
    from django.db.models import Sum

    today = datetime.date.today()
    selected_month = int(request.GET.get('month', today.month))
    selected_year = int(request.GET.get('year', today.year))

    # --- 1. Gather ReadyMixIngredient data (Bahan consumed) — Ready Mix only ---
    ingredients = (
        ReadyMixIngredient.objects
        .filter(
            ready_mix__jenis='Ready Mix',
            ready_mix__tanggal__year=selected_year,
            ready_mix__tanggal__month=selected_month,
        )
        .values('ready_mix__tanggal', 'product__kategori')
        .annotate(total_qty=Sum('qty'))
    )

    bahan_by_day = defaultdict(lambda: {'PU': 0, 'NC': 0})
    for row in ingredients:
        day = row['ready_mix__tanggal'].day
        kat = (row['product__kategori'] or '').upper()
        if kat in ('PU', 'NC'):
            bahan_by_day[day][kat] += row['total_qty']

    # --- 2. Gather ReadyMixOutput data (Ready Mix produced) — Ready Mix only ---
    outputs = (
        ReadyMixOutput.objects
        .filter(
            ready_mix__jenis='Ready Mix',
            ready_mix__tanggal__year=selected_year,
            ready_mix__tanggal__month=selected_month,
        )
        .values('ready_mix__tanggal', 'product__kategori')
        .annotate(total_qty=Sum('qty'))
    )

    rm_by_day = defaultdict(lambda: {'PU': 0, 'NC': 0})
    for row in outputs:
        day = row['ready_mix__tanggal'].day
        kat = (row['product__kategori'] or '').upper()
        if kat in ('PU', 'NC'):
            rm_by_day[day][kat] += row['total_qty']

    # --- 3. Gather ReadyMix faktur list per day (Ready Mix only, not Moving) ---
    readymix_records = (
        ReadyMix.objects
        .filter(
            jenis='Ready Mix',
            tanggal__year=selected_year,
            tanggal__month=selected_month,
        )
        .order_by('tanggal', 'pk')
    )

    faktur_by_day = defaultdict(list)
    for rm in readymix_records:
        faktur_by_day[rm.tanggal.day].append({
            'pk': rm.pk,
            'nomor_faktur': rm.nomor_faktur,
        })

    # --- 4. Build day rows ---
    import calendar
    days_in_month = calendar.monthrange(selected_year, selected_month)[1]

    rows = []
    totals = {'bahan_pu': 0, 'bahan_nc': 0, 'rm_pu': 0, 'rm_nc': 0}

    for day in range(1, days_in_month + 1):
        bahan_pu = bahan_by_day[day]['PU']
        bahan_nc = bahan_by_day[day]['NC']
        rm_pu = rm_by_day[day]['PU']
        rm_nc = rm_by_day[day]['NC']
        faktur_list = faktur_by_day[day]

        totals['bahan_pu'] += bahan_pu
        totals['bahan_nc'] += bahan_nc
        totals['rm_pu'] += rm_pu
        totals['rm_nc'] += rm_nc

        rows.append({
            'day': day,
            'bahan_pu': bahan_pu,
            'bahan_nc': bahan_nc,
            'rm_pu': rm_pu,
            'rm_nc': rm_nc,
            'faktur_list': faktur_list,
            'has_data': bool(bahan_pu or bahan_nc or rm_pu or rm_nc or faktur_list),
        })

    # --- Difference: Bahan consumed minus Ready Mix produced ---
    totals['selisih_pu'] = totals['bahan_pu'] - totals['rm_pu']
    totals['selisih_nc'] = totals['bahan_nc'] - totals['rm_nc']

    # --- 5. Build year list for filter ---
    from .models import ReadyMix as RM
    year_dates = RM.objects.dates('tanggal', 'year', order='DESC')
    year_list = [d.year for d in year_dates]
    if not year_list:
        year_list = [today.year]
    if today.year not in year_list:
        year_list.insert(0, today.year)

    month_names = [
        (1, 'Januari'), (2, 'Februari'), (3, 'Maret'), (4, 'April'),
        (5, 'Mei'), (6, 'Juni'), (7, 'Juli'), (8, 'Agustus'),
        (9, 'September'), (10, 'Oktober'), (11, 'November'), (12, 'Desember'),
    ]

    context = {
        'rows': rows,
        'totals': totals,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'year_list': year_list,
        'month_names': month_names,
    }
    return render(request, 'sales/rekap_yudi.html', context)


# --- AJAX: Next Customer Code Preview ---
def ajax_next_customer_code(request):
    """
    Returns the next available kode_cust for a given wilayah.
    Used by customer_admin.js to live-preview the code before saving.
    GET /api/next-customer-code/?wilayah=Jawa+Tengah → {"kode_cust": "JT-029"}
    """
    from .models import WILAYAH_PREFIX_MAP
    wilayah = request.GET.get('wilayah', '').strip()
    if not wilayah:
        return JsonResponse({'kode_cust': ''})

    prefix = WILAYAH_PREFIX_MAP.get(wilayah, wilayah[:2].upper())
    last = (
        Customer.objects
        .filter(kode_cust__startswith=f"{prefix}-")
        .order_by('-kode_cust')
        .first()
    )
    if last:
        try:
            seq = int(last.kode_cust.split('-')[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    else:
        seq = 1
    return JsonResponse({'kode_cust': f"{prefix}-{seq:03d}"})


# --- AJAX: Get Customer's Kode Sales ---
def ajax_customer_sales(request):
    """
    Returns the kode_sales for a given customer.
    Used by invoice_admin.js to auto-fill the sales field when a customer is selected.
    GET /api/customer-sales/?kode_cust=JT-001 → {"kode_sales": "A1"}
    """
    kode_cust = request.GET.get('kode_cust', '').strip()
    if not kode_cust:
        return JsonResponse({'kode_sales': ''})
    try:
        customer = Customer.objects.get(kode_cust=kode_cust)
        return JsonResponse({'kode_sales': customer.kode_sales or ''})
    except Customer.DoesNotExist:
        return JsonResponse({'kode_sales': ''})