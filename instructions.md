# Instructions — Smart IoT Predictive Maintenance System

This guide walks you through setting up and running every component of the project: **ML model training**, **backend server**, **ESP32 firmware**, and **React frontend dashboard**.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | 3.9+ | Backend server & ML training |
| **Node.js** | 18+ | Frontend dashboard |
| **npm** | 9+ | Frontend package manager |
| **PlatformIO** or **Arduino IDE** | Latest | ESP32 firmware upload |
| **Git** | Latest | Clone the repository |

---

## 1. Clone the Repository

```bash
git clone https://github.com/unstoppableh3r0/IoT-PDM.git
cd IoT-PDM
```

---

## 2. Prepare the Dataset

1. Download the **AI4I 2020 Predictive Maintenance** dataset from:  
   <https://archive.ics.uci.edu/ml/datasets/ai4i+2020+predictive+maintenance+dataset>
2. Place the file `ai4i2020.csv` inside the `data/` folder so the path is:
   ```
   data/ai4i2020.csv
   ```

---

## 3. Backend Setup (Python)

### 3.1 Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

The key packages installed are:
- `paho-mqtt` — MQTT client
- `scikit-learn` / `pandas` / `joblib` — ML training & inference
- `google-generativeai` — Gemini API for AI explanations

### 3.2 Train the ML model

```bash
python train_model.py
```

This trains a **Random Forest** classifier on the AI4I dataset and saves the model as `backend/pdm_model.pkl`. You should see accuracy metrics printed to the console.

### 3.3 Set the Gemini API key (optional but recommended)

The backend uses Google Gemini to generate human-readable fault explanations. Set the environment variable before starting the server:

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY = "your-api-key-here"
```

**Windows (CMD):**
```cmd
set GEMINI_API_KEY=your-api-key-here
```

**Linux / macOS:**
```bash
export GEMINI_API_KEY="your-api-key-here"
```

> If the key is not set, the system still works but explanations will show "Explanation unavailable."

### 3.4 Start the backend server

```bash
python server.py
```

- The server connects to the public MQTT broker (`broker.mqttdashboard.com:8000`).
- It subscribes to `iot/pdm/project/data`, runs ML inference on incoming sensor data, calls Gemini for an explanation, and publishes results to `iot/pdm/project/result`.
- **Demo mode:** Press **`f` + Enter** in the terminal to toggle **Fault Injection** — the server will use fake faulty data (`vib: 45, temp: 85`) for testing without hardware.

---

## 4. Firmware Setup (ESP32)

You have two options depending on whether you have physical sensors.

### Option A — Full firmware with sensors (PlatformIO)

**Hardware required:** ESP32, MPU6050 (vibration), DS18B20 (temperature on GPIO14), ACS712 (current on GPIO34).

1. Open the `firmware/` folder in **VS Code with PlatformIO** extension installed.
2. Edit `firmware/src/main.cpp` and set your Wi-Fi credentials:
   ```cpp
   const char* WIFI_SSID     = "your-wifi-ssid";
   const char* WIFI_PASSWORD = "your-wifi-password";
   ```
3. Connect the ESP32 via USB.
4. Build and upload:
   ```bash
   pio run --target upload
   ```
5. Open the serial monitor (115200 baud) to verify it publishes JSON to the MQTT topic every second.

### Option B — Dummy-data test sketch (Arduino IDE, no sensors needed)

Use `firmware/pdm_test/pdm_test.ino` to run without physical sensors — it sends random simulated data.

1. **Install ESP32 board support:**  
   File → Preferences → Additional Boards Manager URLs → add:  
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```  
   Then: Tools → Board → Boards Manager → search **ESP32** → Install.

2. **Install required libraries** (Sketch → Include Library → Manage Libraries):
   - **PubSubClient** (Nick O'Leary)
   - **ArduinoJson** (Benoit Blanchon)

3. **Open the sketch:** File → Open → select `firmware/pdm_test/pdm_test.ino`.

4. **Set Wi-Fi credentials** in the sketch:
   ```cpp
   const char* WIFI_SSID     = "your-wifi-ssid";
   const char* WIFI_PASSWORD = "your-wifi-password";
   ```

5. **Upload:** Tools → Board → **ESP32 Dev Module** → select correct Port → Upload.

6. **Verify:** Open Serial Monitor at **115200 baud**. You should see `Published: {...}` every second.

---

## 5. Frontend Setup (React Dashboard)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

- The dashboard connects to `ws://broker.hivemq.com:8000/mqtt` for live MQTT data.
- It displays a **vibration chart**, **status card**, and **AI diagnosis** in real time.
- A **"DEMO MODE"** badge appears when vibration is unusually high (≥ 40) or static (same value repeated), indicating simulated data.
- The dashboard shows placeholder data even if the backend/ESP32 are not running yet.

---

## 6. Full System Run Order

For the complete end-to-end flow, start components in this order:

| Step | Command | Directory |
|------|---------|-----------|
| 1 | `python train_model.py` | `backend/` |
| 2 | `python server.py` | `backend/` |
| 3 | Upload firmware to ESP32 | `firmware/` |
| 4 | `npm run dev` | `frontend/` |

Once all components are running:
1. The **ESP32** reads sensors (or generates dummy data) and publishes to `iot/pdm/project/data`.
2. The **backend** receives the data, predicts Healthy/Faulty, generates an AI explanation, and publishes to `iot/pdm/project/result`.
3. The **frontend** subscribes to the result topic and updates the dashboard in real time.

---

## 7. Troubleshooting

| Problem | Solution |
|---------|----------|
| `Model not found` error | Run `python train_model.py` first |
| `Dataset not found` error | Ensure `data/ai4i2020.csv` exists |
| Backend can't connect to MQTT | Check internet connection; the public broker may be temporarily down |
| ESP32 won't connect to Wi-Fi | Double-check SSID/password in the firmware source |
| Frontend shows no live data | Ensure the backend is running and connected to the same MQTT broker |
| Gemini explanation says "unavailable" | Set the `GEMINI_API_KEY` environment variable |
| `pip install` fails | Try `pip install --upgrade pip` first, or use a virtual environment |

---

## Project Architecture

```
ESP32 (sensors)               Backend (Python)              Frontend (React)
┌──────────────┐   MQTT    ┌─────────────────┐   MQTT    ┌──────────────────┐
│ MPU6050      │──────────►│ MQTT Subscriber  │──────────►│ Live Dashboard   │
│ DS18B20      │  topic:   │ ML Inference     │  topic:   │ Vibration Chart  │
│ ACS712       │  /data    │ Gemini Explain   │  /result  │ AI Diagnosis     │
└──────────────┘           └─────────────────┘           └──────────────────┘
```
