#pragma once
// ============================================================
//  GroundEye — DSP Pipeline
//  Butterworth bandpass (4Hz-80Hz, order 8) + Hilbert envelope
//  + STA/LTA event detector
//
//  One NodeDSP instance per sensor node.
//  Call push(sample) for every incoming ADC sample.
//  Events are returned via callback.
// ============================================================

#include <array>
#include <cmath>
#include <cstdint>
#include <deque>
#include <functional>
#include <string>
#include <vector>

namespace groundeye {

    // ------------------------------------------------------------
    //  Butterworth bandpass — Second-Order Sections (biquad kaskadı)
    //  scipy.signal.butter(4, [2, 25], 'bandpass', fs=2000) -> tf2sos
    //
    //  İNSAN YÜRÜYÜŞÜ bandı (2-25 Hz):
    //    - Adım sismik enerjisini (≈2-25 Hz) geçirir.
    //    - 50 Hz şebeke hum'ını ~26 dB (≈20×) bastırır.
    //    - 100 Hz+ gürültüyü ~51 dB ezer.
    //  (Tokmak için eski band 4-80 Hz idi; 50 Hz'i hiç süzmüyordu.)
    //
    //  NEDEN SOS: Bu düşük bantta kutuplar birim çembere çok yakın
    //  (|z| ≈ 0.9998). Tek 8. derece Direct Form bölüm sayısal olarak
    //  bozulur (~%2 hata). Biquad kaskadı her bantta kararlıdır.
    //
    //  Bandı değiştirmek için: yukarıdaki scipy satırını çalıştır,
    //  tf2sos çıktısını aşağıdaki tabloya yapıştır.
    // ------------------------------------------------------------
    static constexpr int NUM_SECTIONS = 4;
    // Her satır: { b0, b1, b2, a1, a2 }   (a0 = 1 normalize edilmiş)
    static constexpr double SOS[NUM_SECTIONS][5] = {
        { 1.552871946694384e-06, 3.10593715473906e-06, 1.553065220071868e-06, -1.882028838218187, 0.8863611291259829 },
        { 1.0, 1.999875545855084, 0.9998755535987913, -1.944446890318106, 0.9502473232947605 },
        { 1.0, -1.999999995912507, 1.000000002038517, -1.993438666977459, 0.9935148024522368 },
        { 1.0, -2.000000004087489, 0.9999999979614813, -1.989361721724033, 0.989363272472687 }
    };

    // ------------------------------------------------------------
    //  IIR Filter — biquad kaskadı (her bölüm Transposed Direct Form II)
    //  Sayısal olarak kararlı, gerçek zamanlı stream için ideal.
    // ------------------------------------------------------------
    class IIRFilter {
    public:
        IIRFilter() { reset(); }

        void reset() {
            for (auto& v : z1_) v = 0.0;
            for (auto& v : z2_) v = 0.0;
        }

        // Her yeni sample için bir kez çağır — filtrelenmiş değeri döner.
        // Sinyal bölümler arasında zincirleme akar (kaskad).
        double process(double x) {
            for (int s = 0; s < NUM_SECTIONS; ++s) {
                const double b0 = SOS[s][0], b1 = SOS[s][1], b2 = SOS[s][2];
                const double a1 = SOS[s][3], a2 = SOS[s][4];
                double y = b0 * x + z1_[s];
                z1_[s]   = b1 * x - a1 * y + z2_[s];
                z2_[s]   = b2 * x - a2 * y;
                x = y;   // bu bölümün çıkışı → sonraki bölümün girişi
            }
            return x;
        }

    private:
        std::array<double, NUM_SECTIONS> z1_{};
        std::array<double, NUM_SECTIONS> z2_{};
    };

    // ------------------------------------------------------------
    //  Hilbert Envelope — sliding window yaklaşımı
    //  Gerçek Hilbert dönüşümü FFT gerektirir.
    //  Burada batch-based approximate envelope kullanıyoruz:
    //  kısa pencerede RMS → smooth amplitude estimate.
    //  Hafif, gerçek zamanlı, event tespiti için yeterli.
    // ------------------------------------------------------------
    class EnvelopeEstimator {
    public:
        explicit EnvelopeEstimator(int window_samples = 50)
        : window_(window_samples < 1 ? 1 : window_samples) {}

