#pragma once

#include <stdint.h>

// TODO: Confirm the real ZS-X11H signal mode and voltage requirements.
// This first version assumes simple 3.3 V GPIO-compatible direction/brake/stop
// pins and duty-cycle PWM input.

static constexpr uint32_t PWM_FREQUENCY_HZ = 1000;
static constexpr uint16_t PWM_WRAP = 999;
static constexpr uint8_t MOTOR_COUNT = 4;

struct MotorPins {
    uint8_t pwm;
    uint8_t speed;
    uint8_t direction;
};

static constexpr MotorPins MOTOR_PINS[MOTOR_COUNT] = {
    {2, 3, 10},   // Motor 1: front left. TODO: Confirm physical position.
    {4, 5, 11},   // Motor 2: front right. TODO: Confirm physical position.
    {6, 7, 12},   // Motor 3: rear left. TODO: Confirm physical position.
    {18, 19, 13}, // Motor 4: rear right. Starts around GP18 for board layout.
};

static constexpr uint8_t BRAKE_PIN = 14;
static constexpr uint8_t STOP_PIN = 15;

// TODO: Confirm active polarity for the motor controllers.
static constexpr bool DIRECTION_FORWARD_LEVEL = true;
static constexpr bool BRAKE_ACTIVE_LEVEL = true;
static constexpr bool STOP_ACTIVE_LEVEL = true;
