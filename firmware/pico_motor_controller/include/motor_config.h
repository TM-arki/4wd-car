#pragma once

#include <stdint.h>

// TODO: Confirm the real ZS-X11H signal mode and voltage requirements.
// The confirmed wiring uses 3.3 V GPIO-compatible direction and individual
// brake pins with duty-cycle PWM input. There is no shared STOP GPIO.

static constexpr uint32_t PWM_FREQUENCY_HZ = 1000;
static constexpr uint16_t PWM_WRAP = 999;
static constexpr uint8_t MOTOR_COUNT = 4;

struct MotorPins {
    uint8_t pwm;
    uint8_t speed;
    uint8_t direction;
    uint8_t brake;
    bool invert_direction;
};

static constexpr MotorPins MOTOR_PINS[MOTOR_COUNT] = {
    {2, 3, 4, 5, false},       // Motor 1: right rear.
    {6, 7, 8, 9, true},        // Motor 2: left rear.
    {10, 11, 12, 13, true},    // Motor 3: left front.
    {18, 19, 20, 21, false},   // Motor 4: right front; PIO PWM avoids GP2 conflict.
};

static constexpr uint8_t PIO_PWM_MOTOR_INDEX = 3;

// TODO: Confirm active polarity for the motor controllers.
static constexpr bool DIRECTION_FORWARD_LEVEL = false;
static constexpr bool BRAKE_ACTIVE_LEVEL = true;
