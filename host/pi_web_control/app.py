import argparse
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

import serial
from flask import Flask, jsonify, render_template, request
from serial.tools import list_ports


BAUD_RATE = 115200
DEFAULT_PORT = "/dev/ttyACM0"
DEFAULT_SPEED_LIMIT = 0.15
HARD_SPEED_LIMIT = 0.30
READ_DRAIN_SECONDS = 0.03

MOTOR_DRIVE_MAP = [
    {"name": "M1 right rear", "side": "right"},
    {"name": "M2 left rear", "side": "left"},
    {"name": "M3 left front", "side": "left"},
    {"name": "M4 right front", "side": "right"},
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def serial_port_sort_key(port: str) -> tuple[int, str]:
    if "ttyACM" in port or "ttyUSB" in port:
        return (0, port)
    return (1, port)


@dataclass
class RobotState:
    connected: bool = False
    port: str = DEFAULT_PORT
    speed_limit: float = DEFAULT_SPEED_LIMIT
    applied: list[str] = field(default_factory=lambda: ["0.000"] * 4)
    pulse_totals: list[int] = field(default_factory=lambda: [0] * 4)
    log: list[str] = field(default_factory=list)


class PicoSerial:
    def __init__(self, state: RobotState) -> None:
        self.state = state
        self.connection: Optional[serial.Serial] = None
        self.lock = threading.Lock()

    def connect(self, port: str) -> None:
        with self.lock:
            self.close_locked()
            self.connection = serial.Serial(port, BAUD_RATE, timeout=0.02, write_timeout=0.05)
            time.sleep(0.2)
            self.state.connected = True
            self.state.port = port
            self.send_locked("STOP", log=True)

    def disconnect(self) -> None:
        with self.lock:
            self.close_locked()

    def close_locked(self) -> None:
        if self.connection and self.connection.is_open:
            try:
                for _ in range(4):
                    self.send_locked("STOP", log=True)
                    time.sleep(0.02)
                self.connection.close()
            finally:
                self.state.connected = False
                self.connection = None

    def send(self, command: str, log: bool = True) -> None:
        with self.lock:
            self.send_locked(command, log=log)
            self.drain_locked()

    def send_locked(self, command: str, log: bool = True) -> None:
        if not self.connection or not self.connection.is_open:
            return
        command = command.strip()
        if not command:
            return
        self.connection.write((command + "\n").encode("ascii"))
        self.connection.flush()
        if log:
            self.add_log(f"> {command}")

    def status(self) -> None:
        with self.lock:
            self.send_locked("STATUS", log=False)
            self.drain_locked()

    def drain_locked(self) -> None:
        if not self.connection or not self.connection.is_open:
            return
        end_time = time.monotonic() + READ_DRAIN_SECONDS
        while time.monotonic() < end_time:
            raw = self.connection.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            self.handle_line(line)
            self.add_log(line)

    def handle_line(self, line: str) -> None:
        parts = line.split()
        if len(parts) != 5:
            return
        if parts[0] == "APPLIED":
            self.state.applied = parts[1:5]
            return
        if parts[0] == "SPEED_PULSES":
            try:
                self.state.pulse_totals = [int(value) for value in parts[1:5]]
            except ValueError:
                pass

    def add_log(self, line: str) -> None:
        self.state.log.append(line)
        self.state.log = self.state.log[-120:]

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "connected": self.state.connected,
                "port": self.state.port,
                "speedLimit": self.state.speed_limit,
                "applied": list(self.state.applied),
                "pulseTotals": list(self.state.pulse_totals),
                "log": list(self.state.log),
            }


def build_drive_command(left: float, right: float, limit: float) -> str:
    left_power = clamp(left, -1.0, 1.0) * limit
    right_power = clamp(right, -1.0, 1.0) * limit
    powers = []
    for motor in MOTOR_DRIVE_MAP:
        powers.append(left_power if motor["side"] == "left" else right_power)
    return "DRIVE {:.3f} {:.3f} {:.3f} {:.3f}".format(*powers)


def create_app(default_port: str, autoconnect: bool) -> Flask:
    app = Flask(__name__)
    state = RobotState(port=default_port)
    pico = PicoSerial(state)

    if autoconnect:
        try:
            pico.connect(default_port)
        except serial.SerialException as exc:
            pico.add_log(f"Autoconnect failed on {default_port}: {exc}")

    @app.get("/")
    def index():
        return render_template("index.html", motors=MOTOR_DRIVE_MAP, hard_limit=HARD_SPEED_LIMIT)

    @app.get("/api/state")
    def api_state():
        if state.connected:
            pico.status()
        return jsonify(pico.snapshot())

    @app.get("/api/ports")
    def api_ports():
        ports = sorted({port.device for port in list_ports.comports()}, key=serial_port_sort_key)
        if default_port not in ports:
            ports.insert(0, default_port)
        return jsonify({"ports": ports})

    @app.post("/api/connect")
    def api_connect():
        pico.connect(request.json.get("port", default_port))
        return jsonify(pico.snapshot())

    @app.post("/api/disconnect")
    def api_disconnect():
        pico.disconnect()
        return jsonify(pico.snapshot())

    @app.post("/api/speed-limit")
    def api_speed_limit():
        state.speed_limit = clamp(float(request.json.get("value", DEFAULT_SPEED_LIMIT)), 0.03, HARD_SPEED_LIMIT)
        return jsonify(pico.snapshot())

    @app.post("/api/tank")
    def api_tank():
        command = build_drive_command(float(request.json.get("left", 0.0)), float(request.json.get("right", 0.0)), state.speed_limit)
        pico.send(command)
        return jsonify(pico.snapshot())

    @app.post("/api/motor")
    def api_motor():
        motor = max(1, min(4, int(request.json.get("motor", 1))))
        direction = clamp(float(request.json.get("direction", 0.0)), -1.0, 1.0)
        pico.send(f"MOTOR {motor} {direction * state.speed_limit:.3f}")
        return jsonify(pico.snapshot())

    @app.post("/api/stop")
    def api_stop():
        for _ in range(4):
            pico.send("STOP")
        return jsonify(pico.snapshot())

    @app.post("/api/raw")
    def api_raw():
        pico.send(str(request.json.get("command", "")))
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
