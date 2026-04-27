import time

import gc
import json


def _send_all(sock, data):
    view = memoryview(data)
    while len(view):
        sent = sock.send(view)
        if sent is None or sent <= 0:
            break
        view = view[sent:]


def _send_html_response(sock, filename):
    _send_all(sock, b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
    with open(filename, "rb") as f:
        while True:
            chunk = f.read(512)
            if not chunk:
                break
            _send_all(sock, chunk)


def _json(payload):
    return ("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n" + json.dumps(payload)).encode()


def _parse(req):
    parts = req.split("\r\n\r\n", 1)
    if len(parts) < 2 or not parts[1]:
        return {}
    try:
        return json.loads(parts[1])
    except:
        return {}


def _request(c):
    try:
        c.settimeout(0.5)
    except:
        pass

    try:
        data = c.recv(1024)
    except:
        return ""

    if b"\r\n\r\n" not in data:
        try:
            extra = c.recv(1024)
            if extra:
                data += extra
        except:
            pass

    return data.decode("utf-8", "ignore")


def serve_request(app, c, html_file):
    req = _request(c)
    line = req.split("\r\n", 1)[0]
    parts = line.split(" ")
    method = parts[0] if len(parts) > 0 else ""
    path = parts[1] if len(parts) > 1 else ""
    path_no_query = path.split("?", 1)[0]

    if method == "GET" and path_no_query == "/":
        try:
            _send_html_response(c, html_file)
        except Exception as e:
            c.send(("HTTP/1.1 500 Internal Server Error\r\nConnection: close\r\n\r\n{}".format(e)).encode())
        return

    if method == "GET" and path == "/api/time":
        t = app.clock.read_time()
        c.send(_json({
            "year": t[0], "month": t[1], "day": t[2],
            "hour": t[3], "minute": t[4], "second": t[5],
            "weekday": t[6], "weekday_name": app._weekday_name(t[6]),
            "timezone_name": app.clock.timezone_name,
            "timezone_label": app.clock.timezone_label(),
            "alarm_tone": app.tone,
            "alarm_volume": app.volume,
            "alarm_schedule": app.alarm_schedule,
            "alarm_tones": app._get_alarm_tone_options(),
        }))
        return

    if method == "POST" and path == "/api/set-time":
        data = _parse(req)
        now = app.clock.read_time()
        app.clock.set_time(now[0], now[1], now[2], int(data.get("hour", now[3])) % 24, int(data.get("minute", now[4])) % 60, int(data.get("second", 0)) % 60)
        c.send(_json({"ok": True}))
        return

    if method == "POST" and path == "/api/set-timezone":
        data = _parse(req)
        timezone = data.get("timezone", "Europe/Amsterdam")
        app.clock.set_timezone(timezone)
        if app.config:
            app.config.set("ntp", "timezone", timezone)
        c.send(_json({"ok": True}))
        return

    if method == "POST" and path == "/api/sync-ntp":
        ok = app.clock.sync_ntp()
        if ok:
            app._ntp_synced_once = True
            app.next_ntp_sync_ms = None
        c.send(_json({"ok": bool(ok)}))
        return

    if method == "POST" and path == "/api/set-alarm-settings":
        data = _parse(req)
        tone = app._normalize_tone_key(data.get("tone", "classic"))
        volume = int(data.get("volume", 70) or 70)
        app.tone = tone
        app.volume = max(0, min(100, volume))
        if app.config:
            app.config.set("alarm_sound", "tone", app.tone)
            app.config.set("alarm_sound", "volume", app.volume)
        c.send(_json({"ok": True}))
        return

    if method == "POST" and path == "/api/set-alarm-schedule":
        data = _parse(req)
        schedule = data.get("alarm_schedule", data.get("schedule", {}))
        app.alarm_schedule = app._normalize_alarm_schedule(schedule)
        if app.config:
            app.config.config["alarm_schedule"] = app.alarm_schedule
            app.config.save()
        c.send(_json({"ok": True}))
        return

    if method == "POST" and path == "/api/test-alarm":
        data = _parse(req)
        seconds = int(data.get("seconds", 10) or 10)
        seconds = max(1, min(60, seconds))
        app.active_tone = app._tone_now()
        app.alarm_started_ms = time.ticks_ms()
        app.alarm_until = time.ticks_add(time.ticks_ms(), seconds * 1000)
        c.send(_json({"ok": True}))
        return

    if method == "GET" and path == "/api/ping":
        c.send(_json({"ok": True}))
        return

    c.send(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
    gc.collect()