# Startup and Deployment

This page describes a simple workflow for developing on a PC and deploying to the robot.

## Development PC Workflow

1. Build the Pico firmware.
2. Flash the UF2 file to the Pico.
3. Connect to the Pico over USB serial.
4. Send `HELP`, `STATUS`, and `STOP`.
5. Test commands with motor power disconnected first.
6. Test one motor at low power with wheels off the ground.

## Flashing the Pico

1. Hold the `BOOTSEL` button on the Pico.
2. Connect USB.
3. Release `BOOTSEL`.
4. Copy the generated `.uf2` file to the Pico mass storage drive.
5. The Pico will reboot and expose a USB serial port.

TODO:

- Add the exact UF2 filename after the first successful build.
- Add screenshots or notes for the specific Pico USB-C board.

## Host Script Setup

From the repository root:

```powershell
cd host/robot_control
python -m pip install -r requirements.txt
```

Example:

```powershell
python robot_control.py --port COM5 status
python robot_control.py --port COM5 stop
python robot_control.py --port COM5 forward --power 0.15
python robot_control.py --port COM5 reverse --power 0.15
python robot_control.py --port COM5 test
```

On Linux, the serial port may look like `/dev/ttyACM0`.

## Robot Startup Checklist

Use this checklist before each powered test:

- Robot is lifted so wheels can spin freely.
- Main battery is fused.
- Emergency power disconnect is reachable.
- Pico is connected over USB.
- Host can send `STOP`.
- Motor controller signal ground and Pico ground are connected.
- Motor direction is known or test power is very low.

## Deployment Later

When a Raspberry Pi or NVIDIA board is added, it should run the Python host command code or a later service built on the same serial protocol.

TODO:

- Add a Linux service file for automatic startup.
- Add joystick or remote-control input.
- Add structured logging.
- Add a configuration file for port name and motor limits.
