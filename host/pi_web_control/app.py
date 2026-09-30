import argparse
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import serial
from flask import Flask, jsonify, render_template, request
from serial.tools import list_ports


BAUD_RATE = 115200
DEFAULT_PORT = "/dev/ttyACM0"
DRIVE_REPEAT_SECONDS = 0.10
STATUS_INTERVAL_SECONDS = 0.50
DEFAULT_SPEED_LIMIT = 0.15
HARD_SPEED_LIMIT = 0.30
STOP_REPEAT_COUNT = 4
MAX_LOG_LINES = 250
WRITE_QUEUE_LIMIT = 20

MOTOR_DRIVE_MAP = [
    {"name": "M1 right rear", "side": "right"},
    {"name": "M2 left rear", "side": "left"},
    {"name": "M3 left front", "side": "left"},
    {"name": "M4 right front", "side": "right"},
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class RobotState:
    connected: bool = False
    port: str = DEFAULT_PORT
    speed_limit: float = DEFAULT_SPEED_LIMIT
    left_power: float = 0.0
    right_power: float = 0.0
    held_motor_command: str = ""
    last_command: str = "STOP"
    applied: list[str] = field(default_factory=lambda: ["0.000"] * 4)
    pulse_totals: list[int] = field(default_factory=lambda: [0] * 4)
    pulse_rates: list[float] = field(default_factory=lambda: [0.0] * 4)
    log: list[str] = field(default_factory=list)


class SerialWorker:
    def __init__(self, state: RobotState) -> None:
        self.state = state
        self._connection: Optional[serial.Serial] = None
        self._write_queue: "queue.Queue[str]" = queue.Queue(maxsize=WRITE_QUEUE_LIMIT)
        self._running = threading.Event()
        self._lock = threading.Lock()
        self._last_pulses: Optional[list[int]] = None
        self._last_pulse_time: Optional[float] = None

    @property
    def connected(self) -> bool:
        return self._connection is not None and self._connection.is_open

    def start(self, port: str) -> None:
        self.stop()
        self._connection = serial.Serial(port, BAUD_RATE, timeout=0.1, write_timeout=0.05)
        time.sleep(0.2)
        self._running.set()
        with self._lock:
            self.state.connected = True
            self.state.port = port
        threading.Thread(target=self._read_loop, daemon=True).start()
        threading.Thread(target=self._write_loop, daemon=True).start()
        threading.Thread(target=self._drive_repeat_loop, daemon=True).start()
        threading.Thread(target=self._status_loop, daemon=True).start()
        self.send_stop()

    def stop(self) -> None:
        self._running.clear()
        if self._connection is not None:
            try:
                if self._connection.is_open:
                    self.send_stop()
                    time.sleep(0.1)
                    self._connection.close()
            finally:
                self._connection = None
        with self._lock:
            self.state.connected = False

    def send(self, command: str, log: bool = False) -> None:
        if not self.connected:
            return
        command = command.strip()
        if not command:
            return
        try:
            self._write_queue.put_nowait(command)
        except queue.Full:
            try:
                self._write_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._write_queue.put_nowait(command)
            except queue.Full:
                pass
        if log:
            self.append_log(f"> {command}")
            with self._lock:
                self.state.last_command = command

    def send_stop(self) -> None:
        self._clear_write_queue()
        for _ in range(STOP_REPEAT_COUNT):
            self.send("STOP")
        self.append_log("> STOP")
        with self._lock:
            self.state.left_power = 0.0
            self.state.right_power = 0.0
            self.state.held_motor_command = ""
            self.state.last_command = "STOP"

    def append_log(self, line: str) -> None:
        with self._lock:
            self.state.log.append(line)
            if len(self.state.log) > MAX_LOG_LINES:
                self.state.log = self.state.log[-MAX_LOG_LINES:]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connected": self.state.connected,
                "port": self.state.port,
                "speedLimit": self.state.speed_limit,
                "leftPower": self.state.left_power,
                "rightPower": self.state.right_power,
                "lastCommand": self.state.last_command,
                "applied": list(self.state.applied),
                "pulseTotals": list(self.state.pulse_totals),
                "pulseRates": list(self.state.pulse_rates),
                "log": list(self.state.log[-80:]),
            }

    def set_speed_limit(self, value: float) -> float:
        value = clamp(value, 0.03, HARD_SPEED_LIMIT)
        with self._lock:
            self.state.speed_limit = value
        return value

    def set_tank(self, left: float, right: float) -> None:
        with self._lock:
            limit = self.state.speed_limit
            self.state.left_power = clamp(left, -1.0, 1.0) * limit
            self.state.right_power = clamp(right, -1.0, 1.0) * limit
            self.state.held_motor_command = ""
        self._send_drive_now()

    def set_single_motor(self, motor: int, direction: float) -> None:
        motor = max(1, min(4, motor))
        with self._lock:
            power = clamp(direction, -1.0, 1.0) * self.state.speed_limit
            self.state.left_power = 0.0
            self.state.right_power = 0.0
            self.state.held_motor_command = f"MOTOR {motor} {power:.3f}"
            command = self.state.held_motor_command
        self.send(command, log=True)

    def send_raw(self, command: str) -> None:
        self.send(command, log=True)

    def _build_drive_command(self) -> str:
        with self._lock:
            left_power = self.state.left_power
            right_power = self.state.right_power
        powers = []
        for motor in MOTOR_DRIVE_MAP:
            powers.append(left_power if motor["side"] == "left" else right_power)
        return "DRIVE {:.3f} {:.3f} {:.3f} {:.3f}".format(*powers)

    def _send_drive_now(self) -> None:
        command = self._build_drive_command()
        self.send(command, log=True)

    def _clear_write_queue(self) -> None:
        while True:
            try:
                self._write_queue.get_nowait()
            except queue.Empty:
                return

    def _write_loop(self) -> None:
        while self._running.is_set() and self.connected:
            try:
                command = self._write_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._connection.write((command + "\n").encode("ascii"))
                self._connection.flush()
            except (serial.SerialException, serial.SerialTimeoutException) as exc:
                self.append_log(f"SERIAL WRITE ERROR: {exc}")
                self._running.clear()
                with self._lock:
                    self.state.connected = False
                return

    def _read_loop(self) -> None:
        while self._running.is_set() and self.connected:
            try:
                raw = self._connection.readline()
            except serial.SerialException as exc:
                self.append_log(f"SERIAL ERROR: {exc}")
                self._running.clear()
                with self._lock:
                    self.state.connected = False
                return
            if raw:
                line = raw.decode("ascii", errors="replace").strip()
                self._handle_status_line(line)
                self.append_log(line)

    def _drive_repeat_loop(self) -> None:
        while self._running.is_set():
            if self.connected:
                self._repeat_held_drive()
            time.sleep(DRIVE_REPEAT_SECONDS)

    def _status_loop(self) -> None:
        while self._running.is_set():
            if self.connected:
                self.send("STATUS")
            time.sleep(STATUS_INTERVAL_SECONDS)

    def _repeat_held_drive(self) -> None:
        with self._lock:
            motor_command = self.state.held_motor_command
            moving = self.state.left_power != 0.0 or self.state.right_power != 0.0
        if motor_command:
            self.send(motor_command)
        elif moving:
            self.send(self._build_drive_command())

    def _handle_status_line(self, line: str) -> None:
        parts = line.split()
        if len(parts) != 5:
            return
        if parts[0] == "APPLIED":
            with self._lock:
                self.state.applied = parts[1:5]
            return
        if parts[0] != "SPEED_PULSES":
            return
        try:
            pulses = [int(value) for value in parts[1:5]]
        except ValueError:
            return
        now = time.monotonic()
        rates = [0.0] * 4
        if self._last_pulses is not None and self._last_pulse_time is not None:
            elapsed = max(0.001, now - self._last_pulse_time)
            rates = [max(0.0, (total - old) / elapsed) for total, old in zip(pulses, self._last_pulses)]
        self._last_pulses = pulses
        self._last_pulse_time = now
        with self._lock:
            self.state.pulse_totals = pulses
            self.state.pulse_rates = rates


