// Helper.h

#pragma once
#include <WiFi.h>
#include <Wire.h>

void printMAC() {
  Serial.begin(115200);
  delay(2000);
  WiFi.mode(WIFI_STA);
  delay(100);
  Serial.println("MAC Address:");
  Serial.println(WiFi.macAddress());
  // Receiver MAC: A4:CF:12:0A:7B:40
  // Sender MAC:   3C:71:BF:6F:57:48
}

void scanI2C() {
  Wire.begin(21, 22); // SDA=21, SCL=22
  Serial.println("Scanning I2C bus...");
  for (uint8_t addr = 8; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0)
      Serial.printf("Found device at 0x%02X\n", addr);
  }
  Serial.println("Scan complete.");
}