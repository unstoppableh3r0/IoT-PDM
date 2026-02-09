/**
 * PDM Test Sketch - Arduino IDE
 * Publishes DUMMY sensor data to MQTT (no physical sensors needed).
 * Use this to test: WiFi -> MQTT -> Backend -> Frontend
 * 
 * 1. Set WIFI_SSID and WIFI_PASSWORD below
 * 2. Board: ESP32 Dev Module
 * 3. Install libraries: PubSubClient, ArduinoJson
 * 4. Upload and open Serial Monitor (115200)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ----- SET THESE -----
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ----- MQTT -----
const char* MQTT_BROKER   = "broker.hivemq.com";
const uint16_t MQTT_PORT  = 1883;
const char* MQTT_TOPIC    = "iot/pdm/project/data";
const char* MQTT_CLIENT_ID = "esp32_pdm_test";

WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long lastPublish = 0;
const unsigned long INTERVAL_MS = 1000;

void setupWifi() {
  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());
}

void reconnectMqtt() {
  while (!mqttClient.connected()) {
    Serial.print("MQTT connecting...");
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println(" connected");
    } else {
      Serial.print(" failed, rc=");
      Serial.println(mqttClient.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("PDM Test - Dummy data mode");

  setupWifi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(256);
}

void loop() {
  if (!mqttClient.connected()) {
    reconnectMqtt();
  }
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastPublish >= INTERVAL_MS) {
    lastPublish = now;

    // Dummy sensor values (simulated)
    float vib = 8.0 + (random(0, 50) / 10.0);   // 8.0 - 12.9
    float temp = 40.0 + (random(0, 30) / 10.0); // 40.0 - 42.9
    float amp = 1.5 + (random(0, 20) / 10.0);   // 1.5 - 3.4

    StaticJsonDocument<128> doc;
    doc["vib"] = round(vib * 10.0f) / 10.0f;
    doc["temp"] = round(temp * 10.0f) / 10.0f;
    doc["amp"] = round(amp * 10.0f) / 10.0f;

    char payload[128];
    serializeJson(doc, payload);

    if (mqttClient.publish(MQTT_TOPIC, payload, false)) {
      Serial.printf("Published: %s\n", payload);
    } else {
      Serial.println("Publish failed");
    }
  }
}
