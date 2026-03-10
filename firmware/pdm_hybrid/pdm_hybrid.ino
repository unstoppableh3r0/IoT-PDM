/**
 * Smart IoT Predictive Maintenance - ESP32 Hybrid Firmware
 * Sensors: MPU6050 (Vibration), DS18B20 (Temperature), ACS712 (Current)
 * Communication: LoRa (primary), WiFi+MQTT (secondary)
 * 
 * LoRa Configuration (Verified Working):
 *   SCK=5, MISO=19, MOSI=27, CS=18, RST=14, DIO0=26
 * 
 * ARDUINO IDE SETUP:
 *   Board: "ESP32 Dev Module"
 *   Upload Speed: 115200
 *   Required Libraries:
 *     - Adafruit MPU6050
 *     - Adafruit Unified Sensor
 *     - DallasTemperature
 *     - OneWire
 *     - PubSubClient
 *     - ArduinoJson
 *     - LoRa by Sandeep Mistry
 */

#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <SPI.h>
#include <LoRa.h>

// ----- WiFi Configuration -----
const char* WIFI_SSID     = "money trees";
const char* WIFI_PASSWORD = "kendricklamar";

// ----- MQTT Configuration -----
const char* MQTT_BROKER   = "broker.hivemq.com";  // More reliable broker
const uint16_t MQTT_PORT   = 1883;
const char* MQTT_TOPIC    = "iot/pdm/project/data";
const char* MQTT_CLIENT_ID = "esp32_pdm_001";

// ----- LoRa Pins (Verified Working Configuration) -----
#define LORA_SCK     5
#define LORA_MISO    19
#define LORA_MOSI    27
#define LORA_CS      18
#define LORA_RST     14
#define LORA_DIO0    26

// ----- LoRa Configuration -----
#define LORA_FREQUENCY 433E6       // 433 MHz
#define LORA_TX_POWER 20           // Maximum power (20 dBm)
#define LORA_SPREADING_FACTOR 7    // Balance between range and speed
#define LORA_BANDWIDTH 125E3       // 125 kHz
#define LORA_CODING_RATE 5         // 4/5 coding rate

// ----- DS18B20 (Temperature) -----
const int ONE_WIRE_BUS = 14;  // GPIO14 for DS18B20 data
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);

// ----- ACS712 (Current) - analog pin -----
const int ACS712_PIN = 34;   // GPIO34 (ADC1_6)
const float ACS712_SENSITIVITY = 0.066;  // 66 mV/A for ACS712-5A
const float ZERO_CURRENT_VOLTAGE = 2.5; // Vcc/2 at 0A
const float ADC_VREF = 3.3;
const int ADC_RESOLUTION = 4095;

// ----- Fault Detection Thresholds -----
const float VIB_DANGER = 15.0;   // m/s² - ISO 10816 severe threshold
const float TEMP_DANGER = 60.0;  // °C - Motor overheating threshold
const float TEMP_WARNING = 50.0; // °C - Warning threshold

// ----- Objects -----
WiFiClient espClient;
PubSubClient mqttClient(espClient);
Adafruit_MPU6050 mpu;

// ----- State Variables -----
bool loraAvailable = false;
bool wifiAvailable = false;
unsigned long lastPublishTime = 0;
int messageCounter = 0;

// ----- Timing -----
const unsigned long SAMPLE_INTERVAL_MS = 2000;  // 2 seconds between readings

void setupWifi() {
  Serial.print("Initializing WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("=========================================");
    Serial.println("✅ WiFi Connected (SECONDARY path)");
    Serial.print("   SSID: ");
    Serial.println(WIFI_SSID);
    Serial.print("   IP: ");
    Serial.println(WiFi.localIP());
    Serial.println("=========================================");
    wifiAvailable = true;
  } else {
    Serial.println("⚠️  WiFi connection failed - will use LoRa only");
    wifiAvailable = false;
  }
}

