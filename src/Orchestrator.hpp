#pragma once
// ============================================================
//  GroundEye — Orkestrasyon: Config + Amplitude + TDOA
// ============================================================

#include <nlohmann/json.hpp>
#include <array>
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;

namespace groundeye {

    // ------------------------------------------------------------
    //  Node konumu
    // ------------------------------------------------------------
    struct NodePosition {
        std::string id;
        double x;   // metre
        double y;   // metre
    };

    // ------------------------------------------------------------
    //  Config
    // ------------------------------------------------------------
    struct Config {
        std::string broker           = "10.169.254.204";
        int         port             = 1883;
        int         fusion_window_ms = 2000;
        int         min_nodes        = 2;
        std::string sqlite_path      = "/tmp/groundeye.db";
        double      dist_scale       = -1.0;
        double      wave_speed_ms    = 0.200;  // m/ms — toprak dalga hızı
        std::vector<NodePosition> nodes;

        static Config fromFile(const std::string& path) {
            std::ifstream f(path);
            if (!f.is_open())
                throw std::runtime_error("Config açılamadı: " + path);

            json j = json::parse(f);
            Config c;
            c.broker           = j.value("broker",           c.broker);
            c.port             = j.value("port",             c.port);
            c.fusion_window_ms = j.value("fusion_window_ms", c.fusion_window_ms);
            c.min_nodes        = j.value("min_nodes_for_location", c.min_nodes);
            c.sqlite_path      = j.value("sqlite_path",      c.sqlite_path);
            c.wave_speed_ms    = j.value("wave_speed_ms",    c.wave_speed_ms);

            if (j.contains("dist_scale") && !j["dist_scale"].is_null())
                c.dist_scale = j.value("dist_scale", -1.0);

            for (const auto& n : j["nodes"])
                c.nodes.push_back({
                    n["id"].get<std::string>(),
                                  n["x"].get<double>(),
                                  n["y"].get<double>()
                });
            return c;
        }
    };

    // ------------------------------------------------------------
    //  NodeEvent — DSP servisinden gelir
    // ------------------------------------------------------------
    struct NodeEvent {
        std::string node_id;
        uint64_t    onset_ms;
        uint64_t    peak_ms;
        double      rms_energy;
        double      peak_amplitude;
        double      duration_ms;
        bool        time_synced = false;
    };

    // ------------------------------------------------------------
    //  LocationResult — tek bir yöntemin sonucu
    // ------------------------------------------------------------
    struct LocationResult {
        double x          = -1.0;
        double y          = -1.0;
        double confidence = 0.0;   // 0–1 arası
        bool   valid      = false;
    };

    // ------------------------------------------------------------
    //  FusedEvent — füzyon sonucu
    // ------------------------------------------------------------
    struct FusedEvent {
        uint64_t       timestamp_ms;
        LocationResult amplitude;      // amplitude weighted centroid
        LocationResult tdoa;           // TDOA Gauss-Newton
        LocationResult best;           // yüksek confidence olan
        std::string    best_method;    // "amplitude" | "tdoa" | "none"
        std::string    nearest_node;
        double         est_dist_m  = -1.0;
        int            node_count  = 0;
        bool           tdoa_used   = false;  // 3 synced node vardı mı
        std::vector<NodeEvent> events;
    };

    // ============================================================
    //  AmplitudeLocator — weighted centroid
    // ============================================================
    class AmplitudeLocator {
    public:
        explicit AmplitudeLocator(const std::vector<NodePosition>& pos)
        : positions_(pos) {}

        LocationResult compute(const std::vector<NodeEvent>& events,
                               std::string& nearest_node) const {
                                   LocationResult r;
                                   if (events.empty()) return r;

                                   double max_rms = -1.0;
                                   for (const auto& e : events)
                                       if (e.rms_energy > max_rms) {
                                           max_rms      = e.rms_energy;
                                           nearest_node = e.node_id;
                                       }

                                       if (events.size() == 1) {
                                           auto pos = find(events[0].node_id);
                                           if (!pos) return r;
                                           r.x = pos->x; r.y = pos->y;
                                           r.confidence = 0.4;  // tek node — düşük güven
                                           r.valid = true;
                                           return r;
                                       }

                                       double sw = 0, swx = 0, swy = 0;
                                       double min_rms = 1e18, max_r = 0;

                                       for (const auto& e : events) {
                                           auto pos = find(e.node_id);
                                           if (!pos) continue;
                                           sw  += e.rms_energy;
                                           swx += e.rms_energy * pos->x;
                                           swy += e.rms_energy * pos->y;
                                           if (e.rms_energy < min_rms) min_rms = e.rms_energy;
                                           if (e.rms_energy > max_r)   max_r   = e.rms_energy;
                                       }

                                       if (sw < 1e-9) return r;
                                       r.x = swx / sw;
                                   r.y = swy / sw;

                                   // Confidence: node'lar arası denge
                                   // min/max yakınsa kaynak ortada → düşük ayrım gücü
                                   // min/max uzaksa net yön var → yüksek güven
                                   r.confidence = (max_r > 1e-9)
                                   ? std::min(1.0 - min_rms / max_r + 0.3, 1.0)
                                   : 0.5;
                                   r.valid = true;
                                   return r;
                               }

