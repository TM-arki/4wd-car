import argparse
import sys
from pathlib import Path


HOST_DIR = Path(__file__).resolve().parents[1] / "host" / "robot_control"
sys.path.insert(0, str(HOST_DIR))

from robot_control import send_command  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Send STOP to the Pico motor controller.")
    parser.add_argument("--port", required=True, help="Serial port, for example COM5 or /dev/ttyACM0.")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    send_command(args.port, args.baud, "STOP")


if __name__ == "__main__":
    main()
