#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "motor_config.h"
#include "pico/stdlib.h"

static float motor_power[MOTOR_COUNT] = {0.0f, 0.0f, 0.0f, 0.0f};
static volatile uint32_t speed_pulses[MOTOR_COUNT] = {0, 0, 0, 0};

static float clamp_power(float value) {
    if (value > 1.0f) {
        return 1.0f;
    }
    if (value < -1.0f) {
        return -1.0f;
    }
    return value;
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

static void stop_all_motors(void) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        set_motor(i, 0.0f);
    }
    set_brake(true);
    set_controller_stop(true);
}

static void release_for_drive(void) {
    set_controller_stop(false);
    set_brake(false);
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
}

static void print_status(void) {
    printf("POWER %.3f %.3f %.3f %.3f\n",
           motor_power[0], motor_power[1], motor_power[2], motor_power[3]);
    printf("SPEED_PULSES %lu %lu %lu %lu\n",
           speed_pulses[0], speed_pulses[1], speed_pulses[2], speed_pulses[3]);
}

static void run_test_sequence(void) {
    puts("TEST starting");
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
                set_brake(true);
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
            release_for_drive();
            set_motor(static_cast<uint8_t>(motor_number - 1), power);
            puts("OK MOTOR");
            return;
        }
        puts("ERR Use: MOTOR <1-4> <-1.0..1.0>");
        return;
    }

    if (strcmp(command, "DRIVE") == 0) {
        float p[MOTOR_COUNT] = {0.0f, 0.0f, 0.0f, 0.0f};
        if (sscanf(original, "%*s %f %f %f %f", &p[0], &p[1], &p[2], &p[3]) == 4) {
            release_for_drive();
            for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
                set_motor(i, p[i]);
            }
            puts("OK DRIVE");
            return;
        }
        puts("ERR Use: DRIVE <m1> <m2> <m3> <m4>");
        return;
    }

    if (strcmp(command, "FORWARD") == 0 || strcmp(command, "REVERSE") == 0) {
        float power = 0.0f;
        if (sscanf(original, "%*s %f", &power) == 1) {
            power = fabsf(clamp_power(power));
            if (strcmp(command, "REVERSE") == 0) {
                power = -power;
            }
            release_for_drive();
            for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
                set_motor(i, power);
            }
            puts("OK DRIVE");
            return;
        }
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
    puts("Pico motor controller ready. Type HELP.");

    char line[128];
    size_t length = 0;

    while (true) {
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
