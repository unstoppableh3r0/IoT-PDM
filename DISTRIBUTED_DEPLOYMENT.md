# Distributed Deployment Guide - Edge + Dashboard

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      EDGE DEVICE (Laptop 1)                 │
│  ┌────────────┐  ┌──────────┐  ┌─────────────┐             │
│  │ ESP32      │  │ ESP32    │  │  Backend    │             │
│  │ Sensor     │→→│ Gateway  │→→│  Server     │→→ MQTT      │
│  │ Node       │  │ (LoRa→   │  │ (Process)   │   Broker    │
│  │ (LoRa TX)  │  │  MQTT)   │  │             │             │
│  └────────────┘  └──────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────┘
                            ↓ WiFi Network / Internet
┌─────────────────────────────────────────────────────────────┐
│                  DASHBOARD DEVICE (Laptop 2)                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         React Frontend (Web Browser)                │    │
│  │  ← MQTT Broker (receives results, sends commands)  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Option 1: Public MQTT Broker (Easiest - Current Setup)

Both devices connect to `broker.hivemq.com` over the internet.

### ✅ Advantages:
- Zero configuration needed
- Works anywhere with internet
- No firewall issues
- Already configured in your code

### ⚠️ Disadvantages:
- Requires internet on both devices
- ~100-300ms additional latency
- Data passes through public broker

### Setup Steps:

**Edge Device (Laptop 1):**
1. Connect ESP32s via USB
2. Upload gateway and sensor firmware (no changes needed)
3. Start backend:
   ```powershell
   cd D:\IOT-Proj\IoT-PDM\backend
   & d:\IOT-Proj\.venv\Scripts\Activate.ps1
   python server.py
   ```
4. Backend connects to `broker.hivemq.com:1883`

**Dashboard Device (Laptop 2):**
1. Start frontend:
   ```powershell
   cd D:\IOT-Proj\IoT-PDM\frontend
   npm run dev
   ```
2. Open browser: `http://localhost:5173`
3. Frontend connects to `ws://broker.hivemq.com:8000/mqtt`

✅ **That's it! Both connect through public broker automatically.**

---

## Option 2: Local MQTT Broker (Faster, Private Network)

Run MQTT broker on edge device, dashboard connects to edge's IP.

### ✅ Advantages:
- Faster (~10-50ms latency)
- Works without internet
- Data stays on local network
- More private/secure

### ⚠️ Disadvantages:
- Requires Mosquitto installation on edge device
- Need to configure firewall
- Dashboard needs edge device's IP address

### Setup Steps:

#### Step 1: Install Mosquitto on Edge Device (Laptop 1)

**Windows:**
```powershell
# Download from: https://mosquitto.org/download/
# Install Mosquitto 2.x
# Default install to C:\Program Files\mosquitto\

# Enable WebSockets: Edit C:\Program Files\mosquitto\mosquitto.conf
# Add these lines:
listener 1883
protocol mqtt

listener 8000
protocol websockets
```

**Start Mosquitto:**
```powershell
cd "C:\Program Files\mosquitto"
.\mosquitto.exe -c mosquitto.conf -v
```

**Linux/Mac:**
```bash
sudo apt install mosquitto mosquitto-clients  # Ubuntu/Debian
brew install mosquitto  # macOS

# Edit /etc/mosquitto/mosquitto.conf or /usr/local/etc/mosquitto/mosquitto.conf
# Add:
listener 1883
protocol mqtt

listener 8000
protocol websockets

# Start:
sudo systemctl start mosquitto  # Linux
brew services start mosquitto   # macOS
```

#### Step 2: Find Edge Device IP Address

**Windows:**
```powershell
ipconfig
# Look for "IPv4 Address" under your WiFi/Ethernet adapter
# Example: 192.168.1.100
```

**Linux/Mac:**
```bash
ip addr show  # Linux
ifconfig      # macOS
# Example: 192.168.1.100
```

#### Step 3: Configure Backend on Edge Device

I'll create a configuration file for easy switching:

**Edit `backend/mqtt_config.py`:**
```python
DEPLOYMENT_MODE = "local"  # Change from "public" to "local"
LOCAL_MQTT_BROKER = "192.168.1.100"  # Your edge device IP
```

**Start backend:**
```powershell
cd D:\IOT-Proj\IoT-PDM\backend
& d:\IOT-Proj\.venv\Scripts\Activate.ps1
python server.py
# Should show: 🏠 LOCAL MODE: Connecting to 192.168.1.100:1883
```

#### Step 4: Configure Frontend on Dashboard Device

