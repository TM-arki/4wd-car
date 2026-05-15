# Wiring

This document describes the first proposed Pico pin map. Treat it as a starting point until the real wiring and ZS-X11H signal requirements are confirmed.

## Important Electrical Checks

Before connecting the Pico to the motor controllers:

- Confirm the ZS-X11H control input voltage.
- Confirm whether the ZS-X11H expects duty-cycle PWM, servo-style PWM, analog voltage, or another signal.
- Confirm whether speed feedback outputs are safe for 3.3 V Pico GPIO.
- Use common ground between Pico and motor controllers.
- Keep motor power wiring separate from low-voltage signal wiring where possible.

The Pico GPIO pins are 3.3 V only.

## Proposed Pin Map

The preferred layout keeps PWM and speed pins next to each other where possible.

| Motor | Position | PWM pin | Speed input | Direction pin | Brake pin | Stop pin |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Front left | GP2 | GP3 | GP10 | GP14 | GP15 |
| 2 | Front right | GP4 | GP5 | GP11 | GP14 | GP15 |
| 3 | Rear left | GP6 | GP7 | GP12 | GP14 | GP15 |
| 4 | Rear right | GP18 | GP19 | GP13 | GP14 | GP15 |

Notes:

- Brake and stop are shared in this first version.
- GP18/GP19 are used for motor 4 because the fourth controller may need to start around GP18 due to board layout.
- Direction pins are separate from PWM pins for clarity.

TODO:

- Confirm if each ZS-X11H needs separate brake and stop pins.
- Confirm brake and stop active polarity.
- Confirm direction active polarity.
- Confirm whether speed inputs need pull-ups, pull-downs, filtering, or level shifting.

## Power Wiring

TODO:

- Confirm battery voltage and fuse size.
- Add main power switch or contactor details.
- Add emergency stop wiring.
- Add low-voltage regulator details for Pico and host computer.

Recommended bring-up sequence:

1. Test Pico USB serial with no motor power connected.
2. Test GPIO output with a meter or oscilloscope.
3. Connect one motor controller signal at a time.
4. Test with wheels off the ground.
5. Use low power commands only until direction and braking are confirmed.

## Signal Naming

Suggested signal names for labels:

```text
M1_PWM, M1_SPEED, M1_DIR
M2_PWM, M2_SPEED, M2_DIR
M3_PWM, M3_SPEED, M3_DIR
M4_PWM, M4_SPEED, M4_DIR
MOTOR_BRAKE
MOTOR_STOP
GND
```
