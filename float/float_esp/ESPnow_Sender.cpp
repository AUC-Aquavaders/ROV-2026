// ESPnow_sender.cpp
#include "ESPnow_Sender.h"

//Globals
uint8_t receiverMAC[] = {0x80, 0xF3, 0xDA, 0x5D, 0xBA, 0x44};
DataPacket packet;
Adafruit_ADS1115 ads;

//Pressure Reading
float readPressureKPA() {
  // Average 64 samples to smooth ADS1115 ADC noise
  long sum = 0;
  for (int i = 0; i < 64; i++) {
    sum += ads.readADC_SingleEnded(0);  // Channel A0
    delay(1);
  }
  int16_t raw = sum / 64;

  // GAIN_ONE = 0.125 mV per count → divide by 1000 to get volts
  float voltage = raw * 0.125f / 1000.0f;

  // 0V = 0 pressure, 3.3V = SENSOR_MAX_KPA (linear)
  float pressure = (voltage / 3.3f) * SENSOR_MAX_KPA;

  if (pressure < 0) pressure = 0;
  return pressure;
}

//ESP-NOW Send Callback
void onSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  Serial.print("Send Status: ");
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Success" : "Failed");
}

//Setup
void senderSetup() {
  Serial.begin(115200);
  Wire.begin(21, 22);  // SDA=21, SCL=22
  WiFi.mode(WIFI_STA);

  strcpy(packet.companyNumber, "PN01");  // Update when assigned by MATE

  // Init ADS1115
  if (!ads.begin(0x48)) {  // Confirm address with electronics team if needed
    Serial.println("ADS1115 not found! Check wiring or run I2C scanner in Helper.h");
    while (1);
  }
  ads.setGain(GAIN_ONE);  // ±4.096V range — correct for 0–3.3V signal
  Serial.println("ADS1115 ready.");

  // Init ESP-NOW
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESPNow init failed!");
    return;
  }

  esp_now_register_send_cb(onSent);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, receiverMAC, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Failed to add peer!");
    return;
  }
}

//Loop
void senderLoop() {
  packet.floatTime    = millis() / 1000;
  packet.pressure_kpa = readPressureKPA();
  packet.depth_m      = (packet.pressure_kpa * 1000.0f) / (WATER_DENSITY * GRAVITY);

  esp_now_send(receiverMAC, (uint8_t *)&packet, sizeof(packet));

  uint32_t h = packet.floatTime / 3600;
  uint32_t m = (packet.floatTime % 3600) / 60;
  uint32_t s = packet.floatTime % 60;
  Serial.printf("Sending: %s %02d:%02d:%02d %.2f kPa %.2f meters\n",
                packet.companyNumber, h, m, s,
                packet.pressure_kpa, packet.depth_m);

  delay(2000);  // Send every 2 seconds
}