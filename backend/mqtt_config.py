# MQTT Configuration
# Switch between public broker (internet) and local broker (private network)

# ===== DEPLOYMENT MODE =====
# Options: "public" or "local"
DEPLOYMENT_MODE = "public"

# ===== PUBLIC BROKER (Internet) =====
# Use this for distributed deployment over internet
# Both edge and dashboard connect to public broker
PUBLIC_MQTT_BROKER = "broker.hivemq.com"
PUBLIC_MQTT_PORT = 8000  # WebSocket port for frontend
PUBLIC_MQTT_PORT_TCP = 1883  # TCP port for backend

# ===== LOCAL BROKER (Private Network) =====
# Use this when running Mosquitto on edge device
# Dashboard connects to edge device's IP
# Find edge IP with: ipconfig (Windows) or ifconfig (Mac/Linux)
LOCAL_MQTT_BROKER = "192.168.1.100"  # ← CHANGE THIS to your edge device IP
LOCAL_MQTT_PORT = 8000  # WebSocket port for frontend
LOCAL_MQTT_PORT_TCP = 1883  # TCP port for backend

# ===== AUTO-SELECT BASED ON MODE =====
if DEPLOYMENT_MODE == "local":
    MQTT_BROKER = LOCAL_MQTT_BROKER
    MQTT_PORT = LOCAL_MQTT_PORT_TCP
    MQTT_WS_PORT = LOCAL_MQTT_PORT
    print(f"🏠 LOCAL MODE: Connecting to {MQTT_BROKER}:{MQTT_PORT}")
else:
    MQTT_BROKER = PUBLIC_MQTT_BROKER
    MQTT_PORT = PUBLIC_MQTT_PORT_TCP
    MQTT_WS_PORT = PUBLIC_MQTT_PORT
    print(f"🌐 PUBLIC MODE: Connecting to {MQTT_BROKER}:{MQTT_PORT}")

# ===== TOPICS (Same for both modes) =====
TOPIC_DATA = "iot/pdm/project/data"
TOPIC_RESULT = "iot/pdm/project/result"
TOPIC_EXPLAIN_REQ = "iot/pdm/project/explain"
TOPIC_EXPLAIN_RES = "iot/pdm/project/explanation"
TOPIC_RETRAIN_REQ = "iot/pdm/project/retrain"
TOPIC_RETRAIN_RES = "iot/pdm/project/retrain_result"
TOPIC_FEEDBACK = "iot/pdm/project/feedback"
