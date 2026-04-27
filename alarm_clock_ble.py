"""
ESP32 Alarmklok met Bluetooth (BLE) Controle
Verbind met je telefoon en stel tijd/alarm in via BLE
Instellingen worden geladen uit config.json
"""

from machine import Pin, I2C, PWM, SoftI2C
import framebuf
import time
import json
import bluetooth
from ble_advertising import advertising_payload
from micropython import const

# Import config manager
try:
    from config_manager import ConfigManager
except ImportError:
    ConfigManager = None

# ====== PIN CONFIGURATIE ======
SDA_PIN = 21
SCL_PIN = 22
I2C_FREQ = 100_000

UP_BUTTON_PIN = 13
DOWN_BUTTON_PIN = 12
SET_BUTTON_PIN = 14
BUZZER_PIN = 27

WIDTH = 128
HEIGHT = 64
DISPLAY_TYPE = "SH1106"
SH1106_COL_OFFSET = 2

# ====== BLE UUIDs ======
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

_FLAG_READ = const(0x02)
_FLAG_WRITE = const(0x04)
_FLAG_NOTIFY = const(0x10)

# Eigen service UUIDs
_ALARM_SERVICE_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef0")
_TIME_CHAR_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef1")
_ALARM_CHAR_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef2")
_STATUS_CHAR_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef3")

# ====== DISPLAY DRIVERS ======

class SH1106_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self._init_display()

    def _write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes((0x80, cmd)))

    def _write_data(self, data):
        self.i2c.writeto(self.addr, b"\x40" + data)

    def _init_display(self):
        for cmd in (0xAE, 0xD5, 0x80, 0xA8, self.height - 1, 0xD3, 0x00, 0x40,
                   0xAD, 0x8B, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0x7F, 0xD9, 0x22,
                   0xDB, 0x35, 0xA4, 0xA6, 0xAF):
            self._write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        for page in range(self.pages):
            self._write_cmd(0xB0 + page)
            col = SH1106_COL_OFFSET
            self._write_cmd(col & 0x0F)
            self._write_cmd(0x10 | (col >> 4))
            start = self.width * page
            end = start + self.width
            self._write_data(self.buffer[start:end])


def init_i2c():
    return SoftI2C(sda=Pin(SDA_PIN, pull=Pin.PULL_UP),
                   scl=Pin(SCL_PIN, pull=Pin.PULL_UP),
                   freq=I2C_FREQ)


def init_display(i2c):
    try:
        devices = i2c.scan()
        addr = 0x3C if 0x3C in devices else (0x3D if 0x3D in devices else (devices[0] if devices else None))
        if addr is None:
            return None
        return SH1106_I2C(WIDTH, HEIGHT, i2c, addr)
    except:
        return None


# ====== DS3231 RTC MODULE ======

