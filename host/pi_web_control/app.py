import argparse
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import serial
from flask import Flask, jsonify, render_template, request
from serial.tools import list_ports


BAUD_RATE = 115200
DEFAULT_PORT = "auto"
DEFAULT_SPEED_LIMIT = 0.15
HARD_SPEED_LIMIT = 0.30
READ_DRAIN_SECONDS = 0.03
DRIVE_SEND_SECONDS = 0.10
DRIVE_LEASE_SECONDS = 0.30
RECONNECT_SECONDS = 2.0
STATUS_POLL_MIN_SECONDS = 0.15

# This is the conversion that previously gave ~200 RPM on this robot.
# If the motor/controller combination changes, calibrate this value.
SPEED_PULSES_PER_REVOLUTION = 15.0

MOTOR_DRIVE_MAP = [
    {"name": "M1 right rear", "side": "right"},
    {"name": "M2 left rear", "side": "left"},
    {"name": "M3 left front", "side": "left"},
    {"name": "M4 right front", "side": "right"},
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def serial_port_sort_key(port) -> tuple[int, str]:
    device = getattr(port, "device", str(port))
    description = (getattr(port, "description", "") or "").lower()
    vid = getattr(port, "vid", None)
    if vid == 0x2E8A or "pico" in description or "rp2040" in description:
        return (0, device)
    if "ttyACM" in device:
        return (1, device)
    if "ttyUSB" in device:
        return (2, device)
    return (3, device)


def discover_serial_port(preferred: str = DEFAULT_PORT) -> Optional[str]:
    ports = sorted(list(list_ports.comports()), key=serial_port_sort_key)
    devices = [port.device for port in ports]

    if preferred and preferred != "auto" and preferred in devices:
        return preferred

    for port in ports:
        device = port.device
        description = (port.description or "").lower()
        if port.vid == 0x2E8A or "pico" in description or "rp2040" in description:
            return device
    for device in devices:
        if "ttyACM" in device:
            return device
    for device in devices:
        if "ttyUSB" in device:
            return device
    return None


def git_value(repo_dir: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_dir), *args],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1.5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def read_update_status(repo_dir: Path) -> dict:
    state_dir = Path(os.environ.get("ROBOT_STATE_DIR", repo_dir / ".robot_state"))
    status_file = state_dir / "update-status.json"
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "unknown"}


def rpm_from_pulse_delta(delta: int, elapsed_seconds: float) -> float:
    if elapsed_seconds <= 0 or delta < 0:
        return 0.0
    return (delta / SPEED_PULSES_PER_REVOLUTION) * (60.0 / elapsed_seconds)


@dataclass
class RobotState:
    connected: bool = False
    port: str = DEFAULT_PORT
    preferred_port: str = DEFAULT_PORT
    speed_limit: float = DEFAULT_SPEED_LIMIT
    applied: list[str] = field(default_factory=lambda: ["0.000"] * 4)
    pulse_totals: list[int] = field(default_factory=lambda: [0] * 4)
    rpm: list[float] = field(default_factory=lambda: [0.0] * 4)
    log: list[str] = field(default_factory=list)
    pico_firmware: str = "unknown"
    pico_watchdog: str = "unknown"
    last_error: str = ""
    last_command: str = ""
    last_response_monotonic: float = 0.0
    connected_since_monotonic: float = 0.0
    reconnect_count: int = 0