**Edit `frontend/src/mqttConfig.js`:**
```javascript
const DEPLOYMENT_MODE = "local"  // Change from "public" to "local"
const LOCAL_BROKER = {
  host: "192.168.1.100",  // Your edge device IP
  port: 8000,
  url: "ws://192.168.1.100:8000/mqtt"
}
```

**Start frontend:**
```powershell
cd D:\IOT-Proj\IoT-PDM\frontend
npm run dev
# Open browser: http://localhost:5173
# Should connect to ws://192.168.1.100:8000/mqtt
```

#### Step 5: Update ESP32 Gateway (Optional - for local broker)

If using local broker, update gateway firmware to point to edge device:

**Edit `gateway/lora_mqtt_gateway/lora_mqtt_gateway.ino`:**
```cpp
const char* MQTT_BROKER = "192.168.1.100";  // Change from broker.hivemq.com
```

Re-upload gateway firmware.

---

## Firewall Configuration

### Windows (Edge Device):
```powershell
# Allow MQTT ports through Windows Firewall
New-NetFirewallRule -DisplayName "MQTT TCP" -Direction Inbound -LocalPort 1883 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "MQTT WebSocket" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### Linux (Edge Device):
```bash
sudo ufw allow 1883/tcp
sudo ufw allow 8000/tcp
sudo ufw reload
```

---

## Verification Steps

### 1. Check Edge Device Services

**On Edge Device, verify all running:**
```
✅ Mosquitto (if using local broker)
   - Check: netstat -an | findstr :1883
   - Should show: LISTENING on port 1883 and 8000

✅ Backend Server
   - Terminal shows: Connected to MQTT broker
   - Shows: 🏠 LOCAL MODE or 🌐 PUBLIC MODE

✅ ESP32 Gateway
   - Serial Monitor shows: ✅ MQTT Connected!
   - Shows: Gateway Ready - Listening...

✅ ESP32 Sensor Node
   - Serial Monitor shows: 🔋 Mode: HYBRID (LoRa + WiFi)
   - Shows: 📡 LoRa TX [...] every 2 seconds
```

### 2. Check Dashboard Device

**On Dashboard Device:**
```
✅ Frontend running
   - Browser console shows: 🔧 MQTT Config: LOCAL/PUBLIC mode
   - Shows: 📡 Connecting to ...
   - Dashboard shows: 🟢 MQTT Connected

✅ Dashboard displays data
   - Motor Status updates every 2 seconds
   - Communication stats show LoRa messages
   - Charts update in real-time
```

### 3. End-to-End Test

**Watch data flow through entire system:**

1. **Sensor Node** (Edge Device - ESP32 #1):
   ```
   📡 LoRa TX [78B]: {"id":"esp32_pdm_001",...}
   ```

2. **Gateway** (Edge Device - ESP32 #2):
   ```
   📡 LoRa Packet Received! RSSI: -45 dBm
   📤 Forwarded to MQTT [152B]
   ```

3. **Backend** (Edge Device - Laptop 1):
   ```
   << [iot/pdm/project/data] {...}
   📡 LoRa Data | Node: esp32_pdm_001 | RSSI: -45 dBm
   >> Result: Healthy | Health=95 | vib=9.8 temp=28.3
   ```

4. **Frontend** (Dashboard Device - Laptop 2):
   ```
   Browser console:
   [MQTT 14:32:15] << [iot/pdm/project/result] {"prediction":"Healthy",...}
   
   Dashboard displays:
   - Motor Status: Healthy ✅
   - 📡 LoRa Active (-45 dBm)
   - Communication stats: 150 total, 120 LoRa (80%)
   ```

---

## Troubleshooting Distributed Setup

### Dashboard can't connect to MQTT broker

**Symptom:** Dashboard shows "Disconnected", console shows connection errors

**Solutions:**

1. **Check broker is running** (if using local mode):
   ```powershell
   # On edge device:
   netstat -an | findstr :8000
   # Should show: LISTENING
   ```

2. **Verify IP address** in frontend config:
   ```javascript
   // frontend/src/mqttConfig.js
   const LOCAL_BROKER = {
     host: "192.168.1.100",  // Must match edge device IP
   }
   ```
   Get correct IP:
   ```powershell
   ipconfig  # Windows
   ifconfig  # Mac/Linux
   ```

3. **Check firewall** on edge device:
   ```powershell
   # Windows: Temporarily disable to test
   Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False
   # If works, re-enable and add proper rules
   Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True
   ```

4. **Test connection** from dashboard device:
   ```powershell
   # Test if edge device's broker is reachable
   Test-NetConnection -ComputerName 192.168.1.100 -Port 8000
   # Should show: TcpTestSucceeded : True
   ```

5. **Check both devices on same network**:
   ```powershell
   # On dashboard device:
   ping 192.168.1.100
   # Should get replies
   ```

### Backend receives data but dashboard doesn't update

**Symptom:** Backend logs show messages, but dashboard frozen

**Solutions:**

1. **Check browser console** for MQTT errors
2. **Verify topics match** between backend and frontend
3. **Check MQTT broker logs** (if local):
   ```powershell
   # Mosquitto logs show both connections
   ```

### ESP32 gateway can't connect to local broker

**Symptom:** Gateway shows "MQTT connection failed"

**Solutions:**

1. **Update gateway firmware** with correct IP:
   ```cpp
   const char* MQTT_BROKER = "192.168.1.100";
   ```

2. **Check edge device firewall** allows port 1883

3. **Verify edge device IP hasn't changed** (use static IP in router)

### High latency between edge and dashboard

**Symptom:** Dashboard lags 5-10 seconds behind live data

**Solutions:**

1. **Switch to local broker** (Option 2) instead of public
2. **Check network**: High WiFi interference causes delays
3. **Reduce MQTT QoS** if using QoS 2 (change to QoS 0)

---

## Network Setup Recommendations

### Static IP for Edge Device

Assign static IP to edge device in router settings:
- Prevents IP changes requiring reconfiguration
- Typical router UI: 192.168.1.1 or 192.168.0.1
- Set edge device to: 192.168.1.100 (or similar)

### Same WiFi Network

Both devices must be on same WiFi network (or wired to same router):
- Edge device: Connect to WiFi
- Dashboard device: Connect to same WiFi
- Guest networks may block device-to-device communication

### VPN/Remote Access (Advanced)

To access dashboard remotely over internet:

**Option A: Port Forwarding**
- Forward port 8000 on router to edge device
- Access via: `ws://your-public-ip:8000/mqtt`
- Security risk: Enable authentication in Mosquitto

