// SPDX-License-Identifier: MIT
#ifndef STICKS3_DIAGNOSTIC
#include "network.h"
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ctime>
#include <new>

namespace light {
bool Network::begin(const std::string& ssid, const std::string& password,
                    const std::string& url, const std::string& token, const std::string& ca) {
  url_ = url; token_ = token; ca_ = ca;
  work_ = xQueueCreate(1, sizeof(Work*));
  results_ = xQueueCreate(2, sizeof(NetworkResult));
  if (!work_ || !results_ || xTaskCreate(worker, "ha_request", 12288, this, 1, nullptr) != pdPASS) {
    if (work_) vQueueDelete(work_);
    if (results_) vQueueDelete(results_);
    work_ = nullptr; results_ = nullptr;
    return false;
  }
  enabled_ = true;
  WiFi.mode(WIFI_STA);
  // Awake sessions are brief. Keep the radio responsive during browsing/apply;
  // the entire Wi-Fi driver is stopped for the long idle periods in deep sleep.
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid.c_str(), password.c_str());
  lastRetry_ = millis();
  return true;
}

bool Network::online() const { return enabled_ && WiFi.status() == WL_CONNECTED; }

void Network::update(uint32_t now) {
  if (!enabled_) return;
  if (online() && !clockStarted_ && url_.compare(0, 8, "https://") == 0) {
    clockStarted_ = true;
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  }
  if (!online() && uint32_t(now - lastRetry_) >= 10000) {
    lastRetry_ = now; WiFi.reconnect();
  }
}

bool Network::send(const ApplyRequest& request) {
  if (!enabled_ || busy_.exchange(true)) return false;
  auto* work = new (std::nothrow) Work{request, false};
  if (work && xQueueSend(work_, &work, 0) == pdTRUE) return true;
  delete work; busy_ = false; return false;
}

bool Network::check(uint32_t id, const std::string& entity) {
  if (!enabled_ || busy_.exchange(true)) return false;
  auto* work = new (std::nothrow) Work{{id, {}, entity}, true};
  if (work && xQueueSend(work_, &work, 0) == pdTRUE) return true;
  delete work; busy_ = false; return false;
}

bool Network::poll(NetworkResult& result) {
  return results_ && xQueueReceive(results_, &result, 0) == pdTRUE;
}

void Network::stop() {
  if (busy() || !enabled_) return;
  enabled_ = false;
  WiFi.setAutoReconnect(false);
  WiFi.disconnect(true, false);
  WiFi.mode(WIFI_OFF);
}

int Network::request(const std::string& path, const std::string& body, bool post) {
  // HTTPClient borrows the socket and may access it in its destructor even
  // after end(). Declare it last so it is destroyed before either socket.
  WiFiClient plain;
  WiFiClientSecure secure;
  HTTPClient http;
  WiFiClient* client = &plain;
  if (url_.compare(0, 8, "https://") == 0) {
    if (ca_.empty() || std::time(nullptr) < 1700000000) return -1;
    secure.setCACert(ca_.c_str()); secure.setHandshakeTimeout(5); client = &secure;
  }
  http.setConnectTimeout(5000); http.setTimeout(10000);
  http.setReuse(false);  // Each job owns a fresh socket; release it after use.
  if (!http.begin(*client, String((url_ + path).c_str()))) return -1;
  http.addHeader("Authorization", String("Bearer ") + token_.c_str());
  http.addHeader("Content-Type", "application/json");
  // No redirects: never forward a bearer token to another destination.
  int code = post ? http.POST(String(body.c_str())) : http.GET();
  http.end(); return code;
}

void Network::worker(void* context) {
  auto& self = *static_cast<Network*>(context);
  Work* work;
  for (;;) {
    if (xQueueReceive(self.work_, &work, portMAX_DELAY) != pdTRUE) continue;
    uint32_t started = millis();
    while ((!self.online() || (self.url_.compare(0, 8, "https://") == 0 && std::time(nullptr) < 1700000000)) &&
           uint32_t(millis() - started) < 10000) vTaskDelay(pdMS_TO_TICKS(20));
    NetworkResult result{work->request.id, -1, -1, work->check};
    if (self.online()) {
      if (work->check) {
        result.code = self.request("/api/", "", false);
        if (result.code == 200) result.entityCode = self.request("/api/states/" + work->request.entity, "", false);
      } else {
        result.code = self.request("/api/services/light/" + service(work->request.mode),
                                  requestBody(work->request.entity, work->request.mode), true);
      }
    }
    delete work;
    self.busy_ = false;
    xQueueSend(self.results_, &result, portMAX_DELAY);
  }
}
}  // namespace light
#endif
