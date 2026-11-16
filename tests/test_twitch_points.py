import json

from plugins.twitch_points import points_data
from plugins.twitch_points.twitch_points import render

NOW = 1_800_000_000
HOUR = 3600


def write_channel(folder, name, points):
    """points: (seconds before NOW, balance, reason)"""
    folder.mkdir(parents=True, exist_ok=True)
    series = [{"x": (NOW - ago) * 1000, "y": balance, "z": reason} for ago, balance, reason in points]
    (folder / f"{name}.json").write_text(json.dumps({"series": series, "annotations": []}))


def test_change_is_measured_from_the_balance_at_the_start_of_the_window(tmp_path):
    write_channel(tmp_path / "me", "alpha", [
        (30 * HOUR, 1000, "Watch"), (25 * HOUR, 1100, "Watch"),
        (5 * HOUR, 1300, "Watch Streak"), (60, 1310, "Watch"),
    ])
    [channel] = points_data.load_channels(str(tmp_path), NOW, 24 * HOUR)

    assert channel["name"] == "alpha"
    assert channel["points"] == 1310
    assert channel["change"] == 210
    assert channel["mining"] is True
    assert channel["series"] == [(NOW - 24 * HOUR, 1100), (NOW - 5 * HOUR, 1300), (NOW - 60, 1310)]


def test_losses_and_channels_with_no_recent_activity(tmp_path):
    write_channel(tmp_path / "me", "bets", [(3 * HOUR, 5000, "Watch"), (2 * HOUR, 4000, "Prediction")])
    write_channel(tmp_path / "me", "quiet", [(90 * HOUR, 700, "Watch")])
    channels = {c["name"]: c for c in points_data.load_channels(str(tmp_path), NOW, 24 * HOUR)}

    assert channels["bets"]["change"] == -1000
    assert channels["bets"]["mining"] is False
    assert channels["quiet"]["change"] == 0
    assert channels["quiet"]["series"] == [(NOW - 24 * HOUR, 700)]


def test_unreadable_and_temporary_files_are_skipped(tmp_path):
    write_channel(tmp_path / "me", "good", [(60, 10, "Watch")])
    (tmp_path / "me" / "broken.json").write_text("{not json")
    (tmp_path / "me" / "good.json.temp").write_text("{}")
    (tmp_path / "me" / "empty.json").write_text("{}")

    assert [c["name"] for c in points_data.load_channels(str(tmp_path), NOW, 24 * HOUR)] == ["good"]
    assert points_data.load_channels(str(tmp_path / "missing"), NOW, 24 * HOUR) == []


def test_default_order_puts_channels_being_mined_first(tmp_path):
    write_channel(tmp_path, "rich", [(5 * HOUR, 90000, "Watch")])
    write_channel(tmp_path, "live", [(120, 50, "Watch")])
    write_channel(tmp_path, "recent", [(1 * HOUR, 300, "Watch")])
    channels = points_data.load_channels(str(tmp_path), NOW, 24 * HOUR)

    assert [c["name"] for c in points_data.sort_channels(channels, None)] == ["live", "recent", "rich"]
    assert [c["name"] for c in points_data.sort_channels(channels, "points")] == ["rich", "recent", "live"]
    assert [c["name"] for c in points_data.sort_channels(channels, "name")] == ["live", "recent", "rich"]


def test_render_fills_common_display_sizes(tmp_path):
    for i in range(5):
        write_channel(tmp_path, f"channel{i}", [(20 * HOUR, 1000 * i, "Watch"), (i * HOUR + 60, 1000 * i + 250, "Watch")])
    channels = points_data.load_channels(str(tmp_path), NOW, 24 * HOUR)

    for size in [(800, 480), (480, 800), (400, 300)]:
        image = render(size, channels, NOW, 24, "Channel Points", 1250, miner_running=False)
        assert image.size == size
        assert image.getcolors(maxcolors=100000) and len(image.getcolors(maxcolors=100000)) > 1
