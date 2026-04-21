// ESPnow_sender.h
#pragma once

#include <WiFi.h>
#include <esp_now.h>
#include "packet.h"
#include <Arduino.h>

//MAC Address
//ESP32 1, (one with anntenna): 80:F3:DA:5D:BA:44
//ESP32 2: 84:1F:E8:1C:1A:80
extern uint8_t receiverMAC[6];

// extern DataPacket packet;

class ESPNowSender {
public:
  void init();
  void send(const DataPacket& pkt);
  void resetAcks();
  bool hasAckFor(uint16_t seq) const;

private:
  static void onSent(const wifi_tx_info_t *info, esp_now_send_status_t status);
  static void onReceive(const esp_now_recv_info *info, const uint8_t *data, int len);

  static volatile uint16_t _lastAckSeq;
  static volatile bool _hasAck;
};