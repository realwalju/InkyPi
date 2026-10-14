import json
import logging
import math
import time
from datetime import datetime

from PIL import Image, ImageDraw
from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import get_font

from . import mqtt_store

logger = logging.getLogger(__name__)

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

DEFAULT_WINDOW_HOURS = 24
DEFAULT_STALE_MINUTES = 15
TARGET_TILE_ASPECT = 1.4  # width / height the grid layout aims for


class MqttDashboard(BasePlugin):
    def __init__(self, config, **dependencies):
        super().__init__(config, **dependencies)
        # Start listening at boot so history builds up between refreshes.
        mqtt_store.start()

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        status = mqtt_store.get_status()
        topics = mqtt_store.get_topics()
        template_params["mqtt_status"] = status
        template_params["mqtt_topics"] = [
            {"topic": topic, "fields": mqtt_store.get_fields(topic)} for topic in topics
        ]
        return template_params

    def generate_image(self, settings, device_config):
        width, height = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            width, height = height, width

        tiles = _tiles_from_settings(settings)
        if not tiles:
            raise RuntimeError("Add at least one tile in the MQTT Dashboard settings.")

        window_hours = _to_float(settings.get("windowHours"), DEFAULT_WINDOW_HOURS)
        stale_minutes = _to_float(settings.get("staleMinutes"), DEFAULT_STALE_MINUTES)
        title = settings.get("title") or "SENSORS"

        image = Image.new("RGB", (width, height), WHITE)
        draw = ImageDraw.Draw(image)
        margin = round(min(width, height) * 0.04)
        now = time.time()

        header_bottom = _draw_header(draw, title, width, height, margin)

        gap = round(margin * 0.6)
        grid_top = header_bottom + gap
        cols, rows = _grid_shape(len(tiles), width - 2 * margin, height - margin - grid_top)
        tile_w = (width - 2 * margin - gap * (cols - 1)) / cols
        tile_h = (height - margin - grid_top - gap * (rows - 1)) / rows

        for i, tile in enumerate(tiles):
            col, row = i % cols, i // cols
            x0 = margin + col * (tile_w + gap)
            y0 = grid_top + row * (tile_h + gap)
            _draw_tile(draw, tile, (x0, y0, x0 + tile_w, y0 + tile_h), now,
                       window_hours * 3600, stale_minutes * 60)

        return image


def _tiles_from_settings(settings):
    labels = settings.get("tileLabel[]") or []
    topics = settings.get("tileTopic[]") or []
    fields = settings.get("tileField[]") or []
    units = settings.get("tileUnit[]") or []
    tiles = []
    for i, topic in enumerate(topics):
        topic = (topic or "").strip()
        if not topic:
            continue
        tiles.append({
            "topic": topic,
            "label": (labels[i] if i < len(labels) else "").strip() or topic.rsplit("/", 1)[-1],
            "field": (fields[i] if i < len(fields) else "").strip(),
            "unit": (units[i] if i < len(units) else "").strip(),
        })
    return tiles


def _to_float(value, default):
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _grid_shape(count, area_w, area_h):
    """Pick columns so tiles come out close to TARGET_TILE_ASPECT without many empty cells."""
    best = None
    for cols in range(1, count + 1):
        rows = math.ceil(count / cols)
        aspect = (area_w / cols) / (area_h / rows)
        empty = cols * rows - count
        score = abs(math.log(aspect / TARGET_TILE_ASPECT)) + 0.3 * empty
        if best is None or score < best[0]:
            best = (score, cols, rows)
    return best[1], best[2]


def _fit_font(draw, text, max_w, size, weight="normal", min_size=10):
    font = get_font("Jost", size, weight)
    while size > min_size and draw.textlength(text, font=font) > max_w:
        size -= 1
        font = get_font("Jost", size, weight)
    return font


def _draw_header(draw, title, width, height, margin):
    status = mqtt_store.get_status()
    if status.get("connected"):
        right = datetime.now().strftime("%H:%M")
    else:
        right = f"BROKER OFFLINE · {datetime.now():%H:%M}"
    small_font = get_font("Jost", round(min(width, height) * 0.045))
    right_w = draw.textlength(right, font=small_font)

    header_font = _fit_font(draw, title.upper(), width - 2 * margin - right_w - margin,
                            round(min(width, height) * 0.08), "bold")
    draw.text((margin, margin), title.upper(), font=header_font, fill=BLACK)
    header_bottom = margin + header_font.getbbox("Ag")[3]
    draw.text((width - margin - right_w, header_bottom), right, font=small_font, fill=BLACK, anchor="ls")

    rule_y = header_bottom + round(margin * 0.5)
    draw.line((margin, rule_y, width - margin, rule_y), fill=BLACK, width=max(2, round(height * 0.005)))
    return rule_y


def _resolve_value(payload, field):
    """Return (numeric value or None, display text, field used for history)."""
    fields = mqtt_store.numeric_fields(payload)
    if field:
        if field in fields:
            return fields[field], None, field
        return None, "no field " + field, None
    if "" in fields:
        return fields[""], None, ""
    if len(fields) == 1:
        only = next(iter(fields))
        return fields[only], None, only

    # Not a single number: show it as text, e.g. "open" or "pressed".
    try:
        decoded = json.loads(payload)
        if isinstance(decoded, str):
            payload = decoded
    except ValueError:
        pass
    return None, payload.strip(), None


