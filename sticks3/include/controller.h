// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace light {
struct Mode {
  std::string name;
  bool off = false;
  int brightness = 0;
  int kelvin = 0;
  std::string icon;
};
struct Config {
  std::string entity;
  std::vector<Mode> modes;
  bool valid = true;
};
Config defaultConfig();
Config parseConfig(const std::string& json);
std::string requestBody(const std::string& entity, const Mode& mode);
std::string service(const Mode& mode);
std::string modeIcon(const Mode& mode);
uint32_t modeColor(const Mode& mode);
std::string upper(std::string text);

class Controller {
 public:
  explicit Controller(Config config);
  Config config;
  size_t selected = 0;
  std::string applied = "--";
  bool appliedOff = false;
  bool hasApplied = false;
  bool online = false;
  bool hasToken = false;
  int battery = -1;
  bool charging = false;
  std::string status = "Connecting";
  const Mode& mode() const { return config.modes[selected]; }
  using Send = std::function<int(const Mode&, const std::string&)>;
  bool buttons(uint32_t now, bool cycle, bool confirm, const Send& send);
  void next();
  void apply(const Send& send);
  std::string appliedText() const;
 private:
  uint32_t lastCycle_ = 0;
  uint32_t lastConfirm_ = 0;
};
}  // namespace light
