#pragma once

#include <stdint.h>

// TODO: Confirm the real ZS-X11H signal mode and voltage requirements.
// This first version assumes simple 3.3 V GPIO-compatible direction/brake/stop
// pins and duty-cycle PWM input.

static constexpr uint32_t PWM_FREQUENCY_HZ = 1000;
static constexpr uint16_t PWM_WRAP = 999;
static constexpr uint8_t MOTOR_COUNT = 4;
static constexpr uint32_t COMMAND_TIMEOUT_MS = 600;
static constexpr float DEFAULT_RAMP_PER_SECOND = 1.8f;

struct MotorPins {
    uint8_t pwm;
    uint8_t speed;
    uint8_t direction;
    uint8_t brake;
};

struct MotorCalibration {
    float gain;
    float trim;
    float min_power;
    float max_power;
    float deadband;
    bool invert_direction;
};

static constexpr MotorPins MOTOR_PINS[MOTOR_COUNT] = {
    {2, 3, 4, 5},      // Motor 1: PWM, speed, direction, brake.
    {6, 7, 8, 9},      // Motor 2: PWM, speed, direction, brake.
    {10, 11, 12, 13},  // Motor 3: PWM, speed, direction, brake.
    {18, 19, 20, 21},  // Motor 4: PWM, speed, direction, brake.
};

// TODO: Confirm active polarity for the motor controllers.
static constexpr bool DIRECTION_FORWARD_LEVEL = false;
static constexpr bool BRAKE_ACTIVE_LEVEL = true;

static constexpr MotorCalibration DEFAULT_MOTOR_CALIBRATION[MOTOR_COUNT] = {
    // gain, trim, min_power, max_power, deadband, invert_direction
    {1.00f, 0.00f, 0.00f, 0.80f, 0.03f, false}, // Motor 1: right rear
    {1.00f, 0.00f, 0.00f, 0.80f, 0.03f, true},  // Motor 2: left rear
    {1.00f, 0.00f, 0.00f, 0.80f, 0.03f, true},  // Motor 3: left front
    {1.00f, 0.00f, 0.00f, 0.80f, 0.03f, false}, // Motor 4: right front
};
