














// ============================================================
//  GroundEye — C++ Orkestrasyon Servisi
//
//  groundeye/event dinler → 2s pencerede gruplar →
//  trilateration → SQLite → groundeye/location publish
//
//  Derleme:
//    sudo dnf install mosquitto-devel nlohmann-json-devel sqlite-devel gcc-c++
//    sudo apt install libmosquitto-dev nlohmann-json3-dev libsqlite3-dev g++
//    g++ -O2 -std=c++17 main.cpp -lmosquitto -lsqlite3 -lpthread -o groundeye_orch
//
//  Kullanım:
//    ./groundeye_orch --config config.json
// ============================================================

#include "orchestrator.hpp"
#include "logger.hpp"

#include <mosquitto.h>

#include <atomic>
#include <chrono>
#include <csignal>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using namespace groundeye;

// ── Globals ───────────────────────────────────────────────────
static std::atomic<bool>  g_running{true};
static Config             g_cfg;
static mosquitto*         g_mosq      = nullptr;
static EventLogger*       g_logger    = nullptr;
static Fusion*            g_fusion    = nullptr;

// Fusion penceresi — gelen eventlar burada birikir
struct PendingEvent {
    NodeEvent   event;
    uint64_t    received_ms;
};
static std::vector<PendingEvent> g_pending;
static std::mutex                g_pending_mutex;

// ── Signal handler ────────────────────────────────────────────
void onSignal(int) { g_running = false; }

// ── Epoch ms ──────────────────────────────────────────────────
uint64_t epochMs() {
    using namespace std::chrono;
    return static_cast<uint64_t>(
        duration_cast<milliseconds>(
            system_clock::now().time_since_epoch()).count());
}

// ── MQTT publish ──────────────────────────────────────────────
void mqttPublish(const std::string& topic, const std::string& payload,
                 bool retained = false) {
    if (!g_mosq) return;
    mosquitto_publish(g_mosq, nullptr,
                      topic.c_str(),
                      static_cast<int>(payload.size()),
                      payload.c_str(),
                      0, retained);
}

// ── Fusion: penceredeki eventları işle ───────────────────────
void processFusionWindow() {
    std::lock_guard<std::mutex> lock(g_pending_mutex);

    uint64_t now = epochMs();

    // Pencere dışına çıkan eventları bul
    // En erken event'ten itibaren fusion_window_ms geçtiyse işle
    if (g_pending.empty()) return;

    uint64_t oldest = g_pending.front().received_ms;
    if (now - oldest < static_cast<uint64_t>(g_cfg.fusion_window_ms))
        return;  // pencere henüz dolmadı

    // Penceredeki eventları topla
    // Aynı node'dan birden fazla event geldiyse en güçlüyü al
    std::map<std::string, NodeEvent> best_per_node;
    for (const auto& pe : g_pending) {
        auto it = best_per_node.find(pe.event.node_id);
        if (it == best_per_node.end() ||
            pe.event.rms_energy > it->second.rms_energy) {
            best_per_node[pe.event.node_id] = pe.event;
        }
    }
    g_pending.clear();

    // Yeterli node var mı?
    if ((int)best_per_node.size() < g_cfg.min_nodes) {
        // Tek node bile olsa logla — sadece konum tahmini yapma
        if (best_per_node.empty()) return;
    }

    // NodeEvent listesi oluştur
    std::vector<NodeEvent> events;
    for (const auto& kv : best_per_node)
        events.push_back(kv.second);

    // En erken onset timestamp
    uint64_t earliest_ms = events[0].onset_ms;
    for (const auto& e : events)
        if (e.onset_ms < earliest_ms) earliest_ms = e.onset_ms;

    // Füzyon — amplitude + TDOA
    FusedEvent fe = g_fusion->process(events, earliest_ms);

    // SQLite kaydet
    if (g_logger) g_logger->log(fe);

    // groundeye/location publish
    json loc;
    loc["timestamp_ms"] = fe.timestamp_ms;
    loc["node_count"]   = fe.node_count;
    loc["nearest_node"] = fe.nearest_node;
    loc["best_method"]  = fe.best_method;
    loc["tdoa_used"]    = fe.tdoa_used;

    // Best konum
    if (fe.best.valid) {
        loc["x"]          = std::round(fe.best.x * 100.0) / 100.0;
        loc["y"]          = std::round(fe.best.y * 100.0) / 100.0;
        loc["confidence"] = std::round(fe.best.confidence * 1000.0) / 1000.0;
    }

    // Her iki yöntemin sonucu ayrıca — GUI karşılaştırabilsin
    if (fe.amplitude.valid) {
        loc["amplitude"] = {
            {"x",          std::round(fe.amplitude.x * 100.0) / 100.0},
            {"y",          std::round(fe.amplitude.y * 100.0) / 100.0},
            {"confidence", std::round(fe.amplitude.confidence * 1000.0) / 1000.0}
        };
    }
    if (fe.tdoa.valid) {
        loc["tdoa"] = {
            {"x",          std::round(fe.tdoa.x * 100.0) / 100.0},
            {"y",          std::round(fe.tdoa.y * 100.0) / 100.0},
            {"confidence", std::round(fe.tdoa.confidence * 1000.0) / 1000.0}
        };
    }

    if (fe.est_dist_m > 0.0)
        loc["est_dist_m"] = std::round(fe.est_dist_m * 100.0) / 100.0;

    // Node detayları
    json node_data = json::array();
    for (const auto& e : fe.events) {
        node_data.push_back({
            {"node_id",     e.node_id},
            {"rms_energy",  std::round(e.rms_energy * 10.0) / 10.0},
            {"duration_ms", e.duration_ms},
            {"time_synced", e.time_synced}
        });
    }
    loc["nodes"] = node_data;

    std::string payload = loc.dump();
    mqttPublish("groundeye/location", payload, false);
    std::cout << "[FUSED] " << payload << "\n";
}