**Option B: Tailscale/ZeroTier**
- Install VPN on both devices
- Access edge via Tailscale IP (e.g., 100.x.x.x)
- More secure than port forwarding

---

## Performance Comparison

| Metric | Public Broker | Local Broker |
|--------|--------------|--------------|
| **Latency** | 100-300 ms | 10-50 ms |
| **Bandwidth** | Internet required | LAN only |
| **Setup** | Zero config | Mosquitto + firewall |
| **Reliability** | Depends on internet | LAN only |
| **Security** | Data passes public broker | Stays on LAN |
| **Remote Access** | Works anywhere | VPN needed |

---

## Production Deployment Checklist

### Edge Device (Laptop 1):
- ✅ ESP32 gateway powered and connected
- ✅ ESP32 sensor node powered and monitoring
- ✅ Backend server running (auto-start on boot recommended)
- ✅ Mosquitto running (if local mode)
- ✅ Firewall configured (if local mode)
- ✅ Static IP assigned
- ✅ Power management disabled (prevent sleep)

### Dashboard Device (Laptop 2):
- ✅ Frontend running (or built and served via nginx)
- ✅ Browser opens to dashboard URL
- ✅ MQTT connection verified
- ✅ Real-time updates confirmed

### Network:
- ✅ Both devices on same WiFi
- ✅ Edge device has static IP
- ✅ Firewall rules configured
- ✅ Router QoS set (prioritize MQTT traffic)

---

## Quick Switch Between Modes

**To switch from PUBLIC to LOCAL:**

1. Edge Device:
   ```python
   # backend/mqtt_config.py
   DEPLOYMENT_MODE = "local"
   ```

2. Dashboard Device:
   ```javascript
   // frontend/src/mqttConfig.js
   const DEPLOYMENT_MODE = "local"
   ```

3. Restart both backend and frontend

**To switch from LOCAL to PUBLIC:**

1. Change both back to `"public"`
2. Restart backend and frontend
3. No Mosquitto or firewall needed

---

## Support Scripts

Create these helper scripts for quick deployment:

**`start_edge.bat` (Windows) / `start_edge.sh` (Mac/Linux):**
```batch
@echo off
echo Starting Edge Device Services...
start mosquitto  REM if using local mode
cd D:\IOT-Proj\IoT-PDM\backend
call d:\IOT-Proj\.venv\Scripts\Activate.ps1
start python server.py
echo ✅ Edge device started!
pause
```

**`start_dashboard.bat` (Windows) / `start_dashboard.sh` (Mac/Linux):**
```batch
@echo off
echo Starting Dashboard...
cd D:\IOT-Proj\IoT-PDM\frontend
start npm run dev
timeout /t 5
start http://localhost:5173
echo ✅ Dashboard started!
pause
```

---

**Your system is now ready for distributed deployment!** 🚀

Choose Option 1 (public broker) for simplicity, or Option 2 (local broker) for speed and privacy.