def _format_number(value, integral=False):
    """Format for display. Pass integral=True when the sensor reports whole numbers, so
    a float sensor reading exactly 38.0 still shows "38.0" and the width doesn't jump."""
    magnitude = abs(value)
    if integral or magnitude >= 100:
        return f"{value:.0f}"
    if magnitude >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _format_age(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _draw_tile(draw, tile, box, now, window_seconds, stale_seconds):
    x0, y0, x1, y1 = box
    tile_w, tile_h = x1 - x0, y1 - y0
    pad = round(min(tile_w, tile_h) * 0.08)
    radius = round(min(tile_w, tile_h) * 0.06)
    draw.rounded_rectangle(box, radius=radius, outline=BLACK, width=2)

    inner_w = tile_w - 2 * pad
    label_font = _fit_font(draw, tile["label"].upper(), inner_w * 0.7, round(tile_h * 0.11), "bold")
    small_size = max(10, round(tile_h * 0.085))
    small_font = get_font("Jost", small_size)
    label_bottom = y0 + pad + label_font.getbbox("Ag")[3]
    draw.text((x0 + pad, y0 + pad), tile["label"].upper(), font=label_font, fill=BLACK)

    latest = mqtt_store.get_latest(tile["topic"])
    if latest is None:
        draw.text((x0 + tile_w / 2, y0 + tile_h / 2), "waiting for data", font=small_font,
                  fill=BLACK, anchor="mm")
        return

    received, payload = latest
    age = now - received
    age_text = _format_age(age)
    age_w = draw.textlength(age_text, font=small_font)
    if age > stale_seconds:
        # Inverted badge: e-ink has no gray, so stale tiles get a solid marker instead of dimming.
        badge_pad = round(small_size * 0.3)
        badge = (x1 - pad - age_w - 2 * badge_pad, label_bottom - small_size - badge_pad,
                 x1 - pad, label_bottom + badge_pad)
        draw.rectangle(badge, fill=BLACK)
        draw.text((x1 - pad - badge_pad, label_bottom), age_text, font=small_font, fill=WHITE, anchor="rs")
    else:
        draw.text((x1 - pad, label_bottom), age_text, font=small_font, fill=BLACK, anchor="rs")

    value, text, series_field = _resolve_value(payload, tile["field"])
    series = mqtt_store.get_series(tile["topic"], series_field, now - window_seconds) \
        if series_field is not None else []
    has_chart = len(series) >= 2
    value_area_bottom = y0 + tile_h * (0.62 if has_chart else 0.92)
    integral = all(v == int(v) for _, v in series) if series else (value is not None and value == int(value))

    # Value and unit, shrunk together to fit the tile width.
    shown = _format_number(value, integral) if value is not None else (text or "")
    unit = tile["unit"] if value is not None else ""
    value_size = round(tile_h * (0.32 if has_chart else 0.42))
    while True:
        value_font = get_font("Jost", value_size, "bold")
        unit_font = get_font("Jost", max(10, round(value_size * 0.45)))
        unit_gap = round(value_size * 0.12) if unit else 0
        total_w = draw.textlength(shown, font=value_font) + unit_gap + \
            (draw.textlength(unit, font=unit_font) if unit else 0)
        if total_w <= inner_w or value_size <= 12:
            break
        value_size -= 1
    baseline = (label_bottom + value_area_bottom) / 2 + value_size * 0.35
    draw.text((x0 + pad, baseline), shown, font=value_font, fill=BLACK, anchor="ls")
    if unit:
        unit_x = x0 + pad + draw.textlength(shown, font=value_font) + unit_gap
        draw.text((unit_x, baseline), unit, font=unit_font, fill=BLACK, anchor="ls")

    if has_chart:
        _draw_sparkline(draw, series, (x0 + pad, value_area_bottom, x1 - pad, y1 - pad), small_font, now,
                        window_seconds, integral)


def _downsample(series, start, window_seconds, bins):
    """Average points into time bins so noisy data reads as a line, not a solid block."""
    sums = {}
    for ts, v in series:
        b = min(bins - 1, int((ts - start) / window_seconds * bins))
        total, count, last_ts = sums.get(b, (0.0, 0, ts))
        sums[b] = (total + v, count + 1, max(last_ts, ts))
    return [(sums[b][2], sums[b][0] / sums[b][1]) for b in sorted(sums)]


def _draw_sparkline(draw, series, box, font, now, window_seconds, integral):
    x0, y0, x1, y1 = box
    values = [v for _, v in series]
    lo, hi = min(values), max(values)
    caption = f"{_format_number(lo, integral)} – {_format_number(hi, integral)}"
    caption_h = font.getbbox("Ag")[3]
    chart_bottom = y1 - caption_h - 4
    span = hi - lo or 1.0
    start = now - window_seconds

    series = _downsample(series, start, window_seconds, max(2, int((x1 - x0) / 4)))
    if len(series) < 2:
        return
    points = [
        (x0 + (x1 - x0) * (ts - start) / window_seconds,
         chart_bottom - (chart_bottom - y0) * (v - lo) / span)
        for ts, v in series
    ]
    draw.line(points, fill=BLACK, width=max(2, round((y1 - y0) * 0.03)), joint="curve")
    draw.text((x1, y1), caption, font=font, fill=BLACK, anchor="rs")
