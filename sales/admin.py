from django.contrib import admin
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from .models import Customer, Product, Invoice, InvoiceItem, Cashflow
from django.utils.html import format_html 
from django.http import HttpResponseRedirect # <--- Add this import at the very top of admin.py
from django.urls import reverse
from django.db.models import Sum
# pyrefly: ignore [missing-import]
from rangefilter.filters import DateRangeFilter
from datetime import datetime

# --- Tell the importer to use your custom columns instead of 'id' ---
class CustomerResource(resources.ModelResource):
    class Meta:
        model = Customer
        import_id_fields = ('kode_cust',)

class ProductResource(resources.ModelResource):
    class Meta:
        model = Product
        import_id_fields = ('kode_barang',)

# --- Invoice Export Resource ---
class InvoiceResource(resources.ModelResource):
    """Defines which columns appear when exporting Invoices to CSV/Excel."""

    nama_customer = fields.Field(
        column_name='Nama Customer',
        attribute='customer__nama_cust',
    )
    wilayah = fields.Field(
        column_name='Wilayah',
        attribute='customer__wilayah',
    )
    subtotal = fields.Field(column_name='Subtotal (Rp)')
    grand_total = fields.Field(column_name='Grand Total (Rp)')

    class Meta:
        model = Invoice
        # Explicit field order for the exported file
        fields = (
            'nomor_faktur',
            'tanggal',
            'tanggal_jatuh_tempo',
            'nama_customer',
            'wilayah',
            'sales',
            'status_pembayaran',
            'diskon_persen',
            'ppn_persen',
            'subtotal',
            'grand_total',
            'nomor_resi',
        )
        export_order = fields

    def dehydrate_subtotal(self, invoice):
        """Calculate subtotal from all items on this invoice."""
        return sum(item.subtotal for item in invoice.items.all())

    def dehydrate_grand_total(self, invoice):
        """Calculate grand total after discount and PPN."""
        subtotal = sum(item.subtotal for item in invoice.items.all())
        diskon = subtotal * (invoice.diskon_persen / 100)
        setelah_diskon = subtotal - diskon
        ppn = setelah_diskon * (invoice.ppn_persen / 100)
        return int(setelah_diskon + ppn)
# --------------------------------------------------------------------

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    autocomplete_fields = ['product']

class InvoiceAdmin(ImportExportModelAdmin):
    resource_classes = [InvoiceResource]
    inlines = [InvoiceItemInline]
    autocomplete_fields = ['customer']
    list_display = ('nomor_faktur', 'tanggal', 'customer', 'status_pembayaran', 'sudah_cetak', 'cetak_nota', 'cetak_surat_jalan')
    list_editable = ('sudah_cetak',)
    list_filter = (
        'status_pembayaran', 
        ('tanggal', DateRangeFilter) # Adds the From-To calendar!
    )
    
    search_fields = ('nomor_faktur', 'customer__nama_cust')
    change_list_template = "admin/sales/invoice/change_list.html"

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        
        # We only want to calculate the total if we successfully got a response with a ChangeList
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            cl = response.context_data['cl']
            
            # Calculate total based on the filtered queryset shown on the screen
            from django.db.models import Sum
            from .models import InvoiceItem
            
            # Get the exact invoices being shown right now
            filtered_invoices = cl.queryset
            
            # Sum up all items inside those specific invoices
            hasil = InvoiceItem.objects.filter(invoice__in=filtered_invoices).aggregate(total=Sum('subtotal'))
            
            if hasil['total']:
                response.context_data['summary_total'] = f"Rp {hasil['total']:,}".replace(',', '.')
                
                # Check if we are filtering by a specific customer to change the card title
                if 'customer__kode_cust__exact' in request.GET:
                    response.context_data['summary_title'] = "Grand Total Pembelanjaan Customer"
                else:
                    response.context_data['summary_title'] = "Total Nilai Faktur"

        return response

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        context.update({
            'show_save_and_continue': False,
            'show_save_and_add_another': False,
        })
        return super().render_change_form(request, context, add, change, form_url, obj)

    # 2. Redirect to the Print Page if they click our new button (When creating a new invoice)
    def response_add(self, request, obj, post_url_continue=None):
        if '_save_and_print' in request.POST:
            return HttpResponseRedirect(f'/print-nota/{obj.nomor_faktur}/')
        return super().response_add(request, obj, post_url_continue)

    # 3. Redirect to the Print Page if they click our new button (When editing an old invoice)
    def response_change(self, request, obj):
        if '_save_and_print' in request.POST:
            return HttpResponseRedirect(f'/print-nota/{obj.nomor_faktur}/')
        return super().response_change(request, obj)

    def cetak_nota(self, obj):
        return format_html(
            '<a class="button" style="background-color:#4CAF50; color:white; padding:4px 6px; border-radius:4px; font-size: 16px;" href="/print-nota/{}/" title="Cetak Nota" target="_blank">🖨️</a>', 
            obj.nomor_faktur
        )
    cetak_nota.short_description = 'Nota'
    class Media:
        css = {'all': ('admin/css/invoice_list.css?v=2',)}
        js = ('sales/js/invoice_math.js', 'sales/js/invoice_admin_autofill.js')

    def cetak_surat_jalan(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<a class="button" style="background-color:#17a2b8; color:white; padding:4px 6px; border-radius:4px; font-size: 16px;" href="/print-surat-jalan/{}/" title="Surat Jalan" target="_blank">🚚</a>', 
            obj.nomor_faktur
        )
    cetak_surat_jalan.short_description = 'S.Jln'

