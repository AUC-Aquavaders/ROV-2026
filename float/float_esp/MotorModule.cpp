#include "MotorModule.h"

// ============================================================
// construction
// ============================================================

MotorModule::MotorModule()
    : _stepper(nullptr),
      _commandedVelocity(0) {}


// ============================================================
// init
// ============================================================

bool MotorModule::motorInit()
{
  // pins
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  digitalWrite(STEP_PIN, LOW);
  digitalWrite(DIR_PIN, LOW);

  // tmc2209 over uart2
  Serial2.begin(BAUD_RATE);
  _driver.setup(Serial2, BAUD_RATE, TMC2209::SERIAL_ADDRESS_0, RX_PIN, TX_PIN);
  _driver.setRunCurrent(RUN_CURRENT);
  _driver.setHoldCurrent(HOLD_CURRENT);
  _driver.enableCoolStep();
  _driver.enableAutomaticCurrentScaling();
  _driver.enable();

  // fastaccelstepper engine
  _engine.init();
  _stepper = _engine.stepperConnectToPin(STEP_PIN);
  if (_stepper == nullptr)
    return false;

  _stepper->setDirectionPin(DIR_PIN);
  _stepper->setSpeedInHz(MAX_SPEED_HZ);
  _stepper->setAcceleration(MAX_ACCEL);
  _stepper->setCurrentPosition(0);

  return true;
}


// ============================================================
// homing
// ============================================================

bool MotorModule::homeMotor()
{
  // disable load-adaptive features so stallguard sees a clean stall
  _driver.disableCoolStep();
  _driver.disableAutomaticCurrentScaling();
  _driver.setRunCurrent(RUN_CURRENT);
  _driver.setStallGuardThreshold(STALL_SENSITIVITY);
  digitalWrite(DIR_PIN, LOW); // retract

  const uint32_t start = millis();
  bool stalled = false;

  while (millis() - start < HOMING_TIMEOUT_MS)
  {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(HOMING_STEP_US);
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(HOMING_STEP_US);

    if (_driver.getStallGuardResult() < STALL_SENSITIVITY)
    {
      stalled = true;
      break;
    }

    yield();
  }

  // restore normal operating mode
  _driver.enableCoolStep();
  _driver.enableAutomaticCurrentScaling();

  // zero the position counter regardless of outcome
  if (_stepper)
    _stepper->setCurrentPosition(0);
  _commandedVelocity = 0;

  return stalled;
}


// ============================================================
// position mode (pid uses this)
// ============================================================

bool MotorModule::setTargetPosition(long targetSteps)
{
  if (_stepper == nullptr)
    return false;

  // reject nonsense targets
  if (targetSteps < MIN_STEPS || targetSteps > MAX_STEPS)
    return false;

  // re-assert ramp params in case we were in velocity mode
  _stepper->setSpeedInHz(MAX_SPEED_HZ);
  _stepper->setAcceleration(MAX_ACCEL);
  _stepper->moveTo(targetSteps);

  _commandedVelocity = 0;
  return true;
}


// ============================================================
// velocity mode (unused by current fsm, kept for flexibility)
// ============================================================

void MotorModule::setVelocity(long stepsPerSec)
{
  if (_stepper == nullptr)
    return;

  long v = clampSpeed(stepsPerSec);

  // refuse to drive past physical stops
  if (v > 0 && atForwardLimit()) v = 0;
  if (v < 0 && atReverseLimit()) v = 0;

  // case 1: commanded stop
  if (v == 0)
  {
    if (_commandedVelocity != 0)
    {
      _stepper->stopMove();
      _commandedVelocity = 0;
    }
    return;
  }

  // case 2: already moving same direction -> just update speed
  const bool sameDirection = (v > 0 && _commandedVelocity > 0) ||
                             (v < 0 && _commandedVelocity < 0);

  _stepper->setSpeedInHz((uint32_t)labs(v));

  if (sameDirection)
  {
    _stepper->applySpeedAcceleration();
  }
  else
  {
    // direction change or start from rest
    if (v > 0) _stepper->runForward();
    else       _stepper->runBackward();
  }

  _commandedVelocity = v;
}


// ============================================================
// power / braking
// ============================================================

void MotorModule::stop()
{
  if (_stepper) _stepper->stopMove();
  _commandedVelocity = 0;
}

void MotorModule::setHoldingMode(bool enable)
{
  _driver.setStandstillMode(enable ? TMC2209::STRONG_BRAKING : TMC2209::NORMAL);
}

void MotorModule::sleepMotor()
{
  stop();
  _driver.disable();
}


// ============================================================
// status queries
// ============================================================

bool MotorModule::isAtTarget() const
{
  if (_stepper == nullptr) return true;
  return !_stepper->isRunning();
}

long MotorModule::getCurrentPosition() const
{
  if (_stepper == nullptr) return 0;
  return _stepper->getCurrentPosition();
}

bool MotorModule::isRunning() const
{
  return _stepper && _stepper->isRunning();
}


// ============================================================
// conversions
// ============================================================

long MotorModule::volumeToSteps(double volume_mL)
{
  if (volume_mL < 0)              volume_mL = 0;
  if (volume_mL > SYRINGE_MAX_ML) volume_mL = SYRINGE_MAX_ML;
  return (long)(volume_mL * (double)STEPS_PER_ML);
}


// ============================================================
// private helpers
// ============================================================

long MotorModule::clampSpeed(long stepsPerSec) const
{
  if (stepsPerSec >  (long)MAX_SPEED_HZ) return  (long)MAX_SPEED_HZ;
  if (stepsPerSec < -(long)MAX_SPEED_HZ) return -(long)MAX_SPEED_HZ;
  return stepsPerSec;
}

bool MotorModule::atForwardLimit() const
{
  return getCurrentPosition() >= MAX_STEPS;
}

bool MotorModule::atReverseLimit() const
{
  return getCurrentPosition() <= MIN_STEPS;
}
