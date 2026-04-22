#include "PIDController.h"
#include "MotorModule.h"
#include "SensorModule.h"
#include "DataLogger.h"
#include "ESPnow_Sender.h"
#include "packet.h"
#include <math.h>

#define DEEP_DEPTH 2.5f //2.5 meters
#define SHALLOW_DEPTH 0.40f // 40 cm
#define DEPTH_MARGIN 0.33f // +- 33cm
#define TARGET_HOLD_TIME 30 // 30 seconds

#define LOOP_MS 100 // 10 Hz


// TODO: TUNE THESE during pool testing!
#define PID_KP  8.0
#define PID_KI  0.3
#define PID_KD  0.8

#define SYRINGE_MAX_ML 50.0


PIDController pid(PID_KP, PID_KI, PID_KD, 0.0, SYRINGE_MAX_ML);
MotorModule motor;
SensorModule sensor;
DataLogger logger;
ESPNowSender sender;

// State machine 
enum State : uint8_t {
  WAITING = 0,
  DIVING = 1, // going deep
  HOLDING = 2, // hold at current position
  RECOVER = 3, 
  TRANSMIT = 4, // transmit to station
  DONE = 5
};

uint8_t nextTask = 0; // deep1 = 0, shallow1 = 1, deep2 = 2, shallow2 = 3, recover = 4
State currentState = WAITING;
State nextState = WAITING;

bool ack = false; // ack from station to start profiling
float currentDepth = 0;
float currentPressure = 0;
float holdTime = 0;

uint32_t holdCounter = 0;
uint32_t lastHoldUpdateMs = 0;

// loop throttle
uint32_t lastLoopMs = 0;
uint32_t lastLogMs = 0;

uint16_t txIndex = 0; //transmission index to keep track of packets when transmitting

uint32_t lastBeaconMs = 0;
uint16_t nextSequence = 1;

float targetDepth() {
  if (nextTask == 0 || nextTask == 2) return DEEP_DEPTH;
  return SHALLOW_DEPTH;
}

bool atDepth(float target) {
  return fabsf(currentDepth - target) <= DEPTH_MARGIN;
}

// called every loop while in HOLD state
bool holdComplete(uint32_t now) {
  float target = targetDepth();
  uint32_t dt  = now - lastHoldUpdateMs;
  lastHoldUpdateMs = now;

  if (!atDepth(target)) {
    holdCounter = 0;   // TODO: if drifts out, should we reset holdd or what?
    return false;
  }

  holdCounter += dt;
  return holdCounter >= (uint32_t)TARGET_HOLD_TIME * 1000;
}


void runPID(float target, float dt) {
  double pidOut = pid.calculateControlSignal(target, currentDepth, dt);
  long targetSteps = motor.volumeToSteps(pidOut);
  motor.setTargetPosition(targetSteps);
  motor.runMotor();
}

// log info in buffer
void logIfDue(uint32_t now) {
  if (now - lastLogMs < 1000) return;
  lastLogMs = now;

  DataPacket pkt;
  strncpy(pkt.companyID, COMPANY_ID, sizeof(pkt.companyID) - 1);
  pkt.companyID[sizeof(pkt.companyID) - 1] = '\0';
  pkt.timestamp_s  = now / 1000;
  pkt.pressure_kPa = currentPressure;
  pkt.depth_m = currentDepth;
  pkt.profileNum = (nextTask >= 2) ? 2 : 1;
  pkt.state = (uint8_t)currentState;
  logger.log(pkt);
}

// transmit to station
void transmitCallback(const DataPacket& pkt) {
  sender.send(pkt);
}


void setup() {
  Serial.begin(115200);
  sensor.init();

  motor.motorInit();
  sender.init();
}

void loop() {
  uint32_t now = millis();
  if (now - lastLoopMs < LOOP_MS) return;
  float dt = (now - lastLoopMs) / 1000.0f;
  lastLoopMs = now;

  currentDepth = sensor.getDepth();
  currentPressure = sensor.getPressure_kPa();

  switch(currentState) {

    case WAITING: {
      // stay here while ack is false, transition to Deep when ack = true
      if (now - lastBeaconMs >= 1000) {
        lastBeaconMs = now;

        DataPacket pkt = {};
        strncpy(pkt.companyID, COMPANY_ID, sizeof(pkt.companyID) - 1);
        pkt.companyID[sizeof(pkt.companyID) - 1] = '\0';
        pkt.msgType = PKT_READY;
        pkt.seq = nextSequence;
        pkt.depth_m = currentDepth;
        pkt.pressure_kPa = currentPressure;
        pkt.profileNum = 0;
        sender.send(pkt);
      }

      if (sender.hasAckFor(nextSequence)) {
        nextSequence++;
        sensor.calibrateSurface();
        motor.homeMotor();
        pid.reset();
        nextState = DIVING;
      }

      break;
        
    }

    case DIVING: {
      runPID(targetDepth(), dt);
      logIfDue(now);

      if (atDepth(targetDepth())) {
        holdCounter = 0;
        lastHoldUpdateMs = now;
        currentState = HOLDING;
      }

      break;
    }

      case HOLDING: {
        runPID(targetDepth(), dt);
        logIfDue(now);

        if (holdComplete(now)) {
        nextTask++; 
        pid.reset();

          if (nextTask >= 4) {
            motor.setTargetPosition(0); //zero syringe to go back up
            currentState = RECOVER;
          }

          else {
            currentState = DIVING;
          }

        }
        break;
      }

      case RECOVER: { //recvoer to surface depth
        motor.runMotor();

        if (motor.isAtTarget()) {
          txIndex = 0;
          currentState = TRANSMIT;
        }

        break;

      }

      case TRANSMIT: { // transmit to station esp using espnow
        if (txIndex < logger.count()) {
          sender.send(logger.at(txIndex));
          txIndex++;
          delay(10); // small gap between packets
        } 
        
        else {
          motor.sleepMotor();
          currentState = DONE;
        }

        break;
      }

      case DONE:
        break;

    }

  currentState = nextState;
}

