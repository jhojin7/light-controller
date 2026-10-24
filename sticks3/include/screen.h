// SPDX-License-Identifier: MIT
#pragma once
#include "controller.h"
#include <array>

namespace light {
// The same RGB565 framebuffer is rendered on the board and in host tests.
class Screen {
 public:
  static constexpr int width = 135;
  static constexpr int height = 240;
  std::array<uint16_t, width * height> pixels{};
  std::vector<std::string> visible;
  bool clipped = false;
  void render(const Controller& controller);
 private:
  void pixel(int x, int y, uint32_t color);
  void rect(int x, int y, int w, int h, uint32_t color);
  void dot(int x, int y, int size, uint32_t color);
  void text(std::string value, int center, int y, int maxWidth, int maxPitch,
            int minPitch, uint32_t color);
  void small(std::string value, int center, int y, uint32_t color);
};
}  // namespace light
