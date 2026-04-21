#include "DataLogger.h"
// Data logger to log data in a buffer while float is underwater
// Stores DataPackets in RAM during the dive.
// After recovery, replayAll() hands each packet back for transmission.


void DataLogger::log(const DataPacket& pkt) {
  if (_count >= LOGGER_MAX_PACKETS) {
    return;
  }
  _buf[_count++] = pkt;
}

void DataLogger::replayAll(void (*callback)(const DataPacket&)) {
  for (uint16_t i = 0; i < _count; i++) {
    callback(_buf[i]);
    delay(10);   // brief gap so receiver isn't overwhelmed
  }
}

void DataLogger::clear() {
  _count = 0;
}

uint16_t DataLogger::count() const {
  return _count;
}

const DataPacket& DataLogger::at(uint16_t idx) const {
  // Caller must bounds-check; keep lightweight for embedded.
  return _buf[idx];
}
