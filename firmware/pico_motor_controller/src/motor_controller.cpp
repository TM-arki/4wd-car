#include "motor_controller.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "pico/stdlib.h"

static MotorCalibration calibration[MOTOR_COUNT];
static MotorStatus status[MOTOR_COUNT];
static volatile uint32_t speed_pulses[MOTOR_COUNT] = {0, 0, 0, 0};

static uint32_t last_command_ms = 0;
static uint32_t last_poll_ms = 0;
static bool drive_released = false;

static float clamp_float(float value, float low, float high) {
    if (value < low) {
        return low;
    }
    if (value > high) {
        return high;
    }
    return value;
}

static float clamp_power(float value) {
    return clamp_float(value, -1.0f, 1.0f);
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

static float ramp_toward(float current, float target, float step) {
    if (current < target) {
        return (current + step > target) ? target : current + step;
    }
    if (current > target) {
        return (current - step < target) ? target : current - step;
    }
    return current;
}

static float apply_calibration(uint8_t index, float command) {
    const MotorCalibration *cal = &calibration[index];
    float magnitude = fabsf(command);
    if (magnitude < cal->deadband) {
        return 0.0f;
    }

    magnitude = (magnitude * cal->gain) + cal->trim;
    magnitude = clamp_float(magnitude, 0.0f, cal->max_power);
    if (magnitude > 0.0f && magnitude < cal->min_power) {
        magnitude = cal->min_power;
    }

    float signed_output = (command < 0.0f) ? -magnitude : magnitude;
    if (cal->invert_direction) {
        signed_output = -signed_output;
    }
    return clamp_power(signed_output);
}

static void write_motor_output(uint8_t index, float calibrated_power) {
    const MotorPins pins = MOTOR_PINS[index];
    const bool forward = calibrated_power >= 0.0f;
    const float magnitude = fabsf(calibrated_power);
    const uint16_t level = static_cast<uint16_t>(magnitude * PWM_WRAP);

    gpio_put(pins.direction, forward ? DIRECTION_FORWARD_LEVEL : !DIRECTION_FORWARD_LEVEL);
    pwm_set_gpio_level(pins.pwm, level);
    status[index].applied_power = calibrated_power;
}

void motor_controller_init(void) {
    memcpy(calibration, DEFAULT_MOTOR_CALIBRATION, sizeof(calibration));
    memset(status, 0, sizeof(status));

    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        init_pwm_pin(MOTOR_PINS[i].pwm);

        gpio_init(MOTOR_PINS[i].direction);
        gpio_set_dir(MOTOR_PINS[i].direction, GPIO_OUT);
        gpio_put(MOTOR_PINS[i].direction, DIRECTION_FORWARD_LEVEL);

        gpio_init(MOTOR_PINS[i].speed);
        gpio_set_dir(MOTOR_PINS[i].speed, GPIO_IN);
        gpio_pull_down(MOTOR_PINS[i].speed);

        gpio_init(MOTOR_PINS[i].brake);
        gpio_set_dir(MOTOR_PINS[i].brake, GPIO_OUT);
    }

    motor_stop_all();

    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        gpio_set_irq_enabled_with_callback(
            MOTOR_PINS[i].speed,
            GPIO_IRQ_EDGE_RISE,
            true,
            &speed_input_callback);
    }

    last_command_ms = to_ms_since_boot(get_absolute_time());
    last_poll_ms = last_command_ms;
}

void motor_controller_poll(uint32_t now_ms) {
    if (drive_released && (now_ms - last_command_ms > COMMAND_TIMEOUT_MS)) {
        motor_stop_all();
        puts("WARN command timeout; motors stopped");
    }

    const uint32_t elapsed_ms = now_ms - last_poll_ms;
    last_poll_ms = now_ms;

    const float ramp_step = DEFAULT_RAMP_PER_SECOND * (static_cast<float>(elapsed_ms) / 1000.0f);
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        status[i].ramped_power = ramp_toward(status[i].ramped_power, status[i].target_power, ramp_step);
        status[i].speed_pulses = speed_pulses[i];
        write_motor_output(i, apply_calibration(i, status[i].ramped_power));
    }
}

void motor_note_command_received(uint32_t now_ms) {
    last_command_ms = now_ms;
}

void motor_release_for_drive(uint32_t now_ms) {
    motor_note_command_received(now_ms);
    motor_set_controller_stop(false);
    motor_set_brake(false);
    drive_released = true;
}

void motor_stop_all(void) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        status[i].target_power = 0.0f;
        status[i].ramped_power = 0.0f;
        write_motor_output(i, 0.0f);
    }
    motor_set_brake(true);
    motor_set_controller_stop(true);
    drive_released = false;
}

void motor_set_brake(bool enabled) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        gpio_put(MOTOR_PINS[i].brake, enabled ? BRAKE_ACTIVE_LEVEL : !BRAKE_ACTIVE_LEVEL);
    }
}

void motor_set_controller_stop(bool enabled) {
    (void)enabled;
}

void motor_set_one(uint8_t index, float power) {
    if (index >= MOTOR_COUNT) {
        return;
    }
    status[index].target_power = clamp_power(power);
}

void motor_set_drive(const float power[MOTOR_COUNT]) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        motor_set_one(i, power[i]);
    }
}

void motor_set_all(float power) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        motor_set_one(i, power);
    }
}

bool motor_set_calibration(uint8_t index, const char *field, float value) {
    if (index >= MOTOR_COUNT || field == nullptr) {
        return false;
    }

    MotorCalibration *cal = &calibration[index];
    if (strcmp(field, "GAIN") == 0) {
        cal->gain = clamp_float(value, 0.0f, 2.0f);
        return true;
    }
    if (strcmp(field, "TRIM") == 0) {
        cal->trim = clamp_float(value, -0.25f, 0.25f);
        return true;
    }
    if (strcmp(field, "MIN") == 0) {
        cal->min_power = clamp_float(value, 0.0f, 0.50f);
        return true;
    }
    if (strcmp(field, "MAX") == 0) {
        cal->max_power = clamp_float(value, 0.05f, 1.0f);
        return true;
    }
    if (strcmp(field, "DEADBAND") == 0) {
        cal->deadband = clamp_float(value, 0.0f, 0.25f);
        return true;
    }
    if (strcmp(field, "INVERT") == 0) {
        cal->invert_direction = value >= 0.5f;
        return true;
    }

    return false;
}

void motor_reset_calibration(void) {
    memcpy(calibration, DEFAULT_MOTOR_CALIBRATION, sizeof(calibration));
}

void motor_reset_speed_pulses(void) {
    for (uint8_t i = 0; i < MOTOR_COUNT; ++i) {
        speed_pulses[i] = 0;
        status[i].speed_pulses = 0;
    }
}

const MotorStatus *motor_get_status(void) {
    return status;
}

const MotorCalibration *motor_get_calibration(void) {
    return calibration;
}
