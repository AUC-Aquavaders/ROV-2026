#include "MockSensorModule.h"
#include <Arduino.h>
void MockSensorModule::init() {
  _ok = true;
}

void MockSensorModule::calibrateSurface() {
  if (!_ok) return;

  // Mock calibration: set to default
  _surfacePressure_kPa = 101.325f;
}

float MockSensorModule::getPressure_kPa() {
  if (!_ok) return 0.0f;
  // Mock pressure: simulate some variation
  return 102.0f + (millis() % 10000) * 0.001f; // varies from 102 to 112 kPa
}

float MockSensorModule::getDepth() {
  if (!_ok) return 0.0f;

  // Use gauge-pressure conversion so depth is zeroed by calibrateSurface().
  float pressure_kPa = getPressure_kPa();
  float gauge_kPa = pressure_kPa - _surfacePressure_kPa;
  if (gauge_kPa < 0) gauge_kPa = 0;

  // depth = gauge_pressure(Pa) / (rho * g)
  return (gauge_kPa * 1000.0f) / (WATER_DENSITY * GRAVITY);
}
