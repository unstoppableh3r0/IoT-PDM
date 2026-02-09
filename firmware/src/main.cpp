/**
 * Smart IoT Predictive Maintenance - ESP32 Firmware
 * Sensors: MPU6050 (Vibration), DS18B20 (Temperature), ACS712 (Current)
 * Publishes JSON to MQTT: iot/pdm/project/data
 */

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ----- WiFi -----
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ----- MQTT -----
const char* MQTT_BROKER   = "broker.hivemq.com";
const uint16_t MQTT_PORT   = 1883;
const char* MQTT_TOPIC    = "iot/pdm/project/data";
const char* MQTT_CLIENT_ID = "esp32_pdm_001";

// ----- DS18B20 (Temperature) -----
const int ONE_WIRE_BUS = 4;  // GPIO4 for DS18B20 data
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);

// ----- ACS712 (Current) - analog pin -----
const int ACS712_PIN = 34;   // GPIO34 (ADC1_6)
const float ACS712_SENSITIVITY = 0.066;  // 66 mV/A for ACS712-5A
const float ZERO_CURRENT_VOLTAGE = 2.5; // Vcc/2 at 0A
const float ADC_VREF = 3.3;
const int ADC_RESOLUTION = 4095;

// ----- Objects -----
WiFiClient espClient;
PubSubClient mqttClient(espClient);
Adafruit_MPU6050 mpu;

// ----- Timing -----
const unsigned long SAMPLE_INTERVAL_MS = 1000;
unsigned long lastPublishTime = 0;

void setupWifi() {
  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
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

float readVibrationMagnitude() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  float x = a.acceleration.x;
  float y = a.acceleration.y;
  float z = a.acceleration.z;
  return sqrt(x * x + y * y + z * z);
}

float readTemperature() {
  tempSensor.requestTemperatures();
  return tempSensor.getTempCByIndex(0);
}

float readCurrent() {
  int raw = analogRead(ACS712_PIN);
  float voltage = (raw / (float)ADC_RESOLUTION) * ADC_VREF;
  float current = (voltage - ZERO_CURRENT_VOLTAGE) / ACS712_SENSITIVITY;
  return fabs(current);
}

void setup() {
  Serial.begin(115200);
  delay(500);

  if (!mpu.begin()) {
    Serial.println("MPU6050 not found. Check wiring.");
    while (1) delay(10);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  tempSensor.begin();
  pinMode(ACS712_PIN, INPUT);

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
  if (now - lastPublishTime >= SAMPLE_INTERVAL_MS) {
    lastPublishTime = now;

    float vib = readVibrationMagnitude();
    float temp = readTemperature();
    float amp = readCurrent();

    if (isnan(temp)) temp = 0.0f;

    StaticJsonDocument<128> doc;
    doc["vib"] = round(vib * 10.0f) / 10.0f;
    doc["temp"] = round(temp * 10.0f) / 10.0f;
    doc["amp"] = round(amp * 10.0f) / 10.0f;

    char payload[128];
    size_t len = serializeJson(doc, payload);

    if (mqttClient.publish(MQTT_TOPIC, payload, false)) {
      Serial.printf("Published: vib=%.1f temp=%.1f amp=%.1f\n", vib, temp, amp);
    } else {
      Serial.println("Publish failed");
    }
  }
}
