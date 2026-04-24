#pragma once

#define STEPS_PER_ML 200 // TODO: REVIEW STEPS PER ML
#define MAX_STEPS (STEPS_PER_ML * 50) // 50 ml syringe

#define MIN_POSITION 0
#include <ctime>
class MockMotorModule {

public: 

  MockMotorModule() {
    currentPosition = 0;
    targetPosition = 0;
  }

  void motorInit();
  // {
  //   pinMode(STEP_PIN, OUTPUT);
  //   pinMode(DIR_PIN, OUTPUT);
      
  //   // Start UART communication on ESP32 Serial2
  //   Serial2.begin(BAUD_RATE);
  //   driver.setup(Serial2, BAUD_RATE, TMC2209::SERIAL_ADDRESS_0, RX_PIN, TX_PIN);
      
  //   // Set power levels (MKS TMC2209 V2.0 supports up to 2A, Nema 17HS4401S is rated 1.7A) 
  //   driver.setRunCurrent(RUN_CURRENT);
  //   driver.setHoldCurrent(HOLD_CURRENT);
      
    
  //   driver.enableCoolStep(); 
  //   driver.enableAutomaticCurrentScaling(); 
  //   driver.enable();
  // }                           

  void homeMotor();
  // {
  //   driver.setStallGuardThreshold(STALL_SENSITIVITY);
  //   digitalWrite(DIR_PIN, LOW); // Set direction to retract (empty the syringe)
      
  //   bool stalled = false;
  //   while (!stalled) {
  //       // Take a step slowly
  //       digitalWrite(STEP_PIN, HIGH);
  //       delayMicroseconds(1000); 
  //       digitalWrite(STEP_PIN, LOW);
  //       delayMicroseconds(1000);
          
  //       // Read StallGuard result. A low number means we hit the physical wall.
  //       if (driver.getStallGuardResult() < 5) { 
  //           stalled = true;
  //       }
  //   }
      
  //   // Reset our memory to 0 
  //   currentPosition = 0;
  //   targetPosition = 0;
  // }                           

  // Takes output from PID and converts to steps
  long volumeToSteps(double volume);
  // { 
  //   return (long)(volume * STEPS_PER_ML);
  // }      

  void setTargetPosition(long targetSteps);
  // {
  //   targetPosition = targetSteps;
  //   checkLimits(); // Additional safety check
      
  //   // Compare target to memory to determine physical motor direction
  //   if (targetPosition > currentPosition) {
  //       digitalWrite(DIR_PIN, HIGH); // Pulling water IN
  //   } else if (targetPosition < currentPosition) {
  //       digitalWrite(DIR_PIN, LOW);  // Pushing water OUT
  //   }
  // }    

  void runMotor();
  // {
  //   // Only pulse the motor if we haven't reached the PID's target yet
  //   if (currentPosition != targetPosition) {
          
  //       digitalWrite(STEP_PIN, HIGH);
  //       delayMicroseconds(500); 
  //       digitalWrite(STEP_PIN, LOW);
  //       delayMicroseconds(500);
          
  //       // Update the internal tracker
  //       if (targetPosition > currentPosition) {
  //           currentPosition++;
  //       } else {
  //           currentPosition--;
  //       }
  //   }
  // }                           

  void setHoldingMode(bool enable);
  // {  
  //   if (enable) {
  //       driver.setStandstillMode(TMC2209::STRONG_BRAKING);
  //   } else {
  //       driver.setStandstillMode(TMC2209::NORMAL);
  //   }
  // }          

  void sleepMotor();
  // { // For saving battery 
  //   driver.disable();
  // }                          

  void checkLimits();
  // { // Secondary safety check (Primary in PID)
  //   if (targetPosition > MAX_STEPS) targetPosition = MAX_STEPS;
  //   if (targetPosition < 0) targetPosition = 0;
  // }                        


  bool isAtTarget();
  // {
  //     return (currentPosition == targetPosition);
  // }

  long getCurrentPosition();
  //  {
  //   return currentPosition;
  // }

private:
  long currentPosition; // Internal memory tracker
  long targetPosition;  // Destination memory

};
