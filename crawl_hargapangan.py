"""
=============================================================================
 Scraper Harga Pangan Kota Yogyakarta
 Portal : https://hargapangan.jogjakota.go.id/statistik
 Target : Pasar Beringharjo
=============================================================================

 CARA PAKAI:
   1. Sesuaikan KOMODITAS_PILIHAN  -> isi nama komoditas persis seperti
      yang muncul di dropdown portal (case-insensitive, partial match).
   2. Sesuaikan TAHUN_MULAI & TAHUN_AKHIR  -> rentang tahun yang ingin
      diambil datanya.
   3. Jalankan:  python crawl_hargapangan.py

 OUTPUT: file CSV di folder yang sama dengan script ini.
=============================================================================
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import os
import re
import sys
import time
from collections.abc import Callable
from typing import Any

import requests

# Fix encoding untuk Windows terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ===================================================================
# ||  KONFIGURASI - SESUAIKAN DI SINI  ||
# ===================================================================

# Nama komoditas yang ingin di-scrape.
# Tulis persis seperti yang ada di dropdown portal website, contoh:
#   "Daging Sapi Tetelan,1 kg"
#   "Beras Cap IR 64 Kualitas 1,1 kg"
# Boleh juga tulis sebagian saja (partial match), contoh:
#   "Daging Sapi Tetelan"  -> akan match ke "Daging Sapi Tetelan,1 kg"
#   "Cabai Merah"          -> akan match ke "Cabai Merah Keriting,1 kg"
#
# Pencarian CASE INSENSITIVE (huruf besar/kecil tidak masalah).

KOMODITAS_PILIHAN: list[str] = [
    "Telur Ayam Ras",
    "Cabai Rawit Merah",
    "Cabai Rawit Hijau",
    "Bawang Merah"
]
TAHUN_MULAI: int = 2023
TAHUN_AKHIR: int = 2026

OUTPUT_CSV: str = "harga_pangan_beringharjo.csv"
CHUNK_DAYS: int = 90

# Jeda antar request ke server (detik)
REQUEST_DELAY_SEC: float = 1.0

# ===================================================================
# ||  AKHIR KONFIGURASI                ||
# ===================================================================

BASE_URL = "https://hargapangan.jogjakota.go.id"
LIST_URL = f"{BASE_URL}/harga_pangan"
STAT_URL = f"{BASE_URL}/statistik"
PASAR_URL = f"{BASE_URL}/datapasar"

# ID Pasar Beringharjo
TARGET_MARKET_ID = 1
TARGET_MARKET_NAME = "Pasar Beringharjo"


# --------------- Utilitas -------------------------------------------------


def to_float(value: Any) -> float | None:
    """Konversi nilai harga ke float. Menangani format Indonesia (titik=ribuan, koma=desimal)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = re.sub(r"[^0-9,.\-]", "", text)
    if text.count(",") == 1 and text.count(".") >= 1:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")

    try:
        return float(text)
    except ValueError:
        return None


def banner() -> None:
    """Cetak banner informasi di terminal."""
    print("=" * 70)
    print("  SCRAPER HARGA PANGAN KOTA YOGYAKARTA")
    print(f"  Portal  : {STAT_URL}")
    print(f"  Pasar   : {TARGET_MARKET_NAME}")
    print(f"  Periode : {TAHUN_MULAI} - {TAHUN_AKHIR}")
    print(f"  Output  : {OUTPUT_CSV}")
    print(f"  Chunk   : {CHUNK_DAYS} hari per request")
    print("=" * 70)


def iter_date_chunks(
    start_date: dt.date,
    end_date: dt.date,
    chunk_days: int = CHUNK_DAYS,
) -> list[tuple[dt.date, dt.date]]:
    """Bagi rentang tanggal menjadi potongan kecil."""
    if chunk_days < 1:
        chunk_days = 1

    chunks: list[tuple[dt.date, dt.date]] = []
    current = start_date
    step = dt.timedelta(days=chunk_days)

    while current <= end_date:
        chunk_end = min(end_date, current + step - dt.timedelta(days=1))
        chunks.append((current, chunk_end))
        current = chunk_end + dt.timedelta(days=1)

    return chunks


def ajax_headers() -> dict[str, str]:
    """Header standar untuk request AJAX ke portal Laravel."""
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
        "Referer": STAT_URL,
        "Origin": BASE_URL,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }


# --------------- Session & CSRF -------------------------------------------


