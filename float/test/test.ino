// Mission sequence:
// PRE_COMM -> DESCENDING -> HOLDING(deep)-> ASCENDING -> HOLDING(shallow) -> DESCENDING -> HOLDING(deep) -> ASCENDING -> HOLDING(shallow) -> SURFACING  -> RECOVERED -> TRANSMIT  -> DONE

// Safe failure mode for any motion-state timeout is SURFACING (empty syringe,float to the surface). PRE_COMM does NOT auto-dive on timeout; it keeps beaconing forever because we never want an unacknowledged dive.

#include "PIDController.h"
#include "MockMotorModule.h"
#include "MockSensorModule.h"
#include "DataLogger.h"
#include "MockESPnow_Sender.h"
#include "packet.h"
#include <math.h>

// mission parameters
#define DEEP_DEPTH      2.5f    // m, target for deep holds
#define SHALLOW_DEPTH   0.40f   // m, target for shallow holds
#define DEPTH_MARGIN    0.33f   // m, ± band that counts as "at depth"
#define TARGET_HOLD_MS  30000UL // 30 s hold per MATE rubric

// Surface-detection trigger (SURFACING -> RECOVERED)
#define SURFACE_DEPTH_M   0.15f
#define SURFACE_STABLE_MS 3000UL

// Per-state abort watchdogs. On expiry, motion states route to SURFACING.
// PRE_COMM does not auto-advance; it just logs the timeout.
#define PRECOMM_WARN_MS    300000UL  // 5 min: log a warning but keep beaconing
#define DESCEND_TIMEOUT_MS  90000UL  // 90 s to reach deep target
#define ASCEND_TIMEOUT_MS   90000UL  // 90 s to reach shallow target
#define HOLD_TIMEOUT_MS    120000UL  // 120 s cap on a single hold attempt
#define SURFACE_TIMEOUT_MS  60000UL  // 60 s to surface once syringe is emptying

// Control loop
#define LOOP_MS    100          // 10 Hz
#define MAX_DT_S   0.5f         // clamp dt to avoid PID blowup after a long loop

// Sensor sanity bounds (pool is ~3 m; anything outside is garbage)
#define MIN_VALID_DEPTH_M  (-0.5f)
#define MAX_VALID_DEPTH_M  ( 5.0f)

// PID 
// Shared gains for DESCENDING and ASCENDING for now. Structured so gains can be split later via runPID()'s Direction parameter.
// TODO: TUNE during pool testing!
#define PID_KP_SHARED  8.0
#define PID_KI_SHARED  0.3
#define PID_KD_SHARED  0.8

#define SYRINGE_MAX_ML 50.0

PIDController pid(PID_KP_SHARED, PID_KI_SHARED, PID_KD_SHARED, 0.0, SYRINGE_MAX_ML);
MockMotorModule   motor;
MockSensorModule  sensor;
DataLogger    logger;
MockESPNowSender  sender;

// -------------------- FSM --------------------
enum State : uint8_t {
  PRE_COMM   = 0,
  DESCENDING = 1,
  ASCENDING  = 2,
  HOLDING    = 3,
  SURFACING  = 4,
  RECOVERED  = 5,
  TRANSMIT   = 6,
  DONE       = 7
};

// Task index: 0=deep1, 1=shallow1, 2=deep2, 3=shallow2, 4=profiles complete.
uint8_t nextTask     = 0;
State   currentState = PRE_COMM;
State   prevState    = PRE_COMM; // for enterState() detection

// -------------------- Sensor state --------------------
float currentDepth    = 0.0f;
float currentPressure = 0.0f;
float lastValidDepth  = 0.0f;

// -------------------- Timers --------------------
uint32_t stateEnteredMs    = 0;   // ms at entry to currentState
uint32_t holdCounter       = 0;
uint32_t lastHoldUpdateMs  = 0;
uint32_t surfaceStableMs   = 0;
uint32_t lastSurfaceUpdate = 0;

uint32_t lastLoopMs    = 0;
uint32_t lastLogMs     = 0;
uint32_t lastBeaconMs  = 0;
uint32_t lastTxMs      = 0;
bool     precommWarned = false;

uint16_t txIndex      = 0;
uint16_t nextSequence = 1;

// -------------------- Direction tag (for future gain-splitting) --------------------
enum Direction : uint8_t { DIR_DOWN = 0, DIR_UP = 1 };


// -------------------- Forward decls --------------------
void enterState(State s, uint32_t now);
void fillPacketHeader(DataPacket& pkt);
float targetDepth();
bool  atDepth(float target);
State nextLegState();
bool  holdComplete(uint32_t now);
void  runPID(float target, float dt, Direction dir);
void  logIfDue(uint32_t now);
bool  surfacedAndStable(uint32_t now);
bool  depthIsSane(float d);
void  abortToSurfacing(uint32_t now);


// ==================== Helpers ====================

