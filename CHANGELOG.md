# CHANGELOG — ColorKing

Semua perubahan penting pada proyek ini akan didokumentasikan di file ini.

---

## [2026-06-02] — Keamanan: Secrets & Debug Mode ke `.env`

### 🔒 Hardening: SECRET_KEY & DEBUG Dipindah ke `.env`
- **Masalah:** `SECRET_KEY` Django ter-hardcode di `settings.py` yang sudah terlacak oleh git, dan `DEBUG=True` aktif secara permanen — berbahaya jika server diakses lewat ngrok karena Django menampilkan **full source code + database queries** saat terjadi error.
- **Solusi:** Menggunakan `python-dotenv` untuk membaca semua konfigurasi sensitif dari file `.env` lokal yang **gitignored**.
- **Perubahan:**
  - `SECRET_KEY` diganti dengan kunci baru yang lebih kuat, disimpan di `.env`
  - `DEBUG` dibaca dari `.env`, defaultnya `False` (aman) jika variabel tidak diset
  - `ALLOWED_HOSTS` dibaca dari `.env` sebagai comma-separated string
  - Ditambahkan `.env.example` (aman untuk di-commit) sebagai template setup
  - `requirements.txt` diperbarui dengan tambahan `python-dotenv`
- **File:** `colorking/settings.py`, `.env.example`, `requirements.txt`
- **Catatan:** File `.env` lokal **tidak di-commit**. Saat setup di mesin baru, salin `.env.example` → `.env` dan isi nilainya.

---

## [2026-06-01] — Perbaikan Bug: Autofill Harga Beli & Kode Sales

### 🐛 Fix: Autofill `harga_beli` Tidak Muncul di Form Restock
- **Penyebab:** Kondisi `if (hargaInput && data.harga_beli)` di `restock_math.js` memperlakukan nilai `0` sebagai *falsy* di JavaScript — sehingga produk dengan harga beli `Rp 0` tidak pernah terisi otomatis.
- **Perbaikan:** Kondisi diubah menjadi `data.harga_beli !== undefined` agar nilai `0` tetap mengisi field.
- **File:** `sales/static/sales/js/restock_math.js`

### 🐛 Fix: Autofill `kode_sales` Tidak Berjalan di Form Invoice
- **Penyebab (Root Cause):** Ada dua lapis masalah:
  1. **Salah event:** `autocomplete_fields = ['customer']` pada `InvoiceAdmin` membuat field Customer dirender sebagai widget Select2 oleh Django admin. Select2 menyembunyikan `<select>` asli dan **menelan event `change` native DOM** — sehingga `addEventListener('change', ...)` tidak pernah terpicu.
  2. **Race condition timing:** Bahkan setelah beralih ke `select2:select`, listener di-attach langsung ke elemen `#id_customer` saat `DOMContentLoaded` — namun Django admin baru menginisialisasi Select2 pada elemen tersebut **setelah** `DOMContentLoaded` selesai. Akibatnya listener terpasang sebelum Select2 ada, dan tidak berfungsi.
- **Perbaikan:** Menggunakan **jQuery event delegation pada `document`** (`$(document).on('select2:select', '#id_customer', ...)`). Cara ini bekerja tanpa peduli kapan Select2 diinisialisasi karena event selalu naik ke `document`.
- **File:** `sales/static/sales/js/invoice_admin_autofill.js`

---

## [2026-05-30] — Fitur Baru: Kode Sales per Customer, Sorting Faktur, Checklist Cetak & Autocomplete Customer

