// MotorModule.h
// Non-blocking stepper control for the float's buoyancy engine.
// Uses FastAccelStepper for step generation (hardware-timer based on ESP32)
// and TMC2209 over UART for current/stall configuration.

// API supports both:
//   - Position mode: setTargetPosition(steps)  — used by RECOVER / homing checks
//   - Velocity mode: setVelocity(stepsPerSec)  — used by the PID control loop

// Sign convention for velocity:
//   +velocity = pull water IN  = syringe fills  = float sinks
//   -velocity = push water OUT = syringe empties = float rises

#pragma once

#include <Arduino.h>
#include <TMC2209.h>
#include <FastAccelStepper.h>

// ---- Pin assignments ----
// TODO: confirm against final wiring before pool test
#define STEP_PIN 25
#define DIR_PIN 26
#define RX_PIN 16 
#define TX_PIN 17 

// Microstep pins: NOT USED when TMC2209 microstepping is configured via UART.
// Left defined for wiring reference only.
#define MS1_PIN 32
#define MS2_PIN 33

// ---- Driver config ---- (Stall Sensitivity should be tested
#define BAUD_RATE 115200
#define RUN_CURRENT 80
#define HOLD_CURRENT 40
#define STALL_SENSITIVITY 5 

// ---- Mechanical config ----
// STEPS_PER_ML: microsteps required to displace 1 mL of syringe volume.
// Value depends on microstepping setting (TMC2209 default: 8x) and leadscrew pitch.
// TODO: verify empirically on bench (mark syringe, count steps per mL)
#define STEPS_PER_ML 200
#define SYRINGE_MAX_ML 50
#define MAX_STEPS (STEPS_PER_ML * SYRINGE_MAX_ML) // 10,000 steps full stroke
#define MIN_STEPS 0

// ---- Motion config ----
// MAX_SPEED_HZ: cap on step rate (steps/sec). PID velocity commands are clamped to this.
// At 8000 Hz we can traverse full 10,000-step stroke in ~1.25s — plenty fast for buoyancy control.
#define MAX_SPEED_HZ 8000
// MAX_ACCEL: smoothness ramp (steps/sec^2). High accel = snappy response; low = gentle.
#define MAX_ACCEL 20000

// ---- Homing config ----
// Homing steps at ~400-500 steps/sec (limited by HOMING_STEP_US + UART read time).
// At that rate, traversing the full 10,000-step stroke takes ~20-25 seconds.
// 30 s timeout guarantees we reach the end stop from any starting position.
#define HOMING_TIMEOUT_MS 30000
#define HOMING_STEP_US 1000 // half-period between pulses during homing

class MotorModule
{
public:
  MotorModule();

  // ---- Lifecycle ----
  // Initialize pins, UART, FastAccelStepper engine, and TMC2209 driver.
  // Call once from setup(). Returns true on success.
  bool motorInit();

  // Retract syringe to physical zero using StallGuard.
  // BLOCKING but watchdog-safe (calls yield() each iteration).
  // Resets position counters to 0 on success.
  // Returns true if stall detected, false on timeout.
  bool homeMotor();

  // ---- Command interface ----

  // Position mode: command motor to drive to absolute step position.
  // Rejects out-of-range targets (returns false, makes no change).
  // Uses FastAccelStepper's ramp generator (respects MAX_SPEED_HZ, MAX_ACCEL).
  bool setTargetPosition(long targetSteps);

  // Velocity mode: command continuous motion at given signed step rate.
  //   +steps/sec = fill syringe (sink)
  //   -steps/sec = empty syringe (rise)
  //    0         = stop
  // Auto-clamps to 0 when position is at/past the limit in the commanded direction.
  // Magnitude is clamped to MAX_SPEED_HZ.
  void setVelocity(long stepsPerSec);

  // Decelerate gracefully and stop. Safe to call anytime.
  void stop();

  // ---- Power / hold ----
  // Enable/disable strong electrical braking when motor is idle.
  void setHoldingMode(bool enable);

  // Disable driver output entirely (save battery at surface).
  void sleepMotor();

  // ---- Status ----
  bool isAtTarget() const;
  long getCurrentPosition() const;
  bool isRunning() const;

  // ---- Utility ----
  static long volumeToSteps(double volume_mL);

private:
  // Hardware
  TMC2209 _driver;
  FastAccelStepperEngine _engine;
  FastAccelStepper *_stepper;

  // Velocity-mode bookkeeping:
  // FastAccelStepper's runForward/runBackward is continuous; we track the
  // currently-commanded signed velocity so setVelocity() can detect sign flips
  // and re-issue runForward/runBackward only when direction actually changes.
  long _commandedVelocity;

  // Helpers
  long clampSpeed(long stepsPerSec) const;
  bool atForwardLimit() const; // at or past MAX_STEPS
  bool atReverseLimit() const; // at or past MIN_STEPS (0)
};
