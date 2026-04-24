#include "MockMotorModule.h"

void MockMotorModule::motorInit() {
  // Mock: do nothing
}

void MockMotorModule::homeMotor() {
  currentPosition = 0;
  targetPosition = 0;
}

void MockMotorModule::setTargetPosition(long targetSteps) {
  targetPosition = targetSteps;
  checkLimits();
}

void MockMotorModule::runMotor() {
  if (currentPosition == targetPosition) return;

  // Mock: instantly move to target for simplicity, or step by step
  if (targetPosition > currentPosition) {
    currentPosition++;
  } else {
    currentPosition--;
  }
}

void MockMotorModule::setHoldingMode(bool enable) {
  // holdingMode = enable;
  
}

void MockMotorModule::sleepMotor() {
  // Mock: do nothing
}

void MockMotorModule::checkLimits() { 
  if (targetPosition > MAX_STEPS) targetPosition = MAX_STEPS;
  if (targetPosition < 0) targetPosition = 0;
}                        

long MockMotorModule::volumeToSteps(double volume) {
  if (volume < 0) volume = 0;
  double maxMl = (double)MAX_STEPS / (double)STEPS_PER_ML;
  if (volume > maxMl) volume = maxMl;
  return (long)(volume * (double)STEPS_PER_ML);
}

bool MockMotorModule::isAtTarget() {
  return (currentPosition == targetPosition);
}

long MockMotorModule::getCurrentPosition() {
  return currentPosition;
}
