// float_esp.ino
// mate rov 2026 pioneer class — autonomous vertical profiling float.
//
// mission sequence:
//   pre_comm -> descending -> holding(deep)    -> ascending -> holding(shallow)
//            -> descending -> holding(deep)    -> ascending -> holding(shallow)
//            -> surfacing  -> recovered        -> transmit  -> done
//
// depth reference:
//   sensor is at the bottom of the float. mate measures deep hold to the
//   bottom of the float (= sensor) and shallow hold to the top of the float
//   (= sensor - FLOAT_LENGTH_M). shallow_depth accounts for this offset.
//
// safe failure modes:
//   - motorInit() fails at boot: trapPermanent(), loop() never runs.
//   - homeMotor() fails at pre_comm: stay in pre_comm, next ack retries.
//   - any motion-state watchdog expires: route to surfacing (empty syringe).
//   - ascending sensor depth above BREACH_GUARD_M: override pid, fill syringe.

#include "PIDController.h"
#include "MotorModule.h"
#include "SensorModule.h"
#include "DataLogger.h"
#include "ESPnow_Sender.h"
#include "packet.h"
#include <math.h>

// ============================================================
// mission parameters
// ============================================================

#define FLOAT_LENGTH_M 0.50f                   // top-to-bottom float length
#define DEEP_DEPTH 2.5f                        // sensor target for deep hold
#define SHALLOW_DEPTH (0.40f + FLOAT_LENGTH_M) // sensor target = top-at-0.40m
#define DEPTH_MARGIN 0.33f                     // ± band per mate rubric
#define TARGET_HOLD_MS 30000UL                 // 30 s hold per mate rubric

// surface-detection trigger (surfacing -> recovered)
#define SURFACE_DEPTH_M 0.15f
#define SURFACE_STABLE_MS 3000UL

// anti-breach floor for ascending: if sensor gets shallower than this,
// override pid and fill syringe. sensor at 0.57m = top of float at 0.07m,
// matching the upper edge of the rubric's shallow band.
#define BREACH_GUARD_M 0.57f

// per-state abort watchdogs; motion states route to surfacing on expiry.
#define PRECOMM_WARN_MS 300000UL // 5 min: warn but keep beaconing
#define DESCEND_TIMEOUT_MS 90000UL
#define ASCEND_TIMEOUT_MS 90000UL
#define HOLD_TIMEOUT_MS 60000UL // tight to protect 15-min demo budget
#define SURFACE_TIMEOUT_MS 60000UL

// boot-time motor init retry
#define INIT_RETRY_MS 500UL
#define INIT_RETRY_BUDGET_MS 5000UL

// on-deck calibration sanity check
#define ONDECK_DEPTH_THRESHOLD_M 0.05f

// control loop
#define LOOP_MS 100
#define MAX_DT_S 0.5f

// sensor sanity bounds
#define MIN_VALID_DEPTH_M (-0.5f)
#define MAX_VALID_DEPTH_M 5.0f

// ============================================================
// pid config
// ============================================================

// output: absolute syringe volume (mL), clamped to [0, SYRINGE_MAX_ML].
// shared gains for both directions; split later via runPID's Direction arg.
// TODO: tune during pool testing
#define PID_KP_SHARED 8.0
#define PID_KI_SHARED 0.3
#define PID_KD_SHARED 0.8

// SYRINGE_MAX_ML comes from MotorModule.h (single source of truth)

PIDController pid(PID_KP_SHARED, PID_KI_SHARED, PID_KD_SHARED, 0.0, SYRINGE_MAX_ML);
MotorModule motor;
SensorModule sensor;
DataLogger logger;
ESPNowSender sender;

// ============================================================
// fsm
// ============================================================

enum State : uint8_t
{
  PRE_COMM = 0,
  DESCENDING = 1,
  ASCENDING = 2,
  HOLDING = 3,
  SURFACING = 4,
  RECOVERED = 5,
  TRANSMIT = 6,
  DONE = 7
};

// task index: 0=deep1, 1=shallow1, 2=deep2, 3=shallow2, 4=profiles complete
uint8_t nextTask = 0;
State currentState = PRE_COMM;
State prevState = PRE_COMM;

