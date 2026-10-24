// SPDX-License-Identifier: MIT
#pragma once
#include "interaction.h"
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

namespace light {
struct NetworkResult { uint32_t id; int code; int entityCode; bool check; };
class Network {
 public:
  bool begin(const std::string& ssid, const std::string& password,
             const std::string& url, const std::string& token, const std::string& ca);
  void update(uint32_t now);
  bool send(const ApplyRequest& request);
  bool check(uint32_t id, const std::string& entity);
  bool poll(NetworkResult& result);
  bool online() const;
  bool busy() const { return busy_.load(); }
  void stop();
 private:
  struct Work { ApplyRequest request; bool check = false; };
  std::string url_, token_, ca_;
  QueueHandle_t work_ = nullptr, results_ = nullptr;
  std::atomic<bool> busy_{false};
  bool enabled_ = false, clockStarted_ = false;
  uint32_t lastRetry_ = 0;
  static void worker(void* self);
  int request(const std::string& path, const std::string& body, bool post);
};
}  // namespace light
