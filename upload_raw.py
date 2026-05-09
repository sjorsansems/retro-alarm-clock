#!/usr/bin/env python3
import socket
import os

ESP_IP = "192.168.68.126"
ESP_PORT = 80
FILE_PATH = "retro_georgy_alarm_klok_v6.py"
UPLOAD_URL = "/api/upload-file"

print(f"📤 Uploading {FILE_PATH} to {ESP_IP}:{ESP_PORT}...")

if not os.path.exists(FILE_PATH):
    print(f"❌ File not found: {FILE_PATH}")
    exit(1)

with open(FILE_PATH, 'rb') as f:
    file_data = f.read()

file_size = len(file_data)
print(f"   File size: {file_size} bytes")

# Create multipart form data
boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="{FILE_PATH}"\r\n'
    f"Content-Type: application/octet-stream\r\n\r\n"
).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

# Create HTTP request
request = (
    f"POST {UPLOAD_URL} HTTP/1.1\r\n"
    f"Host: {ESP_IP}\r\n"
    f"Connection: close\r\n"
    f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
    f"Content-Length: {len(body)}\r\n"
    f"\r\n"
).encode() + body

print("   Connecting...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect((ESP_IP, ESP_PORT))
    print("   ✓ Connected")
    
    print("   Sending...")
    sock.sendall(request)
    print("   ✓ Sent")
    
    # Read response
    response = b""
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        except socket.timeout:
            break
    
    sock.close()
    
    # Parse response
    response_str = response.decode('utf-8', errors='ignore')
    print(f"\n   Response:\n{response_str[:500]}")
    
    if '"ok": true' in response_str or '"ok":true' in response_str:
        print("\n✅ Upload successful!")
    elif '"ok": false' in response_str or '"ok":false' in response_str:
        print("\n❌ Upload failed - check response above")
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
