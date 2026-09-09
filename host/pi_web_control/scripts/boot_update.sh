#!/usr/bin/env bash
set -u

REPO_DIR="${ROBOT_REPO_DIR:-/home/pi/4wd-car}"
APP_DIR="$REPO_DIR/host/pi_web_control"
VENV_PYTHON="$APP_DIR/.venv/bin/python"
BRANCH="${ROBOT_GIT_BRANCH:-main}"
REMOTE="${ROBOT_GIT_REMOTE:-origin}"
HOME_WIFI="${ROBOT_HOME_WIFI_CONNECTION:-HomeWiFi}"
HOTSPOT="${ROBOT_HOTSPOT_CONNECTION:-Hotspot}"
NETWORK_TIMEOUT_SECONDS="${ROBOT_NETWORK_TIMEOUT_SECONDS:-45}"
ROLLBACK_ENABLED="${ROBOT_ENABLE_ROLLBACK:-0}"
STATE_DIR="${ROBOT_STATE_DIR:-$REPO_DIR/.robot_state}"
LAST_GOOD_FILE="$STATE_DIR/last-good-commit"
PENDING_FILE="$STATE_DIR/pending-commit"
STATUS_FILE="$STATE_DIR/update-status.json"

mkdir -p "$STATE_DIR"

log() {
  echo "robot-boot-update: $*"
}

write_status() {
  local state="$1"
  local detail="${2:-}"
  printf '{"state":"%s","detail":"%s","time":"%s"}\n' \
    "$state" "$(printf '%s' "$detail" | tr '"' "'")" "$(date -Iseconds)" > "$STATUS_FILE"
}

connection_exists() {
  nmcli -t -f NAME connection show | grep -Fxq "$1"
}

has_internet() {
  ping -c 1 -W 2 github.com >/dev/null 2>&1
}

current_commit() {
  git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true
}

rollback_to_last_good() {
  if [ ! -s "$LAST_GOOD_FILE" ]; then
    log "no last-known-good commit is available"
    return 1
  fi

  local last_good
  last_good=$(cat "$LAST_GOOD_FILE")
  log "rolling back to last-known-good commit $last_good"
  git -C "$REPO_DIR" reset --hard "$last_good" || return 1

  if [ -x "$VENV_PYTHON" ] && [ -f "$APP_DIR/requirements.txt" ]; then
    "$VENV_PYTHON" -m pip install -r "$APP_DIR/requirements.txt" >/dev/null 2>&1 || true
  fi
  rm -f "$PENDING_FILE"
  return 0
}

recover_unconfirmed_release() {
  [ "$ROLLBACK_ENABLED" = "1" ] || return 0
  [ -s "$PENDING_FILE" ] || return 0

  local pending current
  pending=$(cat "$PENDING_FILE")
  current=$(current_commit)
  log "previous release $pending was never health-confirmed"

  if [ "$current" = "$pending" ] && rollback_to_last_good; then
    write_status "rolled-back" "Previous release did not pass health confirmation"
  else
    rm -f "$PENDING_FILE"
  fi
}

initialize_last_good() {
  [ "$ROLLBACK_ENABLED" = "1" ] || return 0
  [ -d "$REPO_DIR/.git" ] || return 0
  [ -s "$LAST_GOOD_FILE" ] && return 0
  [ -s "$PENDING_FILE" ] && return 0

  local current
  current=$(current_commit)
  if [ -n "$current" ]; then
    printf '%s\n' "$current" > "$LAST_GOOD_FILE"
    log "initialized last-known-good commit to ${current:0:8}"
  fi
}

