"""
GroundEye — Binary Stream to JSON Converter
============================================
Ham binary ADC verisini okunabilir JSON formatına çevirir.

Kullanım:
    python bin_to_json.py /tmp/node1.bin
    python bin_to_json.py /tmp/node1.bin --pretty
    python bin_to_json.py /tmp/node1.bin --stats-only
    python bin_to_json.py /tmp/node1.bin --output /tmp/output.json
"""

import sys
import json
import argparse
import numpy as np
from pathlib import Path

FS = 2000  # Hz

def convert(path: str, pretty: bool, stats_only: bool, output: str):
    raw = np.fromfile(path, dtype='<i2')

    if len(raw) == 0:
        print("Hata: Dosya boş veya okunamadı.")
        sys.exit(1)

    duration_s  = len(raw) / FS
    t           = np.arange(len(raw)) / FS

    # ── İstatistikler ──────────────────────────────────────────
    stats = {
        "file":           path,
        "total_samples":  int(len(raw)),
        "duration_s":     round(duration_s, 4),
        "sample_rate_hz": FS,
        "adc_min":        int(raw.min()),
        "adc_max":        int(raw.max()),
        "adc_mean":       round(float(raw.mean()), 2),
        "adc_median":     round(float(np.median(raw)), 2),
        "adc_std":        round(float(raw.std()), 2),
        "adc_range":      int(raw.max() - raw.min()),
    }

    if stats_only:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    # ── Her sample için zaman damgalı kayıt ───────────────────
    # Tüm samples tek tek yazılırsa dosya çok büyür.
    # Bunun yerine batch grupları olarak yaz — her 256 sample bir batch.
    BATCH = 256
    batches = []
    for i in range(0, len(raw), BATCH):
        chunk = raw[i:i+BATCH]
        batch_t = round(i / FS, 4)
        batches.append({
            "batch_index":   i // BATCH,
            "time_s":        batch_t,
            "sample_count":  int(len(chunk)),
            "adc_min":       int(chunk.min()),
            "adc_max":       int(chunk.max()),
            "adc_mean":      round(float(chunk.mean()), 2),
            "adc_std":       round(float(chunk.std()), 2),
            "samples":       chunk.tolist(),   # ham ADC değerleri
        })

    result = {
        "metadata": stats,
        "batches":  batches,
    }

    # ── Çıktı ──────────────────────────────────────────────────
    indent = 2 if pretty else None

    if output:
        out_path = output
    else:
        out_path = str(Path(path).with_suffix('.json'))

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=indent, ensure_ascii=False)

    print(f"Dönüştürüldü: {path}")
    print(f"  Samples  : {stats['total_samples']}")
    print(f"  Süre     : {stats['duration_s']}s")
    print(f"  ADC min  : {stats['adc_min']}")
    print(f"  ADC max  : {stats['adc_max']}")
    print(f"  ADC mean : {stats['adc_mean']}")
    print(f"  ADC std  : {stats['adc_std']}")
    print(f"  Çıktı    : {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="GroundEye binary ADC verisini JSON'a çevirir"
    )
    parser.add_argument("file",
                        help="Giriş .bin dosyası")
    parser.add_argument("--pretty",
                        action="store_true",
                        help="Girintili (okunabilir) JSON yaz")
    parser.add_argument("--stats-only",
                        action="store_true",
                        help="Sadece istatistikleri yaz, sample'ları yazma")
    parser.add_argument("--output", "-o",
                        default=None,
                        help="Çıktı dosya yolu (varsayılan: giriş adı .json)")
    args = parser.parse_args()

    convert(args.file, args.pretty, args.stats_only, args.output)
