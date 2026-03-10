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
import numpy as np
from collections import deque
from scipy import stats

from train_model import FEATURE_COLUMNS, retrain_with_history
from explain_agent import get_explanation
from mqtt_config import (
    MQTT_BROKER, MQTT_PORT, DEPLOYMENT_MODE,
    TOPIC_DATA, TOPIC_RESULT, TOPIC_EXPLAIN_REQ, TOPIC_EXPLAIN_RES,
    TOPIC_RETRAIN_REQ, TOPIC_RETRAIN_RES, TOPIC_FEEDBACK
)
from http_server import run_http_server

# ----- Config -----
HTTP_PORT = 5000  # Port for receiving LoRa data from gateway
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pdm_model.pkl")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sensor_history.csv")

# CRITICAL DEMO: Toggle with 'f' + Enter in admin console
FORCE_FAULT = False
STATIC_FAULTY_MODE = False  # Use static faulty data instead of live feed
PAUSE_DATA = False  # Pause data processing to freeze at current state
PUBLISH_THROTTLE_SECS = 2.0  # Throttle frontend updates to every N seconds
_last_publish_time = 0  # Track last time we published a result
_last_threshold_breach = None  # Track latest threshold breach for AI explanation

# Threshold definitions (ISO 10816 & Industrial Standards)
VIB_DANGER = 15.0
TEMP_DANGER = 60.0

# ----- Hybrid LoRa/MQTT Statistics -----
_comm_stats = {
    'total_messages': 0,
    'lora_messages': 0,
    'mqtt_messages': 0,
    'last_lora_time': None,
    'last_mqtt_time': None,
    'lora_nodes': set(),  # Track unique LoRa node IDs
    'lora_rssi_avg': 0,
    'lora_snr_avg': 0,
    'rssi_samples': [],
    'snr_samples': []
}

# ----- Model (global for predict) -----
_model = None
# In-memory corrections: { timestamp_str: corrected_label_int }
_corrections = {}
# Global MQTT client for publishing results
_mqtt_client = None


def load_model():
    global _model
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found: {MODEL_PATH}. Run: python train_model.py")
        sys.exit(1)
    _model = joblib.load(MODEL_PATH)
    print("Model loaded.")


def _ensure_history_csv():
    """Create the history CSV with headers if it doesn't exist."""
    if not os.path.exists(HISTORY_PATH):
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        pd.DataFrame(columns=[
            "timestamp", "vib", "temp", "label"
        ]).to_csv(HISTORY_PATH, index=False)
        _log(f"Created sensor history: {HISTORY_PATH}")


