// Pressure → depth conversion using BlueRobotics MS5837.
// Call calibrateSurface() once before diving to zero depth.
#pragma once
#include <ctime>
// Fluid parameters
#define WATER_DENSITY   997.0f    // kg/m^3 freshwater (use 1025.0 for seawater)
#define GRAVITY         9.80665f

class MockSensorModule {
public:
  void   init();
  void   calibrateSurface();   // store current reading as "zero depth"

  float  getPressure_kPa();
  float  getDepth();

private:
  float _surfacePressure_kPa = 101.325f;  // default to 1 atm
  bool  _ok = false;
};