        double process(double x) {
            double sq = x * x;          // x²
            buf_.push_back(sq);
            sum_ += sq;                 // running sum — O(1) yerine O(window) değil
            if ((int)buf_.size() > window_) {
                sum_ -= buf_.front();
                buf_.pop_front();
            }
            if (sum_ < 0.0) sum_ = 0.0; // kayan nokta drift koruması
            return std::sqrt(sum_ / buf_.size());  // RMS = envelope
        }

        void reset() { buf_.clear(); sum_ = 0.0; }

    private:
        int window_;
        double sum_ = 0.0;
        std::deque<double> buf_;
    };

    // ------------------------------------------------------------
    //  STA/LTA Detector
    // ------------------------------------------------------------
    class STALTADetector {
    public:
        STALTADetector(int sta_samples, int lta_samples,
                       double trigger_on, double trigger_off)
        : sta_len_(sta_samples < 1 ? 1 : sta_samples)
        , lta_len_(lta_samples < 1 ? 1 : lta_samples)
        , trigger_on_(trigger_on)
        , trigger_off_(trigger_off) {}

        // Envelope değerini gönder, tetik durumu döner.
        // ÖNEMLİ: Event sırasında LTA DONDURULUR (recharge prevention).
        // Aksi halde event enerjisi LTA'ya sızar, ratio çöker ve
        // event erken kesilir / parçalanır.
        bool process(double env) {
            // STA her zaman güncellenir (running sum)
            sta_buf_.push_back(env);
            sta_sum_ += env;
            if ((int)sta_buf_.size() > sta_len_) {
                sta_sum_ -= sta_buf_.front();
                sta_buf_.pop_front();
            }

            // LTA yalnızca event DIŞINDA güncellenir
            if (!in_event_) {
                lta_buf_.push_back(env);
                lta_sum_ += env;
                if ((int)lta_buf_.size() > lta_len_) {
                    lta_sum_ -= lta_buf_.front();
                    lta_buf_.pop_front();
                }
            }

            double sta = sta_buf_.empty() ? 0.0 : sta_sum_ / sta_buf_.size();
            double lta = lta_buf_.empty() ? 0.0 : lta_sum_ / lta_buf_.size();
            ratio_ = (lta > 1e-9) ? sta / lta : 0.0;

            // Tetik durum makinesi (histerezis)
            if (!in_event_ && ratio_ >= trigger_on_) {
                in_event_ = true;
            } else if (in_event_ && ratio_ < trigger_off_) {
                in_event_ = false;
            }
            return in_event_;
        }

        double ratio() const { return ratio_; }

        void reset() {
            sta_buf_.clear();
            lta_buf_.clear();
            sta_sum_  = 0.0;
            lta_sum_  = 0.0;
            ratio_    = 0.0;
            in_event_ = false;
        }

    private:
        int sta_len_, lta_len_;
        double trigger_on_, trigger_off_;
        bool   in_event_ = false;
        double ratio_    = 0.0;
        double sta_sum_  = 0.0;
        double lta_sum_  = 0.0;
        std::deque<double> sta_buf_, lta_buf_;
    };

    // ------------------------------------------------------------
    //  Event — DSP pipeline çıktısı
    // ------------------------------------------------------------
    struct Event {
        std::string node_id;
        uint64_t    onset_ms;        // epoch ms (NTP synced)
        uint64_t    peak_ms;
        double      rms_energy;
        double      peak_amplitude;
        double      duration_ms;
        bool        time_synced = false;  // NTP sync güvenilir miydi
    };

    // ------------------------------------------------------------
    //  DetectorParams — config.json'dan yüklenir, recompile gerekmez
    // ------------------------------------------------------------
    struct DetectorParams {
        int    fs              = 2000;   // örnekleme frekansı (Hz)
        double sta_s           = 0.1;    // STA penceresi (s)
        double lta_s           = 1.0;    // LTA penceresi (s)
        double trigger_on      = 2.0;    // tetik açma eşiği (ratio)
        double trigger_off     = 1.3;    // tetik kapatma eşiği (ratio)
        double env_window_s    = 0.05;   // envelope RMS penceresi (s)
        double min_duration_ms = 80.0;   // bundan kısa eventları at (gürültü spike)
        double min_peak_amp    = 0.0;    // bundan zayıf eventları at (0 = kapalı)
    };

