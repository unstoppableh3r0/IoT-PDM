// MQTT Broker Configuration for Frontend
// Switch between public broker (internet) and local broker (private network)

// ===== DEPLOYMENT MODE =====
// Options: "public" or "local"
const DEPLOYMENT_MODE = "public"

// ===== PUBLIC BROKER (Internet) =====
// Use this for distributed deployment over internet
const PUBLIC_BROKER = {
  host: "broker.hivemq.com",
  port: 8000,
  url: "ws://broker.hivemq.com:8000/mqtt"
}

// ===== LOCAL BROKER (Private Network) =====
// Use this when running Mosquitto on edge device
// !! CHANGE THE IP ADDRESS to your edge device's IP !!
// Find edge IP with: ipconfig (Windows) or ifconfig (Mac/Linux)
const LOCAL_BROKER = {
  host: "192.168.1.100",  // ← CHANGE THIS to your edge device IP
  port: 8000,
  url: "ws://192.168.1.100:8000/mqtt"
}

// ===== AUTO-SELECT BASED ON MODE =====
export const BROKER_CONFIG = DEPLOYMENT_MODE === "local" ? LOCAL_BROKER : PUBLIC_BROKER

// Display which mode is active
console.log(`🔧 MQTT Config: ${DEPLOYMENT_MODE.toUpperCase()} mode`)
console.log(`📡 Connecting to: ${BROKER_CONFIG.url}`)

// ===== TOPICS (Same for both modes) =====
export const TOPICS = {
  DATA: "iot/pdm/project/data",
  RESULT: "iot/pdm/project/result",
  EXPLAIN_REQ: "iot/pdm/project/explain",
  EXPLAIN_RES: "iot/pdm/project/explanation",
  RETRAIN_REQ: "iot/pdm/project/retrain",
  RETRAIN_RES: "iot/pdm/project/retrain_result",
  FEEDBACK: "iot/pdm/project/feedback"
}
