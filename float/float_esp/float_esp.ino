// MAIN ENTRY POINT FOR FLOAT

// STATE MACHINE:
//   IDLE
//     └─(button press)→ PRE_COMM       send "ready" beacon
//   PRE_COMM
//     └─(sent)→ HOMING                 zero syringe position
//   HOMING
//     └─(homed)→ DESCEND_1
//
//   ── Profile 1 ──────────────────────────────────────────────
//   DESCEND_1   PID drives to DEEP_TARGET_M
//     └─(depth reached)→ HOLD_DEEP_1
//   HOLD_DEEP_1  maintain 2.5 m for HOLD_DURATION_S seconds
//     └─(timer done)→ ASCEND_1
//   ASCEND_1    PID drives to SHALLOW_TARGET_M
//     └─(depth reached)→ HOLD_SHALLOW_1
//   HOLD_SHALLOW_1  maintain 0.4 m for HOLD_DURATION_S seconds
//     └─(timer done)→ DESCEND_2
//
//   ── Profile 2 ──────────────────────────────────────────────
//   DESCEND_2 … HOLD_SHALLOW_2  (same structure)
//
//   SURFACE_WAIT  float is recovered, press button to transmit
//   TRANSMITTING  replay log over ESPNow, one packet at a time
//   DONE


//TODO: review float main
#include "PIDController.h"
#include "MotorModule.h"
#include "SensorModule.h"
#include "DataLogger.h"
#include "ESPnow_Sender.h"
#include "packet.h"
#include <math.h>

// Dive profile parameters (meters)
#define DEEP_TARGET_M     2.5f
#define SHALLOW_TARGET_M  0.40f
#define DEPTH_TOLERANCE_M 0.05f     // within ±5 cm = "at depth"
#define HOLD_DURATION_S   30        // seconds to hold each depth

#define SYRINGE_MAX_ML 50.0

// Safety ceiling
// If float gets shallower than this while in HOLD_SHALLOW, warn.
#define SURFACE_PENALTY_DEPTH_M  0.05f


// PID Parameters
// TODO: TUNE THESE during pool testing!
#define PID_KP  8.0
#define PID_KI  0.3
#define PID_KD  0.8

// Loop timing
#define LOOP_INTERVAL_MS  100 // 10 Hz control loop

// Comms reliability
#define READY_BEACON_INTERVAL_MS 1000
#define ACK_TIMEOUT_MS           200
#define ACK_MAX_RETRIES          8

// Surface detection for autonomous transmit after recovery
#define SURFACE_DETECT_DEPTH_M   0.15f
#define SURFACE_STABLE_MS        10000


// Objects
PIDController pid(PID_KP, PID_KI, PID_KD, 0.0, SYRINGE_MAX_ML);
MotorModule motor;
SensorModule sensor;
DataLogger logger;
ESPNowSender sender;

// State machine 
enum State : uint8_t {
  IDLE            = 0,
  PRE_COMM        = 1,
  HOMING          = 2,
  DESCEND_1       = 3,
  HOLD_DEEP_1     = 4,
  ASCEND_1        = 5,
  HOLD_SHALLOW_1  = 6,
  DESCEND_2       = 7,
  HOLD_DEEP_2     = 8,
  ASCEND_2        = 9,
  HOLD_SHALLOW_2  = 10,
  SURFACE_WAIT    = 11,
  TRANSMITTING    = 12,
  DONE            = 13
};


State currentState  = IDLE;
uint32_t holdStartTime = 0;
uint32_t lastLoopTime  = 0;
uint32_t lastLogTime   = 0;

uint8_t currentProfile = 0;   // 1 or 2, set when profile starts

// Hold tracking (continuous-in-tolerance)
uint32_t holdAccumMs = 0;
uint32_t lastHoldUpdateMs = 0;

// Comms tracking
uint16_t nextSeq = 1;
uint32_t lastReadyBeaconMs = 0;
uint32_t lastTxAttemptMs = 0;
uint8_t  txRetries = 0;
uint16_t awaitingAckSeq = 0;
bool     awaitingAck = false;

