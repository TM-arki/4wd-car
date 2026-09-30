# Raspberry Pi Web Control

This is a small Flask web app for running the robot without a PC GUI. The Raspberry Pi connects to the Pico over USB serial and hosts a browser control page on port `8080`.

The app uses the same serial commands as `host/robot_control/gui_drive.py`:

- `DRIVE m1 m2 m3 m4`
- `MOTOR n power`
- `STOP`
- `STATUS`

## Run on a Raspberry Pi

```bash
cd ~/4wd-car/host/pi_web_control
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py --serial-port /dev/ttyACM0 --port 8080
```

Open:

```text
http://raspberrypi.local:8080
```

or, when using the hotspot guide:

```text
http://10.42.0.1:8080
```

## Autostart

The `systemd/robot-web-control.service` file assumes this repository is copied to `/home/pi/4wd-car` and that the virtualenv exists at `/home/pi/4wd-car/host/pi_web_control/.venv`.

Install it with:

```bash
sudo cp systemd/robot-web-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now robot-web-control.service
sudo systemctl status robot-web-control.service
```