    // ------------------------------------------------------------
    //  NodeDSP — tek bir node için tam pipeline
    // ------------------------------------------------------------
    class NodeDSP {
    public:
        explicit NodeDSP(std::string node_id,
                         const DetectorParams& p = DetectorParams{})
        : node_id_(std::move(node_id))
        , fs_(p.fs)
        , params_(p)
        , envelope_(static_cast<int>(p.env_window_s * p.fs))
        , stalta_(static_cast<int>(p.sta_s * p.fs),
                  static_cast<int>(p.lta_s * p.fs),
                  p.trigger_on, p.trigger_off)
        {}

        // Callback tipi: event hazır olduğunda çağrılır
        using EventCallback = std::function<void(const Event&)>;
        void setCallback(EventCallback cb) { callback_ = std::move(cb); }

        // ── Ana giriş noktası ────────────────────────────────────
        // Her ADC sample için çağır.
        // epoch_ms: bu sample'ın NTP-synced zaman damgası
        void push(int16_t raw_sample, uint64_t epoch_ms) {
            sample_count_++;

            // 1) IIR Bandpass filter
            double filtered = filter_.process(static_cast<double>(raw_sample));

            // 2) Envelope
            double env = envelope_.process(filtered);

            // 3) STA/LTA (LTA event sırasında dondurulur)
            bool triggered = stalta_.process(env);

            // 4) Event state machine
            if (!in_event_ && triggered) {
                // Event başladı
                in_event_       = true;
                event_onset_ms_ = epoch_ms;
                event_peak_ms_  = epoch_ms;
                event_peak_amp_ = env;
                event_samples_.clear();
                event_samples_.push_back(filtered);

            } else if (in_event_ && triggered) {
                // Event devam ediyor
                event_samples_.push_back(filtered);
                if (env > event_peak_amp_) {
                    event_peak_amp_ = env;
                    event_peak_ms_  = epoch_ms;
                }

            } else if (in_event_ && !triggered) {
                // Event bitti
                in_event_ = false;

                double duration_ms = static_cast<double>(
                    epoch_ms - event_onset_ms_);

                // Çok kısa eventları atla (gürültü spike'ı)
                if (duration_ms < params_.min_duration_ms) {
                    event_samples_.clear();
                    return;
                }

                // Zayıf eventları atla (düşük enerjili false trigger)
                if (params_.min_peak_amp > 0.0 &&
                    event_peak_amp_ < params_.min_peak_amp) {
                    event_samples_.clear();
                    return;
                }

                // RMS hesapla
                double rms = 0.0;
                for (double s : event_samples_) rms += s * s;
                rms = std::sqrt(rms / event_samples_.size());

                Event e;
                e.node_id        = node_id_;
                e.onset_ms       = event_onset_ms_;
                e.peak_ms        = event_peak_ms_;
                e.rms_energy     = rms;
                e.peak_amplitude = event_peak_amp_;
                e.duration_ms    = duration_ms;
                e.time_synced    = time_synced_;

                if (callback_) callback_(e);
                event_samples_.clear();
            }
        }

        // Batch push — MQTT'den gelen 256 sample'ı toplu gönder
        // batch_epoch_ms: batch'in ilk sample'ının epoch zamanı
        void pushBatch(const int16_t* samples, int count,
                       uint64_t batch_epoch_ms) {
            for (int i = 0; i < count; ++i) {
                uint64_t sample_ms = batch_epoch_ms
                + static_cast<uint64_t>(i * 1000.0 / fs_);
                push(samples[i], sample_ms);
            }
                       }

                       // main.cpp'den her batch öncesi çağrılır
                       void setTimeSynced(bool synced) { time_synced_ = synced; }

                       void reset() {
                           filter_.reset();
                           envelope_.reset();
                           stalta_.reset();
                           in_event_ = false;
                           event_samples_.clear();
                       }

                       const std::string& nodeId() const { return node_id_; }

    private:
        std::string      node_id_;
        int              fs_;
        DetectorParams   params_;
        IIRFilter        filter_;
        EnvelopeEstimator envelope_;
        STALTADetector   stalta_;
        EventCallback    callback_;

        // Sayaç
        uint64_t sample_count_ = 0;

        // Timestamp güvenilirlik flag'i — main.cpp tarafından set edilir
        bool                  time_synced_    = false;

        // Event state
        bool                  in_event_       = false;
        uint64_t              event_onset_ms_ = 0;
        uint64_t              event_peak_ms_  = 0;
        double                event_peak_amp_ = 0.0;
        std::vector<double>   event_samples_;
    };

} // namespace groundeye
