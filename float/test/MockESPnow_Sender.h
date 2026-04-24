// MockESPnow_sender.h
#pragma once

#include "packet.h"
#include <ctime>
//MAC Address
//ESP32 1, (one with anntenna): 80:F3:DA:5D:BA:44
//ESP32 2: 84:1F:E8:1C:1A:80
extern uint8_t receiverMAC[6];

// extern DataPacket packet;

class MockESPNowSender {
public:
  void init();
  void send(const DataPacket& pkt);
  void resetAcks();
  bool hasAckFor(uint16_t seq) const;

private:
  uint32_t lastSendTime = 0;
  uint16_t lastSeq = 0;
};