// Centralized state transition. Resets per-state counters here so no call site
// can forget to initialize them.
void enterState(State s, uint32_t now) {
  prevState      = currentState;
  currentState   = s;
  stateEnteredMs = now;

  switch (s) {
    case HOLDING:
      holdCounter      = 0;
      lastHoldUpdateMs = now;
      break;
    case SURFACING:
      motor.setTargetPosition(0); // empty syringe = max buoyancy
      surfaceStableMs   = 0;
      lastSurfaceUpdate = now;
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

// Fills the common identifier/timestamp/state fields on any outgoing packet.
void fillPacketHeader(DataPacket& pkt) {
  strncpy(pkt.companyID, COMPANY_ID, sizeof(pkt.companyID) - 1);
  pkt.companyID[sizeof(pkt.companyID) - 1] = '\0';
  pkt.state      = (uint8_t)currentState;
  pkt.profileNum = (nextTask >= 2) ? 2 : 1;
}

float targetDepth() {
  if (nextTask == 0 || nextTask == 2) {
    Serial.println("Target is deep depth");
    return DEEP_DEPTH;
  } 
  
  if (nextTask == 1 || nextTask == 3) {
    Serial.println("Target is shallow depth");
    return SHALLOW_DEPTH;
  }
  return NAN;
}

bool atDepth(float target) {
  return fabsf(currentDepth - target) <= DEPTH_MARGIN;
}

State nextLegState() {
  if (nextTask == 0 || nextTask == 2) return DESCENDING;
  return ASCENDING;
}

bool holdComplete(uint32_t now) {
  float target = targetDepth();
  uint32_t dt  = now - lastHoldUpdateMs;
  lastHoldUpdateMs = now;

  if (!atDepth(target)) {
    holdCounter = 0;
    return false;
  }
  holdCounter += dt;
  return holdCounter >= TARGET_HOLD_MS;
}

void runPID(float target, float dt, Direction /*dir*/) {
  // When gains get split:
  //   if (dir == DIR_UP)  pid.setGains(Kp_up,   Ki_up,   Kd_up);
  //   else                pid.setGains(Kp_down, Ki_down, Kd_down);
  double pidOut      = pid.calculateControlSignal(target, currentDepth, dt);
  long   targetSteps = motor.volumeToSteps(pidOut);
  motor.setTargetPosition(targetSteps);
  // motor.runMotor(); // assumed non-blocking: one step-tick per call
}

void logIfDue(uint32_t now) {
  if (now - lastLogMs < 1000) return;
  lastLogMs = now;

  DataPacket pkt = {};
  fillPacketHeader(pkt);
  pkt.timestamp_s  = now / 1000;
  pkt.pressure_kPa = currentPressure;
  pkt.depth_m      = currentDepth;
  logger.log(pkt);
}

bool surfacedAndStable(uint32_t now) {
  uint32_t dt = now - lastSurfaceUpdate;
  lastSurfaceUpdate = now;

  if (currentDepth > SURFACE_DEPTH_M) {
    surfaceStableMs = 0;
    return false;
  }
  surfaceStableMs += dt;
  return (surfaceStableMs >= SURFACE_STABLE_MS) && motor.isAtTarget();
}

bool depthIsSane(float d) {
  return !isnan(d) && d >= MIN_VALID_DEPTH_M && d <= MAX_VALID_DEPTH_M;
}

// Safe failure path: empty the syringe and try to surface.
void abortToSurfacing(uint32_t now) {
  Serial.print(F("[ABORT] state="));
  Serial.print((int)currentState);
  Serial.print(F(" t="));
  Serial.println(now);
  pid.reset();
  enterState(SURFACING, now);
}


// ==================== Arduino entry points ====================

void setup() {
  Serial.begin(115200);
  delay(2000); // give the monitor time to connect
  Serial.println(F("=== SETUP START ==="));
  sensor.init();
  motor.motorInit();
  sender.init();

  uint32_t now = millis();
  lastLoopMs     = now;
  stateEnteredMs = now;
  currentState   = PRE_COMM;
  prevState      = PRE_COMM;
  // Note: sender should start with a clean ACK table. If ESPNowSender caches
  // ACKs across resets (unlikely but possible), clear it here.
}

void loop() {
  delay(2000);
  uint32_t now = millis();
  Serial.print("loop() now="); Serial.print(now);
  Serial.print(" lastLoopMs="); Serial.println(lastLoopMs);

  if (now - lastLoopMs < LOOP_MS) {
    Serial.println("returning here");
    return;
  }

  Serial.println("passed guard");

  float dt = (now - lastLoopMs) / 1000.0f;
  if (dt > MAX_DT_S) dt = MAX_DT_S; // clamp after any blocking hiccup
  lastLoopMs = now;

  // --- Sensor read with sanity filter ---
  float d = sensor.getDepth();
  Serial.print("depth="); Serial.println(d);

  float p = sensor.getPressure_kPa();
  Serial.print("pressure="); Serial.println(p);

  if (depthIsSane(d)) {
    currentDepth   = d;
    lastValidDepth = d;
  } else {
    currentDepth = lastValidDepth; // hold the last good reading
  }
  currentPressure = p;

  Serial.println(currentState);
  // --- State machine ---
  switch (currentState) {

    case PRE_COMM: {
      // check ack first
      if (sender.hasAckFor(nextSequence)) {
        nextSequence++;
        sensor.calibrateSurface();
        motor.homeMotor();
        pid.reset();
        enterState(DESCENDING, now);
        break;
      }

      // Beacon once per second until the station ACKs our sequence number.
      if (now - lastBeaconMs >= 1000) {
        lastBeaconMs = now;
        Serial.println("lastLoopMs updated");

        DataPacket pkt = {};
        fillPacketHeader(pkt);
        pkt.msgType      = PKT_READY;
        pkt.seq          = nextSequence;
        pkt.depth_m      = currentDepth;
        pkt.pressure_kPa = currentPressure;
        pkt.timestamp_s  = now / 1000;
        sender.send(pkt);
        Serial.println("sent packet");
      }

      if (sender.hasAckFor(nextSequence)) {
        nextSequence++;
        sensor.calibrateSurface(); // zero depth at real waterline
        motor.homeMotor();
        pid.reset();
        enterState(DESCENDING, now);
        Serial.println("ack received");
        break;
      }

      // Deliberately never auto-advance on timeout: we only dive on ACK.
      if (!precommWarned && now - stateEnteredMs >= PRECOMM_WARN_MS) {
        precommWarned = true;
        Serial.println(F("[WARN] PRE_COMM unacked > 5 min, still beaconing"));
      }

      Serial.println("at end of PRE-COMM");
      break;

    }

    case DESCENDING: {
      Serial.println("IN DESCENDING CASE");
      runPID(targetDepth(), dt, DIR_DOWN);
      logIfDue(now);

      if (atDepth(targetDepth())) {
        enterState(HOLDING, now);
      } else if (now - stateEnteredMs >= DESCEND_TIMEOUT_MS) {
        abortToSurfacing(now);
      }
      break;
    }

    case ASCENDING: {
      Serial.println("IN ASCENDING CASE");
      runPID(targetDepth(), dt, DIR_UP);
      logIfDue(now);

      if (atDepth(targetDepth())) {
        enterState(HOLDING, now);
      } 
      else if (now - stateEnteredMs >= ASCEND_TIMEOUT_MS) {
        abortToSurfacing(now);
      }
      break;
    }

    case HOLDING: {
      Serial.println("IN HOLDING CASE");
      Direction dir = (targetDepth() == DEEP_DEPTH) ? DIR_DOWN : DIR_UP;
      runPID(targetDepth(), dt, dir);
      logIfDue(now);

      if (holdComplete(now)) {
        nextTask++;
        pid.reset();

        if (nextTask >= 4) {
          enterState(SURFACING, now);
        } else {
          enterState(nextLegState(), now);
        }
      } else if (now - stateEnteredMs >= HOLD_TIMEOUT_MS) {
        // Couldn't stabilize for 30 s within a 2-minute budget: abort up.
        abortToSurfacing(now);
      }
      break;
    }

    case SURFACING: {
      Serial.println("IN SURFACING CASE");
      // motor.runMotor(); // non-blocking step toward target=0 set at entry
      logIfDue(now);

      if (surfacedAndStable(now)) {
        enterState(RECOVERED, now);
      } else if (now - stateEnteredMs >= SURFACE_TIMEOUT_MS) {
        // If we can't confirm surface in 60 s, assume we're close enough
        // and proceed to transmit anyway — better to get partial data out
        // than sit silent until battery dies.
        Serial.println(F("[WARN] SURFACING timeout, forcing RECOVERED"));
        enterState(RECOVERED, now);
      }
      break;
    }

    case RECOVERED: {
      Serial.println("IN RECOVERED CASE");
      // Brief marker state. Could hang a post-recovery handshake here later.
      enterState(TRANSMIT, now);
      break;
    }

    case TRANSMIT: {
      Serial.println("IN TRANSMIT CASE");
      // Non-blocking: one packet per loop tick (every LOOP_MS = 100 ms).
      // For a ~5-minute dive logging at 1 Hz, that's ~300 packets -> 30 s TX.
      if (txIndex < logger.count()) {
        if (now - lastTxMs >= 10) { // minimum 10 ms between packets
          sender.send(logger.at(txIndex));
          txIndex++;
          lastTxMs = now;
        }
      } else {
        motor.sleepMotor();
        enterState(DONE, now);
      }
      break;
    }

    case DONE:
      // Idle until power cycle / retrieval.
      Serial.println("DONE!");
      break;
  }
}

