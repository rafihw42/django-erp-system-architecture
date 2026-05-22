# CHANGELOG — ColorKing

Semua perubahan penting pada proyek ini akan didokumentasikan di file ini.

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
