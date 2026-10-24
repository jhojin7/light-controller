// SPDX-License-Identifier: MIT
#include "controller.h"
#include <ArduinoJson.h>
#include <cctype>
#include <utility>

namespace light {
Config defaultConfig() {
  return {"light.example", {{"DAY", false, 255, 5000, ""},
                            {"EVENING", false, 128, 2700, ""},
                            {"SLEEP", false, 25, 2200, ""},
                            {"OFF", true, 0, 0, ""}}, true};
}

static Config errorConfig() {
  return {"light.example", {{"ERROR", false, 0, 0, ""}}, false};
}

Config parseConfig(const std::string& text) {
  JsonDocument doc;
  // Missing/unreadable/malformed files use the same defaults as the Feather.
  if (text.empty() || deserializeJson(doc, text)) return defaultConfig();
  if (!doc.is<JsonObject>()) return errorConfig();
  auto entity = doc["entity_id"];
  if (!entity.is<const char*>()) return errorConfig();
  Config config{entity.as<std::string>(), {}, true};
  if (config.entity.compare(0, 6, "light.") != 0 || config.entity.size() <= 6 ||
      !doc["modes"].is<JsonArray>() || doc["modes"].size() == 0) return errorConfig();
  for (JsonVariant item : doc["modes"].as<JsonArray>()) {
    if (!item.is<JsonObject>() || !item["name"].is<const char*>()) return errorConfig();
    Mode mode;
    mode.name = item["name"].as<std::string>();
    if (mode.name.find_first_not_of(" \t\r\n") == std::string::npos) return errorConfig();
    std::string action = item["action"] | "on";
    if (action != "on" && action != "off") return errorConfig();
    mode.off = action == "off";
    if (!mode.off) {
      if (!item["brightness"].is<int>() || !item["kelvin"].is<int>()) return errorConfig();
      mode.brightness = item["brightness"].as<int>();
      mode.kelvin = item["kelvin"].as<int>();
      if (mode.brightness < 0 || mode.brightness > 255 || mode.kelvin <= 0) return errorConfig();
    }
    mode.icon = item["icon"] | "";
    config.modes.push_back(std::move(mode));
  }
  return config;
}

std::string upper(std::string text) {
  for (char& ch : text) ch = static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
  return text;
}

std::string modeIcon(const Mode& mode) {
  if (mode.off) return "off";
  if (mode.icon == "sun" || mode.icon == "sunset" || mode.icon == "moon" || mode.icon == "off")
    return mode.icon;
  auto name = upper(mode.name);
  for (auto word : {"SLEEP", "NIGHT", "BED"})
    if (name.find(word) != std::string::npos) return "moon";
  for (auto word : {"EVENING", "DUSK", "SUNSET"})
    if (name.find(word) != std::string::npos) return "sunset";
  for (auto word : {"DAY", "MORNING"})
    if (name.find(word) != std::string::npos) return "sun";
  return mode.kelvin >= 4000 ? "sun" : mode.kelvin >= 2500 ? "sunset" : "moon";
}

uint32_t modeColor(const Mode& mode) {
  auto icon = modeIcon(mode);
  return icon == "off" ? 0xAAB7C9 : icon == "sun" ? 0xFFE49C :
         icon == "sunset" ? 0xFFB580 : 0xB6BEFF;
}

std::string service(const Mode& mode) { return mode.off ? "turn_off" : "turn_on"; }

std::string requestBody(const std::string& entity, const Mode& mode) {
  JsonDocument doc;
  doc["entity_id"] = entity;
  if (!mode.off) {
    doc["brightness"] = mode.brightness;
    doc["color_temp_kelvin"] = mode.kelvin;
  }
  std::string result;
  serializeJson(doc, result);
  return result;
}

Controller::Controller(Config config) : config(std::move(config)) {
  if (this->config.modes.empty()) this->config = errorConfig();
}

void Controller::next() {
  selected = (selected + 1) % config.modes.size();
  status = "Selected";
}

void Controller::apply(const Send& send) {
  if (!config.valid) { status = "Config error"; return; }
  if (!online) { status = "No WiFi"; return; }
  if (!hasToken) { status = "No token"; return; }
  status = "Sending...";
  int code = send(mode(), config.entity);
  recordResult(mode(), code);
}

void Controller::recordResult(const Mode& mode, int code) {
  if (code == 200 || code == 201) {
    applied = mode.name;
    appliedOff = mode.off;
    hasApplied = true;
    status = "OK";
  } else {
    status = code > 0 ? "Err " + std::to_string(code) : "Failed";
  }
}

std::string Controller::appliedText() const {
  return hasApplied && appliedOff ? "LIGHT OFF" : "ON: " + upper(applied);
}
}  // namespace light
