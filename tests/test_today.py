import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import icalendar
import pytest
import requests
from flask import Flask, render_template

from config import Config
from plugins.today import data
from plugins.today.today import Today

TZ = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 14, 10, tzinfo=TZ)


def calendar_text(*events):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//InkyPi Tests//EN",
                         *["BEGIN:VEVENT\r\n" + event + "\r\nEND:VEVENT" for event in events],
                         "END:VCALENDAR"])


def response_for(content=None, payload=None):
    response = MagicMock()
    response.__enter__.return_value = response
    response.content = (content or "").encode()
    response.json.return_value = payload
    return response


def test_calendar_excludes_ended_and_cancelled_and_interprets_floating_times_locally():
    calendar = icalendar.Calendar.from_ical(calendar_text(
        "UID:old\r\nSUMMARY:Ended\r\nDTSTART:20261014T090000\r\nDTEND:20261014T093000",
        "UID:now\r\nSUMMARY:Ongoing\r\nDTSTART:20261014T093000\r\nDTEND:20261014T110000",
        "UID:utc\r\nSUMMARY:UTC event\r\nDTSTART:20261014T180000Z\r\nDTEND:20261014T190000Z",
        "UID:all\r\nSUMMARY:All day\r\nDTSTART;VALUE=DATE:20261014\r\nDTEND;VALUE=DATE:20261015",
        "UID:yesterday\r\nSUMMARY:Yesterday\r\nDTSTART;VALUE=DATE:20261013\r\nDTEND;VALUE=DATE:20261014",
        "UID:cancelled\r\nSTATUS:CANCELLED\r\nSUMMARY:Cancelled\r\nDTSTART:20261014T130000",
        "UID:repeat\r\nSUMMARY:Daily\r\nDTSTART:20261013T120000\r\nDTEND:20261013T123000\r\nRRULE:FREQ=DAILY;COUNT=3",
    ))
    events = data.agenda_events(calendar, NOW, "12h")
    titles = [event["title"] for event in events]
    assert "Ended" not in titles and "Cancelled" not in titles and "Yesterday" not in titles
    assert titles.count("Daily") == 2
    assert next(e["when"] for e in events if e["title"] == "Ongoing") == "Now · until 11:00 AM"
    assert next(e["when"] for e in events if e["title"] == "UTC event") == "Today · 11:00 AM"
    assert next(e["when"] for e in events if e["title"] == "All day") == "Today · All day"


def test_calendar_recurrence_crosses_dst_with_local_time_preserved():
    calendar = icalendar.Calendar.from_ical(calendar_text(
        "UID:dst\r\nSUMMARY:Morning\r\nDTSTART;TZID=America/Los_Angeles:20261031T090000\r\n"
        "DTEND;TZID=America/Los_Angeles:20261031T100000\r\nRRULE:FREQ=DAILY;COUNT=3"
    ))
    events = data.agenda_events(calendar, datetime(2026, 10, 31, 8, tzinfo=TZ), "24h")
    assert len(events) == 3
    assert all(event["start"].hour == 9 and event["when"].endswith("09:00") for event in events)
    assert events[0]["start"].utcoffset() != events[1]["start"].utcoffset()


def test_calendar_failure_keeps_other_calendars_sorts_and_limits(monkeypatch, caplog):
    response = response_for(calendar_text(*[
        f"UID:{hour}\r\nSUMMARY:Event {hour}\r\nDTSTART:20261014T{hour}0000"
        for hour in (16, 14, 12, 11)
    ]))
    get = MagicMock(side_effect=[requests.Timeout("private-token"), response])
    monkeypatch.setattr(data.requests, "get", get)
    result = data.get_agenda({"calendarUrls": "https://bad/private-token\nwebcal://good/calendar"}, NOW, "24h")
    assert [event["title"] for event in result["events"]] == ["Event 11", "Event 12", "Event 14"]
    assert result["warning"] == "Some calendars unavailable"
    assert "private-token" not in caplog.text
    assert get.call_args.args[0] == "https://good/calendar"
    assert response.__exit__.called


@pytest.mark.parametrize("temperature", [None, float("nan"), float("inf")])
def test_weather_missing_temperature_is_not_displayed_as_zero(monkeypatch, temperature):
    monkeypatch.setattr(data.requests, "get", MagicMock(return_value=response_for(payload={"current": {"temperature_2m": temperature}})))
    assert data.get_weather({"latitude": "0", "longitude": "0"}, TZ)["message"] == "Weather unavailable"


