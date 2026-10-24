// SPDX-License-Identifier: MIT
#include "interaction.h"
#include "screen.h"
#include <cstdlib>
#include <iostream>

using namespace light;
static unsigned checks = 0;
static void expect(bool ok, const char* message) {
  ++checks;
  if (!ok) { std::cerr << "FAIL " << message << '\n'; std::exit(1); }
}
struct Rig {
  Controller c{defaultConfig()};
  Interaction ui{c};
  Rig() { c.hasToken = true; ui.wake(0); }
  void tap(uint32_t at) {
    ui.update(at, true, false); ui.update(at + 30, true, false);
    ui.update(at + 100, false, false); ui.update(at + 130, false, false);
  }
  ApplyRequest hold(uint32_t at) {
    ui.update(at, true, false); ui.update(at + 30, true, false);
    ui.update(at + 729, true, false);
    expect(!ui.takeRequest(), "hold below threshold sends nothing");
    ui.update(at + 730, true, false);
    auto request = ui.takeRequest();
    expect(bool(request), "hold commits a request at threshold");
    return *request;
  }
  void release(uint32_t at) { ui.update(at, false, false); ui.update(at + 30, false, false); }
};

int main() {
  {
    Rig r;
    r.ui.update(2999, false, false);
    expect(r.ui.view() == View::Preview, "wake screen visible until 3 seconds");
    r.ui.update(3000, false, false);
    expect(r.ui.view() == View::Sleep, "unused wake sleeps at 3 seconds, even offline");
    expect(!r.ui.takeRequest(), "wake and sleep send no light command");
  }
  {
    Rig r; r.tap(100); r.tap(300);
    expect(r.c.selected == 2, "two quick taps advance twice");
    r.tap(500); expect(r.c.mode().off, "OFF remains browsable");
    r.tap(700); expect(r.c.selected == 0, "selection wraps");
    r.ui.update(15829, false, false);
    expect(r.ui.view() == View::Browse, "A interaction grants 15 seconds");
    r.ui.update(15830, false, false);
    expect(r.ui.view() == View::Sleep, "browse deadline expires");
  }
  {
    Rig r;
    r.ui.update(100, true, false); r.ui.update(110, false, false);
    r.ui.update(120, true, false); r.ui.update(130, false, false);
    r.ui.update(200, false, false);
    expect(r.c.selected == 0 && !r.ui.takeRequest(), "switch bounce is not a tap or hold");
  }
  {
    Rig r; auto job = r.hold(100);
    expect(r.c.selected == 0 && job.mode.name == "DAY", "hold applies displayed mode without cycling");
    r.ui.update(2000, true, false);
    expect(!r.ui.takeRequest(), "held A never repeats apply");
    r.ui.complete(job.id, 200, 2100);
    r.release(2200);
    expect(r.c.selected == 0 && r.c.applied == "DAY", "release after hold never cycles");
    expect(r.ui.view() == View::Success, "successful request shows confirmation");
    r.ui.update(5099, false, false);
    expect(r.ui.view() == View::Success, "success remains visible for 3 seconds");
    r.ui.update(5100, false, false);
    expect(r.ui.view() == View::Sleep, "success expires after 3 seconds");
  }
  {
    Rig r; r.ui.update(2990, true, false); r.ui.update(3000, true, false);
    expect(r.ui.view() != View::Sleep, "A press near timeout is not interrupted");
    r.ui.update(3020, true, false); r.ui.update(3720, true, false);
    expect(bool(r.ui.takeRequest()), "hold started near wake deadline still applies");
  }
  {
    Rig r; r.ui.wake(0, false, true);
    r.ui.update(1000, false, true);
    expect(r.ui.view() == View::Preview, "held B wake does not request sleep");
    r.ui.update(1100, false, false); r.ui.update(1130, false, false);
    expect(r.ui.view() == View::Preview, "wake release does not act as a fresh press");
    r.ui.update(1200, true, true); r.ui.update(1230, true, true);
    expect(r.ui.view() == View::Sleep && !r.ui.takeRequest(), "B wins simultaneous A/B");
  }
  {
    Rig r; auto job = r.hold(100); r.release(900);
    r.ui.update(1000, false, true); r.ui.update(1030, false, true);
    expect(r.ui.busy() && r.ui.sleepQueued(), "B defers sleep during apply");
    r.ui.complete(job.id, 201, 1100);
    expect(r.ui.view() == View::Sleep && r.c.hasApplied, "deferred sleep preserves successful result");
  }
  {
    Rig r; r.c.online = false; r.tap(100);
    auto job = r.hold(300); r.release(1200);
    r.ui.next(2000); r.ui.apply(2000);
    expect(r.c.selected == 1 && !r.ui.takeRequest(), "pending connection freezes selection and avoids duplicate applies");
    r.ui.complete(job.id, 200, 5000);
    expect(r.c.applied == "EVENING", "apply before connection completes automatically using captured mode");
    r.tap(5100); auto failed = r.hold(5400); r.release(6200);
    r.ui.complete(failed.id, 500, 7000);
    expect(r.c.applied == "EVENING" && r.ui.view() == View::Error, "failure preserves last applied mode");
    r.ui.update(14999, false, false);
    expect(r.ui.view() == View::Error, "error remains visible for 8 seconds");
    r.ui.update(15000, false, false);
    expect(r.ui.view() == View::Sleep, "error expires after 8 seconds");
  }
  {
    Rig r; auto job = r.hold(100); r.release(900);
    r.ui.update(30830, false, false);
    expect(r.ui.view() == View::Error, "connection/request waiting is bounded");
    r.ui.complete(job.id, 200, 31000);
    expect(!r.c.hasApplied, "late completion cannot overwrite timed-out result");
    r.ui.sleep(); r.ui.wake(32000); r.ui.complete(job.id, 200, 33000);
    expect(r.ui.view() == View::Preview && !r.c.hasApplied, "obsolete completion cannot change new wake session");
  }
  {
    Rig r; r.c.selected = 3; r.c.recordResult(r.c.mode(), 200);
    auto saved = r.ui.retain(); Rig restored;
    expect(restored.ui.restore(saved) && restored.c.selected == 3 && restored.c.appliedOff,
           "deep sleep restores selection and successful OFF history");
    saved.selected ^= 1;
    expect(!restored.ui.restore(saved), "corrupt retention is rejected");
    saved = r.ui.retain(); restored.c.config.modes[0].kelvin = 6500;
    expect(!restored.ui.restore(saved), "changed configuration invalidates cached indices");
  }
  {
    Rig r; r.ui.wake(UINT32_MAX - 1000);
    r.ui.update(1998, false, false);
    expect(r.ui.view() == View::Preview, "wake timer handles millis rollover");
    r.ui.update(1999, false, false);
    expect(r.ui.view() == View::Sleep, "rollover does not extend deadline");
    Screen s;
    for (unsigned progress : {0u, 1u, 50u, 100u}) { s.render(r.c, progress); expect(!s.clipped, "hold bar stays within framebuffer"); }
  }
  {
    Rig r; r.c.hasToken = false; r.ui.apply(100);
    expect(r.ui.view() == View::Error && !r.ui.takeRequest(), "missing settings never queues a light command");
  }
  std::cout << "PASS " << checks << " interaction assertions\n";
}
