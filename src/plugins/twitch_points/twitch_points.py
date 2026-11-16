import logging
import math
import time
from datetime import datetime

from PIL import Image, ImageDraw
from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import get_font

from . import points_data

logger = logging.getLogger(__name__)

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

DEFAULT_WINDOW_HOURS = 24
DEFAULT_MAX_CHANNELS = 6
TARGET_TILE_ASPECT = 1.4  # width / height the grid layout aims for


class TwitchPoints(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["default_analytics_dir"] = points_data.DEFAULT_ANALYTICS_DIR
        template_params["miner_running"] = points_data.miner_running()
        return template_params

    def generate_image(self, settings, device_config):
        width, height = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            width, height = height, width

        folder = (settings.get("analyticsDir") or "").strip() or points_data.DEFAULT_ANALYTICS_DIR
        window_hours = _to_number(settings.get("windowHours"), DEFAULT_WINDOW_HOURS)
        max_channels = max(1, int(_to_number(settings.get("maxChannels"), DEFAULT_MAX_CHANNELS)))
        now = time.time()

        channels = points_data.load_channels(folder, now, window_hours * 3600)
        if not channels:
            raise RuntimeError(
                f"No channel points data in {folder}. Check that the miner is running "
                "with enable_analytics=True and that the folder is right.")
        shown = points_data.sort_channels(channels, settings.get("sortBy"))[:max_channels]

        return render(
            (width, height), shown, now, window_hours,
            title=settings.get("title") or "CHANNEL POINTS",
            total_change=sum(c["change"] for c in channels),
            miner_running=points_data.miner_running(),
        )


def render(dimensions, channels, now, window_hours, title, total_change, miner_running=None):
    width, height = dimensions
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    margin = round(min(width, height) * 0.04)
    window_label = _window_label(window_hours)

    clock = datetime.fromtimestamp(now).strftime("%H:%M")
    if miner_running is False:
        right = f"MINER STOPPED · {clock}"
    else:
        right = f"{_signed(total_change)} IN {window_label} · {clock}"
    header_bottom = _draw_header(draw, title, right, width, height, margin)

    gap = round(margin * 0.6)
    grid_top = header_bottom + gap
    cols, rows = _grid_shape(len(channels), width - 2 * margin, height - margin - grid_top)
    tile_w = (width - 2 * margin - gap * (cols - 1)) / cols
    tile_h = (height - margin - grid_top - gap * (rows - 1)) / rows

    for i, channel in enumerate(channels):
        col, row = i % cols, i // cols
        x0 = margin + col * (tile_w + gap)
        y0 = grid_top + row * (tile_h + gap)
        _draw_tile(draw, channel, (x0, y0, x0 + tile_w, y0 + tile_h), now,
                   window_hours * 3600, window_label)
    return image


def _to_number(value, default):
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _window_label(hours):
    if hours >= 48:
        return f"{round(hours / 24)}D"
    return f"{round(hours)}H"


def _signed(value):
    return f"+{value:,}" if value >= 0 else f"−{abs(value):,}"


def _format_age(seconds):
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


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
    size = max(min_size, round(size))
    font = get_font("Jost", size, weight)
    while size > min_size and draw.textlength(text, font=font) > max_w:
        size -= 1
        font = get_font("Jost", size, weight)
    return font


def _draw_header(draw, title, right, width, height, margin):
    small_font = _fit_font(draw, right, (width - 2 * margin) * 0.6, min(width, height) * 0.045)
    right_w = draw.textlength(right, font=small_font)
    header_font = _fit_font(draw, title.upper(), width - 2 * margin - right_w - margin,
                            min(width, height) * 0.08, "bold")
    draw.text((margin, margin), title.upper(), font=header_font, fill=BLACK)
    header_bottom = margin + header_font.getbbox("Ag")[3]
    draw.text((width - margin - right_w, header_bottom), right, font=small_font, fill=BLACK, anchor="ls")

    rule_y = header_bottom + round(margin * 0.5)
    draw.line((margin, rule_y, width - margin, rule_y), fill=BLACK, width=max(2, round(height * 0.005)))
    return rule_y


def _draw_tile(draw, channel, box, now, window_seconds, window_label):
    x0, y0, x1, y1 = box
    tile_w, tile_h = x1 - x0, y1 - y0
    pad = round(min(tile_w, tile_h) * 0.08)
    radius = round(min(tile_w, tile_h) * 0.06)
    draw.rounded_rectangle(box, radius=radius, outline=BLACK, width=2)

    inner_w = tile_w - 2 * pad
    small_size = max(10, round(tile_h * 0.085))
    small_font = get_font("Jost", small_size)
    label_font = _fit_font(draw, channel["name"].upper(), inner_w * 0.68, tile_h * 0.11, "bold")
    label_bottom = y0 + pad + label_font.getbbox("Ag")[3]
    draw.text((x0 + pad, y0 + pad), channel["name"].upper(), font=label_font, fill=BLACK)

    if channel["mining"]:
        # Inverted badge: e-ink has no gray, so the channels being watched get a solid marker.
        badge_text = "LIVE"
        badge_w = draw.textlength(badge_text, font=small_font)
        badge_pad = round(small_size * 0.3)
        draw.rectangle((x1 - pad - badge_w - 2 * badge_pad, label_bottom - small_size - badge_pad,
                        x1 - pad, label_bottom + badge_pad), fill=BLACK)
        draw.text((x1 - pad - badge_pad, label_bottom), badge_text, font=small_font, fill=WHITE, anchor="rs")
    else:
        draw.text((x1 - pad, label_bottom), _format_age(now - channel["last_ts"]), font=small_font,
                  fill=BLACK, anchor="rs")

    series = channel["series"]
    has_chart = len({y for _, y in series}) > 1
    value_area_bottom = y0 + tile_h * (0.62 if has_chart else 0.92)

    # Balance, with the change over the window beside it, shrunk together to fit the tile width.
    shown = f"{channel['points']:,}"
    change = f"{_signed(channel['change'])} / {window_label}"
    value_size = round(tile_h * (0.3 if has_chart else 0.4))
    while True:
        value_font = get_font("Jost", value_size, "bold")
        change_font = get_font("Jost", max(10, round(value_size * 0.42)))
        change_gap = round(value_size * 0.25)
        total_w = draw.textlength(shown, font=value_font) + change_gap + draw.textlength(change, font=change_font)
        if total_w <= inner_w or value_size <= 12:
            break
        value_size -= 1
    baseline = (label_bottom + value_area_bottom) / 2 + value_size * 0.35
    draw.text((x0 + pad, baseline), shown, font=value_font, fill=BLACK, anchor="ls")
    draw.text((x0 + pad + draw.textlength(shown, font=value_font) + change_gap, baseline), change,
              font=change_font, fill=BLACK, anchor="ls")

    if has_chart:
        _draw_chart(draw, series, (x0 + pad, value_area_bottom, x1 - pad, y1 - pad), now, window_seconds)


def _draw_chart(draw, series, box, now, window_seconds):
    """Balance over the window as a stepped line, since points arrive in jumps."""
    x0, y0, x1, y1 = box
    values = [y for _, y in series]
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    start = now - window_seconds

    def to_xy(ts, value):
        return (x0 + (x1 - x0) * max(0.0, min(1.0, (ts - start) / window_seconds)),
                y1 - (y1 - y0) * (value - lo) / span)

    points = [to_xy(*series[0])]
    for ts, value in series[1:]:
        x, y = to_xy(ts, value)
        points.append((x, points[-1][1]))
        points.append((x, y))
    points.append((x1, points[-1][1]))  # hold the latest balance up to now
    draw.line(points, fill=BLACK, width=max(2, round((y1 - y0) * 0.04)))