### 🧑‍💼 Kode Sales Default per Customer
- **Field Baru `kode_sales` pada Customer:** Menambahkan field pilihan (dropdown A1/A2/A3) pada model `Customer` untuk menyimpan Kode Sales default masing-masing customer.
- **Auto-fill saat Membuat Faktur (Backend):** Saat faktur baru disimpan, field `sales` pada `Invoice` otomatis terisi dari `kode_sales` customer yang dipilih — jika field sales masih kosong. Tidak mempengaruhi faktur yang sudah ada.
- **Auto-fill Langsung di Form (Frontend):** Menambahkan script JavaScript (`invoice_admin_autofill.js`) yang langsung mengisi field Kode Sales begitu user memilih customer di form Invoice — tanpa perlu menyimpan dulu. Diimplementasikan via endpoint AJAX baru `/api/customer-sales/`.
- **Edit Cepat dari Daftar Customer:** Kolom `kode_sales` ditambahkan ke tampilan daftar Customer di Admin dengan `list_editable` — bisa langsung diubah dari halaman list tanpa membuka tiap customer.
- **`SALES_CHOICES` dipindah ke level modul** agar dapat digunakan bersama oleh model `Customer` dan `Invoice`.
- **File:** `sales/models.py`, `sales/admin.py`, `sales/views.py`, `sales/static/sales/js/invoice_admin_autofill.js`, `colorking/urls.py`
- **Migrasi:** `0028_customer_kode_sales.py`

### 📅 Sorting Default Faktur: Terbaru di Atas
- **Default Ordering Invoice:** Menambahkan `class Meta` dengan `ordering = ['-tanggal', '-nomor_faktur']` pada model `Invoice`.
- Faktur di halaman Admin sekarang diurutkan dari **tanggal terbaru ke terlama** secara otomatis. Faktur JT dan JB tercampur murni berdasarkan tanggal.
- **File:** `sales/models.py`

### 🖨️ Checklist "Sudah Cetak" pada Faktur
- **Field Baru `sudah_cetak`:** Menambahkan `BooleanField` (default `False`) pada model `Invoice` untuk menandai apakah faktur sudah dicetak.
- **Edit Langsung dari List:** Kolom `sudah_cetak` ditampilkan di halaman daftar Invoice sebagai checkbox yang bisa dicentang langsung tanpa membuka faktur.
- **File:** `sales/models.py`, `sales/admin.py`
- **Migrasi:** `0029_invoice_sudah_cetak.py`

### 🔍 Autocomplete Search untuk Customer di Form Invoice
- **Dropdown Customer Berubah Jadi Search Box:** Mengaktifkan `autocomplete_fields = ['customer']` pada `InvoiceAdmin`.
- User kini bisa mengetik nama atau kode customer untuk mencari, alih-alih scroll dropdown panjang.
- Memanfaatkan `search_fields` yang sudah ada di `CustomerAdmin` (`kode_cust`, `nama_cust`) — tidak perlu konfigurasi tambahan.
- **File:** `sales/admin.py`

---

## [2026-05-26] — Fitur Baru: Edit Ready Mix & Link Referensi Clickable

### 🧪 Fitur Edit Transaksi Ready Mix / Moving
- **Akses Pengeditan:** Menambahkan kemampuan untuk mengedit transaksi Ready Mix / Moving. Mengklik baris transaksi di Django Admin akan membuka custom web view form yang terpopulasi dengan data asli (tanggal, jenis, catatan, bahan, hasil) untuk diedit.
- **Rekonsiliasi Stok & Ledger:** Proses update berjalan di dalam `transaction.atomic()`. Menghapus detail transaksi dan catatan ledger (`StockTransaction`) lama, menulis ulang data baru, dan menghitung ulang stok produk yang terlibat menggunakan `update_stock_from_history()`.
- **Validasi Ketersediaan Stok (Offset):** Sistem pengecekan stok saat edit memperhitungkan kuantitas yang saat ini sudah digunakan oleh transaksi tersebut, mencegah error "Stok tidak cukup" ketika user memperkecil atau mempertahankan jumlah bahan.

### 🔗 Link Referensi Riwayat Stok Clickable
- **Navigasi Langsung:** Kolom "Referensi" pada Riwayat Stok kini menjadi link clickable yang mengarah langsung ke dokumen sumber:
  - Faktur Penjualan (Nota) -> Halaman edit Invoice di Django Admin.
  - Restock Invoice (PO Masuk) -> Halaman edit Restock Invoice di Django Admin.
  - Ready Mix / Moving -> Custom edit form Ready Mix.
- **Penyederhanaan Log Referensi:** Log referensi Ready Mix / Moving disederhanakan hanya menampilkan `"Ready Mix"` atau `"Moving"` karena rincian bahan dan produk dapat langsung dilihat dengan mengklik link tersebut.

