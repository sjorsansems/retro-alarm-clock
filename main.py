# Autostart entrypoint for ESP32 MicroPython.
# Running from file avoids Thonny %Run -c RAM overhead.
import gc
import time

PRIMARY_MODULE = "retro_georgy_alarm_klok_v6"
BACKUP_MODULE = "retro_georgy_alarm_klok_v6_backup"
FAIL_COUNT_FILE = "/boot_fail_count.txt"
BOOT_MODE_FILE = "/boot_mode.txt"
FAILOVER_THRESHOLD = 3


def _read_fail_count():
    try:
        with open(FAIL_COUNT_FILE, "r") as f:
            return int((f.read() or "0").strip())
    except Exception:
        return 0


def _write_fail_count(value):
    try:
        with open(FAIL_COUNT_FILE, "w") as f:
            f.write(str(int(value)))
    except Exception:
        pass


def _write_boot_mode(value):
    try:
        with open(BOOT_MODE_FILE, "w") as f:
            f.write(str(value))
    except Exception:
        pass


def _boot_module(module_name):
    mod = __import__(module_name)
    app = mod.App()
    # App is succesvol gestart; reset fail counter.
    _write_fail_count(0)
    app.run()


gc.collect()
forced_backup = False

while True:
    fail_count = _read_fail_count()
    use_backup = forced_backup or (fail_count >= FAILOVER_THRESHOLD)
    target = BACKUP_MODULE if use_backup else PRIMARY_MODULE

    try:
        print("BOOT:", target, "(fails={})".format(fail_count))
        _write_boot_mode("backup" if use_backup else "primary")
        _boot_module(target)
        # app.run() hoort niet terug te keren; behandel return als fout.
        raise RuntimeError("App run() returned unexpectedly")
    except Exception as e:
        fail_count = min(99, _read_fail_count() + 1)
        _write_fail_count(fail_count)
        if (not forced_backup) and fail_count >= FAILOVER_THRESHOLD:
            forced_backup = True
            print("SAFE MODE: overschakelen naar backup app")
        print("FATAL in main:", e)
        gc.collect()
        time.sleep(2)
