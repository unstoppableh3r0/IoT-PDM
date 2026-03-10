"""
HTTP Server for receiving LoRa data from gateway
Runs alongside MQTT publisher in server.py
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# Callback function to be set by server.py
process_lora_data_callback = None

@app.route('/api/lora/data', methods=['POST'])
def receive_lora_data():
    """
    Receive LoRa data from gateway via HTTP POST
    Gateway forwards: {vib, temp, amp, fault, ts, source, rssi, snr, node_id, gateway}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        print(f"📡 LoRa Data Received [HTTP]: Node={data.get('node_id')}, RSSI={data.get('rssi')}dBm")
        
        # Call the processing callback (set by server.py)
        if process_lora_data_callback:
            process_lora_data_callback(data)
        
        return jsonify({
            "status": "received",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node_id": data.get('node_id')
        }), 200
    
    except Exception as e:
        print(f"❌ Error processing LoRa data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "ok", "service": "lora-backend"}), 200

def run_http_server(callback, port=5000):
    """
    Start HTTP server to receive LoRa data
    callback: function to process incoming data
    """
    global process_lora_data_callback
    process_lora_data_callback = callback
    
    print(f"🌐 HTTP Server starting on port {port}")
    print(f"   Endpoint: POST http://localhost:{port}/api/lora/data")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Test mode
    def test_callback(data):
        print(f"Test callback received: {data}")
    
    run_http_server(test_callback, port=5000)