def create_session() -> requests.Session:
    """Buat requests session dengan header browser standar."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        }
    )
    # Inisialisasi cookie (dengan retry)
    for attempt in range(1, 4):
        try:
            session.get(BASE_URL, timeout=60)
            return session
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < 3:
                wait = attempt * 5
                print(f"\n      [RETRY {attempt}/3] Koneksi timeout, tunggu {wait}s...", flush=True)
                time.sleep(wait)
            else:
                raise
    return session


def get_csrf_token(session: requests.Session) -> str:
    """Ambil token CSRF dari halaman /statistik."""
    for attempt in range(1, 4):
        try:
            response = session.get(STAT_URL, timeout=120)
            response.raise_for_status()
            html = response.text

            match = re.search(
                r'name=["\']_token["\']\s+value=["\']([^"\']+)["\']', html, flags=re.I
            )
            if not match:
                match = re.search(r'_token\s*[:=]\s*["\']([^"\']+)["\']', html, flags=re.I)
            if not match:
                raise RuntimeError("[ERROR] Token CSRF tidak ditemukan dari halaman /statistik")

            return match.group(1)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < 3:
                wait = attempt * 5
                print(f"      [RETRY {attempt}/3] Timeout, tunggu {wait}s...", flush=True)
                time.sleep(wait)
            else:
                raise
    return ""


# --------------- Data Pasar & Komoditas -----------------------------------


def get_all_commodities(session: requests.Session) -> list[dict[str, Any]]:
    """
    Ambil daftar SEMUA komoditas yang tersedia di portal
    dari endpoint DataTables /harga_pangan.
    """
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
    }
    params = {
        "draw": 1,
        "start": 0,
        "length": 200,
        "id_pasar": TARGET_MARKET_ID,
    }

    # Retry sampai 3 kali
    for attempt in range(1, 4):
        try:
            response = session.get(LIST_URL, params=params, headers=headers, timeout=120)
            response.raise_for_status()
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < 3:
                wait = attempt * 10  # 10s, 20s
                print(f"      [RETRY {attempt}/3] Timeout, tunggu {wait}s...", flush=True)
                time.sleep(wait)
            else:
                raise
    else:
        return []

    payload = response.json()
    if not isinstance(payload, dict):
        return []

    rows = payload.get("data", [])
    if not isinstance(rows, list):
        return []

    commodities: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue

        commodity_id = row.get("id_komoditas")
        price_row_id = row.get("id_harga_pangan")
        commodity_obj = row.get("komoditas")

        if commodity_id is None or price_row_id is None:
            continue

        commodity_name = ""
        if isinstance(commodity_obj, dict):
            commodity_name = str(commodity_obj.get("nama_komoditas", ""))

        if not commodity_name:
            continue

        key = str(commodity_id)
        if key in seen_ids:
            continue

        commodities.append(
            {
                "id_komoditas": key,
                "nama_komoditas": commodity_name,
                "id_harga_pangan": str(price_row_id),
            }
        )
        seen_ids.add(key)

    return commodities


def match_commodities(
    all_commodities: list[dict[str, Any]],
    pilihan: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Cocokkan nama komoditas yang dipilih user dengan daftar komoditas portal.
    Menggunakan partial match (case-insensitive).
    """
    matched: list[dict[str, Any]] = []
    unmatched: list[str] = []

    for nama_input in pilihan:
        found = False
        keyword = nama_input.strip().lower()

        for commodity in all_commodities:
            if keyword in commodity["nama_komoditas"].lower():
                # Cek duplikat
                if not any(
                    m["id_komoditas"] == commodity["id_komoditas"] for m in matched
                ):
                    matched.append(commodity)
                found = True
                break

        if not found:
            unmatched.append(nama_input)

    return matched, unmatched


# --------------- Scrape Data Harga ----------------------------------------


def _parse_chart_response(body: Any) -> tuple[list[str], list[Any]]:
    """Parse JSON respons chart dari endpoint /statistik."""
    if not isinstance(body, dict):
        return [], []

    if body.get("status") is not True:
        return [], []

    data = body.get("data", {})
    if not isinstance(data, dict):
        return [], []

    categories = data.get("categories", [])
    if not isinstance(categories, list):
        categories = []

    series = data.get("series", [])
    points: list[Any] = []

    if isinstance(series, list):
        if (
            series
            and isinstance(series[0], dict)
            and isinstance(series[0].get("data"), list)
        ):
            points = series[0]["data"]
        else:
            points = series
    elif isinstance(series, dict) and isinstance(series.get("data"), list):
        points = series["data"]

    return [str(x) for x in categories], points


