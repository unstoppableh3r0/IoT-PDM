"""
PDM Server: MQTT subscriber, ML inference, Gemini explanation, result publisher.
Listens to iot/pdm/project/data; publishes to iot/pdm/project/result.
Press 'f' + Enter to toggle FORCE_FAULT (inject fake faulty data for demo).
"""

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

import paho.mqtt.client as mqtt
import joblib
import pandas as pd

from train_model import FEATURE_COLUMNS
from explain_agent import get_explanation

# ----- Config -----
MQTT_BROKER = "broker.mqttdashboard.com"
MQTT_PORT = 8000  # Port 8000 for WebSockets
TOPIC_DATA = "iot/pdm/project/data"
TOPIC_RESULT = "iot/pdm/project/result"
TOPIC_EXPLAIN_REQ = "iot/pdm/project/explain"
TOPIC_EXPLAIN_RES = "iot/pdm/project/explanation"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pdm_model.pkl")

# CRITICAL DEMO: Toggle with 'f' + Enter
FORCE_FAULT = False
FAKE_FAULTY_DATA = {"vib": 45.0, "temp": 85.0}

# ----- Model (global for predict) -----
_model = None


def load_model():
    global _model
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found: {MODEL_PATH}. Run: python train_model.py")
        sys.exit(1)
    _model = joblib.load(MODEL_PATH)
    print("Model loaded.")


def predict(sensor_data: dict) -> str:
    """Map sensor keys to feature order [Air temp, Rotational speed] -> temp, vib.
    
    AI4I 2020 dataset ranges:
      Air temperature [K]: 295.3 - 304.5  (mean ~300, i.e. ~27°C)
      Rotational speed [rpm]: 1168 - 2886  (mean ~1539)
    
    ESP32 sensor ranges:
      temp: ~20-50 °C  ->  scale into 295-305 K range
      vib:  ~5-50      ->  scale into 1100-2900 rpm range
    """
    temp_c = float(sensor_data.get("temp", 0))
    vib = float(sensor_data.get("vib", 0))

    # Map temp (°C) into training range: 20°C->296K, 30°C->300K, 50°C->304K
    air_temp_k = 296.0 + (temp_c - 20.0) * (8.0 / 30.0)  # 20-50°C -> 296-304 K
    air_temp_k = min(max(air_temp_k, 295.0), 305.0)

    # Map vib into training range: low vib(~5)->1500rpm(normal), high vib(>30)->1200rpm(abnormal low)
    # In the dataset, low rotational speed correlates with failure
    rot_speed = 1800.0 - (vib * 15.0)  # vib=5->1725, vib=20->1500, vib=40->1200
    rot_speed = min(max(rot_speed, 1100.0), 2900.0)

    X = pd.DataFrame([[air_temp_k, rot_speed]], columns=FEATURE_COLUMNS)
    pred = _model.predict(X)[0]
    _log(f"   predict: temp={temp_c}°C->air_temp={air_temp_k:.1f}K, vib={vib}->rpm={rot_speed:.0f} => {pred}")
    return "Faulty" if pred == 1 else "Healthy"


# Store last reading for on-demand explain
_last_sensor_data = {}
_last_prediction = ""


def _log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def on_connect(client, userdata, flags, reason_code, properties=None):
    _log(f"Connected to MQTT broker {MQTT_BROKER}:{MQTT_PORT} (reason_code={reason_code})")
    client.subscribe(TOPIC_DATA)
    client.subscribe(TOPIC_EXPLAIN_REQ)
    _log(f"Subscribed to: {TOPIC_DATA}, {TOPIC_EXPLAIN_REQ}")


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    _log(f"Disconnected from MQTT (reason_code={reason_code})")


def on_subscribe(client, userdata, mid, reason_codes, properties=None):
    _log(f"Subscribe ACK mid={mid} reason_codes={reason_codes}")


def on_message(client, userdata, msg):
    global _last_sensor_data, _last_prediction

    _log(f"<< [{msg.topic}] {msg.payload.decode()[:200]}")

    # Handle on-demand explain request
    if msg.topic == TOPIC_EXPLAIN_REQ:
        if not _last_sensor_data or not _last_prediction:
            resp = {"explanation": "No sensor data available yet."}
        else:
            explanation = get_explanation(_last_sensor_data, _last_prediction)
            resp = {"explanation": explanation}
        client.publish(TOPIC_EXPLAIN_RES, json.dumps(resp), qos=0)
        _log(f"[EXPLAIN] {resp['explanation'][:80]}")
        return

    # Normal sensor data handling
    try:
        raw = msg.payload.decode()
        data = json.loads(raw)
    except Exception as e:
        print("Invalid JSON:", e)
        return

    if FORCE_FAULT:
        data = FAKE_FAULTY_DATA.copy()
        print("[DEMO] Using FAKE faulty data:", data)

    prediction = predict(data)
    _last_sensor_data = data
    _last_prediction = prediction
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = {
        "prediction": prediction,
        "timestamp": timestamp,
        "vib": data.get("vib"),
        "temp": data.get("temp"),
    }
    payload = json.dumps(result)
    client.publish(TOPIC_RESULT, payload, qos=0)
    _log(f">> Result: {prediction} | vib={data.get('vib')} temp={data.get('temp')}")


def keyboard_listener():
    """Listen for 'f' + Enter to toggle FORCE_FAULT."""
    global FORCE_FAULT
    print("Press 'f' + Enter to toggle FAULT INJECTION (demo mode).")
    while True:
        try:
            line = input().strip().lower()
            if line == "f":
                FORCE_FAULT = not FORCE_FAULT
                status = "ON (fake faulty data)" if FORCE_FAULT else "OFF (live data)"
                print(f"[FORCE_FAULT] {status}")
        except EOFError:
            break


def main():
    load_model()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    client.ws_set_options(path="/mqtt")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    _log(f"Connecting to {MQTT_BROKER}:{MQTT_PORT} ...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    thread = threading.Thread(target=keyboard_listener, daemon=True)
    thread.start()
    client.loop_forever()


if __name__ == "__main__":
    main()
