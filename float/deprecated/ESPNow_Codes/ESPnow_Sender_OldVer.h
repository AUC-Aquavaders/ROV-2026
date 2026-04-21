#include <WiFi.h>
#include <esp_now.h>
//Receiver MAC Address:
//A4:CF:12:0A:7B:40

// Sender MAC Address:
// 3C:71:BF:6F:57:48

// // //To find ESP32 Mac Address
// void setup() {
//   Serial.begin(115200);
//   delay(1000);
//   WiFi.mode(WIFI_STA);
//   delay(100);
//   Serial.println("Receiver MAC Address:");
//   Serial.println(WiFi.macAddress());
// }

//Sender Code
// === CHANGE THIS to the receiver's MAC address ===
uint8_t receiverMAC[] = {0xA4, 0xCF, 0x12, 0x0A, 0x7B, 0x40};

// Data packet structure
typedef struct {
  char companyNumber[10];  // e.g. "PN01"
  uint32_t floatTime;      // seconds since startup
  float pressure_kpa;      // in kilopascals
  float depth_m;           // in meters
} DataPacket;

DataPacket packet;

void onSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  Serial.print("Send Status: ");
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Success" : "Failed");
}


void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);

  // Set company number (change when you get it from MATE)
  strcpy(packet.companyNumber, "PN01");

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESPNow init failed!");
    return;
  }

  esp_now_register_send_cb(onSent);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, receiverMAC, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Failed to add peer!");
    return;
  }
}

void loop() {
  // Time since startup in seconds
  packet.floatTime = millis() / 1000;

  // === REPLACE THESE with real sensor readings later ===
  packet.pressure_kpa = 9.8;   // placeholder
  packet.depth_m = 1.00;       // placeholder

  // Send packet
  esp_now_send(receiverMAC, (uint8_t *)&packet, sizeof(packet));

  // Print what we're sending
  uint32_t h = packet.floatTime / 3600;
  uint32_t m = (packet.floatTime % 3600) / 60;
  uint32_t s = packet.floatTime % 60;
  Serial.printf("Sending: %s %02d:%02d:%02d %.2f kPa %.2f meters\n",
                packet.companyNumber, h, m, s,
                packet.pressure_kpa, packet.depth_m);

  delay(2000); // Send every 2 seconds
}