class PicoSerial:
    def __init__(self, state: RobotState, autoconnect: bool = True) -> None:
        self.state = state
        self.connection: Optional[serial.Serial] = None
        self.lock = threading.RLock()
        self.autoconnect = autoconnect
        self.manual_disconnect = not autoconnect
        self._last_status_request = 0.0
        self._previous_pulse_totals: Optional[list[int]] = None
        self._previous_pulse_time = 0.0
        self._shutdown = False
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()

    def connect(self, preferred_port: Optional[str] = None) -> bool:
        with self.lock:
            if preferred_port:
                self.state.preferred_port = preferred_port
            self.manual_disconnect = False
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        self._close_locked(send_stop=False)
        port = discover_serial_port(self.state.preferred_port)
        if not port:
            self.state.connected = False
            self.state.port = self.state.preferred_port
            self.state.last_error = "No Pico/serial port found"
            return False

        try:
            self.connection = serial.Serial(
                port,
                BAUD_RATE,
                timeout=0.02,
                write_timeout=0.05,
            )
            time.sleep(0.20)
            self.state.connected = True
            self.state.port = port
            self.state.last_error = ""
            self.state.connected_since_monotonic = time.monotonic()
            self.state.reconnect_count += 1
            self._previous_pulse_totals = None
            self._previous_pulse_time = 0.0
            self._send_locked("STOP", log=True)
            self._send_locked("STATUS", log=False)
            self._drain_locked()
            self.add_log(f"Connected to Pico on {port}")
            return True
        except (serial.SerialException, OSError) as exc:
            self._mark_disconnected_locked(exc)
            return False

    def disconnect(self, manual: bool = True) -> None:
        with self.lock:
            if manual:
                self.manual_disconnect = True
            self._close_locked(send_stop=True)

    def _close_locked(self, send_stop: bool) -> None:
        connection = self.connection
        if connection and connection.is_open:
            if send_stop:
                for _ in range(4):
                    try:
                        connection.write(b"STOP\n")
                        connection.flush()
                        time.sleep(0.02)
                    except (serial.SerialException, OSError):
                        break
            try:
                connection.close()
            except (serial.SerialException, OSError):
                pass
        self.connection = None
        self.state.connected = False
        self.state.rpm = [0.0] * 4

    def _mark_disconnected_locked(self, exc: Exception) -> None:
        message = f"{type(exc).__name__}: {exc}"
        self.state.last_error = message
        self.add_log(f"Serial disconnected: {message}")
        self._close_locked(send_stop=False)

    def _reconnect_loop(self) -> None:
        while not self._shutdown:
            time.sleep(RECONNECT_SECONDS)
            if not self.autoconnect or self.manual_disconnect:
                continue
            with self.lock:
                if self.state.connected:
                    continue
                self._connect_locked()

    def send(self, command: str, log: bool = True) -> bool:
        with self.lock:
            if not self.state.connected:
                return False
            try:
                self._send_locked(command, log=log)
                self._drain_locked()
                return True
            except (serial.SerialException, OSError) as exc:
                self._mark_disconnected_locked(exc)
                return False

    def _send_locked(self, command: str, log: bool = True) -> None:
        if not self.connection or not self.connection.is_open:
            return
        command = command.strip()
        if not command:
            return
        self.connection.write((command + "\n").encode("ascii"))
        self.connection.flush()
        self.state.last_command = command
        if log:
            self.add_log(f"> {command}")

    def status(self) -> None:
        now = time.monotonic()
        if now - self._last_status_request < STATUS_POLL_MIN_SECONDS:
            return
        self._last_status_request = now
        self.send("STATUS", log=False)

    def _drain_locked(self) -> None:
        if not self.connection or not self.connection.is_open:
            return
        end_time = time.monotonic() + READ_DRAIN_SECONDS
        while time.monotonic() < end_time:
            raw = self.connection.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue
            self.state.last_response_monotonic = time.monotonic()
            self.handle_line(line)
            self.add_log(line)

    def _update_rpm(self, totals: list[int]) -> None:
        now = time.monotonic()
        if self._previous_pulse_totals is None:
            self._previous_pulse_totals = list(totals)
            self._previous_pulse_time = now
            return

        elapsed = now - self._previous_pulse_time
        if elapsed < 0.05:
            return

        rpm_values = []
        for current, previous in zip(totals, self._previous_pulse_totals):
            if current >= previous:
                delta = current - previous
            else:
                delta = (2**32 - previous) + current
            rpm_values.append(rpm_from_pulse_delta(delta, elapsed))

        self.state.rpm = rpm_values
        self._previous_pulse_totals = list(totals)
        self._previous_pulse_time = now

    def handle_line(self, line: str) -> None:
        parts = line.split()
        if not parts:
            return

        if parts[0] in {"APPLIED", "POWER"} and len(parts) == 5:
            self.state.applied = parts[1:5]
            return

        if parts[0] == "SPEED_PULSES" and len(parts) == 5:
            try:
                totals = [int(value) for value in parts[1:5]]
            except ValueError:
                return
            self.state.pulse_totals = totals
            self._update_rpm(totals)
            return

        if parts[0] == "FW" and len(parts) >= 2:
            self.state.pico_firmware = " ".join(parts[1:])
            return

        if parts[0] == "WATCHDOG" and len(parts) >= 2:
            self.state.pico_watchdog = " ".join(parts[1:])
            return

    def add_log(self, line: str) -> None:
        self.state.log.append(line)
        self.state.log = self.state.log[-160:]

    def snapshot(self) -> dict:
        with self.lock:
            now = time.monotonic()
            last_response_age = (
                round(now - self.state.last_response_monotonic, 2)
                if self.state.last_response_monotonic
                else None
            )
            connected_for = (
                round(now - self.state.connected_since_monotonic, 1)
                if self.state.connected and self.state.connected_since_monotonic
                else 0.0
            )
            return {
                "connected": self.state.connected,
                "port": self.state.port,
                "preferredPort": self.state.preferred_port,
                "speedLimit": self.state.speed_limit,
                "applied": list(self.state.applied),
                "pulseTotals": list(self.state.pulse_totals),
                "rpm": [round(value, 1) for value in self.state.rpm],
                "picoFirmware": self.state.pico_firmware,
                "picoWatchdog": self.state.pico_watchdog,
                "lastError": self.state.last_error,
                "lastCommand": self.state.last_command,
                "lastResponseAge": last_response_age,
                "connectedFor": connected_for,
                "reconnectCount": self.state.reconnect_count,
                "log": list(self.state.log),
            }


