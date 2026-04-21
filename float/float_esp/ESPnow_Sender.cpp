#include "ESPnow_Sender.h"

// MAC address
uint8_t receiverMAC[] = {0x80, 0xF3, 0xDA, 0x5D, 0xBA, 0x44};

void ESPNowSender::init() {
  Serial.println("[ESP-NOW] Init...");

  Wire.begin(21, 22);
  WiFi.mode(WIFI_STA);

  // Init ADS1115
  if (!ads.begin(0x48)) {
    Serial.println("ADS1115 not found!");
    while (1);
  }
  ads.setGain(GAIN_ONE);

  // Init ESP-NOW
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

  Serial.println("[ESP-NOW] Ready.");
}

void ESPNowSender::send(const DataPacket& pkt) {
  esp_now_send(receiverMAC, (uint8_t *)&pkt, sizeof(pkt));

  uint32_t h = pkt.timestamp_s / 3600;
  uint32_t m = (pkt.timestamp_s % 3600) / 60;
  uint32_t s = pkt.timestamp_s % 60;

  Serial.printf("Sending: %s %02lu:%02lu:%02lu %.2f kPa %.2f m\n",
                pkt.companyID, h, m, s,
                pkt.pressure_kPa, pkt.depth_m);
}

float ESPNowSender::readPressureKPA() {
  long sum = 0;
  for (int i = 0; i < 64; i++) {
    sum += ads.readADC_SingleEnded(0);
    delay(1);
  }

  int16_t raw = sum / 64;
  float voltage = raw * 0.125f / 1000.0f;

  float pressure = (voltage / 3.3f) * SENSOR_MAX_KPA;
  if (pressure < 0) pressure = 0;

  return pressure;
}

void ESPNowSender::onSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  Serial.print("Send Status: ");
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Success" : "Failed");
}