try_home_wifi() {
  if ! command -v nmcli >/dev/null 2>&1; then
    log "nmcli is not installed; skipping Wi-Fi switching"
    return 1
  fi

  if ! connection_exists "$HOME_WIFI"; then
    log "home Wi-Fi connection '$HOME_WIFI' is not configured; skipping update network"
    return 1
  fi

  log "connecting to home Wi-Fi profile '$HOME_WIFI'"
  nmcli connection up "$HOME_WIFI" >/dev/null 2>&1 || true

  local start
  start=$(date +%s)
  while [ "$(($(date +%s) - start))" -lt "$NETWORK_TIMEOUT_SECONDS" ]; do
    if has_internet; then
      log "internet connection is available"
      return 0
    fi
    sleep 2
  done

  log "no internet after ${NETWORK_TIMEOUT_SECONDS}s"
  return 1
}

smoke_test_app() {
  if [ ! -x "$VENV_PYTHON" ]; then
    log "virtualenv not found; cannot run Python smoke test"
    return 1
  fi

  "$VENV_PYTHON" -m py_compile "$APP_DIR/app.py" || return 1
  (
    cd "$APP_DIR"
    "$VENV_PYTHON" -c \
      "import app; flask_app = app.create_app('auto', False); assert flask_app.url_map"
  ) || return 1
}

update_repo() {
  if [ ! -d "$REPO_DIR/.git" ]; then
    log "$REPO_DIR is not a git checkout; skipping code update"
    write_status "local-only" "Repository is not a git checkout"
    return 0
  fi

  if ! has_internet; then
    log "internet is unavailable; keeping installed code"
    write_status "offline" "Internet unavailable; kept installed code"
    return 0
  fi

  local old_commit new_commit
  old_commit=$(current_commit)
  log "fetching $REMOTE/$BRANCH"
  git -C "$REPO_DIR" fetch --depth 1 "$REMOTE" "$BRANCH" || {
    write_status "fetch-failed" "Git fetch failed; kept installed code"
    return 0
  }

  new_commit=$(git -C "$REPO_DIR" rev-parse FETCH_HEAD 2>/dev/null || true)
  if [ -z "$new_commit" ] || [ "$new_commit" = "$old_commit" ]; then
    write_status "up-to-date" "${old_commit:0:8}"
    return 0
  fi

  if [ "$ROLLBACK_ENABLED" = "1" ] && [ -n "$old_commit" ]; then
    printf '%s\n' "$old_commit" > "$LAST_GOOD_FILE"
  fi

  log "updating from ${old_commit:0:8} to ${new_commit:0:8}"
  git -C "$REPO_DIR" reset --hard "$new_commit" || {
    write_status "update-failed" "git reset failed"
    return 0
  }

  if [ -x "$VENV_PYTHON" ] && [ -f "$APP_DIR/requirements.txt" ]; then
    log "updating Python dependencies"
    "$VENV_PYTHON" -m pip install -r "$APP_DIR/requirements.txt" || true
  fi

  if ! smoke_test_app; then
    log "new release failed smoke test"
    if [ "$ROLLBACK_ENABLED" = "1" ] && rollback_to_last_good; then
      write_status "rolled-back" "New release failed Python smoke test"
    else
      write_status "smoke-test-failed" "New release failed; automatic rollback unavailable"
    fi
    return 0
  fi

  if [ "$ROLLBACK_ENABLED" = "1" ]; then
    printf '%s\n' "$new_commit" > "$PENDING_FILE"
    write_status "pending-health" "${new_commit:0:8}"
  else
    write_status "updated" "${new_commit:0:8}; rollback disabled until reliability service is installed"
  fi
}

start_hotspot() {
  if ! command -v nmcli >/dev/null 2>&1; then
    return 0
  fi

  if connection_exists "$HOTSPOT"; then
    log "starting robot hotspot profile '$HOTSPOT'"
    nmcli connection up "$HOTSPOT" >/dev/null 2>&1 || true
  else
    log "hotspot profile '$HOTSPOT' is not configured"
  fi
}

recover_unconfirmed_release
initialize_last_good
try_home_wifi && update_repo
start_hotspot
log "boot update finished"
exit 0
