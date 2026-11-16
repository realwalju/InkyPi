"""Reads the analytics files written by Twitch-Channel-Points-Miner-v2.

The miner (run with enable_analytics=True) keeps one JSON file per channel under
analytics/<twitch username>/<channel>.json. Each file has a "series" list of
{"x": epoch milliseconds, "y": points balance, "z": reason} entries, appended every
time the balance changes.
"""
import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

DEFAULT_ANALYTICS_DIR = "/opt/twitch-miner/analytics"
SERVICE_NAME = "twitch-miner"
# Watching a live channel earns points every 5 minutes, so a channel with a gain
# in the last 20 minutes is one the miner is watching right now.
MINING_SECONDS = 20 * 60


def _analytics_files(folder):
    """Channel files directly in the folder or one level down (the per-username folders)."""
    files = []
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name)
    except OSError:
        return files
    for entry in entries:
        if entry.is_dir():
            files.extend(_analytics_files_flat(entry.path))
        elif entry.name.endswith(".json"):
            files.append(entry.path)
    return files


def _analytics_files_flat(folder):
    try:
        return sorted(e.path for e in os.scandir(folder) if e.is_file() and e.name.endswith(".json"))
    except OSError:
        return []


def _read_series(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        logger.warning("Skipping %s: %s", path, e)
        return []
    points = []
    for entry in data.get("series") or []:
        try:
            points.append((entry["x"] / 1000, int(entry["y"]), str(entry.get("z") or "")))
        except (KeyError, TypeError, ValueError):
            continue
    points.sort(key=lambda p: p[0])
    return points


def load_channels(folder, now, window_seconds):
    """One dict per channel: name, points, change over the window, last activity, chart series."""
    start = now - window_seconds
    channels = []
    for path in _analytics_files(folder):
        points = _read_series(path)
        if not points:
            continue
        last_ts, balance, last_reason = points[-1]
        before = [p for p in points if p[0] < start]
        inside = [(ts, y) for ts, y, _ in points if ts >= start]
        # Balance at the start of the window: the last value before it, or the first one known.
        baseline = before[-1][1] if before else points[0][1]
        series = [(start if before else points[0][0], baseline)] + inside
        channels.append({
            "name": os.path.splitext(os.path.basename(path))[0],
            "points": balance,
            "change": balance - baseline,
            "last_ts": last_ts,
            "last_reason": last_reason,
            "mining": now - last_ts <= MINING_SECONDS,
            "series": series,
        })
    return channels


def sort_channels(channels, order):
    if order == "points":
        return sorted(channels, key=lambda c: -c["points"])
    if order == "name":
        return sorted(channels, key=lambda c: c["name"].lower())
    # Default: channels being mined now first, then the most recently active.
    return sorted(channels, key=lambda c: (not c["mining"], -c["last_ts"]))


def miner_running():
    """True/False from systemd, or None when that can't be determined (e.g. not on the Pi)."""
    try:
        result = subprocess.run(["systemctl", "is-active", SERVICE_NAME],
                                capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    state = result.stdout.strip()
    if state == "active":
        return True
    if state in ("inactive", "failed", "activating", "deactivating"):
        return False
    return None
