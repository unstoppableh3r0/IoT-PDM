# PDM Hybrid Firmware - Arduino IDE Instructions

## 📋 Arduino IDE Setup

### 1. Install Arduino IDE
- Download from: https://www.arduino.cc/en/software
- Version 2.x recommended

### 2. Add ESP32 Board Support
1. Go to **File → Preferences**
2. Add to "Additional Board Manager URLs":
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Go to **Tools → Board → Boards Manager**
4. Search for "esp32" and install "esp32 by Espressif Systems"

### 3. Install Required Libraries
Go to **Sketch → Include Library → Manage Libraries** and install:
- **Adafruit MPU6050** (by Adafruit)
- **Adafruit Unified Sensor** (by Adafruit)
- **DallasTemperature** (by Miles Burton)
- **OneWire** (by Paul Stoffregen)
- **PubSubClient** (by Nick O'Leary)
- **ArduinoJson** (by Benoit Blanchon) - Version 6.x
- **LoRa** (by Sandeep Mistry)

### 4. Configure Board Settings
1. Connect ESP32 to computer via USB
2. Select board: **Tools → Board → ESP32 Arduino → ESP32 Dev Module**
3. Select port: **Tools → Port → COM[X]** (your ESP32 port)
4. Set upload speed: **Tools → Upload Speed → 115200**

### 5. Upload Firmware
1. Open `pdm_hybrid.ino` in Arduino IDE
2. Click **Upload** button (→) or press Ctrl+U
3. Wait for "Done uploading" message

### 6. Monitor Serial Output
1. Click **Serial Monitor** button or press Ctrl+Shift+M
2. Set baud rate to **115200**
3. You should see:
   ```
   --- Starting Smart IoT PDM Node ---
   SUCCESS: MPU6050 init successful!
   SUCCESS: DS18B20 Temp Sensor init successful!
   
   Initializing LoRa...
   ✅ LoRa Ready (PRIMARY communication)
   
   ✅ WiFi Connected (SECONDARY path)
   
   ===== HYBRID COMMUNICATION STATUS =====
   📡 LoRa:  ✅ READY
   📶 WiFi:  ✅ READY
   🔋 Mode:  HYBRID (LoRa + WiFi)
   =======================================
   
   📡 LoRa TX [78B]: {"id":"esp32_pdm_001","msg":1,"vib":9.8,"temp":25.3,"amp":0.15,"fault":0,"ts":5}
   📶 MQTT TX [95B]: published successfully
   Sensors: vib=9.8 m/s² | temp=25.3°C | amp=0.15A
   ```

## 🔧 Hardware Wiring

### LoRa SX1278 Module
- **SCK** → GPIO5
- **MISO** → GPIO19
- **MOSI** → GPIO27
- **CS** → GPIO18
- **RST** → GPIO14
- **DIO0** → GPIO26
- **VCC** → 3.3V
- **GND** → GND

### MPU6050 (Vibration Sensor)
- **SDA** → GPIO21 (default I2C)
- **SCL** → GPIO22 (default I2C)
- **VCC** → 3.3V
- **GND** → GND

### DS18B20 (Temperature Sensor)
- **Data** → GPIO14 (with 4.7kΩ pull-up resistor to 3.3V)
- **VCC** → 3.3V
- **GND** → GND

### ACS712 (Current Sensor)
- **OUT** → GPIO34 (ADC pin)
- **VCC** → 5V
- **GND** → GND

## 🧪 Testing

### Test LoRa Transmission
1. Upload `pdm_hybrid.ino` to ESP32
2. Use a second ESP32 with `lora_receiver_test.ino` (in `firmware/lora_test/`)
3. You should see LoRa packets being received

### Test WiFi/MQTT
1. Ensure WiFi credentials are correct in the sketch
2. Use MQTT client (like MQTT Explorer) to subscribe to: `iot/pdm/project/data`
3. You should see MQTT messages arriving

### Test Fault Detection
1. Trigger a fault by:
   - Shaking the device violently (vibration > 15 m/s²)
   - Heating the DS18B20 sensor (temp > 60°C)
2. Watch serial monitor for: `🚨 FAULT DETECTED!`
3. Check that the LoRa packet has `"fault":1`

## 🐛 Troubleshooting

### LoRa initialization fails
- Check wiring carefully (especially RST and DIO0)
- Verify LoRa module is 433 MHz version
- Try reflowing solder joints

### WiFi won't connect
- Verify SSID and password in sketch
- Check WiFi is 2.4 GHz (ESP32 doesn't support 5 GHz)
- Try moving closer to router

### MPU6050 not found
- Check I2C wiring (SDA/SCL)
- Verify MPU6050 address (default 0x68)
- Try different I2C pull-up resistors (4.7kΩ recommended)

### DS18B20 shows -127°C
- Check 4.7kΩ pull-up resistor on data line
- Verify sensor is DS18B20 (not DHT11/DHT22)
- Try different GPIO pin

## 📊 Expected Output

Every 2 seconds you should see:
```
📡 LoRa TX [78B]: {"id":"esp32_pdm_001","msg":15,"vib":9.8,"temp":25.3,"amp":0.15,"fault":0,"ts":30}
📶 MQTT TX [95B]: published successfully
Sensors: vib=9.8 m/s² | temp=25.3°C | amp=0.15A
```

**LoRa packet size**: ~60-80 bytes (optimized for long range)
**MQTT packet size**: ~90-100 bytes (includes metadata)

## 🔋 Power Consumption

- **Hybrid Mode**: ~240 mA (WiFi + LoRa)
- **LoRa-only Mode**: ~40 mA (WiFi disabled)
- **Deep Sleep** (future): ~10 µA

For battery operation, WiFi will fail to connect, and device will operate in low-power LoRa-only mode.
