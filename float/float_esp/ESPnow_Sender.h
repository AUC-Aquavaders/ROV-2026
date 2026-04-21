// ESPnow_sender.h
#pragma once

#include <WiFi.h>
#include <esp_now.h>
#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include "packet.h"
#include <Arduino.h>

//MAC Address
//ESP32 1, (one with anntenna): 80:F3:DA:5D:BA:44
//ESP32 2: 84:1F:E8:1C:1A:80
extern uint8_t receiverMAC[6];

// extern DataPacket packet;

//Sensor Config
#define SENSOR_MAX_KPA  1600.0f  // SEN0257 rated 0–1.6 MPa
#define WATER_DENSITY   1000.0f  // kg/m³ — use 1025.0 for saltwater
#define GRAVITY         9.81f

// extern Adafruit_ADS1115 ads;

// //Function Declarations
// float readPressureKPA();
// void  onSent(const wifi_tx_info_t *info, esp_now_send_status_t status);
// void  senderSetup();
// void  senderLoop();

class ESPNowSender {
public:
  void init();
  void send(const DataPacket& pkt);
  void resetAcks();
  bool hasAckFor(uint16_t seq) const;

private:
  Adafruit_ADS1115 ads;

  float readPressureKPA();
  static void onSent(const wifi_tx_info_t *info, esp_now_send_status_t status);
  static void onReceive(const esp_now_recv_info *info, const uint8_t *data, int len);

  static volatile uint16_t _lastAckSeq;
  static volatile bool _hasAck;
};