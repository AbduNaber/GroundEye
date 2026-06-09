// ============================================================
//  GroundEye — C++ DSP Servisi
//  MQTT'den binary stream alır → DSP pipeline → event JSON publish
//
//  Düzeltme: batch_epoch_ms artık ESP32'nin NTP-synced timestamp'inden
//  alınıyor — Pi'nin alış zamanından değil.
//
//  Derleme:
//    sudo dnf install mosquitto-devel nlohmann-json-devel   # Fedora
//    sudo apt install libmosquitto-dev nlohmann-json3-dev   # Pi/Debian
//    g++ -O2 -std=c++17 main.cpp -lmosquitto -o groundeye_dsp
//
//  Kullanım:
//    ./groundeye_dsp --broker localhost --nodes node-1,node-2,node-3
// ============================================================

#include "dsp.hpp"

#include <mosquitto.h>
#include <nlohmann/json.hpp>

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using json = nlohmann::json;

// ── Config ────────────────────────────────────────────────────
struct Config {
    std::string broker      = "localhost";
    int         port        = 1883;
    std::string event_topic = "groundeye/event";
    std::vector<std::string> nodes = {"node-1"};
    bool        verbose     = false;
    std::string config_path = "";   // boş = config dosyası yükleme

    // Tüm node'lara uygulanan detection parametreleri.
    // config.json "detection" bloğundan yüklenir — recompile gerekmez.
    groundeye::DetectorParams detector;
};

// ── config.json'dan detection parametrelerini yükle ──────────
// Beklenen yapı (hepsi opsiyonel, eksikler default kalır):
//   { "broker": "...", "port": 1883, "nodes": ["node-1", ...],
//     "event_topic": "...",
//     "detection": {
//       "fs": 2000, "sta_s": 0.1, "lta_s": 1.0,
//       "trigger_on": 2.0, "trigger_off": 1.3,
//       "env_window_s": 0.05, "min_duration_ms": 80,
//       "min_peak_amp": 0.0 } }
void loadConfigFile(Config& cfg, const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) {
        std::cerr << "[CONFIG] Açılamadı, defaultlar kullanılıyor: "
                  << path << "\n";
        return;
    }
    try {
        json j = json::parse(f);

        cfg.broker      = j.value("broker",      cfg.broker);
        cfg.port        = j.value("port",        cfg.port);
        cfg.event_topic = j.value("event_topic", cfg.event_topic);

        if (j.contains("nodes") && j["nodes"].is_array() &&
            !j["nodes"].empty()) {
            cfg.nodes.clear();
            for (const auto& n : j["nodes"]) {
                // node hem string ("node-1") hem obje ({"id": "node-1"}) olabilir
                if (n.is_string())            cfg.nodes.push_back(n.get<std::string>());
                else if (n.contains("id"))    cfg.nodes.push_back(n["id"].get<std::string>());
            }
        }

        if (j.contains("detection") && j["detection"].is_object()) {
            const auto& d = j["detection"];
            auto& p = cfg.detector;
            p.fs              = d.value("fs",              p.fs);
            p.sta_s           = d.value("sta_s",           p.sta_s);
            p.lta_s           = d.value("lta_s",           p.lta_s);
            p.trigger_on      = d.value("trigger_on",      p.trigger_on);
            p.trigger_off     = d.value("trigger_off",     p.trigger_off);
            p.env_window_s    = d.value("env_window_s",    p.env_window_s);
            p.min_duration_ms = d.value("min_duration_ms", p.min_duration_ms);
            p.min_peak_amp    = d.value("min_peak_amp",    p.min_peak_amp);
        }
        std::cout << "[CONFIG] Yüklendi: " << path << "\n";
    }
    catch (const std::exception& ex) {
        std::cerr << "[CONFIG] Parse hatası (" << path << "): "
                  << ex.what() << " — defaultlar kullanılıyor\n";
    }
}

// ── Node meta — stream_meta'dan gelen son bilgi ───────────────
// Her node için ayrı tutulur.
// stream_meta mesajı stream mesajından önce veya sonra gelebilir,
// bu yüzden mutex ile koruyoruz.
struct NodeMeta {
    uint64_t epoch_ms    = 0;      // ESP32 NTP-synced batch start zamanı
    bool     time_synced = false;  // NTP sync başarılı mıydı
    uint32_t seq         = 0;      // batch sıra numarası
    uint32_t dropped     = 0;      // node'da düşen batch sayısı
};

// ── Globals ───────────────────────────────────────────────────
static std::atomic<bool> g_running{true};
static Config             g_cfg;

static std::map<std::string, std::unique_ptr<groundeye::NodeDSP>> g_nodes;
static std::map<std::string, NodeMeta>  g_meta;   // node_id → son meta
static std::mutex                       g_meta_mutex;

static mosquitto* g_mosq = nullptr;

// ── Signal handler ────────────────────────────────────────────
void onSignal(int) { g_running = false; }

// ── Fallback epoch (Pi saati) — NTP sync yoksa kullanılır ─────
uint64_t piEpochMs() {
    using namespace std::chrono;
    return static_cast<uint64_t>(
        duration_cast<milliseconds>(
            system_clock::now().time_since_epoch()).count());
}

