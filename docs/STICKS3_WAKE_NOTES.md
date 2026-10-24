# StickS3 motion and button wake implementation notes

Research date: 2026-10-24. These notes record source inspection before board testing;
see [testing results](TESTING.md) for subsequent hardware validation. Sleep current
has not been measured.

## Recommended hardware path

Use ESP32-S3 deep sleep while retaining its 3.3 V supply. Keep the BMI270 supply enabled. Configure BMI270 INT1 → M5PM1 GPIO4 input → M5PM1 GPIO1 IRQ output → ESP32-S3 GPIO13. Button B is ESP GPIO12. Both wake sources are active low, so enable EXT1 on GPIO12 and GPIO13 with `ESP_EXT1_WAKEUP_ANY_LOW`. This follows M5Stack's documented chained ESP wake path and Espressif's supported multiple-pin wake mode. Do not use PMIC shutdown/L1-only mode: it removes the ESP supply and prevents B from waking it. [M5Stack wake examples](https://docs.m5stack.com/en/arduino/m5sticks3/m5pm1), [ESP-IDF 4.4.7 sleep API](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/system/sleep_modes.html)

## Pinned libraries and shared I2C

Keep `m5stack/M5Unified@0.2.27` and `m5stack/M5GFX@0.2.34`. M5Unified supplies `M5.Power.M5pm1` (`m5::M5PM1_Class`) and all required GPIO/IRQ functions; a second M5PM1 dependency is unnecessary. Its BMI270 wrapper does not expose any-motion configuration. Add `sparkfun/SparkFun BMI270 Arduino Library@1.0.3`, whose tag resolves to `21ea234de321da07c552f7a43cb36f7df4f73a27`, and use its bundled Bosch C API, `bmi270_api/bmi270.h`. This avoids copying feature-page register layouts and configuration firmware into the application. [M5Unified PMIC API](https://github.com/m5stack/M5Unified/blob/0.2.27/src/utility/power/M5PM1_Class.hpp), [SparkFun v1.0.3](https://github.com/sparkfun/SparkFun_BMI270_Arduino_Library/tree/v1.0.3), [Bosch API](https://github.com/sparkfun/SparkFun_BMI270_Arduino_Library/blob/v1.0.3/src/bmi270_api/bmi270.h)

Set `config.internal_imu = false` before `M5.begin(config)` and initialize the sensor once through Bosch. Use M5Unified's existing I2C transport rather than creating another Arduino `Wire` driver on the same pins. The callbacks are:

```cpp
static int8_t readBmi(uint8_t reg, uint8_t* data, uint32_t length, void*) {
  return M5.In_I2C.readRegister(0x68, reg, data, length, 400000) ? 0 : -1;
}
static int8_t writeBmi(uint8_t reg, const uint8_t* data, uint32_t length, void*) {
  return M5.In_I2C.writeRegister(0x68, reg, data, length, 400000) ? 0 : -1;
}
static void delayBmi(uint32_t us, void*) { delayMicroseconds(us); }

bmi2_dev sensor{};
sensor.intf = BMI2_I2C_INTF;
sensor.read = readBmi;
sensor.write = writeBmi;
sensor.delay_us = delayBmi;
sensor.read_write_len = 32;
// Check every API result, starting with bmi270_init(&sensor).
```

These signatures match the bundled Bosch declarations and M5Unified register methods. Keep sensor and PMIC access on the application task; networking must not concurrently manipulate their configuration. [I2C API](https://github.com/m5stack/M5Unified/blob/0.2.27/src/utility/I2C_Class.hpp), [Bosch callback declarations](https://github.com/sparkfun/SparkFun_BMI270_Arduino_Library/blob/v1.0.3/src/bmi270_api/bmi2_defs.h)

## Sensor configuration

After `bmi270_init`, retrieve two `bmi2_sens_config` entries with types `BMI2_ACCEL` and `BMI2_ANY_MOTION` using `bmi270_get_sensor_config`. Set acceleration ODR `BMI2_ACC_ODR_50HZ`, bandwidth `BMI2_ACC_NORMAL_AVG4`, filter performance `BMI2_POWER_OPT_MODE`, range `BMI2_ACC_RANGE_2G`. Start any-motion with threshold 170, duration 5, and `select_x/y/z = 1`. These correspond approximately to 83 mg and 100 ms; they are initial tuning values, not validated pickup sensitivity. Save with `bmi270_set_sensor_config`. [Bosch implementation and configuration fields](https://github.com/sparkfun/SparkFun_BMI270_Arduino_Library/blob/v1.0.3/src/bmi270_api/bmi270.c), [Bosch constants](https://github.com/sparkfun/SparkFun_BMI270_Arduino_Library/blob/v1.0.3/src/bmi270_api/bmi2_defs.h)

Configure `bmi2_int_pin_config{}` with `pin_type = BMI2_INT1`, `int_latch = BMI2_INT_NON_LATCH`, and `pin_cfg[0]` active low, push-pull, output enabled, input disabled; apply using `bmi2_set_int_pin_config`. Route with `bmi2_sens_int_config{BMI2_ANY_MOTION, BMI2_INT1}` and `bmi270_map_feat_int`. Disable `BMI2_GYRO`, `BMI2_AUX`, `BMI2_TEMP`; enable `BMI2_ACCEL`, `BMI2_ANY_MOTION`; enable advanced power save using `bmi2_set_adv_power_save(BMI2_ENABLE, &sensor)`. Use Bosch's `BMI2_ANY_MOTION` identifier here, not SparkFun wrapper's `BMI2_ANY_MOTION_INT`. [Bosch interrupt APIs](https://github.com/sparkfun/SparkFun_BMI270_Arduino_Library/blob/v1.0.3/src/bmi270_api/bmi270.h), [Bosch common APIs](https://github.com/sparkfun/SparkFun_BMI270_Arduino_Library/blob/v1.0.3/src/bmi270_api/bmi2.h)

## PMIC setup and sleep safety

Using `M5.Power.M5pm1`:

- GPIO4: function `gpio`, mode `input`, pull `pull_up`.
- GPIO1: mode `output`, drive `push_pull`, pull `pull_up`, output latch high, then function `irq`.
- `setGPIOIRQMaskBits(0x0F)` unmasks only GPIO4; `setSystemIRQMaskBits(0x3F)` and `setButtonIRQMaskBits(0x07)` mask the other interrupt classes.
- `clearIRQStatus()` writes zero to status registers 0x40–0x42. Mask bit 1 means disabled. The GPIO1 IRQ signal is active low and remains asserted until its status is cleared.
- Keep PMIC I2C idle sleep disabled (its M5Unified `begin()` writes register 0x09 = 0). Do not call `powerOff()`/PMIC shutdown. Keep LDO (BMI270) and DCDC (ESP) on. GPIO2 controls L3B: set its output low after stopping the display to remove backlight/audio power; M5GFX restores it during boot.

The register semantics and API names come from the pinned wrapper and official driver. [M5Unified PMIC implementation](https://github.com/m5stack/M5Unified/blob/0.2.27/src/utility/power/M5PM1_Class.inl), [official M5PM1 driver](https://github.com/m5stack/M5PM1/blob/be9a5456c007c333e7ac963f33bfde1ffa5d82ee/src/M5PM1.cpp)

Disable the any-motion feature while awake. On sleep entry, wait for A/B release and device settling, enable any-motion, read BMI interrupt status with `bmi2_get_int_status`, clear PMIC IRQ status, and ensure GPIO13 and GPIO12 are high before arming EXT1. Sensor assertion/release can both produce PMIC GPIO events, so clear stale events after settling. Bound setup retries; a failed motion setup should leave button wake available with a visible diagnostic rather than spin indefinitely. On reboot call `rtc_gpio_deinit(GPIO_NUM_12)` and `rtc_gpio_deinit(GPIO_NUM_13)` before digital button/IRQ reads. Preserve selection with RTC memory. [Espressif wake pin handling](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/system/sleep_modes.html)

Hardware acceptance still requires natural-pickup tests, repeated B/motion wake cycles, no immediate re-wake after putting it down, and standby-current measurements. Keeping the PMIC active changes consumption from the vendor's L1 shutdown example, so do not claim its published L1 current for this configuration.
