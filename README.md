# 4WD Hoverboard Hub Motor Robot

Small 4 wheel drive robot using hoverboard hub motors, four ZS-X11H motor controllers, an RP2040 / Raspberry Pi Pico as the low-level motor controller, and a Raspberry Pi as the host computer.

The repository is intentionally split into two safety layers:

- **Pico:** PWM, direction, speed feedback, STOP/BRAKE and the final command watchdog.
- **Raspberry Pi:** web control, joystick/tank mixing, USB reconnect, diagnostics and software update/recovery.

## Repository layout

```text
.
|-- .github/workflows/ci.yml
|-- docs/
|   |-- architecture.md
|   |-- raspberry-pi-web-control.md
|   |-- reliability-upgrade.md
|   |-- startup-and-deployment.md
|   `-- wiring.md
|-- firmware/
|   `-- pico_motor_controller/
|       |-- CMakeLists.txt
|       |-- include/motor_config.h
|       `-- src/main.cpp
|-- host/
|   |-- pi_web_control/
|   |   |-- app.py
|   |   |-- requirements.txt
|   |   |-- scripts/
|   |   |-- systemd/
|   |   |-- templates/
|   |   `-- tests/
|   `-- robot_control/
|-- scripts/
`-- .gitignore
```

## Current hardware assumptions

- 4 hoverboard hub motors.
- 4x ZS-X11H motor controllers.
- Pico outputs duty-cycle PWM speed commands.
- Pico reads one ZS-X11H SC speed-pulse signal per motor.
- USB serial at 115200 baud is the command link between Raspberry Pi and Pico.
- Raspberry Pi hosts the control UI and robot Wi-Fi hotspot.

See [docs/wiring.md](docs/wiring.md) before changing hardware.

## Safety model

Motion commands are leased rather than permanent.

The Raspberry Pi renews active commands about every 100 ms. The Pico has an independent **400 ms command watchdog**. If new motion commands stop arriving because the browser closes, the Pi process crashes, USB is disconnected, or communication otherwise fails, the Pico sets all PWM outputs to zero and activates STOP/BRAKE.

Always keep a physical power disconnect available as the final safety layer.

## Serial commands

Commands are newline-terminated ASCII.

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

`STATUS` returns applied motor values, cumulative speed pulses, Pico firmware version and watchdog state.

## Build Pico firmware

Install the Raspberry Pi Pico SDK and CMake toolchain first.

```powershell
cd firmware/pico_motor_controller
cmake -S . -B build
cmake --build build
```

Or from the repository root on Windows:

```powershell
.\scripts\build_firmware.ps1
```

The UF2 appears under `firmware/pico_motor_controller/build`.

CI also builds the firmware automatically on pushes and pull requests.

## Raspberry Pi web control

The Raspberry Pi can connect to the Pico automatically, host a Wi-Fi hotspot and serve the browser UI.

The web UI includes:

- joystick drive control;
- left/right tank test;
- individual motor tests;
- emergency STOP;
- wheel RPM;
- Pico and Pi software versions;
- USB reconnect state;
- update/rollback status;
- raw command/log view.

See [docs/raspberry-pi-web-control.md](docs/raspberry-pi-web-control.md).

## Reliability upgrade

The reliability layer adds:

- Pico-side 400 ms command watchdog;
- automatic Pico USB discovery/reconnect;
- serial exception handling;
- `/health` endpoint;
- last-known-good software rollback;
- diagnostics/version information;
- automated host and firmware CI;
- RPM conversion using the robot's previously tested 15 pulses/revolution calibration.

See [docs/reliability-upgrade.md](docs/reliability-upgrade.md).

## RPM

Wheel speed is calculated from the ZS-X11H SC pulse output:

```text
RPM = (pulse_delta / 15) * (60 / elapsed_seconds)
```

The 15 pulses/revolution value is the calibration previously used on this robot and produced readings around 200 RPM during testing. Recalibrate if the motor/controller combination changes.

## Host development script

A simple PC-side script is still available under `host/robot_control`.

```powershell
cd host/robot_control
python -m pip install -r requirements.txt
python robot_control.py --port COM5 stop
```

Replace `COM5` with the Pico serial port shown on the PC.

## Safety notes

- First test after firmware/software changes with all wheels off the ground.
- Press STOP before beginning a motion test.
- Start with a low speed limit.
- Keep a physical power disconnect nearby.
- Do not change motor mapping, pin assignments, signal polarity or PWM electrical assumptions without hardware verification.
- The software watchdog is an additional layer; it is not a substitute for a physical emergency power disconnect.

## Next hardware-validation tasks

- Verify the current Pico GPIO mapping against the physical harness.
- Confirm RPM calibration against an independent wheel-speed measurement.
- Verify watchdog stop by deliberately disconnecting USB during a low-speed elevated-wheel test.
- Verify automatic rollback with a deliberately unhealthy test release before promoting the reliability branch to `main`.
