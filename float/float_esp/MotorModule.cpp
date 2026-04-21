#include <Arduino.h>
#include "MotorModule.h"

void MotorModule::motorInit() {
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);

  Serial2.begin(BAUD_RATE);

  driver.setup(Serial2, BAUD_RATE, TMC2209::SERIAL_ADDRESS_0, RX_PIN, TX_PIN);

  driver.setRunCurrent(RUN_CURRENT);
  driver.setHoldCurrent(HOLD_CURRENT);

  driver.enableCoolStep();
  driver.enableAutomaticCurrentScaling();
  driver.enable();
}

void MotorModule::homeMotor() {
  driver.setStallGuardThreshold(STALL_SENSITIVITY);
  digitalWrite(DIR_PIN, LOW);

  uint32_t start = millis();  // safety timeout

  while (millis() - start < 5000) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(1000);
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(1000);

    if (driver.getStallGuardResult() < STALL_SENSITIVITY) {
      break;
    }
  }

  currentPosition = 0;
  targetPosition = 0;
}

void MotorModule::setTargetPosition(long targetSteps) {
  targetPosition = targetSteps;
  checkLimits();

  if (targetPosition > currentPosition) {
    digitalWrite(DIR_PIN, HIGH);
  } else if (targetPosition < currentPosition) {
    digitalWrite(DIR_PIN, LOW);
  }
}

void MotorModule::runMotor() {
  if (currentPosition == targetPosition) return;

  digitalWrite(STEP_PIN, HIGH);
  delayMicroseconds(500);
  digitalWrite(STEP_PIN, LOW);
  delayMicroseconds(500);

  if (targetPosition > currentPosition) {
    currentPosition++;
  } else {
    currentPosition--;
  }
}

void MotorModule::setHoldingMode(bool enable) {
  if (enable) {
    driver.setStandstillMode(TMC2209::STRONG_BRAKING);
  } else {
    driver.setStandstillMode(TMC2209::NORMAL);
  }
}

void MotorModule::sleepMotor() {
  driver.disable();
}

void MotorModule::checkLimits() { 
  //Secondary safety check (Primary in PID)
  if (targetPosition > MAX_STEPS) targetPosition = MAX_STEPS;
  if (targetPosition < 0) targetPosition = 0;
}                        

long MotorModule::volumeToSteps(double volume) {
  // Clamp to physical syringe volume range.
  if (volume < 0) volume = 0;
  double maxMl = (double)MAX_STEPS / (double)STEPS_PER_ML;
  if (volume > maxMl) volume = maxMl;
  return (long)(volume * (double)STEPS_PER_ML);
}
