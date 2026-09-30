#!/usr/bin/env bash
set -u

REPO_DIR="${ROBOT_REPO_DIR:-/home/pi/4wd-car}"
APP_DIR="$REPO_DIR/host/pi_web_control"
VENV_PYTHON="$APP_DIR/.venv/bin/python"
STATE_DIR="${ROBOT_STATE_DIR:-$REPO_DIR/.robot_state}"
LAST_GOOD_FILE="$STATE_DIR/last-good-commit"
PENDING_FILE="$STATE_DIR/pending-commit"
STATUS_FILE="$STATE_DIR/update-status.json"
HEALTH_URL="${ROBOT_HEALTH_URL:-http://127.0.0.1:8080/health}"
HEALTH_TIMEOUT_SECONDS="${ROBOT_HEALTH_TIMEOUT_SECONDS:-20}"

mkdir -p "$STATE_DIR"

write_status() {
  local state="$1"
  local detail="${2:-}"
  printf '{"state":"%s","detail":"%s","time":"%s"}\n' \
    "$state" "$(printf '%s' "$detail" | tr '"' "'")" "$(date -Iseconds)" > "$STATUS_FILE"
}

[ -s "$PENDING_FILE" ] || exit 0

pending=$(cat "$PENDING_FILE")
start=$(date +%s)

while [ "$(($(date +%s) - start))" -lt "$HEALTH_TIMEOUT_SECONDS" ]; do
  if curl -fsS "$HEALTH_URL" 2>/dev/null | grep -q '"ok":true'; then
    printf '%s\n' "$pending" > "$LAST_GOOD_FILE"
    rm -f "$PENDING_FILE"
    write_status "healthy" "${pending:0:8}"
    exit 0
  fi
  sleep 1
done

if [ ! -s "$LAST_GOOD_FILE" ]; then
  write_status "health-failed" "No last-known-good commit available for rollback"
  exit 1
fi

last_good=$(cat "$LAST_GOOD_FILE")
git -C "$REPO_DIR" reset --hard "$last_good" || {
  write_status "rollback-failed" "$last_good"
  exit 1
}

if [ -x "$VENV_PYTHON" ] && [ -f "$APP_DIR/requirements.txt" ]; then
  "$VENV_PYTHON" -m pip install -r "$APP_DIR/requirements.txt" >/dev/null 2>&1 || true
fi

rm -f "$PENDING_FILE"
write_status "rolled-back" "Health check failed; restored ${last_good:0:8}"
exit 1