// Transmission replay
uint16_t txIndex = 0;

// Surface stable tracking
uint32_t surfaceStableStartMs = 0;


// Helpers

const char* stateName(State s) {
  switch(s) {
    case IDLE:           return "IDLE";
    case PRE_COMM:       return "PRE_COMM";
    case HOMING:         return "HOMING";
    case DESCEND_1:      return "DESCEND_1";
    case HOLD_DEEP_1:    return "HOLD_DEEP_1";
    case ASCEND_1:       return "ASCEND_1";
    case HOLD_SHALLOW_1: return "HOLD_SHALLOW_1";
    case DESCEND_2:      return "DESCEND_2";
    case HOLD_DEEP_2:    return "HOLD_DEEP_2";
    case ASCEND_2:       return "ASCEND_2";
    case HOLD_SHALLOW_2: return "HOLD_SHALLOW_2";
    case SURFACE_WAIT:   return "SURFACE_WAIT";
    case TRANSMITTING:   return "TRANSMITTING";
    case DONE:           return "DONE";
    default:             return "UNKNOWN";
  }
}

void transitionTo(State next) {
  currentState = next;

  // Reset per-state timers where appropriate
  if (next == HOLD_DEEP_1 || next == HOLD_DEEP_2 || next == HOLD_SHALLOW_1 || next == HOLD_SHALLOW_2) {
    holdAccumMs = 0;
    lastHoldUpdateMs = millis();
  }
}

// bool buttonPressed() {
//   // Active low (pulled-up BOOT button)
//   return digitalRead(TRIGGER_BTN_PIN) == LOW;
// }

bool atDepth(float current, float target) {
  return fabsf(current - target) <= DEPTH_TOLERANCE_M;
}

void markHoldProgress(uint32_t now, bool inTolerance) {
  if (lastHoldUpdateMs == 0) lastHoldUpdateMs = now;
  uint32_t dtMs = now - lastHoldUpdateMs;
  lastHoldUpdateMs = now;

  if (!inTolerance) {
    holdAccumMs = 0;
    return;
  }

  // Accumulate continuous time in tolerance
  if (holdAccumMs < 0xFFFFFFF0u) holdAccumMs += dtMs;
}


void buildPacket(DataPacket& pkt, float depth, float pressure) {
  // strncpy(pkt.companyID, COMPANY_ID, sizeof(pkt.companyID));
  strncpy(pkt.companyID, COMPANY_ID, sizeof(pkt.companyID) - 1);
  pkt.companyID[sizeof(pkt.companyID) - 1] = '\0';
  pkt.msgType      = PKT_DATA;
  pkt.reserved0    = 0;
  pkt.seq          = 0;
  pkt.timestamp_s  = millis() / 1000;
  pkt.pressure_kPa = pressure;
  pkt.depth_m      = depth;
  pkt.profileNum   = currentProfile;
  pkt.state        = (uint8_t)currentState;
}

// Callback used by logger.replayAll()
void transmitPacket(const DataPacket& pkt) {
  sender.send(pkt);
}

//TODO: REPLACE SERIAL PRINTS
// Setup
void setup() {
  Serial.begin(115200);
  delay(500);

  // pinMode(TRIGGER_BTN_PIN, INPUT_PULLUP);

  sensor.init();
  motor.motorInit();
  sender.init();
}


