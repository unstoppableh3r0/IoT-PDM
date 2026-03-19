import time
import json
import requests
import threading
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ThingsBoard Configuration
TB_SERVER = "https://thingsboard.cloud"
# The Device ID in ThingsBoard (Required for REST API telemetry fetching)
# You can find this in ThingsBoard -> Devices -> your device -> Copy Device ID
DEVICE_ID = os.getenv("TB_DEVICE_ID", "b1d4bbd0-2354-11f1-b5ad-e9bed839c74c") 

# ThingsBoard Tenant/Customer Login (Required to read telemetry)
# A device token (like LRvOEzgOd6HPXzdrufMI) can only PUBLISH telemetry. To READ it back,
# you must authenticate as a User.
TB_USERNAME = os.getenv("TB_USERNAME", "aathityashan@gmail.com")
TB_PASSWORD = os.getenv("TB_PASSWORD", "Thingsboard")

_jwt_token = None
_callback = None

def login_to_thingsboard():
    """Authenticate with ThingsBoard REST API to get a JWT token."""
    global _jwt_token
    
    if TB_USERNAME == "your_email@example.com":
        print("⚠️ [TB Client] Warning: Using default TB_USERNAME. Please update your credentials.")
        
    url = f"{TB_SERVER}/api/auth/login"
    payload = {
        "username": TB_USERNAME,
        "password": TB_PASSWORD
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            _jwt_token = response.json().get("token")
            print("✅ [TB Client] Successfully authenticated with ThingsBoard.")
            return True
        else:
            print(f"❌ [TB Client] Authentication failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ [TB Client] Login error: {e}")
        return False

def pull_latest_telemetry():
    """Fetch the latest telemetry (vib, temp) for the device."""
    global _jwt_token
    if not _jwt_token:
        if not login_to_thingsboard():
            return None
            
    headers = {
        "X-Authorization": f"Bearer {_jwt_token}",
        "Accept": "application/json"
    }
    
    # keys=temperature,vibration (Matching the Arduino JSON payload)
    url = f"{TB_SERVER}/api/plugins/telemetry/DEVICE/{DEVICE_ID}/values/timeseries?keys=temperature,vibration"
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        
        # If token expired, unauthorized
        if response.status_code == 401:
            print("🔄 [TB Client] Token expired. Relogging in...")
            if login_to_thingsboard():
                headers["X-Authorization"] = f"Bearer {_jwt_token}"
                response = requests.get(url, headers=headers, timeout=5)
            else:
                return None
                
        if response.status_code == 200:
            data = response.json()
            return data
        elif response.status_code == 400 and "Invalid UUID" in response.text:
            print(f"❌ [TB Client] Invalid DEVICE_ID ({DEVICE_ID}). Please update it.")
            time.sleep(10) # slow down polling on error
            return None
        else:
            print(f"❌ [TB Client] Failed to fetch telemetry: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ [TB Client] Error fetching telemetry: {e}")
        return None

def tb_polling_worker(interval=2.0):
    """Background thread to poll ThingsBoard and trigger the callback."""
    print(f"🌐 [TB Client] Started polling ThingsBoard every {interval}s")
    last_timestamp = 0
    
    while True:
        data = pull_latest_telemetry()
        
        if data and _callback:
            try:
                # The response structure is usually {"temperature": [{"ts": 123, "value": "25.0"}], ...}
                temp_data = data.get("temperature", [])
                vib_data = data.get("vibration", [])
                
                if temp_data and vib_data:
                    latest_temp = temp_data[0]
                    latest_vib = vib_data[0]
                    
                    # Use the latest timestamp to avoid processing duplicates
                    current_ts = max(latest_temp.get("ts", 0), latest_vib.get("ts", 0))
                    
                    if current_ts > last_timestamp:
                        last_timestamp = current_ts
                        
                        # Build the standardized data dict for the ML model
                        formatted_data = {
                            "temp": float(latest_temp.get("value", 0)),
                            "vib": float(latest_vib.get("value", 0)),
                            "source": "thingsboard",
                            "node_id": "ESP32_Gateway",
                            "timestamp": current_ts
                        }
                        
                        # Trigger the ML processor
                        _callback(formatted_data)
            except Exception as e:
                print(f"❌ [TB Client] Error processing telemetry: {e}")
                
        time.sleep(interval)

def start_tb_client(callback, poll_interval=2.0):
    """Starts the background ThingsBoard polling thread."""
    global _callback
    _callback = callback
    
    # Try one login immediately
    login_to_thingsboard()
    
    # Start thread
    t = threading.Thread(target=tb_polling_worker, args=(poll_interval,), daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    # Test
    def test_cb(data):
        print(f"Got data: {data}")
    start_tb_client(test_cb)
    while True:
        time.sleep(1)