enum Direction : uint8_t
{
  DIR_DOWN = 0,
  DIR_UP = 1
};

// ============================================================
// runtime state
// ============================================================

// sensor readings
float currentDepth = 0.0f;
float currentPressure = 0.0f;
float lastValidDepth = 0.0f;

// timers
uint32_t stateEnteredMs = 0;
uint32_t holdCounter = 0;
uint32_t lastHoldUpdateMs = 0;
uint32_t surfaceStableMs = 0;
uint32_t lastSurfaceUpdate = 0;

uint32_t lastLoopMs = 0;
uint32_t lastLogMs = 0;
uint32_t lastBeaconMs = 0;
uint32_t lastTxMs = 0;
bool precommWarned = false;

uint16_t txIndex = 0;
uint16_t nextSequence = 1;

// true only after a successful home
bool homingOk = false;

// ============================================================
// forward decls
// ============================================================

void enterState(State s, uint32_t now);
void fillPacketHeader(DataPacket &pkt);
float targetDepth();
bool atDepth(float target);
State nextLegState();
bool holdComplete(uint32_t now);
void runPID(float target, float dt, Direction dir);
void logIfDue(uint32_t now);
bool surfacedAndStable(uint32_t now);
bool depthIsSane(float d);
void abortToSurfacing(uint32_t now);
void trapPermanent(const __FlashStringHelper *reason);

// ============================================================
// helpers
// ============================================================

// centralized state transition; resets per-state counters in one place
void enterState(State s, uint32_t now)
{
  prevState = currentState;
  currentState = s;
  stateEnteredMs = now;

  switch (s)
  {
  case HOLDING:
    holdCounter = 0;
    lastHoldUpdateMs = now;
    // TODO (pool): if drift observed during deep hold, uncomment:
    // motor.setHoldingMode(true);
    break;
  case SURFACING:
    motor.setTargetPosition(0); // empty syringe = max buoyancy
    surfaceStableMs = 0;
    lastSurfaceUpdate = now;
    // motor.setHoldingMode(false);
    break;
  case TRANSMIT:
    txIndex = 0;
    lastTxMs = 0;
    break;
  case PRE_COMM:
    precommWarned = false;
    break;
  default:
    break;
  }
}

// fills common fields on any outgoing packet
void fillPacketHeader(DataPacket &pkt)
{
  strncpy(pkt.companyID, COMPANY_ID, sizeof(pkt.companyID) - 1);
  pkt.companyID[sizeof(pkt.companyID) - 1] = '\0';
  pkt.state = (uint8_t)currentState;
  pkt.profileNum = (nextTask >= 2) ? 2 : 1;
  pkt.homingOk = homingOk; // requires field in packet.h
}

float targetDepth()
{
  if (nextTask == 0 || nextTask == 2)
    return DEEP_DEPTH;
  if (nextTask == 1 || nextTask == 3)
    return SHALLOW_DEPTH;
  return NAN;
}

bool atDepth(float target)
{
  return fabsf(currentDepth - target) <= DEPTH_MARGIN;
}

State nextLegState()
{
  if (nextTask == 0 || nextTask == 2)
    return DESCENDING;
  return ASCENDING;
}

// resets on drift-out per mate rubric; returns true when 30 s in-band
bool holdComplete(uint32_t now)
{
  float target = targetDepth();
  uint32_t dt = now - lastHoldUpdateMs;
  lastHoldUpdateMs = now;

  if (!atDepth(target))
  {
    holdCounter = 0;
    return false;
  }
  holdCounter += dt;
  return holdCounter >= TARGET_HOLD_MS;
}

// pid -> volume_mL -> steps -> setTargetPosition (non-blocking)
// dir arg is plumbing for future gain-splitting; unused today
void runPID(float target, float dt, Direction /*dir*/)
{
  double volume_mL = pid.calculateControlSignal(target, currentDepth, dt);
  long targetSteps = motor.volumeToSteps(volume_mL);
  motor.setTargetPosition(targetSteps);
}