---

## [2026-05-26] — Perbaikan Tampilan Cetak: Surat Jalan & Nota

### 🖨️ Surat Jalan — Unifikasi Ukuran Font
- **Sebelumnya:** Font size tidak konsisten — `8pt` untuk alamat, `12pt` untuk isi tabel (dideklarasikan ulang di `th` dan `td`), dan `15pt` untuk judul.
- **Sesudahnya:** Semua teks kini menggunakan ukuran seragam yang diwarisi dari `body` (`11pt`), kecuali judul "Surat Jalan CK" yang tetap `15pt`.
- **File:** `sales/templates/sales/surat_jalan.html`

### 🖨️ Surat Jalan — Header Tabel Hanya Garis Atas & Bawah
- **Sebelumnya:** Header tabel (`<th>`) memiliki `border: 1px solid black` pada semua sisi (termasuk kiri dan kanan antar kolom).
- **Sesudahnya:** Hanya `border-top` dan `border-bottom` yang dipertahankan, menghasilkan tampilan header yang lebih bersih tanpa pembatas vertikal antar kolom.
- **File:** `sales/templates/sales/surat_jalan.html`

### 📋 Nota — Perbaikan Alignment Alamat Multi-Baris
- **Sebelumnya:** Saat alamat customer terdiri dari lebih dari satu baris, baris kedua (dan seterusnya) wrap kembali ke posisi titik dua (`:`) alih-alih sejajar dengan awal teks alamat.
- **Sesudahnya:** Tanda titik dua dan teks alamat dibungkus dalam flex container terpisah, sehingga baris lanjutan selalu rata dengan karakter pertama alamat.
- **File:** `sales/templates/sales/nota.html`

---

## [2026-05-25] — Fitur Baru: Ekspor Faktur & Perbaikan Tampilan Surat Jalan

### 📤 Ekspor Faktur Berdasarkan Filter/Pencarian
- **Fitur Ekspor:** Menambahkan tombol **Export** di halaman daftar Invoices pada Admin Panel.
- **Filter-Aware:** Ekspor hanya mengambil faktur yang sedang ditampilkan — mengikuti filter tanggal, status pembayaran, maupun hasil pencarian yang aktif.
- **Format:** Mendukung ekspor ke **CSV** dan **Excel** menggunakan library `django-import-export` yang sudah terpasang.
- **Kolom yang Diekspor:** Nomor Faktur, Tanggal, Jatuh Tempo, Nama Customer, Wilayah, Sales, Status Pembayaran, Diskon (%), PPN (%), Subtotal (Rp), Grand Total (Rp), dan Nomor Resi.
- **Implementasi:**
  - Menambahkan class `InvoiceResource` di `sales/admin.py` dengan field `nama_customer`, `wilayah`, `subtotal`, dan `grand_total` yang dihitung dari relasi item.
  - Mengubah `InvoiceAdmin` dari `admin.ModelAdmin` menjadi `ImportExportModelAdmin`.

### 🖨️ Perbaikan Tampilan Surat Jalan — Hapus Border Baris Data
- **Sebelumnya:** Semua baris tabel (header dan data) memiliki border `1px solid black`.
- **Sesudahnya:** Hanya baris **header** (`<th>`) yang mempertahankan border. Baris data (`<td>`) tidak memiliki border sama sekali, menghasilkan tampilan yang lebih bersih.
- **File:** `sales/templates/sales/surat_jalan.html`

### 📐 Penyesuaian Ukuran Font & Jumlah Baris Surat Jalan
- **Jumlah Baris Maksimal:** Dikurangi dari **15** menjadi **13** baris untuk memberikan ruang vertikal tambahan.
- **Ukuran Font:** Ditingkatkan dari `10pt` menjadi **`12pt`** untuk header dan isi tabel, menghasilkan teks yang lebih mudah dibaca.
- **Tinggi Baris:** Dinaikkan dari `16px` menjadi **`20px`** agar teks dengan font lebih besar tidak terpotong.
- **Penyesuaian Spasi:** `line-height` diperketat (`1.2` → `1.1`), margin header dan footer dikurangi sedikit untuk memastikan semua elemen tetap muat dalam satu halaman *Half Letter*.
- **File:** `sales/views.py` (baris cap) + `sales/templates/sales/surat_jalan.html` (CSS)

