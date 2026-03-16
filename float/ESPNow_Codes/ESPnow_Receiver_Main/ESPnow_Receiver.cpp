// ESPnow_receiver.cpp
#include "ESPnow_Receiver.h"

//Globals
DataPacket packet;

//Receive Callback
void onReceive(const esp_now_recv_info *info, const uint8_t *data, int len) {
  memcpy(&packet, data, sizeof(packet));

  // Format time as HH:MM:SS
  uint32_t h = packet.floatTime / 3600;
  uint32_t m = (packet.floatTime % 3600) / 60;
  uint32_t s = packet.floatTime % 60;

  // Print in MATE required format
  Serial.printf("%s %02d:%02d:%02d %.2f kPa %.2f meters\n",
                packet.companyNumber, h, m, s,
                packet.pressure_kpa, packet.depth_m);
}

//Setup
void receiverSetup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESPNow init failed!");
    return;
  }

  esp_now_register_recv_cb(onReceive);
  Serial.println("Receiver ready, waiting for data...");
}