// ============================================================
//  GroundEye — Kalibrasyon Aracı (düz C++)
//
//  Amaç: Canlı MQTT akışını dinler. Sen sırayla node-1, node-2,
//  node-3'e VURURSUN. Her vuruşta DSP pipeline'ın ürettiği TÜM
//  değerleri toplar (peak amplitude, RMS enerji, STA/LTA tepe
//  oranı, onset, süre, gürültü tabanı, SNR, time-sync) ve
//  sonunda "config.json'da şu detection değerleri olmalı" diye
//  hazır bir blok basar.
//
//  Gerçek DSP sınıflarını (IIRFilter, EnvelopeEstimator,
//  STALTADetector) DSP.hpp'den kullanır — yani önerilen eşikler
//  gerçek dedektörle birebir uyumludur.
//
//  Derleme:
//    make calibrate
//      veya
//    g++ -O2 -std=c++17 calibrate.cpp -lmosquitto -lpthread -o groundeye_calibrate
//
//  Kullanım:
//    ./groundeye_calibrate --config config.json --nodes node-1,node-2,node-3
//    -> Her node'a EN ZAYIF algılamak istediğin şiddette birkaç kez vur.
//    -> Bitince Ctrl+C — öneri ekrana basılır.
// ============================================================

#include "dsp.hpp"

#include <mosquitto.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using json = nlohmann::json;

// ── Config ────────────────────────────────────────────────────
struct Config {
    std::string broker = "localhost";
    int         port   = 1883;
    std::vector<std::string> nodes = {"node-1"};
    groundeye::DetectorParams det;   // sadece fs / pencere boyutları için
};

// ── Tek bir vuruşun ölçümleri ─────────────────────────────────
struct Tap {
    double   peak_amp   = 0.0;   // tepe envelope genliği
    double   peak_ratio = 0.0;   // tepe STA/LTA oranı
    double   rms        = 0.0;   // olay boyunca filtrelenmiş RMS
    double   duration_ms = 0.0;
    double   snr        = 0.0;   // peak_amp / gürültü tabanı
    bool     time_synced = false;
};

// ── Node başına kalibrasyon durumu ────────────────────────────
//  Eşik, gürültüden ÖLÇÜLÜR (keyfi sayı yok):
//   1) BASELINE fazı: ilk `baseline_s` saniye VURMA. Bu sürede
//      gürültünün envelope ortalaması (μ) ve std sapması (σ) ile
//      gürültünün ürettiği en yüksek sahte-tetik genliği ölçülür.
//   2) Kabul eşiği = max(μ + K·σ,  baseline_noise_peak · margin)
//      Yani "gürültünün istatistiksel olarak ulaşamayacağı seviye".
//      Bu seviyenin üstündeki her tetik = GERÇEK vuruş.
struct NodeCalib {
    explicit NodeCalib(const groundeye::DetectorParams& p,
                       double baseline_s, double sigma_k, double seg_on)
    : envelope(static_cast<int>(p.env_window_s * p.fs))
    // Segmentasyon eşiği (zayıf vuruşları yakalamak için düşük tut)
    , stalta(static_cast<int>(p.sta_s * p.fs),
             static_cast<int>(p.lta_s * p.fs),
             seg_on, std::max(1.05, seg_on * 0.75))
    , fs(p.fs)
    , lta_len(static_cast<int>(p.lta_s * p.fs))
    , baseline_samples(static_cast<uint64_t>(baseline_s * p.fs))
    , sigma_k(sigma_k) {}

    groundeye::IIRFilter         filter;
    groundeye::EnvelopeEstimator envelope;
    groundeye::STALTADetector    stalta;
    int                          fs;
    int                          lta_len;
    uint64_t                     baseline_samples;  // bu süre boyunca öğren
    double                       sigma_k;           // eşik = μ + K·σ
    uint64_t                     rejected = 0;       // baseline + eşik altı

    uint64_t sample_idx  = 0;
    bool     time_synced = false;