---

## [2026-05-24] — Fitur Baru: Deplesi & Restorasi Stok Ready Mix/Moving & Pengurutan Produk Default

### 🗑️ Fitur Hapus Transaksi Ready Mix / Moving
- **Penghapusan Transaksi:** Membuka akses untuk menghapus histori transaksi Ready Mix / Moving langsung dari Django Admin.
- **Cascading & Relasi:** Menambahkan foreign key `readymix` pada model `StockTransaction` agar saat transaksi Ready Mix dihapus, semua transaksi stok terkait otomatis terhapus (CASCADE).
- **Restorasi Stok Otomatis:** Menggunakan Django signals (`pre_delete` dan `post_delete`) pada model `ReadyMix` untuk mendeteksi produk yang terlibat dan mengoreksi (recalculate) stok mereka kembali ke kondisi semula secara otomatis.

### 📋 Pengurutan Produk Berdasarkan Urutan Import (Default Position)
- **Kolom `created_at`:** Menambahkan field timestamp `created_at` dengan `default=timezone.now` pada model `Product`.
- **Default Ordering:** Mengatur default sorting list product (`ordering = ['created_at']`) agar produk diurutkan berdasarkan urutan saat diimport dari Excel.

---

## [2026-05-22] — Fitur Baru: Dashboard Analisis Penjualan & Visualisasi Data

### 📊 Fitur Dashboard Baru
- **Visualisasi Chart.js**: Menampilkan tren penjualan bulanan (line chart) dan kontribusi penjualan top 5 customer (doughnut chart).
- **KPI Ringkasan Utama**: Kartu indikator kinerja utama seperti Pendapatan Total (YTD), Customer Aktif, Rata-rata Nilai Order (AOV), dan Top Customer.
- **Matriks Heatmap Bulanan**: Tabel dinamis bulanan customer dengan pewarnaan heatmap berdasarkan volume penjualan untuk memudahkan analisis visual.
- **Ekspor CSV**: Fitur ekspor langsung data matriks penjualan bulanan customer ke file CSV.
- **Integrasi Admin Panel**: Tautan navigasi langsung ke dashboard di bagian atas header admin Django.

---

## [2026-05-20] — Fitur Baru: Ready Mix / Moving (Pemindahan) dengan Multi-Output

### ⚙️ Fitur & Model Baru
- **Jenis Transaksi (Ready Mix / Moving):** Menambahkan pilihan jenis transaksi agar pengguna bisa memilih antara pencampuran produk (`Ready Mix`) atau pemindahan stok (`Moving`).
- **Multi-Output (Produk Hasil Lebih dari Satu):** Mendukung pembuatan/pemindahan lebih dari satu produk hasil sekaligus dalam satu sesi transaksi.
- **Relasi Database Baru:** Membuat model `ReadyMixOutput` untuk mendukung relasi one-to-many antara satu transaksi dengan banyak produk hasil.
- **Migrasi Data Aman:** Memindahkan data produk hasil pada transaksi `ReadyMix` lama secara otomatis ke dalam tabel baru `ReadyMixOutput` tanpa kehilangan data historis.
- **Tampilan Dinamis Form:** Form `/readymix/new/` kini secara dinamis merubah istilah label ("Produk Hasil/Bahan Dipakai" vs "Produk Tujuan/Produk Sumber") berdasarkan jenis transaksi yang dipilih.

### 💼 Admin Panel
- Menambahkan inline detail `ReadyMixOutputInline` untuk menampilkan produk hasil di halaman riwayat transaksi.
- Memperbarui pencarian admin agar dapat mendeteksi barang hasil di dalam tabel baru.
- Memperbarui kolom list riwayat agar menampilkan ringkasan semua produk hasil dan bahan secara lengkap.

## [2026-05-18] — Perbaikan UI/UX Admin & Cetakan Nota/Surat Jalan

