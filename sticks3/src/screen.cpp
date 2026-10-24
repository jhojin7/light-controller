// SPDX-License-Identifier: MIT
#include "screen.h"
#include "bitmaps.h"
#include <algorithm>

namespace light {
static constexpr uint32_t background = 0x070B12;
static constexpr uint32_t white = 0xEDF3FB;
static constexpr uint32_t muted = 0x8291A6;
static constexpr uint32_t green = 0x7EE7B4;

static uint16_t rgb565(uint32_t color) {
  return ((color >> 8) & 0xF800) | ((color >> 5) & 0x07E0) | ((color >> 3) & 0x001F);
}

void Screen::pixel(int x, int y, uint32_t color) {
  if (x < 0 || x >= width || y < 0 || y >= height) { clipped = true; return; }
  pixels[y * width + x] = rgb565(color);
}
void Screen::rect(int x, int y, int w, int h, uint32_t color) {
  for (int dy = 0; dy < h; ++dy)
    for (int dx = 0; dx < w; ++dx) pixel(x + dx, y + dy, color);
}
void Screen::dot(int x, int y, int size, uint32_t color) {
  for (int dy = 0; dy < size; ++dy)
    for (int dx = 0; dx < size; ++dx) {
      if (size >= 3 && (dx == 0 || dx == size - 1) && (dy == 0 || dy == size - 1)) continue;
      pixel(x + dx, y + dy, color);
    }
}

void Screen::text(std::string value, int center, int y, int maxWidth, int maxPitch,
                  int minPitch, uint32_t color) {
  value = upper(value);
  for (char& ch : value) {
    bool known = false;
    for (const auto& glyph : glyphs) if (glyph.ch == ch) { known = true; break; }
    if (!known) ch = '?';
  }
  int pitch = maxPitch;
  auto textWidth = [&]() { return (int(value.size()) * 6 - 2) * pitch + std::max(1, pitch - 1); };
  while (pitch > minPitch && textWidth() > maxWidth) --pitch;
  int size = std::max(1, pitch - 1);
  int maxChars = ((maxWidth - size) / pitch + 2) / 6;
  if (int(value.size()) > maxChars) value = value.substr(0, std::max(0, maxChars - 3)) + "...";
  visible.push_back(value);
  int x = center - std::max(1, textWidth()) / 2;
  for (size_t i = 0; i < value.size(); ++i) {
    for (const auto& glyph : glyphs) {
      if (glyph.ch != value[i]) continue;
      for (int row = 0; row < 7; ++row)
        for (int col = 0; col < 5; ++col)
          if (glyph.rows[row] & (1 << (4 - col))) dot(x + (i * 6 + col) * pitch, y + row * pitch, size, color);
      break;
    }
  }
}

void Screen::small(std::string value, int center, int y, uint32_t color) {
  // Original built-in alphabet, six-pixel advance; no font installation needed.
  std::replace(value.begin(), value.end(), '\n', ' ');
  text(value, center, y + 3, width - 16, 1, 1, color);
}

void Screen::render(const Controller& c, unsigned holdProgress) {
  pixels.fill(rgb565(background));
  visible.clear();
  clipped = false;
  small("LIGHT", 23, 8, white);
  // Battery outline and percentage occupy the top right; Wi-Fi sits to the left.
  uint32_t batteryColor = c.charging ? green : c.battery >= 0 && c.battery <= 20 ? 0xFF8A88 : muted;
  rect(92, 10, 11, 1, batteryColor);
  rect(92, 16, 11, 1, batteryColor);
  rect(92, 11, 1, 5, batteryColor);
  rect(102, 11, 1, 5, batteryColor);
  rect(103, 12, 1, 3, batteryColor);
  if (c.battery > 0) rect(94, 12, std::max(1, std::min(100, c.battery) * 7 / 100), 3, batteryColor);
  if (c.charging) {
    rect(96, 11, 1, 5, white);
    rect(94, 13, 5, 1, white);
  }
  small(c.battery < 0 ? "--%" : std::to_string(c.battery) + "%", 118, 8, batteryColor);
  for (int y : {24, 164}) rect(8, y, width - 16, 1, 0x233044);
  const auto& mode = c.mode();
  auto iconName = modeIcon(mode);
  auto accent = modeColor(mode);
  for (const auto& icon : icons) if (iconName == icon.name) {
    for (int y = 0; y < 13; ++y)
      for (int x = 0; x < 13; ++x)
        if (icon.rows[y][x] == '#') dot(width / 2 - 19 + x * 3, 32 + y * 3, 2, accent);
  }
  const char* wifi[] = {"..#######..", ".#.......#.", "#..#####..#", "..#.....#..", "....###....", "...#...#...", ".....#....."};
  for (int y = 0; y < 7; ++y)
    for (int x = 0; x < 11; ++x)
      if (wifi[y][x] == '#') pixel(76 + x, 10 + y, c.online ? green : muted);
  text(mode.name, width / 2, 80, width - 8, 5, 2, accent);
  text(std::to_string(mode.off ? 0 : mode.brightness * 100 / 255) + "%", 34, 126, 54, 2, 1, white);
  text(mode.off ? "--" : std::to_string(mode.kelvin) + "K", 101, 126, 59, 2, 1, white);
  small("BRIGHT", 34, 145, muted);
  small("KELVIN", 101, 145, muted);
  text(std::to_string(c.selected + 1) + "/" + std::to_string(c.config.modes.size()), width / 2, 174, width - 16, 2, 1, muted);
  auto message = c.status == "Ready" || c.status == "Selected" ? "HOLD A TO SET" : c.status == "OK" ? "APPLIED" : c.status;
  uint32_t statusColor = muted;
  if (c.status == "OK") statusColor = green;
  else if (c.status == "Sending..." || c.status == "Connecting") statusColor = 0xFFE49C;
  else if (c.status != "Ready" && c.status != "Selected") statusColor = 0xFF8A88;
  small(message, width / 2, 194, statusColor);
  small(c.appliedText(), width / 2, 208, c.hasApplied && c.applied == mode.name ? green : muted);
  if (holdProgress) rect(8, 220, (width - 16) * std::min(100u, holdProgress) / 100, 2, accent);
  small("A NEXT  B SLEEP", width / 2, 224, muted);
}
}  // namespace light
