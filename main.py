# Autostart entrypoint for ESP32 MicroPython.
# Running from file avoids Thonny %Run -c RAM overhead.
import gc
import time

gc.collect()

def _boot():
    import retro_georgy_alarm_klok_v6
    app = retro_georgy_alarm_klok_v6.App()
    app.run()

while True:
    try:
        _boot()
    except Exception as e:
        print("FATAL in main:", e)
        gc.collect()
        time.sleep(2)