                               static double estimateDist(double rms, double dist_scale) {
                                   if (dist_scale <= 0.0 || rms < 1e-6) return -1.0;
                                   return dist_scale / rms;
                               }

    private:
        std::vector<NodePosition> positions_;

        const NodePosition* find(const std::string& id) const {
            for (const auto& p : positions_)
                if (p.id == id) return &p;
                return nullptr;
        }
    };

    // ============================================================
    //  TDOALocator — Gauss-Newton iterative solver
    //
    //  Gereksinim: en az 3 node, hepsi time_synced = true
    //
    //  Algoritma:
    //    Kaynak S(x,y) için residual:
    //      f12 = (d1-d2) - v*Δt12 = 0
    //      f13 = (d1-d3) - v*Δt13 = 0
    //    Jacobian ile iteratif güncelle: S += (JᵀJ)⁻¹Jᵀr
    //    Başlangıç noktası: amplitude sonucu (daha hızlı yakınsama)
    // ============================================================
    class TDOALocator {
    public:
        explicit TDOALocator(const std::vector<NodePosition>& pos,
                             double wave_speed_ms = 0.200)
        : positions_(pos)
        , v_(wave_speed_ms) {}

        // amplitude_x/y: başlangıç tahmini (amplitude locator'dan)
        LocationResult compute(const std::vector<NodeEvent>& events,
                               double amplitude_x, double amplitude_y) const {
                                   LocationResult r;

                                   // En az 3 node, hepsi time_synced olmalı
                                   if (events.size() < 3) return r;
                                   for (const auto& e : events)
                                       if (!e.time_synced) return r;

                                       // Node konumlarını ve onset zamanlarını eşleştir
                                       struct Anchor {
                                           double   x, y;
                                           uint64_t onset_ms;
                                       };
                                   std::vector<Anchor> anchors;
                                   for (const auto& e : events) {
                                       auto pos = find(e.node_id);
                                       if (!pos) continue;
                                       anchors.push_back({pos->x, pos->y, e.onset_ms});
                                   }
                                   if (anchors.size() < 3) return r;

                                   // Referans node: en erken onset (node 0)
                                   // Diğerleri için Δt hesapla
                                   // Not: onset_ms uint64 — fark negatif olabilir (geç gelen)
                                   //      int64_t'ye cast ederek işaretle farkı alıyoruz
                                   auto dt_ms = [&](int i) -> double {
                                       return static_cast<double>(
                                           static_cast<int64_t>(anchors[i].onset_ms)
                                           - static_cast<int64_t>(anchors[0].onset_ms)
                                       );
                                   };

                                   // Gauss-Newton — maksimum 20 iterasyon
                                   double sx = amplitude_x;
                                   double sy = amplitude_y;

                                   for (int iter = 0; iter < 20; ++iter) {
                                       // d0, d1, d2 — S'den her anchor'a mesafe
                                       std::vector<double> d(anchors.size());
                                       for (size_t i = 0; i < anchors.size(); ++i) {
                                           double dx = sx - anchors[i].x;
                                           double dy = sy - anchors[i].y;
                                           d[i] = std::sqrt(dx*dx + dy*dy);
                                           if (d[i] < 1e-9) d[i] = 1e-9;
                                       }

                                       // Residuals: f_i = (d0 - d_i) - v * dt_i
                                       // (i = 1, 2 için)
                                       double f1 = (d[0] - d[1]) - v_ * dt_ms(1);
                                       double f2 = (d[0] - d[2]) - v_ * dt_ms(2);

                                       // Jacobian 2x2:
                                       // J[row][col] = ∂f_row / ∂(sx, sy)
                                       auto ddx = [&](int i) {
                                           return (sx - anchors[i].x) / d[i]; };
                                           auto ddy = [&](int i) {
                                               return (sy - anchors[i].y) / d[i]; };

                                               double j11 = ddx(0) - ddx(1);
                                               double j12 = ddy(0) - ddy(1);
                                               double j21 = ddx(0) - ddx(2);
                                               double j22 = ddy(0) - ddy(2);

                                               // (JᵀJ)⁻¹Jᵀr — 2x2 için doğrudan hesapla
                                               // JᵀJ = [[j11²+j21², j11*j12+j21*j22],
                                               //         [j12*j11+j22*j21, j12²+j22²]]
                                               double a11 = j11*j11 + j21*j21;
                                               double a12 = j11*j12 + j21*j22;
                                               double a22 = j12*j12 + j22*j22;
                                               double det = a11*a22 - a12*a12;

                                               if (std::abs(det) < 1e-12) break;  // tekil matris

                                               // Jᵀr
                                               double b1 = j11*f1 + j21*f2;
                                       double b2 = j12*f1 + j22*f2;

                                       // Güncelleme: Δs = (JᵀJ)⁻¹ Jᵀr
                                       double ds_x = (a22*b1 - a12*b2) / det;
                                       double ds_y = (a11*b2 - a12*b1) / det;

                                       sx -= ds_x;
                                       sy -= ds_y;

                                       // Yakınsama kontrolü
                                       if (std::sqrt(ds_x*ds_x + ds_y*ds_y) < 1e-4) break;
                                   }

                                   // Final residual — kalite skoru için
                                   std::vector<double> d_final(anchors.size());
                                   for (size_t i = 0; i < anchors.size(); ++i) {
                                       double dx = sx - anchors[i].x;
                                       double dy = sy - anchors[i].y;
                                       d_final[i] = std::sqrt(dx*dx + dy*dy);
                                   }

                                   double res = 0.0;
                                   for (size_t i = 1; i < anchors.size(); ++i) {
                                       double pred = (d_final[0] - d_final[i]) / v_;
                                       double meas = dt_ms(i);
                                       res += std::abs(pred - meas);
                                   }

                                   // Confidence: residual ne kadar küçükse o kadar iyi
                                   // res ms cinsinden — 5ms altı çok iyi, 20ms üstü kötü
                                   r.x          = sx;
                                   r.y          = sy;
                                   r.confidence = 1.0 / (1.0 + res / 5.0);
                                   r.valid      = true;
                                   return r;
                               }

