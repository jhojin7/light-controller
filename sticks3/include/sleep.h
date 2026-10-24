// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>

namespace light {
class SleepHardware {
 public:
  bool begin();
  // Non-blocking preparation: do not cut power while keys/IRQ remain asserted.
  // Keeps the ESP32 in light sleep if motion continues; settles into deep sleep
  // when quiet. Timer wakes only serve this bounded settling phase or tests.
  bool prepare(uint32_t now, bool keysReleased);
  void enter(uint32_t testWakeSeconds = 0);
  bool motionReady() const { return ready_; }
  int error() const { return error_; }
  bool irqActive() const;
  void cancel();
 private:
  bool ready_ = false, armed_ = false;
  uint32_t armedAt_ = 0;
  int error_ = 0;
};
}  // namespace light
