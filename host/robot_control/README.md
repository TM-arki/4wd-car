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
python robot_control.py --port COM5 tank --left 0.10 --right 0.08
python robot_control.py --port COM5 --hold 2 tank --left 0.10 --right 0.08
python robot_control.py --port COM5 cal
python robot_control.py --port COM5 cal --motor 2 --field gain --value 0.95
python robot_control.py --port COM5 raw "CAL 1 MAX 0.60"
python robot_control.py --port COM5 test
```

On Linux, the port may be `/dev/ttyACM0`.

## Low Speed GUI

Start the local USB drive GUI:

```powershell
python gui_drive.py
```

The GUI sends low-speed drive commands every 100 ms while moving. Default speed limit is `0.15`, with a hard GUI cap at `0.30`. WASD and arrow keys are hold-to-drive. Space, Escape, button release, or window focus loss sends `STOP`.
