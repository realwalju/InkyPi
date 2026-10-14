"""Background MQTT listener that keeps the latest value and 24h of history per topic.

InkyPi plugins only run at refresh time, but MQTT messages arrive whenever sensors
publish. This module runs one paho-mqtt client for the whole process; the plugin
renders from the snapshot it keeps.

Broker settings come from the API Keys page (.env):
    MQTT_HOST      default localhost
    MQTT_PORT      default 1883
    MQTT_USERNAME  optional
    MQTT_PASSWORD  optional
    MQTT_TOPICS    comma-separated subscription filters, default "#"
"""

import json
import logging
import math
import os
import threading
import time
from collections import deque

from dotenv import load_dotenv
from utils.app_utils import resolve_path

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    mqtt = None
    PAHO_AVAILABLE = False

HISTORY_FILE = resolve_path(os.path.join("config", "mqtt_history.json"))
HISTORY_SECONDS = 24 * 60 * 60
BUCKET_SECONDS = 60              # at most one history point per topic per minute
MAX_TOPICS = 200                 # ignore new topics past this, so a noisy broker can't eat the Pi's RAM
MAX_FIELDS = 32                  # numeric fields kept per JSON payload
MAX_PAYLOAD_CHARS = 256
SAVE_INTERVAL_SECONDS = 5 * 60

_lock = threading.Lock()
_latest = {}                     # topic -> (timestamp, payload string)
_history = {}                    # topic -> deque of (bucket timestamp, {field: value})
_status = {"connected": False, "error": None, "broker": None}
_started = False
_client = None


def numeric_fields(payload):
    """Return {field: float} for a payload: "" for a bare number, dot paths for JSON objects."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return {}

    fields = {}

    def walk(value, path, depth):
        if len(fields) >= MAX_FIELDS or depth > 3:
            return
        if isinstance(value, bool):
            fields[path] = 1.0 if value else 0.0
        elif isinstance(value, (int, float)):
            if math.isfinite(value):
                fields[path] = float(value)
        elif isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else str(key), depth + 1)

    walk(data, "", 0)
    return fields


def _record(topic, payload, now=None):
    now = now or time.time()
    payload = payload[:MAX_PAYLOAD_CHARS]
    fields = numeric_fields(payload)
    with _lock:
        if topic not in _latest and len(_latest) >= MAX_TOPICS:
            return
        _latest[topic] = (now, payload)
        if not fields:
            return
        history = _history.setdefault(topic, deque(maxlen=HISTORY_SECONDS // BUCKET_SECONDS))
        bucket = now - (now % BUCKET_SECONDS)
        if history and history[-1][0] == bucket:
            history[-1] = (bucket, fields)
        else:
            history.append((bucket, fields))


def _on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        with _lock:
            _status.update(connected=False, error=str(reason_code))
        logger.warning(f"MQTT connection refused: {reason_code}")
        return
    with _lock:
        _status.update(connected=True, error=None)
    for topic in userdata["topics"]:
        client.subscribe(topic)
    logger.info(f"MQTT connected to {_status['broker']}, subscribed to {userdata['topics']}")


def _on_disconnect(client, userdata, flags, reason_code, properties):
    with _lock:
        _status["connected"] = False
    logger.info(f"MQTT disconnected: {reason_code}")


def _on_message(client, userdata, message):
    try:
        _record(message.topic, message.payload.decode("utf-8", errors="replace"))
    except Exception:
        logger.exception(f"Failed to record MQTT message on {message.topic}")


def _load_history():
    if not os.path.exists(HISTORY_FILE):
        return
    try:
        with open(HISTORY_FILE) as f:
            saved = json.load(f)
    except (OSError, ValueError) as e:
        logger.warning(f"Could not load MQTT history: {e}")
        return
    cutoff = time.time() - HISTORY_SECONDS
    with _lock:
        for topic, (ts, payload) in saved.get("latest", {}).items():
            _latest[topic] = (ts, payload)
        for topic, points in saved.get("history", {}).items():
            history = deque(maxlen=HISTORY_SECONDS // BUCKET_SECONDS)
            history.extend((ts, fields) for ts, fields in points if ts >= cutoff)
            if history:
                _history[topic] = history


def save_history():
    with _lock:
        snapshot = {
            "latest": dict(_latest),
            "history": {topic: list(points) for topic, points in _history.items()},
        }
    tmp_path = HISTORY_FILE + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(snapshot, f)
        os.replace(tmp_path, HISTORY_FILE)
    except OSError as e:
        logger.warning(f"Could not save MQTT history: {e}")


def _save_loop():
    while True:
        time.sleep(SAVE_INTERVAL_SECONDS)
        save_history()


def start():
    """Start the shared MQTT client once per process. Safe to call repeatedly."""
    global _started, _client
    with _lock:
        if _started:
            return
        _started = True

    if not PAHO_AVAILABLE:
        with _lock:
            _status["error"] = "paho-mqtt not installed"
        logger.error("paho-mqtt is not installed; run install/update.sh")
        return

    load_dotenv(override=True)
    host = os.getenv("MQTT_HOST") or "localhost"
    port = int(os.getenv("MQTT_PORT") or 1883)
    topics = [t.strip() for t in (os.getenv("MQTT_TOPICS") or "#").split(",") if t.strip()]
    with _lock:
        _status["broker"] = f"{host}:{port}"

    _load_history()
    threading.Thread(target=_save_loop, name="mqtt-history-save", daemon=True).start()

    _client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"inkypi-{os.getpid()}",
        userdata={"topics": topics},
    )
    username = os.getenv("MQTT_USERNAME")
    if username:
        _client.username_pw_set(username, os.getenv("MQTT_PASSWORD"))
    _client.on_connect = _on_connect
    _client.on_disconnect = _on_disconnect
    _client.on_message = _on_message
    _client.reconnect_delay_set(min_delay=1, max_delay=60)

    # connect_async + loop_start keeps retrying in the background if the broker isn't up yet.
    _client.connect_async(host, port, keepalive=60)
    _client.loop_start()


def get_status():
    with _lock:
        return dict(_status)


def get_topics():
    with _lock:
        return sorted(_latest)


def get_latest(topic):
    """Return (timestamp, payload) or None."""
    with _lock:
        return _latest.get(topic)


def get_series(topic, field, since):
    """Return [(timestamp, value)] for one numeric field since a timestamp."""
    with _lock:
        points = list(_history.get(topic, ()))
    return [(ts, fields[field]) for ts, fields in points if ts >= since and field in fields]


def get_fields(topic):
    """Numeric field names seen in the topic's latest payload."""
    latest = get_latest(topic)
    return sorted(numeric_fields(latest[1])) if latest else []
