"""
GroundEye — Single Node Signal Analysis v2
Spectral subtraction noise reduction + adaptive parameters for walking
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal as sp
from scipy.ndimage import uniform_filter1d

# ── Config ────────────────────────────────────────────────────
FS             = 2000
BANDPASS_LOW   = 4       # Hz — yürüyüş için 4 Hz'e indirdik
BANDPASS_HIGH  = 80      # Hz — yürüyüş enerjisi burada yoğun
STA_S          = 0.1     # 100ms — yürüyüş adımı için daha uzun
LTA_S          = 1.0     # 1s background
TRIGGER_ON     = 2.0     # düşürüldü
TRIGGER_OFF    = 1.3
MIN_EVENT_MS   = 80      # yürüyüş adımı en az 80ms sürer
ENERGY_WIN_S   = 0.3     # 300ms RMS pencere
BASELINE_WIN_S = 1.0

# Spectral subtraction parametreleri
SPEC_ALPHA     = 2.0     # over-subtraction faktörü (1.0-3.0 arası)
SPEC_BETA      = 0.01    # spectral floor (gürültünün altına inmesin)

DIST_SCALE     = None

# ── Dosya yükleme ─────────────────────────────────────────────
# Kullanım:
#   python analyze_node.py walk.bin             → sadece sinyal
#   python analyze_node.py walk.bin noise.bin   → spectral subtraction ile
args = sys.argv[1:]
if len(args) == 0:
    signal_path = '/tmp/node1_tap.bin'
    noise_path  = None
elif len(args) == 1:
    signal_path = args[0]
    noise_path  = None
else:
    signal_path = args[0]
    noise_path  = args[1]

raw = np.fromfile(signal_path, dtype='<i2').astype(np.float32)
print(f"Sinyal: {len(raw)} sample — {len(raw)/FS:.2f}s")
print(f"Raw  min={raw.min():.0f}  max={raw.max():.0f}  mean={raw.mean():.1f}")

t = np.arange(len(raw)) / FS

# ── Step 1: Baseline removal ──────────────────────────────────
baseline  = uniform_filter1d(raw, size=int(BASELINE_WIN_S * FS))
detrended = raw - baseline

# ── Step 2: Bandpass ──────────────────────────────────────────
b, a     = sp.butter(4, [BANDPASS_LOW, BANDPASS_HIGH],
                      btype='bandpass', fs=FS)
filtered = sp.filtfilt(b, a, detrended)

# ── Step 3: Spectral Subtraction (opsiyonel) ──────────────────
# Gürültü kaydı varsa frekans domeninde çıkar.
# Yoksa yine de çalışır, sadece bu adım atlanır.
def spectral_subtract(signal, noise_profile, fs,
                      alpha=SPEC_ALPHA, beta=SPEC_BETA):
    """
    Her frame için:
      |S_clean(f)|² = max(|S_noisy(f)|² - alpha*|N(f)|², beta*|S_noisy(f)|²)
    Fazı koru, temizlenmiş sinyali geri dönüştür.
    """
    frame_len  = 256       # ~128ms @ 2kHz
    hop        = frame_len // 2
    n_frames   = (len(signal) - frame_len) // hop
    output     = np.zeros(len(signal))
    window     = np.hanning(frame_len)

    # Gürültü profili — ortalama güç spektrumu
    noise_psd  = np.zeros(frame_len // 2 + 1)
    n_noise    = (len(noise_profile) - frame_len) // hop
    for i in range(n_noise):
        frame      = noise_profile[i*hop : i*hop + frame_len] * window
        noise_psd += np.abs(np.fft.rfft(frame)) ** 2
    noise_psd /= max(n_noise, 1)

    # Her sinyal frame'ine uygula
    norm = np.zeros(len(signal))
    for i in range(n_frames):
        start      = i * hop
        frame      = signal[start:start+frame_len] * window
        S          = np.fft.rfft(frame)
        mag        = np.abs(S)
        phase      = np.angle(S)
        mag2       = mag ** 2

        # Spectral subtraction
        clean_mag2 = np.maximum(mag2 - alpha * noise_psd,
                                beta * mag2)
        clean_mag  = np.sqrt(clean_mag2)

        # Fazı koru, geri dönüştür
        S_clean    = clean_mag * np.exp(1j * phase)
        frame_out  = np.fft.irfft(S_clean) * window

        output[start:start+frame_len] += frame_out
        norm[start:start+frame_len]   += window ** 2

    # Normalize overlap-add
    norm = np.where(norm > 1e-8, norm, 1.0)
    return output / norm

if noise_path is not None:
    noise_raw = np.fromfile(noise_path, dtype='<i2').astype(np.float32)
    # Gürültü kaydına da aynı bandpass uygula
    noise_base     = uniform_filter1d(noise_raw, size=int(BASELINE_WIN_S * FS))
    noise_detrend  = noise_raw - noise_base
    noise_filtered = sp.filtfilt(b, a, noise_detrend)

    print(f"Gürültü profili: {len(noise_raw)} sample — {len(noise_raw)/FS:.2f}s")
    filtered_clean = spectral_subtract(filtered, noise_filtered, FS)
    used_spec_sub  = True
    print("Spectral subtraction uygulandı")
else:
    filtered_clean = filtered
    used_spec_sub  = False
    print("Spectral subtraction yok (gürültü kaydı verilmedi)")

# ── Step 4: Envelope ──────────────────────────────────────────
analytic        = sp.hilbert(filtered_clean)
envelope        = np.abs(analytic)
envelope_smooth = uniform_filter1d(envelope, size=int(0.05 * FS))

# ── Step 5: STA/LTA ───────────────────────────────────────────
sta_len = int(STA_S * FS)
lta_len = int(LTA_S * FS)
sta     = uniform_filter1d(envelope_smooth, size=sta_len)
lta     = uniform_filter1d(envelope_smooth, size=lta_len)
ratio   = np.where(lta > 1e-6, sta / lta, 0.0)

# ── Step 6: Event extraction ──────────────────────────────────
def extract_events(ratio, envelope, filtered, fs):
    events      = []
    in_event    = False
    evt_start   = 0
    energy_win  = int(ENERGY_WIN_S * fs)
    min_samples = int(MIN_EVENT_MS / 1000 * fs)

    for i in range(len(ratio)):
        if not in_event and ratio[i] > TRIGGER_ON:
            in_event  = True
            evt_start = i
        elif in_event and ratio[i] < TRIGGER_OFF:
            in_event = False
            duration = i - evt_start
            if duration < min_samples:
                continue

            peak_idx = evt_start + np.argmax(envelope[evt_start:i])
            w0  = max(0, peak_idx - energy_win // 2)
            w1  = min(len(filtered), peak_idx + energy_win // 2)
            rms = float(np.sqrt(np.mean(filtered[w0:w1] ** 2)))

            est_dist = None
            if DIST_SCALE is not None and rms > 0:
                est_dist = round(DIST_SCALE / rms, 2)

            events.append({
                'onset_sample':   evt_start,
                'peak_sample':    peak_idx,
                'end_sample':     i,
                'onset_time_s':   evt_start / fs,
                'peak_time_s':    peak_idx  / fs,
                'duration_ms':    duration  / fs * 1000,
                'rms_energy':     round(rms, 2),
                'peak_amplitude': round(float(envelope[peak_idx]), 2),
                'est_dist_m':     est_dist,
            })
    return events

events = extract_events(ratio, envelope_smooth, filtered_clean, FS)

# ── Sonuçlar ──────────────────────────────────────────────────
print(f"\n{'─'*65}")
print(f"{'#':<4} {'onset':>8} {'peak':>8} {'dur':>8} {'rms':>10} {'peak_amp':>10}")
print(f"{'─'*65}")
for idx, e in enumerate(events):
    print(f"{idx+1:<4} "
          f"{e['onset_time_s']:>7.3f}s "
          f"{e['peak_time_s']:>7.3f}s "
          f"{e['duration_ms']:>7.0f}ms "
          f"{e['rms_energy']:>10.1f} "
          f"{e['peak_amplitude']:>10.1f}")
print(f"{'─'*65}")
print(f"Toplam event: {len(events)}")

event_mask = np.zeros(len(filtered_clean), dtype=bool)
for e in events:
    event_mask[e['onset_sample']:e['end_sample']] = True
quiet       = filtered_clean[~event_mask]
noise_floor = float(np.sqrt(np.mean(quiet ** 2))) if len(quiet) > 0 else 0
print(f"Gürültü tabanı RMS: {noise_floor:.1f} count")
if events and noise_floor > 0:
    snr = [e['rms_energy'] / noise_floor for e in events]
    print(f"SNR aralığı: {min(snr):.1f}x – {max(snr):.1f}x")

# ── Plot ──────────────────────────────────────────────────────
subtitle = "Spectral subtraction uygulandı" if used_spec_sub else "Spectral subtraction yok"
fig, axes = plt.subplots(5, 1, figsize=(14, 13), sharex=True)
fig.suptitle(f"GroundEye — {signal_path}\n{subtitle}", fontsize=11)

axes[0].plot(t, raw, lw=0.4, color='steelblue')
axes[0].plot(t, baseline, lw=1, color='red', label='baseline')
axes[0].set_title("1. Raw ADC + baseline")
axes[0].set_ylabel("counts")
axes[0].legend(fontsize=8)

axes[1].plot(t, detrended, lw=0.4, color='steelblue')
axes[1].set_title("2. Baseline çıkarıldı")
axes[1].set_ylabel("counts")
axes[1].axhline(0, color='red', lw=0.8, linestyle='--')

axes[2].plot(t, filtered_clean, lw=0.4, color='green')
axes[2].set_title(f"3. Bandpass {BANDPASS_LOW}–{BANDPASS_HIGH}Hz"
                  + (" + Spectral subtraction" if used_spec_sub else ""))
axes[2].set_ylabel("counts")
axes[2].axhline(0, color='red', lw=0.8, linestyle='--')

axes[3].plot(t, envelope_smooth, lw=0.8, color='darkorange')
axes[3].set_title("4. Envelope (Hilbert)")
axes[3].set_ylabel("amplitude")

axes[4].plot(t, ratio, lw=0.8, color='crimson')
axes[4].axhline(TRIGGER_ON,  color='black', linestyle='--',
                lw=1, label=f'trigger ON ({TRIGGER_ON})')
axes[4].axhline(TRIGGER_OFF, color='gray',  linestyle='--',
                lw=1, label=f'trigger OFF ({TRIGGER_OFF})')
axes[4].set_title("5. STA/LTA oranı")
axes[4].set_ylabel("oran")
axes[4].set_xlabel("Zaman (s)")
axes[4].legend(fontsize=8)

colors = ['blue', 'purple', 'teal', 'olive', 'navy', 'darkred']
for idx, e in enumerate(events):
    c = colors[idx % len(colors)]
    for ax in axes:
        ax.axvline(e['onset_time_s'], color=c, alpha=0.35, lw=1.2)
        ax.axvline(e['peak_time_s'],  color=c, alpha=0.6,
                   lw=1, linestyle=':')
    axes[4].text(e['peak_time_s'],
                 min(ratio.max() * 0.85, axes[4].get_ylim()[1] * 0.85),
                 f"#{idx+1}\n{e['rms_energy']:.0f}",
                 fontsize=7, ha='center', color=c)

plt.tight_layout()
out = signal_path.replace('.bin', '_analysis.png')
plt.savefig(out, dpi=150)
plt.show()
print(f"Kaydedildi: {out}")
