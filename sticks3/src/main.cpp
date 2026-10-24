// SPDX-License-Identifier: MIT
#ifndef STICKS3_DIAGNOSTIC
#include <M5Unified.h>
#include <lgfx/v1/platforms/esp32/Light_PWM.hpp>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ctime>
#include <memory>
#include "controller.h"
#include "screen.h"

namespace {
std::unique_ptr<light::Controller> controller;
light::Screen screen;
std::string ssid, password, haUrl, token, ca;
bool filesystemOk = false;
bool settingsOk = false;
bool tlsReady = false;
uint32_t lastBatteryAt = 0;
uint32_t lastWifiRetryAt = 0;
volatile uint32_t wifiDisconnectReason = 0;
int backlightChannel = -1;

void configureBacklight() {
  constexpr uint8_t brightness = 128;
  if (M5.getBoard() == m5::board_t::board_M5StickS3 && M5.Display.light()) {
    // The pinned M5GFX StickS3 driver uses Light_PWM at 256 Hz. Raise its
    // frequency, preserving its channel, resolution, polarity and brightness curve.
    auto* backlight = static_cast<lgfx::Light_PWM*>(M5.Display.light());
    const auto original = backlight->config();
    backlightChannel = original.pwm_channel;
    auto config = original;
    config.freq = 20000;
    backlight->config(config);
    if (!backlight->init(brightness)) {
      // Keep the display usable if the timer cannot be reconfigured.
      backlight->config(original);
      backlight->init(brightness);
    }
  }
  M5.Display.setBrightness(brightness);
}

bool updateBattery() {
  int level = M5.Power.getBatteryLevel();
  if (level > 100) level = 100;
  if (level < -1) level = -1;
  bool charging = M5.Power.isCharging() == m5::Power_Class::is_charging;
  bool changed = controller->battery != level || controller->charging != charging;
  controller->battery = level;
  controller->charging = charging;
  lastBatteryAt = millis();
  return changed;
}

std::string readFile(const char* path) {
  if (!filesystemOk) return {};
  File file = LittleFS.open(path, "r");
  if (!file || file.size() > 65536) return {};
  std::string contents;
  contents.reserve(file.size());
  while (file.available()) contents.push_back(static_cast<char>(file.read()));
  return contents;
}

void draw() {
  screen.render(*controller);
  M5.Display.startWrite();
  M5.Display.pushImage(0, 0, light::Screen::width, light::Screen::height, screen.pixels.data());
  M5.Display.endWrite();
}

// Never print URLs, credentials, request bodies, or arbitrary HTTP responses.
int request(const String& path, const String& body, bool post) {
  HTTPClient http;
  WiFiClient plain;
  WiFiClientSecure secure;
  WiFiClient* client = &plain;
  if (haUrl.compare(0, 8, "https://") == 0) {
    if (!tlsReady) return -1;
    secure.setCACert(ca.c_str());
    secure.setHandshakeTimeout(10);
    client = &secure;
  }
  http.setConnectTimeout(10000);
  http.setTimeout(10000);
  // Redirects are deliberately disabled: do not forward a Bearer token elsewhere.
  if (!http.begin(*client, String(haUrl.c_str()) + path)) return -1;
  http.addHeader("Authorization", String("Bearer ") + token.c_str());
  http.addHeader("Content-Type", "application/json");
  int code = post ? http.POST(body) : http.GET();
  http.end();
  return code;
}

int sendMode(const light::Mode& mode, const std::string& entity) {
  draw();  // Show SENDING before a synchronous network request.
  return request(String("/api/services/light/") + light::service(mode).c_str(),
                 light::requestBody(entity, mode).c_str(), true);
}

void readSettings() {
  JsonDocument doc;
  if (deserializeJson(doc, readFile("/settings.json"))) return;
  for (const char* key : {"ssid", "password", "ha_url", "ha_token"})
    if (!doc[key].is<const char*>()) return;
  ssid = doc["ssid"].as<std::string>();
  password = doc["password"].as<std::string>();
  haUrl = doc["ha_url"].as<std::string>();
  token = doc["ha_token"].as<std::string>();
  while (!haUrl.empty() && haUrl.back() == '/') haUrl.pop_back();
  settingsOk = !ssid.empty() && !token.empty() &&
      (haUrl.compare(0, 7, "http://") == 0 || haUrl.compare(0, 8, "https://") == 0);
  ca = readFile("/ca.pem");
}

void connectNetwork() {
  if (!filesystemOk) { controller->status = "Upload settings"; return; }
  if (!settingsOk) { controller->status = "No settings"; return; }
  WiFi.mode(WIFI_STA);
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED)
      wifiDisconnectReason = info.wifi_sta_disconnected.reason;
  });
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid.c_str(), password.c_str());
  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && uint32_t(millis() - started) < 15000) {
    M5.update();
    delay(25);
  }
  controller->online = WiFi.status() == WL_CONNECTED;
  controller->status = controller->online ? "Ready" : "WiFi fail";
  if (controller->online && haUrl.compare(0, 8, "https://") == 0) {
    if (ca.empty()) { controller->status = "TLS CA missing"; return; }
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    started = millis();
    while (std::time(nullptr) < 1700000000 && uint32_t(millis() - started) < 10000) delay(25);
    tlsReady = std::time(nullptr) >= 1700000000;
    if (!tlsReady) controller->status = "TLS clock error";
  }
}

