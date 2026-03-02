import paho.mqtt.client as mqtt
import json

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_DATA = "iot/pdm/project/data"

def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"Connected to MQTT Broker @ {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Listening for ESP32 data on topic: '{TOPIC_DATA}'...\n")
    client.subscribe(TOPIC_DATA)

def on_message(client, userdata, msg):
    try:
        raw = msg.payload.decode()
        data = json.loads(raw)
        print(f"[{msg.topic}] RAW JSON RECEIVED:")
        print(f"  Vib:  {data.get('vib')}")
        print(f"  Temp: {data.get('temp')} °C")
        if 'amp' in data:
            print(f"  Amp:  {data.get('amp')} A")
        print("-" * 30)
    except Exception as e:
        print(f"Received non-JSON message: {msg.payload.decode()}")

if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"Connection failed: {e}")
