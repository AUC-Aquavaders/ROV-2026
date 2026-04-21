// ESPnow_receiver.cpp
#include "ESPnow_Receiver.h"

//Globals
DataPacket packet;

//Receive Callback
void onReceive(const esp_now_recv_info *info, const uint8_t *data, int len) {
  if (len != sizeof(DataPacket)) {
    Serial.println("Received packet with wrong size!");
    return;
  }
  memcpy(&packet, data, sizeof(packet));

//   // Format time as HH:MM:SS
//   uint32_t h = packet.floatTime / 3600;
//   uint32_t m = (packet.floatTime % 3600) / 60;
//   uint32_t s = packet.floatTime % 60;

//   // Print in MATE required format
//   Serial.printf("%s %02d:%02d:%02d %.2f kPa %.2f meters\n",
//                 packet.companyNumber, h, m, s,
//                 packet.pressure_kpa, packet.depth_m);

uint32_t h = packet.timestamp_s / 3600;
uint32_t m = (packet.timestamp_s % 3600) / 60;
uint32_t s = packet.timestamp_s % 60;

Serial.printf("%s %02d:%02d:%02d %.2f kPa %.2f meters\n",
  packet.companyID, h, m, s,
  packet.pressure_kPa, packet.depth_m);
  
}

//Setup
void receiverSetup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);

  if (PRINT_MAC_ON_BOOT) {
    Serial.print("MAC: ");
    Serial.println(WiFi.macAddress());
  }
  
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESPNow init failed!");
    return;
  }


  esp_now_register_recv_cb(onReceive);
  Serial.println("Receiver ready, waiting for data...");
}