void status(JsonDocument& doc) {
  doc["kind"] = "status";
  doc["board"] = M5.getBoard() == m5::board_t::board_M5StickS3 ? "StickS3" : "unknown";
  doc["width"] = M5.Display.width();
  doc["height"] = M5.Display.height();
  // Read after initialization, once the hardware duty update has taken effect.
  doc["backlight_pwm_hz"] = backlightChannel >= 0 ? ledcReadFreq(backlightChannel) : 0;
  doc["backlight_brightness"] = M5.Display.getBrightness();
  doc["psram"] = ESP.getPsramSize();
  doc["filesystem"] = filesystemOk;
  doc["settings"] = settingsOk;
  doc["config_valid"] = controller->config.valid;
  doc["online"] = controller->online;
  doc["wifi_status"] = int(WiFi.status());
  doc["wifi_reason"] = uint32_t(wifiDisconnectReason);
  doc["wifi_rssi"] = controller->online ? WiFi.RSSI() : 0;
  doc["selected"] = controller->selected;
  doc["mode_count"] = controller->config.modes.size();
  doc["mode"] = controller->mode().name;
  doc["status"] = controller->status;
  doc["applied"] = controller->appliedText();
  doc["applied_name"] = controller->applied;
  doc["applied_off"] = controller->appliedOff;
  doc["has_applied"] = controller->hasApplied;
  doc["clipped"] = screen.clipped;
  doc["button_a"] = M5.BtnA.isPressed();
  doc["button_b"] = M5.BtnB.isPressed();
  doc["battery"] = controller->battery;
  doc["charging"] = controller->charging;
  auto visible = doc["visible"].to<JsonArray>();
  for (auto& text : screen.visible) visible.add(text);
}

