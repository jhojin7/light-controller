// SPDX-License-Identifier: MIT
#pragma once
#include "controller.h"
#include <optional>

namespace light {
enum class View { Preview, Browse, Applying, Success, Error, Sleep };
struct ApplyRequest {
  uint32_t id;
  Mode mode;
  std::string entity;
};
struct RetainedSelection {
  uint32_t magic = 0;
  uint32_t config = 0;
  uint32_t selected = 0;
  uint32_t applied = UINT32_MAX;
  uint32_t checksum = 0;
};

// Hardware-independent interaction contract. All times are unsigned millis;
// only the hardware adapter performs networking or actually enters sleep.
class Interaction {
 public:
  static constexpr uint32_t debounceMs = 30, holdMs = 700;
  static constexpr uint32_t previewMs = 3000, browseMs = 15000;
  static constexpr uint32_t successMs = 3000, errorMs = 8000, applyMs = 30000;
  explicit Interaction(Controller& controller) : c(controller) {}
  void wake(uint32_t now, bool a = false, bool b = false);
  bool update(uint32_t now, bool a, bool b);
  void next(uint32_t now);
  void apply(uint32_t now);
  void sleep();
  void keepAwake(uint32_t now) { if (!busy()) since_ = now; }
  void complete(uint32_t id, int code, uint32_t now);
  std::optional<ApplyRequest> takeRequest();
  View view() const { return view_; }
  bool busy() const { return view_ == View::Applying; }
  bool sleepQueued() const { return sleepQueued_; }
  unsigned holdProgress() const { return progress_; }
  RetainedSelection retain() const;
  bool restore(const RetainedSelection& saved);
  static const char* viewName(View view);
 private:
  struct Button {
    bool raw = false, stable = false, blocked = false;
    uint32_t changed = 0;
    int update(uint32_t now, bool down);
  };
  Controller& c;
  Button a_, b_;
  View view_ = View::Preview;
  uint32_t since_ = 0, pressedAt_ = 0, sequence_ = 0;
  bool consumed_ = false, sleepQueued_ = false;
  unsigned progress_ = 0;
  std::optional<ApplyRequest> request_, active_;
  void enter(View view, uint32_t now);
  uint32_t configHash() const;
};
}  // namespace light
