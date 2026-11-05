# Referensi G-code Hasil Print SUKSES (bedah per-file)

Dihasilkan dari teardown otomatis (parser teks + labcheck per-layer) atas tiga
file yang dipakai user sebagai patokan mutu. Semuanya **dialect vendor**
(ZhenCai / Taesin letter printer), bukan output slicer konvensional.

| # | file | tipe | arti bagi user |
|---|------|------|----------------|
| 1 | `5 (3).gcode` | 2 band (T0+T1) | **settingan fix printer** — hasil rapih, acuan MESIN |
| 2 | `arr.gcode`   | 2 band (T0+T1) | **acuan utama** — hasil cetak paling bersih, acuan STYLE |
| 3 | `TES IM.gcode`| 3 band (T0+T2+T1) | huruf K — **sample ALAS** (dasar tebal), hasil rapih |

## Angka proven (berlaku untuk ketiganya)

- **Layer step: 0.3 mm** di semua band semua file — sama persis dengan INI
  vendor (`dbHeightLayer=0.3`). Pola Z awal: 0.3 → 0.4 → 0.6 → 0.9 (ramp
  squash pertama), setelah itu konstan 0.3.
- **Trick Z vendor** di setiap mulai band: `G0 Z0.4` → `G0 Z0.3` → `G0 X.. Z0.9`
  → prime `E8` (F1800) → turun `Z0.3` → lead-in. Universal emitter
  tidak meniru pola ini (Marlin retracted-travel biasa), tapi mesin asli
  menerima keduanya.
- **Hotend**: 220°C (file `5` & `arr`, huruf pendek ≤15.3 mm);
  **230°C** at `TES IM` (huruf 50.7 mm — massa lebih besar, plastik lebih cair).
- **G92 E0** tiap pass + E absolut kubik; retract perubahan tool = `E-85`
  (F1200), prime balik `E85`. Ini dialect khusus — universal memakai
  M83 retraction fisik filament standar.

## Per-file

### 1. "5" — `5 (3).gcode` (settingan fix printer)

- 52 level Z, z 0.30..15.30 mm, 8858 move, path 97.3 m, 8410 titik.
- Ring-per-layer: 1 ring × 39 layer (huruf kontur tunggal), 16 ring × 6 layer
  (ruang sempit multi-kontur), 4/8/10/13 ring masing-masing 1 layer.
- Kecepatan print (mm/min): **3000 (50 mm/s) dominan**, 1800 untuk aproach,
  2400 detail sekunder; travel 18000.
- Band: T0 z 0.3..15.0 (74.15 m), T1 z 5.4..15.3 (23.16 m) — overlap band 5.4-15.0.
- Prime awal band: `E-85 F1200` → `E85 F1500` (mesin 2 nozzle, purging pair),
  turun separuh `E-42.5` sebelum mulai.

### 2. "arr" — `arr.gcode` (acuan utama, paling bersih)

- 20 level band-cycle, z 0.30..15.00, 22590 move, path 50.1 m, 20687 titik.
- Ring tiap layer lebih banyak & detail: 73 ring × 5 layer, 46/44/25 ring ×
  4-2 layer, 15/2 ring × 5 layer — arti: outline HF (high-frequency) banyak
  pas dinding-dinding tipis dekat.
- Kecepatan print bertingkat per fitur (mm/min): 2400 (2890 move), 1800 (2351),
  3000 (2290), 1500 (2004) — tier kecil→besar; travel 18000.
- Band: T0 z 0.3..15.0 (22.34 m), T1 z 2.4..5.4 (27.78 m).
- Prime F mulai 750 (lebih pelan dari "5": 1500) — pengaruh kecil.

### 3. "TES IM" — huruf K, sample ALAS

- 170 level Z, z span 0.30..50.70 mm (pas 169 × 0.3 + ramps), 101768 move,
  path 143.2 m, 100708 titik.
- Ring-per-layer: **2 ring × 164 layer** = dinding ganda konsisten (tebal),
  0 ring × 3 layer (pass isi solid), 6-7 ring × 3 layer (daerah detail).
- Kecepatan print (mm/min): **3000 dominan (53031+36834+4288 move)**,
  1800 detail; travel 12000 lebih pelan (huruf tinggi, akses sulit).
- Band (3 warna): T0 z 0.3..15.0 (33.63 m), T2 z 10.5..40.8 (82.36 m — band
  besar tengah), T1 z 40.5..50.7 (27.18 m top yang ramping).
- Hotend 230°C.

## Arti praktis

- **Layer 0.3 + F3000 (50 mm/s) + 220°C** = resep yang dipakai printer nyata
  untuk huruf ini. MachineProfile universal sekarang memakai angka ini
  (`work_speed=3000`, `nozzle_temp=220`) dengan layer dari INI (0.3).
- "arr" menunjukkan tiering kecepatan per-fitur (2400/1800/1500 untuk fitur
  kecil, 3000 untuk sisi lebar). Emitter universal belum melakukan dithering
  per-fitur — satu F per layer — cukup untuk mesin umum, dan bisa
  ditambahkan nanti kalau hasil universal kelihatan kurang bersih di sudut.
- "TES IM" menunjukkan 2-ring dinding ganda tiap layer menyusun huruf ALAS
  setinggi 50 mm secara stabil — sesuai pola walls+infill universal
  (2 epsilon solid + hatch), jadi cukup sebagai pegangan mental + dokumentasi,
  bukan perubahan kode.
