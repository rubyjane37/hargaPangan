# Prediksi Harga Pangan — Pasar Beringharjo

Proyek **Data Mining** untuk memperkirakan harga harian komoditas pangan di Pasar Beringharjo, Yogyakarta. Data diambil dari [Portal Harga Pangan Kota Yogyakarta](https://hargapangan.jogjakota.go.id/statistik), dianalisis, dimodelkan dengan **SARIMA** dan **XGBoost**, lalu di-deploy sebagai aplikasi web **Streamlit**.

**Komoditas:** Telur Ayam Ras · Cabai Rawit Merah · Cabai Rawit Hijau · Bawang Merah

---

## Struktur Proyek

| File | Fungsi |
|---|---|
| `crawl_hargapangan.py` | Scraping data harga dari portal resmi → CSV |
| `harga_pangan_beringharjo.csv` | Dataset hasil scraping |
| `Pangan_Forecasting.ipynb` | EDA, preprocessing, modeling, evaluasi |
| `forecast_utils.py` | Modul training & prediksi XGBoost |
| `forecast_compare.py` | Perbandingan cepat SARIMA vs XGBoost |
| `app.py` | Aplikasi web Streamlit (deployment) |
| `requirements.txt` | Dependensi Python |

---

## Persyaratan

- Python **3.10 – 3.12**
- Koneksi internet (scraping & menjalankan app)

---

## Instalasi

```bash
git clone <url>
cd hargaPangan

python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

---

## Cara Menjalankan

### 1. Ambil / perbarui data (opsional)

Jika ingin scrape ulang dari portal:

```bash
python crawl_hargapangan.py
```

Output: `harga_pangan_beringharjo.csv`

Konfigurasi komoditas dan rentang tahun ada di bagian atas file `crawl_hargapangan.py`.

### 2. Analisis & modeling (notebook)

```bash
jupyter notebook Pangan_Forecasting.ipynb
```

Jalankan semua cell (`Run All`) untuk EDA, preprocessing, perbandingan SARIMA vs XGBoost, dan visualisasi.

### 3. Perbandingan model (script cepat)

```bash
python forecast_compare.py
```

Menampilkan tabel MAPE dan RMSE per komoditas di terminal.

### 4. Aplikasi web (deployment)

```bash
streamlit run app.py
```

Buka browser: **http://localhost:8501**

Fitur aplikasi:
- Pilih komoditas
- Atur horizon prediksi (3–14 hari)
- Lihat grafik historis + prediksi
- Tampilkan metrik MAPE & RMSE

---

## Dataset

| Item | Keterangan |
|---|---|
| Sumber | Portal resmi Pemerintah Kota Yogyakarta |
| Pasar | Pasar Beringharjo |
| Frekuensi | Harian |
| Kolom | `tanggal`, `id_komoditas`, `nama_komoditas`, `harga`, dll. |

**Catatan:** Portal mengembalikan `harga = 0` untuk tanggal tanpa data historis. Nilai tersebut difilter saat preprocessing (`harga > 0`). Data valid dimulai sekitar **Februari 2024**.

---

## Model

| Model | Peran |
|---|---|
| **SARIMA** | Baseline statistik time series |
| **XGBoost** | Model utama (fitur lag + rolling + kalender) |

Evaluasi menggunakan **MAPE**, **RMSE**, dan **MAE** pada split test 20% terakhir (temporal split). Hasil perbandingan menunjukkan **XGBoost unggul** di semua komoditas — dipakai di aplikasi Streamlit.

---

## Alur Kerja Singkat

```
Scraping → CSV → EDA & Preprocessing → SARIMA vs XGBoost → Evaluasi → Streamlit App
```

---

## Lisensi & Etika Data

Data bersumber dari portal publik pemerintah daerah. Gunakan scraping secara wajar (jeda antar request sudah diset di crawler) dan utamakan sebagai keperluan akademik / edukasi.
