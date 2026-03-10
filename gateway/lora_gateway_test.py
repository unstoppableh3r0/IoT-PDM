#!/usr/bin/env python3
"""
LoRa Gateway Test Script
Tests reception of LoRa packets from ESP32 without MQTT integration

Requirements:
- Raspberry Pi with Dragino LoRa HAT
- Python 3.7+
- pyserial library: pip install pyserial

Usage:
    python lora_gateway_test.py
    
Expected: Receives JSON packets from ESP32 LoRa sender and displays them
"""

import serial
import json
import time
import sys
from datetime import datetime

# ===== Configuration =====
SERIAL_PORT = "/dev/ttyAMA0"  # Raspberry Pi serial port (may be /dev/ttyUSB0)
BAUDRATE = 115200
TIMEOUT = 1

# Color codes for terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Statistics
stats = {
    'packets_received': 0,
    'packets_failed': 0,
    'start_time': time.time()
}

def print_header():
    """Print colorful header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 50}")
    print(f"    LoRa Gateway Test - Raspberry Pi")
    print(f"{'=' * 50}{Colors.ENDC}\n")

def connect_serial():
    """Connect to serial port"""
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=TIMEOUT)
        print(f"{Colors.GREEN}✓{Colors.ENDC} Connected to {SERIAL_PORT} @ {BAUDRATE} baud")
        return ser
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.ENDC} Failed to connect to {SERIAL_PORT}")
        print(f"  Error: {e}")
        print(f"\n{Colors.YELLOW}Troubleshooting:{Colors.ENDC}")
        print(f"  1. Check if Dragino HAT is properly connected")
        print(f"  2. Try: ls /dev/tty* to find correct port")
        print(f"  3. May need sudo: sudo python lora_gateway_test.py")
        print(f"  4. Enable serial: sudo raspi-config → Interface → Serial")
        return None

def parse_packet(raw_data):
    """Parse incoming packet"""
    try:
        # Try to decode as UTF-8
        decoded = raw_data.decode('utf-8').strip()
        
        # Try to parse as JSON
        data = json.loads(decoded)
        return data, decoded, True
    except json.JSONDecodeError:
        # Not JSON, return as string
        try:
            decoded = raw_data.decode('utf-8').strip()
            return None, decoded, False
        except:
            return None, str(raw_data), False
    except Exception as e:
        return None, str(raw_data), False

def display_packet(packet_num, data, raw, is_json):
    """Display received packet with formatting"""
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'─' * 50}{Colors.ENDC}")
    print(f"{Colors.BOLD}📡 Packet #{packet_num}{Colors.ENDC} | {Colors.CYAN}{timestamp}{Colors.ENDC}")
    print(f"{Colors.BLUE}{'─' * 50}{Colors.ENDC}")
    
    if is_json:
        # Display JSON fields
        print(f"{Colors.GREEN}📦 Parsed Data:{Colors.ENDC}")
        for key, value in data.items():
            print(f"   {Colors.BOLD}{key}:{Colors.ENDC} {value}")
        
        # Check for sensor data
        if 'vib' in data and 'temp' in data:
            vib = float(data['vib'])
            temp = float(data['temp'])
            
            # Visual indicators
            vib_status = "⚠️  HIGH" if vib > 15.0 else "✓ Normal"
            temp_status = "⚠️  HIGH" if temp > 60.0 else "✓ Normal"
            
            print(f"\n{Colors.YELLOW}🔍 Analysis:{Colors.ENDC}")
            print(f"   Vibration: {vib:.1f} m/s² - {vib_status}")
            print(f"   Temperature: {temp:.1f} °C - {temp_status}")
    else:
        # Display raw data
        print(f"{Colors.YELLOW}📄 Raw Data:{Colors.ENDC}")
        print(f"   {raw}")
    
    print(f"{Colors.BLUE}{'─' * 50}{Colors.ENDC}\n")

def display_stats():
    """Display statistics"""
    uptime = time.time() - stats['start_time']
    total = stats['packets_received'] + stats['packets_failed']
    success_rate = (stats['packets_received'] / total * 100) if total > 0 else 0
    
    print(f"\n{Colors.CYAN}┌{'─' * 48}┐{Colors.ENDC}")
    print(f"{Colors.CYAN}│{Colors.ENDC} {Colors.BOLD}Statistics{Colors.ENDC}{' ' * 38}{Colors.CYAN}│{Colors.ENDC}")
    print(f"{Colors.CYAN}├{'─' * 48}┤{Colors.ENDC}")
    print(f"{Colors.CYAN}│{Colors.ENDC} Uptime: {uptime:.0f}s{' ' * (40 - len(str(int(uptime))))}{Colors.CYAN}│{Colors.ENDC}")
    print(f"{Colors.CYAN}│{Colors.ENDC} Packets Received: {stats['packets_received']}{' ' * (30 - len(str(stats['packets_received'])))}{Colors.CYAN}│{Colors.ENDC}")
    print(f"{Colors.CYAN}│{Colors.ENDC} Packets Failed: {stats['packets_failed']}{' ' * (32 - len(str(stats['packets_failed'])))}{Colors.CYAN}│{Colors.ENDC}")
    print(f"{Colors.CYAN}│{Colors.ENDC} Success Rate: {success_rate:.1f}%{' ' * (32 - len(f'{success_rate:.1f}'))}{Colors.CYAN}│{Colors.ENDC}")
    print(f"{Colors.CYAN}└{'─' * 48}┘{Colors.ENDC}\n")

def main():
    """Main test loop"""
    print_header()
    
    # Connect to serial
    ser = connect_serial()
    if not ser:
        sys.exit(1)
    
    print(f"\n{Colors.GREEN}🎧 Listening for LoRa packets...{Colors.ENDC}")
    print(f"{Colors.YELLOW}Press Ctrl+C to stop{Colors.ENDC}\n")
    
    last_stats_time = time.time()
    
    try:
        while True:
            # Check if data available
            if ser.in_waiting > 0:
                try:
                    # Read line
                    raw_data = ser.readline()
                    
                    if raw_data:
                        # Parse packet
                        data, raw_str, is_json = parse_packet(raw_data)
                        
                        if is_json or raw_str:
                            stats['packets_received'] += 1
                            display_packet(stats['packets_received'], data, raw_str, is_json)
                        else:
                            stats['packets_failed'] += 1
                
                except Exception as e:
                    stats['packets_failed'] += 1
                    print(f"{Colors.RED}✗ Parse error: {e}{Colors.ENDC}")
            
            # Display stats every 10 seconds
            if time.time() - last_stats_time > 10:
                display_stats()
                last_stats_time = time.time()
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Shutting down...{Colors.ENDC}")
        display_stats()
        ser.close()
        print(f"{Colors.GREEN}✓ Serial port closed{Colors.ENDC}\n")

if __name__ == "__main__":
    main()
