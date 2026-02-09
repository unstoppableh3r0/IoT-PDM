# Smart IoT Predictive Maintenance System (PDM)

Industrial motor fault detection: **ESP32** → **MQTT** → **Python (ML + Gemini)** → **React Dashboard**.

## Structure

- **`firmware/`** – ESP32 C++ (PlatformIO): MPU6050, DS18B20, ACS712 → JSON to `iot/pdm/project/data`
- **`backend/`** – Python: train Random Forest, MQTT subscriber, Gemini explanation, publish to `iot/pdm/project/result`
- **`frontend/`** – React + Vite + Tailwind + Recharts: live vibration chart, status card, AI diagnosis
- **`data/`** – Place `ai4i2020.csv` here for training

## Quick Start

### 1. Data & model

- Download [AI4I 2020 Predictive Maintenance](https://archive.ics.uci.edu/ml/datasets/ai4i+2020+predictive+maintenance+dataset) and put `ai4i2020.csv` in `data/`.
- Backend:
  ```bash
  cd backend
  pip install -r requirements.txt
  python train_model.py
  ```
- Set `GEMINI_API_KEY` in the environment for explanations.

### 2. Backend server

```bash
cd backend
python server.py
```
- Press **`f` + Enter** to toggle **Fault Injection** (fake faulty data for demo).

### 3. Firmware (ESP32)

- In `firmware/src/main.cpp` set `WIFI_SSID` and `WIFI_PASSWORD`.
- Open in PlatformIO and upload. Sensors: MPU6050 (I2C), DS18B20 (GPIO4), ACS712 (GPIO34).

#### Arduino IDE — test without sensors (dummy data)

Use `firmware/pdm_test/` to upload from Arduino IDE with **no physical sensors**:

1. **Install ESP32 board support:** File → Preferences → Additional Boards Manager URLs → add  
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`  
   Then Tools → Board → Boards Manager → search "ESP32" → Install.

2. **Install libraries:** Sketch → Include Library → Manage Libraries → search and install:
   - **PubSubClient** (Nick O’Leary)
   - **ArduinoJson** (Benoit Blanchon)

3. **Open sketch:** File → Open → select `firmware/pdm_test/pdm_test.ino`.

4. **Configure WiFi:** In the sketch, set `WIFI_SSID` and `WIFI_PASSWORD`.

5. **Upload:** Tools → Board → ESP32 Dev Module, select correct Port → Upload.

6. **Monitor:** Tools → Serial Monitor (115200 baud). You should see "Published: {...}" every second. Backend and frontend will receive the dummy data.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173** in your browser. The dashboard shows placeholder data even without the backend or ESP32. It connects to `ws://broker.hivemq.com:8000/mqtt` for live data when available.

## Demo mode

- Backend: **`f` + Enter** toggles `FORCE_FAULT`; when ON, fake data `{vib: 45, temp: 85, amp: 5.5}` is used.
- Frontend: “DEMO MODE” badge appears when vibration is high (≥40) or static (same value repeated).
