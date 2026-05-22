from django.db import models, transaction
from datetime import timedelta
from django.utils import timezone
import datetime
from django.db.models import F
from django.core.exceptions import ValidationError
import re

class Customer(models.Model):
    kode_cust = models.CharField(max_length=20, primary_key=True) # e.g., JT-001
    nama_cust = models.CharField(max_length=200) # e.g., ABADI BANYUMAS
    alamat = models.TextField(blank=True, null=True)
    wilayah = models.CharField(max_length=100) # e.g., JAWA TENGAH
    no_telp = models.CharField(max_length=20, blank=True, null=True, help_text="Contoh: 0812-3456-7890")
    tempo_hari = models.IntegerField(default=60, help_text="Batas pembayaran dalam hari (Contoh: 30 untuk 1 bulan, 60 untuk 2 bulan)")

    def __str__(self):
        return self.nama_cust

class Product(models.Model):
    kode_barang = models.CharField(max_length=50, primary_key=True) # e.g., NC 800
    nama_barang = models.CharField(max_length=200) # e.g., NC 800 NC White
    
    # --- ADD THE NEW CATEGORY FIELD HERE ---
    kategori = models.CharField(max_length=20, blank=True, null=True, help_text="Terisi otomatis dari Kode Barang (contoh: TH, NC)")
    
    harga_jual = models.IntegerField() # e.g., 72000
    stok_saat_ini = models.IntegerField(default=0)
    

    # --- 1. THE MEMORY FUNCTION (Keep exactly as is) ---
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # When Django loads the product, remember the current stock
        self._original_stock = self.stok_saat_ini

    # --- 2. THE SMART SAVE FUNCTION (Merged!) ---
    def save(self, *args, **kwargs):
        
        # --- BULLETPROOF CATEGORY EXTRACTOR ---
        if self.kode_barang:
            # Grabs the first block of text (e.g., "NC-800" -> "NC", "TH CS" -> "TH")
            match = re.search(r'^([A-Za-z]+)', str(self.kode_barang))
            if match:
                self.kategori = match.group(1).upper()

        # Determine if this is a brand new product being created
        is_new = self._state.adding

        # Save the product normally first so it exists in the database
        super().save(*args, **kwargs)

        skip_log = getattr(self, '_skip_manual_log', False)
        
        # Check if the stock number changed on an existing product
        if not is_new and self.stok_saat_ini != self._original_stock and not skip_log:
            difference = self.stok_saat_ini - self._original_stock
            
            if difference > 0:
                StockTransaction.objects.create(
                    product=self,
                    transaction_type='IN',
                    qty=difference,
                    reference='Manual Admin Adjustment (Stock Added)'
                )
            else:
                StockTransaction.objects.create(
                    product=self,
                    transaction_type='OUT',
                    qty=abs(difference),
                    reference='Manual Admin Adjustment (Stock Removed)'
                )
                
        # Check if it is a brand new product that was created with starting stock
        elif is_new and self.stok_saat_ini > 0:
            StockTransaction.objects.create(
                product=self,
                transaction_type='IN',
                qty=self.stok_saat_ini,
                reference='Initial Stock on Creation'
            )

        # Update the memory to the new stock number
        self._original_stock = self.stok_saat_ini

    
    def update_stock_from_history(self):
        from django.db.models import Sum
        
        # 1. Sum up all 'IN' transactions for this specific product
        total_in = self.transactions.filter(transaction_type='IN').aggregate(Sum('qty'))['qty__sum'] or 0
        
        # 2. Sum up all 'OUT' transactions
        total_out = self.transactions.filter(transaction_type='OUT').aggregate(Sum('qty'))['qty__sum'] or 0
        
        # 3. Calculate absolute reality
        real_stock = total_in - total_out
        
        # 4. Forcefully update the database (using update() prevents your manual adjustment bug!)
        Product.objects.filter(pk=self.pk).update(stok_saat_ini=real_stock)

    def __str__(self):
        return f"{self.nama_barang} (Stok: {self.stok_saat_ini})"
    
 

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('Lunas', 'Lunas'),
        ('Belum Lunas', 'Belum Lunas'),
    ]

    SALES_CHOICES = [
        ('A1', 'A1'),
        ('A2', 'A2'),
        ('A3', 'A3'),
    ]

    nomor_faktur = models.CharField(max_length=50, primary_key=True, blank=True, editable=False)
    
    tanggal = models.DateField(default=datetime.date.today)
    tanggal_jatuh_tempo = models.DateField(blank=True, null=True, help_text="Kosongkan agar terisi otomatis berdasarkan aturan Customer")
    
    customer = models.ForeignKey(Customer, on_delete=models.RESTRICT)
    status_pembayaran = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Belum Lunas')
    diskon_persen = models.IntegerField(default=0)
    ppn_persen = models.IntegerField(default=0)

    nomor_resi = models.CharField(max_length=100, blank=True, null=True, help_text="Contoh: JNE - 10293848 atau Supir Budi")

    sales = models.CharField(
        max_length=5, 
        choices=SALES_CHOICES, 
        blank=True, 
        null=True,
        verbose_name="Kode Sales")

    # --- 4. ADD THIS MAGICAL SAVE RULE ---
    # --- FIX #1: Invoice numbering wrapped in transaction.atomic() for safety ---
    def save(self, *args, **kwargs):
        with transaction.atomic():
            # A. GENERATE NOMOR FAKTUR (Only if it doesn't exist yet)
            if not self.nomor_faktur:
                # 1. Get the Region Code (JT/JB)
                wilayah_text = self.customer.wilayah.upper()
                if "TENGAH" in wilayah_text or wilayah_text == "JT":
                    kode_wilayah = "JT"
                elif "BARAT" in wilayah_text or wilayah_text == "JB":
                    kode_wilayah = "JB"
                else:
                    # Fallback: Just grab the first 2 letters of whatever they typed
                    kode_wilayah = wilayah_text[:2]

                # 2. Get the Year and Month (e.g., "2603" for March 2026)
                yymm = self.tanggal.strftime('%y%m')

                # 3. Create the Prefix to search the database (e.g., "CK-JT2603")
                prefix = f"CK-{kode_wilayah}{yymm}"

                # 4. Find the highest invoice number (select_for_update locks the row for safety)
                last_invoice = (
                    Invoice.objects
                    .select_for_update()
                    .filter(nomor_faktur__startswith=prefix)
                    .order_by('-nomor_faktur')
                    .first()
                )

                if last_invoice:
                    # Grab the last 3 characters (the "001"), turn it into a number, and add 1
                    last_number = int(last_invoice.nomor_faktur[-3:])
                    sequence = last_number + 1
                else:
                    # If no invoices exist for this month yet, start at 1
                    sequence = 1

                # 5. Combine everything! {:03d} forces the number to have 3 digits (001, 002)
                self.nomor_faktur = f"{prefix}{sequence:03d}"

            # B. EXISTING DUE DATE LOGIC
            if not self.tanggal_jatuh_tempo and self.customer and self.tanggal:
                self.tanggal_jatuh_tempo = self.tanggal + timedelta(days=self.customer.tempo_hari)

            # C. SAVE TO DATABASE (inside the atomic block for numbering safety)
            super().save(*args, **kwargs)

        # D. CASHFLOW SYNC (called here for status/discount changes on existing invoices)
        self.sync_cashflow()

    # --- FIX #4: Extracted cashflow sync into its own method ---
    # This is called from Invoice.save() AND from InvoiceItem.save()/delete()
    # so cashflow always reflects the real total after items are saved.
    def sync_cashflow(self):
        try:
            subtotal = sum(item.subtotal for item in self.items.all())
        except Exception:
            subtotal = 0

        nilai_diskon = subtotal * self.diskon_persen / 100
        setelah_diskon = subtotal - nilai_diskon
        nilai_ppn = setelah_diskon * self.ppn_persen / 100
        grand_total = setelah_diskon + nilai_ppn

        cashflow_status = 'LUNAS' if self.status_pembayaran == 'Lunas' else 'BELUM'

        Cashflow.objects.update_or_create(
            invoice=self,
            defaults={
                'tanggal': self.tanggal,
                'nama_transaksi': f"Faktur Penjualan: {self.nomor_faktur}",
                'jenis_transaksi': 'IN',
                'nominal': grand_total,
                'status_pembayaran': cashflow_status,
                'keterangan': f"Customer: {self.customer.nama_cust}"
            }
        )

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.RESTRICT)
    qty = models.IntegerField()
    
    harga_satuan = models.IntegerField() 
    subtotal = models.IntegerField() 

    # --- FIX #5: Remember original qty so we can detect edits ---
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_qty = self.qty if self.pk else 0

    # --- FIX #3: Validate stock before allowing a sale ---
    def clean(self):
        super().clean()
        if self.product_id and self.qty:
            # For new items: check full qty against stock
            if self.pk is None:
                if self.product.stok_saat_ini < self.qty:
                    raise ValidationError(
                        f"Stok {self.product.nama_barang} tidak cukup! "
                        f"Tersedia: {self.product.stok_saat_ini}, Diminta: {self.qty}"
                    )
            # For edited items: check only the INCREASE against stock
            else:
                increase = self.qty - self._original_qty
                if increase > 0 and self.product.stok_saat_ini < increase:
                    raise ValidationError(
                        f"Stok {self.product.nama_barang} tidak cukup untuk penambahan! "
                        f"Tersedia: {self.product.stok_saat_ini}, Tambahan diminta: {increase}"
                    )

    def save(self, *args, **kwargs):
        # Auto-fill price (only if the box is actually empty)
        if not self.harga_satuan:
            self.harga_satuan = self.product.harga_jual
        
        # Auto-calculate subtotal (just in case JavaScript fails, Django double-checks it)
        self.subtotal = self.qty * self.harga_satuan

        # Check if this is a new item being added
        is_new = self.pk is None

        # Save the item to the database first
        super().save(*args, **kwargs)
        
        if is_new:
            # --- FIX #2: Atomic stock deduction using F() ---
            Product.objects.filter(pk=self.product.pk).update(
                stok_saat_ini=F('stok_saat_ini') - self.qty
            )
            self.product.refresh_from_db()

            # Log the transaction to StockTransaction table
            StockTransaction.objects.create(
                product=self.product,
                transaction_type='OUT',
                qty=self.qty,
                customer=self.invoice.customer,
                reference=f"Nota: {self.invoice.nomor_faktur}"
            )
        else:
            # --- FIX #5: Handle qty edits on existing items ---
            delta = self.qty - self._original_qty
            if delta != 0:
                # Adjust stock atomically by the difference
                Product.objects.filter(pk=self.product.pk).update(
                    stok_saat_ini=F('stok_saat_ini') - delta
                )
                self.product.refresh_from_db()

                # Log a correction transaction
                if delta > 0:
                    StockTransaction.objects.create(
                        product=self.product,
                        transaction_type='OUT',
                        qty=delta,
                        customer=self.invoice.customer,
                        reference=f"Edit Nota: {self.invoice.nomor_faktur} (+{delta})"
                    )
                else:
                    StockTransaction.objects.create(
                        product=self.product,
                        transaction_type='IN',
                        qty=abs(delta),
                        reference=f"Edit Nota: {self.invoice.nomor_faktur} ({delta})"
                    )

                # Update memory to the new qty
                self._original_qty = self.qty

        # --- FIX #4: Sync cashflow AFTER item is saved so the total is correct ---
        self.invoice.sync_cashflow()

    def delete(self, *args, **kwargs):
        product = self.product
        invoice = self.invoice
        qty = self.qty

        # Remove the matching stock transaction from the ledger
        StockTransaction.objects.filter(
            product=product,
            transaction_type='OUT',
            qty=qty,
            reference=f"Nota: {invoice.nomor_faktur}"
        ).first().delete()

        # Delete the item itself
        super().delete(*args, **kwargs)

        # Recalculate stock from the ledger (single source of truth)
        product.update_stock_from_history()

        # Sync cashflow to reflect the removed item
        invoice.sync_cashflow()

    def __str__(self):
        return f"{self.qty}x {self.product.nama_barang} ({self.invoice.nomor_faktur})"

