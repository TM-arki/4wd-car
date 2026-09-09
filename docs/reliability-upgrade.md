# Reliability upgrade

This branch adds the safety and recovery layer needed before the robot is driven more seriously.

## What changed

1. **Pico command watchdog**
   - Any `MOTOR`, `DRIVE`, `FORWARD`, or `REVERSE` command that produces motion must be renewed within 400 ms.
   - If commands stop arriving, the Pico sets every PWM output to zero and activates STOP/BRAKE.
   - This is independent of the Raspberry Pi and protects against a crashed host process or broken USB link.

2. **Automatic Pico USB discovery and reconnect**
   - The Pi web app accepts `--serial-port auto`.
   - Raspberry Pi Pico USB devices are preferred, followed by `/dev/ttyACM*` and then `/dev/ttyUSB*`.
   - If the serial link disappears, the app marks the Pico disconnected and retries automatically.
   - Every successful reconnect immediately sends `STOP` before other commands.

3. **Serial error handling**
   - Read/write failures transition to a disconnected state rather than killing the control thread.
   - The UI shows the most recent serial error and reconnect count.

4. **Version and diagnostics in the web UI**
   - Git commit and branch.
   - Pico firmware version.
   - Pico watchdog state.
   - Last Pico response age.
   - Reconnect count.
   - Update/rollback state.
   - Web-service uptime.

5. **Last-known-good software rollback**
   - `boot_update.sh` records the previous commit before installing a candidate release.
   - The candidate receives a Python syntax/import smoke test.
   - `confirm_release.sh` then waits for `/health`.
   - If the health check fails, the repository is reset to the last-known-good commit and systemd restarts the old version.
   - An unconfirmed pending release is also rolled back at the next boot.

6. **Health endpoint**
   - `GET /health` returns HTTP 200 when the web service itself is healthy.
   - Pico connection state is reported but is not required for service health, so a disconnected Pico does not trigger a software rollback.

7. **CI**
   - Python syntax checks and pytest coverage for mapping, RPM conversion, USB discovery, protocol parsing and `/health`.
   - Shell syntax checks for boot/recovery scripts.
   - Full Raspberry Pi Pico firmware build against Pico SDK 2.1.1 and the ARM GCC toolchain.

8. **RPM display**
   - The Pi converts the ZS-X11H speed-pulse totals to wheel RPM.
   - Current calibration is **15 pulses per wheel revolution**, which is the value previously used on this robot and gave about 200 RPM at the tested speed.
   - The raw cumulative pulse totals remain available through `/api/state`.

## One-time installation on the Raspberry Pi

Do this only when testing this branch with the robot safely lifted so all wheels can spin freely.

```bash
cd ~/4wd-car
git fetch origin
git checkout reliability-upgrade
git pull

cd host/pi_web_control
. .venv/bin/activate
python -m pip install -r requirements.txt

sudo cp systemd/robot-boot-update.service /etc/systemd/system/
sudo cp systemd/robot-web-control.service /etc/systemd/system/
```

The service template deliberately still defaults to `main` for normal production use. While this PR is being hardware-tested, add a temporary systemd override so a reboot does not replace the test branch with `main`:

```bash
sudo mkdir -p /etc/systemd/system/robot-boot-update.service.d
printf '[Service]\nEnvironment=ROBOT_GIT_BRANCH=reliability-upgrade\n' | sudo tee /etc/systemd/system/robot-boot-update.service.d/test-branch.conf

sudo systemctl daemon-reload
sudo systemctl enable robot-boot-update.service robot-web-control.service
sudo systemctl restart robot-web-control.service
```

The updated systemd files are important because they enable the health-confirmation/rollback flow and switch the serial setting to `auto`.

After the PR has passed hardware testing and is merged to `main`, remove the temporary branch override:

```bash
sudo rm -f /etc/systemd/system/robot-boot-update.service.d/test-branch.conf
sudo systemctl daemon-reload
```

From then on, the installed boot-update service follows `main` again.

## Test checklist before merging to main

1. Wheels off the ground.
2. Start the Pi and open `http://10.42.0.1:8080`.
3. Confirm the diagnostics section shows the expected Git commit and Pico firmware.
4. Press STOP before any motion test.
5. Test each wheel individually at the default 0.15 limit.
6. Confirm RPM appears and is roughly consistent across all four wheels.
7. Hold a low joystick command, then deliberately disconnect the USB cable to the Pico. Motion must stop within about 0.4 seconds.
8. Reconnect USB. The UI should reconnect automatically and remain stopped.
9. Reboot the Pi and confirm it remains on `reliability-upgrade` during testing and update status becomes `healthy`.
10. Only after these checks should `reliability-upgrade` be merged into `main`.

## State files

Runtime update state is stored under:

```text
~/4wd-car/.robot_state/
```

It is intentionally ignored by Git. Important files are:

- `last-good-commit`
- `pending-commit`
- `update-status.json`

## RPM calibration

The software currently uses:

```text
RPM = (pulse_delta / 15) * (60 / elapsed_seconds)
```

If a later controller or motor produces a different number of SC pulses per revolution, change `SPEED_PULSES_PER_REVOLUTION` in `host/pi_web_control/app.py` and update its unit test.