def test_weather_accepts_zero_and_sends_timezone_and_units(monkeypatch):
    get = MagicMock(return_value=response_for(payload={
        "current": {"temperature_2m": 0, "apparent_temperature": -2, "weather_code": 3},
        "daily": {"temperature_2m_max": [5], "temperature_2m_min": [-3], "precipitation_probability_max": [0]},
    }))
    monkeypatch.setattr(data.requests, "get", get)
    result = data.get_weather({"latitude": "0", "longitude": "0", "units": "imperial"}, TZ)
    assert result["temperature"] == "0" and result["rain"] == "0" and result["message"] is None
    assert get.call_args.kwargs["params"]["temperature_unit"] == "fahrenheit"
    assert get.call_args.kwargs["params"]["timezone"] == "America/Los_Angeles"


@pytest.mark.parametrize("latitude", ["nan", "91", "bad"])
def test_invalid_weather_coordinates_do_not_make_a_request(monkeypatch, latitude):
    get = MagicMock()
    monkeypatch.setattr(data.requests, "get", get)
    assert data.get_weather({"latitude": latitude, "longitude": "0"}, TZ)["message"] == "Check latitude and longitude"
    get.assert_not_called()


@pytest.mark.parametrize("payload,field,expected", [
    ('{"sensor":{"temperature":21.5}}', "sensor.temperature", "21.5"),
    ('{"door":"open"}', "door", "open"),
    ('{"motion":true}', "motion", "On"),
    ('{"temperature":0}', "temperature", "0"),
    ('{"temperature":null}', "temperature", "—"),
    ('{"temperature":20}', "missing", "Missing field"),
    ('{"temperature":20}', "", "Choose a field"),
    ("offline", "", "offline"), ("NaN", "", "—"),
])
def test_sensor_payloads(payload, field, expected):
    assert data.sensor_value(payload, field) == expected


@pytest.mark.parametrize("connected,age,status", [(True, 30, "just now"), (True, 1800, "Stale · 30m ago"), (False, 30, "Offline · just now")])
def test_sensor_freshness_and_offline_cache(monkeypatch, connected, age, status):
    monkeypatch.setattr(data.mqtt_store, "start", lambda: None)
    monkeypatch.setattr(data.mqtt_store, "get_status", lambda: {"connected": connected})
    monkeypatch.setattr(data.mqtt_store, "get_latest", lambda topic: (NOW.timestamp() - age, "0"))
    row = data.get_sensors({"sensorTopic1": "desk/temp"}, NOW.timestamp())[0]
    assert row["value"] == "0" and row["status"] == status
    assert row["stale"] == (not connected or age > 900)


def test_empty_settings_do_not_fetch_or_start_mqtt(monkeypatch):
    get, start = MagicMock(), MagicMock()
    monkeypatch.setattr(data.requests, "get", get)
    monkeypatch.setattr(data.mqtt_store, "start", start)
    config = MagicMock()
    config.get_resolution.return_value = (800, 480)
    config.get_config.side_effect = lambda key, default=None: {"timezone": "UTC", "orientation": "vertical"}.get(key, default)
    image = Today({"id": "today"}).generate_image({}, config)
    assert image.size == (480, 800) and image.mode == "RGB"
    get.assert_not_called()
    start.assert_not_called()


def test_settings_template_has_all_saved_fields_and_escapes_topics():
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / "src/plugins"))
    with app.app_context():
        html = render_template("today/settings.html", mqtt_topics=['room/\"><script>bad</script>'])
    assert '<script>bad</script>' not in html
    assert 'name="sensorTopic3"' in html and 'name="calendarUrls"' in html


def test_retired_playlist_entries_are_removed_without_touching_ai_image(tmp_path, monkeypatch):
    entries = [{"plugin_id": plugin, "name": plugin, "plugin_settings": {"kept": True}, "refresh": {"interval": 900}}
               for plugin in ("ai_text", "ai_image", "year_progress", "github", "hardwarebuttons")]
    path = tmp_path / "device.json"
    path.write_text(json.dumps({
        "playlist_config": {"playlists": [{"name": "Default", "start_time": "00:00", "end_time": "24:00", "plugins": entries, "current_plugin_index": 4}]},
        "refresh_info": {"plugin_id": "github", "refresh_time": NOW.isoformat()},
    }))
    monkeypatch.setattr(Config, "config_file", str(path))
    config = Config()
    playlist = config.playlist_manager.playlists[0]
    assert [p.plugin_id for p in playlist.plugins] == ["ai_image"]
    assert playlist.current_plugin_index is None
    assert playlist.plugins[0].settings == {"kept": True}
    assert config.refresh_info.plugin_id is None
    assert config.get_plugin("today") and config.get_plugin("ai_image")
    config.write_config()
    assert [p["plugin_id"] for p in json.loads(path.read_text())["playlist_config"]["playlists"][0]["plugins"]] == ["ai_image"]
