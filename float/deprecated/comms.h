struct DataPacket {
    unsigned int company_num;
    unsigned int timestamp_ms;
    float pressure_kPa;
    float depth_m;
};

void commsInit();
void sendPacket(DataPacket p);
void broadcastStoredLog();