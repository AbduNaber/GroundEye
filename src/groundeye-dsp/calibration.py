#!/usr/bin/env python3
# ============================================================
#  GroundEye — Kalibrasyon Aracı (Python)
#
#  C++ calibrate.cpp mantığının birebir Python portu.
#  Gerçek DSP pipeline (IIR + Envelope + STA/LTA) kullanır.
#
#  Kullanım:
#    python3 groundeye_calibrate.py --config config.json
#    python3 groundeye_calibrate.py --broker 192.168.4.1 --nodes node-1,node-2,node-3
#    python3 groundeye_calibrate.py --baseline 5 --sigma-k 5.0 --seg-on 1.6
#
#  Akış:
#    1) İlk --baseline saniye HİÇ VURMA — gürültü ölçülür
#    2) "ŞİMDİ VUR" yazınca sırayla node'lara vur
#    3) Ctrl+C → öneri basılır
# ============================================================

import argparse
import json
import math
import struct
import sys
import threading
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("[HATA] paho-mqtt kurulu değil: pip install paho-mqtt")
    sys.exit(1)

# ── Progress bar ─────────────────────────────────────────────
def progress_bar(duration_s, label):
    """Terminal'de canli geri sayac + progress bar"""
    start = time.time()
    bar_width = 30
    while True:
        elapsed = time.time() - start
        if elapsed >= duration_s:
            elapsed = duration_s
        ratio  = elapsed / duration_s
        filled = int(bar_width * ratio)
        bar    = "#" * filled + "." * (bar_width - filled)
        remaining = max(0, duration_s - elapsed)
        sys.stdout.write(
            "\r  " + C.CYAN + label + C.RESET +
            " [" + bar + "] " +
            C.YELLOW + str(int(remaining)) + "s" + C.RESET + "   "
        )
        sys.stdout.flush()
        if elapsed >= duration_s:
            print()
            break
        time.sleep(0.25)

# ── Renk kodları ──────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    RED    = "\033[91m"
    GREY   = "\033[90m"

def cprint(color, msg):
    print(f"{color}{msg}{C.RESET}")

# ── Butterworth bandpass — dsp.hpp ile aynı katsayılar ────────
B = [
    0.00015140978602327354, 0.0, -0.0006056391440930942, 0.0,
    0.0009084587161396413,  0.0, -0.0006056391440930942, 0.0,
    0.00015140978602327354,
]
A = [
    1.0, -7.36508881404129, 23.759641924916412, -43.853259539567226,
    50.65340482669531, -37.49565167249384, 17.37135926566954,
    -4.605314959075437, 0.5349089679706243,
]
FILTER_ORDER = 8

# ── DSP sınıfları — dsp.hpp ile birebir aynı mantık ──────────

class IIRFilter:
    def __init__(self):
        self.state = [0.0] * FILTER_ORDER

    def process(self, x):
        y = B[0] * x + self.state[0]
        for i in range(1, FILTER_ORDER):
            self.state[i - 1] = B[i] * x - A[i] * y + self.state[i]
        self.state[FILTER_ORDER - 1] = B[FILTER_ORDER] * x - A[FILTER_ORDER] * y
        return y

    def reset(self):
        self.state = [0.0] * FILTER_ORDER


class EnvelopeEstimator:
    def __init__(self, window=100):
        self.window = max(1, window)
        self.buf = []
        self.sum = 0.0

    def process(self, x):
        sq = x * x
        self.buf.append(sq)
        self.sum += sq
        if len(self.buf) > self.window:
            self.sum -= self.buf.pop(0)
        if self.sum < 0:
            self.sum = 0.0
        return math.sqrt(self.sum / len(self.buf))

    def reset(self):
        self.buf.clear()
        self.sum = 0.0


