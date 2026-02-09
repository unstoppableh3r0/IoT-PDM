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
from datetime import datetime

import paho.mqtt.client as mqtt
import joblib
import pandas as pd

from train_model import FEATURE_COLUMNS
from explain_agent import get_explanation

# ----- Config -----
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_DATA = "iot/pdm/project/data"
TOPIC_RESULT = "iot/pdm/project/result"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pdm_model.pkl")

# CRITICAL DEMO: Toggle with 'f' + Enter
FORCE_FAULT = False
FAKE_FAULTY_DATA = {"vib": 45.0, "temp": 85.0, "amp": 5.5}

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
    """Map sensor keys to feature order [Air temp, Torque, Rotational speed] -> temp, amp, vib."""
    # Our sensors: vib, temp, amp -> map to Air temperature (temp), Torque (amp), Rotational speed (vib)
    # AI4I uses K for temp; we use °C. Approximate: Air temp K ≈ temp_C + 273
    temp_c = float(sensor_data.get("temp", 0))
    amp = float(sensor_data.get("amp", 0))
    vib = float(sensor_data.get("vib", 0))
    air_temp_k = temp_c + 273.15
    torque = amp * 10  # scale current to Nm range (~40 Nm in dataset)
    rot_speed = min(max(vib * 100, 0), 3000)  # scale vibration to rpm-like
    X = pd.DataFrame([[air_temp_k, torque, rot_speed]], columns=FEATURE_COLUMNS)
    pred = _model.predict(X)[0]
    return "Faulty" if pred == 1 else "Healthy"


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"Connected to MQTT (reason_code={reason_code})")
    client.subscribe(TOPIC_DATA)


def on_message(client, userdata, msg):
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
    explanation = get_explanation(data, prediction)
    timestamp = datetime.utcnow().isoformat() + "Z"
    result = {
        "prediction": prediction,
        "explanation": explanation,
        "timestamp": timestamp,
        "vib": data.get("vib"),
        "temp": data.get("temp"),
        "amp": data.get("amp"),
    }
    payload = json.dumps(result)
    client.publish(TOPIC_RESULT, payload, qos=0)
    print(f"Result: {prediction} | {explanation[:60]}...")


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
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    thread = threading.Thread(target=keyboard_listener, daemon=True)
    thread.start()
    client.loop_forever()


if __name__ == "__main__":
    main()
