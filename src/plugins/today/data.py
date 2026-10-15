"""Independent data sources: a failed source never hides the rest of Today."""

import json
import logging
import math
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse

import icalendar
import recurring_ical_events
import requests

from plugins.mqtt_dashboard import mqtt_store

logger = logging.getLogger(__name__)
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MAX_CALENDARS = 5
MAX_EVENTS = 3
MAX_SENSORS = 3


def clock_time(value, time_format):
    return value.strftime("%H:%M") if time_format == "24h" else value.strftime("%I:%M %p").lstrip("0")


def number(value, decimals=0):
    if value is None or isinstance(value, bool):
        return "—"
    try:
        value = float(value)
        if not math.isfinite(value):
            return "—"
        return f"{value:.{decimals}f}"
    except (ValueError, TypeError):
        return "—"


def weather_description(code):
    descriptions = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Freezing fog", 51: "Light drizzle", 53: "Drizzle",
        55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
        61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain",
        67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
        77: "Snow grains", 80: "Light showers", 81: "Showers", 82: "Heavy showers",
        85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
        96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
    }
    return descriptions.get(code, "Conditions unavailable")


def get_weather(settings, tz):
    result = {"label": str(settings.get("locationName") or "Weather"), "message": "Add a weather location"}
    lat, lon = settings.get("latitude"), settings.get("longitude")
    if lat in (None, "") and lon in (None, ""):
        return result
    try:
        lat, lon = float(lat), float(lon)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except (TypeError, ValueError):
        result["message"] = "Check latitude and longitude"
        return result

    fahrenheit = settings.get("units", "metric") == "imperial"
    try:
        with requests.get(WEATHER_URL, params={
            "latitude": lat, "longitude": lon, "timezone": str(tz), "forecast_days": 1,
            "temperature_unit": "fahrenheit" if fahrenheit else "celsius",
            "current": "temperature_2m,apparent_temperature,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        }, timeout=(5, 15)) as response:
            response.raise_for_status()
            payload = response.json()
        current = payload["current"]
        temperature = number(current.get("temperature_2m"))
        if temperature == "—":
            raise ValueError("Missing current temperature")
        daily = payload.get("daily") or {}

        def first(key):
            values = daily.get(key) or []
            return values[0] if values else None

        result.update(
            message=None, temperature=temperature, unit="°F" if fahrenheit else "°C",
            description=weather_description(current.get("weather_code")),
            feels_like=number(current.get("apparent_temperature")),
            high=number(first("temperature_2m_max")), low=number(first("temperature_2m_min")),
            rain=number(first("precipitation_probability_max")),
        )
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        logger.warning("Today: weather unavailable")
        result["message"] = "Weather unavailable"
    return result


def _local_datetime(value, tz):
    # Floating ICS times belong to the device timezone, not the operating system timezone.
    if not isinstance(value, datetime):
        return datetime.combine(value, time.min, tzinfo=tz)
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def agenda_events(calendar, now, time_format):
    tz = now.tzinfo
    start = datetime.combine(now.date(), time.min, tzinfo=tz)
    horizon = datetime.combine(now.date() + timedelta(days=7), time.min, tzinfo=tz)
    result = []
    for event in recurring_ical_events.of(calendar).between(start, horizon):
        if str(event.get("status", "")).upper() == "CANCELLED":
            continue
        try:
            raw_start = event.decoded("dtstart")
            all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)
            begins = _local_datetime(raw_start, tz)
            if "dtend" in event:
                ends = _local_datetime(event.decoded("dtend"), tz)
            elif "duration" in event:
                ends = begins + event.decoded("duration")
            else:
                ends = begins + timedelta(days=1) if all_day else begins
            if (ends <= now and begins < now) or begins >= horizon:
                continue
            day = "Today" if begins.date() <= now.date() else (
                "Tomorrow" if begins.date() == now.date() + timedelta(days=1)
                else f"{begins:%a} {begins.day}"
            )
            if all_day:
                when = f"{day} · All day"
            elif begins <= now < ends:
                when = f"Now · until {clock_time(ends, time_format)}"
            else:
                when = f"{day} · {clock_time(begins, time_format)}"
            result.append({
                "start": begins, "when": when,
                "title": str(event.get("summary") or "Untitled event"),
            })
        except (ValueError, KeyError, TypeError):
            logger.warning("Today: skipped an invalid calendar event")
    return result


def get_agenda(settings, now, time_format):
    urls = list(dict.fromkeys(line.strip() for line in str(settings.get("calendarUrls") or "").splitlines() if line.strip()))
    if not urls:
        return {"events": [], "message": "Add a calendar to see what's next", "warning": ""}
    events, failures = [], 0
    for url in urls[:MAX_CALENDARS]:
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://"):]
        try:
            if urlparse(url).scheme not in ("http", "https"):
                raise ValueError("Expected an HTTP calendar URL")
            with requests.get(url, timeout=(5, 15)) as response:
                response.raise_for_status()
                calendar = icalendar.Calendar.from_ical(response.content)
            events.extend(agenda_events(calendar, now, time_format))
        except Exception:
            # ICS links may contain access tokens. Do not put the URL or exception in logs.
            logger.warning("Today: a calendar could not be loaded")
            failures += 1
    events.sort(key=lambda event: event["start"])
    message = "" if events else ("Calendar unavailable" if failures else "No upcoming events this week")
    warning = "Some calendars unavailable" if failures and failures < min(len(urls), MAX_CALENDARS) else ""
    return {"events": events[:MAX_EVENTS], "message": message, "warning": warning}


def sensor_value(payload, field):
    try:
        value = json.loads(payload)
    except (ValueError, TypeError):
        value = payload
    if field:
        for part in field.split("."):
            if not isinstance(value, dict) or part not in value:
                return "Missing field"
            value = value[part]
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, (int, float)):
        shown = number(value, 1)
        return shown.removesuffix(".0")
    if isinstance(value, (dict, list)):
        return "Choose a field"
    return "—" if value is None else str(value).strip() or "—"


def get_sensors(settings, now):
    topics = [str(settings.get(f"sensorTopic{i}") or "").strip() for i in range(1, MAX_SENSORS + 1)]
    if not any(topics):
        return []
    try:
        mqtt_store.start()
    except Exception:
        logger.warning("Today: MQTT listener unavailable")
    connected = mqtt_store.get_status().get("connected", False)
    try:
        stale_minutes = max(1, min(1440, int(settings.get("staleMinutes") or 15)))
    except (TypeError, ValueError):
        stale_minutes = 15
    result = []
    for i, topic in enumerate(topics, 1):
        if not topic:
            continue
        latest = mqtt_store.get_latest(topic)
        row = {
            "label": str(settings.get(f"sensorLabel{i}") or topic.rsplit("/", 1)[-1]),
            "value": "—", "unit": "", "status": "Waiting for data" if connected else "Broker offline",
            "stale": True,
        }
        if latest:
            received, payload = latest
            age = max(0, now - received)
            minutes = int(age // 60)
            age_label = "just now" if minutes == 0 else (f"{minutes}m ago" if minutes < 60 else f"{minutes // 60}h ago")
            stale = age > stale_minutes * 60
            prefix = "Offline · " if not connected else ("Stale · " if stale else "")
            row.update(
                value=sensor_value(payload, str(settings.get(f"sensorField{i}") or "").strip()),
                unit=str(settings.get(f"sensorUnit{i}") or ""), status=prefix + age_label,
                stale=stale or not connected,
            )
        result.append(row)
    return result
