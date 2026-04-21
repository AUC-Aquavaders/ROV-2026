// ESPnow_receiver.h
#pragma once

#include <esp_now.h>
#include <WiFi.h>
#include "packet.h"
#include <Arduino.h>

// Set true once to print this ESP's MAC address, then set false.
#define PRINT_MAC_ON_BOOT  false

extern DataPacket packet;

//Function Declarations
void onReceive(const esp_now_recv_info *info, const uint8_t *data, int len);
void receiverSetup();

// Send ACK back to the float
bool ensurePeer(const uint8_t mac[6]);
void sendAck(const uint8_t mac[6], uint16_t seqToAck);