from machine import Pin, PWM
import math
import rp2
import select
import sys
import time


PWM_FREQUENCY_HZ = 1000
MOTOR_COUNT = 4
COMMAND_TIMEOUT_MS = 600
RAMP_PER_SECOND = 1.8

DIRECTION_FORWARD_LEVEL = 0
BRAKE_ACTIVE_LEVEL = 1

MOTOR_PINS = [
    {"pwm": 2, "speed": 3, "direction": 4, "brake": 5},      # Motor 1
    {"pwm": 6, "speed": 7, "direction": 8, "brake": 9},      # Motor 2
    {"pwm": 10, "speed": 11, "direction": 12, "brake": 13},  # Motor 3
    {"pwm": 18, "speed": 19, "direction": 20, "brake": 21},  # Motor 4
]

DEFAULT_CALIBRATION = [
    {"gain": 1.0, "trim": 0.0, "min": 0.0, "max": 0.80, "deadband": 0.03, "invert": False},
    {"gain": 1.0, "trim": 0.0, "min": 0.0, "max": 0.80, "deadband": 0.03, "invert": True},
    {"gain": 1.0, "trim": 0.0, "min": 0.0, "max": 0.80, "deadband": 0.03, "invert": True},
    {"gain": 1.0, "trim": 0.0, "min": 0.0, "max": 0.80, "deadband": 0.03, "invert": False},
]


@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW)
def pio_pwm_program():
    pull(noblock).side(0)
    mov(x, osr)
    mov(y, isr)
    label("loop")
    jmp(x_not_y, "skip")
    nop().side(1)
    label("skip")
    jmp(y_dec, "loop")


