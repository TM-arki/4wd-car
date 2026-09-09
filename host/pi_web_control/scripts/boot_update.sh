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

log() {
  echo "robot-boot-update: $*"
}

connection_exists() {
  nmcli -t -f NAME connection show | grep -Fxq "$1"
}

has_internet() {
  ping -c 1 -W 2 github.com >/dev/null 2>&1
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

update_repo() {
  if [ ! -d "$REPO_DIR/.git" ]; then
    log "$REPO_DIR is not a git checkout; skipping code update"
    return 0
  fi

  if ! has_internet; then
    log "internet is unavailable; keeping installed code"
    return 0
  fi

  log "updating $REPO_DIR from $REMOTE/$BRANCH"
  git -C "$REPO_DIR" fetch --depth 1 "$REMOTE" "$BRANCH" || return 0
  git -C "$REPO_DIR" reset --hard "FETCH_HEAD" || return 0

  if [ -x "$VENV_PYTHON" ] && [ -f "$APP_DIR/requirements.txt" ]; then
    log "updating Python dependencies"
    "$VENV_PYTHON" -m pip install -r "$APP_DIR/requirements.txt" || true
  else
    log "virtualenv not found at $APP_DIR/.venv; skipping dependency update"
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

try_home_wifi && update_repo
start_hotspot
log "boot update finished"
exit 0