# ====================================================================
# NEW CODE FOR CUSTOMER HISTORY
# ====================================================================

# This puts the Read-Only Table inside the Customer Profile (Method 2)
class CustomerInvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0
    # Show these columns in the profile
    fields = ('nomor_faktur', 'tanggal', 'tanggal_jatuh_tempo', 'status_pembayaran', 'total_invoice', 'cetak_faktur')
    # Make them read-only so you don't accidentally edit an invoice from here
    readonly_fields = ('nomor_faktur', 'tanggal', 'tanggal_jatuh_tempo', 'status_pembayaran', 'total_invoice', 'cetak_faktur')
    can_delete = False
    
    # This prevents adding a new invoice from this screen (keeps it clean)
    def has_add_permission(self, request, obj=None):
        return False
    
    def total_invoice(self, obj):
        if obj.pk:
            from .models import InvoiceItem 
            from django.db.models import Sum # Make sure this is imported!
            
            # Sum up the subtotal of every item connected to THIS specific invoice
            hasil = InvoiceItem.objects.filter(invoice=obj).aggregate(grand_total=Sum('subtotal'))
            total = hasil['grand_total'] or 0 
            
            # Format the number beautifully (e.g., Rp 150.000) and make it bold
            formatted_total = f"Rp {total:,}".replace(',', '.')
            return format_html('<strong>{}</strong>', formatted_total)
        return "-"
    total_invoice.short_description = "Grand Total"
    
    def cetak_faktur(self, obj):
        # Only show the button if the invoice actually exists (obj.pk checks if it has an ID)
        if obj.pk:
            # Note: target="_blank" forces the print page to open in a new tab so you don't lose your spot!
            return format_html(
                '<a class="button" style="background-color:#28a745; color:white; padding:4px 10px; border-radius:4px; font-weight:bold; text-decoration:none;" href="/print-nota/{}/" target="_blank">🖨️ Print</a>',
                obj.nomor_faktur
            )
        return "-"
    
    # 3. Give the column a clean title
    cetak_faktur.short_description = "Aksi"

