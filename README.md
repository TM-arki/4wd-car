# 4WD Hoverboard Hub Motor Robot

Minimal starting repository for a small 4 wheel drive robot using hoverboard hub motors, four ZS-X11H motor controllers, and an RP2040 / Raspberry Pi Pico as the low-level motor controller.

The first goal is not a perfect robot stack. The first goal is a clean, safe, testable foundation:

- Pico handles PWM motor output, speed feedback inputs, and safety stop behavior.
- A future Raspberry Pi or NVIDIA board sends simple commands over USB serial.
- Development PC can run the host scripts before the robot computer is installed.
- Code and comments are in English.

## Repository Layout

```text
.
|-- docs/
|   |-- architecture.md
|   |-- startup-and-deployment.md
|   `-- wiring.md
|-- firmware/
|   `-- pico_motor_controller/
|       |-- CMakeLists.txt
|       |-- include/
|       |   `-- motor_config.h
|       `-- src/
|           `-- main.cpp
|-- host/
|   `-- robot_control/
|       |-- README.md
|       |-- requirements.txt
|       `-- robot_control.py
|-- scripts/
|   |-- build_firmware.ps1
|   `-- send_stop.py
`-- .gitignore
```

## Current Hardware Assumptions

- Robot uses 4 hoverboard hub motors.
- Motor controllers are 4x ZS-X11H.
- Pico outputs PWM speed commands.
- Pico reads one speed feedback input per motor.
- Direction, brake, and stop pins are included in the first firmware because they are useful for safe bring-up.
- USB serial is the command interface between the host computer and the Pico.

See [docs/wiring.md](docs/wiring.md) before connecting hardware.

## Example Serial Commands

Commands are newline-terminated ASCII text.

```text
HELP
STATUS
STOP
FORWARD 0.20
REVERSE 0.20
DRIVE 0.15 0.15 0.15 0.15
MOTOR 1 0.10
BRAKE ON
BRAKE OFF
TEST
```

Power values are normalized from `-1.0` to `1.0`.

- Positive values drive forward.
- Negative values drive reverse.
- `0.0` stops PWM output for that motor.

## Build Firmware

Install the Raspberry Pi Pico SDK and CMake toolchain first.

```powershell
cd firmware/pico_motor_controller
cmake -S . -B build
cmake --build build
```

Or from the repository root:

```powershell
.\scripts\build_firmware.ps1
```

The output UF2 file should appear under `firmware/pico_motor_controller/build`.

## Run Host Script

Install Python dependencies:

```powershell
cd host/robot_control
python -m pip install -r requirements.txt
```

Send a stop command:

```powershell
python robot_control.py --port COM5 stop
```

Run a very gentle test:

```powershell
python robot_control.py --port COM5 test
```

Replace `COM5` with the Pico serial port shown on your development PC.

## Safety Notes

- Test first with the wheels off the ground.
- Start with motor controllers powered, but motors mechanically safe.
- Keep a physical power disconnect nearby.
- Confirm ZS-X11H signal voltage expectations before connecting Pico GPIO directly.
- Confirm whether each controller expects servo-style PWM, duty-cycle PWM, direction pins, brake pins, or another control mode.

## TODO

- Confirm exact ZS-X11H pinout and signal mode.
- Confirm Pico board variant and available GPIO pins.
- Confirm speed feedback signal type and voltage.
- Add measured speed calculation once feedback hardware is known.
- Add watchdog timeout behavior for lost USB serial commands.
- Add host-side logging and configuration file later.
