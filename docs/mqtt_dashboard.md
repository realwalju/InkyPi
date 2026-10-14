# MQTT Dashboard

Shows live values from MQTT topics as a grid of tiles: a large current value, how long ago it arrived, and a sparkline of the last 1–24 hours. Anything that publishes to MQTT works, such as the ESP32 node in [`hardware/esp32-sensor-node`](../hardware/esp32-sensor-node), Home Assistant, zigbee2mqtt or Tasmota.

## How it works

A background listener starts with InkyPi and subscribes to the broker. It keeps each topic's latest message plus one point per minute for 24 hours, and saves that history to `src/config/mqtt_history.json` every 5 minutes so it survives restarts. At refresh time the plugin draws from that history. It caps out at 200 topics so a busy broker can't use up the Pi's memory.

Payloads can be:
- a plain number (`21.5`), shown with a sparkline
- JSON (`{"temp_c": 21.5, "sensor": {"rh": 40}}`). Set the tile's **Field** to `temp_c` or `sensor.rh`.
- text (`open`, `pressed`), shown as-is

A tile shows its age in the top-right corner. Past the stale threshold (default 15 minutes) the age switches to an inverted badge. The header shows `BROKER OFFLINE` when the listener isn't connected.

## 1. Install Mosquitto on the Pi

```bash
sudo apt install -y mosquitto mosquitto-clients
```

Let other devices on your network connect, with a password required:

```bash
printf 'listener 1883\nallow_anonymous false\npassword_file /etc/mosquitto/passwd\n' | sudo tee /etc/mosquitto/conf.d/inkypi.conf
```

Create one login for InkyPi and one for the ESP32 (each command prompts for a password):

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd inkypi
```
```bash
sudo mosquitto_passwd /etc/mosquitto/passwd esp32-s3
```
```bash
sudo chown mosquitto: /etc/mosquitto/passwd && sudo chmod 600 /etc/mosquitto/passwd && sudo systemctl restart mosquitto
```

Check it's running:

```bash
mosquitto_sub -h localhost -u inkypi -P '<password>' -t 'inkypi/#' -v
```

## 2. Point InkyPi at the broker

On the **API Keys** page, add:

| Key | Value |
|:-|:-|
| `MQTT_USERNAME` | `inkypi` |
| `MQTT_PASSWORD` | the password you set |
| `MQTT_HOST` | optional, defaults to `localhost` |
| `MQTT_PORT` | optional, defaults to `1883` |
| `MQTT_TOPICS` | optional, comma-separated filters, defaults to `#` |

Install the `paho-mqtt` dependency and restart:

```bash
cd ~/InkyPi && sudo bash install/update.sh
```

## 3. Add tiles

Open **MQTT Dashboard** in the web UI. The settings page shows whether the broker is connected and lists every topic seen so far, with **+ field** buttons that add a tile in one click. Each tile has a label, topic, optional JSON field and unit.
