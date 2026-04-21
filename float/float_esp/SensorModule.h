// Pressure → depth conversion using ADS1115 + SEN0257.
// Call calibrateSurface() once before diving.
#pragma once

#include <Wire.h>
#include <Adafruit_ADS1X15.h>

// Sensor parameters TODO: review these parameters
#define SENSOR_MAX_KPA  1600.0f   // SEN0257 rated 0–1.6 MPa
#define WATER_DENSITY   1000.0f   // kg/m³  (use 1025.0 for saltwater)
#define GRAVITY         9.81f

//  ADS1115 
// TODO: REPLACE WITH CORRECT PINS
#define ADS_SDA_PIN  21
#define ADS_SCL_PIN  22

class SensorModule {
public:
  void   init();
  void   calibrateSurface();   // store current reading as "zero depth"

  float  getPressure_kPa();
  float  getDepth();

private:
  Adafruit_ADS1115 _ads;
  float _surfacePressure_kPa = 101.325f;  // default to 1 atm

  float rawToKPa(int16_t raw);
};
