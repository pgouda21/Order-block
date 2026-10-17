#!/usr/bin/env bash
# Install or update the scanner on the VM. Idempotent; never overwrites an existing env file.
#
#   sudo git clone <repo> /opt/marketboard     # first time
#   sudo git -C /opt/marketboard pull          # updates
#   sudo /opt/marketboard/scanner/deploy/install.sh
set -euo pipefail

APP_DIR=/opt/marketboard
STATE_DIR=/var/lib/marketboard
ENV_FILE=/etc/marketboard/env
SERVICE_USER=marketboard
PYTHON=${PYTHON:-python3.12}

die() { echo "install.sh: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root (sudo)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ "$here" == "$APP_DIR" ]] || die "repo must be checked out at $APP_DIR (found $here); the units hard-code it"
command -v "$PYTHON" >/dev/null || die "$PYTHON not found (Ubuntu 24.04: apt install python3.12-venv)"

if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --home-dir "$STATE_DIR" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$STATE_DIR"
install -d -o root -g root -m 0755 "$(dirname "$ENV_FILE")"
if [[ ! -e "$ENV_FILE" ]]; then
  install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0600 "$APP_DIR/scanner/.env.example" "$ENV_FILE"
  echo "created $ENV_FILE from .env.example: fill in the secrets before running the self-test"
fi
chown "$SERVICE_USER:$SERVICE_USER" "$ENV_FILE"
chmod 0600 "$ENV_FILE"

# Code and venv stay root-owned and read-only to the service user.
"$PYTHON" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -e "$APP_DIR/scanner"

install -o root -g root -m 0644 "$APP_DIR"/scanner/deploy/*.service /etc/systemd/system/
systemctl daemon-reload

echo "installed. P0 check: sudo systemctl start marketboard-selftest && journalctl -u marketboard-selftest -n 20 --no-pager"
