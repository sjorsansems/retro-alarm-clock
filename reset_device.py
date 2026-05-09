#!/usr/bin/env python3
import subprocess
import time

# Reset via mpremote
result = subprocess.run(
    ["python", "-m", "mpremote", "connect", "COM7", "exec", "import machine; machine.reset()"],
    capture_output=True,
    text=True,
    timeout=5
)

print("Reset sent. Waiting for reboot...")
time.sleep(3)
print("✓ Device should be booting now")
