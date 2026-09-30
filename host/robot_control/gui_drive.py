import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

import serial
from serial.tools import list_ports


BAUD_RATE = 115200
SEND_INTERVAL_MS = 100
STATUS_INTERVAL_MS = 500
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


class SerialWorker:
    def __init__(self, line_queue: "queue.Queue[str]") -> None:
        self._line_queue = line_queue
        self._connection: Optional[serial.Serial] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._write_queue: "queue.Queue[str]" = queue.Queue(maxsize=WRITE_QUEUE_LIMIT)
        self._running = threading.Event()

    @property
    def connected(self) -> bool:
        return self._connection is not None and self._connection.is_open

    def connect(self, port: str) -> None:
        self.disconnect()
        self._connection = serial.Serial(port, BAUD_RATE, timeout=0.1, write_timeout=0.05)
        time.sleep(0.2)
        self._running.set()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._writer_thread = threading.Thread(target=self._write_loop, daemon=True)
        self._reader_thread.start()
        self._writer_thread.start()

    def disconnect(self) -> None:
        self._running.clear()
        if self._connection is not None:
            try:
                if self._connection.is_open:
                    self.send_stop()
                    time.sleep(0.1)
                    self._connection.close()
            finally:
                self._connection = None

    def send(self, command: str) -> None:
        if not self.connected:
            return
        try:
            self._write_queue.put_nowait(command.strip())
        except queue.Full:
            try:
                self._write_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._write_queue.put_nowait(command.strip())
            except queue.Full:
                pass

    def send_stop(self) -> None:
        if not self.connected:
            return
        self._clear_write_queue()
        for _ in range(STOP_REPEAT_COUNT):
            self.send("STOP")

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
                self._line_queue.put(f"SERIAL WRITE ERROR: {exc}")
                self._running.clear()
                return

    def _read_loop(self) -> None:
        while self._running.is_set() and self.connected:
            try:
                raw = self._connection.readline()
            except serial.SerialException as exc:
                self._line_queue.put(f"SERIAL ERROR: {exc}")
                self.disconnect()
                return
            if raw:
                self._line_queue.put(raw.decode("ascii", errors="replace").strip())


class DriveGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Pico Motor Drive")
        self.minsize(720, 560)

        self.line_queue: "queue.Queue[str]" = queue.Queue()
        self.serial_worker = SerialWorker(self.line_queue)

        self.left_power = 0.0
        self.right_power = 0.0
        self.last_command = "STOP"
        self.held_motor_command = ""

        self.port_var = tk.StringVar()
        self.connection_var = tk.StringVar(value="Disconnected")
        self.speed_limit_var = tk.DoubleVar(value=DEFAULT_SPEED_LIMIT)
        self.left_var = tk.DoubleVar(value=0.0)
        self.right_var = tk.DoubleVar(value=0.0)
        self.raw_var = tk.StringVar()

        self.applied_vars = [tk.StringVar(value="0.000") for _ in range(4)]
        self.pulse_rate_vars = [tk.StringVar(value="0.0 p/s") for _ in range(4)]
        self.pulse_total_vars = [tk.StringVar(value="0") for _ in range(4)]
        self.pulse_bars = []
        self.last_pulses = None
        self.last_pulse_time = None

        self._build_ui()
        self.refresh_ports()
        self._bind_keys()

        self.after(SEND_INTERVAL_MS, self._send_drive_tick)
        self.after(STATUS_INTERVAL_MS, self._status_tick)
        self.after(100, self._drain_serial_lines)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(5, weight=1)

        connection = ttk.LabelFrame(root, text="USB connection", padding=10)
        connection.grid(row=0, column=0, columnspan=2, sticky="ew")
        connection.columnconfigure(1, weight=1)

        ttk.Label(connection, text="Port").grid(row=0, column=0, sticky="w")
        self.port_combo = ttk.Combobox(connection, textvariable=self.port_var, state="readonly")
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(connection, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(connection, text="Connect", command=self.connect).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(connection, text="Disconnect", command=self.disconnect).grid(row=0, column=4)
        ttk.Label(connection, textvariable=self.connection_var).grid(row=1, column=1, sticky="w", padx=8, pady=(6, 0))

        controls = ttk.LabelFrame(root, text="Low speed drive", padding=10)
        controls.grid(row=1, column=0, sticky="nsew", pady=12, padx=(0, 6))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Speed limit").grid(row=0, column=0, sticky="w", columnspan=2)
        ttk.Scale(controls, from_=0.03, to=HARD_SPEED_LIMIT, variable=self.speed_limit_var, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Label(controls, text="Hard capped at 0.30").grid(row=2, column=0, columnspan=2, sticky="w")

        button_grid = ttk.Frame(controls)
        button_grid.grid(row=3, column=0, columnspan=2, pady=12)
        self._drive_button(button_grid, "Forward", 1.0, 1.0).grid(row=0, column=1, padx=4, pady=4)
        self._drive_button(button_grid, "Left", -0.5, 0.5).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(button_grid, text="STOP", command=self.stop, style="Stop.TButton").grid(row=1, column=1, padx=4, pady=4)
        self._drive_button(button_grid, "Right", 0.5, -0.5).grid(row=1, column=2, padx=4, pady=4)
        self._drive_button(button_grid, "Reverse", -1.0, -1.0).grid(row=2, column=1, padx=4, pady=4)

        sliders = ttk.LabelFrame(root, text="Manual tank trim", padding=10)
        sliders.grid(row=1, column=1, sticky="nsew", pady=12, padx=(6, 0))
        sliders.columnconfigure(1, weight=1)

        ttk.Label(sliders, text="Left").grid(row=0, column=0, sticky="w")
        ttk.Scale(sliders, from_=-1.0, to=1.0, variable=self.left_var, orient="horizontal", command=self._slider_changed).grid(row=0, column=1, sticky="ew")
        ttk.Label(sliders, text="Right").grid(row=1, column=0, sticky="w")
        ttk.Scale(sliders, from_=-1.0, to=1.0, variable=self.right_var, orient="horizontal", command=self._slider_changed).grid(row=1, column=1, sticky="ew")
        ttk.Button(sliders, text="Apply Sliders", command=self.apply_sliders).grid(row=2, column=1, sticky="e", pady=(8, 0))

        motor_test = ttk.LabelFrame(root, text="Single motor test", padding=10)
        motor_test.grid(row=2, column=0, columnspan=2, sticky="ew")
        for column in range(4):
            motor_test.columnconfigure(column, weight=1)
        for index in range(4):
            ttk.Label(motor_test, text=MOTOR_DRIVE_MAP[index]["name"]).grid(row=0, column=index, pady=(0, 4))
            self._motor_button(motor_test, index + 1, 1.0, "Fwd").grid(row=1, column=index, sticky="ew", padx=4)
            self._motor_button(motor_test, index + 1, -1.0, "Rev").grid(row=2, column=index, sticky="ew", padx=4, pady=(4, 0))

        meters = ttk.LabelFrame(root, text="Wheel feedback", padding=10)
        meters.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        meters.columnconfigure(1, weight=1)
        ttk.Label(meters, text="Wheel").grid(row=0, column=0, sticky="w")
        ttk.Label(meters, text="Speed pulses/s").grid(row=0, column=1, sticky="w")
        ttk.Label(meters, text="Applied").grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Label(meters, text="Total").grid(row=0, column=3, sticky="e", padx=(8, 0))
        for index, motor in enumerate(MOTOR_DRIVE_MAP):
            row = index + 1
            ttk.Label(meters, text=motor["name"]).grid(row=row, column=0, sticky="w", pady=2)
            bar = ttk.Progressbar(meters, maximum=50.0, mode="determinate")
            bar.grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=2)
            self.pulse_bars.append(bar)
            ttk.Label(meters, textvariable=self.pulse_rate_vars[index], width=10).grid(row=row, column=1, sticky="e", padx=(8, 12))
            ttk.Label(meters, textvariable=self.applied_vars[index], width=8).grid(row=row, column=2, sticky="e", padx=(8, 0))
            ttk.Label(meters, textvariable=self.pulse_total_vars[index], width=8).grid(row=row, column=3, sticky="e", padx=(8, 0))

        safety = ttk.Frame(root)
        safety.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        safety.columnconfigure(0, weight=1)
        ttk.Button(safety, text="Emergency STOP", command=self.stop, style="Stop.TButton").grid(row=0, column=0, sticky="ew", ipady=10)
        ttk.Button(safety, text="STATUS", command=lambda: self.send_once("STATUS")).grid(row=0, column=1, padx=(8, 0))

        raw = ttk.Frame(root)
        raw.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        raw.columnconfigure(0, weight=1)
        raw.rowconfigure(1, weight=1)
        ttk.Entry(raw, textvariable=self.raw_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(raw, text="Send Raw", command=self.send_raw).grid(row=0, column=1)
        self.log = tk.Text(raw, height=10, wrap="word", state="disabled")
        self.log.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

        style = ttk.Style(self)
        style.configure("Stop.TButton", font=("Segoe UI", 11, "bold"))

    def _bind_keys(self) -> None:
        self.bind("<KeyPress-w>", lambda _event: self.set_tank(1.0, 1.0))
        self.bind("<KeyPress-s>", lambda _event: self.set_tank(-1.0, -1.0))
        self.bind("<KeyPress-a>", lambda _event: self.set_tank(-0.5, 0.5))
        self.bind("<KeyPress-d>", lambda _event: self.set_tank(0.5, -0.5))
        self.bind("<KeyPress-Up>", lambda _event: self.set_tank(1.0, 1.0))
        self.bind("<KeyPress-Down>", lambda _event: self.set_tank(-1.0, -1.0))
        self.bind("<KeyPress-Left>", lambda _event: self.set_tank(-0.5, 0.5))
        self.bind("<KeyPress-Right>", lambda _event: self.set_tank(0.5, -0.5))
        self.bind("<KeyRelease-w>", lambda _event: self.stop())
        self.bind("<KeyRelease-s>", lambda _event: self.stop())
        self.bind("<KeyRelease-a>", lambda _event: self.stop())
        self.bind("<KeyRelease-d>", lambda _event: self.stop())
        self.bind("<KeyRelease-Up>", lambda _event: self.stop())
        self.bind("<KeyRelease-Down>", lambda _event: self.stop())
        self.bind("<KeyRelease-Left>", lambda _event: self.stop())
        self.bind("<KeyRelease-Right>", lambda _event: self.stop())
        self.bind("<space>", lambda _event: self.stop())
        self.bind("<Escape>", lambda _event: self.stop())

    def _drive_button(self, parent: ttk.Frame, text: str, left: float, right: float) -> ttk.Button:
        button = ttk.Button(parent, text=text)
        button.bind("<ButtonPress-1>", lambda _event: self.set_tank(left, right))
        button.bind("<ButtonRelease-1>", lambda _event: self.stop())
        return button

    def _motor_button(self, parent: ttk.Frame, motor: int, direction: float, text: str) -> ttk.Button:
        button = ttk.Button(parent, text=text)
        button.bind("<ButtonPress-1>", lambda _event: self.set_single_motor(motor, direction))
        button.bind("<ButtonRelease-1>", lambda _event: self.stop())
        return button

    def refresh_ports(self) -> None:
        ports = [port.device for port in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def connect(self) -> None:
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Missing port", "Choose the Pico serial port first.")
            return
        try:
            self.serial_worker.connect(port)
        except serial.SerialException as exc:
            messagebox.showerror("Serial error", str(exc))
            return
        self.connection_var.set(f"Connected to {port}")
        self._append_log(f"Connected to {port}")
        self.send_once("STOP")

    def disconnect(self) -> None:
        self.stop()
        self.serial_worker.disconnect()
        self.connection_var.set("Disconnected")
        self._append_log("Disconnected")

    def speed_limit(self) -> float:
        return clamp(self.speed_limit_var.get(), 0.03, HARD_SPEED_LIMIT)

    def set_tank(self, left: float, right: float) -> None:
        limit = self.speed_limit()
        self.held_motor_command = ""
        self.left_power = clamp(left, -1.0, 1.0) * limit
        self.right_power = clamp(right, -1.0, 1.0) * limit
        self.left_var.set(self.left_power / limit)
        self.right_var.set(self.right_power / limit)

    def _slider_changed(self, _value: str) -> None:
        limit = self.speed_limit()
        self.held_motor_command = ""
        self.left_power = clamp(self.left_var.get(), -1.0, 1.0) * limit
        self.right_power = clamp(self.right_var.get(), -1.0, 1.0) * limit

    def apply_sliders(self) -> None:
        self._slider_changed("")

    def build_drive_command(self) -> str:
        powers = []
        for motor in MOTOR_DRIVE_MAP:
            side_power = self.left_power if motor["side"] == "left" else self.right_power
            powers.append(side_power)
        return "DRIVE {:.3f} {:.3f} {:.3f} {:.3f}".format(*powers)

    def set_single_motor(self, motor: int, direction: float) -> None:
        power = clamp(direction, -1.0, 1.0) * self.speed_limit()
        self.left_power = 0.0
        self.right_power = 0.0
        self.left_var.set(0.0)
        self.right_var.set(0.0)
        self.held_motor_command = f"MOTOR {motor} {power:.3f}"
        self.send_once(self.held_motor_command)

    def stop(self) -> None:
        self.held_motor_command = ""
        self.left_power = 0.0
        self.right_power = 0.0
        self.left_var.set(0.0)
        self.right_var.set(0.0)
        self.serial_worker.send_stop()
        self.last_command = "STOP"
        self._append_log("> STOP")

    def send_once(self, command: str) -> None:
        self.serial_worker.send(command)
        self.last_command = command
        self._append_log(f"> {command}")

    def send_raw(self) -> None:
        command = self.raw_var.get().strip()
        if command:
            self.send_once(command)

    def _send_drive_tick(self) -> None:
        if self.serial_worker.connected and self.held_motor_command:
            command = self.held_motor_command
            self.serial_worker.send(command)
            if command != self.last_command:
                self._append_log(f"> {command}")
                self.last_command = command
        elif self.serial_worker.connected and (self.left_power != 0.0 or self.right_power != 0.0):
            command = self.build_drive_command()
            self.serial_worker.send(command)
            if command != self.last_command:
                self._append_log(f"> {command}")
                self.last_command = command
        self.after(SEND_INTERVAL_MS, self._send_drive_tick)

    def _status_tick(self) -> None:
        if self.serial_worker.connected:
            self.serial_worker.send("STATUS")
        self.after(STATUS_INTERVAL_MS, self._status_tick)

    def _drain_serial_lines(self) -> None:
        while True:
            try:
                line = self.line_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_status_line(line)
            self._append_log(line)
        self.after(100, self._drain_serial_lines)

    def _handle_status_line(self, line: str) -> None:
        parts = line.split()
        if len(parts) != 5:
            return
        if parts[0] == "APPLIED":
            for index, value in enumerate(parts[1:5]):
                self.applied_vars[index].set(value)
            return
        if parts[0] != "SPEED_PULSES":
            return
        try:
            pulses = [int(value) for value in parts[1:5]]
        except ValueError:
            return
        now = time.monotonic()
        for index, total in enumerate(pulses):
            self.pulse_total_vars[index].set(str(total))
        if self.last_pulses is not None and self.last_pulse_time is not None:
            elapsed = max(0.001, now - self.last_pulse_time)
            for index, total in enumerate(pulses):
                rate = max(0.0, (total - self.last_pulses[index]) / elapsed)
                self.pulse_rate_vars[index].set(f"{rate:.1f} p/s")
                self.pulse_bars[index]["value"] = min(rate, 50.0)
        self.last_pulses = pulses
        self.last_pulse_time = now

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        line_count = int(self.log.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.log.delete("1.0", f"{line_count - MAX_LOG_LINES}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_close(self) -> None:
        self.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = DriveGui()
    app.mainloop()