def create_app(default_port: str, autoconnect: bool) -> Flask:
    app = Flask(__name__)
    state = RobotState(port=default_port)
    worker = SerialWorker(state)

    if autoconnect:
        try:
            worker.start(default_port)
        except serial.SerialException as exc:
            worker.append_log(f"Autoconnect failed on {default_port}: {exc}")

    @app.get("/")
    def index():
        return render_template("index.html", motors=MOTOR_DRIVE_MAP, hard_limit=HARD_SPEED_LIMIT)

    @app.get("/api/state")
    def api_state():
        return jsonify(worker.snapshot())

    @app.get("/api/ports")
    def api_ports():
        ports = [port.device for port in list_ports.comports()]
        if default_port not in ports:
            ports.insert(0, default_port)
        return jsonify({"ports": ports})

    @app.post("/api/connect")
    def api_connect():
        port = request.json.get("port", default_port)
        worker.start(port)
        return jsonify(worker.snapshot())

    @app.post("/api/disconnect")
    def api_disconnect():
        worker.stop()
        return jsonify(worker.snapshot())

    @app.post("/api/stop")
    def api_stop():
        worker.send_stop()
        return jsonify(worker.snapshot())

    @app.post("/api/speed-limit")
    def api_speed_limit():
        worker.set_speed_limit(float(request.json.get("value", DEFAULT_SPEED_LIMIT)))
        return jsonify(worker.snapshot())

    @app.post("/api/tank")
    def api_tank():
        worker.set_tank(float(request.json.get("left", 0.0)), float(request.json.get("right", 0.0)))
        return jsonify(worker.snapshot())

    @app.post("/api/motor")
    def api_motor():
        worker.set_single_motor(int(request.json.get("motor", 1)), float(request.json.get("direction", 0.0)))
        return jsonify(worker.snapshot())

    @app.post("/api/raw")
    def api_raw():
        worker.send_raw(str(request.json.get("command", "")))
        return jsonify(worker.snapshot())

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Raspberry Pi web controller for the Pico motor controller.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--serial-port", default=DEFAULT_PORT)
    parser.add_argument("--no-autoconnect", action="store_true")
    args = parser.parse_args()
    app = create_app(args.serial_port, not args.no_autoconnect)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()



