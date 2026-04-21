#pragma once
#include <stdint.h> 
// IF U CHANGE ANYTHING HERE CHANGE PACKET.H ON OTHER SIDE

#define COMPANY_ID "PN01"  
// TODO: review packet structure

enum PacketType : uint8_t {
  PKT_READY = 0,  // float -> station before dive / at surface
  PKT_DATA  = 1,  // float -> station data record
  PKT_ACK   = 2,  // station -> float ack for seq
  PKT_DONE  = 3   // float -> station end-of-transmission marker
};

typedef struct {
  char     companyID[8];    // e.g. "PN01"
  uint8_t  msgType;         // PacketType
  uint8_t  reserved0;       // alignment / future flags
  uint16_t seq;             // sequence number (DATA/READY/DONE). ACK uses this field too.
  uint32_t timestamp_s;     // seconds since float powered on
  float    pressure_kPa;    // absolute pressure in kPa
  float    depth_m;         // calculated depth in meters
  uint8_t  profileNum;      // 1 or 2
  uint8_t  state;           // encodes which phase of the dive (for debugging)
} DataPacket;