class STALTADetector:
    def __init__(self, sta_len, lta_len, trigger_on, trigger_off):
        self.sta_len     = max(1, sta_len)
        self.lta_len     = max(1, lta_len)
        self.trigger_on  = trigger_on
        self.trigger_off = trigger_off
        self.sta_buf     = []
        self.lta_buf     = []
        self.sta_sum     = 0.0
        self.lta_sum     = 0.0
        self._ratio      = 0.0
        self.in_event    = False

    def process(self, env):
        # STA her zaman güncellenir
        self.sta_buf.append(env)
        self.sta_sum += env
        if len(self.sta_buf) > self.sta_len:
            self.sta_sum -= self.sta_buf.pop(0)

        # LTA sadece event dışında güncellenir
        if not self.in_event:
            self.lta_buf.append(env)
            self.lta_sum += env
            if len(self.lta_buf) > self.lta_len:
                self.lta_sum -= self.lta_buf.pop(0)

        sta = self.sta_sum / len(self.sta_buf) if self.sta_buf else 0.0
        lta = self.lta_sum / len(self.lta_buf) if self.lta_buf else 0.0
        self._ratio = sta / lta if lta > 1e-9 else 0.0

        if not self.in_event and self._ratio >= self.trigger_on:
            self.in_event = True
        elif self.in_event and self._ratio < self.trigger_off:
            self.in_event = False
        return self.in_event

    def ratio(self):
        return self._ratio

    def reset(self):
        self.sta_buf.clear()
        self.lta_buf.clear()
        self.sta_sum  = 0.0
        self.lta_sum  = 0.0
        self._ratio   = 0.0
        self.in_event = False


# ── Tek bir vuruşun ölçümleri — C++ Tap struct karşılığı ──────
class Tap:
    def __init__(self):
        self.peak_amp    = 0.0
        self.peak_ratio  = 0.0
        self.rms         = 0.0
        self.duration_ms = 0.0
        self.snr         = 0.0
        self.time_synced = False


# ── Node kalibrasyon durumu — C++ NodeCalib karşılığı ─────────
class NodeCalib:
    def __init__(self, fs, sta_s, lta_s, env_window_s,
                 baseline_s, sigma_k, seg_on):
        self.fs              = fs
        self.lta_len         = int(lta_s * fs)
        self.baseline_samples = int(baseline_s * fs)
        self.sigma_k         = sigma_k

        self.filter   = IIRFilter()
        self.envelope = EnvelopeEstimator(window=int(env_window_s * fs))
        self.stalta   = STALTADetector(
            sta_len    = int(sta_s * fs),
            lta_len    = int(lta_s * fs),
            trigger_on = seg_on,
            trigger_off= max(1.05, seg_on * 0.75),
        )

        self.sample_idx   = 0
        self.time_synced  = False
        self.announced    = False

        # Gürültü istatistiği (baseline + event dışı)
        self.noise_sum    = 0.0
        self.noise_sqsum  = 0.0
        self.noise_n      = 0
        self.baseline_peak = 0.0  # baseline sırasında gözlenen en yüksek sahte tetik
        self.rejected     = 0

        # Event state
        self.in_event     = False
        self.onset_idx    = 0
        self.peak_amp     = 0.0
        self.peak_ratio   = 0.0
        self.rms_acc      = 0.0
        self.rms_n        = 0

        self.taps  = []   # kabul edilen vuruşlar
        self.weak  = []   # eşik altı kalan vuruşlar (teşhis)
        self.accepting = False  # sadece aktif sıradayken vuruş kabul et

        self.lock  = threading.Lock()

    def noise_mean(self):
        return self.noise_sum / self.noise_n if self.noise_n else 0.0

    def noise_std(self):
        if self.noise_n < 2:
            return 0.0
        m = self.noise_mean()
        v = self.noise_sqsum / self.noise_n - m * m
        return math.sqrt(v) if v > 0 else 0.0

    def gate(self):
        """Gürültüden ölçülmüş kabul eşiği — keyfi sayı yok"""
        stat = self.noise_mean() + self.sigma_k * self.noise_std()
        seen = self.baseline_peak * 1.3
        return max(stat, seen)

    def in_baseline(self):
        return self.sample_idx < self.baseline_samples

    def process(self, raw):
        """
        Tek sample işle.
        Yeni kabul edilen vuruş tamamlandıysa True döner.
        """
        # DC offset çıkar: ADC 12-bit unsigned → 2048 merkez
        # IIR filtre DC'yi keser ama başlangıç transient'ını azaltır
        f   = self.filter.process(float(raw) - 2048.0)
        env = self.envelope.process(f)
        trig  = self.stalta.process(env)
        ratio = self.stalta.ratio()
        idx   = self.sample_idx
        self.sample_idx += 1

        if not self.in_event and trig:
            self.in_event   = True
            self.onset_idx  = idx
            self.peak_amp   = env
            self.peak_ratio = ratio
            self.rms_acc    = f * f
            self.rms_n      = 1

        elif self.in_event and trig:
            self.rms_acc += f * f
            self.rms_n   += 1
            if env   > self.peak_amp:   self.peak_amp   = env
            if ratio > self.peak_ratio: self.peak_ratio = ratio

        elif self.in_event and not trig:
            self.in_event = False
            dur_ms = (idx - self.onset_idx) * 1000.0 / self.fs

            # Çok kısa — gürültü spike
            if dur_ms < 40.0:
                return False

            # LTA henüz dolmadı — oran güvenilmez
            if self.onset_idx < self.lta_len:
                return False

            # Baseline fazındaki tetikler: gürültü tepesi olarak kaydet
            if self.onset_idx < self.baseline_samples:
                if self.peak_amp > self.baseline_peak:
                    self.baseline_peak = self.peak_amp
                self.rejected += 1
                return False

            t = Tap()
            t.peak_amp    = self.peak_amp
            t.peak_ratio  = self.peak_ratio
            t.rms         = math.sqrt(self.rms_acc / max(1, self.rms_n))
            t.duration_ms = dur_ms
            m = self.noise_mean()
            t.snr         = self.peak_amp / m if m > 1e-9 else 0.0
            t.time_synced = self.time_synced

            # Sira bu node'da degilse kabul etme
            if not self.accepting:
                self.rejected += 1
                return False

            # Esik alti mi?
            if self.peak_amp < self.gate():
                self.weak.append(t)
                self.rejected += 1
                return False

            self.taps.append(t)
            return True

        else:
            # Gürültü istatistiğini yalnızca baseline'da ve
            # filtre transient'ı geçtikten sonra öğren (ilk 1s atla)
            if (self.sample_idx >= self.fs and
                    self.sample_idx < self.baseline_samples):
                self.noise_sum   += env
                self.noise_sqsum += env * env
                self.noise_n     += 1

        return False


