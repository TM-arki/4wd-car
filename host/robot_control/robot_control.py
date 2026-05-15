import argparse
import time

import serial


def clamp_power(value: float) -> float:
    return max(-1.0, min(1.0, value))


def send_command(port: str, baud: int, command: str, wait: float = 0.2) -> None:
    with serial.Serial(port, baudrate=baud, timeout=1) as connection:
        time.sleep(0.2)
        connection.write((command.strip() + "\n").encode("ascii"))
        connection.flush()
        time.sleep(wait)

        while connection.in_waiting:
            print(connection.readline().decode("ascii", errors="replace").strip())


def build_command(args: argparse.Namespace) -> str:
    if args.action == "help":
        return "HELP"
    if args.action == "status":
        return "STATUS"
    if args.action == "stop":
        return "STOP"
    if args.action == "test":
        return "TEST"
    if args.action == "forward":
        return f"FORWARD {clamp_power(args.power):.3f}"
    if args.action == "reverse":
        return f"REVERSE {abs(clamp_power(args.power)):.3f}"
    if args.action == "motor":
        return f"MOTOR {args.motor} {clamp_power(args.power):.3f}"
    if args.action == "drive":
        return (
            f"DRIVE {clamp_power(args.m1):.3f} {clamp_power(args.m2):.3f} "
            f"{clamp_power(args.m3):.3f} {clamp_power(args.m4):.3f}"
        )
    raise ValueError(f"Unsupported action: {args.action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send commands to the Pico motor controller.")
    parser.add_argument("--port", required=True, help="Serial port, for example COM5 or /dev/ttyACM0.")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate.")

    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("help")
    subparsers.add_parser("status")
    subparsers.add_parser("stop")
    subparsers.add_parser("test")

    forward_parser = subparsers.add_parser("forward")
    forward_parser.add_argument("--power", type=float, default=0.15)

    reverse_parser = subparsers.add_parser("reverse")
    reverse_parser.add_argument("--power", type=float, default=0.15)

    motor_parser = subparsers.add_parser("motor")
    motor_parser.add_argument("--motor", type=int, choices=[1, 2, 3, 4], required=True)
    motor_parser.add_argument("--power", type=float, required=True)

    drive_parser = subparsers.add_parser("drive")
    drive_parser.add_argument("--m1", type=float, required=True)
    drive_parser.add_argument("--m2", type=float, required=True)
    drive_parser.add_argument("--m3", type=float, required=True)
    drive_parser.add_argument("--m4", type=float, required=True)

    args = parser.parse_args()
    command = build_command(args)
    print(f"> {command}")
    send_command(args.port, args.baud, command)


if __name__ == "__main__":
    main()