# This updates the main Customer list page
class CustomerAdmin(ImportExportModelAdmin):
    resource_classes = [CustomerResource]
    change_list_template = "admin/sales/customer/change_list.html"
    list_display = ('kode_cust', 'nama_cust', 'riwayat_faktur', 'no_telp', 'wilayah', 'tempo_hari', 'kode_sales')
    list_editable = ('tempo_hari', 'kode_sales')
    list_filter = ('wilayah',)
    search_fields = ('kode_cust', 'nama_cust')
    inlines = [CustomerInvoiceInline]

    # kode_cust is always read-only — it is auto-generated on save()
    readonly_fields = ('kode_cust',)

    class Media:
        js = ('sales/js/customer_admin.js',)

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        context.update({
            'show_save_and_continue': False,
            'show_save_and_add_another': False,
        })
        return super().render_change_form(request, context, add, change, form_url, obj)


    def riwayat_faktur(self, obj):
        return format_html(
            '<a class="button" style="background-color:#007bff; color:white; padding:4px 8px; border-radius:4px; font-weight:bold;" href="/admin/sales/invoice/?customer__kode_cust__exact={}">📋 Lihat Faktur</a>',
            obj.kode_cust
        )
    riwayat_faktur.short_description = 'Riwayat'

    def changelist_view(self, request, extra_context=None):
        # 1. Let Django build the page with any filters the user clicked
        response = super().changelist_view(request, extra_context=extra_context)

        # 2. Ensure we are loading the webpage (not a CSV export)
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            filtered_qs = response.context_data['cl'].queryset

            # 3. PIVOT TABLE MAGIC: Group by wilayah, sum the invoices!
            # THE FIX: We use 'items' because of your related_name='items' in models.py
            raw_regional_data = filtered_qs.values('wilayah').annotate(
                total_revenue=Sum('invoice__items__subtotal') 
            ).order_by('-total_revenue') # Sort from highest revenue to lowest

            # 4. Format the data into clean Rupiah strings for the HTML
            formatted_regional_data = []
            for item in raw_regional_data:
                region_name = item['wilayah'] or "Belum Ada Wilayah"
                revenue = item['total_revenue'] or 0

                # Only create a card if the region has actual revenue
                # if revenue > 0:
                formatted_revenue = f"Rp {revenue:,}".replace(',', '.')
                formatted_regional_data.append({
                    'wilayah': region_name,
                    'revenue': formatted_revenue
                })

            # print("DATA REGIONAL:", formatted_regional_data)

            # 5. Send our beautiful data to the screen!
            response.context_data['regional_turnover'] = formatted_regional_data

        return response

class ProductAdmin(ImportExportModelAdmin):
    resource_classes = [ProductResource]
    list_display = ('kode_barang', 'nama_barang', 'stok_saat_ini', 'harga_jual_rp', 'harga_beli', 'kategori', 'lihat_riwayat')
    list_editable = ('harga_beli',)  # Editable directly in the product list
    
    # UPDATE THIS LINE: Now it searches by name AND code
    search_fields = ('nama_barang', 'kode_barang')

    list_filter = ('kategori',)

    actions = ['auto_categorize_action', 'fix_negative_stock']

    @admin.action(description="⚡ Generate Kategori Otomatis (Update Massal)")
    def auto_categorize_action(self, request, queryset):
        count = 0
        for product in queryset:
            # By calling save() here, it triggers the new Regex math we just wrote in models.py!
            product.save() 
            count += 1
        
        # Shows a green success message at the top of the screen
        self.message_user(request, f"{count} produk berhasil dikategorikan otomatis!")

    @admin.action(description="🔧 Fix Stok Negatif ke 0 (Koreksi Otomatis)")
    def fix_negative_stock(self, request, queryset):
        from .models import StockTransaction
        negative_products = queryset.filter(stok_saat_ini__lt=0)
        count = 0
        for product in negative_products:
            correction_qty = abs(product.stok_saat_ini)
            # Add a correction transaction so the ledger balances to 0
            StockTransaction.objects.create(
                product=product,
                transaction_type='IN',
                qty=correction_qty,
                reference='Koreksi Otomatis: Stok Negatif → 0'
            )
            # Recalculate stock from the full ledger history
            product.update_stock_from_history()
            count += 1
        self.message_user(request, f"✅ {count} produk berhasil dikoreksi dari stok negatif ke 0!")
    
    def harga_jual_rp(self, obj):
        # Adds commas for thousands, then swaps them to dots for Indonesia
        return f"Rp {obj.harga_jual:,}".replace(',', '.')
    harga_jual_rp.short_description = "Harga Jual"

    def harga_beli_rp(self, obj):
        return f"Rp {obj.harga_beli:,}".replace(',', '.')
    harga_beli_rp.short_description = "Harga Beli"
    
    def lihat_riwayat(self, obj):
        return format_html(
            '<a class="button" style="background-color:#17a2b8; color:white; padding:4px 8px; border-radius:4px; font-weight:bold;" href="/product/{}/" target="_blank">📊 Riwayat Stok</a>',
            obj.kode_barang
        )
    lihat_riwayat.short_description = 'Riwayat'

