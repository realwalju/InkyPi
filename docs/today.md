# Today dashboard

Today puts weather, upcoming calendar events, a short reminder, and up to three MQTT readings on one e-ink screen. It adapts to landscape and portrait displays and renders with Pillow, without starting a browser.

## Setup

1. Open **Today** in the InkyPi web interface.
2. Enter a title and an optional reminder. Leave the reminder blank to hide it.
3. For weather, enter latitude and longitude, choose Celsius or Fahrenheit, and optionally give the location a label. [Open-Meteo](https://open-meteo.com/en/docs) supplies current temperature, conditions, feels-like temperature, today's high and low, and maximum precipitation probability. No API key is required for this personal-use setup.
4. For upcoming events, paste up to five ICS subscription URLs, one per line. These can be the same links used in the Calendar plugin; `https://` and `webcal://` links are supported. Today shows the next three events within seven days, including recurring, all-day, and ongoing events. Ended and cancelled events are omitted.
5. Optionally enter up to three MQTT topics with labels, JSON fields, and units. Topics already seen by the listener appear as suggestions. Broker configuration is shared with [MQTT Dashboard](mqtt_dashboard.md).
6. Choose **Display** to preview on the device, or add Today to a playlist and choose its refresh interval. The displayed time is the time of the last render, not a live clock.

Weather and calendar sections can be hidden independently. Blank MQTT topics hide their readings. Today does not automatically copy settings from other plugin instances.

Set the device's **timezone** and **time format** first. Calendar times, the date header, and the weather day's boundaries use that timezone. Floating calendar times (without a timezone) are interpreted in the device timezone. A missing timezone falls back to UTC.

## Missing or unavailable data

- An unconfigured section shows a setup prompt; hide that section if it is not needed.
- A failed weather request shows **Weather unavailable** while the other sections continue to render.
- A failed calendar does not hide events from working calendars. A warning identifies incomplete results. Calendar URLs are not included in this plugin's error logs.
- MQTT readings show their age. The default stale threshold is 15 minutes. Cached readings remain visible with **Offline** when the broker is disconnected; a topic with no data shows a dash, never a made-up zero.
- Dotted JSON fields can contain numbers, text, or booleans. If the payload is an object, choose a field to display. MQTT data keeps the units supplied by its publisher; the weather temperature setting does not convert sensor values.

Long event titles, labels, and reminders are shortened to fit. Smaller displays show fewer events with a **MORE** count for the remaining entries in the three-event shortlist. This is a compact overview; the existing Calendar and MQTT Dashboard plugins remain available for full views and sensor charts.

## Offline layout preview

From the project root with development dependencies installed:

```bash
python scripts/test_plugin.py
```

This renders clearly labelled sample data at several display sizes to `mock_display_output/today/`, without accessing a calendar, MQTT broker, or weather service.
