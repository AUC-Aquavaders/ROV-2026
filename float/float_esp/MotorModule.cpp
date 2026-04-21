#include "MotorModule.h"

MotorModule::MotorModule() : _currentSteps(0), _targetSteps(0) {}

void MotorModule::init() {
  pinMode(MOTOR_STEP_PIN, OUTPUT);
  pinMode(MOTOR_DIR_PIN,  OUTPUT);

  Serial2.begin(MOTOR_BAUD_RATE);
  _driver.setup(Serial2, MOTOR_BAUD_RATE,
                TMC2209::SERIAL_ADDRESS_0,
                MOTOR_RX_PIN, MOTOR_TX_PIN);

  _driver.setRunCurrent(MOTOR_RUN_CURRENT);
  _driver.setHoldCurrent(MOTOR_HOLD_CURRENT);
  _driver.enableCoolStep();
  _driver.enableAutomaticCurrentScaling();
  _driver.enable();
}

void MotorModule::home() {
  _driver.setStallGuardThreshold(STALL_SENSITIVITY);
  digitalWrite(MOTOR_DIR_PIN, LOW); // direction: empty syringe

  while (true) {
    digitalWrite(MOTOR_STEP_PIN, HIGH); delayMicroseconds(1000);
    digitalWrite(MOTOR_STEP_PIN, LOW);  delayMicroseconds(1000);
    if (_driver.getStallGuardResult() < STALL_SENSITIVITY) break;
  }

  _currentSteps = 0;
  _targetSteps  = 0;
}

void MotorModule::setTargetVolume(double mL) {
  _targetSteps = volumeToSteps(mL);
  clampTarget();

  if (_targetSteps > _currentSteps)      digitalWrite(MOTOR_DIR_PIN, HIGH);
  else if (_targetSteps < _currentSteps) digitalWrite(MOTOR_DIR_PIN, LOW);
}

void MotorModule::run() {
  if (_currentSteps == _targetSteps) return;

  digitalWrite(MOTOR_STEP_PIN, HIGH); delayMicroseconds(500);
  digitalWrite(MOTOR_STEP_PIN, LOW);  delayMicroseconds(500);

  _currentSteps += (_targetSteps > _currentSteps) ? 1 : -1;
}

void MotorModule::hold(bool enable) {
  _driver.setStandstillMode(enable ? TMC2209::STRONG_BRAKING : TMC2209::NORMAL);
}

void MotorModule::sleep() {
  _driver.disable();
}

bool   MotorModule::isAtTarget()      const { return _currentSteps == _targetSteps; }
long   MotorModule::getCurrentSteps() const { return _currentSteps; }
double MotorModule::getCurrentVolume()const { return (double)_currentSteps / STEPS_PER_ML; }

long MotorModule::volumeToSteps(double mL) const {
  return (long)(mL * STEPS_PER_ML);
}

void MotorModule::clampTarget() {
  long maxSteps = volumeToSteps(SYRINGE_MAX_ML);
  if (_targetSteps > maxSteps) _targetSteps = maxSteps;
  if (_targetSteps < 0)        _targetSteps = 0;
}
