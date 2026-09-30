#pragma once

#include <stdint.h>

#include "motor_config.h"

struct MotorStatus {
    float target_power;
    float ramped_power;
    float applied_power;
    uint32_t speed_pulses;
};

void motor_controller_init(void);
void motor_controller_poll(uint32_t now_ms);

void motor_note_command_received(uint32_t now_ms);
void motor_release_for_drive(uint32_t now_ms);
void motor_stop_all(void);
void motor_set_brake(bool enabled);
void motor_set_controller_stop(bool enabled);

void motor_set_one(uint8_t index, float power);
void motor_set_drive(const float power[MOTOR_COUNT]);
void motor_set_all(float power);

bool motor_set_calibration(uint8_t index, const char *field, float value);
void motor_reset_calibration(void);
void motor_reset_speed_pulses(void);

const MotorStatus *motor_get_status(void);
const MotorCalibration *motor_get_calibration(void);
