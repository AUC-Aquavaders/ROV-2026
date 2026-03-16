// ESPnow_receiver.h
#pragma once

#include <esp_now.h>
#include <WiFi.h>

//Data Packet
// Must match sender struct exactly
typedef struct {
  char companyNumber[10];  // e.g. "PN01"
  uint32_t floatTime;      // seconds since startup
  float pressure_kpa;      // in kilopascals
  float depth_m;           // in meters
} DataPacket;

extern DataPacket packet;

//Function Declarations
void onReceive(const esp_now_recv_info *info, const uint8_t *data, int len);
void receiverSetup();