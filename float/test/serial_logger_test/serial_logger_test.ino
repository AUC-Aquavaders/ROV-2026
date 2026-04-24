// test_serial_output.ino
// Simulates station ESP32 serial output for testing serial_logger.py and grapher.py
// Flash this to any ESP32, open serial_logger.py, then run grapher.py on the result.

#define COMPANY_ID "PN01"
#define BAUD_RATE 115200

uint32_t startMs = 0;
uint16_t seq = 1;

void setup() {
  Serial.begin(BAUD_RATE);
  delay(1000);
  startMs = millis();

  // Simulate PRE_COMM beacon
  Serial.printf("#READY,%s,0\n", COMPANY_ID);
  delay(500);
}

void loop() {
  uint32_t now = millis();
  uint32_t t = (now - startMs) / 1000;

  // Simulate a full two-profile dive
  // Profile 1: descend to 2.5m, hold, ascend to 0.4m, hold
  // Profile 2: same
  // Each phase lasts ~10 seconds in this test (not 30, so it runs fast)

  float depth;
  uint8_t profile;
  uint8_t state;

  if      (t < 10)  { depth = t * 0.25f;               profile = 1; state = 1; } // descending
  else if (t < 20)  { depth = 2.5f;                    profile = 1; state = 2; } // holding deep
  else if (t < 30)  { depth = 2.5f - (t-20) * 0.21f;  profile = 1; state = 3; } // ascending
  else if (t < 40)  { depth = 0.40f;                   profile = 1; state = 2; } // holding shallow
  else if (t < 50)  { depth = 0.40f + (t-40) * 0.21f; profile = 2; state = 1; } // descending p2
  else if (t < 60)  { depth = 2.5f;                    profile = 2; state = 2; } // holding deep p2
  else if (t < 70)  { depth = 2.5f - (t-60) * 0.21f;  profile = 2; state = 3; } // ascending p2
  else if (t < 80)  { depth = 0.40f;                   profile = 2; state = 2; } // holding shallow p2
  else if (t < 85)  { depth = 0.40f - (t-80) * 0.08f; profile = 2; state = 4; } // surfacing
  else              { depth = 0.0f;                    profile = 2; state = 4; } // at surface

  // Pressure from depth: P = surface + depth * rho * g / 1000
  float pressure = 101.325f + depth * 997.0f * 9.80665f / 1000.0f;

  // companyID,timestamp_s,profile,state,seq,pressure_kPa,depth_m
  Serial.printf("%s,%u,%u,%u,%u,%.3f,%.3f\n",
    COMPANY_ID, t, profile, state, seq++, pressure, depth);

  // Send DONE marker and stop after surfacing
  if (t >= 90) {
    Serial.printf("#DONE,%s,%u\n", COMPANY_ID, t);
    Serial.println("[test] Done. Reset ESP to run again.");
    while (true) delay(1000);
  }

  delay(1000); // one packet per second, same as real float
}