    // Gürültü istatistiği (olay DIŞI envelope) — μ, σ için
    double   noise_sum   = 0.0;
    double   noise_sqsum = 0.0;
    uint64_t noise_n     = 0;
    // Baseline sırasında gürültünün ürettiği en yüksek sahte-tetik genliği
    double   baseline_peak = 0.0;

    // olay durumu
    bool     in_event   = false;
    uint64_t onset_idx  = 0;
    double   peak_amp   = 0.0;
    double   peak_ratio = 0.0;
    double   rms_acc    = 0.0;
    uint64_t rms_n      = 0;

    std::vector<Tap> taps;
    std::vector<Tap> weak;               // segment oldu ama eşik ALTI (teşhis)
    bool             announced = false;  // "baseline bitti, vur" duyuruldu mu

    double noiseMean() const { return noise_n ? noise_sum / noise_n : 0.0; }
    double noiseStd()  const {
        if (noise_n < 2) return 0.0;
        double m = noiseMean();
        double v = noise_sqsum / noise_n - m * m;
        return v > 0.0 ? std::sqrt(v) : 0.0;
    }
    // Gürültüden ölçülmüş kabul eşiği (genlik)
    double gate() const {
        double stat = noiseMean() + sigma_k * noiseStd();   // istatistiksel
        double seen = baseline_peak * 1.3;                   // gözlenen tepe + pay
        return std::max(stat, seen);
    }
    bool inBaseline() const { return sample_idx < baseline_samples; }

    // Her sample için çağrılır. Yeni GERÇEK vuruş tamamlanırsa true döner.
    bool process(int16_t raw) {
        double f   = filter.process(static_cast<double>(raw));
        double env = envelope.process(f);
        bool   trig = stalta.process(env);
        double ratio = stalta.ratio();
        uint64_t idx = sample_idx++;

        if (!in_event && trig) {
            in_event   = true;
            onset_idx  = idx;
            peak_amp   = env;
            peak_ratio = ratio;
            rms_acc    = f * f;
            rms_n      = 1;
        } else if (in_event && trig) {
            rms_acc += f * f;
            rms_n++;
            if (env   > peak_amp)   peak_amp   = env;
            if (ratio > peak_ratio) peak_ratio = ratio;
        } else if (in_event && !trig) {
            in_event = false;
            double dur_ms = (idx - onset_idx) * 1000.0 / fs;
            if (dur_ms < 40.0) return false;      // çok kısa — gürültü spike

            // Isınma: LTA dolmadan oran güvenilmez
            if (onset_idx < static_cast<uint64_t>(lta_len)) return false;

            // ── BASELINE fazı: bu bir vuruş DEĞİL, gürültü örneği ──
            // Genliğini "gürültü tepesi" olarak kaydet, kabul etme.
            if (onset_idx < baseline_samples) {
                if (peak_amp > baseline_peak) baseline_peak = peak_amp;
                rejected++;
                return false;
            }

            double m = noiseMean();
            Tap t;
            t.peak_amp    = peak_amp;
            t.peak_ratio  = peak_ratio;
            t.rms         = std::sqrt(rms_acc / std::max<uint64_t>(rms_n, 1));
            t.duration_ms = dur_ms;
            t.snr         = m > 1e-9 ? peak_amp / m : 0.0;
            t.time_synced = time_synced;

            // ── CANLI faz: gürültüden ölçülmüş eşiğin üstü mü? ──
            if (peak_amp < gate()) {      // eşik altı — teşhis için sakla, kabul etme
                weak.push_back(t);
                rejected++;
                return false;
            }
            taps.push_back(t);
            return true;
        } else {
            // Gürültü istatistiğini SADECE baseline'da ve filtre oturduktan
            // sonra öğren. Tapping sırasında öğrenirsek vuruş kuyrukları σ'yı
            // şişirir → eşik patlar (gözlenen sorun buydu). Baseline bitince dondur.
            if (sample_idx >= static_cast<uint64_t>(fs) &&  // ilk 1sn: filtre transiyeni
                sample_idx <  baseline_samples) {           // sadece baseline
                noise_sum   += env;
                noise_sqsum += env * env;
                noise_n++;
            }
        }
        return false;
    }
};