void serialCommand() {
  // Bounded JSON command protocol; there is no shell, evaluator, or settings dump.
  static std::string line;
  static bool overflow = false;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch != '\n') {
      if (line.size() < 128 && !overflow) line.push_back(ch);
      else overflow = true;
      continue;
    }
    JsonDocument command, reply;
    bool valid = !overflow && !deserializeJson(command, line);
    line.clear();
    overflow = false;
    std::string cmd = command["cmd"] | "";
    if (!valid) reply["error"] = "Invalid command";
    else if (cmd == "frame") {
      draw();
      status(reply);
      // Stream RGB565 runs rather than allocate another frame-sized JSON tree.
      // Include the exact state rendered, avoiding a race with battery/Wi-Fi changes.
      Serial.print("{\"kind\":\"frame\",\"width\":135,\"height\":240,\"state\":");
      serializeJson(reply, Serial);
      Serial.print(",\"runs\":[");
      size_t i = 0;
      while (i < screen.pixels.size()) {
        uint16_t color = screen.pixels[i];
        size_t end = i + 1;
        while (end < screen.pixels.size() && screen.pixels[end] == color) ++end;
        if (i) Serial.print(',');
        Serial.printf("%u,%u", unsigned(end - i), unsigned(color));
        i = end;
      }
      Serial.println("]}");
      break;
    } else if (cmd == "wifi_scan") {
      bool reconnect = !controller->online;
      if (reconnect) {
        WiFi.setAutoReconnect(false);
        WiFi.disconnect(false, false);
        delay(100);
      }
      int count = WiFi.scanNetworks(false, true);
      reply["kind"] = "wifi_scan";
      reply["network_count"] = count;
      reply["target_seen"] = false;
      for (int i = 0; i < count; ++i) if (WiFi.SSID(i) == ssid.c_str()) {
        reply["target_seen"] = true;
        reply["rssi"] = WiFi.RSSI(i);
        reply["channel"] = WiFi.channel(i);
        break;
      }
      WiFi.scanDelete();
      if (reconnect) {
        WiFi.setAutoReconnect(true);
        WiFi.begin(ssid.c_str(), password.c_str());
        lastWifiRetryAt = millis();
      }
    } else if (cmd == "status" || cmd == "next" || cmd == "apply" || cmd == "ha_check") {
      if (cmd == "next") controller->next();
      if (cmd == "apply") controller->apply(sendMode);
      draw();
      status(reply);
      if (cmd == "ha_check") {
        int code = controller->online && settingsOk ? request("/api/", "", false) : -1;
        reply["ha_http"] = code;
        int entityCode = code == 200 ? request(String("/api/states/") + controller->config.entity.c_str(), "", false) : -1;
        reply["entity_http"] = entityCode;
      }
    } else reply["error"] = "Unknown command";
    serializeJson(reply, Serial);
    Serial.println();
    break;
  }
}
}  // namespace

void setup() {
  auto cfg = M5.config();
  cfg.internal_imu = false;
  cfg.internal_rtc = false;
  cfg.internal_spk = false;
  cfg.internal_mic = false;
  M5.begin(cfg);
  Serial.begin(115200);  // Standalone boot never waits for a monitor.
  M5.Display.setRotation(0);
  configureBacklight();
  // pixels[] stores native-endian RGB565; M5GFX defaults to wire-order data.
  M5.Display.setSwapBytes(true);
  filesystemOk = LittleFS.begin(false);  // Never silently erase private settings.
  controller.reset(new light::Controller(light::parseConfig(readFile("/config.json"))));
  updateBattery();
  readSettings();
  controller->hasToken = settingsOk;
  draw();
  connectNetwork();
  if (!controller->config.valid) controller->status = "Config error";
  draw();
}

void loop() {
  M5.update();
  bool wasOnline = controller->online;
  controller->online = WiFi.status() == WL_CONNECTED;
  if (settingsOk && !controller->online && uint32_t(millis() - lastWifiRetryAt) >= 30000) {
    lastWifiRetryAt = millis();
    WiFi.reconnect();
  }
  auto selection = controller->selected;
  auto previousStatus = controller->status;
  bool batteryChanged = uint32_t(millis() - lastBatteryAt) >= 15000 && updateBattery();
  bool inputAccepted = controller->buttons(millis(), M5.BtnA.isPressed(), M5.BtnB.isPressed(), sendMode);
  // Even reapplying the same mode must replace the intermediate SENDING frame.
  if (inputAccepted || batteryChanged || wasOnline != controller->online || selection != controller->selected || previousStatus != controller->status) draw();
  serialCommand();
  delay(10);
}
#endif