def _request_chart_chunk(
    session: requests.Session,
    token: str,
    commodity_id: str,
    start_date: dt.date,
    end_date: dt.date,
    max_retries: int = 3,
) -> tuple[list[str], list[Any]]:
    """Satu request POST untuk satu potongan rentang tanggal."""
    payload = [
        ("_token", token),
        ("statistik", "pasar"),
        ("id_pasar", str(TARGET_MARKET_ID)),
        ("id_komoditas[]", str(commodity_id)),
        ("tgl_mulai", start_date.strftime("%Y-%m-%d")),
        ("tgl_akhir", end_date.strftime("%Y-%m-%d")),
    ]

    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            timeout = 60 + (attempt - 1) * 30
            response = session.post(
                STAT_URL,
                data=payload,
                headers=ajax_headers(),
                timeout=timeout,
            )
            response.raise_for_status()

            body = response.json()
            return _parse_chart_response(body)

        except requests.exceptions.HTTPError as e:
            last_error = e
            status = e.response.status_code if e.response is not None else "?"
            label = f"HTTP {status}"
        except requests.exceptions.Timeout as e:
            last_error = e
            label = "timeout"
        except requests.exceptions.ConnectionError as e:
            last_error = e
            label = "koneksi putus"
        except ValueError as e:
            last_error = e
            label = "respons bukan JSON"

        if attempt < max_retries:
            wait = attempt * 10
            print(
                f"\n             [RETRY {attempt}/{max_retries}] {label}, tunggu {wait}s...",
                end=" ",
                flush=True,
            )
            time.sleep(wait)
        elif last_error is not None:
            raise last_error

    return [], []


def get_chart_data(
    session: requests.Session,
    token: str,
    commodity_id: str,
    start_date: dt.date,
    end_date: dt.date,
    refresh_token: Callable[[requests.Session], str] | None = None,
) -> tuple[list[str], list[Any]]:
    """
    Ambil data harga dari endpoint /statistik (POST).
    Rentang besar dipecah per CHUNK_DAYS hari agar server tidak timeout.
    """
    chunks = iter_date_chunks(start_date, end_date)
    merged: dict[str, Any] = {}
    current_token = token

    for idx, (chunk_start, chunk_end) in enumerate(chunks, 1):
        if idx > 1:
            time.sleep(REQUEST_DELAY_SEC)
            if refresh_token is not None:
                current_token = refresh_token(session)

        if len(chunks) > 1:
            print(
                f"\n             chunk {idx}/{len(chunks)} "
                f"({chunk_start} s.d. {chunk_end})...",
                end=" ",
                flush=True,
            )

        categories, points = _request_chart_chunk(
            session,
            current_token,
            commodity_id,
            chunk_start,
            chunk_end,
        )

        for date_text, price_raw in zip(categories, points):
            merged[str(date_text)] = price_raw

    if not merged:
        return [], []

    dates_sorted = sorted(merged.keys())
    return dates_sorted, [merged[d] for d in dates_sorted]


# --------------- Main -----------------------------------------------------


