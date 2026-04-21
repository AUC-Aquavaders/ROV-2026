// This ESP32 sits at the surface connected to the station laptop via USB.
// It receives DataPackets from the float over ESPNow and prints
// them to Serial.  On your PC, capture Serial output to a .txt
// file, then run:  python tools/grapher.py my_log.txt
//
// FIRST-TIME SETUP:
//   1. Set PRINT_MAC_ON_BOOT true in ESPNowReceiver.h
//   2. Flash and open Serial Monitor
//   3. Copy the printed MAC address
//   4. Paste it into float/ESPNowSender.h → STATION_MAC
//   5. Set PRINT_MAC_ON_BOOT back to false
// ═══════════════════════════════════════════════════════════════

#include "ESPNowReceiver.h"

void setup() {
  receiverSetup();
}

void loop() {
  // All work is done in the ESPNow receive callback.
  // Nothing needed here.
}
