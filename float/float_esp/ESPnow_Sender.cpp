#include "ESPnow_Sender.h"

// MAC address
uint8_t receiverMAC[] = {0x80, 0xF3, 0xDA, 0x5D, 0xBA, 0x44};

volatile uint16_t ESPNowSender::_lastAckSeq = 0;
volatile bool ESPNowSender::_hasAck = false;

void ESPNowSender::init() {
  WiFi.mode(WIFI_STA);

  // Init ESP-NOW
  if (esp_now_init() != ESP_OK) {
    return;
  }

  esp_now_register_send_cb(onSent);
  esp_now_register_recv_cb(onReceive);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, receiverMAC, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    return;
  }
}

void ESPNowSender::send(const DataPacket& pkt) {
  esp_now_send(receiverMAC, (uint8_t *)&pkt, sizeof(pkt));
}

void ESPNowSender::resetAcks() {
  _hasAck = false;
}

bool ESPNowSender::hasAckFor(uint16_t seq) const {
  return _hasAck && _lastAckSeq == seq;
}

void ESPNowSender::onSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
}

void ESPNowSender::onReceive(const esp_now_recv_info *info, const uint8_t *data, int len) {
  if (len != sizeof(DataPacket)) return;

  DataPacket pkt;
  memcpy(&pkt, data, sizeof(pkt));
  if (pkt.msgType != PKT_ACK) return;

  _lastAckSeq = pkt.seq;
  _hasAck = true;
}