def build_drive_command(left: float, right: float, limit: float) -> str:
    left_power = clamp(left, -1.0, 1.0) * limit
    right_power = clamp(right, -1.0, 1.0) * limit
    powers = []
    for motor in MOTOR_DRIVE_MAP:
        powers.append(left_power if motor["side"] == "left" else right_power)
    return "DRIVE {:.3f} {:.3f} {:.3f} {:.3f}".format(*powers)


class DriveWatchdog:
    def __init__(self, pico: PicoSerial, state: RobotState) -> None:
        self.pico = pico
        self.state = state
        self.lock = threading.Lock()
        self.left = 0.0
        self.right = 0.0
        self.active = False
        self.stop_sent = True
        self.last_update = 0.0
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def update(self, left: float, right: float) -> None:
        with self.lock:
            self.left = clamp(left, -1.0, 1.0)
            self.right = clamp(right, -1.0, 1.0)
            self.active = True
            self.stop_sent = False
            self.last_update = time.monotonic()

    def cancel(self) -> None:
        with self.lock:
            self.left = 0.0
            self.right = 0.0
            self.active = False
            self.stop_sent = True
            self.last_update = 0.0

    def stop(self) -> None:
        self.cancel()
        for _ in range(4):
            self.pico.send("STOP")

    def _loop(self) -> None:
        while True:
            time.sleep(DRIVE_SEND_SECONDS)
            with self.lock:
                left = self.left
                right = self.right
                active = self.active
                stale = active and time.monotonic() - self.last_update > DRIVE_LEASE_SECONDS
                stop_needed = stale and not self.stop_sent
                if stale:
                    self.active = False
                    self.left = 0.0
                    self.right = 0.0
                    self.stop_sent = True
            if stop_needed:
                for _ in range(4):
                    self.pico.send("STOP")
                continue
            if active and not stale:
                self.pico.send(build_drive_command(left, right, self.state.speed_limit))


