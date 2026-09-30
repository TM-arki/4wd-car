#include "command_processor.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "motor_controller.h"
#include "pico/stdlib.h"

static float clamp_power(float value) {
    if (value > 1.0f) {
        return 1.0f;
    }
    if (value < -1.0f) {
        return -1.0f;
    }
    return value;
}

static void uppercase(char *text) {
    while (*text != '\0') {
        *text = static_cast<char>(toupper(static_cast<unsigned char>(*text)));
        text++;
    }
}

static void print_status(void) {
    const MotorStatus *status = motor_get_status();
    printf("TARGET %.3f %.3f %.3f %.3f\n",
           status[0].target_power, status[1].target_power, status[2].target_power, status[3].target_power);
    printf("RAMPED %.3f %.3f %.3f %.3f\n",
           status[0].ramped_power, status[1].ramped_power, status[2].ramped_power, status[3].ramped_power);
    printf("APPLIED %.3f %.3f %.3f %.3f\n",
           status[0].applied_power, status[1].applied_power, status[2].applied_power, status[3].applied_power);
    printf("SPEED_PULSES %lu %lu %lu %lu\n",
           status[0].speed_pulses, status[1].speed_pulses, status[2].speed_pulses, status[3].speed_pulses);
}

static void print_calibration(void) {
    const MotorCalibration *calibration = motor_get_calibration();
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        printf("CAL %u GAIN %.3f TRIM %.3f MIN %.3f MAX %.3f DEADBAND %.3f INVERT %u\n",
               i + 1,
               calibration[i].gain,
               calibration[i].trim,
               calibration[i].min_power,
               calibration[i].max_power,
               calibration[i].deadband,
               calibration[i].invert_direction ? 1 : 0);
    }
}

static void run_test_sequence(uint32_t now_ms) {
    puts("TEST starting");
    motor_release_for_drive(now_ms);

    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        motor_set_one(i, 0.12f);
        for (uint8_t tick = 0; tick < 40; ++tick) {
            const uint32_t tick_ms = to_ms_since_boot(get_absolute_time());
            motor_note_command_received(tick_ms);
            motor_controller_poll(tick_ms);
            sleep_ms(20);
        }
        motor_set_one(i, 0.0f);
        for (uint8_t tick = 0; tick < 15; ++tick) {
            const uint32_t tick_ms = to_ms_since_boot(get_absolute_time());
            motor_note_command_received(tick_ms);
            motor_controller_poll(tick_ms);
            sleep_ms(20);
        }
    }

    motor_stop_all();
    puts("TEST done");
}

void command_print_help(void) {
    puts("Commands:");
    puts("  HELP");
    puts("  STATUS");
    puts("  CAL");
    puts("  CAL RESET");
    puts("  CAL <1-4> GAIN|TRIM|MIN|MAX|DEADBAND|INVERT <value>");
    puts("  STOP");
    puts("  BRAKE ON|OFF");
    puts("  MOTOR <1-4> <-1.0..1.0>");
    puts("  DRIVE <m1> <m2> <m3> <m4>");
    puts("  TANK <left> <right>");
    puts("  FORWARD <0.0..1.0>");
    puts("  REVERSE <0.0..1.0>");
    puts("  RESET_PULSES");
    puts("  TEST");
}

