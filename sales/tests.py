from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Product, ReadyMix, ReadyMixIngredient, ReadyMixOutput, StockTransaction

class ReadyMixEditTest(TestCase):
    def setUp(self):
        # Create a superuser and log in
        self.user = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.client.login(username='admin', password='password')

        # Create products with initial stocks
        self.prod_a = Product.objects.create(kode_barang="PROD-A", nama_barang="Product A", harga_jual=10000, stok_saat_ini=20)
        self.prod_b = Product.objects.create(kode_barang="PROD-B", nama_barang="Product B", harga_jual=15000, stok_saat_ini=5)

    def test_create_and_edit_readymix(self):
        # 1. Verify initial stocks
        self.assertEqual(self.prod_a.stok_saat_ini, 20)
        self.assertEqual(self.prod_b.stok_saat_ini, 5)

        # 2. Create a Ready Mix transaction (mix 5 of PROD-A to produce 2 of PROD-B)
        payload = {
            'jenis': 'Ready Mix',
            'tanggal': '2026-05-26',
            'nomor_faktur': 'RM-001',
            'ingredient_product[]': ['PROD-A'],
            'ingredient_qty[]': ['5'],
            'output_product[]': ['PROD-B'],
            'output_qty[]': ['2']
        }
        response = self.client.post(reverse('create_readymix'), payload)
        self.assertEqual(response.status_code, 302)

        # Refresh products from DB
        self.prod_a.refresh_from_db()
        self.prod_b.refresh_from_db()

        # Check stock changes: PROD-A: 20 - 5 = 15; PROD-B: 5 + 2 = 7
        self.assertEqual(self.prod_a.stok_saat_ini, 15)
        self.assertEqual(self.prod_b.stok_saat_ini, 7)

        # Retrieve the created transaction
        tx = ReadyMix.objects.first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.jenis, 'Ready Mix')
        self.assertEqual(tx.nomor_faktur, 'RM-001')

        # Assert reference text is simplified and reference URL is correct
        out_tx = StockTransaction.objects.filter(product=self.prod_a, transaction_type='OUT').exclude(reference__contains='Initial').first()
        self.assertEqual(out_tx.reference, 'Ready Mix')
        self.assertEqual(out_tx.reference_url, reverse('edit_readymix', args=[tx.pk]))

        # Test printing the Ready Mix invoice
        print_url = reverse('print_readymix', args=[tx.pk])
        print_response = self.client.get(print_url)
        self.assertEqual(print_response.status_code, 200)
        self.assertContains(print_response, "READY MIX")
        self.assertContains(print_response, "RM-001")
        self.assertContains(print_response, "Bahan Masuk")
        self.assertContains(print_response, "Bahan Keluar")

        # 3. Edit the transaction (increase PROD-A ingredient to 12, increase PROD-B output to 4)
        edit_payload = {
            'jenis': 'Ready Mix',
            'tanggal': '2026-05-26',
            'nomor_faktur': 'RM-001-EDITED',
            'ingredient_product[]': ['PROD-A'],
            'ingredient_qty[]': ['12'],
            'output_product[]': ['PROD-B'],
            'output_qty[]': ['4']
        }
        edit_url = reverse('edit_readymix', args=[tx.pk])
        response = self.client.post(edit_url, edit_payload)
        self.assertEqual(response.status_code, 302)

        # Refresh products from DB
        self.prod_a.refresh_from_db()
        self.prod_b.refresh_from_db()

        # Check stock changes:
        # PROD-A initial stock is 20. Usage is 12 -> final stock should be 8.
        # PROD-B initial stock is 5. Output is 4 -> final stock should be 9.
        self.assertEqual(self.prod_a.stok_saat_ini, 8)
        self.assertEqual(self.prod_b.stok_saat_ini, 9)

        # Verify edited field
        tx.refresh_from_db()
        self.assertEqual(tx.nomor_faktur, 'RM-001-EDITED')

        # 4. Test validation logic - attempt to edit to use 25 of PROD-A (exceeds available 8 + 12 = 20)
        invalid_payload = {
            'jenis': 'Ready Mix',
            'tanggal': '2026-05-26',
            'nomor_faktur': 'RM-001-INVALID',
            'ingredient_product[]': ['PROD-A'],
            'ingredient_qty[]': ['25'],  # 25 > 20
            'output_product[]': ['PROD-B'],
            'output_qty[]': ['4']
        }
        response = self.client.post(edit_url, invalid_payload)
        self.assertEqual(response.status_code, 302)  # should redirect back with error message
        
        # Verify stocks haven't changed from the last valid edit
        self.prod_a.refresh_from_db()
        self.assertEqual(self.prod_a.stok_saat_ini, 8)

        # 5. Create a Moving transaction to test 404 on print page
        moving_payload = {
            'jenis': 'Moving',
            'tanggal': '2026-05-26',
            'nomor_faktur': 'MV-001',
            'ingredient_product[]': ['PROD-A'],
            'ingredient_qty[]': ['2'],
            'output_product[]': ['PROD-B'],
            'output_qty[]': ['1']
        }
        response = self.client.post(reverse('create_readymix'), moving_payload)
        self.assertEqual(response.status_code, 302)

        moving_tx = ReadyMix.objects.filter(jenis='Moving').first()
        self.assertIsNotNone(moving_tx)

        # Printing Moving transaction should return 404
        moving_print_url = reverse('print_readymix', args=[moving_tx.pk])
        moving_print_response = self.client.get(moving_print_url)
        self.assertEqual(moving_print_response.status_code, 404)

    def test_reference_url_mapping(self):
        import datetime
        from .models import Customer, Invoice, InvoiceItem, Supplier, RestockInvoice, RestockItem
        
        # 1. Test Invoice Reference URL
        cust = Customer.objects.create(kode_cust="CUST-01", nama_cust="Customer 1", wilayah="Jawa Tengah", tempo_hari=30)
        invoice = Invoice.objects.create(customer=cust, tanggal=datetime.date(2026, 5, 26))
        invoice_item = InvoiceItem.objects.create(invoice=invoice, product=self.prod_a, qty=2, harga_satuan=10000, subtotal=20000)
        
        sales_tx = StockTransaction.objects.filter(product=self.prod_a, reference__startswith="Nota:").first()
        self.assertIsNotNone(sales_tx)
        self.assertEqual(sales_tx.reference_url, f"/admin/sales/invoice/{invoice.nomor_faktur}/change/")

        # 2. Test Restock Reference URL
        supplier = Supplier.objects.create(nama_supplier="Supplier 1")
        restock = RestockInvoice.objects.create(supplier=supplier, nomor_faktur="REST-123", tanggal=datetime.date(2026, 5, 26), tanggal_jatuh_tempo=datetime.date(2026, 7, 26))
        restock_item = RestockItem.objects.create(restock_invoice=restock, product=self.prod_b, qty=3, harga_beli=12000, subtotal=36000)
        
        restock_tx = StockTransaction.objects.filter(product=self.prod_b, reference__startswith="PO Masuk:").first()
        self.assertIsNotNone(restock_tx)
        self.assertEqual(restock_tx.reference_url, f"/admin/sales/restockinvoice/{restock.pk}/change/")
