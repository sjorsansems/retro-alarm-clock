#!/usr/bin/env python3
import requests
import sys
import os

# Configuration
ESP_IP = "192.168.68.126"
FILE_PATH = "retro_georgy_alarm_klok_v6.py"
UPLOAD_URL = f"http://{ESP_IP}/api/upload-file"

print(f"📤 Uploading {FILE_PATH} to http://{ESP_IP}...")

if not os.path.exists(FILE_PATH):
    print(f"❌ File not found: {FILE_PATH}")
    sys.exit(1)

try:
    with open(FILE_PATH, 'rb') as f:
        files = {'file': (os.path.basename(FILE_PATH), f)}
        print(f"   File size: {os.path.getsize(FILE_PATH)} bytes")
        print(f"   Uploading...")
        
        response = requests.post(UPLOAD_URL, files=files, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ Upload successful!")
            print(f"   Response: {response.text[:100]}")
        else:
            print(f"❌ Upload failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            sys.exit(1)
            
except requests.exceptions.ConnectionError:
    print(f"❌ Connection error - ESP32 not reachable at {ESP_IP}")
    print("   Make sure ESP32 is connected and powered on")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

print("\n🔄 Now restart the ESP32...")
print("   Option 1: Press RESET button on device")
print("   Option 2: Use web UI 'Herstarten' button")
print("   Option 3: Run: curl -X POST http://192.168.68.126/api/restart")
