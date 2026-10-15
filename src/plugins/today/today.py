"""A daily overview drawn directly with Pillow for e-ink displays."""

from datetime import datetime
from zoneinfo import ZoneInfo

from plugins.base_plugin.base_plugin import BasePlugin
from plugins.mqtt_dashboard import mqtt_store

from .data import get_agenda, get_sensors, get_weather
from .layout import render_dashboard


class Today(BasePlugin):
    def generate_settings_template(self):
        params = super().generate_settings_template()
        params["mqtt_topics"] = mqtt_store.get_topics()
        return params

    def generate_image(self, settings, device_config):
        tz = ZoneInfo(device_config.get_config("timezone", default="UTC") or "UTC")
        now = datetime.now(tz)
        time_format = device_config.get_config("time_format", default="12h")
        data = {
            "now": now,
            "time_format": time_format,
            "title": str(settings.get("title") or "Today").strip(),
            "reminder": str(settings.get("reminder") or "").strip(),
            "weather": get_weather(settings, tz) if settings.get("showWeather") != "false" else None,
            "agenda": get_agenda(settings, now, time_format) if settings.get("showCalendar") != "false" else None,
            "sensors": get_sensors(settings, now.timestamp()),
        }
        width, height = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            width, height = height, width
        return render_dashboard((width, height), data)
