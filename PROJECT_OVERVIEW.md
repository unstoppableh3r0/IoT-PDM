# IoT Predictive Maintenance (PDM) Project Overview

## Project Architecture

The system is designed to perform Predictive Maintenance on industrial machinery using a combination of edge sensors, long-range communication (LoRa), a central cloud platform (ThingsBoard), and a local Python-based Machine Learning (ML) backend.

The architecture flows from the physical sensors all the way to the user dashboard:

```mermaid
graph TD
    %% Define styles
    style SensorNode fill:#e0f7fa,stroke:#00acc1,stroke-width:2px,color:#000
    style Gateway fill:#fff8e1,stroke:#fbc02d,stroke-width:2px,color:#000
    style ThingsBoard fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#000
    style MLBackend fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px,color:#000
    style Frontend fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px,color:#000

    %% Nodes
    subgraph "Edge / Factory Floor"
        direction TB
        SensorNode["📡 LoRa Sensor Node (ESP32)
        - MPU6050 (Vibration)
        - DS18B20 (Temperature)"]
    end

    Gateway["🌐 LoRa Gateway (ESP32)
    - Receives LoRa packets
    - Connects to WiFi"]

    ThingsBoard["☁️ ThingsBoard Cloud
    - Ingests Telemetry (MQTT)
    - Live Dashboard Visualization
    - (Future: Rule Engine Forwarding)"]

    subgraph "Local / Edge Backend"
        direction TB
        MLBackend["🧠 Python ML Backend
        - Polls / Receives TB Telemetry
        - Runs Random Forest inference (pdm_model.pkl)
        - Calculates RUL & Health Score
        - Interacts with Gemini (AI Diagnosis)"]
    end

    Frontend["💻 React Frontend
    - Subscribes via local MQTT
    - Displays ML Results & Trends"]

    %% Edges
    SensorNode -- "LoRa (433MHz)" --> Gateway
    Gateway -- "Publish" --> ThingsBoard
    ThingsBoard -- "REST API / Webhook" --> MLBackend
    MLBackend -- "Publish ML Result (MQTT)" --> Frontend
    ThingsBoard -. "Live Telemetry" .-> Frontend
```

## How It Works

### 1. Sensor Node (Transmitter)
An ESP32 sits on the machinery and reads:
- **Temperature** from the DS18B20 sensor.
- **Vibration/Acceleration** from the MPU6050 sensor.
These values are bundled into a packet and sent via LoRa (433MHz) to maximize range and battery efficiency in noisy industrial environments.

### 2. Receiver Gateway
A second ESP32 acts as the LoRa receiver and internet gateway. It:
- Listens for LoRa packets from the sensor nodes.
- Extracts the temperature and vibration strings.
- Connects to a local WiFi network.
- Formats the data into a JSON payload.
- Publishes the payload directly to **ThingsBoard Cloud** using ThingsBoard's built-in MQTT broker.

### 3. ThingsBoard Cloud
ThingsBoard acts as the central data ingestion point. It receives the live streaming telemetry from the Gateway. This allows for immediate, out-of-the-box dashboards on ThingsBoard without routing through intermediate local servers.

### 4. Machine Learning Backend (Python)
The backend (`server.py`) is responsible for AI analysis and predictive maintenance. Since the live data now goes directly to ThingsBoard, the Python backend interfaces with ThingsBoard to retrieve the latest telemetry.
- It applies a highly trained scikit-learn model (`pdm_model.pkl`) to classify the machinery as `Healthy` or `Faulty`.
- It calculates advanced metrics like **Health Score**, **Remaining Useful Life (RUL)**, and **Statistical Trends**.
- It provides root cause analysis using Google's Gemini LLM.

### 5. Frontend Dashboard
A React dashboard connects to a local/public HiveMQ MQTT broker to receive the processed analytical results (AI classification, health score) from the backend, providing a comprehensive operational view.