void logIfDue(uint32_t now)
{
  if (now - lastLogMs < 1000)
    return;
  lastLogMs = now;

  DataPacket pkt = {};
  fillPacketHeader(pkt);
  pkt.timestamp_s = now / 1000;
  pkt.pressure_kPa = currentPressure;
  pkt.depth_m = currentDepth;
  logger.log(pkt);
}

// true when motor at zero AND depth stable near surface for 3s
bool surfacedAndStable(uint32_t now)
{
  uint32_t dt = now - lastSurfaceUpdate;
  lastSurfaceUpdate = now;

  if (currentDepth > SURFACE_DEPTH_M)
  {
    surfaceStableMs = 0;
    return false;
  }
  surfaceStableMs += dt;
  return (surfaceStableMs >= SURFACE_STABLE_MS) && motor.isAtTarget();
}

bool depthIsSane(float d)
{
  return !isnan(d) && d >= MIN_VALID_DEPTH_M && d <= MAX_VALID_DEPTH_M;
}

// safe failure path: empty syringe and try to surface
void abortToSurfacing(uint32_t now)
{
  Serial.print(F("[ABORT] state="));
  Serial.print((int)currentState);
  Serial.print(F(" t="));
  Serial.println(now);
  pid.reset();
  enterState(SURFACING, now);
}

// permanent trap: used when boot-time init fails. loop() never runs.
void trapPermanent(const __FlashStringHelper *reason)
{
  while (true)
  {
    Serial.print(F("[FATAL] "));
    Serial.println(reason);
    delay(1000);
    yield();
  }
}

// ============================================================
// setup
// ============================================================

void setup()
{
  Serial.begin(115200);
  delay(100);

  sensor.init();
  sender.init();

  // motor init retry loop; trap if permanently broken
  uint32_t initStart = millis();
  bool motorReady = false;
  while (millis() - initStart < INIT_RETRY_BUDGET_MS)
  {
    if (motor.motorInit())
    {
      motorReady = true;
      break;
    }
    Serial.println(F("[BOOT] motorInit failed, retrying..."));
    delay(INIT_RETRY_MS);
  }
  if (!motorReady)
  {
    trapPermanent(F("motorInit permanently failed; retrieve float"));
  }

  // on-deck calibration (in air). sensor is at the bottom of the float,
  // which is also mate's scoring reference for deep hold. calibrating in
  // air means "depth = 0" = atmospheric, so later readings directly
  // represent true sensor depth below waterline.
  sensor.calibrateSurface();
  delay(100);
  float depthAfterCal = sensor.getDepth();
  if (depthAfterCal > ONDECK_DEPTH_THRESHOLD_M)
  {
    Serial.print(F("[WARN] on-deck depth="));
    Serial.print(depthAfterCal, 3);
    Serial.println(F(" m; float may already be submerged"));
  }
  else
  {
    Serial.print(F("[BOOT] on-deck cal ok, depth="));
    Serial.print(depthAfterCal, 3);
    Serial.println(F(" m"));
  }

  uint32_t now = millis();
  lastLoopMs = now;
  stateEnteredMs = now;
  currentState = PRE_COMM;
  prevState = PRE_COMM;
  homingOk = false;
}

// ============================================================
// loop
// ============================================================