def clean_sensor_history():
    """Clean corrupted sensor history CSV by reading valid rows and rewriting in new format."""
    if not os.path.exists(HISTORY_PATH):
        _log("No sensor history to clean")
        return
    
    try:
        # Try to read with error handling
        df = pd.read_csv(HISTORY_PATH, on_bad_lines='skip')
        
        # Check if this is the old format (no timestamp column)
        if 'timestamp' not in df.columns and 'vib' in df.columns:
            _log("Detected legacy CSV format (no timestamps). Converting to new format...")
            # Keep only vib, temp, label columns
            essential_cols = []
            if 'vib' in df.columns:
                essential_cols.append('vib')
            if 'temp' in df.columns:
                essential_cols.append('temp')
            if 'label' in df.columns:
                essential_cols.append('label')
            
            df = df[essential_cols]
            
            # Add timestamps (using current time with incremental offsets)
            from datetime import datetime, timedelta
            base_time = datetime.now() - timedelta(hours=len(df))
            df.insert(0, 'timestamp', [
                (base_time + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')
                for i in range(len(df))
            ])
        
        # Ensure we have the required columns now
        required_cols = ['timestamp', 'vib', 'temp', 'label']
        if not all(col in df.columns for col in required_cols):
            _log(f"Invalid columns in CSV. Found: {df.columns.tolist()}")
            raise ValueError("Missing required columns after conversion")
        
        # Keep only essential columns
        df = df[required_cols]
        
        # Convert to numeric
        df['vib'] = pd.to_numeric(df['vib'], errors='coerce')
        df['temp'] = pd.to_numeric(df['temp'], errors='coerce')
        df['label'] = pd.to_numeric(df['label'], errors='coerce')
        
        # Drop rows with missing values
        df = df.dropna()
        
        # Backup original
        backup_path = HISTORY_PATH + ".backup"
        import shutil
        try:
            shutil.copy(HISTORY_PATH, backup_path)
            _log(f"Backed up sensor history to {backup_path}")
        except Exception as be:
            _log(f"Backup warning: {be}")
        
        # Rewrite clean data
        df.to_csv(HISTORY_PATH, index=False, quoting=1)
        _log(f"Cleaned sensor history: {len(df)} valid rows retained")
        
    except Exception as e:
        _log(f"Error cleaning sensor history: {e}")
        # If all else fails, just start fresh
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        pd.DataFrame(columns=[
            "timestamp", "vib", "temp", "label"
        ]).to_csv(HISTORY_PATH, index=False)
        _log("Created fresh sensor history file")


def save_reading(timestamp, vib, temp, label):
    """Append a single reading to the sensor history CSV (simplified: only essential fields)."""
    _ensure_history_csv()
    row = pd.DataFrame([{
        "timestamp": timestamp,
        "vib": float(vib),
        "temp": float(temp),
        "label": int(label),
    }])
    # Use quoting to prevent CSV corruption from special characters
    row.to_csv(HISTORY_PATH, mode="a", header=False, index=False, quoting=1)


def apply_feedback(timestamp, corrected_label):
    """Store operator correction for a reading. Used during retrain."""
    _corrections[timestamp] = int(corrected_label)
    _log(f"Feedback stored: {timestamp} -> label={corrected_label}")
    # Also update the CSV row in-place
    try:
        if os.path.exists(HISTORY_PATH):
            df = pd.read_csv(HISTORY_PATH)
            mask = df["timestamp"] == timestamp
            if mask.any():
                df.loc[mask, "label"] = int(corrected_label)
                df.to_csv(HISTORY_PATH, index=False)
                _log(f"CSV updated for {timestamp}")
            else:
                _log(f"Timestamp {timestamp} not found in history — feedback stored in memory only")
    except Exception as e:
        _log(f"Error updating CSV: {e}")


def do_retrain(client):
    """Retrain model from base dataset + sensor history, reload, publish result."""
    _log("RETRAIN: Starting...")
    try:
        history_count = 0
        if os.path.exists(HISTORY_PATH):
            df = pd.read_csv(HISTORY_PATH)
            history_count = len(df)

        result = retrain_with_history(HISTORY_PATH)
        # Reload the model
        global _model
        _model = joblib.load(MODEL_PATH)
        _log(f"RETRAIN: Complete! Accuracy={result['accuracy']:.4f}, "
             f"base={result['base_count']}, history={result['history_count']}, "
             f"total={result['total_count']}")

        resp = {
            "status": "success",
            "accuracy": round(result["accuracy"], 4),
            "base_count": result["base_count"],
            "history_count": result["history_count"],
            "total_count": result["total_count"],
            "message": f"Model retrained! Accuracy: {result['accuracy']:.1%} on {result['total_count']} samples "
                       f"({result['base_count']} base + {result['history_count']} sensor readings)"
        }
    except Exception as e:
        _log(f"RETRAIN ERROR: {e}")
        resp = {"status": "error", "message": str(e)}

    if client:
        client.publish(TOPIC_RETRAIN_RES, json.dumps(resp), qos=0)
        _log(f">> [{TOPIC_RETRAIN_RES}] {json.dumps(resp)[:150]}")


def predict(sensor_data: dict) -> str:
    """Predict status using priority features [temp, vib].
    Threshold-based override: If readings exceed danger levels, immediately mark as Faulty.
    """
    temp_c = float(sensor_data.get("temp", 0))
    vib = float(sensor_data.get("vib", 0))

    # THRESHOLD OVERRIDE: If readings exceed danger thresholds, immediately classify as Faulty
    # This ensures demo mode clearly shows faults even if ML model isn't trained on extreme values
    if vib > VIB_DANGER or temp_c > TEMP_DANGER:
        _log(f"   🔴 THRESHOLD EXCEEDED: temp={temp_c}°C, vib={vib} => FAULTY (override)")
        return "Faulty"

    # Fall back to ML model prediction for borderline cases
    X = pd.DataFrame([[temp_c, vib]], columns=FEATURE_COLUMNS)
    pred = _model.predict(X)[0]
    _log(f"   predict: temp={temp_c}°C, vib={vib} => {pred}")
    return "Faulty" if pred == 1 else "Healthy"


# Store last reading for on-demand explain
_last_sensor_data = {}
_last_prediction = ""


def _log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def get_historical_baseline():
    """Get healthy baseline stats from sensor history (healthy readings only, label=0)."""
    if not os.path.exists(HISTORY_PATH):
        return None
    try:
        # Read with error handling for malformed rows (pandas 1.3+)
        df = pd.read_csv(HISTORY_PATH, on_bad_lines='skip')
    except TypeError:
        # Fallback for older pandas without on_bad_lines parameter
        try:
            df = pd.read_csv(HISTORY_PATH)
        except Exception as e:
            _log(f"Baseline calc error: {e}")
            return None
    except Exception as e:
        _log(f"Baseline calc error: {e}")
        return None
    
    try:
        # Convert columns to numeric, handling any string values
        if 'vib' in df.columns:
            df['vib'] = pd.to_numeric(df['vib'], errors='coerce')
        if 'temp' in df.columns:
            df['temp'] = pd.to_numeric(df['temp'], errors='coerce')
        if 'label' in df.columns:
            df['label'] = pd.to_numeric(df['label'], errors='coerce')
        
        # Filter to healthy readings (label=0) and drop rows with NaN values
        healthy = df[df['label'] == 0].dropna(subset=['vib', 'temp'])
        
        if len(healthy) < 5:  # Need enough data
            return None
        
        return {
            'vib_mean': float(healthy['vib'].mean()),
            'vib_std': float(healthy['vib'].std()),
            'temp_mean': float(healthy['temp'].mean()),
            'temp_std': float(healthy['temp'].std()),
            'rot_speed_mean': 1750.0,  # Typical healthy baseline
        }
    except Exception as e:
        _log(f"Baseline calc error: {e}")
        return None


def calculate_health_score(recent_vib, recent_temp):
    """Calculate health score 0-100 based on proximity to danger thresholds.
    100 = Healthy, 0 = Critical failure imminent.
    Formula: 100 * (1 - avg_severity), where avg_severity = mean([vib_ratio, temp_ratio])."""
    vib_ratio = min(recent_vib / VIB_DANGER, 1.0)  # Cap at 1.0
    temp_ratio = min(recent_temp / TEMP_DANGER, 1.0)  # Cap at 1.0
    avg_severity = (vib_ratio + temp_ratio) / 2.0
    health_score = max(0, 100 * (1 - avg_severity))
    return round(health_score, 1)


def calculate_trend(vib_history, temp_history):
    """Calculate trend direction (up/down/stable) and rate of change.
    Returns dict with trend direction and slope (m/s² per hour, °C per hour)."""
    if len(vib_history) < 3:
        return {'vib_trend': 'insufficient', 'temp_trend': 'insufficient', 'vib_slope': 0, 'temp_slope': 0}
    
    x = np.arange(len(vib_history))
    vib_slope, _, _, p_vib, _ = stats.linregress(x, vib_history)
    temp_slope, _, _, p_temp, _ = stats.linregress(x, temp_history)
    
    # Determine trend direction (significant if p-value < 0.05)
    vib_trend = 'rising' if (vib_slope > 0.1 and p_vib < 0.05) else ('falling' if (vib_slope < -0.1 and p_vib < 0.05) else 'stable')
    temp_trend = 'rising' if (temp_slope > 0.1 and p_temp < 0.05) else ('falling' if (temp_slope < -0.1 and p_temp < 0.05) else 'stable')
    
    return {
        'vib_trend': vib_trend,
        'temp_trend': temp_trend,
        'vib_slope': round(vib_slope, 3),
        'temp_slope': round(temp_slope, 3)
    }


def estimate_rul(current_vib, current_temp, vib_slope, temp_slope):
    """Estimate Remaining Useful Life (RUL) in hours until critical threshold.
    Uses linear extrapolation from trend slopes."""
    rul_estimates = []
    
    # Vibration RUL: hours until exceeding danger threshold
    if vib_slope > 0.01:  # Only estimate if trending up
        hours_to_critical = (VIB_DANGER - current_vib) / vib_slope
        if hours_to_critical > 0:
            rul_estimates.append(hours_to_critical)
    
    # Temperature RUL: hours until exceeding danger threshold
    if temp_slope > 0.01:  # Only estimate if trending up
        hours_to_critical = (TEMP_DANGER - current_temp) / temp_slope
        if hours_to_critical > 0:
            rul_estimates.append(hours_to_critical)
    
    # Return minimum RUL (conservative estimate)
    if rul_estimates:
        rul_hours = min(rul_estimates)
        rul_days = rul_hours / 24.0
        return max(0.1, round(rul_days, 1))  # Min 0.1 days = 2.4 hours
    else:
        return float('inf')  # No critical trend detected


def detect_anomalies(current_vib, current_temp, baseline):
    """Detect anomalies by comparing to healthy baseline.
    Flag if current reading deviates >2 std devs from healthy mean."""
    if not baseline:
        return {'vib_anomaly': False, 'temp_anomaly': False}
    
    vib_z_score = abs((current_vib - baseline['vib_mean']) / (baseline['vib_std'] + 0.1))
    temp_z_score = abs((current_temp - baseline['temp_mean']) / (baseline['temp_std'] + 0.1))
    
    return {
        'vib_anomaly': vib_z_score > 2.0,
        'temp_anomaly': temp_z_score > 2.0,
        'vib_z_score': round(vib_z_score, 2),
        'temp_z_score': round(temp_z_score, 2)
    }


# Global: store recent readings for trend analysis
_reading_buffer = {
    'timestamps': deque(maxlen=20),
    'vib_history': deque(maxlen=20),
    'temp_history': deque(maxlen=20)
}


def generate_static_faulty_data():
    """Generate static faulty sensor data for demonstration."""
    return {
        'vib': 22.5,      # m/s² - far exceeds danger threshold (15)
        'temp': 82.0,     # °C - far exceeds danger threshold (60)
        'air_temp_k': 312.0,  # K - elevated spindle ambient temp
        'rot_speed': 1200,    # RPM - motor struggling due to bearing friction
        'amp': 45.0       # A - higher current draw from struggling motor
    }


def on_connect(client, userdata, flags, reason_code, properties=None):
    _log(f"Connected to MQTT broker {MQTT_BROKER}:{MQTT_PORT} (reason_code={reason_code})")
    client.subscribe(TOPIC_EXPLAIN_REQ)
    client.subscribe(TOPIC_RETRAIN_REQ)
    client.subscribe(TOPIC_FEEDBACK)
    _log(f"Subscribed to: {TOPIC_EXPLAIN_REQ}, {TOPIC_RETRAIN_REQ}, {TOPIC_FEEDBACK}")
    _log("(Raw sensor data now arrives via HTTP from gateway, not MQTT)")


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    _log(f"Disconnected from MQTT (reason_code={reason_code})")


def on_subscribe(client, userdata, mid, reason_codes, properties=None):
    _log(f"Subscribe ACK mid={mid} reason_codes={reason_codes}")


def process_lora_data(data):
    """
    Process LoRa sensor data received from gateway via HTTP.
    Runs ML inference and publishes ONLY results to MQTT.
    This keeps raw data local (20-50ms latency) but publishes analysis to cloud dashboard.
    """
    global _last_sensor_data, _last_prediction, _last_threshold_breach, _mqtt_client
    
    try:
        # Track hybrid communication statistics
        _comm_stats['total_messages'] += 1
        source = data.get('source', 'lora')
        
        if source == 'lora':
            _comm_stats['lora_messages'] += 1
            _comm_stats['last_lora_time'] = datetime.now(timezone.utc).isoformat()
            
            # Track LoRa nodes
            node_id = data.get('node_id')
            if node_id:
                _comm_stats['lora_nodes'].add(node_id)
            
            # Track signal quality (sliding window average)
            rssi = data.get('rssi')
            snr = data.get('snr')
            if rssi is not None:
                _comm_stats['rssi_samples'].append(rssi)
                if len(_comm_stats['rssi_samples']) > 100:
                    _comm_stats['rssi_samples'].pop(0)
                _comm_stats['lora_rssi_avg'] = sum(_comm_stats['rssi_samples']) / len(_comm_stats['rssi_samples'])
            if snr is not None:
                _comm_stats['snr_samples'].append(snr)
                if len(_comm_stats['snr_samples']) > 100:
                    _comm_stats['snr_samples'].pop(0)
                _comm_stats['lora_snr_avg'] = sum(_comm_stats['snr_samples']) / len(_comm_stats['snr_samples'])
            
            _log(f"📡 LoRa Data | Node: {node_id} | RSSI: {rssi} dBm | SNR: {snr} dB")
        else:
            _comm_stats['mqtt_messages'] += 1
            _comm_stats['last_mqtt_time'] = datetime.now(timezone.utc).isoformat()
            _log(f"📶 WiFi/MQTT Data")
        
        # Check if data processing is paused
        if PAUSE_DATA:
            _log("⏸️  DATA PAUSED: Ignoring incoming data")
            return
        
        # Skip if STATIC_FAULTY_MODE is active
        if STATIC_FAULTY_MODE:
            _log("⏸️  STATIC MODE: Ignoring live data")
            return
        
        # VMC Physics Injection (demo mode)
        if FORCE_FAULT:
            data['vib'] = data.get('vib', 0) + 12.0
            data['temp'] = data.get('temp', 0) + 45.0
            data['air_temp_k'] = data.get('air_temp_k', 300.0) + 8.0
            data['rot_speed'] = data.get('rot_speed', 1500) * 0.75
            _log("🔴 DEMO MODE: Injected Fake Data (VMC Spindle Failure)")
            _log(f"   Modified: vib={data['vib']:.1f}, temp={data['temp']:.1f}")
        else:
            _log("🟢 Real Data (Live Sensor Stream)")
        
        # Run ML prediction
        prediction = predict(data)
        _last_sensor_data = data
        _last_prediction = prediction
        
        # Detect threshold breaches
        vib = float(data.get('vib', 0))
        temp = float(data.get('temp', 0))
        
        if vib > VIB_DANGER or temp > TEMP_DANGER:
            _last_threshold_breach = {
                'reason': (
                    f"Vibration {vib:.1f} exceeds danger threshold ({VIB_DANGER})" if vib > VIB_DANGER
                    else f"Temperature {temp:.1f}°C exceeds danger threshold ({TEMP_DANGER}°C)"
                ),
                'vib_value': vib,
                'vib_danger': VIB_DANGER,
                'temp_value': temp,
                'temp_danger': TEMP_DANGER,
            }
        else:
            _last_threshold_breach = None
        
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Save reading to history
        label = 1 if prediction == "Faulty" else 0
        save_reading(timestamp, vib, temp, label)
        
        # Update reading buffer
        _reading_buffer['timestamps'].append(timestamp)
        _reading_buffer['vib_history'].append(vib)
        _reading_buffer['temp_history'].append(temp)
        
        # Calculate predictive maintenance metrics
        health_score = calculate_health_score(vib, temp)
        baseline = get_historical_baseline()
        trend = calculate_trend(list(_reading_buffer['vib_history']), list(_reading_buffer['temp_history']))
        rul = estimate_rul(vib, temp, trend['vib_slope'], trend['temp_slope'])
        anomalies = detect_anomalies(vib, temp, baseline)
        
        # Build result (ONLY THIS GOES TO MQTT, not raw data)
        result = {
            "prediction": prediction,
            "timestamp": timestamp,
            "vib": vib,
            "temp": temp,
            "health_score": health_score,
            "trend": trend,
            "rul_days": rul if rul != float('inf') else None,
            "anomalies": anomalies,
            "comm_stats": {
                "total_messages": _comm_stats['total_messages'],
                "lora_messages": _comm_stats['lora_messages'],
                "mqtt_messages": _comm_stats['mqtt_messages'],
                "lora_percentage": round((_comm_stats['lora_messages'] / _comm_stats['total_messages'] * 100) if _comm_stats['total_messages'] > 0 else 0, 1),
                "active_lora_nodes": len(_comm_stats['lora_nodes']),
                "lora_rssi_avg": round(_comm_stats['lora_rssi_avg'], 1) if _comm_stats['lora_rssi_avg'] else None,
                "lora_snr_avg": round(_comm_stats['lora_snr_avg'], 1) if _comm_stats['lora_snr_avg'] else None,
                "last_source": data.get('source', 'lora'),
                "current_rssi": data.get('rssi'),
                "current_snr": data.get('snr'),
                "gateway": data.get('gateway'),
                "node_id": data.get('node_id')
            }
        }
        
        if baseline:
            result['baseline'] = {
                'vib_mean': baseline['vib_mean'],
                'temp_mean': baseline['temp_mean'],
                'rot_speed_mean': baseline['rot_speed_mean']
            }
        
        payload = json.dumps(result, default=str)
        
        # Publish ONLY result to MQTT (not raw data) - throttled
        global _last_publish_time
        current_time = time.time()
        if current_time - _last_publish_time >= PUBLISH_THROTTLE_SECS:
            if _mqtt_client and _mqtt_client.is_connected():
                _mqtt_client.publish(TOPIC_RESULT, payload, qos=0)
                _last_publish_time = current_time
                _log(f">> Result: {prediction} | Health={health_score} RUL={rul if rul != float('inf') else 'N/A'} days | vib={vib:.1f} temp={temp:.1f}")
        else:
            _log(f"   (throttled) prediction={prediction} | Health={health_score} | vib={vib:.1f} temp={temp:.1f}")
    
    except Exception as e:
        _log(f"❌ Error processing LoRa data: {e}")
        import traceback
        traceback.print_exc()


def on_message(client, userdata, msg):
    global _last_sensor_data, _last_prediction, _last_threshold_breach

    _log(f"<< [{msg.topic}] {msg.payload.decode()[:200]}")

    # ⚠️ NOTE: Raw sensor data now arrives via HTTP from gateway (not MQTT)
    # This function now only handles:
    # - AI explanation requests (TOPIC_EXPLAIN_REQ)
    # - Model retraining requests (TOPIC_RETRAIN_REQ)
    # - Operator feedback/corrections (TOPIC_FEEDBACK)
    
    # Handle on-demand explain request
    if msg.topic == TOPIC_EXPLAIN_REQ:
        if not _last_sensor_data or not _last_prediction:
            resp = {"explanation": "No sensor data available yet."}
        else:
            # Pass threshold breach context to provide richer diagnosis
            explanation = get_explanation(_last_sensor_data, _last_prediction, _last_threshold_breach)
            resp = {"explanation": explanation}
        client.publish(TOPIC_EXPLAIN_RES, json.dumps(resp), qos=0)
        _log(f"[EXPLAIN] {resp['explanation'][:100]}")
        return

    # Handle retrain request
    if msg.topic == TOPIC_RETRAIN_REQ:
        threading.Thread(target=do_retrain, args=(client,), daemon=True).start()
        return

    # Handle operator feedback (label correction)
    if msg.topic == TOPIC_FEEDBACK:
        try:
            fb = json.loads(msg.payload.decode())
            ts = fb.get("timestamp")
            label = fb.get("label")  # 0 = Healthy, 1 = Faulty
            if ts is not None and label is not None:
                apply_feedback(ts, label)
        except Exception as e:
            _log(f"Feedback parse error: {e}")
        return


def static_data_publisher(client):
    """Background thread: Continuously publish static faulty data when STATIC_FAULTY_MODE is enabled.
    Processes analytics and publishes both DATA and RESULT in one pass - avoids circular message handling."""
    global STATIC_FAULTY_MODE, _last_publish_time, _reading_buffer
    global _last_sensor_data, _last_prediction, _last_threshold_breach
    
    while True:
        try:
            if STATIC_FAULTY_MODE:
                # Generate static faulty data
                data = generate_static_faulty_data()
                timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                
                # 1. Publish raw data to TOPIC_DATA for frontend chart
                data_payload = json.dumps({
                    'vib': data['vib'],
                    'temp': data['temp'],
                    'amp': data.get('amp', 45.0),
                    'air_temp_k': data.get('air_temp_k', 312.0),
                    'rot_speed': data.get('rot_speed', 1200)
                })
                client.publish(TOPIC_DATA, data_payload, qos=0)
                
                # 2. Process analytics
                vib = data['vib']
                temp = data['temp']
                
                # Update reading buffer
                _reading_buffer['timestamps'].append(timestamp)
                _reading_buffer['vib_history'].append(vib)
                _reading_buffer['temp_history'].append(temp)
                
                # Calculate metrics
                prediction = predict(data)  # Will return "Faulty" due to threshold override
                
                # Update globals for AI diagnosis
                _last_sensor_data = data
                _last_prediction = prediction
                _last_threshold_breach = {
                    'reason': f"Vibration {vib:.1f} exceeds danger threshold ({VIB_DANGER})",
                    'vib_value': vib,
                    'vib_danger': VIB_DANGER,
                    'temp_value': temp,
                    'temp_danger': TEMP_DANGER,
                }
                
                health_score = calculate_health_score(vib, temp)
                baseline = get_historical_baseline()
                trend = calculate_trend(list(_reading_buffer['vib_history']), list(_reading_buffer['temp_history']))
                rul = estimate_rul(vib, temp, trend['vib_slope'], trend['temp_slope'])
                anomalies = detect_anomalies(vib, temp, baseline)
                
                # 3. Build and publish comprehensive result
                result = {
                    "prediction": prediction,
                    "timestamp": timestamp,
                    "vib": vib,
                    "temp": temp,
                    "health_score": health_score,
                    "trend": trend,
                    "rul_days": rul if rul != float('inf') else None,
                    "anomalies": anomalies,
                }
                
                if baseline:
                    result['baseline'] = {
                        'vib_mean': baseline['vib_mean'],
                        'temp_mean': baseline['temp_mean'],
                        'rot_speed_mean': baseline['rot_speed_mean']
                    }
                
                result_payload = json.dumps(result, default=str)
                client.publish(TOPIC_RESULT, result_payload, qos=0)
                _log(f"📊 Static Faulty Data: vib={vib}, temp={temp}, prediction={prediction}, health={health_score}")
                
            time.sleep(1.0)  # Publish every 1 second
        except Exception as e:
            _log(f"Error in static_data_publisher: {e}")
            time.sleep(2.0)


def admin_console():
    """Background listener: Toggle demo modes (live fault injection, static faulty data, etc.)."""
    global FORCE_FAULT, STATIC_FAULTY_MODE, PAUSE_DATA, PUBLISH_THROTTLE_SECS
    print("\n" + "="*70)
    print("🔧 ADMIN CONSOLE: VMC Fault Injection Demo Mode")
    print("="*70)
    print("Press 'f' + Enter to toggle LIVE FAULT INJECTION (modify incoming sensor data).")
    print("Press 'a' + Enter to toggle STATIC FAULTY DATA (hardcoded faulty demo values).")
    print("Press 't' + Enter to adjust frontend UPDATE THROTTLE (slower = more time to diagnose).")
    print("Press 's' + Enter to STOP all anomaly data and return to normal live feed.")
    print("Press 'r' + Enter to retrain model from sensor history.")
    print("Press 'clean' + Enter to clean corrupted sensor history CSV.")
    print("="*70 + "\n")
    while True:
        try:
            line = input().strip().lower()
            if line == "f":
                FORCE_FAULT = not FORCE_FAULT
                STATIC_FAULTY_MODE = False  # Turn off static mode when toggling live mode
                print("\n" + "🔴"*35 if FORCE_FAULT else "\n" + "🟢"*35)
                if FORCE_FAULT:
                    print("⚠️  LIVE FAULT INJECTION: ON  ⚠️")
                    print("Modifying incoming live sensor data with VMC spindle failure physics:")
                    print("  • Vibration +12.0 m/s² (ISO 10816 critical pitting)")
                    print("  • Temperature +45.0°C (bearing thermal runout)")
                    print("  • Air Temp +8.0 K (spindle heat)")
                    print("  • Rot Speed ×0.75 (motor struggling, seized bearings)")
                else:
                    print("✅ LIVE FAULT INJECTION: OFF")
                    print("Routing real live sensor data to ML model.")
                print("🔴"*35 if FORCE_FAULT else "🟢"*35)
                print()
            elif line == "a":
                STATIC_FAULTY_MODE = not STATIC_FAULTY_MODE
                FORCE_FAULT = False  # Turn off live mode when toggling static mode
                print("\n" + "🔴"*35 if STATIC_FAULTY_MODE else "\n" + "🟢"*35)
                if STATIC_FAULTY_MODE:
                    print("⚠️  STATIC FAULTY DATA: ON  ⚠️")
                    print("Publishing hardcoded faulty sensor values for demonstration:")
                    print("  • Vibration: 22.5 m/s² (well above danger threshold 15)")
                    print("  • Temperature: 82.0°C (well above danger threshold 60)")
                    print("  • Air Temp: 312.0 K (elevated spindle ambient)")
                    print("  • Rot Speed: 1200 RPM (motor struggling)")
                    print("  • Current: 45.0 A (higher power draw)")
                else:
                    print("✅ STATIC FAULTY DATA: OFF")
                    print("Routing real live sensor data to ML model.")
                print("🔴"*35 if STATIC_FAULTY_MODE else "🟢"*35)
                print()
            elif line == "t":
                try:
                    print(f"Current throttle: {PUBLISH_THROTTLE_SECS} seconds")
                    val = input("Enter new throttle interval (0.5-5 seconds): ").strip()
                    new_throttle = float(val)
                    if 0.5 <= new_throttle <= 5.0:
                        PUBLISH_THROTTLE_SECS = new_throttle
                        print(f"✅ Throttle updated to {PUBLISH_THROTTLE_SECS}s (slower = more time to diagnose)")
                    else:
                        print("❌ Invalid range (use 0.5-5 seconds)")
                except ValueError:
                    print("❌ Invalid input")
                print()
            elif line == "r":
                print("[RETRAIN] Triggering retrain from keyboard...")
                do_retrain(None)
            elif line == "clean":
                print("[CLEAN] Cleaning sensor history CSV...")
                clean_sensor_history()
            elif line == "s":
                FORCE_FAULT = False
                STATIC_FAULTY_MODE = False
                print("\n" + "🟢"*35)
                print("✅ ALL ANOMALY DATA STOPPED")
                print("Routing real live sensor data to ML model.")
                print("🟢"*35)
                print()
            elif line == "p":
                PAUSE_DATA = True
                print("\n" + "⏸️ "*35)
                print("⏸️  DATA PAUSED")
                print("Current state is FROZEN — you can now ask AI for diagnosis.")
                print("Press 'c' to resume data processing.")
                print("⏸️ "*35)
                print()
            elif line == "c":
                PAUSE_DATA = False
                print("\n" + "▶️ "*35)
                print("▶️  DATA RESUMED")
                print("Processing new incoming data.")
                print("▶️ "*35)
                print()
        except EOFError:
            break


def main():
    global _mqtt_client
    
    load_model()
    
    # Initialize MQTT client for publishing results only
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    _mqtt_client = client  # Store globally for process_lora_data()
    client.ws_set_options(path="/mqtt")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    _log(f"Connecting to {MQTT_BROKER}:{MQTT_PORT} ...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    
    # Start HTTP server for local LoRa gateway data (non-blocking)
    _log(f"Starting HTTP server on port {HTTP_PORT} for local LoRa data...")
    http_thread = threading.Thread(
        target=run_http_server,
        args=(process_lora_data, HTTP_PORT),
        daemon=True
    )
    http_thread.start()
    
    # Start admin console in background daemon thread
    admin_thread = threading.Thread(target=admin_console, daemon=True)
    admin_thread.start()
    
    # Start static data publisher in background daemon thread
    publisher_thread = threading.Thread(target=static_data_publisher, args=(client,), daemon=True)
    publisher_thread.start()
    
    _log("="*60)
    _log("IoT-PDM Backend Ready:")
    _log(f"  - HTTP Server: http://0.0.0.0:{HTTP_PORT}/api/lora/data (local gateway)")
    _log(f"  - MQTT Broker: {MQTT_BROKER}:{MQTT_PORT} (cloud results)")
    _log(f"  - Architecture: Gateway → HTTP(local) → ML → MQTT(results)")
    _log("="*60)
    
    client.loop_forever()


if __name__ == "__main__":
    main()
