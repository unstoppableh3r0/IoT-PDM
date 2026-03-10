# LoRa-to-Backend Gateway for IoT-PDM

## Overview
This ESP32 gateway receives LoRa packets from remote PDM sensors and forwards them to the **local backend via HTTP**. The backend processes data locally (20-50ms latency) and publishes only **results** to MQTT cloud.

## Architecture
```
ESP32 Sensor → LoRa (1s, 60B) → Gateway → HTTP (local, 20-50ms) → Backend
                                                                      ↓
                                                               ML Processing
                                                                      ↓
                                                          MQTT (results only, 80B)
                                                                      ↓
                                                               Cloud Dashboard
```

### Key Benefits
- **Low Latency**: 20-50ms local processing (vs 100-300ms cloud MQTT)
- **Offline Capable**: Works without internet connection
- **Reduced Bandwidth**: Raw data stays local, only alerts go to cloud
- **Real-time**: Critical fault detection happens locally

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
Install from **Tools → Manage Libraries**:
- **LoRa** by Sandeep Mistry
- **ArduinoJson** by Benoit Blanchon
- **HTTPClient** (built-in with ESP32)

### 2. Configure WiFi Credentials
Edit in `lora_mqtt_gateway.ino`:
```cpp
const char* WIFI_SSID     = "your_wifi_ssid";
const char* WIFI_PASSWORD = "your_wifi_password";
```

### 3. Configure Backend Server
Edit the backend host IP:
```cpp
const char* BACKEND_HOST = "192.168.1.100";  // IP of laptop running backend
const int   BACKEND_PORT = 5000;
```

### 4. Upload to ESP32
1. Select **Tools → Board → ESP32 Dev Module**
2. Select your ESP32's COM port
3. Click **Upload**
4. Open **Serial Monitor** at 115200 baud

## Expected Serial Output
```
╔════════════════════════════════════════╗
║  LoRa to Backend Gateway - Starting    ║
╚════════════════════════════════════════╝

✅ WiFi Connected!
   IP Address: 192.168.1.100
   SSID: your_network

✅ Backend Connection: http://192.168.1.100:5000/api/lora/data

✅ LoRa receiver ready!
   Frequency: 433.0 MHz
   SF: 7

╔════════════════════════════════════════╗
║  Gateway Ready - Forwarding Local...  ║
╚════════════════════════════════════════╝

📡 LoRa Packet Received!
   Size: 78 bytes
   RSSI: -45 dBm
   SNR:  9.5 dB
   Data: {"id":"esp32_pdm_001","msg":1,"vib":9.8,"temp":25.3,"amp":0.15,"fault":0,"ts":5}
📤 Forwarded to Backend via HTTP [200 OK]
```

## Message Flow
1. **Sensor Node** → Transmits via LoRa (60-80 bytes, low power)
2. **Gateway** → Receives LoRa packet
3. **Gateway** → Enriches with signal quality (RSSI, SNR, source="lora")
4. **Gateway** → POSTs to local backend via HTTP (20-50ms)
5. **Backend** → Runs ML inference locally
6. **Backend** → Publishes only **results** to MQTT cloud
7. **Frontend** → Receives analysis from MQTT

## HTTP Payload Format
Gateway POSTs JSON to `http://BACKEND_HOST:5000/api/lora/data`:
```json
{
  "vib": 9.8,
  "temp": 25.3,
  "amp": 0.15,
  "fault": 0,
  "ts": 5,
  "source": "lora",
  "gateway": "gateway_001",
  "node_id": "esp32_pdm_001",
  "msg_num": 1,
  "rssi": -45,
  "snr": 9.5
}
```

Backend processes this locally and publishes results (prediction, health score, RUL) to MQTT.

## Statistics
The gateway prints statistics every 30 seconds:
```
========== GATEWAY STATISTICS ==========
Packets Received:  120
Packets Forwarded: 118 (HTTP 200)
Packets Failed:    2
Success Rate:      98.3%
Average RSSI:      -47 dBm
Average SNR:       8.2 dB
========================================
```

## Troubleshooting

### Connection Failed
- Verify backend is running: `python backend/server.py`
- Check backend IP matches `BACKEND_HOST`
- Ensure both devices on same network
- Test with: `curl http://192.168.1.100:5000/api/lora/data -X POST -H "Content-Type: application/json" -d "{}"`

### "HTTP POST failed"
- Backend Flask server not running
- Firewall blocking port 5000
- Wrong BACKEND_HOST IP address

### High Latency (>100ms)
- Check WiFi signal strength
- Verify backend on same local network (not cloud)
- Use `ping 192.168.1.100` to test network latency

## Comparison: HTTP vs MQTT

| Feature | HTTP (Local) | MQTT (Cloud) |
|---------|--------------|--------------|
| Latency | 20-50ms | 100-300ms |
| Offline | ✅ Works | ❌ Requires internet |
| Bandwidth | 60B/sec | 60B/sec + 80B/alert |
| Use Case | Raw sensor data | Results & alerts |
| Reliability | Local network | Internet dependent |
| Processing | Backend (immediate) | Cloud (delayed) |

## Integration with Backend
The backend `server.py` now:
1. Runs Flask HTTP server on port 5000
2. Receives LoRa data via `POST /api/lora/data`
3. Processes with ML model locally
4. Publishes only results to MQTT (not raw data)

This architecture ensures critical fault detection happens with minimal latency while still providing cloud dashboard access to analysis results.