void loop()
{
  uint32_t now = millis();
  if (now - lastLoopMs < LOOP_MS)
    return;

  float dt = (now - lastLoopMs) / 1000.0f;
  if (dt > MAX_DT_S)
    dt = MAX_DT_S;
  lastLoopMs = now;

  // sensor read with sanity filter
  float d = sensor.getDepth();
  float p = sensor.getPressure_kPa();
  if (depthIsSane(d))
  {
    currentDepth = d;
    lastValidDepth = d;
    currentPressure = p;
  }
  else
  {
    currentDepth = lastValidDepth;
    // pressure left at last good value
  }

  switch (currentState)
  {

  // ----------------------------------------
  // pre_comm: active handshake, no auto-dive
  // ----------------------------------------
  case PRE_COMM:
  {
    // beacon once per second
    if (now - lastBeaconMs >= 1000)
    {
      lastBeaconMs = now;

      DataPacket pkt = {};
      fillPacketHeader(pkt);
      pkt.msgType = PKT_READY;
      pkt.seq = nextSequence;
      pkt.depth_m = currentDepth;
      pkt.pressure_kPa = currentPressure;
      pkt.timestamp_s = now / 1000;
      sender.send(pkt);
    }

    // on ack: attempt homing. no recalibration here (already done on deck).
    // success -> descending. failure -> stay, beacon homingOk=false, re-ack retries.
    if (sender.hasAckFor(nextSequence))
    {
      nextSequence++;
      pid.reset();

      bool stalled = motor.homeMotor();
      if (stalled)
      {
        homingOk = true;
        enterState(DESCENDING, now);
      }
      else
      {
        homingOk = false;
        Serial.println(F("[PRE_COMM] homing failed, awaiting re-ack"));
      }
      break;
    }

    if (!precommWarned && now - stateEnteredMs >= PRECOMM_WARN_MS)
    {
      precommWarned = true;
      Serial.println(F("[WARN] pre_comm unacked > 5 min, still beaconing"));
    }
    break;
  }

  // ----------------------------------------
  // descending: pull water in, sink to deep target
  // ----------------------------------------
  case DESCENDING:
  {
    runPID(targetDepth(), dt, DIR_DOWN);
    logIfDue(now);

    if (atDepth(targetDepth()))
    {
      enterState(HOLDING, now);
    }
    else if (now - stateEnteredMs >= DESCEND_TIMEOUT_MS)
    {
      abortToSurfacing(now);
    }
    break;
  }

  // ----------------------------------------
  // ascending: push water out, rise to shallow target
  // anti-breach floor overrides pid if we get too shallow
  // ----------------------------------------
  case ASCENDING:
  {
    if (currentDepth < BREACH_GUARD_M)
    {
      // override: fill syringe fully to force sinking
      motor.setTargetPosition(motor.volumeToSteps(SYRINGE_MAX_ML));
      Serial.print(F("[BREACH_GUARD] depth="));
      Serial.println(currentDepth, 2);
    }
    else
    {
      runPID(targetDepth(), dt, DIR_UP);
    }
    logIfDue(now);

    if (atDepth(targetDepth()))
    {
      enterState(HOLDING, now);
    }
    else if (now - stateEnteredMs >= ASCEND_TIMEOUT_MS)
    {
      abortToSurfacing(now);
    }
    break;
  }

  // ----------------------------------------
  // holding: maintain target for 30s, drift resets timer
  // ----------------------------------------
  case HOLDING:
  {
    Direction dir = (targetDepth() == DEEP_DEPTH) ? DIR_DOWN : DIR_UP;
    runPID(targetDepth(), dt, dir);
    logIfDue(now);

    if (holdComplete(now))
    {
      nextTask++;
      pid.reset();
      if (nextTask >= 4)
      {
        enterState(SURFACING, now);
      }
      else
      {
        enterState(nextLegState(), now);
      }
    }
    else if (now - stateEnteredMs >= HOLD_TIMEOUT_MS)
    {
      abortToSurfacing(now);
    }
    break;
  }

  // ----------------------------------------
  // surfacing: target=0 set on entry, motor runs autonomously
  // ----------------------------------------
  case SURFACING:
  {
    logIfDue(now);

    if (surfacedAndStable(now))
    {
      enterState(RECOVERED, now);
    }
    else if (now - stateEnteredMs >= SURFACE_TIMEOUT_MS)
    {
      Serial.println(F("[WARN] surfacing timeout, forcing recovered"));
      enterState(RECOVERED, now);
    }
    break;
  }

  // ----------------------------------------
  // recovered: marker state, immediate advance to transmit
  // ----------------------------------------
  case RECOVERED:
  {
    enterState(TRANSMIT, now);
    break;
  }

  // ----------------------------------------
  // transmit: drain ram buffer over esp-now
  // ----------------------------------------
  case TRANSMIT:
  {
    if (txIndex < logger.count())
    {
      if (now - lastTxMs >= 10)
      {
        sender.send(logger.at(txIndex));
        txIndex++;
        lastTxMs = now;
      }
    }
    else
    {
      motor.sleepMotor();
      enterState(DONE, now);
    }
    break;
  }

  // ----------------------------------------
  // done: idle until retrieval
  // ----------------------------------------
  case DONE:
    break;
  }
}
