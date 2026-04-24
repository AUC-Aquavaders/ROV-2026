#include "SensorModule.h"

void SensorModule::init() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  // MS5837 startup can take a moment after power-up
  delay(15);

  _ok = _sensor.begin(Wire);
  if (!_ok) {
    return;
  }

  // Default is 30BA; set explicitly for clarity.
  _sensor.setModel(MS5837::MS5837_30BA);
  _sensor.setFluidDensity(WATER_DENSITY);

  // Prime first read so later calls have data immediately.
  _sensor.read();
}

void SensorModule::calibrateSurface() {
  if (!_ok) return;

  // Average a few readings to reduce noise
  float sum = 0;
  const int samples = 8;
  for (int i = 0; i < samples; i++) {
    _sensor.read();
    // library returns mbar
    float mbar = _sensor.pressure();
    float kPa = mbar * 0.1f;
    sum += kPa;
    delay(15);
  }
  _surfacePressure_kPa = sum / (float)samples;
}

float SensorModule::getPressure_kPa() {
  if (!_ok) return 0.0f;
  _sensor.read();
  // MS5837 pressure() returns mbar by default
  return _sensor.pressure() * 0.1f; // kPa
}

float SensorModule::getDepth() {
  if (!_ok) return 0.0f;

  // Use gauge-pressure conversion so depth is zeroed by calibrateSurface().
  float pressure_kPa = getPressure_kPa();
  float gauge_kPa = pressure_kPa - _surfacePressure_kPa;
  if (gauge_kPa < 0) gauge_kPa = 0;

  // depth = gauge_pressure(Pa) / (rho * g)
  return (gauge_kPa * 1000.0f) / (WATER_DENSITY * GRAVITY);
}
