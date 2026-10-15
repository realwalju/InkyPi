"""Responsive, high-contrast layout; each panel is clipped to its own bounds."""

from PIL import Image, ImageDraw
from utils.app_utils import get_font

from .data import clock_time


def _line(draw, text, x, y, width, size, bold=False, fill="black"):
    text = " ".join(str(text).split())
    size = max(9, round(size))
    font = get_font("Jost", size, "bold" if bold else "normal")
    while size > 10 and draw.textlength(text, font=font) > width:
        size -= 1
        font = get_font("Jost", size, "bold" if bold else "normal")
    if draw.textlength(text, font=font) > width:
        while text and draw.textlength(text + "…", font=font) > width:
            text = text[:-1]
        text += "…"
    draw.text((x, y), text, font=font, fill=fill, anchor="lt")


def _paragraph(draw, text, x, y, width, size, lines=2, fill="black", bold=False):
    size = max(10, round(size))
    font = get_font("Jost", size, "bold" if bold else "normal")
    words = str(text).split()
    for row in range(lines):
        if not words:
            break
        current = words.pop(0)
        while words and draw.textlength(current + " " + words[0], font=font) <= width:
            current += " " + words.pop(0)
        if row == lines - 1 and words:
            current += "…"
        # Keep the body size consistent; truncate a long word instead of shrinking a paragraph.
        while current and draw.textlength(current, font=font) > width:
            current = current[:-2] + "…" if len(current) > 1 else ""
        draw.text((x, y + row * size * 1.3), current, font=font, fill=fill, anchor="lt")


def _panel(image, box, draw_content, data, scale):
    x, y, width, height = [round(value) for value in box]
    panel = Image.new("RGB", (max(1, width), max(1, height)), "white")
    draw = ImageDraw.Draw(panel)
    draw_content(draw, data, width, height, scale)
    image.paste(panel, (x, y))


def _weather(draw, data, width, height, scale):
    pad = max(8, round(16 * scale))
    inner = width - 2 * pad
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=round(8 * scale), outline="black", width=max(1, round(2 * scale)))
    _line(draw, data["label"].upper(), pad, pad, inner, 15 * scale, bold=True)
    if data.get("message"):
        _paragraph(draw, data["message"], pad, height * .4, inner, 22 * scale)
        return
    # Reserve the lower half for conditions and today's range.
    _line(draw, data["temperature"] + data["unit"], pad, height * .20, inner, min(70 * scale, height * .32), bold=True)
    _line(draw, data["description"], pad, height * .57, inner, 21 * scale)
    _line(draw, f"High {data['high']}°  /  Low {data['low']}°", pad, height * .73, inner, 17 * scale)
    _line(draw, f"Feels {data['feels_like']}° · Precip. {data['rain']}%", pad, height * .87, inner, 14 * scale)


def _agenda(draw, data, width, height, scale):
    heading = max(24, round(29 * scale))
    warning_height = max(14, round(20 * scale)) if data.get("warning") else 0
    events = data["events"]
    capacity = max(1, int((height - heading - warning_height) / max(28, 43 * scale)))
    visible = events[:capacity]
    hidden = len(events) - len(visible)
    label = f"UP NEXT · {hidden} MORE" if hidden else "UP NEXT"
    _line(draw, label, 0, 0, width, 15 * scale, bold=True)
    if not events:
        _paragraph(draw, data["message"], 0, heading + 12 * scale, width, 22 * scale, lines=3)
    else:
        row_height = (height - heading - warning_height) / len(visible)
        for index, event in enumerate(visible):
            y = heading + index * row_height
            _line(draw, event["when"], 0, y, width, min(14 * scale, row_height * .23))
            title_offset = max(13, 18 * scale)
            title_y = y + title_offset
            size = max(10, min(21 * scale, row_height * .42))
            lines = max(1, min(2, int((row_height - title_offset - 5) / (max(10, round(size)) * 1.3))))
            _paragraph(draw, event["title"], 0, title_y, width, size, lines=lines, bold=True)
            if index < len(visible) - 1:
                draw.line((0, y + row_height - 5 * scale, width, y + row_height - 5 * scale), fill="black")
    if warning_height:
        _line(draw, data["warning"], 0, height - warning_height, width, 12 * scale, bold=True)


