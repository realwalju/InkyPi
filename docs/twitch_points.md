# Twitch Points

Shows the Twitch channel points collected by [Twitch-Channel-Points-Miner-v2](https://github.com/rdavydov/Twitch-Channel-Points-Miner-v2) as a grid of tiles: one per channel, with the current balance, the change over the last 24 hours, 7 days or 30 days, and a chart of the balance. Channels the miner is watching right now carry a **LIVE** badge; the others show how long ago they last earned points.

## How it works

The miner runs as its own service on the Pi, separate from InkyPi, so restarting or updating one doesn't interrupt the other. With `enable_analytics=True` it keeps one JSON file per channel in `/opt/twitch-miner/analytics/<your username>/`. At refresh time the plugin reads those files. It never talks to Twitch itself and needs no API key.

A channel counts as live when it earned points in the last 20 minutes. The header shows the total change across every channel, or `MINER STOPPED` when the `twitch-miner` service isn't running.

Automated point collection is against Twitch's terms of service. Use it at your own risk.

## 1. Install the miner on the Pi

From the InkyPi folder:

```bash
sudo bash install/twitch_miner/install.sh
```

This downloads the miner to `/opt/twitch-miner`, installs its dependencies in their own virtual environment, and adds a `twitch-miner` service that starts at boot. It does not start the miner yet.

## 2. Configure it

Edit `/opt/twitch-miner/run.py` and set your Twitch username and the channels to mine:

```bash
nano /opt/twitch-miner/run.py
```

If you already run the miner elsewhere, copy your existing `run.py` over this one instead. Make sure it has `enable_analytics=True`, and stop the miner on the other machine so two copies don't watch on the same account.

## 3. Start it and log in

```bash
sudo systemctl start twitch-miner
```
```bash
journalctl -u twitch-miner -f
```

On the first start the log shows a code. Open <https://www.twitch.tv/activate> on any device, sign in, and enter it. The miner saves the login in `/opt/twitch-miner/cookies/`, so this is only needed once. To skip it, copy `cookies/<your username>.pkl` from an existing install before starting.

## 4. Add the plugin

Open **Twitch Points** in the web UI. The settings page shows whether the miner is running. The defaults work with the install above; the options are:

- **Analytics Folder:** only needed if the miner lives somewhere other than `/opt/twitch-miner`
- **Chart Window:** 24 hours, 7 days or 30 days, used for both the chart and the change figure
- **Order:** live channels first, most points, or by name
- **Channels Shown:** the most tiles to draw (default 6)

Points only change every few minutes, so a refresh interval of 15 minutes or more is plenty.

## Maintenance

| Task | Command |
| --- | --- |
| Update the miner | `sudo bash install/twitch_miner/install.sh` |
| Restart after editing `run.py` | `sudo systemctl restart twitch-miner` |
| See what it's doing | `journalctl -u twitch-miner -f` |
| Stop mining | `sudo systemctl disable --now twitch-miner` |