void command_handle_line(char *line, uint32_t now_ms) {
    char original[128];
    strncpy(original, line, sizeof(original));
    original[sizeof(original) - 1] = '\0';

    char command[16] = {0};
    if (sscanf(line, "%15s", command) != 1) {
        return;
    }
    uppercase(command);
    motor_note_command_received(now_ms);

    if (strcmp(command, "HELP") == 0) {
        command_print_help();
        return;
    }

    if (strcmp(command, "STATUS") == 0) {
        print_status();
        return;
    }

    if (strcmp(command, "CAL") == 0) {
        char field[16] = {0};
        if (sscanf(original, "%*s %15s", field) != 1) {
            print_calibration();
            return;
        }
        uppercase(field);
        if (strcmp(field, "RESET") == 0) {
            motor_reset_calibration();
            puts("OK CAL RESET");
            return;
        }

        int motor_number = 0;
        float value = 0.0f;
        if (sscanf(original, "%*s %d %15s %f", &motor_number, field, &value) == 3 &&
            motor_number >= 1 && motor_number <= MOTOR_COUNT) {
            uppercase(field);
            if (motor_set_calibration(static_cast<uint8_t>(motor_number - 1), field, value)) {
                puts("OK CAL");
                return;
            }
        }
        puts("ERR Use: CAL <1-4> GAIN|TRIM|MIN|MAX|DEADBAND|INVERT <value>");
        return;
    }

    if (strcmp(command, "STOP") == 0) {
        motor_stop_all();
        puts("OK STOP");
        return;
    }

    if (strcmp(command, "BRAKE") == 0) {
        char state[8] = {0};
        if (sscanf(original, "%*s %7s", state) == 1) {
            uppercase(state);
            if (strcmp(state, "ON") == 0) {
                motor_set_brake(true);
                puts("OK BRAKE ON");
                return;
            }
            if (strcmp(state, "OFF") == 0) {
                motor_set_brake(false);
                puts("OK BRAKE OFF");
                return;
            }
        }
        puts("ERR Use: BRAKE ON|OFF");
        return;
    }

    if (strcmp(command, "MOTOR") == 0) {
        int motor_number = 0;
        float power = 0.0f;
        if (sscanf(original, "%*s %d %f", &motor_number, &power) == 2 &&
            motor_number >= 1 && motor_number <= MOTOR_COUNT) {
            motor_release_for_drive(now_ms);
            motor_set_one(static_cast<uint8_t>(motor_number - 1), power);
            puts("OK MOTOR");
            return;
        }
        puts("ERR Use: MOTOR <1-4> <-1.0..1.0>");
        return;
    }

    if (strcmp(command, "DRIVE") == 0) {
        float power[MOTOR_COUNT] = {0.0f, 0.0f, 0.0f, 0.0f};
        if (sscanf(original, "%*s %f %f %f %f", &power[0], &power[1], &power[2], &power[3]) == 4) {
            motor_release_for_drive(now_ms);
            motor_set_drive(power);
            puts("OK DRIVE");
            return;
        }
        puts("ERR Use: DRIVE <m1> <m2> <m3> <m4>");
        return;
    }

    if (strcmp(command, "TANK") == 0) {
        float left = 0.0f;
        float right = 0.0f;
        if (sscanf(original, "%*s %f %f", &left, &right) == 2) {
            const float power[MOTOR_COUNT] = {left, right, left, right};
            motor_release_for_drive(now_ms);
            motor_set_drive(power);
            puts("OK TANK");
            return;
        }
        puts("ERR Use: TANK <left> <right>");
        return;
    }

    if (strcmp(command, "FORWARD") == 0 || strcmp(command, "REVERSE") == 0) {
        float power = 0.0f;
        if (sscanf(original, "%*s %f", &power) == 1) {
            power = fabsf(clamp_power(power));
            if (strcmp(command, "REVERSE") == 0) {
                power = -power;
            }
            motor_release_for_drive(now_ms);
            motor_set_all(power);
            puts("OK DRIVE");
            return;
        }
        puts("ERR Use: FORWARD <0.0..1.0> or REVERSE <0.0..1.0>");
        return;
    }

    if (strcmp(command, "RESET_PULSES") == 0) {
        motor_reset_speed_pulses();
        puts("OK RESET_PULSES");
        return;
    }

    if (strcmp(command, "TEST") == 0) {
        run_test_sequence(now_ms);
        return;
    }

    motor_stop_all();
    puts("ERR Unknown command. Motors stopped.");
}
