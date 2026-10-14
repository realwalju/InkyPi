import os
import re
from datetime import datetime
from PIL import Image, ImageDraw
from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import get_font

PC_FILE = "/home/walju/pc_stats.txt"  # must match DestPath in windows_scripts/pc_sync.ps1

# (key in file, setting toggle, display label)
STATS_MAP = [
    ('cpu', 'show_cpu', 'CPU'),
    ('gpu', 'show_gpu', 'GPU'),
    ('ram', 'show_ram', 'RAM'),
    ('ssd', 'show_disk', 'SSD'),
    ('localip', 'show_local_ip', 'IP'),
    ('extip', 'show_ext_ip', 'EXT'),
    ('focus', 'show_focus', 'WIN'),
]

# The "Font Size" setting keeps its original 12/14/16 values but now scales the layout.
FONT_SCALES = {'12': 0.85, '14': 1.0, '16': 1.15}

# Data older than this is flagged, e.g. when the PC is off or the sync script stopped.
STALE_AFTER_SECONDS = 10 * 60

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


class PCStats(BasePlugin):
    def generate_image(self, settings, device_config):
        width, height = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            width, height = height, width

        image = Image.new("RGB", (width, height), WHITE)
        draw = ImageDraw.Draw(image)

        def is_on(key):
            val = settings.get(key, False)
            if isinstance(val, str):
                return val.lower() == 'true'
            return bool(val)

        title = settings.get('title') or 'WINDOWS PC'
        scale = FONT_SCALES.get(str(settings.get('font_size_base', '14')), 1.0)
        margin = round(min(width, height) * 0.05)

        content_w = width - 2 * margin

        # Header: title on the left, time the data was last received on the right.
        stamp = None
        if os.path.exists(PC_FILE):
            modified = os.path.getmtime(PC_FILE)
            stamp = datetime.fromtimestamp(modified).strftime("%H:%M")
            if datetime.now().timestamp() - modified > STALE_AFTER_SECONDS:
                stamp = f"STALE · {stamp}"

        small_font = get_font("Jost", round(min(width, height) * 0.05))
        stamp_w = draw.textlength(stamp, font=small_font) if stamp else 0
        header_size = round(height * 0.09)
        header_font = get_font("Jost", header_size, "bold")
        # Shrink the title until it fits beside the timestamp (matters in vertical orientation).
        while header_size > 10 and draw.textlength(title.upper(), font=header_font) + stamp_w + margin > content_w:
            header_size -= 1
            header_font = get_font("Jost", header_size, "bold")
        draw.text((margin, margin), title.upper(), font=header_font, fill=BLACK)
        header_bottom = margin + header_font.getbbox("Ag")[3]

        if stamp:
            stamp_y = header_bottom - small_font.getbbox("Ag")[3]
            draw.text((width - margin - stamp_w, stamp_y), stamp, font=small_font, fill=BLACK)

        rule_y = header_bottom + round(margin * 0.6)
        draw.line((margin, rule_y, width - margin, rule_y), fill=BLACK, width=max(2, round(height * 0.006)))

        if not os.path.exists(PC_FILE):
            msg_font = get_font("Jost", round(height * 0.08), "bold")
            msg = "NO DATA RECEIVED"
            msg_w = draw.textlength(msg, font=msg_font)
            draw.text(((width - msg_w) / 2, (rule_y + height) / 2), msg, font=msg_font, fill=BLACK, anchor="lm")
            return image

        data = {}
        with open(PC_FILE, "r") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    data[k.strip().lower()] = v.strip()

        rows = [(label, data[key]) for key, toggle, label in STATS_MAP if is_on(toggle) and key in data]
        if not rows:
            return image

        # Rows share the space below the rule; at least 4 slots so a short list doesn't get huge text.
        top = rule_y + margin * 0.6
        row_h = (height - margin - top) / max(len(rows), 4)
        font_size = round(row_h * 0.55 * scale)
        while True:
            label_font = get_font("Jost", font_size, "bold")
            value_font = get_font("Jost", font_size)
            gap = round(font_size * 0.6)
            label_w = max(draw.textlength(label, font=label_font) for label, _ in rows)
            value_w = max(draw.textlength(value, font=value_font) for _, value in rows)
            # Shrink until the widest label and value fit across the screen.
            if label_w + gap + value_w <= content_w or font_size <= 10:
                break
            font_size -= 1

        value_x = margin + label_w + gap
        bar_x = value_x + value_w + gap
        bar_h = round(row_h * 0.4)
        bar_outline = max(2, round(bar_h * 0.08))
        show_bars = is_on('show_bars') and width - margin - bar_x > width * 0.15

        for i, (label, value) in enumerate(rows):
            center_y = top + row_h * (i + 0.5)
            draw.text((margin, center_y), label, font=label_font, fill=BLACK, anchor="lm")
            draw.text((value_x, center_y), value, font=value_font, fill=BLACK, anchor="lm")

            percent = re.match(r'(\d+)\s*%', value)
            if show_bars and percent:
                pct = min(100, int(percent.group(1)))
                y0, y1 = center_y - bar_h / 2, center_y + bar_h / 2
                draw.rectangle([bar_x, y0, width - margin, y1], outline=BLACK, width=bar_outline)
                fill_w = (width - margin - bar_x) * pct / 100
                if fill_w > 0:
                    draw.rectangle([bar_x, y0, bar_x + fill_w, y1], fill=BLACK)

        return image