// ── MQTT publish ──────────────────────────────────────────────
void mqttPublish(const std::string& topic, const std::string& payload) {
    if (!g_mosq) return;
    mosquitto_publish(g_mosq, nullptr,
                      topic.c_str(),
                      static_cast<int>(payload.size()),
                      payload.c_str(),
                      0, false);
}

// ── Event callback ────────────────────────────────────────────
void onEvent(const groundeye::Event& e) {
    json j;
    j["node_id"]        = e.node_id;
    j["onset_ms"]       = e.onset_ms;
    j["peak_ms"]        = e.peak_ms;
    j["duration_ms"]    = std::round(e.duration_ms);
    j["rms_energy"]     = std::round(e.rms_energy    * 100.0) / 100.0;
    j["peak_amplitude"] = std::round(e.peak_amplitude * 100.0) / 100.0;
    j["time_synced"]    = e.time_synced;
    j["source"]         = "groundeye_dsp";

    std::string payload = j.dump();
    mqttPublish(g_cfg.event_topic, payload);
    std::cout << "[EVENT] " << payload << "\n";
}

// ── MQTT callbacks ────────────────────────────────────────────
void onConnect(mosquitto*, void*, int rc) {
    if (rc != 0) {
        std::cerr << "[MQTT] Bağlantı başarısız: " << rc << "\n";
        return;
    }
    std::cout << "[MQTT] Bağlandı: " << g_cfg.broker << "\n";

    for (const auto& node_id : g_cfg.nodes) {
        std::string stream = "groundeye/stream/"      + node_id;
        std::string meta   = "groundeye/stream_meta/" + node_id;
        mosquitto_subscribe(g_mosq, nullptr, stream.c_str(), 0);
        mosquitto_subscribe(g_mosq, nullptr, meta.c_str(),   0);
        std::cout << "[MQTT] Subscribe: " << stream << "\n";
        std::cout << "[MQTT] Subscribe: " << meta   << "\n";
    }
}

void onDisconnect(mosquitto*, void*, int rc) {
    if (rc != 0)
        std::cerr << "[MQTT] Kesildi rc=" << rc << " — yeniden bağlanılıyor\n";
}

void onMessage(mosquitto*, void*, const mosquitto_message* msg) {
    if (!msg || !msg->topic) return;

    std::string topic(msg->topic);

    // ── stream_meta — önce işle, epoch_ms'i sakla ─────────────
    if (topic.rfind("groundeye/stream_meta/", 0) == 0) {
        std::string node_id = topic.substr(strlen("groundeye/stream_meta/"));
        std::string payload(static_cast<char*>(msg->payload), msg->payloadlen);

        try {
            json j = json::parse(payload);

            NodeMeta m;

            // epoch_ms firmware'de iki parçaya bölünmüştü:
            //   epoch_ms      → alt 32 bit
            //   epoch_ms_high → üst 32 bit
            uint64_t lo = j.value("epoch_ms",      uint64_t(0));
            uint64_t hi = j.value("epoch_ms_high", uint64_t(0));
            m.epoch_ms    = (hi << 32) | lo;
            m.time_synced = j.value("time_synced", false);
            m.seq         = j.value("seq",         uint32_t(0));
            m.dropped     = j.value("dropped_batches", uint32_t(0));

            {
                std::lock_guard<std::mutex> lock(g_meta_mutex);
                g_meta[node_id] = m;
            }

            if (g_cfg.verbose) {
                std::cout << "[META] " << node_id
                << " seq="     << m.seq
                << " epoch="   << m.epoch_ms
                << " synced="  << m.time_synced
                << " dropped=" << m.dropped << "\n";
            }
        }
        catch (const std::exception& ex) {
            std::cerr << "[META] Parse hatası: " << ex.what() << "\n";
        }
        return;
    }

    // ── stream — binary batch işle ────────────────────────────
    if (topic.rfind("groundeye/stream/", 0) == 0 &&
        topic.find("_meta") == std::string::npos) {

        std::string node_id = topic.substr(strlen("groundeye/stream/"));

    auto dsp_it = g_nodes.find(node_id);
    if (dsp_it == g_nodes.end()) return;

    const int16_t* samples =
    reinterpret_cast<const int16_t*>(msg->payload);
    int count = msg->payloadlen / sizeof(int16_t);
    if (count <= 0) return;

    // ── Timestamp kaynağını seç ───────────────────────────
    // Öncelik: ESP32 NTP-synced epoch_ms (stream_meta'dan)
    // Fallback: Pi'nin kendi saati (NTP sync yoksa)
    uint64_t batch_epoch_ms;
        bool     time_synced = false;

        {
            std::lock_guard<std::mutex> lock(g_meta_mutex);
            auto meta_it = g_meta.find(node_id);

            if (meta_it != g_meta.end() &&
                meta_it->second.time_synced &&
                meta_it->second.epoch_ms > 0) {
                // ✅ ESP32 NTP-synced timestamp — güvenilir
                batch_epoch_ms = meta_it->second.epoch_ms;
            time_synced    = true;
                } else {
                    // ⚠️ Fallback — Pi alış zamanı, TDOA için güvenilmez
                    batch_epoch_ms = piEpochMs()
                    - static_cast<uint64_t>(count * 1000.0 / 2000.0);
                    time_synced = false;

                    if (g_cfg.verbose)
                        std::cout << "[WARN] " << node_id
                        << " NTP sync yok — Pi saati kullanılıyor\n";
                }
        }

        // NodeDSP'ye time_synced flag'ini taşı
        dsp_it->second->setTimeSynced(time_synced);
        dsp_it->second->pushBatch(samples, count, batch_epoch_ms);

        if (g_cfg.verbose)
            std::cout << "[STREAM] " << node_id
            << " count=" << count
            << " synced=" << time_synced << "\n";
        }
}