// MAIN LOOP ///////////////////////////////////////
void loop() {
  uint32_t now = millis();

  // Throttle to LOOP_INTERVAL_MS
  if (now - lastLoopTime < LOOP_INTERVAL_MS) return;
  float dt = (now - lastLoopTime) / 1000.0f;
  lastLoopTime = now;

  // Read sensors every cycle
  float depth    = sensor.getDepth();
  float pressure = sensor.getPressure_kPa();

  // ── State machine ─────────────────────────────────────────
  switch (currentState) {

    // ── IDLE: wait for button press ──────────────────────────
    case IDLE:
      // on power-up, calibrate surface and begin handshake.
      sensor.calibrateSurface();
      sender.resetAcks();
      lastReadyBeaconMs = 0;
      awaitingAck = false;
      transitionTo(PRE_COMM);
      break;

    // ── PRE_COMM: send ready beacon to station ───────────────
    case PRE_COMM: {
      // Keep broadcasting READY until station ACKs, then proceed.
      if (now - lastReadyBeaconMs >= READY_BEACON_INTERVAL_MS) {
        lastReadyBeaconMs = now;

        DataPacket pkt;
        buildPacket(pkt, depth, pressure);
        pkt.msgType = PKT_READY;
        pkt.profileNum = 0;
        pkt.seq = nextSeq++;
        sender.send(pkt);

        awaitingAck = true;
        awaitingAckSeq = pkt.seq;
      }

      if (awaitingAck && sender.hasAckFor(awaitingAckSeq)) {
        awaitingAck = false;
        transitionTo(HOMING);
      }
      break;
    }

    // ── HOMING: zero the syringe ─────────────────────────────
    case HOMING:
      motor.homeMotor();
      pid.reset();
      currentProfile = 1;
      transitionTo(DESCEND_1);
      break;

    // ── DESCEND: PID toward deep target ──────────────────────
    case DESCEND_1:
    case DESCEND_2: {
      double pidOut = pid.calculateControlSignal(DEEP_TARGET_M, depth, dt);
      long targetSteps = motor.volumeToSteps(pidOut); // PID output is mL
      motor.setTargetPosition(targetSteps);
      motor.runMotor();

      logIfDue(now, depth, pressure);

      if (atDepth(depth, DEEP_TARGET_M)) {
        holdStartTime = now;
        transitionTo(currentState == DESCEND_1 ? HOLD_DEEP_1 : HOLD_DEEP_2);
      }
      break;
    }

    // ── HOLD_DEEP: maintain 2.5 m for 30 s ──────────────────
    case HOLD_DEEP_1:
    case HOLD_DEEP_2: {
      double pidOut = pid.calculateControlSignal(DEEP_TARGET_M, depth, dt);
      long targetSteps = motor.volumeToSteps(pidOut);
      motor.setTargetPosition(targetSteps);
      motor.runMotor();

      logIfDue(now, depth, pressure);

      markHoldProgress(now, atDepth(depth, DEEP_TARGET_M));
      if (holdAccumMs >= (uint32_t)HOLD_DURATION_S * 1000) {
        pid.reset();
        transitionTo(currentState == HOLD_DEEP_1 ? ASCEND_1 : ASCEND_2);
      }
      break;
    }

    // ── ASCEND: PID toward shallow target ────────────────────
    case ASCEND_1:
    case ASCEND_2: {
      double pidOut = pid.calculateControlSignal(SHALLOW_TARGET_M, depth, dt);
      long targetSteps = motor.volumeToSteps(pidOut);
      motor.setTargetPosition(targetSteps);
      motor.runMotor();

      logIfDue(now, depth, pressure);

      // Safety: warn if approaching surface
      if (depth < SURFACE_PENALTY_DEPTH_M) {
      }

      if (atDepth(depth, SHALLOW_TARGET_M)) {
        holdStartTime = now;
        transitionTo(currentState == ASCEND_1 ? HOLD_SHALLOW_1 : HOLD_SHALLOW_2);
      }
      break;
    }

    // ── HOLD_SHALLOW: maintain 0.4 m for 30 s ───────────────
    case HOLD_SHALLOW_1:
    case HOLD_SHALLOW_2: {
      double pidOut = pid.calculateControlSignal(SHALLOW_TARGET_M, depth, dt);
      long targetSteps = motor.volumeToSteps(pidOut);
      motor.setTargetPosition(targetSteps);
      motor.runMotor();

      logIfDue(now, depth, pressure);

      if (depth < SURFACE_PENALTY_DEPTH_M) {
      }

      markHoldProgress(now, atDepth(depth, SHALLOW_TARGET_M));
      if (holdAccumMs >= (uint32_t)HOLD_DURATION_S * 1000) {
        pid.reset();
        if (currentState == HOLD_SHALLOW_1) {
          currentProfile = 2;
          transitionTo(DESCEND_2);        // start profile 2
        } else {
          motor.setTargetPosition(0);       // push water out, float rises
          transitionTo(SURFACE_WAIT);
        }
      }
      break;
    }

    // ── SURFACE_WAIT: recovered — button to transmit ─────────
    case SURFACE_WAIT:
      motor.runMotor();   // finish emptying syringe
      // No button: once we are near-surface and stable, start transmitting.
      if (depth <= SURFACE_DETECT_DEPTH_M) {
        if (surfaceStableStartMs == 0) surfaceStableStartMs = now;
        if (now - surfaceStableStartMs >= SURFACE_STABLE_MS) {
          txIndex = 0;
          awaitingAck = false;
          txRetries = 0;
          lastTxAttemptMs = 0;
          sender.resetAcks();
          transitionTo(TRANSMITTING);
        }
      } else {
        surfaceStableStartMs = 0;
      }
      break;

    // ── TRANSMITTING: replay log over ESPNow ─────────────────
    case TRANSMITTING:
      // Reliable stop-and-wait replay with ACK+retry.
      if (txIndex >= logger.count()) {
        // Send DONE marker once, with best-effort retry.
        if (!awaitingAck) {
          DataPacket donePkt;
          buildPacket(donePkt, depth, pressure);
          donePkt.msgType = PKT_DONE;
          donePkt.profileNum = 0;
          donePkt.seq = nextSeq++;
          sender.send(donePkt);
          awaitingAck = true;
          awaitingAckSeq = donePkt.seq;
          txRetries = 0;
          lastTxAttemptMs = now;
        } else if (sender.hasAckFor(awaitingAckSeq)) {
          motor.sleepMotor();
          transitionTo(DONE);
        } else if (now - lastTxAttemptMs >= ACK_TIMEOUT_MS) {
          if (txRetries++ >= ACK_MAX_RETRIES) {
            motor.sleepMotor();
            transitionTo(DONE);
          } else {
            // Re-send DONE by reusing awaitingAckSeq as reference; create a fresh DONE with same seq
            DataPacket donePkt;
            buildPacket(donePkt, depth, pressure);
            donePkt.msgType = PKT_DONE;
            donePkt.profileNum = 0;
            donePkt.seq = awaitingAckSeq;
            sender.send(donePkt);
            lastTxAttemptMs = now;
          }
        }
        break;
      }

      if (!awaitingAck) {
        DataPacket pkt = logger.at(txIndex);
        pkt.msgType = PKT_DATA;
        pkt.seq = nextSeq++;
        sender.send(pkt);

        awaitingAck = true;
        awaitingAckSeq = pkt.seq;
        txRetries = 0;
        lastTxAttemptMs = now;
      } else {
        if (sender.hasAckFor(awaitingAckSeq)) {
          awaitingAck = false;
          txIndex++;
        } else if (now - lastTxAttemptMs >= ACK_TIMEOUT_MS) {
          if (txRetries++ >= ACK_MAX_RETRIES) {
            awaitingAck = false;
            txIndex++;
          } else {
            DataPacket pkt = logger.at(txIndex);
            pkt.msgType = PKT_DATA;
            pkt.seq = awaitingAckSeq; // keep seq constant across retries
            sender.send(pkt);
            lastTxAttemptMs = now;
          }
        }
      }
      break;

    case DONE:
      // Nothing left to do.
      break;
  }
}


//  Log one packet per second
void logIfDue(uint32_t now, float depth, float pressure) {
  if (now - lastLogTime < 1000) return;
  lastLogTime = now;

  DataPacket pkt;
  buildPacket(pkt, depth, pressure);
  logger.log(pkt);
}