class StockTransaction(models.Model):
    # Transaction Types
    TRANSACTION_CHOICES = [
        ('IN', 'Stock In (Masuk)'),
        ('OUT', 'Stock Out (Keluar)'),
    ]

    # The Item
    product = models.ForeignKey(
        'Product', # <-- We need to confirm this model name
        on_delete=models.CASCADE, 
        related_name='transactions'
    )
    
    # In or Out
    transaction_type = models.CharField(
        max_length=3, 
        choices=TRANSACTION_CHOICES
    )
    
    # How many items moved
    qty = models.PositiveIntegerField()
    
    # Who bought it? (Will be blank for Stock IN)
    customer = models.ForeignKey(
        'Customer', # <-- We need to confirm this model name
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='stock_purchases'
    )
    
    # Invoice Number or PO Number from Excel
    reference = models.CharField(
        max_length=100, 
        help_text="Nomor Faktur, Surat Jalan, atau Referensi PO"
    )
    
    # Exact date and time it happened
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # This makes sure the newest transactions show up first
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.nama_barang} | {self.transaction_type} | Qty: {self.qty}"
    
class Supplier(models.Model):
    nama_supplier = models.CharField(max_length=100, unique=True) # e.g., PT MITRA RAJA ANUGERAH
    alamat = models.TextField(blank=True, null=True)
    rekening_bank = models.CharField(max_length=200, blank=True, null=True, help_text="Contoh: BCA a/n PT MITRA RAJA 123456")
    
    def __str__(self):
        return self.nama_supplier

