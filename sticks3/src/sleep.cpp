// SPDX-License-Identifier: MIT
#ifndef STICKS3_DIAGNOSTIC
#include "sleep.h"
#include <M5Unified.h>
#include <SparkFun_BMI270_Arduino_Library.h>
#include <esp_sleep.h>
#include <driver/rtc_io.h>

namespace light {
namespace {
bmi2_dev sensor{};
int8_t readRegister(uint8_t reg, uint8_t* data, uint32_t size, void*) {
  return M5.In_I2C.readRegister(0x68, reg, data, size, 400000) ? 0 : -1;
}
int8_t writeRegister(uint8_t reg, const uint8_t* data, uint32_t size, void*) {
  return M5.In_I2C.writeRegister(0x68, reg, data, size, 400000) ? 0 : -1;
}
void sensorDelay(uint32_t us, void*) {
  if (us >= 1000) delay(us / 1000);
  delayMicroseconds(us % 1000);
}
constexpr uint8_t motion = BMI2_ANY_MOTION;
}

bool SleepHardware::begin() {
  rtc_gpio_deinit(GPIO_NUM_12);
  rtc_gpio_deinit(GPIO_NUM_13);
  auto& pm = M5.Power.M5pm1;
  bool pmOk = pm.setLDOOutput(true);
  // Keep PM1 running to forward IMU events to the ESP's RTC wake pin.
  pmOk &= M5.In_I2C.writeRegister8(0x6e, 0x09, 0, 100000);
  pmOk &= pm.setGPIOFunction(m5::M5PM1_Class::gpio4, m5::M5PM1_Class::gpio);
  pmOk &= pm.setGPIOMode(m5::M5PM1_Class::gpio4, m5::M5PM1_Class::input);
  pmOk &= pm.setGPIOPull(m5::M5PM1_Class::gpio4, m5::M5PM1_Class::pull_up);
  pmOk &= pm.setGPIOFunction(m5::M5PM1_Class::gpio1, m5::M5PM1_Class::gpio);
  pmOk &= pm.setGPIOMode(m5::M5PM1_Class::gpio1, m5::M5PM1_Class::output);
  pmOk &= pm.setGPIODrive(m5::M5PM1_Class::gpio1, m5::M5PM1_Class::push_pull);
  pmOk &= pm.setGPIOPull(m5::M5PM1_Class::gpio1, m5::M5PM1_Class::pull_up);
  pmOk &= pm.setGPIOOutput(m5::M5PM1_Class::gpio1, true);
  pmOk &= pm.setGPIOFunction(m5::M5PM1_Class::gpio1, m5::M5PM1_Class::irq);
  pmOk &= pm.setGPIOIRQMaskBits(0x0f);  // Only motion GPIO4 raises IRQ.
  pmOk &= pm.setSystemIRQMaskBits(0x3f);
  pmOk &= pm.setButtonIRQMaskBits(0x07);
  pmOk &= pm.clearIRQStatus();
  if (!pmOk) { error_ = -100; return false; }
  pinMode(13, INPUT_PULLUP);
  sensor.intf = BMI2_I2C_INTF;
  sensor.read = readRegister; sensor.write = writeRegister;
  sensor.delay_us = sensorDelay; sensor.read_write_len = 32;
  if ((error_ = bmi270_init(&sensor)) != BMI2_OK) return false;
  bmi2_sens_config config[2]{};
  config[0].type = BMI2_ACCEL; config[1].type = BMI2_ANY_MOTION;
  if ((error_ = bmi270_get_sensor_config(config, 2, &sensor)) != BMI2_OK) return false;
  config[0].cfg.acc.odr = BMI2_ACC_ODR_50HZ;
  config[0].cfg.acc.bwp = BMI2_ACC_NORMAL_AVG4;
  config[0].cfg.acc.filter_perf = BMI2_POWER_OPT_MODE;
  config[0].cfg.acc.range = BMI2_ACC_RANGE_2G;
  config[1].cfg.any_motion.duration = 5;
  config[1].cfg.any_motion.threshold = 170;  // ~83 mg, 100 ms; tune on hardware.
  config[1].cfg.any_motion.select_x = 1;
  config[1].cfg.any_motion.select_y = 1;
  config[1].cfg.any_motion.select_z = 1;
  if ((error_ = bmi270_set_sensor_config(config, 2, &sensor)) != BMI2_OK) return false;
  bmi2_int_pin_config pin{};
  pin.pin_type = BMI2_INT1; pin.int_latch = BMI2_INT_NON_LATCH;
  pin.pin_cfg[0].lvl = BMI2_INT_ACTIVE_LOW;
  pin.pin_cfg[0].od = BMI2_INT_PUSH_PULL;
  pin.pin_cfg[0].output_en = BMI2_INT_OUTPUT_ENABLE;
  if ((error_ = bmi2_set_int_pin_config(&pin, &sensor)) != BMI2_OK) return false;
  bmi2_sens_int_config route{BMI2_ANY_MOTION, BMI2_INT1};
  if ((error_ = bmi270_map_feat_int(&route, 1, &sensor)) != BMI2_OK) return false;
  uint8_t off[] = {BMI2_GYRO, BMI2_AUX, BMI2_TEMP, BMI2_ANY_MOTION};
  if ((error_ = bmi270_sensor_disable(off, 4, &sensor)) != BMI2_OK) return false;
  uint8_t accel = BMI2_ACCEL;
  if ((error_ = bmi270_sensor_enable(&accel, 1, &sensor)) != BMI2_OK) return false;
  if ((error_ = bmi2_set_adv_power_save(BMI2_ENABLE, &sensor)) != BMI2_OK) return false;
  ready_ = true;
  return true;
}

bool SleepHardware::irqActive() const { return digitalRead(13) == LOW; }

bool SleepHardware::prepare(uint32_t now, bool keysReleased) {
  if (!keysReleased) return false;
  if (!armed_) {
    armed_ = true; armedAt_ = now;
    M5.Display.setBrightness(0);
    M5.Display.sleep();
    if (ready_) {
      uint8_t enable = motion;
      error_ = bmi270_sensor_enable(&enable, 1, &sensor);
      if (error_ != BMI2_OK) ready_ = false;
    }
  }
  // Let setting the device down settle without a busy-wait on the UI thread.
  if (uint32_t(now - armedAt_) < 500) return false;
  M5.Power.M5pm1.clearIRQStatus();
  return true;
}

void SleepHardware::cancel() {
  if (ready_ && armed_) {
    uint8_t disable = motion;
    bmi270_sensor_disable(&disable, 1, &sensor);
  }
  armed_ = false;
}

void SleepHardware::enter(uint32_t testWakeSeconds) {
  M5.Display.setBrightness(0);
  M5.Display.sleep();
  // L3B supplies the backlight and audio; LDO keeps the IMU, DCDC the ESP rail.
  M5.Power.M5pm1.setGPIOOutput(m5::M5PM1_Class::gpio2, false);
  rtc_gpio_pullup_en(GPIO_NUM_12); rtc_gpio_pulldown_dis(GPIO_NUM_12);
  rtc_gpio_pullup_en(GPIO_NUM_13); rtc_gpio_pulldown_dis(GPIO_NUM_13);
  esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
  esp_sleep_enable_ext1_wakeup((1ULL << 12) | (ready_ ? 1ULL << 13 : 0), ESP_EXT1_WAKEUP_ANY_LOW);
  if (testWakeSeconds) esp_sleep_enable_timer_wakeup(uint64_t(testWakeSeconds) * 1000000);
  // Continuous movement must not keep the CPU and screen on or repeatedly cold
  // boot. Settle with low-power sleeps before arming the final indefinite sleep.
  while (digitalRead(12) == LOW || (ready_ && irqActive())) {
    // A new B press during settling is a wake request. Enter deep sleep with
    // that asserted wake source so the normal boot path retains RTC selection;
    // a software restart would reinitialize RTC data instead.
    if (digitalRead(12) == LOW) {
      esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
      esp_sleep_enable_ext1_wakeup(1ULL << 12, ESP_EXT1_WAKEUP_ANY_LOW);
      esp_deep_sleep_start();
    }
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_EXT1);
    esp_sleep_enable_ext1_wakeup(1ULL << 12, ESP_EXT1_WAKEUP_ANY_LOW);
    esp_sleep_enable_timer_wakeup(500000);
    esp_light_sleep_start();
    rtc_gpio_deinit(GPIO_NUM_12); rtc_gpio_deinit(GPIO_NUM_13);
    M5.Power.M5pm1.clearIRQStatus();
    rtc_gpio_pullup_en(GPIO_NUM_12); rtc_gpio_pullup_en(GPIO_NUM_13);
  }
  esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
  if (testWakeSeconds) esp_sleep_enable_timer_wakeup(uint64_t(testWakeSeconds) * 1000000);
  esp_sleep_enable_ext1_wakeup((1ULL << 12) | (ready_ ? 1ULL << 13 : 0), ESP_EXT1_WAKEUP_ANY_LOW);
  esp_deep_sleep_start();
}
}  // namespace light
#endif