def _sensor(draw, data, width, height, scale):
    pad = max(6, round(10 * scale))
    inner = width - 2 * pad
    draw.line((0, 0, width, 0), fill="black", width=max(1, round(2 * scale)))
    _line(draw, data["label"].upper(), pad, pad, inner, 12 * scale, bold=True)
    value = data["value"] + (" " + data["unit"] if data["unit"] and data["value"] not in ("—", "Missing field", "Choose a field") else "")
    _line(draw, value, pad, height * .32, inner, 29 * scale, bold=True)
    _line(draw, data["status"], pad, height - max(13, round(18 * scale)), inner, 11 * scale, bold=data["stale"])


def _reminder(draw, text, width, height, scale):
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=round(6 * scale), fill="black")
    pad = max(6, round(12 * scale))
    _line(draw, "REMEMBER", pad, pad, width - 2 * pad, 11 * scale, bold=True, fill="white")
    _line(draw, text, pad, height * .48, width - 2 * pad, 22 * scale, fill="white")


def render_dashboard(dimensions, data):
    width, height = dimensions
    portrait = height > width
    scale = min(width / (480 if portrait else 800), height / (800 if portrait else 480))
    margin = max(10, round(min(dimensions) * .045))
    gap = max(8, round(14 * scale))
    inner_width = width - 2 * margin
    image = Image.new("RGB", dimensions, "white")
    draw = ImageDraw.Draw(image)
    now = data["now"]

    _line(draw, data["title"].upper(), margin, margin, inner_width * .49, 34 * scale, bold=True)
    date_label = f"{now:%a}, {now:%b} {now.day}, {now.year}"
    _line(draw, date_label, margin + inner_width * .53, margin + 9 * scale, inner_width * .47, 21 * scale)
    rule_y = margin + max(32, round(50 * scale))
    draw.line((margin, rule_y, width - margin, rule_y), fill="black", width=max(1, round(2 * scale)))
    top = rule_y + gap
    footer_y = height - margin - max(11, round(14 * scale))
    updated = "Updated " + clock_time(now, data["time_format"])
    _line(draw, updated, margin + inner_width * .55, footer_y, inner_width * .45, 11 * scale)
    if data["weather"]:
        _line(draw, "Weather: Open-Meteo", margin, footer_y, inner_width * .5, 11 * scale)
    bottom = footer_y - gap

    if data["reminder"]:
        reminder_height = max(38, round(56 * scale))
        _panel(image, (margin, bottom - reminder_height, inner_width, reminder_height), _reminder, data["reminder"], scale)
        bottom -= reminder_height + gap
    if data["sensors"]:
        sensor_height = max(60, round((100 if portrait else 84) * scale))
        sensor_width = (inner_width - gap * (len(data["sensors"]) - 1)) / len(data["sensors"])
        for index, sensor in enumerate(data["sensors"]):
            _panel(image, (margin + index * (sensor_width + gap), bottom - sensor_height, sensor_width, sensor_height), _sensor, sensor, scale)
        bottom -= sensor_height + gap

    available_height = max(1, bottom - top)
    weather, agenda = data["weather"], data["agenda"]
    if weather and agenda:
        if portrait:
            weather_height = available_height * .43
            _panel(image, (margin, top, inner_width, weather_height), _weather, weather, scale)
            _panel(image, (margin, top + weather_height + gap, inner_width, available_height - weather_height - gap), _agenda, agenda, scale)
        else:
            weather_width = inner_width * .40
            _panel(image, (margin, top, weather_width, available_height), _weather, weather, scale)
            _panel(image, (margin + weather_width + gap, top, inner_width - weather_width - gap, available_height), _agenda, agenda, scale)
    elif weather or agenda:
        _panel(image, (margin, top, inner_width, available_height), _weather if weather else _agenda, weather or agenda, scale)
    elif not data["reminder"] and not data["sensors"]:
        _paragraph(draw, "Add weather, a calendar, or a reminder in Today settings.", margin, top + gap, inner_width, 24 * scale)
    return image