# --- Connect those rules to the Admin dashboard ---
admin.site.register(Customer, CustomerAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(Invoice, InvoiceAdmin)

# --- NEW MODELS ---
from .models import Supplier, RestockInvoice, RestockItem, StockTransaction

class RestockItemInline(admin.TabularInline):
    model = RestockItem
    extra = 1
    autocomplete_fields = ['product']

class SupplierRestockInline(admin.TabularInline):
    model = RestockInvoice
    extra = 0
    # The columns you want to see in the Supplier profile
    fields = ('detail_link', 'tanggal', 'tanggal_jatuh_tempo', 'grand_total')
    readonly_fields = ('detail_link', 'tanggal', 'tanggal_jatuh_tempo', 'grand_total')
    can_delete = False

    def detail_link(self, obj):
        if obj.pk:
            url = reverse('admin:sales_restockinvoice_change', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.nomor_faktur)
        return "-"
    detail_link.short_description = "Nomor Faktur"

    def has_add_permission(self, request, obj=None):
        return False # Prevents adding new invoices directly from the profile

    # --- THIS MAGIC FUNCTION FILTERS FOR THE CURRENT MONTH ---
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        today = datetime.today()
        # Only return invoices where the year and month match right now
        return qs.filter(tanggal__year=today.year, tanggal__month=today.month)


# Create the new SupplierAdmin to attach the inline
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('nama_supplier', 'rekening_bank')
    search_fields = ('nama_supplier',)
    inlines = [SupplierRestockInline] # Attach the inline here!

class RestockInvoiceAdmin(admin.ModelAdmin):
    inlines = [RestockItemInline]
    list_display = ('nomor_faktur', 'supplier', 'tanggal', 'tanggal_jatuh_tempo', 'subtotal', 'grand_total')
    list_filter = (
        'supplier', 
        ('tanggal', DateRangeFilter), 
        ('tanggal_jatuh_tempo', DateRangeFilter), 
    )
    search_fields = ('nomor_faktur', 'supplier__nama_supplier')

    def add_view(self, request, form_url='', extra_context=None):
        return HttpResponseRedirect(reverse('create_restock'))

    # --- ADD THIS NEW FUNCTION ---
    def changelist_view(self, request, extra_context=None):
        # 1. Let Django build the standard page with all the filters applied
        response = super().changelist_view(request, extra_context=extra_context)

        # 2. Safety check: Ensure we are loading the webpage (not downloading a CSV, etc.)
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            
            # 3. cl.queryset contains ONLY the rows that survived the user's filters!
            filtered_qs = response.context_data['cl'].queryset
            from django.db.models import Sum
            
            # Sum up the grand_total of the visible rows
            total = filtered_qs.aggregate(Sum('grand_total'))['grand_total__sum'] or 0
            formatted_total = f"Rp {total:,}".replace(',', '.')
            
            # 4. Inject our math into the webpage's data dictionary
            response.context_data['filtered_grand_total'] = formatted_total

        return response

class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('product', 'transaction_type', 'qty', 'customer', 'reference', 'created_at')
    list_filter = (
        'transaction_type', 
        ('created_at', DateRangeFilter) # Adds the From-To calendar for the exact timestamps!
    )
    search_fields = ('product__nama_barang', 'reference')

admin.site.register(Supplier, SupplierAdmin)
admin.site.register(RestockInvoice, RestockInvoiceAdmin)
admin.site.register(StockTransaction, StockTransactionAdmin)

@admin.register(Cashflow)
class CashflowAdmin(admin.ModelAdmin):
    # --- 1. TELL DJANGO TO USE A CUSTOM TEMPLATE ---
    # Create the folder 'sales' and 'cashflow' inside your templates/admin folder if they don't exist
    change_list_template = "admin/sales/cashflow/change_list.html" 

    list_display = ('tanggal', 'nama_transaksi', 'tampil_debit', 'tampil_kredit', 'status_pembayaran', 'keterangan')
    list_filter = (
        'jenis_transaksi', 
        'status_pembayaran', 
        ('tanggal', DateRangeFilter), 
    )
    search_fields = ('nama_transaksi', 'keterangan')
    date_hierarchy = 'tanggal'

    def tampil_debit(self, obj):
        if obj.jenis_transaksi == 'IN':
            return f"Rp {obj.nominal:,.0f}".replace(',', '.')
        return "-"
    tampil_debit.short_description = "DEBIT"

    def tampil_kredit(self, obj):
        if obj.jenis_transaksi == 'OUT':
            return f"Rp {obj.nominal:,.0f}".replace(',', '.')
        return "-"
    tampil_kredit.short_description = "KREDIT"

    # --- 2. THE MAGICAL MATH ENGINE ---
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)

        # Ensure we are actually rendering the dashboard (not exporting a file)
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            # Grab the CURRENTLY FILTERED data on the screen
            qs = response.context_data['cl'].queryset

            # Sum up the nominals, but ONLY if they are actually LUNAS (No Ghost Money!)
            total_in = qs.filter(jenis_transaksi='IN', status_pembayaran='LUNAS').aggregate(Sum('nominal'))['nominal__sum'] or 0
            total_out = qs.filter(jenis_transaksi='OUT', status_pembayaran='LUNAS').aggregate(Sum('nominal'))['nominal__sum'] or 0
            saldo_bersih = total_in - total_out

            # Format the numbers perfectly and send them to the HTML
            response.context_data['summary_in'] = f"Rp {total_in:,.0f}".replace(',', '.')
            response.context_data['summary_out'] = f"Rp {total_out:,.0f}".replace(',', '.')
            response.context_data['summary_saldo'] = f"Rp {saldo_bersih:,.0f}".replace(',', '.')

        return response