// ── Globals ───────────────────────────────────────────────────
static std::atomic<bool> g_running{true};
static Config            g_cfg;
static double            g_baseline_s = 5.0;  // --baseline: gürültü öğrenme süresi
static double            g_sigma_k    = 5.0;  // --sigma-k: eşik = μ + K·σ
static double            g_seg_on     = 1.6;  // --seg-on: STA/LTA segmentasyon eşiği
static std::map<std::string, NodeCalib> g_calib;
static std::mutex        g_mutex;
static mosquitto*        g_mosq = nullptr;

void onSignal(int) { g_running = false; }

// ── config.json yükle (broker/port/nodes + fs/pencereler) ─────
void loadConfig(Config& cfg, const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) {
        std::cerr << "[CONFIG] Açılamadı, default: " << path << "\n";
        return;
    }
    try {
        json j = json::parse(f);
        cfg.broker = j.value("broker", cfg.broker);
        cfg.port   = j.value("port",   cfg.port);
        if (j.contains("nodes") && j["nodes"].is_array() && !j["nodes"].empty()) {
            cfg.nodes.clear();
            for (const auto& n : j["nodes"]) {
                if (n.is_string())         cfg.nodes.push_back(n.get<std::string>());
                else if (n.contains("id")) cfg.nodes.push_back(n["id"].get<std::string>());
            }
        }
        if (j.contains("detection") && j["detection"].is_object()) {
            const auto& d = j["detection"];
            cfg.det.fs           = d.value("fs",           cfg.det.fs);
            cfg.det.sta_s        = d.value("sta_s",        cfg.det.sta_s);
            cfg.det.lta_s        = d.value("lta_s",        cfg.det.lta_s);
            cfg.det.env_window_s = d.value("env_window_s", cfg.det.env_window_s);
        }
        std::cout << "[CONFIG] Yüklendi: " << path << "\n";
    } catch (const std::exception& ex) {
        std::cerr << "[CONFIG] Parse hatası: " << ex.what() << "\n";
    }
}

// ── MQTT callbacks ────────────────────────────────────────────
void onConnect(mosquitto*, void*, int rc) {
    if (rc != 0) { std::cerr << "[MQTT] Bağlantı başarısız: " << rc << "\n"; return; }
    std::cout << "[MQTT] Bağlandı: " << g_cfg.broker << "\n";
    for (const auto& id : g_cfg.nodes) {
        std::string stream = "groundeye/stream/"      + id;
        std::string meta   = "groundeye/stream_meta/" + id;
        mosquitto_subscribe(g_mosq, nullptr, stream.c_str(), 0);
        mosquitto_subscribe(g_mosq, nullptr, meta.c_str(),   0);
    }
    std::cout << "\n>>> BASELINE: ilk " << g_baseline_s << " saniye HİÇ VURMA — "
                 "gürültü ölçülüyor (μ, σ).\n"
                 ">>> Her node hazır olunca ekrana 'BASELINE BİTTİ — ŞİMDİ VUR!' "
                 "yazacak.\n"
                 ">>> O yazıyı görünce sırayla node'lara EN ZAYIF şiddette 3-5 kez vur.\n"
                 ">>> Bitince Ctrl+C — öneri basılacak.\n\n";
}

