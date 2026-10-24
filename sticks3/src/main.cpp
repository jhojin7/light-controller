// SPDX-License-Identifier: MIT
#ifndef STICKS3_DIAGNOSTIC
#include <M5Unified.h>
#include <lgfx/v1/platforms/esp32/Light_PWM.hpp>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <esp_sleep.h>
#include <driver/rtc_io.h>
#include <algorithm>
#include <memory>
#include "controller.h"
#include "interaction.h"
#include "network.h"
#include "screen.h"
#include "sleep.h"

namespace {
std::unique_ptr<light::Controller> controller;
std::unique_ptr<light::Interaction> interaction;
light::Screen screen;
light::Network network;
light::SleepHardware sleepHardware;
std::string ssid, password, haUrl, token, ca;
bool filesystemOk = false, settingsOk = false;
uint32_t lastBatteryAt = 0;
int backlightChannel = -1;
RTC_DATA_ATTR light::RetainedSelection retained;
RTC_DATA_ATTR uint32_t testResumeSeconds = 0;
uint32_t maintenanceAt = 0, maintenanceMs = 0, testWakeSeconds = 0;
bool syntheticA = false, syntheticB = false, applyReply = false, checkReply = false, scanReply = false;
uint32_t syntheticAt = 0;

bool maintenance() { return maintenanceMs && uint32_t(millis() - maintenanceAt) < maintenanceMs; }
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
  screen.render(*controller, interaction->holdProgress());
  M5.Display.startWrite();
  M5.Display.pushImage(0, 0, light::Screen::width, light::Screen::height, screen.pixels.data());
  M5.Display.endWrite();
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
  doc["view"] = light::Interaction::viewName(interaction->view());
  doc["hold_progress"] = interaction->holdProgress();
  doc["sleep_queued"] = interaction->sleepQueued();
  doc["motion_ready"] = sleepHardware.motionReady();
  doc["motion_error"] = sleepHardware.error();
  doc["motion_power"] = M5.In_I2C.readRegister8(0x68, 0x7d, 400000);
  doc["motion_irq"] = sleepHardware.irqActive();
  doc["wake_cause"] = unsigned(esp_sleep_get_wakeup_cause());
  doc["wake_pins"] = esp_sleep_get_ext1_wakeup_status();
  doc["network_busy"] = network.busy();
  doc["maintenance"] = maintenance();
  auto visible = doc["visible"].to<JsonArray>();
  for (auto& text : screen.visible) visible.add(text);
}

void replyStatus() {
  JsonDocument reply; status(reply); serializeJson(reply, Serial); Serial.println();
}

void serialCommand() {
  static std::string line;
  static bool overflow = false;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch != '\n') {
      if (line.size() < 192 && !overflow) line.push_back(ch); else overflow = true;
      continue;
    }
    JsonDocument command, reply;
    bool valid = !overflow && !deserializeJson(command, line);
    line.clear(); overflow = false;
    std::string cmd = command["cmd"] | "";
    if (!valid) reply["error"] = "Invalid command";
    else if (cmd == "frame") {
      draw(); status(reply);
      Serial.print("{\"kind\":\"frame\",\"width\":135,\"height\":240,\"state\":");
      serializeJson(reply, Serial); Serial.print(",\"runs\":[");
      size_t i = 0;
      while (i < screen.pixels.size()) {
        uint16_t color = screen.pixels[i]; size_t end = i + 1;
        while (end < screen.pixels.size() && screen.pixels[end] == color) ++end;
        if (i) Serial.print(',');
        Serial.printf("%u,%u", unsigned(end - i), unsigned(color)); i = end;
      }
      Serial.println("]}"); break;
    } else if (cmd == "maintenance") {
      // Explicit USB test lease, never enabled by normal boot or status polling.
      maintenanceAt = millis();
      maintenanceMs = std::min(120u, command["seconds"] | 60u) * 1000;
      status(reply);
    } else if (cmd == "button" && maintenance()) {
      syntheticA = command["a"] | false; syntheticB = command["b"] | false;
      syntheticAt = millis(); status(reply);
    } else if (cmd == "sleep_test" && maintenance()) {
      testWakeSeconds = std::min(60u, std::max(1u, command["seconds"] | 2u));
      testResumeSeconds = 60;
      interaction->sleep(); status(reply);
    } else if (cmd == "wifi_scan") {
      if (network.busy() || scanReply) reply["error"] = "Busy";
      else {
        WiFi.scanNetworks(true, true);
        scanReply = true; break;
      }
    } else if (cmd == "status" || cmd == "next" || cmd == "apply" || cmd == "ha_check") {
      if (cmd == "next") interaction->next(millis());
      if (cmd == "apply") {
        if (network.busy() || interaction->busy() || applyReply) reply["error"] = "Busy";
        else {
          interaction->apply(millis()); draw();
          if (interaction->busy()) { applyReply = true; break; }
        }
      }
      if (cmd == "ha_check") {
        if (network.check(UINT32_MAX, controller->config.entity)) { checkReply = true; break; }
        reply["error"] = "Network unavailable or busy";
      }
      if (!reply["error"].is<const char*>()) { draw(); status(reply); }
    } else reply["error"] = "Unknown command";
    serializeJson(reply, Serial); Serial.println(); break;
  }
}
}  // namespace