class PioPwm:
    def __init__(self, state_machine_id, pin, max_count=1000, frequency=1_200_000):
        self.max_count = max_count
        self.state_machine = rp2.StateMachine(
            state_machine_id,
            pio_pwm_program,
            freq=frequency,
            sideset_base=Pin(pin),
        )
        self.state_machine.put(max_count)
        self.state_machine.exec("pull()")
        self.state_machine.exec("mov(isr, osr)")
        self.state_machine.active(1)
        self.duty_u16(0)

    def duty_u16(self, duty):
        duty = int(clamp(duty, 0, 65535))
        self.state_machine.put((duty * self.max_count) // 65535)


def clamp(value, low, high):
    return max(low, min(high, value))


def copy_calibration():
    return [item.copy() for item in DEFAULT_CALIBRATION]


class MotorController:
    def __init__(self):
        self.calibration = copy_calibration()
        self.target = [0.0] * MOTOR_COUNT
        self.ramped = [0.0] * MOTOR_COUNT
        self.applied = [0.0] * MOTOR_COUNT
        self.speed_pulses = [0] * MOTOR_COUNT
        self.drive_released = False
        self.last_command_ms = time.ticks_ms()
        self.last_poll_ms = self.last_command_ms

        self.pwm = []
        self.direction = []
        self.speed = []
        self.brake = []

        for index, pins in enumerate(MOTOR_PINS):
            if index == 3:
                pwm = PioPwm(0, pins["pwm"])
            else:
                pwm = PWM(Pin(pins["pwm"]))
                pwm.freq(PWM_FREQUENCY_HZ)
            pwm.duty_u16(0)
            self.pwm.append(pwm)

            direction = Pin(pins["direction"], Pin.OUT)
            direction.value(DIRECTION_FORWARD_LEVEL)
            self.direction.append(direction)

            speed = Pin(pins["speed"], Pin.IN, Pin.PULL_DOWN)
            speed.irq(trigger=Pin.IRQ_RISING, handler=self._make_speed_handler(index))
            self.speed.append(speed)

            brake = Pin(pins["brake"], Pin.OUT)
            self.brake.append(brake)

        self.stop_all()

    def _make_speed_handler(self, index):
        def handler(_pin):
            self.speed_pulses[index] += 1

        return handler

    def note_command(self, now_ms=None):
        self.last_command_ms = now_ms if now_ms is not None else time.ticks_ms()

    def release_for_drive(self, now_ms=None):
        self.note_command(now_ms)
        self.set_controller_stop(False)
        self.set_brake(False)
        self.drive_released = True

    def set_brake(self, enabled):
        for brake in self.brake:
            brake.value(BRAKE_ACTIVE_LEVEL if enabled else 1 - BRAKE_ACTIVE_LEVEL)

    def set_motor_brake(self, index, enabled):
        if 0 <= index < MOTOR_COUNT:
            self.brake[index].value(BRAKE_ACTIVE_LEVEL if enabled else 1 - BRAKE_ACTIVE_LEVEL)

    def set_controller_stop(self, enabled):
        pass

    def stop_all(self):
        for index in range(MOTOR_COUNT):
            self.target[index] = 0.0
            self.ramped[index] = 0.0
            self._write_motor(index, 0.0)
        self.set_brake(True)
        self.set_controller_stop(True)
        self.drive_released = False

    def set_one(self, index, power):
        if 0 <= index < MOTOR_COUNT:
            self.target[index] = clamp(power, -1.0, 1.0)

    def set_pwm_only(self, index, power):
        if 0 <= index < MOTOR_COUNT:
            self.target[index] = 0.0
            self.ramped[index] = 0.0
            duty = int(abs(clamp(power, -1.0, 1.0)) * 65535)
            self.pwm[index].duty_u16(duty)
            self.applied[index] = abs(clamp(power, -1.0, 1.0))

    def set_direction_only(self, index, reverse):
        if 0 <= index < MOTOR_COUNT:
            forward = not reverse
            self.direction[index].value(DIRECTION_FORWARD_LEVEL if forward else 1 - DIRECTION_FORWARD_LEVEL)

    def set_drive(self, powers):
        for index, power in enumerate(powers[:MOTOR_COUNT]):
            self.set_one(index, power)

    def set_all(self, power):
        for index in range(MOTOR_COUNT):
            self.set_one(index, power)

    def reset_pulses(self):
        self.speed_pulses = [0] * MOTOR_COUNT

    def reset_calibration(self):
        self.calibration = copy_calibration()

    def set_calibration(self, index, field, value):
        if not 0 <= index < MOTOR_COUNT:
            return False

        field = field.lower()
        cal = self.calibration[index]
        if field == "gain":
            cal["gain"] = clamp(value, 0.0, 2.0)
        elif field == "trim":
            cal["trim"] = clamp(value, -0.25, 0.25)
        elif field == "min":
            cal["min"] = clamp(value, 0.0, 0.50)
        elif field == "max":
            cal["max"] = clamp(value, 0.05, 1.0)
        elif field == "deadband":
            cal["deadband"] = clamp(value, 0.0, 0.25)
        elif field == "invert":
            cal["invert"] = value >= 0.5
        else:
            return False
        return True

    def poll(self):
        now_ms = time.ticks_ms()
        if self.drive_released and time.ticks_diff(now_ms, self.last_command_ms) > COMMAND_TIMEOUT_MS:
            self.stop_all()
            print("WARN command timeout; motors stopped")

        elapsed_ms = max(0, time.ticks_diff(now_ms, self.last_poll_ms))
        self.last_poll_ms = now_ms
        step = RAMP_PER_SECOND * (elapsed_ms / 1000.0)

        for index in range(MOTOR_COUNT):
            self.ramped[index] = self._ramp_toward(self.ramped[index], self.target[index], step)
            self._write_motor(index, self._apply_calibration(index, self.ramped[index]))

    def _ramp_toward(self, current, target, step):
        if current < target:
            return min(target, current + step)
        if current > target:
            return max(target, current - step)
        return current

    def _apply_calibration(self, index, command):
        cal = self.calibration[index]
        magnitude = abs(command)
        if magnitude < cal["deadband"]:
            return 0.0

        magnitude = (magnitude * cal["gain"]) + cal["trim"]
        magnitude = clamp(magnitude, 0.0, cal["max"])
        if 0.0 < magnitude < cal["min"]:
            magnitude = cal["min"]

        signed_output = -magnitude if command < 0.0 else magnitude
        if cal["invert"]:
            signed_output = -signed_output
        return clamp(signed_output, -1.0, 1.0)

    def _write_motor(self, index, power):
        forward = power >= 0.0
        duty = int(abs(power) * 65535)
        self.direction[index].value(DIRECTION_FORWARD_LEVEL if forward else 1 - DIRECTION_FORWARD_LEVEL)
        self.pwm[index].duty_u16(duty)
        self.applied[index] = power


controller = MotorController()


def print_help():
    print("Commands:")
    print("  HELP")
    print("  STATUS")
    print("  CAL")
    print("  CAL RESET")
    print("  CAL <1-4> GAIN|TRIM|MIN|MAX|DEADBAND|INVERT <value>")
    print("  STOP")
    print("  BRAKE ON|OFF")
    print("  BRAKE <1-4> ON|OFF")
    print("  MOTOR <1-4> <-1.0..1.0>")
    print("  PWMONLY <1-4> <0.0..1.0>")
    print("  DIR <1-4> FWD|REV")
    print("  DRIVE <m1> <m2> <m3> <m4>")
    print("  TANK <left> <right>")
    print("  FORWARD <0.0..1.0>")
    print("  REVERSE <0.0..1.0>")
    print("  RESET_PULSES")
    print("  TEST")


def print_status():
    print("TARGET {:.3f} {:.3f} {:.3f} {:.3f}".format(*controller.target))
    print("RAMPED {:.3f} {:.3f} {:.3f} {:.3f}".format(*controller.ramped))
    print("APPLIED {:.3f} {:.3f} {:.3f} {:.3f}".format(*controller.applied))
    print("SPEED_PULSES {} {} {} {}".format(*controller.speed_pulses))


def print_calibration():
    for index, cal in enumerate(controller.calibration):
        print(
            "CAL {} GAIN {:.3f} TRIM {:.3f} MIN {:.3f} MAX {:.3f} DEADBAND {:.3f} INVERT {}".format(
                index + 1,
                cal["gain"],
                cal["trim"],
                cal["min"],
                cal["max"],
                cal["deadband"],
                1 if cal["invert"] else 0,
            )
        )


def run_test():
    print("TEST starting")
    controller.release_for_drive()
    for index in range(MOTOR_COUNT):
        controller.set_one(index, 0.12)
        for _ in range(40):
            controller.note_command()
            controller.poll()
            time.sleep_ms(20)
        controller.set_one(index, 0.0)
        for _ in range(15):
            controller.note_command()
            controller.poll()
            time.sleep_ms(20)
    controller.stop_all()
    print("TEST done")


def handle_command(line):
    parts = line.strip().split()
    if not parts:
        return

    command = parts[0].upper()
    controller.note_command()

    try:
        if command == "HELP":
            print_help()
        elif command == "STATUS":
            print_status()
        elif command == "CAL":
            if len(parts) == 1:
                print_calibration()
            elif len(parts) == 2 and parts[1].upper() == "RESET":
                controller.reset_calibration()
                print("OK CAL RESET")
            elif len(parts) == 4 and controller.set_calibration(int(parts[1]) - 1, parts[2], float(parts[3])):
                print("OK CAL")
            else:
                print("ERR Use: CAL <1-4> GAIN|TRIM|MIN|MAX|DEADBAND|INVERT <value>")
        elif command == "STOP":
            controller.stop_all()
            print("OK STOP")
        elif command == "BRAKE" and len(parts) in (2, 3):
            motor = None
            state_index = 1
            if len(parts) == 3:
                motor = int(parts[1])
                state_index = 2
            state = parts[state_index].upper()
            if state == "ON":
                if motor is None:
                    controller.set_brake(True)
                else:
                    controller.set_motor_brake(motor - 1, True)
                print("OK BRAKE ON")
            elif state == "OFF":
                if motor is None:
                    controller.set_brake(False)
                else:
                    controller.set_motor_brake(motor - 1, False)
                print("OK BRAKE OFF")
            else:
                print("ERR Use: BRAKE [1-4] ON|OFF")
        elif command == "MOTOR" and len(parts) == 3:
            motor = int(parts[1])
            if 1 <= motor <= MOTOR_COUNT:
                controller.release_for_drive()
                controller.set_one(motor - 1, float(parts[2]))
            else:
                print("ERR Use: MOTOR <1-4> <-1.0..1.0>")
        elif command == "PWMONLY" and len(parts) == 3:
            motor = int(parts[1])
            if 1 <= motor <= MOTOR_COUNT:
                controller.release_for_drive()
                controller.set_pwm_only(motor - 1, float(parts[2]))
                print("OK PWMONLY")
            else:
                print("ERR Use: PWMONLY <1-4> <0.0..1.0>")
        elif command == "DIR" and len(parts) == 3:
            motor = int(parts[1])
            state = parts[2].upper()
            if 1 <= motor <= MOTOR_COUNT and state in ("FWD", "REV"):
                controller.set_direction_only(motor - 1, state == "REV")
                print("OK DIR")
            else:
                print("ERR Use: DIR <1-4> FWD|REV")
        elif command == "DRIVE" and len(parts) == 5:
            controller.release_for_drive()
            controller.set_drive([float(value) for value in parts[1:5]])
        elif command == "TANK" and len(parts) == 3:
            left = float(parts[1])
            right = float(parts[2])
            controller.release_for_drive()
            controller.set_drive([left, right, left, right])
        elif command == "FORWARD" and len(parts) == 2:
            controller.release_for_drive()
            controller.set_all(abs(clamp(float(parts[1]), -1.0, 1.0)))
        elif command == "REVERSE" and len(parts) == 2:
            controller.release_for_drive()
            controller.set_all(-abs(clamp(float(parts[1]), -1.0, 1.0)))
        elif command == "RESET_PULSES":
            controller.reset_pulses()
            print("OK RESET_PULSES")
        elif command == "TEST":
            run_test()
        else:
            controller.stop_all()
            print("ERR Unknown command. Motors stopped.")
    except (ValueError, IndexError):
        controller.stop_all()
        print("ERR Bad command. Motors stopped.")


poller = select.poll()
poller.register(sys.stdin, select.POLLIN)
line_buffer = ""

print("MicroPython Pico motor controller ready. Type HELP.")

while True:
    controller.poll()

    while poller.poll(0):
        char = sys.stdin.read(1)
        if char == "\r":
            continue
        if char == "\n":
            handle_command(line_buffer)
            line_buffer = ""
        else:
            line_buffer += char
            if len(line_buffer) > 127:
                line_buffer = ""
                controller.stop_all()
                print("ERR Line too long. Motors stopped.")

    time.sleep_ms(5)
