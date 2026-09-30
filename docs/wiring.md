# Wiring

This document records the pin map confirmed during the May 2026 hardware tests.

## Important Electrical Checks

Before connecting the Pico to the motor controllers:

- Confirm the ZS-X11H control input voltage.
- Confirm whether the ZS-X11H expects duty-cycle PWM, servo-style PWM, analog voltage, or another signal.
- Confirm whether speed feedback outputs are safe for 3.3 V Pico GPIO.
- Use common ground between Pico and motor controllers.
- Keep motor power wiring separate from low-voltage signal wiring where possible.

The Pico GPIO pins are 3.3 V only.

## Confirmed Pin Map

The preferred layout keeps PWM and speed pins next to each other where possible.

| Motor | Position | PWM pin | Speed input | Direction pin | Brake pin |
| --- | --- | --- | --- | --- | --- |
| 1 | Right rear | GP2 | GP3 | GP4 | GP5 |
| 2 | Left rear | GP6 | GP7 | GP8 | GP9 |
| 3 | Left front | GP10 | GP11 | GP12 | GP13 |
| 4 | Right front | GP18 | GP19 | GP20 | GP21 |

Notes:

- Each motor controller has its own brake pin.
- No shared STOP GPIO is connected in this wiring.
- GP2 and GP18 share the same RP2040 hardware-PWM slice/channel. Motor 4 therefore uses PIO PWM on GP18; changing it back to ordinary hardware PWM makes motors 1 and 4 mirror each other.
- Positive drive commands are inverted for motors 2 and 3 in firmware so all four physical wheels agree on forward direction.

TODO:

- Confirm brake active polarity if the motor-controller model or wiring changes.
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
M1_PWM, M1_SPEED, M1_DIR, M1_BRAKE
M2_PWM, M2_SPEED, M2_DIR, M2_BRAKE
M3_PWM, M3_SPEED, M3_DIR, M3_BRAKE
M4_PWM, M4_SPEED, M4_DIR, M4_BRAKE
GND
```
