#pragma once

#include "packet.h"

#define LOGGER_MAX_PACKETS 600

class DataLogger {
public:
  void log(const DataPacket& pkt);
  void replayAll(void (*callback)(const DataPacket&));
  void clear();

  uint16_t count() const;

private:
  DataPacket _buf[LOGGER_MAX_PACKETS];
  uint16_t   _count = 0;
};
