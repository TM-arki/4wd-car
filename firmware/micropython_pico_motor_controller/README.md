# MicroPython Pico Motor Controller

This is a Thonny-friendly version of the Pico firmware. It implements the same USB serial commands as the C++ Pico SDK firmware, so the PC GUI can drive it without changes.

## Install with Thonny

1. Open Thonny.
2. Connect to the Pico MicroPython interpreter.
3. Open `main.py` from this folder.
4. Save it to the Pico as `main.py`.
5. Reboot the Pico.
6. Close Thonny or disconnect its interpreter before starting the PC GUI.

Thonny and the GUI cannot use the same Pico serial port at the same time.

## Quick Check

After reboot, the Pico should print:

```text
MicroPython Pico motor controller ready. Type HELP.
```

Then the GUI can send:

```text
STOP
STATUS
TANK 0.10 0.10
```
