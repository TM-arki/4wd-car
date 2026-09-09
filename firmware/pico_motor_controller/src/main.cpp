#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "motor_config.h"
#include "pico/stdlib.h"

static constexpr char FIRMWARE_VERSION[] = "2026.09-reliability";
static constexpr uint32_t COMMAND_WATCHDOG_MS = 400;

static float motor_power[MOTOR_COUNT] = {0.0f, 0.0f, 0.0f, 0.0f};
static volatile uint32_t speed_pulses[MOTOR_COUNT] = {0, 0, 0, 0};
static bool motion_command_active = false;
static uint32_t last_motion_command_ms = 0;

static float clamp_power(float value) {
    if (value > 1.0f) {
        return 1.0f;
    }
    if (value < -1.0f) {
        return -1.0f;
    }
    return value;
}

static bool has_motion(float value) {
    return fabsf(value) > 0.0005f;
}

static void speed_input_callback(uint gpio, uint32_t events) {
    (void)events;
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        if (gpio == MOTOR_PINS[i].speed) {
            speed_pulses[i]++;
            return;
        }
    }
}

static void set_brake(bool enabled) {
    gpio_put(BRAKE_PIN, enabled ? BRAKE_ACTIVE_LEVEL : !BRAKE_ACTIVE_LEVEL);
}

static void set_controller_stop(bool enabled) {
    gpio_put(STOP_PIN, enabled ? STOP_ACTIVE_LEVEL : !STOP_ACTIVE_LEVEL);
}

static void set_motor(uint8_t index, float power) {
    if (index >= MOTOR_COUNT) {
        return;
    }

    power = clamp_power(power);
    motor_power[index] = power;

    const MotorPins pins = MOTOR_PINS[index];
    const bool forward = power >= 0.0f;
    const float magnitude = fabsf(power);
    const uint16_t level = static_cast<uint16_t>(magnitude * PWM_WRAP);

    gpio_put(pins.direction, forward ? DIRECTION_FORWARD_LEVEL : !DIRECTION_FORWARD_LEVEL);
    pwm_set_gpio_level(pins.pwm, level);
}

static void disarm_motion_watchdog(void) {
    motion_command_active = false;
    last_motion_command_ms = 0;
}

static void arm_motion_watchdog(void) {
    motion_command_active = true;
    last_motion_command_ms = to_ms_since_boot(get_absolute_time());
}

static void stop_all_motors(void) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        set_motor(i, 0.0f);
    }
    set_brake(true);
    set_controller_stop(true);
    disarm_motion_watchdog();
}

static void release_for_drive(void) {
    set_controller_stop(false);
    set_brake(false);
}

static void enforce_motion_watchdog(void) {
    if (!motion_command_active) {
        return;
    }

    const uint32_t now_ms = to_ms_since_boot(get_absolute_time());
    if (static_cast<uint32_t>(now_ms - last_motion_command_ms) > COMMAND_WATCHDOG_MS) {
        stop_all_motors();
        puts("WATCHDOG STOP");
    }
}

static void init_pwm_pin(uint8_t gpio) {
    gpio_set_function(gpio, GPIO_FUNC_PWM);
    const uint slice_num = pwm_gpio_to_slice_num(gpio);
    const float divider = static_cast<float>(clock_get_hz(clk_sys)) /
                          (static_cast<float>(PWM_FREQUENCY_HZ) * (PWM_WRAP + 1));

    pwm_config config = pwm_get_default_config();
    pwm_config_set_wrap(&config, PWM_WRAP);
    pwm_config_set_clkdiv(&config, divider);
    pwm_init(slice_num, &config, true);
    pwm_set_gpio_level(gpio, 0);
}

static void init_hardware(void) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        init_pwm_pin(MOTOR_PINS[i].pwm);

        gpio_init(MOTOR_PINS[i].direction);
        gpio_set_dir(MOTOR_PINS[i].direction, GPIO_OUT);
        gpio_put(MOTOR_PINS[i].direction, DIRECTION_FORWARD_LEVEL);

        gpio_init(MOTOR_PINS[i].speed);
        gpio_set_dir(MOTOR_PINS[i].speed, GPIO_IN);
        gpio_pull_down(MOTOR_PINS[i].speed);
    }

    gpio_init(BRAKE_PIN);
    gpio_set_dir(BRAKE_PIN, GPIO_OUT);

    gpio_init(STOP_PIN);
    gpio_set_dir(STOP_PIN, GPIO_OUT);

    stop_all_motors();

    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        gpio_set_irq_enabled_with_callback(
            MOTOR_PINS[i].speed,
            GPIO_IRQ_EDGE_RISE,
            true,
            &speed_input_callback);
    }
}

static void print_help(void) {
    puts("Commands:");
    puts("  HELP");
    puts("  STATUS");
    puts("  STOP");
    puts("  BRAKE ON|OFF");
    puts("  MOTOR <1-4> <-1.0..1.0>");
    puts("  DRIVE <m1> <m2> <m3> <m4>");
    puts("  FORWARD <0.0..1.0>");
    puts("  REVERSE <0.0..1.0>");
    puts("  TEST");
    printf("Motion commands must be renewed within %lu ms.\n",
           static_cast<unsigned long>(COMMAND_WATCHDOG_MS));
}