void reconnectMqtt() {
  while (!mqttClient.connected()) {
    Serial.print("Attempting MQTT connection to ");
    Serial.print(MQTT_BROKER);
    Serial.print("...");
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println(" SUCCESS: MQTT connected!");
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

// ===== LoRa Functions =====
bool initLoRa() {
  Serial.println("\nInitializing LoRa...");
  Serial.println("  Pins: SCK=5, MISO=19, MOSI=27, CS=18, RST=14, DIO0=26");
  
  // Initialize SPI with custom pins
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
  
  // Set LoRa pins
  LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);
  
  // Initialize LoRa
  if (!LoRa.begin(LORA_FREQUENCY)) {
    Serial.println("❌ LoRa initialization FAILED!");
    return false;
  }
  
  // Configure LoRa
  LoRa.setTxPower(LORA_TX_POWER);
  LoRa.setSpreadingFactor(LORA_SPREADING_FACTOR);
  LoRa.setSignalBandwidth(LORA_BANDWIDTH);
  LoRa.setCodingRate4(LORA_CODING_RATE);
  LoRa.enableCrc();
  
  Serial.println("=========================================");
  Serial.println("✅ LoRa Ready (PRIMARY communication)");
  Serial.print("   Frequency: ");
  Serial.print(LORA_FREQUENCY / 1E6);
  Serial.println(" MHz");
  Serial.print("   TX Power: ");
  Serial.print(LORA_TX_POWER);
  Serial.println(" dBm");
  Serial.print("   SF: ");
  Serial.println(LORA_SPREADING_FACTOR);
  Serial.println("=========================================");
  
  return true;
}

void sendViaLoRa(float vib, float temp, float amp, bool fault) {
  // Create compact JSON for LoRa (keep under 100 bytes)
  StaticJsonDocument<128> doc;
  doc["id"] = MQTT_CLIENT_ID;
  doc["msg"] = messageCounter;
  doc["vib"] = round(vib * 10.0f) / 10.0f;
  doc["temp"] = round(temp * 10.0f) / 10.0f;
  doc["amp"] = round(amp * 100.0f) / 100.0f;
  doc["fault"] = fault ? 1 : 0;
  doc["ts"] = millis() / 1000;
  
  String payload;
  serializeJson(doc, payload);
  
  // Send LoRa packet
  LoRa.beginPacket();
  LoRa.print(payload);
  LoRa.endPacket();
  
  Serial.print("📡 LoRa TX [");
  Serial.print(payload.length());
  Serial.print("B]: ");
  Serial.println(payload);
}

void sendViaMQTT(float vib, float temp, float amp) {
  StaticJsonDocument<256> doc;
  doc["vib"] = round(vib * 10.0f) / 10.0f;
  doc["temp"] = round(temp * 10.0f) / 10.0f;
  doc["amp"] = round(amp * 10.0f) / 10.0f;
  doc["ts"] = millis() / 1000;
  doc["source"] = "mqtt_fallback";
  
  char payload[256];
  size_t len = serializeJson(doc, payload);
  
  if (mqttClient.publish(MQTT_TOPIC, payload, false)) {
    Serial.print("📶 MQTT TX [");
    Serial.print(len);
    Serial.println("B]: published successfully");
  } else {
    Serial.println("⚠️  MQTT publish failed");
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("\n--- Starting Smart IoT PDM Node ---");

  if (!mpu.begin()) {
    Serial.println("ERROR: MPU6050 not found. Check wiring (SDA/SCL).");
    while (1) delay(10);
  }
  Serial.println("SUCCESS: MPU6050 init successful!");
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  tempSensor.begin();
  Serial.println("SUCCESS: DS18B20 Temp Sensor init successful!");
  
  pinMode(ACS712_PIN, INPUT);

  // Initialize LoRa (primary communication)
  loraAvailable = initLoRa();
  
  // Initialize WiFi + MQTT (secondary communication)
  setupWifi();
  
  Serial.println("Configuring MQTT Broker...");
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(256);

  // Display hybrid status
  Serial.println("\n===== HYBRID COMMUNICATION STATUS =====");
  Serial.print("📡 LoRa:  ");
  Serial.println(loraAvailable ? "✅ READY" : "❌ UNAVAILABLE");
  Serial.print("📶 WiFi:  ");
  Serial.println(wifiAvailable ? "✅ READY" : "❌ UNAVAILABLE");
  Serial.print("🔋 Mode:  ");
  if (loraAvailable && !wifiAvailable) {
    Serial.println("LOW-POWER (LoRa only)");
  } else if (!loraAvailable && wifiAvailable) {
    Serial.println("FALLBACK (WiFi/MQTT only)");
  } else if (loraAvailable && wifiAvailable) {
    Serial.println("HYBRID (LoRa + WiFi)");
  } else {
    Serial.println("⚠️  NO CONNECTIVITY");
  }
  Serial.println("=======================================\n");

  Serial.println("Setup Complete. Entering Main Loop.\n");
}

void loop() {
  // Maintain MQTT connection if WiFi available
  if (wifiAvailable) {
    if (!mqttClient.connected()) {
      reconnectMqtt();
    }
    mqttClient.loop();
  }

  unsigned long now = millis();
  if (now - lastPublishTime >= SAMPLE_INTERVAL_MS) {
    lastPublishTime = now;
    messageCounter++;

    // Read all sensors
    float vib = readVibrationMagnitude();
    float temp = readTemperature();
    float amp = readCurrent();

    if (isnan(temp)) temp = 0.0f;

    // Check for fault conditions
    bool isFault = (vib >= VIB_DANGER || temp >= TEMP_DANGER);
    if (isFault) {
      Serial.println("🚨 FAULT DETECTED!");
      Serial.printf("   Vibration: %.1f m/s² (threshold: %.1f)\n", vib, VIB_DANGER);
      Serial.printf("   Temperature: %.1f°C (threshold: %.1f)\n", temp, TEMP_DANGER);
    }

    // === HYBRID SEND LOGIC ===
    // Primary: Send via LoRa (low power, long range)
    if (loraAvailable) {
      sendViaLoRa(vib, temp, amp, isFault);
    } else {
      Serial.println("⚠️  LoRa unavailable, skipping LoRa transmission");
    }

    // Secondary: Send via MQTT (rich data, cloud integration)
    if (wifiAvailable && mqttClient.connected()) {
      sendViaMQTT(vib, temp, amp);
    } else if (!loraAvailable) {
      // If LoRa is also down, we have a problem
      Serial.println("🔴 NO CONNECTIVITY: Both LoRa and WiFi unavailable!");
    }

    // Display sensor readings
    Serial.printf("Sensors: vib=%.1f m/s² | temp=%.1f°C | amp=%.2fA\n\n", vib, temp, amp);
  }
}