# --- READY MIX ---
from .models import ReadyMix, ReadyMixIngredient, ReadyMixOutput

class ReadyMixOutputInline(admin.TabularInline):
    model = ReadyMixOutput
    extra = 0
    readonly_fields = ('product', 'qty')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

class ReadyMixIngredientInline(admin.TabularInline):
    model = ReadyMixIngredient
    extra = 0
    readonly_fields = ('product', 'qty')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(ReadyMix)
class ReadyMixAdmin(admin.ModelAdmin):
    inlines = [ReadyMixOutputInline, ReadyMixIngredientInline]
    list_display = ('tanggal', 'jenis', 'cetak_faktur', 'nomor_faktur', 'ringkasan_hasil', 'ringkasan_bahan', 'created_at')
    list_filter = ('jenis', ('tanggal', DateRangeFilter))
    search_fields = ('nomor_faktur', 'outputs__product__nama_barang')

    def cetak_faktur(self, obj):
        if obj.jenis == 'Ready Mix':
            return format_html(
                '<a class="button" style="background-color:#28a745; color:white; padding:4px 8px; border-radius:4px; font-weight:bold; text-decoration:none;" href="/print-readymix/{}/" target="_blank">🖨️ Cetak</a>',
                obj.pk
            )
        return "-"
    cetak_faktur.short_description = "Cetak"

    def ringkasan_hasil(self, obj):
        outputs = obj.outputs.all()
        if outputs:
            parts = [f"{out.product.nama_barang} ×{out.qty}" for out in outputs]
            return ", ".join(parts)
        return "-"
    ringkasan_hasil.short_description = "Produk Hasil"

    def ringkasan_bahan(self, obj):
        ingredients = obj.ingredients.all()
        if ingredients:
            parts = [f"{ing.product.nama_barang} ×{ing.qty}" for ing in ingredients]
            return ", ".join(parts)
        return "-"
    ringkasan_bahan.short_description = "Bahan Dipakai"

    # Clicking "+ Add Ready Mix" in admin goes to the custom form page
    def add_view(self, request, form_url='', extra_context=None):
        return HttpResponseRedirect(reverse('create_readymix'))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return HttpResponseRedirect(reverse('edit_readymix', args=[object_id]))