void onMessage(mosquitto*, void*, const mosquitto_message* msg) {
    if (!msg || !msg->topic) return;
    std::string topic(msg->topic);

    // time_synced bilgisini meta'dan al
    if (topic.rfind("groundeye/stream_meta/", 0) == 0) {
        std::string id = topic.substr(strlen("groundeye/stream_meta/"));
        try {
            json j = json::parse(std::string(
                static_cast<char*>(msg->payload), msg->payloadlen));
            bool sync = j.value("time_synced", false);
            std::lock_guard<std::mutex> lock(g_mutex);
            auto it = g_calib.find(id);
            if (it != g_calib.end()) it->second.time_synced = sync;
        } catch (...) {}
        return;
    }

    if (topic.rfind("groundeye/stream/", 0) == 0 &&
        topic.find("_meta") == std::string::npos) {
        std::string id = topic.substr(strlen("groundeye/stream/"));

        std::lock_guard<std::mutex> lock(g_mutex);
        auto it = g_calib.find(id);
        if (it == g_calib.end()) return;

        const int16_t* s = reinterpret_cast<const int16_t*>(msg->payload);
        int count = msg->payloadlen / sizeof(int16_t);

        size_t before      = it->second.taps.size();
        size_t before_weak = it->second.weak.size();
        for (int i = 0; i < count; ++i)
            it->second.process(s[i]);

        // ── Baseline → Canlı geçişi: artık vurabilirsin ──
        if (!it->second.announced && !it->second.inBaseline()) {
            it->second.announced = true;
            std::cout << std::fixed << std::setprecision(2)
                      << ">>> [" << id << "] BASELINE BİTTİ — ŞİMDİ VUR!  "
                      << "(μ=" << it->second.noiseMean()
                      << " σ=" << it->second.noiseStd()
                      << " eşik=" << it->second.gate() << ")\n";
        }

        // Yeni vuruş(lar) varsa canlı bas
        for (size_t k = before; k < it->second.taps.size(); ++k) {
            const Tap& t = it->second.taps[k];
            std::cout << std::fixed << std::setprecision(2)
                      << "[VURUŞ] " << id
                      << "  #" << (k + 1)
                      << "  peak_amp=" << t.peak_amp
                      << "  ratio="    << t.peak_ratio
                      << "  rms="      << t.rms
                      << "  snr="      << t.snr
                      << "  dur="      << t.duration_ms << "ms"
                      << "  sync="     << (t.time_synced ? "OK" : "YOK")
                      << "\n";
        }

        // Eşik ALTI kalan (elenmiş) olayları da göster — TEŞHİS
        for (size_t k = before_weak; k < it->second.weak.size(); ++k) {
            const Tap& t = it->second.weak[k];
            std::cout << std::fixed << std::setprecision(2)
                      << "[zayıf] " << id
                      << "  peak_amp=" << t.peak_amp
                      << "  ratio="    << t.peak_ratio
                      << "  (eşik="    << it->second.gate() << ")"
                      << "  -> eşiğin ALTINDA, elendi\n";
        }
    }
}

