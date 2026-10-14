# ESP32-S3 sensor node

ESP-IDF v6 firmware that feeds the [MQTT Dashboard](../../docs/mqtt_dashboard.md) plugin. It needs no extra wiring: it reports the ESP32-S3's built-in temperature sensor, Wi-Fi signal, free heap and uptime, plus the BOOT button.

| Topic | Payload | When |
|:-|:-|:-|
| `inkypi/<node>/state` | `{"temp_c":38.2,"rssi":-55,"heap_kb":213,"uptime_s":3600}` | every 30 s (retained) |
| `inkypi/<node>/button` | `pressed` / `released` | on change (retained) |
| `inkypi/<node>/status` | `online`, or `offline` via last will | on connect / disconnect (retained) |

The chip temperature runs well above room temperature, because it measures the die rather than the air. It's here to prove the pipeline works. Swap in a real sensor (BME280, SCD40, ...) by adding fields to the JSON in `publish_task`.

## Build and flash

From an ESP-IDF v6 PowerShell:

```bash
idf.py set-target esp32s3
```
```bash
idf.py menuconfig
```

Under **InkyPi Sensor Node**, set the Wi-Fi SSID and password and the MQTT username and password (`esp32-s3` from the Mosquitto setup). The broker defaults to `mqtt://walju.local`; use the Pi's IP if `.local` names don't resolve. These values are saved to `sdkconfig`, which is gitignored.

```bash
idf.py build flash monitor
```

Once it's connected, the topics appear in the MQTT Dashboard settings page and can be added as tiles.
