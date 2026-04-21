#include "PIDController.h"

PIDController::PIDController(double p, double i, double d, double outMin, double outMax) {
    Kp = p;
    Ki = i;
    Kd = d;
    previousError = 0;
    integral = 0;
    outputMin = outMin;
    outputMax = outMax;
}

double PIDController::calculateControlSignal(double setpoint, double measuredValue, double dt) {
    if (dt <= 0.0) {
        // avoid divide-by-zero
        dt = 1e-6;
    }

    double error = setpoint - measuredValue;
    // integral with time scaling
    integral += error * dt;

    // derivative term 
    double derivative = (error - previousError) / dt;

    // PID output before saturation
    double output = (Kp * error) + (Ki * integral) + (Kd * derivative); // P + I + D

    // apply output limits
    double clamped = std::clamp(output, outputMin, outputMax);

    // anti-windup: if we saturated, roll back integral addition
    if (output != clamped) {
        // remove last integral contribution to prevent windup
        integral -= error * dt;
    }

    previousError = error;
    return clamped;
}

void PIDController::reset() {
    previousError = 0;
    integral = 0;
}

void PIDController::setTunings(double p, double i, double d) {
    Kp = p;
    Ki = i;
    Kd = d;
}

void PIDController::setOutputLimits(double minVal, double maxVal) {
    if (minVal > maxVal) return; // invalid
    outputMin = minVal;
    outputMax = maxVal;
}
