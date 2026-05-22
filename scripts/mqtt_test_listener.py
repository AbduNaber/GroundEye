import re
import time
from collections import deque

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from paho.mqtt import client as mqtt


MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/#"

MAX_POINTS = 300
SMOOTH_WINDOW = 10

times = deque(maxlen=MAX_POINTS)
sinyal_values = deque(maxlen=MAX_POINTS)
merkez_values = deque(maxlen=MAX_POINTS)
sapma_values = deque(maxlen=MAX_POINTS)

trigger_times = deque(maxlen=100)
trigger_sapma_values = deque(maxlen=100)

start_time = time.time()

log_pattern = re.compile(
    r"Sinyal:(?P<sinyal>-?\d+),Merkez:(?P<merkez>-?\d+),Sapma:(?P<sapma>-?\d+)"
)

trigger_pattern = re.compile(
    r"TETIKLENDI!\s*Sapma:(?P<sapma>-?\d+)"
)


def moving_average(values, window):
    values = list(values)

    if len(values) == 0:
        return []

    smoothed = []

    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start:i + 1]
        smoothed.append(sum(chunk) / len(chunk))

    return smoothed


def on_connect(client, userdata, flags, reason_code, properties=None):
    print("MQTT bağlandı:", reason_code)
    client.subscribe(MQTT_TOPIC)
    print("Dinlenen topic:", MQTT_TOPIC)


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="ignore").strip()
    print(msg.topic, payload)

    t = time.time() - start_time

    if msg.topic == "sensor/log":
        match = log_pattern.search(payload)
        if not match:
            return

        sinyal = int(match.group("sinyal"))
        merkez = int(match.group("merkez"))
        sapma = int(match.group("sapma"))

        times.append(t)
        sinyal_values.append(sinyal)
        merkez_values.append(merkez)
        sapma_values.append(sapma)

    elif msg.topic == "sensor/trigger":
        match = trigger_pattern.search(payload)
        if not match:
            return

        sapma = int(match.group("sapma"))

        trigger_times.append(t)
        trigger_sapma_values.append(sapma)

        print(f"*** TETIKLENDI! t={t:.2f}s Sapma={sapma} ***")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
client.loop_start()


fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(11, 7))

line_sinyal, = ax1.plot([], [], label="Sinyal Smooth")
line_merkez, = ax1.plot([], [], label="Merkez Smooth")

ax1.set_ylabel("ADC Değeri")
ax1.grid(True)
ax1.legend(loc="upper left")

line_sapma, = ax2.plot([], [], label="Sapma Smooth")

ax2.set_xlabel("Zaman (s)")
ax2.set_ylabel("Sapma")
ax2.grid(True)
ax2.legend(loc="upper left")

def update(frame):
    # MQTT callback aynı anda deque değiştirebildiği için önce kopya alıyoruz
    t_values = list(times)
    sinyal_copy = list(sinyal_values)
    merkez_copy = list(merkez_values)
    sapma_copy = list(sapma_values)
    trigger_times_copy = list(trigger_times)
    trigger_sapma_copy = list(trigger_sapma_values)

    if len(t_values) == 0:
        return line_sinyal, line_merkez, line_sapma

    smooth_sinyal = moving_average(sinyal_copy, SMOOTH_WINDOW)
    smooth_merkez = moving_average(merkez_copy, SMOOTH_WINDOW)
    smooth_sapma = moving_average(sapma_copy, SMOOTH_WINDOW)

    line_sinyal.set_data(t_values, smooth_sinyal)
    line_merkez.set_data(t_values, smooth_merkez)
    line_sapma.set_data(t_values, smooth_sapma)

    xmin = max(0, t_values[0])
    xmax = t_values[-1] + 1

    ax1.set_xlim(xmin, xmax)

    all_adc = smooth_sinyal + smooth_merkez
    if all_adc:
        ymin = min(all_adc) - 20
        ymax = max(all_adc) + 20

        if ymin == ymax:
            ymin -= 1
            ymax += 1

        ax1.set_ylim(ymin, ymax)

    all_sapma = smooth_sapma + trigger_sapma_copy
    if all_sapma:
        ymax = max(all_sapma) + 10
        ax2.set_ylim(0, ymax if ymax > 10 else 10)

    # Sapma çizgisi hariç trigger dikey çizgilerini temizle
    for artist in ax2.lines[1:]:
        artist.remove()

    # Trigger noktalarını temizle
    for collection in list(ax2.collections):
        collection.remove()

    # Kopya listeler üzerinden çiziyoruz; artık deque değişse bile hata vermez
    for tt, ss in zip(trigger_times_copy, trigger_sapma_copy):
        if xmin <= tt <= xmax:
            ax2.axvline(tt, linestyle="--", alpha=0.5)
            ax2.scatter([tt], [ss], marker="o", label="_nolegend_")

    return line_sinyal, line_merkez, line_sapma


ani = animation.FuncAnimation(
    fig,
    update,
    interval=100,
    blit=False,
    cache_frame_data=False
)

try:
    plt.suptitle("MQTT Sensör Verisi ve Tetiklenmeler")
    plt.tight_layout()
    plt.show()
finally:
    client.loop_stop()
    client.disconnect()
