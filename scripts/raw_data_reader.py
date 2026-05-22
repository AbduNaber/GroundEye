import numpy as np
import matplotlib.pyplot as plt

samples = np.fromfile('/tmp/node1_tap.bin', dtype='<i2')
center  = samples.mean()
signal  = samples - center   # deviation from baseline

t = np.arange(len(samples)) / 2000.0   # time axis in seconds

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6))

# Raw ADC
ax1.plot(t, samples, linewidth=0.5)
ax1.axhline(center, color='r', linestyle='--', label=f'mean={center:.0f}')
ax1.set_title("Raw ADC")
ax1.set_ylabel("ADC count")
ax1.legend()

# Deviation from center — what the signal processing will actually use
ax2.plot(t, signal, linewidth=0.5, color='orange')
ax2.axhline(0, color='r', linestyle='--')
ax2.set_title("Signal deviation from baseline")
ax2.set_xlabel("Time (s)")
ax2.set_ylabel("ADC deviation")

plt.tight_layout()
plt.show()
