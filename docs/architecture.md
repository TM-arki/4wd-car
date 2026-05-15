# Architecture

This project starts with a two-layer robot control architecture.

## Layers

```text
Development PC / Raspberry Pi / NVIDIA board
        |
        | USB serial commands
        v
Raspberry Pi Pico / RP2040
        |
        | PWM, direction, brake, stop, speed inputs
        v
4x ZS-X11H motor controllers
        |
        v
4x hoverboard hub motors
```

## Pico Responsibilities

The Pico is responsible for low-level behavior that should stay simple and reliable:

- Keep motors stopped during startup.
- Generate PWM signals for four motor controllers.
- Set direction pins for forward and reverse commands.
- Optionally control brake and stop pins.
- Read speed feedback pins.
- Accept simple USB serial commands from a host computer.
- Provide status information for debugging.

The Pico should not run high-level navigation, mapping, camera processing, or autonomy.

## Host Computer Responsibilities

The host computer can be a development PC at first, then later a Raspberry Pi or NVIDIA board.

The host is responsible for:

- Sending drive commands over USB serial.
- Running manual test scripts.
- Later: joystick control, autonomy, navigation, logging, and safety supervision.

## Serial Protocol

The first protocol is intentionally plain text and beginner-friendly.

Each command is one line ending with `\n`.

Examples:

```text
STOP
FORWARD 0.20
REVERSE 0.20
DRIVE 0.10 0.10 0.10 0.10
MOTOR 2 -0.15
STATUS
```

Power values are normalized:

- `-1.0` is full reverse.
- `0.0` is stopped.
- `1.0` is full forward.

## Safety Model

Current first-version safety behavior:

- On boot, all PWM outputs are set to zero.
- Brake is enabled during startup when configured.
- `STOP` immediately sets all motor outputs to zero.
- Invalid commands do not move the robot.
- `TEST` uses low power values and returns to stop.

TODO:

- Add a command timeout so motors stop if the host stops sending commands.
- Add measured speed sanity checks.
- Add emergency stop input pin if the hardware includes one.
- Add current or voltage monitoring if available from the motor controllers.

## Motor Numbering

Initial motor numbering:

```text
Motor 1: front left
Motor 2: front right
Motor 3: rear left
Motor 4: rear right
```

TODO: Confirm physical motor numbering before final wiring labels are printed.
