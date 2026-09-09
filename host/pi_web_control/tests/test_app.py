from types import SimpleNamespace

import app


def test_clamp():
    assert app.clamp(2.0, -1.0, 1.0) == 1.0
    assert app.clamp(-2.0, -1.0, 1.0) == -1.0
    assert app.clamp(0.25, -1.0, 1.0) == 0.25


def test_drive_mapping_matches_robot_layout():
    command = app.build_drive_command(left=0.5, right=-0.25, limit=0.2)
    assert command == "DRIVE -0.050 0.100 0.100 -0.050"


def test_rpm_conversion_matches_previous_working_calibration():
    assert app.rpm_from_pulse_delta(15, 1.0) == 60.0
    assert app.rpm_from_pulse_delta(50, 1.0) == 200.0


def test_serial_discovery_prefers_raspberry_pi_pico(monkeypatch):
    ports = [
        SimpleNamespace(device="/dev/ttyUSB0", description="USB serial", vid=0x1234),
        SimpleNamespace(device="/dev/ttyACM1", description="Raspberry Pi Pico", vid=0x2E8A),
        SimpleNamespace(device="/dev/ttyACM0", description="Other ACM", vid=0x9999),
    ]
    monkeypatch.setattr(app.list_ports, "comports", lambda: ports)
    assert app.discover_serial_port("auto") == "/dev/ttyACM1"


def test_serial_discovery_honors_existing_preferred_port(monkeypatch):
    ports = [
        SimpleNamespace(device="/dev/ttyACM0", description="Pico", vid=0x2E8A),
        SimpleNamespace(device="/dev/ttyACM1", description="Pico", vid=0x2E8A),
    ]
    monkeypatch.setattr(app.list_ports, "comports", lambda: ports)
    assert app.discover_serial_port("/dev/ttyACM1") == "/dev/ttyACM1"


def test_protocol_parser_accepts_applied_and_firmware_lines():
    state = app.RobotState()
    pico = app.PicoSerial(state, autoconnect=False)
    pico.handle_line("APPLIED 0.100 -0.200 0.300 -0.400")
    pico.handle_line("FW 2026.09-reliability")
    pico.handle_line("WATCHDOG ACTIVE 400")
    assert state.applied == ["0.100", "-0.200", "0.300", "-0.400"]
    assert state.pico_firmware == "2026.09-reliability"
    assert state.pico_watchdog == "ACTIVE 400"


def test_health_endpoint_does_not_require_motor_hardware():
    flask_app = app.create_app("auto", False)
    client = flask_app.test_client()
    response = client.get("/health")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["service"] == "4wd-robot-web-control"


def test_state_endpoint_exposes_rpm_and_system_info():
    flask_app = app.create_app("auto", False)
    client = flask_app.test_client()
    response = client.get("/api/state")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["rpm"] == [0.0, 0.0, 0.0, 0.0]
    assert payload["system"]["pulsesPerRevolution"] == 15.0
