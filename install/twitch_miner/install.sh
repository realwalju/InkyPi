#!/bin/bash
# Installs rdavydov's Twitch-Channel-Points-Miner-v2 as a systemd service next to InkyPi.
# The Twitch Points plugin reads the analytics files it writes. See docs/twitch_points.md.
#
#   sudo bash install/twitch_miner/install.sh
#
# Safe to run again: it updates the miner and its dependencies and keeps run.py,
# cookies, analytics and logs.
set -euo pipefail

MINER_DIR="/opt/twitch-miner"
REPO_URL="https://github.com/rdavydov/Twitch-Channel-Points-Miner-v2.git"
SERVICE_NAME="twitch-miner"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-root}"

if [ "$EUID" -ne 0 ]; then
  echo "Run this with sudo." >&2
  exit 1
fi

as_user() {
  sudo -u "$RUN_USER" "$@"
}

echo "Installing packages"
apt-get install -y git python3-venv > /dev/null

mkdir -p "$MINER_DIR"
chown "$RUN_USER": "$MINER_DIR"

if [ -d "$MINER_DIR/.git" ]; then
  echo "Updating the miner in $MINER_DIR"
  as_user git -C "$MINER_DIR" pull --ff-only
else
  echo "Downloading the miner to $MINER_DIR"
  as_user git clone --depth 1 "$REPO_URL" "$MINER_DIR"
fi

echo "Installing Python dependencies (this can take a few minutes)"
[ -d "$MINER_DIR/venv" ] || as_user python3 -m venv "$MINER_DIR/venv"
as_user "$MINER_DIR/venv/bin/pip" install --quiet --upgrade pip
as_user "$MINER_DIR/venv/bin/pip" install --quiet -r "$MINER_DIR/requirements.txt"

if [ ! -f "$MINER_DIR/run.py" ]; then
  as_user cp "$SCRIPT_DIR/run.py.example" "$MINER_DIR/run.py"
  chmod 600 "$MINER_DIR/run.py"
  echo "Created $MINER_DIR/run.py from the example"
fi

echo "Installing the $SERVICE_NAME service"
sed "s/__USER__/$RUN_USER/" "$SCRIPT_DIR/$SERVICE_NAME.service" > "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" > /dev/null 2>&1

if systemctl is-active --quiet "$SERVICE_NAME"; then
  systemctl restart "$SERVICE_NAME"
  echo "Restarted the miner."
  exit 0
fi

cat <<EOF

Done. The miner is installed but not started yet.

1. Put your Twitch username and channels in $MINER_DIR/run.py
   (or copy your existing run.py there and set enable_analytics=True):
       nano $MINER_DIR/run.py
2. Start it:
       sudo systemctl start $SERVICE_NAME
3. First start only, approve the login. Watch the log for the code,
   then enter it at https://www.twitch.tv/activate:
       journalctl -u $SERVICE_NAME -f
EOF
