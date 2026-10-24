// SPDX-License-Identifier: MIT
#include "controller.h"
#include "screen.h"
#include <ArduinoJson.h>
#include <fstream>
#include <iostream>

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    JsonDocument spec;
    if (deserializeJson(spec, line)) return 2;
    std::string configText;
    if (spec["config"].is<JsonObject>()) serializeJson(spec["config"], configText);
    else if (spec["config"] == "malformed") configText = "{";
    light::Controller c(light::parseConfig(configText));
    c.online = !spec["missing_wifi"].as<bool>() && !spec["wifi_fail"].as<bool>();
    if (spec["online"].is<bool>()) c.online = spec["online"].as<bool>();
    c.hasToken = !spec["missing_token"].as<bool>();
    c.battery = spec["battery"] | -1;
    c.charging = spec["charging"] | false;
    c.status = c.online ? "Ready" : "WiFi fail";
    if (spec["has_applied"] == true) {
      c.hasApplied = true;
      c.applied = spec["applied_name"].as<std::string>();
      c.appliedOff = spec["applied_off"] | false;
    }
    JsonDocument result;
    auto posts = result["posts"].to<JsonArray>();
    size_t outcome = 0;
    auto send = [&](const light::Mode& mode, const std::string& entity) {
      auto post = posts.add<JsonObject>();
      post["service"] = light::service(mode);
      JsonDocument body;
      deserializeJson(body, light::requestBody(entity, mode));
      post["body"].set(body);
      auto value = spec["outcomes"][outcome++];
      return value.is<int>() ? value.as<int>() : value == "raise" ? -1 : 200;
    };
    light::Screen screen;
    auto frames = result["frames"].to<JsonArray>();
    for (JsonVariant frame : spec["frames"].as<JsonArray>()) {
      bool inputAccepted = frame["cycle"] | false;
      if (inputAccepted) c.next();
      if (frame["confirm"] | false) { c.apply(send); inputAccepted = true; }
      if (frame["render_status"].is<const char*>()) c.status = frame["render_status"].as<std::string>();
      screen.render(c);
      auto output = frames.add<JsonObject>();
      auto visible = output["visible"].to<JsonArray>();
      for (auto& text : screen.visible) visible.add(text);
      output["status"] = c.status;
      output["selected"] = c.selected;
      output["clipped"] = screen.clipped;
      output["icon"] = light::modeIcon(c.mode());
      output["redraw"] = inputAccepted;
    }
    if (spec["dump"].is<const char*>()) {
      std::ofstream file(spec["dump"].as<const char*>(), std::ios::binary);
      file.write(reinterpret_cast<const char*>(screen.pixels.data()), screen.pixels.size() * 2);
    }
    serializeJson(result, std::cout);
    std::cout << std::endl;
  }
}