class RestockInvoice(models.Model):
    # 1. ADDED STATUS CHOICES FOR SUPPLIER PAYMENTS
    STATUS_CHOICES = [
        ('Lunas', 'Lunas'),
        ('Belum Lunas', 'Belum Lunas'),
    ]

    supplier = models.ForeignKey('Supplier', on_delete=models.CASCADE) # Assuming Supplier model exists
    nomor_faktur = models.CharField(max_length=50, unique=True)
    tanggal = models.DateField(default=timezone.now, help_text="Tanggal di kertas faktur")
    tanggal_jatuh_tempo = models.DateField(help_text="Tgl J/T (Kredit 60 Hari)")
    
    # 2. ADDED THE STATUS FIELD
    status_pembayaran = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Belum Lunas')
    
    catatan = models.TextField(blank=True, null=True)
    subtotal = models.IntegerField(default=0)
    grand_total = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    # 3. ADDED THE AUTOMATION ENGINE
    def save(self, *args, **kwargs):
        # Save the restock document first so it exists in the database
        super().save(*args, **kwargs)



        # Calculate the money owed. 
        # Notice we use 'self.items.all()' because you set related_name='items' in RestockItem!
        try:
            total_uang = sum(item.subtotal for item in self.items.all() if item.subtotal)
            
            # Fallback: If no items are saved yet, but you typed a grand_total manually
            if total_uang == 0 and self.grand_total > 0:
                total_uang = self.grand_total
                
        except Exception:
            total_uang = self.grand_total 

        # Map the status to our Cashflow vocabulary
        cashflow_status = 'LUNAS' if self.status_pembayaran == 'Lunas' else 'BELUM'

        # Send it to the Cashflow Dashboard as KREDIT (OUT)
        Cashflow.objects.update_or_create(
            restock_invoice=self, 
            defaults={
                'tanggal': self.tanggal,
                'nama_transaksi': f"Faktur Supplier: {self.nomor_faktur}", 
                'jenis_transaksi': 'OUT', # KREDIT
                'nominal': total_uang,
                'status_pembayaran': cashflow_status, 
                # Notice we use 'nama_supplier' because that's what you used in your __str__ below
                'keterangan': f"Supplier: {self.supplier.nama_supplier}" 
            }
        )

    def __str__(self):
        return f"Restock {self.nomor_faktur} - {self.supplier.nama_supplier}"

