#include "MockESPnow_Sender.h"
#include <Arduino.h>
// MAC address
uint8_t receiverMAC[] = {0x80, 0xF3, 0xDA, 0x5D, 0xBA, 0x44};

void MockESPNowSender::init() {
  // Mock: do nothing
}

void MockESPNowSender::send(const DataPacket& pkt) {
  // Mock: simulate sending, record time and seq for ack simulation
  lastSendTime = millis();
  lastSeq = pkt.seq;
  // Perhaps print for debugging
  // Serial.println("Mock send packet seq: " + String(pkt.seq));
}

void MockESPNowSender::resetAcks() {
  lastSeq = 0;
}

bool MockESPNowSender::hasAckFor(uint16_t seq) const {
  // Mock: simulate ack after 1 second
  if (seq == lastSeq && millis() - lastSendTime > 1000) {
    return true;
  }
  return false;
}