#include "SensorModule.h"

//TODO: REVIEW SENSOR CODE
void SensorModule::init() {
  Wire.begin(ADS_SDA_PIN, ADS_SCL_PIN);
  _ads.setGain(GAIN_ONE);   // ±4.096 V range
  if (!_ads.begin()) {
    Serial.println("[SENSOR] ADS1115 not found — check wiring!");
  }
}

void SensorModule::calibrateSurface() {
  // Average 10 readings to reduce noise
  float sum = 0;
  for (int i = 0; i < 10; i++) {
    int16_t raw = _ads.readADC_SingleEnded(0);
    sum += rawToKPa(raw);
    delay(20);
  }
  _surfacePressure_kPa = sum / 10.0f;
  Serial.printf("[SENSOR] Surface calibrated: %.2f kPa\n", _surfacePressure_kPa);
}

float SensorModule::getPressure_kPa() {
  int16_t raw = _ads.readADC_SingleEnded(0);
  return rawToKPa(raw);
}

float SensorModule::getDepth() {
  float pressure = getPressure_kPa();
  float gauge_kPa = pressure - _surfacePressure_kPa;
  if (gauge_kPa < 0) gauge_kPa = 0;
  // depth = gauge_pressure / (rho * g)
  // kPa → Pa: × 1000
  return (gauge_kPa * 1000.0f) / (WATER_DENSITY * GRAVITY);
}

float SensorModule::rawToKPa(int16_t raw) {
  // ADS1115 at GAIN_ONE: 1 bit = 0.125 mV
  float voltage = raw * 0.125f / 1000.0f;  // volts
  // SEN0257: 0.5 V = 0 kPa, 4.5 V = SENSOR_MAX_KPA
  float kPa = (voltage - 0.5f) / 4.0f * SENSOR_MAX_KPA;
  if (kPa < 0) kPa = 0;
  return kPa;
}