    private:
        std::vector<NodePosition> positions_;
        double v_;  // dalga hızı m/ms

        const NodePosition* find(const std::string& id) const {
            for (const auto& p : positions_)
                if (p.id == id) return &p;
                return nullptr;
        }
    };

    // ============================================================
    //  Fusion — her iki yöntemi çalıştırır, best'i seçer
    // ============================================================
    class Fusion {
    public:
        Fusion(const std::vector<NodePosition>& pos,
               double wave_speed_ms, double dist_scale)
        : amp_(pos)
        , tdoa_(pos, wave_speed_ms)
        , dist_scale_(dist_scale) {}

        FusedEvent process(std::vector<NodeEvent> events,
                           uint64_t timestamp_ms) const {
                               FusedEvent fe;
                               fe.timestamp_ms = timestamp_ms;
                               fe.node_count   = static_cast<int>(events.size());
                               fe.events       = events;

                               // Amplitude
                               fe.amplitude = amp_.compute(events, fe.nearest_node);

                               // TDOA — sadece 3+ synced node varsa
                               int synced_count = 0;
                               for (const auto& e : events)
                                   if (e.time_synced) synced_count++;

                                   if (synced_count >= 3 && fe.amplitude.valid) {
                                       fe.tdoa = tdoa_.compute(events,
                                                               fe.amplitude.x,
                                                               fe.amplitude.y);
                                       fe.tdoa_used = fe.tdoa.valid;
                                   }

                                   // Best seç
                                   if (fe.tdoa.valid && fe.tdoa.confidence > fe.amplitude.confidence) {
                                       fe.best        = fe.tdoa;
                                       fe.best_method = "tdoa";
                                   } else if (fe.amplitude.valid) {
                                       fe.best        = fe.amplitude;
                                       fe.best_method = "amplitude";
                                   } else {
                                       fe.best_method = "none";
                                   }

                                   // Mesafe tahmini
                                   if (dist_scale_ > 0.0) {
                                       double max_rms = 0.0;
                                       for (const auto& e : events)
                                           if (e.rms_energy > max_rms) max_rms = e.rms_energy;
                                           fe.est_dist_m = AmplitudeLocator::estimateDist(
                                               max_rms, dist_scale_);
                                   }

                                   return fe;
                           }

    private:
        AmplitudeLocator amp_;
        TDOALocator      tdoa_;
        double           dist_scale_;
    };

} // namespace groundeye
