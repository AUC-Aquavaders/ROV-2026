// Pressure → depth conversion using BlueRobotics MS5837.
// Call calibrateSurface() once before diving to zero depth.
#pragma once

#include <Wire.h>
#include <MS5837.h>

// Fluid parameters
#define WATER_DENSITY   997.0f    // kg/m^3 freshwater (use 1025.0 for seawater)
#define GRAVITY         9.80665f

#define I2C_SDA_PIN  21
#define I2C_SCL_PIN  22

class SensorModule {
public:
  void   init();
  void   calibrateSurface();   // store current reading as "zero depth"

  float  getPressure_kPa();
  float  getDepth();

private:
  MS5837 _sensor;
  float _surfacePressure_kPa = 101.325f;  // default to 1 atm
  bool  _ok = false;
};