# ── MQTT Collector ────────────────────────────────────────────
class Collector:
    def __init__(self, broker, port, nodes, baseline_s, sigma_k, seg_on,
                 fs, sta_s, lta_s, env_window_s):
        self.nodes     = nodes
        self.connected = threading.Event()
        self.calib     = {
            n: NodeCalib(fs, sta_s, lta_s, env_window_s,
                         baseline_s, sigma_k, seg_on)
            for n in nodes
        }
        self.client = mqtt.Client(client_id="groundeye-calibrate")
        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message    = self._on_message
        self.client.connect(broker, port, keepalive=60)
        self.client.loop_start()
        if not self.connected.wait(timeout=8):
            cprint(C.RED, f"[HATA] Broker'a bağlanılamadı: {broker}:{port}")
            sys.exit(1)

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            for n in self.nodes:
                client.subscribe(f"groundeye/stream/{n}",      qos=0)
                client.subscribe(f"groundeye/stream_meta/{n}", qos=0)
            self.connected.set()
            cprint(C.GREEN, f"[MQTT] Bağlandı")
        else:
            cprint(C.RED, f"[MQTT] Bağlantı hatası rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            cprint(C.YELLOW, f"[MQTT] Bağlantı kesildi rc={rc}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic

        # time_synced bilgisini meta'dan al
        if "stream_meta/" in topic:
            node_id = topic.split("stream_meta/")[-1]
            try:
                j = json.loads(msg.payload)
                nc = self.calib.get(node_id)
                if nc:
                    with nc.lock:
                        nc.time_synced = j.get("time_synced", False)
            except Exception:
                pass
            return

        # Binary stream
        if "stream/" in topic and "_meta" not in topic:
            node_id = topic.split("stream/")[-1]
            nc = self.calib.get(node_id)
            if not nc:
                return

            count = len(msg.payload) // 2
            if count == 0:
                return
            samples = struct.unpack(f"<{count}h", msg.payload[:count * 2])

            with nc.lock:
                before      = len(nc.taps)
                before_weak = len(nc.weak)

                for s in samples:
                    nc.process(s)

                # Yeni kabul edilen vuruşları bas
                for k in range(before, len(nc.taps)):
                    t = nc.taps[k]
                    print(
                        f"{C.GREEN}[VURUŞ]{C.RESET} {node_id}"
                        f"  #{k+1}"
                        f"  peak_amp={t.peak_amp:.2f}"
                        f"  ratio={t.peak_ratio:.2f}"
                        f"  rms={t.rms:.2f}"
                        f"  snr={t.snr:.2f}"
                        f"  dur={t.duration_ms:.0f}ms"
                        f"  sync={'OK' if t.time_synced else 'YOK'}"
                    )

                # Eşik altı kalanları göster — teşhis
                for k in range(before_weak, len(nc.weak)):
                    t = nc.weak[k]
                    print(
                        f"{C.GREY}[zayıf] {node_id}"
                        f"  peak_amp={t.peak_amp:.2f}"
                        f"  ratio={t.peak_ratio:.2f}"
                        f"  (eşik={nc.gate():.2f})"
                        f"  → eşiğin ALTINDA, elendi{C.RESET}"
                    )


# ── Özet & öneri — C++ printSummary karşılığı ─────────────────
def print_summary(calib, nodes, fs, sta_s, lta_s, env_window_s,
                  sigma_k, out_path):
    print()
    cprint(C.BOLD, "=" * 60)
    cprint(C.BOLD, " KALİBRASYON ÖZETİ")
    cprint(C.BOLD, "=" * 60)

    global_min_ratio = 1e18
    global_min_amp   = 1e18
    global_max_gate  = 0.0
    total_taps       = 0
    all_synced       = True
    node_results     = {}

    for node_id in nodes:
        nc = calib.get(node_id)
        if not nc:
            continue

        print(f"\n{C.CYAN}[{node_id}]{C.RESET}"
              f"  vuruş={len(nc.taps)}"
              f"  elenen={nc.rejected}")
        print(f"   gürültü μ={nc.noise_mean():.2f}"
              f"  σ={nc.noise_std():.2f}"
              f"  baseline_tepe={nc.baseline_peak:.2f}"
              f"  → ÖLÇÜLEN_EŞİK={nc.gate():.2f}")

        global_max_gate = max(global_max_gate, nc.gate())

        if not nc.taps:
            cprint(C.YELLOW, "   (vuruş yok — bu node'a vurmadın mı?)")
            all_synced = False
            continue

        amps   = [t.peak_amp   for t in nc.taps]
        ratios = [t.peak_ratio for t in nc.taps]
        snrs   = [t.snr        for t in nc.taps]
        n = len(nc.taps)

        print(f"   peak_amp : min={min(amps):.2f}"
              f"  ort={sum(amps)/n:.2f}"
              f"  max={max(amps):.2f}")
        print(f"   ratio    : min={min(ratios):.2f}"
              f"  ort={sum(ratios)/n:.2f}"
              f"  max={max(ratios):.2f}")
        print(f"   snr      : min={min(snrs):.2f}"
              f"  ort={sum(snrs)/n:.2f}")

        global_min_ratio = min(global_min_ratio, min(ratios))
        global_min_amp   = min(global_min_amp,   min(amps))
        total_taps      += n

        node_results[node_id] = {
            "gate":      nc.gate(),
            "min_amp":   min(amps),
            "min_ratio": min(ratios),
        }

        for t in nc.taps:
            if not t.time_synced:
                all_synced = False

    if total_taps == 0:
        cprint(C.RED, "\nHiç vuruş alınmadı — broker/node ayarlarını kontrol et.")
        return

    # ── Öneri hesapla — C++ printSummary ile aynı formül ──────
    # trigger_on: en zayıf gerçek vuruşun tepe oranının %60'ı
    trigger_on  = max(1.8, global_min_ratio * 0.6)
    trigger_off = max(1.2, trigger_on * 0.65)
    # min_peak_amp: gürültüden ölçülmüş en yüksek eşik
    min_peak_amp = global_max_gate
    # Ama en zayıf vuruşun %90'ını geçmesin
    if min_peak_amp > global_min_amp * 0.9:
        min_peak_amp = global_min_amp * 0.5

    # ── Per-node detection blokları ────────────────────────────
    per_node = {}
    for node_id, r in node_results.items():
        node_trigger_on  = max(1.8, r["min_ratio"] * 0.6)
        node_trigger_off = max(1.2, node_trigger_on * 0.65)
        node_min_amp     = r["gate"]
        if node_min_amp > r["min_amp"] * 0.9:
            node_min_amp = r["min_amp"] * 0.5
        per_node[node_id] = {
            "trigger_on":      round(node_trigger_on,  2),
            "trigger_off":     round(node_trigger_off, 2),
            "min_peak_amp":    round(node_min_amp,      2),
            "fs":              fs,
            "sta_s":           sta_s,
            "lta_s":           lta_s,
            "env_window_s":    env_window_s,
            "min_duration_ms": 80,
        }

    print()
    cprint(C.BOLD, "=" * 60)
    cprint(C.BOLD, " ÖNERİLEN DEĞERLER")
    cprint(C.BOLD, "=" * 60)
    print(f"\n{C.YELLOW}Global detection bloğu (fallback):{C.RESET}")
    global_block = {
        "fs":              fs,
        "sta_s":           sta_s,
        "lta_s":           lta_s,
        "trigger_on":      round(trigger_on,  2),
        "trigger_off":     round(trigger_off, 2),
        "env_window_s":    env_window_s,
        "min_duration_ms": 80,
        "min_peak_amp":    round(min_peak_amp, 2),
    }
    print(json.dumps({"detection": global_block}, indent=2))

    print(f"\n{C.YELLOW}Per-node detection blokları:{C.RESET}")
    print(json.dumps({"nodes_detection": per_node}, indent=2))

    # JSON dosyasına yaz
    output = {
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "global_detection": global_block,
        "nodes": per_node,
    }
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    cprint(C.GREEN, f"\n✓ Kaydedildi: {out_path}")

    if not all_synced:
        cprint(C.YELLOW,
               "\n[UYARI] Bazı vuruşlarda time_synced=YOK. "
               "TDOA için NTP senkronizasyonunu düzelt.")

    if global_max_gate >= global_min_amp:
        cprint(C.RED,
               f"\n[UYARI] En gürültülü node eşiği ({global_max_gate:.2f}) "
               f"en zayıf vuruştan ({global_min_amp:.2f}) YÜKSEK.\n"
               f"        Yazılımla çözülmez — daha sert vur veya "
               f"gürültü kaynağını (kablo/zemin/RF) azalt.")

    cprint(C.GREY,
           f"\nNot: min_peak_amp uydurma değil — "
           f"μ + {sigma_k}·σ ve gözlenen gürültü tepesinden hesaplandı.")


# ── Ana akış ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="GroundEye Kalibrasyon Aracı")
    parser.add_argument("--broker",   default="192.168.4.1")
    parser.add_argument("--port",     type=int,   default=1883)
    parser.add_argument("--nodes",    default="node-1,node-2,node-3")
    parser.add_argument("--config",   default="")
    parser.add_argument("--baseline", type=float, default=30.0,
                        help="Gürültü öğrenme süresi sn (bu sürede VURMA)")
    parser.add_argument("--sigma-k",  type=float, default=5.0,
                        help="Eşik = μ + K·σ (düşür = daha hassas)")
    parser.add_argument("--seg-on",   type=float, default=1.6,
                        help="STA/LTA segmentasyon eşiği (düşür = daha hassas)")
    parser.add_argument("--out",      default="calibration_result.json")
    args = parser.parse_args()

    # Varsayılan DSP parametreleri
    broker = args.broker
    port   = args.port
    nodes  = [n.strip() for n in args.nodes.split(",") if n.strip()]
    fs, sta_s, lta_s, env_window_s = 2000, 0.1, 1.0, 0.05

    # config.json varsa oku
    if args.config:
        try:
            with open(args.config) as f:
                j = json.load(f)
            broker = j.get("broker", broker)
            port   = j.get("port",   port)
            if "nodes" in j and j["nodes"]:
                nodes = []
                for n in j["nodes"]:
                    if isinstance(n, str): nodes.append(n)
                    elif isinstance(n, dict) and "id" in n: nodes.append(n["id"])
            if "detection" in j:
                d = j["detection"]
                fs           = d.get("fs",           fs)
                sta_s        = d.get("sta_s",        sta_s)
                lta_s        = d.get("lta_s",        lta_s)
                env_window_s = d.get("env_window_s", env_window_s)
            cprint(C.GREEN, f"[CONFIG] Yüklendi: {args.config}")
        except Exception as e:
            cprint(C.YELLOW, f"[CONFIG] Yüklenemedi: {e}")

    print()
    cprint(C.BOLD + C.CYAN, "╔══════════════════════════════════════════╗")
    cprint(C.BOLD + C.CYAN, "║      GroundEye — Kalibrasyon Aracı       ║")
    cprint(C.BOLD + C.CYAN, "╚══════════════════════════════════════════╝")
    print()
    cprint(C.GREY, f"  Broker   : {broker}:{port}")
    cprint(C.GREY, f"  Nodes    : {', '.join(nodes)}")
    cprint(C.GREY, f"  Baseline : {args.baseline}s  (bu sürede HİÇ VURMA)")
    cprint(C.GREY, f"  Sigma-K  : {args.sigma_k}  (eşik = μ + K·σ)")
    cprint(C.GREY, f"  Seg-on   : {args.seg_on}  (STA/LTA segmentasyon)")
    print()
    cprint(C.YELLOW, ">>> Başlıyor. Her node için 'BASELINE BİTTİ — ŞİMDİ VUR!'")
    cprint(C.YELLOW, ">>> yazısını bekle, sonra o node'a 3-5 kez vur.")
    cprint(C.YELLOW, ">>> Bitince Ctrl+C.")
    print()

    collector = Collector(
        broker, port, nodes,
        baseline_s   = args.baseline,
        sigma_k      = args.sigma_k,
        seg_on       = args.seg_on,
        fs           = fs,
        sta_s        = sta_s,
        lta_s        = lta_s,
        env_window_s = env_window_s,
    )

    # ── Baseline: tüm node'lar aynı anda gürültü öğrenir ──
    cprint(C.YELLOW, f'>>> İlk {args.baseline:.0f} saniye HİÇ VURMA — gürültü ölçülüyor...')
    try:
        progress_bar(args.baseline, 'Baseline')
    except KeyboardInterrupt:
        collector.stop()
        print_summary(
            calib=collector.calib, nodes=nodes,
            fs=fs, sta_s=sta_s, lta_s=lta_s,
            env_window_s=env_window_s, sigma_k=args.sigma_k,
            out_path=args.out,
        )
        return
    cprint(C.GREEN, '  ✓ Baseline tamamlandı.')

    # ── Sıralı vuruş: her node için ayrı ayrı ──
    for node_id in nodes:
        nc = collector.calib[node_id]
        print()
        cprint(C.BOLD + C.GREEN,
               f'>>> [{node_id}] SIRANIZ GELDİ — hazır olunca Enter.')
        cprint(C.GREY,
               f'    (μ={nc.noise_mean():.2f}  '
               f'σ={nc.noise_std():.2f}  '
               f'eşik={nc.gate():.2f})')
        try:
            input(f'  {C.YELLOW}[ENTER]{C.RESET} {node_id} için vurușa başla...')
        except KeyboardInterrupt:
            break

        with nc.lock:
            nc.accepting = True

        cprint(C.CYAN, f'  [{node_id}] dinleniyor — 3-5 kez vur, bitince Enter.')
        try:
            input(f'  {C.YELLOW}[ENTER]{C.RESET} {node_id} bitti...')
        except KeyboardInterrupt:
            pass

        with nc.lock:
            nc.accepting = False

        cprint(C.GREEN,
               f'  [{node_id}] tamamlandı — '
               f'{len(nc.taps)} vuruş kabul, '
               f'{len(nc.weak)} zayıf, '
               f'{nc.rejected} elendi.')

    collector.stop()

    print_summary(
        calib        = collector.calib,
        nodes        = nodes,
        fs           = fs,
        sta_s        = sta_s,
        lta_s        = lta_s,
        env_window_s = env_window_s,
        sigma_k      = args.sigma_k,
        out_path     = args.out,
    )


if __name__ == "__main__":
    main()