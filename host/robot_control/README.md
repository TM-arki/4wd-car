# Robot Control Host Script

This folder contains a small Python command-line tool for sending USB serial commands to the Pico.

## Install

```powershell
python -m pip install -r requirements.txt
```

## Examples

```powershell
python robot_control.py --port COM5 status
python robot_control.py --port COM5 stop
python robot_control.py --port COM5 forward --power 0.15
python robot_control.py --port COM5 reverse --power 0.15
python robot_control.py --port COM5 motor --motor 1 --power 0.10
python robot_control.py --port COM5 drive --m1 0.10 --m2 0.10 --m3 0.10 --m4 0.10
python robot_control.py --port COM5 test
```

On Linux, the port may be `/dev/ttyACM0`.