// ── MQTT callbacks ────────────────────────────────────────────
void onConnect(mosquitto*, void*, int rc) {
    if (rc != 0) {
        std::cerr << "[MQTT] Bağlantı başarısız rc=" << rc << "\n";
        return;
    }
    std::cout << "[MQTT] Bağlandı: " << g_cfg.broker << "\n";

    // DSP servisinden gelen event'leri dinle
    mosquitto_subscribe(g_mosq, nullptr, "groundeye/event", 0);
    std::cout << "[MQTT] Subscribe: groundeye/event\n";
}

void onDisconnect(mosquitto*, void*, int rc) {
    if (rc != 0)
        std::cerr << "[MQTT] Bağlantı kesildi rc=" << rc << "\n";
}

void onMessage(mosquitto*, void*, const mosquitto_message* msg) {
    if (!msg || !msg->topic) return;

    std::string topic(msg->topic);
    if (topic != "groundeye/event") return;

    std::string payload(static_cast<char*>(msg->payload), msg->payloadlen);

    try {
        json j     = json::parse(payload);
        NodeEvent e;
        e.node_id        = j["node_id"].get<std::string>();
        e.onset_ms       = j["onset_ms"].get<uint64_t>();
        e.peak_ms        = j["peak_ms"].get<uint64_t>();
        e.rms_energy     = j["rms_energy"].get<double>();
        e.peak_amplitude = j["peak_amplitude"].get<double>();
        e.duration_ms    = j["duration_ms"].get<double>();
        e.time_synced    = j.value("time_synced", false);

        std::lock_guard<std::mutex> lock(g_pending_mutex);
        g_pending.push_back({e, epochMs()});

        std::cout << "[EVENT] " << e.node_id
                  << " rms=" << e.rms_energy
                  << " dur=" << e.duration_ms << "ms\n";
    }
    catch (const std::exception& ex) {
        std::cerr << "[PARSE] Event parse hatası: " << ex.what() << "\n";
    }
}

// ── Argüman parser ────────────────────────────────────────────
std::string parseArgs(int argc, char* argv[]) {
    std::string config_path = "config.json";
    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if ((arg == "--config" || arg == "-c") && i + 1 < argc)
            config_path = argv[++i];
        else if (arg == "--help" || arg == "-h") {
            std::cout << "Kullanım: groundeye_orch --config config.json\n";
            std::exit(0);
        }
    }
    return config_path;
}

// ── Main ──────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    std::signal(SIGINT,  onSignal);
    std::signal(SIGTERM, onSignal);

    // Config yükle
    std::string config_path = parseArgs(argc, argv);
    try {
        g_cfg = Config::fromFile(config_path);
    } catch (const std::exception& ex) {
        std::cerr << "Config hatası: " << ex.what() << "\n";
        return 1;
    }

    std::cout << "GroundEye Orkestrasyon Servisi\n";
    std::cout << "Broker  : " << g_cfg.broker << ":" << g_cfg.port << "\n";
    std::cout << "Nodes   : " << g_cfg.nodes.size() << "\n";
    std::cout << "Window  : " << g_cfg.fusion_window_ms << "ms\n";
    std::cout << "Min nodes for location: " << g_cfg.min_nodes << "\n";

    for (const auto& n : g_cfg.nodes)
        std::cout << "  " << n.id
                  << " x=" << n.x << " y=" << n.y << "\n";

    // Fusion (amplitude + TDOA)
    g_fusion = new Fusion(g_cfg.nodes, g_cfg.wave_speed_ms, g_cfg.dist_scale);

    // SQLite logger
    try {
        g_logger = new EventLogger(g_cfg.sqlite_path);
    } catch (const std::exception& ex) {
        std::cerr << "SQLite hatası: " << ex.what() << "\n";
        return 1;
    }

    // Mosquitto
    mosquitto_lib_init();
    g_mosq = mosquitto_new("groundeye-orch", true, nullptr);
    if (!g_mosq) {
        std::cerr << "mosquitto_new başarısız\n";
        return 1;
    }

    mosquitto_connect_callback_set(g_mosq,    onConnect);
    mosquitto_disconnect_callback_set(g_mosq, onDisconnect);
    mosquitto_message_callback_set(g_mosq,    onMessage);
    mosquitto_reconnect_delay_set(g_mosq, 1, 5, false);

    int rc = mosquitto_connect(g_mosq,
                               g_cfg.broker.c_str(),
                               g_cfg.port, 60);
    if (rc != MOSQ_ERR_SUCCESS) {
        std::cerr << "Bağlantı hatası: "
                  << mosquitto_strerror(rc) << "\n";
        return 1;
    }

    mosquitto_loop_start(g_mosq);
    std::cout << "[BOOT] Orkestrasyon çalışıyor — Ctrl+C ile dur\n";

    // Ana döngü — fusion window kontrolü
    while (g_running) {
        processFusionWindow();
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    std::cout << "\n[STOP] Durduruluyor...\n";
    mosquitto_loop_stop(g_mosq, true);
    mosquitto_disconnect(g_mosq);
    mosquitto_destroy(g_mosq);
    mosquitto_lib_cleanup();

    delete g_logger;
    delete g_fusion;
    return 0;
}