def main() -> None:
    banner()

    # Hitung rentang tanggal dari TAHUN_MULAI dan TAHUN_AKHIR
    start_date = dt.date(TAHUN_MULAI, 1, 1)
    today = dt.date.today()

    if TAHUN_AKHIR >= today.year:
        end_date = today
    else:
        end_date = dt.date(TAHUN_AKHIR, 12, 31)

    print(f"\n>> Rentang tanggal: {start_date} s.d. {end_date}")
    print(f">> Jumlah komoditas yang diminta: {len(KOMODITAS_PILIHAN)}")

    # -- Step 1: Buat session --
    print("\n[1/4] Membuat koneksi ke portal...")
    session = create_session()

    # -- Step 2: Ambil daftar komoditas --
    print("[2/4] Mengambil daftar komoditas tersedia...")
    all_commodities = get_all_commodities(session)
    print(f"      -> Ditemukan {len(all_commodities)} komoditas di portal")

    if not all_commodities:
        print("[ERROR] Gagal mengambil daftar komoditas dari portal!")
        print("        Pastikan koneksi internet aktif dan portal dapat diakses.")
        sys.exit(1)

    # Tampilkan daftar komoditas yang tersedia
    print("\n   Daftar komoditas tersedia di portal:")
    print("   " + "-" * 55)
    for i, c in enumerate(all_commodities, 1):
        print(f"   {i:3d}. {c['nama_komoditas']} (ID: {c['id_komoditas']})")
    print("   " + "-" * 55)

    # -- Step 3: Cocokkan komoditas pilihan --
    print("\n[3/4] Mencocokkan komoditas pilihan...")
    matched, unmatched = match_commodities(all_commodities, KOMODITAS_PILIHAN)

    if unmatched:
        print(f"\n   [WARNING] Komoditas tidak ditemukan ({len(unmatched)}):")
        for name in unmatched:
            print(f'       x "{name}"')
        print("       -> Pastikan nama sesuai daftar di atas (partial match OK)")

    if not matched:
        print("\n[ERROR] Tidak ada komoditas yang cocok! Script berhenti.")
        sys.exit(1)

    print(f"\n   [OK] Komoditas yang akan di-scrape ({len(matched)}):")
    for i, m in enumerate(matched, 1):
        print(f"       {i}. {m['nama_komoditas']} (ID: {m['id_komoditas']})")

    # -- Step 4: Scrape data harga --
    print("\n[4/4] Mengambil data harga dari portal...")
    csrf_token = get_csrf_token(session)

    records: list[dict[str, Any]] = []
    failed_items: list[str] = []
    total = len(matched)

    for idx, item in enumerate(matched, 1):
        nama = item["nama_komoditas"]
        print(f"      [{idx}/{total}] {nama}...", end=" ", flush=True)

        try:
            if idx > 1:
                time.sleep(REQUEST_DELAY_SEC)
                csrf_token = get_csrf_token(session)

            categories, points = get_chart_data(
                session,
                csrf_token,
                item["id_komoditas"],
                start_date,
                end_date,
                refresh_token=get_csrf_token,
            )

            if not categories or not points:
                print("[SKIP] Tidak ada data")
                continue

            count = 0
            for date_text, price_raw in zip(categories, points):
                try:
                    date_obj = dt.datetime.strptime(str(date_text), "%Y-%m-%d").date()
                except ValueError:
                    continue

                if not (start_date <= date_obj <= end_date):
                    continue

                price_value = to_float(price_raw)
                if price_value is None:
                    continue

                records.append(
                    {
                        "tanggal": date_obj.isoformat(),
                        "id_komoditas": item["id_komoditas"],
                        "nama_komoditas": nama,
                        "id_harga_pangan": item["id_harga_pangan"],
                        "nama_pasar": TARGET_MARKET_NAME,
                        "harga": price_value,
                    }
                )
                count += 1

            print(f"OK - {count} data harian")

        except Exception as e:
            print(f"[GAGAL] {type(e).__name__}: {e}")
            failed_items.append(nama)
            continue

    # -- Simpan ke CSV --
    if not records:
        print("\n[ERROR] Tidak ada data yang berhasil di-scrape!")
        sys.exit(1)

    records.sort(key=lambda x: (x["nama_komoditas"], x["tanggal"]))

    # Simpan di folder yang sama dengan script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, OUTPUT_CSV)

    fieldnames = [
        "tanggal",
        "id_komoditas",
        "nama_komoditas",
        "id_harga_pangan",
        "nama_pasar",
        "harga",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    # -- Summary --
    print("\n" + "=" * 70)
    print("  SCRAPING SELESAI!")
    print(f"  File output : {output_path}")
    print(f"  Total baris : {len(records):,}")
    print(f"  Komoditas   : {len(matched)}")
    print(f"  Periode     : {start_date} s.d. {end_date}")
    print("=" * 70)

    # Ringkasan per komoditas
    print("\n  Ringkasan per komoditas:")
    print("  " + "-" * 55)
    from collections import Counter

    counts = Counter(r["nama_komoditas"] for r in records)
    for nama, jumlah in sorted(counts.items()):
        print(f"  - {nama}: {jumlah:,} data harian")
    print("  " + "-" * 55)

    if failed_items:
        print(f"\n  [WARNING] Komoditas yang gagal di-scrape ({len(failed_items)}):")
        for nama in failed_items:
            print(f"  x {nama}")
        print("  -> Coba jalankan ulang script untuk mengambil data yang gagal.")


if __name__ == "__main__":
    main()