### 💅 Admin UI Enhancements
- **Global Filter Toggle:** Menambahkan tombol 🔍 mengambang (floating button) di semua halaman list admin untuk menyembunyikan/menampilkan sidebar filter. Status tersimpan di browser.
- **Compact Invoice List:** 
  - Mengganti tombol Cetak Nota & Surat Jalan menjadi icon (🖨️ dan 🚚) agar lebih hemat tempat.
  - Teks pada tabel kini bisa wrap otomatis sehingga tidak perlu *horizontal scroll* di layar kecil.
  - Menghapus kolom "Nomor Resi" dari tampilan list utama faktur untuk menghemat ruang.
- **Customer Admin Cleanup:** 
  - Kolom `Riwayat` dipindah agar tampil tepat setelah `Nama cust`.
  - Menghapus kotak statis "Grand Total" dari halaman edit Customer agar form lebih bersih.
  - Menghilangkan tombol "Save and add another" dan "Save and continue editing" di halaman edit Customer untuk mencegah kebingungan.

### 💰 Dynamic Invoice Grand Total
- Menambahkan kartu ringkasan **Grand Total Pembelanjaan** berwarna merah muda di bagian atas halaman Invoices.
- Total ini dihitung **secara dinamis** berdasarkan faktur yang sedang ditampilkan (misalnya, total belanja untuk *satu* customer tertentu saat tombol "Lihat Faktur" diklik, atau saat filter tanggal diterapkan).

### 🖨️ Print Layout Fixes (Surat Jalan & Nota)
- **Alamat Panjang:** Memperbaiki bug di mana alamat customer yang terlalu panjang mendorong bagian Tanda Tangan keluar dari halaman (mengganti font menjadi 8pt dan menyesuaikan flex container).
- **Satuan Kuantitas Dinamis:** 
  - Kolom kuantitas pada Nota dan Surat Jalan sekarang otomatis mendeteksi kategori barang.
  - Jika barang berkategori **TH** (Thinner), kuantitas akan tercetak dengan akhiran **LTR** (contoh: `2 LTR`).
  - Untuk barang kategori lain, akan tercetak **KLG** (contoh: `5 KLG`).

---

## [2026-05-18] — Fitur Baru: Ready Mix (Racik Produk)

### 🆕 Ready Mix — Racik Produk dari Bahan yang Ada
**URL:** `/readymix/new/`  
**Model:** `ReadyMix` + `ReadyMixIngredient`

Fitur manufacturing/assembly: ambil bahan-bahan dari stok, campurkan, dan hasilkan produk baru.

**Cara Kerja:**
- Pilih produk output (hasil) + jumlah yang dihasilkan
- Pilih 1 atau lebih bahan (ingredient) + jumlah masing-masing
- Klik "Proses" → stok bahan berkurang, stok output bertambah
- Semua dicatat di `StockTransaction` dengan referensi jelas

**Contoh:**
```
INPUT:  NC 800 ×2, TH CS ×1
OUTPUT: NC 800 Ready Mix ×5
```

**Fitur:**
- Validasi stok bahan sebelum proses (tidak bisa pakai lebih dari yang tersedia)
- Halaman dilindungi `@staff_member_required` (harus login admin)
- Riwayat bisa dilihat di Admin → Ready Mix (read-only)
- Select2 searchable dropdown untuk semua produk
- Bisa tambah/hapus baris bahan secara dinamis

---

## [2026-05-18] — Medium Severity Fixes (Kebersihan Kode)

### 🧹 Fix #12: Hapus Self-Import yang Tidak Perlu
**File:** `sales/models.py`
- Dihapus 5 baris `from .models import ...` di dalam method body
- Semua class (StockTransaction, Cashflow) sudah ada di file yang sama, jadi import ini tidak diperlukan
- Membersihkan kode dan mengurangi kebingungan

### 🧹 Fix #13: Hapus Tag HTML Duplikat
**File:** `sales/templates/sales/create_restock.html`
- Dihapus duplikat `<meta charset>` dan `<title>` di baris 8-9

---

## [2026-05-18] — High Severity Fixes (Stok & Keamanan)