// ── Argüman parser — config dosyasının ÜZERİNE yazar ─────────
// (önce config.json yüklenir, sonra CLI argümanları override eder)
void applyArgs(Config& cfg, int argc, char* argv[]) {
    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--broker" && i + 1 < argc) {
            cfg.broker = argv[++i];
        } else if (arg == "--port" && i + 1 < argc) {
            cfg.port = std::stoi(argv[++i]);
        } else if (arg == "--nodes" && i + 1 < argc) {
            cfg.nodes.clear();
            std::stringstream ss(argv[++i]);
            std::string token;
            while (std::getline(ss, token, ','))
                cfg.nodes.push_back(token);
        } else if (arg == "--config" && i + 1 < argc) {
            ++i;  // ana akışta zaten işlendi — burada atla
        } else if (arg == "--verbose" || arg == "-v") {
            cfg.verbose = true;
        } else if (arg == "--help" || arg == "-h") {
            std::cout
            << "Kullanım: groundeye_dsp [seçenekler]\n"
            << "  --config <yol>       config.json yolu (detection params)\n"
            << "  --broker <ip>        MQTT broker IP\n"
            << "  --port <port>        MQTT port (varsayılan: 1883)\n"
            << "  --nodes <n1,n2,n3>   Node ID listesi\n"
            << "  --verbose            Detaylı çıktı\n";
            std::exit(0);
        }
    }
}

// ── Main ──────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    // 1) --config yolunu bul (varsa)
    std::string config_path;
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--config" && i + 1 < argc)
            config_path = argv[i + 1];

    // 2) config dosyasını yükle (detection params + broker/nodes)
    if (!config_path.empty())
        loadConfigFile(g_cfg, config_path);

    // 3) CLI argümanları config'i override eder
    applyArgs(g_cfg, argc, argv);

    std::signal(SIGINT,  onSignal);
    std::signal(SIGTERM, onSignal);

    std::cout << "GroundEye DSP Servisi\n";
    std::cout << "Broker : " << g_cfg.broker << ":" << g_cfg.port << "\n";
    std::cout << "Nodes  : ";
    for (const auto& n : g_cfg.nodes) std::cout << n << " ";
    std::cout << "\n";
    const auto& d = g_cfg.detector;
    std::cout << "Detect : fs=" << d.fs
              << " sta=" << d.sta_s << "s lta=" << d.lta_s << "s"
              << " on=" << d.trigger_on << " off=" << d.trigger_off
              << " env=" << d.env_window_s << "s"
              << " min_dur=" << d.min_duration_ms << "ms"
              << " min_amp=" << d.min_peak_amp << "\n";

    for (const auto& node_id : g_cfg.nodes) {
        auto dsp = std::make_unique<groundeye::NodeDSP>(node_id, g_cfg.detector);
        dsp->setCallback(onEvent);
        g_nodes[node_id] = std::move(dsp);
        g_meta[node_id]  = NodeMeta{};
        std::cout << "[DSP] Node hazır: " << node_id << "\n";
    }

    mosquitto_lib_init();
    g_mosq = mosquitto_new("groundeye-dsp", true, nullptr);
    if (!g_mosq) {
        std::cerr << "mosquitto_new başarısız\n";
        return 1;
    }

    mosquitto_connect_callback_set(g_mosq,    onConnect);
    mosquitto_disconnect_callback_set(g_mosq, onDisconnect);
    mosquitto_message_callback_set(g_mosq,    onMessage);
    mosquitto_reconnect_delay_set(g_mosq, 1, 5, false);

    int rc = mosquitto_connect(g_mosq, g_cfg.broker.c_str(), g_cfg.port, 60);
    if (rc != MOSQ_ERR_SUCCESS) {
        std::cerr << "Bağlantı hatası: " << mosquitto_strerror(rc) << "\n";
        mosquitto_destroy(g_mosq);
        mosquitto_lib_cleanup();
        return 1;
    }

    mosquitto_loop_start(g_mosq);
    std::cout << "[BOOT] DSP pipeline çalışıyor — Ctrl+C ile dur\n";

    while (g_running)
        std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::cout << "\n[STOP] Durduruluyor...\n";
    mosquitto_loop_stop(g_mosq, true);
    mosquitto_disconnect(g_mosq);
    mosquitto_destroy(g_mosq);
    mosquitto_lib_cleanup();
    return 0;
}
