import gc
import time
import network

print("=== WIFI SMOKE MAIN ===")
gc.collect()
print("heap", gc.mem_free())

sta = network.WLAN(network.STA_IF)
print("sta_obj", sta is not None)

try:
    sta.active(True)
    print("sta_active", sta.active())
except Exception as e:
    print("sta_active_err", e)

try:
    sta.connect("SL2", "anuslikker101")
    print("connect_called")
except Exception as e:
    print("connect_err", e)

for i in range(20):
    try:
        print("status", i, sta.status(), sta.isconnected())
    except Exception as e:
        print("status_err", e)
    time.sleep(0.5)

print("=== DONE ===")