// ── Özet & öneri ──────────────────────────────────────────────
void printSummary() {
    std::cout << "\n";
    std::cout << "============================================================\n";
    std::cout << " KALİBRASYON ÖZETİ\n";
    std::cout << "============================================================\n";

    double global_min_ratio = 1e18;   // tüm node'lardaki en zayıf gerçek vuruş oranı
    double global_min_amp   = 1e18;   // en zayıf gerçek vuruş genliği
    double global_max_gate  = 0.0;    // en yüksek (en gürültülü) node eşiği
    int    total_taps       = 0;
    bool   all_synced       = true;

    std::lock_guard<std::mutex> lock(g_mutex);
    for (const auto& id : g_cfg.nodes) {
        auto it = g_calib.find(id);
        if (it == g_calib.end()) continue;
        const auto& nc = it->second;

        std::cout << std::fixed << std::setprecision(2)
                  << "\n[" << id << "]  vuruş=" << nc.taps.size()
                  << "  elenen=" << nc.rejected << "\n"
                  << "   gürültü μ=" << nc.noiseMean()
                  << "  σ="          << nc.noiseStd()
                  << "  baseline_tepe=" << nc.baseline_peak
                  << "  -> ÖLÇÜLEN_EŞİK=" << nc.gate() << "\n";

        global_max_gate = std::max(global_max_gate, nc.gate());

        if (nc.taps.empty()) {
            std::cout << "   (vuruş yok — bu node'a vurmadın mı?)\n";
            all_synced = false;
            continue;
        }

        double amin = 1e18, amax = 0, asum = 0;
        double rmin = 1e18, rmax = 0, rsum = 0;
        double smin = 1e18, ssum = 0;
        for (const auto& t : nc.taps) {
            amin = std::min(amin, t.peak_amp);  amax = std::max(amax, t.peak_amp); asum += t.peak_amp;
            rmin = std::min(rmin, t.peak_ratio); rmax = std::max(rmax, t.peak_ratio); rsum += t.peak_ratio;
            smin = std::min(smin, t.snr);        ssum += t.snr;
            if (!t.time_synced) all_synced = false;
        }
        int n = static_cast<int>(nc.taps.size());
        std::cout << "   peak_amp : min=" << amin << " ort=" << asum / n << " max=" << amax << "\n";
        std::cout << "   ratio    : min=" << rmin << " ort=" << rsum / n << " max=" << rmax << "\n";
        std::cout << "   snr      : min=" << smin << " ort=" << ssum / n << "\n";

        global_min_ratio = std::min(global_min_ratio, rmin);
        global_min_amp   = std::min(global_min_amp,   amin);
        total_taps      += n;
    }

    if (total_taps == 0) {
        std::cout << "\nHiç vuruş alınmadı — broker/node ayarlarını kontrol et.\n";
        return;
    }

    // ── Öneri mantığı ────────────────────────────────────────
    // trigger_on: en zayıf gerçek vuruşun tepe oranının biraz ALTI
    //   -> böylece o şiddetteki olaylar yakalanır, gürültü elenir.
    double trigger_on  = std::max(1.8, global_min_ratio * 0.6);
    double trigger_off = std::max(1.2, trigger_on * 0.65);
    // min_peak_amp: GÜRÜLTÜDEN ÖLÇÜLEN eşiklerin en yükseği (en gürültülü node).
    //   Keyfi sayı değil — μ+K·σ ve gözlenen gürültü tepesinden hesaplandı.
    //   En zayıf gerçek vuruşun da altında kalmalı, yoksa onu kaçırırız.
    double min_peak_amp = global_max_gate;
    if (min_peak_amp > global_min_amp * 0.9)   // en zayıf vuruşa çok yaklaştıysa
        min_peak_amp = global_min_amp * 0.5;   // güvenli paya çek

    std::cout << "\n============================================================\n";
    std::cout << " ÖNERİLEN config.json -> \"detection\" bloğu\n";
    std::cout << "============================================================\n";
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "  \"detection\": {\n";
    std::cout << "    \"fs\": "              << g_cfg.det.fs           << ",\n";
    std::cout << "    \"sta_s\": "           << g_cfg.det.sta_s        << ",\n";
    std::cout << "    \"lta_s\": "           << g_cfg.det.lta_s        << ",\n";
    std::cout << "    \"trigger_on\": "      << trigger_on             << ",\n";
    std::cout << "    \"trigger_off\": "     << trigger_off            << ",\n";
    std::cout << "    \"env_window_s\": "    << g_cfg.det.env_window_s << ",\n";
    std::cout << "    \"min_duration_ms\": " << 80                     << ",\n";
    std::cout << "    \"min_peak_amp\": "    << min_peak_amp           << "\n";
    std::cout << "  }\n";
    std::cout << "============================================================\n";

    if (!all_synced)
        std::cout << "\n[UYARI] Bazı vuruşlarda time_synced=YOK. TDOA konumlandırma\n"
                     "        için NTP senkronizasyonunu düzeltmen gerekir.\n";

    // Gürültü ile en zayıf sinyal çakışıyorsa: fiziksel SNR sorunu
    if (global_max_gate >= global_min_amp)
        std::cout << "\n[UYARI] En gürültülü node'un eşiği (" << global_max_gate
                  << ") en zayıf vuruştan (" << global_min_amp << ") YÜKSEK.\n"
                     "        Yani o vuruş gürültüden ayırt edilemiyor — daha sert\n"
                     "        vurman ya da o node'un gürültüsünü (kablo/zemin/RF)\n"
                     "        azaltman gerekir. Yazılımla çözülmez.\n";

    std::cout << "\nNot: min_peak_amp'i ben UYDURMADIM — her node'un gürültüsünü\n"
                 "ölçüp (μ + " << g_sigma_k << "·σ) ve gözlenen gürültü tepesinden\n"
                 "hesapladık. trigger_on ise en zayıf gerçek vuruşa göre ayarlandı.\n";
}

