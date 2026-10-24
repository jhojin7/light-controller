#ifdef STICKS3_DIAGNOSTIC
// SPDX-License-Identifier: MIT
#include <M5Unified.h>

void setup() {
  auto cfg = M5.config();
  cfg.internal_imu = false;
  cfg.internal_rtc = false;
  cfg.internal_spk = false;
  cfg.internal_mic = false;
  M5.begin(cfg);
  Serial.begin(115200);
  M5.Display.setRotation(0);
  M5.Display.setBrightness(128);
  M5.Display.fillScreen(0x070B12);
  M5.Display.setTextColor(0xEDF3FB);
  M5.Display.setTextSize(1);
  M5.Display.setCursor(8, 12);
  M5.Display.println("StickS3 diagnostic");
  M5.Display.printf("%d x %d\n", M5.Display.width(), M5.Display.height());
}

void loop() {
  M5.update();
  if (M5.BtnA.wasPressed()) Serial.println("BTN A");
  if (M5.BtnB.wasPressed()) Serial.println("BTN B");
  static uint32_t last = 0;
  if (millis() - last > 2000) {
    last = millis();
    Serial.printf("STICKS3 board=%d size=%dx%d psram=%u battery=%d\n",
                  M5.getBoard(), M5.Display.width(), M5.Display.height(),
                  ESP.getPsramSize(), M5.Power.getBatteryLevel());
  }
  delay(10);
}

#endif
