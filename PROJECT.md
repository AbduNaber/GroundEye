# GroundEye — Proje Durumu

## Sistem Mimarisi

```
ESP32 nodes (3 adet)
    │ MQTT binary stream — groundeye/stream/<node>
    │ MQTT JSON sidecar  — groundeye/stream_meta/<node>
    ▼
C++ DSP Servisi (groundeye_dsp)
    │ Butterworth bandpass 4-80Hz
    │ Hilbert envelope
    │ STA/LTA event detection
    └── MQTT JSON — groundeye/event
    ▼
C++ Orkestrasyon Servisi (groundeye_orch)
    │ 2s fusion window
    │ Amplitude weighted centroid
    │ TDOA Gauss-Newton solver
    │ SQLite event log
    └── MQTT JSON — groundeye/location
    ▼
PyQt Ground Station GUI  ← YAPILACAK
    └── paho-mqtt subscribe → groundeye/location
```

## groundeye/location Payload (C++ servisinden gelir)

```json
{
  "timestamp_ms": 1748812345123,
  "node_count": 3,
  "nearest_node": "node-1",
  "best_method": "tdoa",
  "tdoa_used": true,
  "x": 0.71,
  "y": 0.39,
  "confidence": 0.84,
  "amplitude": {
    "x": 0.87,
    "y": 0.43,
    "confidence": 0.61
  },
  "tdoa": {
    "x": 0.71,
    "y": 0.39,
    "confidence": 0.84
  },
  "est_dist_m": 2.3,
  "nodes": [
    {"node_id": "node-1", "rms_energy": 147.3, "duration_ms": 264, "time_synced": true},
    {"node_id": "node-2", "rms_energy":  82.1, "duration_ms": 251, "time_synced": true},
    {"node_id": "node-3", "rms_energy":  41.6, "duration_ms": 238, "time_synced": true}
  ]
}
```

## groundeye/status Payload (ESP32 node'lardan gelir)

```json
{
  "node_id": "node-1",
  "status": "online",
  "uptime_ms": 52341,
  "rssi": -54,
  "published": 412,
  "dropped_batches": 0
}
```

## Node Konumları (config.json'dan)

Üçgen yerleşim — metre cinsinden:
- node-1: (0.0, 0.0)
- node-2: (3.0, 0.0)
- node-3: (1.5, 2.6)

## MQTT Broker

Host: 10.169.254.204 (geliştirme) → Pi IP (deployment)
Port: 1883

## Subscribe edilecek topicler

- groundeye/location     → konum + füzyon sonucu
- groundeye/status       → node heartbeat / online-offline
- groundeye/event        → ham event (opsiyonel, debug için)
- groundeye/dsp_debug    → DSP servis logları (opsiyonel)

## Teknoloji

- Python 3.10+
- PyQt5 veya PyQt6
- paho-mqtt
- Tailscale üzerinden remote erişim (Pi broker'a bağlanır)

## GUI Gereksinimleri

### Ana Harita Paneli
- Node'ların üçgen yerleşimini göster (sabit)
- Amplitude sonucunu mavi nokta olarak göster
- TDOA sonucunu kırmızı nokta olarak göster
- Best sonucunu yıldız/büyük nokta olarak göster
- Son N konumu iz olarak göster (path tracking)
- Node'ları label ile göster (node-1, node-2, node-3)

### Node Durum Paneli
- Her node için: online/offline, RSSI, dropped_batches
- NTP sync durumu
- Son heartbeat zamanı

### Event Paneli
- Son 20 event listesi
- timestamp, best_method, x, y, confidence, node_count
- TDOA kullanıldıysa işaretle

### Bağlantı Paneli
- Broker IP / port ayarı
- Bağlan / Kes butonu
- Bağlantı durumu

### Opsiyonel
- RMS enerji bar chart (her node için)
- Confidence göstergesi
- Export to CSV butonu