// ── main ──────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    std::string config_path;
    for (int i = 1; i < argc; ++i) {
        std::string a(argv[i]);
        if (a == "--config" && i + 1 < argc) config_path = argv[++i];
        else if (a == "--broker" && i + 1 < argc) g_cfg.broker = argv[++i];
        else if (a == "--port"     && i + 1 < argc) g_cfg.port = std::stoi(argv[++i]);
        else if (a == "--baseline" && i + 1 < argc) g_baseline_s = std::stod(argv[++i]);
        else if (a == "--sigma-k"  && i + 1 < argc) g_sigma_k = std::stod(argv[++i]);
        else if (a == "--seg-on"   && i + 1 < argc) g_seg_on  = std::stod(argv[++i]);
        else if (a == "--nodes"  && i + 1 < argc) {
            g_cfg.nodes.clear();
            std::stringstream ss(argv[++i]); std::string tok;
            while (std::getline(ss, tok, ',')) g_cfg.nodes.push_back(tok);
        } else if (a == "--help" || a == "-h") {
            std::cout << "Kullanım: groundeye_calibrate [--config c.json]"
                         " [--broker ip] [--port p] [--nodes n1,n2,n3]"
                         " [--baseline 5.0] [--sigma-k 5.0] [--seg-on 1.6]\n"
                         "  --baseline: gürültüyü öğrenme süresi (sn) — bu sürede VURMA\n"
                         "  --sigma-k : genlik eşiği = μ + K·σ (DÜŞÜR = daha hassas)\n"
                         "  --seg-on  : STA/LTA segmentasyon eşiği (DÜŞÜR = daha hassas)\n";
            return 0;
        }
    }
    if (!config_path.empty()) loadConfig(g_cfg, config_path);
    // --nodes / --broker CLI override (config sonrası tekrar uygula)
    for (int i = 1; i < argc; ++i) {
        std::string a(argv[i]);
        if (a == "--broker" && i + 1 < argc) g_cfg.broker = argv[++i];
        else if (a == "--nodes" && i + 1 < argc) {
            g_cfg.nodes.clear();
            std::stringstream ss(argv[++i]); std::string tok;
            while (std::getline(ss, tok, ',')) g_cfg.nodes.push_back(tok);
        }
    }

    std::signal(SIGINT,  onSignal);
    std::signal(SIGTERM, onSignal);

    std::cout << "GroundEye Kalibrasyon Aracı\n";
    std::cout << "Broker  : " << g_cfg.broker << ":" << g_cfg.port << "\n";
    std::cout << "Baseline: " << g_baseline_s << "s  eşik = μ + "
              << g_sigma_k << "·σ  seg_on=" << g_seg_on << "\n";
    std::cout << "Nodes   : ";
    for (const auto& n : g_cfg.nodes) {
        std::cout << n << " ";
        g_calib.emplace(n, NodeCalib(g_cfg.det, g_baseline_s, g_sigma_k, g_seg_on));
    }
    std::cout << "\n";

    mosquitto_lib_init();
    g_mosq = mosquitto_new("groundeye-calibrate", true, nullptr);
    if (!g_mosq) { std::cerr << "mosquitto_new başarısız\n"; return 1; }
    mosquitto_connect_callback_set(g_mosq, onConnect);
    mosquitto_message_callback_set(g_mosq, onMessage);
    mosquitto_reconnect_delay_set(g_mosq, 1, 5, false);

    int rc = mosquitto_connect(g_mosq, g_cfg.broker.c_str(), g_cfg.port, 60);
    if (rc != MOSQ_ERR_SUCCESS) {
        std::cerr << "Bağlantı hatası: " << mosquitto_strerror(rc) << "\n";
        mosquitto_destroy(g_mosq); mosquitto_lib_cleanup(); return 1;
    }
    mosquitto_loop_start(g_mosq);

    while (g_running)
        std::this_thread::sleep_for(std::chrono::milliseconds(100));

    mosquitto_loop_stop(g_mosq, true);
    mosquitto_disconnect(g_mosq);
    mosquitto_destroy(g_mosq);
    mosquitto_lib_cleanup();

    printSummary();
    return 0;
}
