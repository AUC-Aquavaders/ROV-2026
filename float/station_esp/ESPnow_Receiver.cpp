// ESPnow_receiver.cpp
#include "ESPnow_Receiver.h"
#include <string.h>

//Globals
DataPacket packet;

static bool ensurePeerImpl(const uint8_t mac[6]) {
  if (esp_now_is_peer_exist(mac)) return true;

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, mac, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;
  return esp_now_add_peer(&peerInfo) == ESP_OK;
}

bool ensurePeer(const uint8_t mac[6]) {
  return ensurePeerImpl(mac);
}

void sendAck(const uint8_t mac[6], uint16_t seqToAck) {
  if (!ensurePeer(mac)) {
    Serial.println("#WARN,peer_add_failed");
    return;
  }

  DataPacket ack = {};
  strncpy(ack.companyID, COMPANY_ID, sizeof(ack.companyID) - 1);
  ack.companyID[sizeof(ack.companyID) - 1] = '\0';
  ack.msgType = PKT_ACK;
  ack.seq = seqToAck;
  ack.timestamp_s = millis() / 1000;
  ack.pressure_kPa = 0;
  ack.depth_m = 0;
  ack.profileNum = 0;
  ack.state = 0;

  esp_now_send(mac, (uint8_t *)&ack, sizeof(ack));
  Serial.println("#Ack packet sent to float");
}

//Receive Callback
void onReceive(const esp_now_recv_info *info, const uint8_t *data, int len) {
  if (len != sizeof(DataPacket)) {
    Serial.println("#ERR,bad_len");
    return;
  }
  memcpy(&packet, data, sizeof(packet));

  const uint8_t *src = info->src_addr;

  // Always ACK READY/DATA/DONE so float can proceed/retry
  if (packet.msgType == PKT_READY || packet.msgType == PKT_DATA || packet.msgType == PKT_DONE) {
    sendAck(src, packet.seq);
  }

  if (packet.msgType == PKT_READY) {
    Serial.printf("#READY,%s,%u\n", packet.companyID, (unsigned)packet.timestamp_s);
    return;
  }

  if (packet.msgType == PKT_DONE) {
    Serial.printf("#DONE,%s,%u\n", packet.companyID, (unsigned)packet.timestamp_s);
    return;
  }

  if (packet.msgType != PKT_DATA) {
    Serial.println("#ERR,unknown_type");
    return;
  }

  // Strict CSV output for deterministic logging/graphing.
  // companyID,timestamp_s,profile,state,seq,pressure_kPa,depth_m
  Serial.printf("%s,%u,%u,%u,%u,%.3f,%.3f\n",
                packet.companyID,
                (unsigned)packet.timestamp_s,
                (unsigned)packet.profileNum,
                (unsigned)packet.state,
                (unsigned)packet.seq,
                packet.pressure_kPa,
                packet.depth_m);
}

//Setup
void receiverSetup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);

  if (PRINT_MAC_ON_BOOT) {
    Serial.print("MAC: ");
    Serial.println(WiFi.macAddress());
  }
  
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESPNow init failed!");
    return;
  }


  esp_now_register_recv_cb(onReceive);
  Serial.println("#STATION,ready");
}