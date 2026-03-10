# LoRa-MQTT Gateway for IoT-PDM

## Overview
This ESP32 gateway receives LoRa packets from remote PDM sensors and forwards them to the MQTT broker, enabling long-range, low-power communication while maintaining cloud connectivity.

## Hardware Requirements
- **ESP32 Dev Module**
- **SX1278 LoRa Module (433 MHz)**
- **Wiring** (same as sensor node):
  - SCK → GPIO5
  - MISO → GPIO19
  - MOSI → GPIO27
  - CS → GPIO18
  - RST → GPIO14
  - DIO0 → GPIO26
  - VCC → 3.3V
  - GND → GND

## Installation (Arduino IDE)

### 1. Install Libraries
Go to **Sketch → Include Library → Manage Libraries** and install:
- LoRa by Sandeep Mistry
- PubSubClient by Nick O'Leary
- ArduinoJson by Benoit Blanchon

### 2. Configure WiFi Credentials
Edit in `lora_mqtt_gateway.ino`:
```cpp
const char* WIFI_SSID     = "your_wifi_ssid";
const char* WIFI_PASSWORD = "your_wifi_password";
```

### 3. Upload to ESP32
1. Select **Tools → Board → ESP32 Dev Module**
2. Select your ESP32's COM port
3. Click **Upload**
4. Open **Serial Monitor** at 115200 baud

## Expected Serial Output
```
╔════════════════════════════════════════╗
║  LoRa to MQTT Gateway - Starting...   ║
╚════════════════════════════════════════╝

✅ WiFi Connected!
   IP Address: 192.168.1.100
   SSID: your_network

✅ MQTT Connected!

✅ LoRa receiver ready!
   Frequency: 433.0 MHz
   SF: 7

╔════════════════════════════════════════╗
║     Gateway Ready - Listening...      ║
╚════════════════════════════════════════╝

📡 LoRa Packet Received!
   Size: 78 bytes
   RSSI: -45 dBm
   SNR:  9.5 dB
   Data: {"id":"esp32_pdm_001","msg":1,"vib":9.8,"temp":25.3,"amp":0.15,"fault":0,"ts":5}
📤 Forwarded to MQTT [152B]
```

## Message Flow
1. **Sensor Node** → Transmits via LoRa (60-80 bytes, low power)
2. **Gateway** → Receives LoRa packet
3. **Gateway** → Enriches with signal quality (RSSI, SNR, source="lora")
4. **Gateway** → Publishes to MQTT broker
5. **Backend** → Processes enriched message
6. **Frontend** → Displays with LoRa indicator

## Enriched MQTT Payload
The gateway adds metadata to forwarded messages:
```json
{
  "vib": 9.8,
  "temp": 25.3,
  "amp": 0.15,
  "fault": 0,
  "ts": 5,
  "source": "lora",          // NEW: Indicates LoRa origin
  "gateway": "gateway_001",   // NEW: Gateway identifier
  "node_id": "esp32_pdm_001", // NEW: Original sensor node
  "msg_num": 1,               // NEW: Message counter
  "rssi": -45,                // NEW: Signal strength
  "snr": 9.5                  // NEW: Signal quality
}
```

## Statistics
The gateway prints statistics every 30 seconds:
```
========== GATEWAY STATISTICS ==========
Packets Received:  120
Packets Forwarded: 118
Packets Failed:    2
Success Rate:      98.33%
========================================
```

## Troubleshooting

### Gateway can't receive LoRa packets
- Verify LoRa wiring matches sensor node
- Check that frequency matches (433 MHz)
- Ensure spreading factor matches (SF=7)
- Test with `lora_sender_test.ino` first

### MQTT publish fails
- Check WiFi credentials
- Verify MQTT broker is accessible: `broker.hivemq.com:1883`
- Check MQTT topic matches backend subscription
- Increase buffer size if packets are large

### JSON parse errors
- Ensure sensor node sends valid JSON
- Check packet size isn't truncated
- Verify ArduinoJson library is v6.x

### Poor RSSI/SNR values
- Move gateway closer to sensor node
- Improve antenna positioning (vertical, clear line-of-sight)
- Check for interference (metal obstacles, other radios)
- Consider higher TX power or different spreading factor

## Deployment

### Indoor Deployment
- Place gateway near WiFi router for reliable internet
- Position antenna vertically
- Avoid metal enclosures that block LoRa signals
- RSSI should be > -100 dBm for reliable reception

### Power Options
1. **USB Power**: Plug into computer or USB adapter
2. **Battery + Solar**: For outdoor deployment (requires power management)
3. **PoE Adapter**: For permanent installation

## Range Testing
Expected range with this configuration:
- **Indoor**: 500m - 1km
- **Urban**: 2-5 km
- **Suburban**: 5-10 km
- **Rural (line-of-sight)**: 10-15+ km

To test range:
1. Deploy sensor node on battery
2. Walk away from gateway with laptop showing Serial Monitor
3. Note RSSI values at different distances
4. Packet loss should stay < 5% within operating range

## Multiple Gateways
To deploy multiple gateways for better coverage:
1. Change `MQTT_CLIENT_ID` to unique value (e.g., "gateway_002")
2. Update `gateway` field in code to match client ID
3. Deploy at different locations
4. Backend will receive packets from all gateways
5. Use RSSI/SNR to determine best gateway for each sensor