void setup() {
  rtc_gpio_deinit(GPIO_NUM_12); rtc_gpio_deinit(GPIO_NUM_13);
  auto cfg = M5.config();
  cfg.internal_imu = false; cfg.internal_rtc = false;
  cfg.internal_spk = false; cfg.internal_mic = false;
  M5.begin(cfg);
  Serial.begin(115200);
  M5.Display.setRotation(0); configureBacklight();
  M5.Display.setSwapBytes(true);
  filesystemOk = LittleFS.begin(false);
  controller.reset(new light::Controller(light::parseConfig(readFile("/config.json"))));
  interaction.reset(new light::Interaction(*controller));
  readSettings(); controller->hasToken = settingsOk;
  interaction->restore(retained);
  M5.update(); interaction->wake(millis(), digitalRead(11) == LOW, digitalRead(12) == LOW);
  updateBattery(); draw();
  // Association begins before sensor bring-up. Neither waits for the router.
  if (settingsOk && !network.begin(ssid, password, haUrl, token, ca)) controller->status = "Network error";
  sleepHardware.begin();
  if (!sleepHardware.motionReady()) controller->status = "Motion error";
  // The wake-screen deadline starts after hardware setup, with input already live.
  interaction->wake(millis(), digitalRead(11) == LOW, digitalRead(12) == LOW);
  if (!sleepHardware.motionReady()) controller->status = "Motion error";
  if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER && testResumeSeconds) {
    maintenanceAt = millis(); maintenanceMs = std::min(120u, testResumeSeconds) * 1000;
  }
  testResumeSeconds = 0;
  draw();
}

void loop() {
  M5.update(); uint32_t now = millis();
  network.update(now);
  bool wasOnline = controller->online;
  controller->online = network.online();
  if (maintenance()) interaction->keepAwake(now);
  if (uint32_t(now - syntheticAt) > 2000) syntheticA = syntheticB = false;
  bool changed = interaction->update(now, digitalRead(11) == LOW || syntheticA, digitalRead(12) == LOW || syntheticB);
  if (auto job = interaction->takeRequest()) {
    if (!network.send(*job)) interaction->complete(job->id, -1, now);
    changed = true;
  }
  light::NetworkResult result;
  while (network.poll(result)) {
    if (result.check) {
      if (checkReply) {
        JsonDocument reply; status(reply);
        reply["ha_http"] = result.code; reply["entity_http"] = result.entityCode;
        serializeJson(reply, Serial); Serial.println(); checkReply = false;
      }
    } else {
      interaction->complete(result.id, result.code, now); changed = true;
    }
  }
  if (scanReply && WiFi.scanComplete() != WIFI_SCAN_RUNNING) {
    int count = WiFi.scanComplete();
    JsonDocument reply;
    reply["kind"] = "wifi_scan"; reply["network_count"] = count;
    reply["target_seen"] = false;
    for (int i = 0; i < count; ++i) if (WiFi.SSID(i) == ssid.c_str()) {
      reply["target_seen"] = true; reply["rssi"] = WiFi.RSSI(i);
      reply["channel"] = WiFi.channel(i); break;
    }
    WiFi.scanDelete(); serializeJson(reply, Serial); Serial.println(); scanReply = false;
  }
  if (applyReply && !interaction->busy()) { draw(); replyStatus(); applyReply = false; }
  if (uint32_t(now - lastBatteryAt) >= 15000 && updateBattery()) changed = true;
  if (changed || wasOnline != controller->online) draw();
  serialCommand();
  if (interaction->view() == light::View::Sleep && !network.busy()) {
    network.stop(); controller->online = false;
    if (sleepHardware.prepare(now, !M5.BtnA.isPressed() && !M5.BtnB.isPressed() && !syntheticA && !syntheticB)) {
      retained = interaction->retain();
      Serial.flush(); sleepHardware.enter(testWakeSeconds);
    }
  }
  delay(10);
}
#endif
