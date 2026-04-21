#pragma once
#include <stdint.h> 

#define COMPANY_ID "PN01"  
// TODO: review packet structure
typedef struct {
  char     companyID[8];    // e.g. "PN01"
  uint32_t timestamp_s;     // seconds since float powered on
  float    pressure_kPa;    // absolute pressure in kPa
  float    depth_m;         // calculated depth in meters
  uint8_t  profileNum;      // 1 or 2
  uint8_t  state;           // encodes which phase of the dive (for debugging)
} DataPacket;