def create_app(default_port: str, autoconnect: bool) -> Flask:
    app = Flask(__name__)
    repo_dir = Path(__file__).resolve().parents[2]
    started_monotonic = time.monotonic()
    state = RobotState(port=default_port, preferred_port=default_port)
    pico = PicoSerial(state, autoconnect=autoconnect)
    drive = DriveWatchdog(pico, state)

    app.config["robot_state"] = state
    app.config["pico_serial"] = pico
    app.config["drive_watchdog"] = drive

    if autoconnect:
        pico.connect(default_port)

    def system_snapshot() -> dict:
        return {
            "commit": git_value(repo_dir, "rev-parse", "--short", "HEAD"),
            "branch": git_value(repo_dir, "rev-parse", "--abbrev-ref", "HEAD"),
            "uptimeSeconds": round(time.monotonic() - started_monotonic, 1),
            "update": read_update_status(repo_dir),
            "pulsesPerRevolution": SPEED_PULSES_PER_REVOLUTION,
        }

    @app.get("/")
    def index():
        return render_template("index.html", motors=MOTOR_DRIVE_MAP, hard_limit=HARD_SPEED_LIMIT)

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "service": "4wd-robot-web-control",
                "picoConnected": state.connected,
                "commit": git_value(repo_dir, "rev-parse", "--short", "HEAD"),
                "uptimeSeconds": round(time.monotonic() - started_monotonic, 1),
            }
        )

    @app.get("/api/state")
    def api_state():
        if state.connected:
            pico.status()
        snapshot = pico.snapshot()
        snapshot["system"] = system_snapshot()
        return jsonify(snapshot)

    @app.get("/api/ports")
    def api_ports():
        ports = sorted(list(list_ports.comports()), key=serial_port_sort_key)
        devices = [port.device for port in ports]
        return jsonify({"ports": ["auto", *devices]})

    @app.post("/api/connect")
    def api_connect():
        drive.stop()
        body = request.get_json(silent=True) or {}
        preferred = str(body.get("port", default_port))
        pico.connect(preferred)
        snapshot = pico.snapshot()
        snapshot["system"] = system_snapshot()
        return jsonify(snapshot)

    @app.post("/api/disconnect")
    def api_disconnect():
        drive.stop()
        pico.disconnect(manual=True)
        snapshot = pico.snapshot()
        snapshot["system"] = system_snapshot()
        return jsonify(snapshot)

    @app.post("/api/speed-limit")
    def api_speed_limit():
        body = request.get_json(silent=True) or {}
        state.speed_limit = clamp(
            float(body.get("value", DEFAULT_SPEED_LIMIT)),
            0.03,
            HARD_SPEED_LIMIT,
        )
        return jsonify(pico.snapshot())

    @app.post("/api/tank")
    def api_tank():
        body = request.get_json(silent=True) or {}
        drive.update(float(body.get("left", 0.0)), float(body.get("right", 0.0)))
        return jsonify(pico.snapshot())

    @app.post("/api/motor")
    def api_motor():
        drive.cancel()
        body = request.get_json(silent=True) or {}
        motor = max(1, min(4, int(body.get("motor", 1))))
        direction = clamp(float(body.get("direction", 0.0)), -1.0, 1.0)
        pico.send(f"MOTOR {motor} {direction * state.speed_limit:.3f}")
        return jsonify(pico.snapshot())

    @app.post("/api/stop")
    def api_stop():
        drive.stop()
        return jsonify(pico.snapshot())

    @app.post("/api/raw")
    def api_raw():
        drive.stop()
        body = request.get_json(silent=True) or {}
        pico.send(str(body.get("command", "")))
        return jsonify(pico.snapshot())

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Raspberry Pi web control for the Pico motor controller.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--serial-port", default=DEFAULT_PORT)
    parser.add_argument("--no-autoconnect", action="store_true")
    args = parser.parse_args()
    app = create_app(args.serial_port, not args.no_autoconnect)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
