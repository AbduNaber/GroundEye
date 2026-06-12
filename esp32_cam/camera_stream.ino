/*
 * GroundEye ESP32-CAM — MJPEG HTTP stream + MQTT status announcer
 *
 * Board : AI-Thinker ESP32-CAM (select in Arduino IDE)
 * Libs  : PubSubClient (2.8+), esp32-camera (bundled with ESP32 board package)
 *
 * Flash at 115200 baud, then switch monitor to 115200 to see IP.
 *
 * MQTT topics published:
 *   groundeye/camera   {"node_id":"cam-1","ip":"...","port":80,"online":true}
 *   groundeye/camera   {"node_id":"cam-1","online":false}   (LWT)
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ─── User config ──────────────────────────────────────────────────────────────
#define WIFI_SSID      "YOUR_SSID"
#define WIFI_PASSWORD  "YOUR_PASSWORD"
#define MQTT_HOST      "192.168.1.100"   // broker IP
#define MQTT_PORT      1883
#define CAM_NODE_ID    "cam-1"
#define STREAM_PORT    80
// ──────────────────────────────────────────────────────────────────────────────

// AI-Thinker ESP32-CAM pin map
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

static const char* BOUNDARY = "gc0boundary";
static const char* MIME_MULTIPART =
    "multipart/x-mixed-replace;boundary=gc0boundary";

WebServer server(STREAM_PORT);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

// ─── Camera init ─────────────────────────────────────────────────────────────

bool init_camera() {
    camera_config_t cfg;
    cfg.ledc_channel  = LEDC_CHANNEL_0;
    cfg.ledc_timer    = LEDC_TIMER_0;
    cfg.pin_d0        = Y2_GPIO_NUM;
    cfg.pin_d1        = Y3_GPIO_NUM;
    cfg.pin_d2        = Y4_GPIO_NUM;
    cfg.pin_d3        = Y5_GPIO_NUM;
    cfg.pin_d4        = Y6_GPIO_NUM;
    cfg.pin_d5        = Y7_GPIO_NUM;
    cfg.pin_d6        = Y8_GPIO_NUM;
    cfg.pin_d7        = Y9_GPIO_NUM;
    cfg.pin_xclk      = XCLK_GPIO_NUM;
    cfg.pin_pclk      = PCLK_GPIO_NUM;
    cfg.pin_vsync     = VSYNC_GPIO_NUM;
    cfg.pin_href      = HREF_GPIO_NUM;
    cfg.pin_sscb_sda  = SIOD_GPIO_NUM;
    cfg.pin_sscb_scl  = SIOC_GPIO_NUM;
    cfg.pin_pwdn      = PWDN_GPIO_NUM;
    cfg.pin_reset     = RESET_GPIO_NUM;
    cfg.xclk_freq_hz  = 20000000;
    cfg.pixel_format  = PIXFORMAT_JPEG;

    if (psramFound()) {
        cfg.frame_size   = FRAMESIZE_VGA;   // 640×480
        cfg.jpeg_quality = 12;
        cfg.fb_count     = 2;
    } else {
        cfg.frame_size   = FRAMESIZE_QVGA;  // 320×240
        cfg.jpeg_quality = 20;
        cfg.fb_count     = 1;
    }

    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed: 0x%x\n", err);
        return false;
    }

    sensor_t* s = esp_camera_sensor_get();
    s->set_framesize(s, FRAMESIZE_VGA);
    s->set_quality(s, 12);
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_hmirror(s, 0);
    s->set_vflip(s, 0);
    return true;
}

// ─── HTTP MJPEG handler ──────────────────────────────────────────────────────

void handle_stream() {
    WiFiClient client = server.client();

    // Send HTTP headers
    client.print("HTTP/1.1 200 OK\r\n");
    client.printf("Content-Type: %s\r\n", MIME_MULTIPART);
    client.print("Connection: close\r\n");
    client.print("Cache-Control: no-cache, no-store\r\n\r\n");

    while (client.connected()) {
        camera_fb_t* fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("Frame capture failed");
            delay(100);
            continue;
        }

        client.printf("--%s\r\n", BOUNDARY);
        client.print("Content-Type: image/jpeg\r\n");
        client.printf("Content-Length: %u\r\n\r\n", fb->len);
        client.write(fb->buf, fb->len);
        client.print("\r\n");

        esp_camera_fb_return(fb);

        // Yield to keep watchdog + MQTT alive between frames
        mqtt.loop();
        delay(1);
    }
}

void handle_snapshot() {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        server.send(503, "text/plain", "frame error");
        return;
    }
    server.sendHeader("Content-Disposition", "inline; filename=snap.jpg");
    server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
    esp_camera_fb_return(fb);
}

void handle_root() {
    String html = "<html><body>"
        "<h3>GroundEye CAM · " CAM_NODE_ID "</h3>"
        "<img src='/stream' style='max-width:100%'>"
        "</body></html>";
    server.send(200, "text/html", html);
}

// ─── MQTT ────────────────────────────────────────────────────────────────────

void mqtt_announce(bool online) {
    StaticJsonDocument<128> doc;
    doc["node_id"] = CAM_NODE_ID;
    doc["online"]  = online;
    if (online) {
        doc["ip"]   = WiFi.localIP().toString();
        doc["port"] = STREAM_PORT;
    }
    char buf[128];
    serializeJson(doc, buf);
    // retain=true so late-joining clients know about the camera
    mqtt.publish("groundeye/camera", buf, /*retain=*/true);
}

void mqtt_reconnect() {
    if (mqtt.connected()) return;

    // LWT: announce offline if we drop
    StaticJsonDocument<64> lwt;
    lwt["node_id"] = CAM_NODE_ID;
    lwt["online"]  = false;
    char lwtBuf[64];
    serializeJson(lwt, lwtBuf);

    if (mqtt.connect(CAM_NODE_ID, nullptr, nullptr,
                     "groundeye/camera", 0, true, lwtBuf)) {
        Serial.println("MQTT connected");
        mqtt_announce(true);
    }
}

// ─── Setup / Loop ─────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.setDebugOutput(false);

    if (!init_camera()) {
        Serial.println("Camera init failed — halting");
        while (true) delay(1000);
    }

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\nIP: %s\n", WiFi.localIP().toString().c_str());

    server.on("/",        handle_root);
    server.on("/stream",  handle_stream);
    server.on("/snapshot", handle_snapshot);
    server.begin();
    Serial.printf("Stream: http://%s/stream\n", WiFi.localIP().toString().c_str());

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setKeepAlive(30);
    mqtt_reconnect();
}

void loop() {
    server.handleClient();

    if (WiFi.status() == WL_CONNECTED) {
        if (!mqtt.connected()) {
            static unsigned long lastRetry = 0;
            if (millis() - lastRetry > 5000) {
                lastRetry = millis();
                mqtt_reconnect();
            }
        } else {
            mqtt.loop();
        }
    }
}
