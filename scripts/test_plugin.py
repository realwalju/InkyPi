"""Render offline Today layout samples at common e-ink display sizes."""
import argparse
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from plugins.today.layout import render_dashboard


def sample_data():
    return {
        "now": datetime(2026, 10, 14, 9, 30, tzinfo=ZoneInfo("America/Los_Angeles")),
        "title": "Today / sample",
        "time_format": "12h",
        "reminder": "Bring the library books back",
        "weather": {
            "label": "Outside", "message": None, "temperature": "18", "unit": "°C",
            "description": "Partly cloudy", "feels_like": "17", "high": "22", "low": "13", "rain": "10",
        },
        "agenda": {
            "events": [
                {"when": "Today · 10:30 AM", "title": "Project check-in"},
                {"when": "Today · 2:00 PM", "title": "Workshop: test the new sensor"},
                {"when": "Tomorrow · All day", "title": "Library books due"},
            ],
            "message": "", "warning": "",
        },
        "sensors": [
            {"label": "Room", "value": "21.5", "unit": "°C", "status": "just now", "stale": False},
            {"label": "Humidity", "value": "45", "unit": "%", "status": "1m ago", "stale": False},
            {"label": "Node", "value": "online", "unit": "", "status": "Stale · 30m ago", "stale": True},
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "mock_display_output" / "today")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = sample_data()
    for width, height in [(800, 480), (480, 800), (600, 448), (400, 300), (300, 400)]:
        path = args.output_dir / f"today-sample-{width}x{height}.png"
        render_dashboard((width, height), data).save(path)
        print(path)
    empty = deepcopy(data)
    empty.update(
        reminder="", sensors=[],
        weather={"label": "Weather", "message": "Weather unavailable"},
        agenda={"events": [], "message": "Calendar unavailable", "warning": ""},
    )
    render_dashboard((800, 480), empty).save(args.output_dir / "today-offline.png")
    long = deepcopy(data)
    long["reminder"] = "A very long reminder that needs to be shortened to remain inside the screen"
    long["agenda"]["warning"] = "Some calendars unavailable"
    long["agenda"]["events"][0]["title"] = "A long event title with extra details that will not fit in a small panel"
    long["sensors"][0].update(label="An unusually long room temperature label", value="Missing field", unit="")
    render_dashboard((400, 300), long).save(args.output_dir / "today-long-text.png")


if __name__ == "__main__":
    main()