static void print_status(void) {
    printf("APPLIED %.3f %.3f %.3f %.3f\n",
           motor_power[0], motor_power[1], motor_power[2], motor_power[3]);
    printf("SPEED_PULSES %lu %lu %lu %lu\n",
           static_cast<unsigned long>(speed_pulses[0]),
           static_cast<unsigned long>(speed_pulses[1]),
           static_cast<unsigned long>(speed_pulses[2]),
           static_cast<unsigned long>(speed_pulses[3]));
    printf("FW %s\n", FIRMWARE_VERSION);
    printf("WATCHDOG %s %lu\n",
           motion_command_active ? "ACTIVE" : "IDLE",
           static_cast<unsigned long>(COMMAND_WATCHDOG_MS));
}

static void run_test_sequence(void) {
    puts("TEST starting");
    disarm_motion_watchdog();
    release_for_drive();

    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        set_motor(i, 0.12f);
        sleep_ms(800);
        set_motor(i, 0.0f);
        sleep_ms(300);
    }

    stop_all_motors();
    puts("TEST done");
}

static void uppercase(char *text) {
    while (*text != '\0') {
        *text = static_cast<char>(toupper(static_cast<unsigned char>(*text)));
        text++;
    }
}

static void zero_other_motors(uint8_t selected_index) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        if (i != selected_index) {
            set_motor(i, 0.0f);
        }
    }
}

static void handle_command(char *line) {
    char original[128];
    strncpy(original, line, sizeof(original));
    original[sizeof(original) - 1] = '\0';

    char command[16] = {0};
    if (sscanf(line, "%15s", command) != 1) {
        return;
    }
    uppercase(command);

    if (strcmp(command, "HELP") == 0) {
        print_help();
        return;
    }

    if (strcmp(command, "STATUS") == 0) {
        print_status();
        return;
    }

    if (strcmp(command, "STOP") == 0) {
        stop_all_motors();
        puts("OK STOP");
        return;
    }

    if (strcmp(command, "BRAKE") == 0) {
        char state[8] = {0};
        if (sscanf(original, "%*s %7s", state) == 1) {
            uppercase(state);
            if (strcmp(state, "ON") == 0) {
                stop_all_motors();
                puts("OK BRAKE ON");
                return;
            }
            if (strcmp(state, "OFF") == 0) {
                set_brake(false);
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
            power = clamp_power(power);
            if (!has_motion(power)) {
                stop_all_motors();
                puts("OK MOTOR STOP");
                return;
            }

            const uint8_t selected = static_cast<uint8_t>(motor_number - 1);
            zero_other_motors(selected);
            release_for_drive();
            set_motor(selected, power);
            arm_motion_watchdog();
            puts("OK MOTOR");
            return;
        }
        stop_all_motors();
        puts("ERR Use: MOTOR <1-4> <-1.0..1.0>");
        return;
    }

    if (strcmp(command, "DRIVE") == 0) {
        float p[MOTOR_COUNT] = {0.0f, 0.0f, 0.0f, 0.0f};
        if (sscanf(original, "%*s %f %f %f %f", &p[0], &p[1], &p[2], &p[3]) == 4) {
            bool moving = false;
            for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
                p[i] = clamp_power(p[i]);
                moving = moving || has_motion(p[i]);
            }

            if (!moving) {
                stop_all_motors();
                puts("OK DRIVE STOP");
                return;
            }

            release_for_drive();
            for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
                set_motor(i, p[i]);
            }
            arm_motion_watchdog();
            puts("OK DRIVE");
            return;
        }
        stop_all_motors();
        puts("ERR Use: DRIVE <m1> <m2> <m3> <m4>");
        return;
    }

    if (strcmp(command, "FORWARD") == 0 || strcmp(command, "REVERSE") == 0) {
        float power = 0.0f;
        if (sscanf(original, "%*s %f", &power) == 1) {
            power = fabsf(clamp_power(power));
            if (!has_motion(power)) {
                stop_all_motors();
                puts("OK DRIVE STOP");
                return;
            }
            if (strcmp(command, "REVERSE") == 0) {
                power = -power;
            }
            release_for_drive();
            for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
                set_motor(i, power);
            }
            arm_motion_watchdog();
            puts("OK DRIVE");
            return;
        }
        stop_all_motors();
        puts("ERR Use: FORWARD <0.0..1.0> or REVERSE <0.0..1.0>");
        return;
    }

    if (strcmp(command, "TEST") == 0) {
        run_test_sequence();
        return;
    }

    stop_all_motors();
    puts("ERR Unknown command. Motors stopped.");
}

int main(void) {
    stdio_init_all();
    init_hardware();

    sleep_ms(1500);
    printf("Pico motor controller %s ready. Type HELP.\n", FIRMWARE_VERSION);

    char line[128];
    size_t length = 0;

    while (true) {
        enforce_motion_watchdog();

        int ch = getchar_timeout_us(1000);
        if (ch == PICO_ERROR_TIMEOUT) {
            continue;
        }

        if (ch == '\r') {
            continue;
        }

        if (ch == '\n') {
            line[length] = '\0';
            handle_command(line);
            length = 0;
            continue;
        }

        if (length < sizeof(line) - 1) {
            line[length++] = static_cast<char>(ch);
        } else {
            length = 0;
            stop_all_motors();
            puts("ERR Line too long. Motors stopped.");
        }
    }
}
