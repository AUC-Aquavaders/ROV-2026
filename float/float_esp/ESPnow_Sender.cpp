#include "ESPnow_Sender.h"

// MAC address
uint8_t receiverMAC[] = {0x80, 0xF3, 0xDA, 0x5D, 0xBA, 0x44};

volatile uint16_t ESPNowSender::_lastAckSeq = 0;
volatile bool ESPNowSender::_hasAck = false;

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
  esp_now_register_recv_cb(onReceive);

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

  Serial.printf("[TX] type=%u seq=%u t=%lus p=%.2fkPa d=%.3fm prof=%u state=%u\n",
                (unsigned)pkt.msgType, (unsigned)pkt.seq,
                (unsigned long)pkt.timestamp_s,
                pkt.pressure_kPa, pkt.depth_m,
                (unsigned)pkt.profileNum, (unsigned)pkt.state);
}

void ESPNowSender::resetAcks() {
  _hasAck = false;
}

bool ESPNowSender::hasAckFor(uint16_t seq) const {
  return _hasAck && _lastAckSeq == seq;
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

void ESPNowSender::onReceive(const esp_now_recv_info *info, const uint8_t *data, int len) {
  if (len != sizeof(DataPacket)) return;

  DataPacket pkt;
  memcpy(&pkt, data, sizeof(pkt));
  if (pkt.msgType != PKT_ACK) return;

  _lastAckSeq = pkt.seq;
  _hasAck = true;
}