class DS3231:
    def __init__(self, i2c, addr=0x68):
        self.i2c = i2c
        self.addr = addr
    
    def read_time(self):
        try:
            data = self.i2c.readfrom(self.addr, 7)
            sec = self._bcd_to_int(data[0])
            minute = self._bcd_to_int(data[1])
            hour = self._bcd_to_int(data[2] & 0x3F)
            day = self._bcd_to_int(data[3])
            month = self._bcd_to_int(data[5] & 0x1F)
            year = self._bcd_to_int(data[6]) + 2000
            weekday = data[4]
            return (year, month, day, hour, minute, sec, weekday, 0)
        except:
            return (2024, 1, 1, 0, 0, 0, 1, 0)
    
    def set_time(self, year, month, day, hour, minute, second):
        try:
            data = bytearray(7)
            data[0] = self._int_to_bcd(second)
            data[1] = self._int_to_bcd(minute)
            data[2] = self._int_to_bcd(hour)
            data[3] = self._int_to_bcd(day)
            data[5] = self._int_to_bcd(month)
            data[6] = self._int_to_bcd(year - 2000)
            self.i2c.writeto(self.addr, bytes([0x00]) + data)
            return True
        except:
            return False
    
    def _bcd_to_int(self, bcd):
        return (bcd >> 4) * 10 + (bcd & 0x0F)
    
    def _int_to_bcd(self, val):
        return ((val // 10) << 4) | (val % 10)


# ====== CONFIGURATIE BEHEER ======

class AlarmConfig:
    def __init__(self, config_manager=None):
        """
        config_manager: ConfigManager object (optional)
        Gebruikt config_manager of default config.json
        """
        if config_manager:
            self.config_manager = config_manager
        else:
            if ConfigManager:
                self.config_manager = ConfigManager("config.json")
            else:
                self.config_manager = None
    
    def get(self, section, key=None, default=None):
        """Haal waarde uit config"""
        if self.config_manager:
            return self.config_manager.get(section, key, default)
        return default
    
    def set(self, section, key, value):
        """Stel waarde in config"""
        if self.config_manager:
            return self.config_manager.set(section, key, value)
        return False


# ====== BLE SERVER ======

class BLE_AlarmClock:
    def __init__(self, rtc, config, display=None):
        self.rtc = rtc
        self.config = config
        self.display = display
        
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._ble_irq)
        
        self.conn_handle = None
        self.register_services()
        self.advertise()
    
    def register_services(self):
        """Registreer BLE services"""
        
        # Time characteristic (write/read)
        time_char = (
            _TIME_CHAR_UUID,
            _FLAG_READ | _FLAG_WRITE | _FLAG_NOTIFY,
        )
        
        # Alarm characteristic (write/read)
        alarm_char = (
            _ALARM_CHAR_UUID,
            _FLAG_READ | _FLAG_WRITE | _FLAG_NOTIFY,
        )
        
        # Status characteristic (read/notify)
        status_char = (
            _STATUS_CHAR_UUID,
            _FLAG_READ | _FLAG_NOTIFY,
        )
        
        service = (
            _ALARM_SERVICE_UUID,
            (time_char, alarm_char, status_char),
        )
        
        self.handles = self.ble.gatts_register_services((service,))
        self.time_handle = self.handles[0][1]
        self.alarm_handle = self.handles[0][2]
        self.status_handle = self.handles[0][3]
    
    def advertise(self):
        """Start BLE advertising"""
        payload = advertising_payload(
            name="AlarmClock",
            services=[_ALARM_SERVICE_UUID],
        )
        self.ble.gap_advertise(100, payload)
        print("BLE Advertising gestart - zoek naar 'AlarmClock'")
    
    def _ble_irq(self, event, data):
        """BLE event handler"""
        if event == _IRQ_CENTRAL_CONNECT:
            self.conn_handle = data[0]
            print(f"BLE: Client verbonden (handle: {self.conn_handle})")
            if self.display:
                self.display.fill(0)
                self.display.text("BLE VERBONDEN!", 20, 25)
                self.display.show()
        
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self.conn_handle = None
            print("BLE: Client verbroken")
            self.advertise()
        
        elif event == _IRQ_GATTS_WRITE:
            handle = data[1]
            value = self.ble.gatts_read(handle)
            
            if handle == self.time_handle:
                self._handle_time_write(value)
            elif handle == self.alarm_handle:
                self._handle_alarm_write(value)
    
    def _handle_time_write(self, data):
        """Verwerk tijd schrijven via BLE"""
        try:
            # Format: "HH:MM" (5 bytes)
            time_str = data.decode('utf-8').strip()
            parts = time_str.split(':')
            if len(parts) == 2:
                hour = int(parts[0])
                minute = int(parts[1])
                
                current_time = self.rtc.read_time()
                self.rtc.set_time(current_time[0], current_time[1], current_time[2],
                                hour, minute, 0)
                
                response = f"TIJD: {hour:02d}:{minute:02d}"
                self.ble.gatts_write(self.status_handle, response.encode())
                print(f"Tijd ingesteld: {hour:02d}:{minute:02d}")
        except Exception as e:
            print(f"Fout bij tijd instellen: {e}")
    
    def _handle_alarm_write(self, data):
        """Verwerk alarm schrijven via BLE"""
        try:
            # Format: "HH:MM" (5 bytes)
            alarm_str = data.decode('utf-8').strip()
            parts = alarm_str.split(':')
            if len(parts) == 2:
                hour = int(parts[0])
                minute = int(parts[1])
                
                self.config.set("alarm", "hour", hour)
                self.config.set("alarm", "minute", minute)
                self.config.set("alarm", "enabled", True)
                
                response = f"ALARM: {hour:02d}:{minute:02d}"
                self.ble.gatts_write(self.status_handle, response.encode())
                print(f"Alarm ingesteld: {hour:02d}:{minute:02d}")
        except Exception as e:
            print(f"Fout bij alarm instellen: {e}")
    
    def update_status(self):
        """Update status karakteristiek"""
        try:
            current_time = self.rtc.read_time()
            hour, minute = current_time[3], current_time[4]
            alarm_hour = self.config.get("alarm_hour", 7)
            alarm_minute = self.config.get("alarm_minute", 0)
            
            status = f"T:{hour:02d}:{minute:02d} A:{alarm_hour:02d}:{alarm_minute:02d}"
            self.ble.gatts_write(self.status_handle, status.encode())
        except:
            pass


# ====== HOOFDAPPLICATIE ======

class AlarmClock:
    def __init__(self):
        self.i2c = init_i2c()
        self.display = init_display(self.i2c)
        self.rtc = DS3231(self.i2c)
        
        # Laad configuratie
        if ConfigManager:
            config_manager = ConfigManager("config.json")
        else:
            config_manager = None
        
        self.config = AlarmConfig(config_manager)
        
        # Knoppen (nog steeds beschikbaar)
        self.btn_up = Pin(UP_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_down = Pin(DOWN_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_set = Pin(SET_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        
        # Buzzer
        buzzer_volume = self.config.get("buzzer", "volume", 500)
        self.buzzer = PWM(Pin(BUZZER_PIN))
        self.buzzer.freq(buzzer_volume)
        self.buzzer.duty(0)
        
        # BLE Server
        self.ble_server = BLE_AlarmClock(self.rtc, self.config, self.display)
        
        self.alarm_ringing = False
        self.last_button_time = 0
        self.debounce_delay = 200
        
        self.btn_set.irq(trigger=Pin.IRQ_FALLING, handler=lambda p: self.on_set_pressed())
    
    def debounce_check(self):
        current_time = time.ticks_ms()
        if current_time - self.last_button_time < self.debounce_delay:
            return False
        self.last_button_time = current_time
        return True
    
    def on_set_pressed(self):
        """SET knop stopt alarm"""
        if not self.debounce_check():
            return
        if self.alarm_ringing:
            self.stop_alarm()
    
    def ring_alarm(self):
        self.alarm_ringing = True
        self.buzzer.duty(512)
    
    def stop_alarm(self):
        self.buzzer.duty(0)
        self.alarm_ringing = False
    
    def check_alarm(self):
        if not self.config.get("alarm", "enabled", False):
            return
        
        current_time = self.rtc.read_time()
        hour = current_time[3]
        minute = current_time[4]
        
        alarm_hour = self.config.get("alarm", "hour", 7)
        alarm_minute = self.config.get("alarm", "minute", 0)
        
        if hour == alarm_hour and minute == alarm_minute and not self.alarm_ringing:
            self.ring_alarm()
    
    def draw_display(self):
        if not self.display:
            return
        
        self.display.fill(0)
        
        current_time = self.rtc.read_time()
        hour, minute, second = current_time[3], current_time[4], current_time[5]
        
        # Grote tijd
        time_str = f"{hour:02d}:{minute:02d}"
        self.display.text(time_str, 30, 20, 1)
        self.display.text(f"{second:02d}s", 100, 25, 1)
        
        # Alarm info
        if self.config.get("alarm", "enabled", False):
            alarm_hour = self.config.get("alarm", "hour", 7)
            alarm_minute = self.config.get("alarm", "minute", 0)
            alarm_str = f"ALARM: {alarm_hour:02d}:{alarm_minute:02d}"
            self.display.text(alarm_str, 10, 40, 1)
        
        # Bluetooth status
        if self.ble_server.conn_handle is not None:
            self.display.text("BLE [VERBONDEN]", 10, 50, 1)
        else:
            self.display.text("BLE [WACHT]", 15, 50, 1)
        
        self.display.show()
    
    def draw_alarm_ringing(self):
        if not self.display:
            return
        
        self.display.fill(0)
        self.display.text("ALARM AFGAAN!", 25, 20, 1)
        self.display.text("SET = UITZETTEN", 15, 40, 1)
        self.display.show()
    
    def run(self):
        print("Alarmklok met Bluetooth gestart!")
        print("Zoek naar 'AlarmClock' in je Bluetooth instellingen")
        
        frame = 0
        while True:
            self.check_alarm()
            self.ble_server.update_status()
            
            if self.alarm_ringing:
                self.draw_alarm_ringing()
                if frame % 10 < 5:
                    self.buzzer.duty(512)
                else:
                    self.buzzer.duty(0)
            else:
                self.draw_display()
            
            frame += 1
            time.sleep(0.2)


# ====== MAIN ======

if __name__ == "__main__":
    try:
        clock = AlarmClock()
        clock.run()
    except Exception as e:
        print(f"Fout: {e}")
        import traceback
        traceback.print_exc()
