/**
 * LoRa to Backend Gateway - ESP32
 * Receives LoRa packets from PDM sensors and forwards to local backend via HTTP
 * Backend processes locally and only sends RESULTS to MQTT cloud
 * 
 * Architecture:
 *   ESP32 Sensor → LoRa (1s, 60B) → Gateway → Backend (local, 20-50ms)
 *   Backend → ML Processing → MQTT (results only, 80B, on fault)
 * 
 * Hardware: ESP32 with SX1278 LoRa module
 * LoRa Pins: SCK=5, MISO=19, MOSI=27, CS=18, RST=14, DIO0=26
 * 
 * ARDUINO IDE SETUP:
 *   Board: "ESP32 Dev Module"
 *   Required Libraries:
 *     - LoRa by Sandeep Mistry
 *     - HTTPClient (built-in)
 *     - ArduinoJson
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <LoRa.h>
#include <ArduinoJson.h>

// ----- WiFi Configuration -----
const char* WIFI_SSID     = "money trees";
const char* WIFI_PASSWORD = "kendricklamar";

// ----- Backend Configuration (Local) -----
const char* BACKEND_HOST = "192.168.1.100";  // IP of laptop running backend
const uint16_t BACKEND_PORT = 5000;
const char* BACKEND_ENDPOINT = "/api/lora/data";  // Backend HTTP endpoint

// ----- LoRa Pins (Same as sensor node) -----
#define LORA_SCK     5
#define LORA_MISO    19
#define LORA_MOSI    27
#define LORA_CS      18
#define LORA_RST     14
#define LORA_DIO0    26

// ----- LoRa Configuration (Must match sensor node) -----
#define LORA_FREQUENCY 433E6
#define LORA_TX_POWER 20
#define LORA_SPREADING_FACTOR 7
#define LORA_BANDWIDTH 125E3
#define LORA_CODING_RATE 5

// ----- Statistics -----
unsigned long packetsReceived = 0;
unsigned long packetsForwarded = 0;
unsigned long packetsFailed = 0;
unsigned long lastStatsTime = 0;

void setupWifi() {
  Serial.print("Connecting to WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("✅ WiFi Connected!");
    Serial.print("   IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("   Backend: http://");
    Serial.print(BACKEND_HOST);
    Serial.print(":");
    Serial.println(BACKEND_PORT);
  } else {
    Serial.println("❌ WiFi connection failed!");
    Serial.println("   Gateway cannot forward without WiFi. Restarting in 10s...");
    delay(10000);
    ESP.restart();
  }
}

bool initLoRa() {
  Serial.println("\nInitializing LoRa receiver...");
  Serial.println("  Pins: SCK=5, MISO=19, MOSI=27, CS=18, RST=14, DIO0=26");
  
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
  LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);
  
  if (!LoRa.begin(LORA_FREQUENCY)) {
    Serial.println("❌ LoRa initialization FAILED!");
    return false;
  }
  
  LoRa.setSpreadingFactor(LORA_SPREADING_FACTOR);
  LoRa.setSignalBandwidth(LORA_BANDWIDTH);
  LoRa.setCodingRate4(LORA_CODING_RATE);
  LoRa.enableCrc();
  
  Serial.println("✅ LoRa receiver ready!");
  Serial.print("   Frequency: ");
  Serial.print(LORA_FREQUENCY / 1E6);
  Serial.println(" MHz");
  Serial.print("   SF: ");
  Serial.println(LORA_SPREADING_FACTOR);
  
  return true;
}

void forwardToBackend(String loraPayload, int rssi, float snr) {
  // Parse incoming LoRa JSON
  StaticJsonDocument<256> loraDoc;
  DeserializationError error = deserializeJson(loraDoc, loraPayload);
  
  if (error) {
    Serial.print("❌ JSON parse error: ");
    Serial.println(error.c_str());
    packetsFailed++;
    return;
  }
  
  // Create enriched payload for backend
  StaticJsonDocument<384> backendDoc;
  
  // Copy sensor data from LoRa packet
  backendDoc["vib"] = loraDoc["vib"];
  backendDoc["temp"] = loraDoc["temp"];
  backendDoc["amp"] = loraDoc["amp"];
  backendDoc["fault"] = loraDoc["fault"];
  backendDoc["ts"] = loraDoc["ts"];
  
  // Add source information
  backendDoc["source"] = "lora";
  backendDoc["gateway"] = "gateway_001";
  backendDoc["node_id"] = loraDoc["id"] | "unknown";
  backendDoc["msg_num"] = loraDoc["msg"];
  
  // Add signal quality
  backendDoc["rssi"] = rssi;
  backendDoc["snr"] = snr;
  
  // Serialize to JSON string
  char jsonPayload[384];
  size_t len = serializeJson(backendDoc, jsonPayload);
  
  // Send HTTP POST to local backend
  HTTPClient http;
  String url = String("http://") + BACKEND_HOST + ":" + BACKEND_PORT + BACKEND_ENDPOINT;
  
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  
  int httpCode = http.POST(jsonPayload);
  
  if (httpCode == 200 || httpCode == 201) {
    Serial.print("📤 Forwarded to Backend [");
    Serial.print(len);
    Serial.print("B] → HTTP ");
    Serial.println(httpCode);
    packetsForwarded++;
  } else {
    Serial.print("❌ HTTP POST failed: ");
    Serial.println(httpCode);
    packetsFailed++;
  }
  
  http.end();
}

void printStats() {
  unsigned long now = millis();
  if (now - lastStatsTime >= 30000) {  // Every 30 seconds
    lastStatsTime = now;
    Serial.println("\n========== GATEWAY STATISTICS ==========");
    Serial.print("Packets Received:  ");
    Serial.println(packetsReceived);
    Serial.print("Packets Forwarded: ");
    Serial.println(packetsForwarded);
    Serial.print("Packets Failed:    ");
    Serial.println(packetsFailed);
    Serial.print("Success Rate:      ");
    if (packetsReceived > 0) {
      Serial.print((packetsForwarded * 100.0) / packetsReceived);
      Serial.println("%");
    } else {
      Serial.println("N/A");
    }
    Serial.println("========================================\n");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n╔════════════════════════════════════════╗");
  Serial.println("║  LoRa to Backend Gateway - Starting   ║");
  Serial.println("╚════════════════════════════════════════╝\n");
  
  // Initialize WiFi
  setupWifi();
  
  // Initialize LoRa
  if (!initLoRa()) {
    Serial.println("CRITICAL: LoRa initialization failed. Restarting in 10s...");
    delay(10000);
    ESP.restart();
  }
  
  Serial.println("\n╔════════════════════════════════════════╗");
  Serial.println("║   Gateway Ready - Forwarding Local    ║");
  Serial.println("╚════════════════════════════════════════╝\n");
}

void loop() {
  // Check for incoming LoRa packets
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    packetsReceived++;
    
    // Read packet
    String payload = "";
    while (LoRa.available()) {
      payload += (char)LoRa.read();
    }
    
    // Get signal quality
    int rssi = LoRa.packetRssi();
    float snr = LoRa.packetSnr();
    
    // Log reception
    Serial.println("\n📡 LoRa Packet Received!");
    Serial.print("   Size: ");
    Serial.print(packetSize);
    Serial.println(" bytes");
    Serial.print("   RSSI: ");
    Serial.print(rssi);
    Serial.println(" dBm");
    Serial.print("   SNR:  ");
    Serial.print(snr);
    Serial.println(" dB");
    Serial.print("   Data: ");
    Serial.println(payload);
    
    // Forward to local backend via HTTP
    forwardToBackend(payload, rssi, snr);
  }
  
  // Print periodic statistics
  printStats();
  
  // Small delay to prevent watchdog issues
  delay(10);
}