class RestockItem(models.Model):
    restock_invoice = models.ForeignKey(RestockInvoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.RESTRICT)
    
    qty = models.PositiveIntegerField()
    harga_beli = models.IntegerField(default=0, blank=True, null=True, help_text="Harga modal dari pabrik")
    subtotal = models.BigIntegerField(default=0, blank=True, null=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None 
        
        super().save(*args, **kwargs)
        
        if is_new:
            
            StockTransaction.objects.create(
                product=self.product,
                transaction_type='IN',
                qty=self.qty,
                reference=f"PO Masuk: {self.restock_invoice.nomor_faktur}"
            )
            
            # THE MAGIC: Instead of F() math, just tell the product to recalculate!
            self.product.update_stock_from_history()

    def delete(self, *args, **kwargs):
        product = self.product
        
        # 1. Find and delete the matching history ledger row
        StockTransaction.objects.filter(
            product=self.product,
            reference=f"PO Masuk: {self.restock_invoice.nomor_faktur}",
            qty=self.qty,
            transaction_type='IN'
        ).delete()
        
        # 2. Delete the Restock Item itself from the database
        super().delete(*args, **kwargs)
        
        # 3. Trigger the Recalculation Engine to fix the current stock!
        product.update_stock_from_history()

    def __str__(self):
        return f"{self.product.nama_barang} ({self.qty})"
    
class Cashflow(models.Model):
    JENIS_CHOICES = [
        ('IN', 'Pemasukan'),
        ('OUT', 'Pengeluaran'),
    ]
    STATUS_CHOICES = [
        ('LUNAS', 'Lunas'),
        ('BELUM', 'Belum Lunas'),
    ]

    tanggal = models.DateField()
    nama_transaksi = models.CharField(max_length=200)
    jenis_transaksi = models.CharField(max_length=3, choices=JENIS_CHOICES)
    nominal = models.DecimalField(max_digits=12, decimal_places=0)
    
    # The safety net for Option 2:
    status_pembayaran = models.CharField(max_length=10, choices=STATUS_CHOICES, default='LUNAS')
    
    keterangan = models.TextField(blank=True, null=True)
    
    # 1. The invisible link to Sales Invoices (Uang Masuk)
    invoice = models.ForeignKey('Invoice', on_delete=models.SET_NULL, null=True, blank=True)

    # 2. THE MISSING PIECE: The link to Supplier Invoices (Uang Keluar)
    restock_invoice = models.ForeignKey('RestockInvoice', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Cashflow"
        ordering = ['-tanggal'] 

    def __str__(self):
        return f"{self.tanggal} - {self.nama_transaksi}"

class ReadyMix(models.Model):
    JENIS_CHOICES = [
        ('Ready Mix', 'Ready Mix'),
        ('Moving', 'Moving / Pemindahan'),
    ]
    jenis = models.CharField(
        max_length=20, 
        choices=JENIS_CHOICES, 
        default='Ready Mix',
        verbose_name='Jenis Transaksi'
    )
    tanggal = models.DateField(default=datetime.date.today)
    catatan = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Ready Mix / Moving'
        verbose_name_plural = 'Ready Mix / Moving'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.jenis} {self.tanggal}"

class ReadyMixOutput(models.Model):
    ready_mix = models.ForeignKey(ReadyMix, on_delete=models.CASCADE, related_name='outputs')
    product = models.ForeignKey(
        'Product', 
        on_delete=models.RESTRICT, 
        related_name='readymix_outputs_items',
        verbose_name='Produk Hasil'
    )
    qty = models.PositiveIntegerField(verbose_name='Jumlah Hasil')

    def __str__(self):
        return f"{self.product.nama_barang} ×{self.qty}"

class ReadyMixIngredient(models.Model):
    ready_mix = models.ForeignKey(ReadyMix, on_delete=models.CASCADE, related_name='ingredients')
    product = models.ForeignKey(
        'Product', 
        on_delete=models.RESTRICT, 
        related_name='readymix_uses',
        verbose_name='Bahan'
    )
    qty = models.PositiveIntegerField(verbose_name='Jumlah Dipakai')

    def __str__(self):
        return f"{self.product.nama_barang} ×{self.qty}"