// SPDX-License-Identifier: MIT
#include "interaction.h"
#include <algorithm>

namespace light {
int Interaction::Button::update(uint32_t now, bool down) {
  if (raw != down) { raw = down; changed = now; }
  if (raw == stable || uint32_t(now - changed) < debounceMs) return 0;
  stable = raw;
  if (blocked) { if (!stable) blocked = false; return 0; }
  return stable ? 1 : -1;
}

const char* Interaction::viewName(View v) {
  switch (v) {
    case View::Preview: return "preview";
    case View::Browse: return "browse";
    case View::Applying: return "applying";
    case View::Success: return "success";
    case View::Error: return "error";
    case View::Sleep: return "sleep";
  }
  return "unknown";
}

void Interaction::wake(uint32_t now, bool a, bool b) {
  a_ = {a, a, a, now}; b_ = {b, b, b, now};
  consumed_ = false; sleepQueued_ = false; progress_ = 0;
  request_.reset(); active_.reset();
  enter(View::Preview, now);
  c.status = c.config.valid ? "Ready" : "Config error";
}

void Interaction::enter(View view, uint32_t now) { view_ = view; since_ = now; }

void Interaction::next(uint32_t now) {
  if (busy() || view_ == View::Sleep) return;
  c.next(); enter(View::Browse, now);
}

void Interaction::apply(uint32_t now) {
  if (busy() || view_ == View::Sleep) return;
  consumed_ = true; progress_ = 0;
  if (!c.config.valid || !c.hasToken) {
    c.status = !c.config.valid ? "Config error" : "No settings";
    enter(View::Error, now);
    return;
  }
  active_ = ApplyRequest{++sequence_, c.mode(), c.config.entity};
  request_ = active_;
  c.status = "Sending...";
  enter(View::Applying, now);
}

void Interaction::sleep() {
  progress_ = 0;
  if (busy()) { sleepQueued_ = true; return; }
  view_ = View::Sleep; c.status = "Sleeping";
  request_.reset(); active_.reset();
}

std::optional<ApplyRequest> Interaction::takeRequest() {
  auto result = request_; request_.reset(); return result;
}

void Interaction::complete(uint32_t id, int code, uint32_t now) {
  if (!busy() || !active_ || active_->id != id) return;
  c.recordResult(active_->mode, code);
  active_.reset(); request_.reset();
  enter(code == 200 || code == 201 ? View::Success : View::Error, now);
  if (sleepQueued_) sleep();
}

bool Interaction::update(uint32_t now, bool a, bool b) {
  auto before = view_; auto status = c.status; auto selected = c.selected;
  auto progress = progress_;
  int edgeA = a_.update(now, a), edgeB = b_.update(now, b);
  if (view_ == View::Sleep) return false;
  if (edgeB == 1) sleep();
  // B wins a simultaneous press. Holding either wake key does not count as input.
  if (view_ != View::Sleep && !sleepQueued_ && !b_.raw && !b_.stable) {
    if (busy()) {
      if (a_.raw || a_.stable) consumed_ = true;
    } else {
      if (edgeA == 1) {
        consumed_ = false; pressedAt_ = now;
        enter(View::Browse, now); c.status = "Selected";
      }
      if (a_.stable && !a_.blocked && !consumed_) {
        uint32_t held = uint32_t(now - pressedAt_);
        progress_ = std::min(100u, unsigned(held * 100 / holdMs));
        if (held >= holdMs) apply(now);
      }
      if (edgeA == -1) {
        if (!consumed_) next(now);
        consumed_ = true; progress_ = 0;
      }
    }
  }
  // Prevent release of a press suppressed by B from becoming a later tap.
  if ((b_.raw || b_.stable) && (a_.raw || a_.stable)) consumed_ = true;
  uint32_t elapsed = uint32_t(now - since_);
  if (busy() && elapsed >= applyMs && active_) complete(active_->id, -1, now);
  else if (!a_.raw && !a_.stable && !b_.raw && !b_.stable) {
    uint32_t timeout = view_ == View::Preview ? previewMs :
        view_ == View::Browse ? browseMs : view_ == View::Success ? successMs : errorMs;
    if (!busy() && view_ != View::Sleep && elapsed >= timeout) sleep();
  }
  return before != view_ || status != c.status || selected != c.selected || progress / 5 != progress_ / 5;
}

uint32_t Interaction::configHash() const {
  uint32_t hash = 2166136261u;
  auto add = [&](const std::string& text) {
    for (unsigned char ch : text) hash = (hash ^ ch) * 16777619u;
    hash = (hash ^ 0xff) * 16777619u;
  };
  add(c.config.entity);
  for (const auto& m : c.config.modes) {
    add(m.name); add(std::to_string(m.brightness)); add(std::to_string(m.kelvin));
    add(m.off ? "off" : "on"); add(m.icon);
  }
  return hash;
}

RetainedSelection Interaction::retain() const {
  RetainedSelection saved;
  saved.magic = 0x4c435301; saved.config = configHash(); saved.selected = c.selected;
  if (c.hasApplied) for (size_t i = 0; i < c.config.modes.size(); ++i)
    if (c.config.modes[i].name == c.applied && c.config.modes[i].off == c.appliedOff) {
      saved.applied = i; break;
    }
  saved.checksum = saved.magic ^ saved.config ^ saved.selected ^ saved.applied ^ 0x193af176;
  return saved;
}

bool Interaction::restore(const RetainedSelection& saved) {
  if (saved.magic != 0x4c435301 || saved.config != configHash() ||
      saved.selected >= c.config.modes.size() ||
      (saved.applied != UINT32_MAX && saved.applied >= c.config.modes.size()) ||
      saved.checksum != (saved.magic ^ saved.config ^ saved.selected ^ saved.applied ^ 0x193af176)) return false;
  c.selected = saved.selected;
  if (saved.applied != UINT32_MAX) {
    c.applied = c.config.modes[saved.applied].name;
    c.appliedOff = c.config.modes[saved.applied].off; c.hasApplied = true;
  }
  return true;
}
}  // namespace light