### 🔧 Fix #5: Edit Qty Item Faktur Sekarang Mengupdate Stok
**File:** `sales/models.py` → `InvoiceItem`
- Sebelumnya: mengubah qty item yang sudah ada TIDAK mempengaruhi stok sama sekali (stok melayang)
- Sesudahnya: perubahan qty dihitung delta-nya (selisih lama vs baru) lalu stok dikoreksi otomatis
- Validasi juga diperbaiki: saat edit, hanya selisih penambahannya yang dicek terhadap stok tersedia
- StockTransaction koreksi dibuat otomatis: `"Edit Nota: CK-JT2605001 (+3)"` atau `"(-2)"`

### 🔧 Fix #7: Halaman Restock & Hapus Stok Sekarang Dilindungi Login
**File:** `sales/views.py` → `create_restock()`, `delete_stock_transaction()`
- Ditambahkan `@staff_member_required` — hanya user admin yang bisa mengakses
- Sebelumnya: siapa saja yang tahu URL `/restock/new/` bisa membuat PO tanpa login (terutama bahaya via ngrok)

### 🔧 Fix #8: Halaman Hapus Stok Tidak Crash Lagi untuk Request GET
**File:** `sales/views.py` → `delete_stock_transaction()`
- Sebelumnya: membuka URL hapus via GET (misalnya klik kanan → buka tab baru) menyebabkan error 500
- Sesudahnya: mengembalikan HTTP 405 (Method Not Allowed) yang benar

---

## [2026-05-18] — Critical Bug Fixes (Data Integrity)

### 🔧 Fix #1: Nomor Faktur Sekarang Atomic (Aman dari Duplikasi)
**File:** `sales/models.py` → `Invoice.save()`
- Logika pembuatan nomor faktur sekarang dibungkus dalam `transaction.atomic()` + `select_for_update()`
- Ini mencegah dua faktur mendapatkan nomor yang sama jika disimpan secara bersamaan
- Catatan: `select_for_update()` hanya efektif di PostgreSQL/MySQL, tapi `transaction.atomic()` tetap memberikan perlindungan di SQLite

### 🔧 Fix #2: Pengurangan Stok Sekarang Atomic (Akurat)
**File:** `sales/models.py` → `InvoiceItem.save()`
- Pengurangan stok sekarang menggunakan `F()` expression (`UPDATE ... SET stok = stok - qty`)
- Sebelumnya: stok dibaca ke Python, dikurangi di memori, lalu ditulis ulang — bisa salah jika ada 2 request bersamaan
- Sesudahnya: pengurangan dilakukan langsung di database dalam 1 operasi atomic

### 🔧 Fix #3: Proteksi Stok Negatif + Koreksi Massal
**File:** `sales/models.py` → `InvoiceItem.clean()`  
**File:** `sales/admin.py` → `ProductAdmin`
- Ditambahkan validasi: tidak bisa menjual barang melebihi stok yang tersedia
- Pesan error akan muncul: *"Stok [nama] tidak cukup! Tersedia: X, Diminta: Y"*
- Ditambahkan admin action baru: **"🔧 Fix Stok Negatif ke 0"** — pilih produk, jalankan action, semua stok negatif otomatis dikoreksi ke 0 dengan StockTransaction koreksi

### 🔧 Fix #4: Cashflow Sekarang Sinkron Setelah Item Disimpan
**File:** `sales/models.py` → `Invoice.sync_cashflow()` (baru) + `InvoiceItem.save()` + `InvoiceItem.delete()`
- Sebelumnya: saat membuat faktur baru, Cashflow langsung dibuat dengan nominal **Rp 0** karena item belum tersimpan saat `Invoice.save()` dipanggil
- Sesudahnya: logika cashflow diekstrak ke method `sync_cashflow()` yang dipanggil dari:
  - `Invoice.save()` — untuk perubahan status/diskon
  - `InvoiceItem.save()` — setelah item tersimpan, cashflow langsung di-update
  - `InvoiceItem.delete()` — saat item dihapus, cashflow otomatis disesuaikan
- Cashflow sekarang selalu menampilkan nominal yang benar

### 🆕 Tambahan: InvoiceItem.delete() sekarang mengembalikan stok
- Saat item faktur dihapus, stok dikembalikan otomatis lewat `update_stock_from_history()`
- StockTransaction yang terkait juga dihapus dari ledger
