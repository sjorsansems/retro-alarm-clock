from machine import Pin, PWM, SoftI2C
import framebuf
import time

# ====== PIN CONFIG ======
SDA_PIN = 21
SCL_PIN = 22
UP_BUTTON_PIN = 13
DOWN_BUTTON_PIN = 12
SET_BUTTON_PIN = 14
BUZZER_PIN = 27

WIDTH = 128
HEIGHT = 64
SH1106_COL_OFFSET = 2


# ====== DISPLAY ======
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
        for cmd in (
            0xAE, 0xD5, 0x80, 0xA8, self.height - 1, 0xD3, 0x00, 0x40,
            0xAD, 0x8B, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0x7F, 0xD9, 0x22,
            0xDB, 0x35, 0xA4, 0xA6, 0xAF
        ):
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
    return SoftI2C(
        sda=Pin(SDA_PIN, Pin.PULL_UP),
        scl=Pin(SCL_PIN, Pin.PULL_UP),
        freq=100000
    )


def init_display(i2c):
    devices = i2c.scan()
    print("I2C:", devices)

    if not devices:
        print("Geen display gevonden!")
        return None

    addr = 0x3C if 0x3C in devices else devices[0]
    return SH1106_I2C(WIDTH, HEIGHT, i2c, addr)


# ====== ALARM CLOCK ======
class AlarmClock:

    def __init__(self):
        self.i2c = init_i2c()
        self.display = init_display(self.i2c)

        # Knoppen
        self.btn_up = Pin(UP_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_down = Pin(DOWN_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_set = Pin(SET_BUTTON_PIN, Pin.IN, Pin.PULL_UP)

        # Buzzer
        self.buzzer = PWM(Pin(BUZZER_PIN))
        self.buzzer.freq(2000)
        self.buzzer.duty(0)

        # Alarm instellingen (in RAM)
        self.alarm_hour = 7
        self.alarm_minute = 0
        self.alarm_enabled = True

        # State
        self.mode = "display"
        self.edit_hour = 0
        self.edit_minute = 0
        self.edit_alarm_hour = self.alarm_hour
        self.edit_alarm_minute = self.alarm_minute
        self.alarm_ringing = False

        # debounce
        self.last_button_time = 0

        # interrupts
        self.btn_up.irq(trigger=Pin.IRQ_FALLING, handler=lambda p: self.on_up())
        self.btn_down.irq(trigger=Pin.IRQ_FALLING, handler=lambda p: self.on_down())
        self.btn_set.irq(trigger=Pin.IRQ_FALLING, handler=lambda p: self.on_set())

    def debounce(self):
        now = time.ticks_ms()
        if now - self.last_button_time < 200:
            return False
        self.last_button_time = now
        return True

    def get_time(self):
        return time.localtime()

    # ===== BUTTONS =====
    def on_up(self):
        if not self.debounce():
            return

        if self.mode == "display":
            self.mode = "set_time"
            t = self.get_time()
            self.edit_hour = t[3]
            self.edit_minute = t[4]

        elif self.mode == "set_time":
            self.edit_hour = (self.edit_hour + 1) % 24

        elif self.mode == "set_alarm":
            self.edit_alarm_hour = (self.edit_alarm_hour + 1) % 24

    def on_down(self):
        if not self.debounce():
            return

        if self.mode == "display":
            self.mode = "set_alarm"

        elif self.mode == "set_time":
            self.edit_minute = (self.edit_minute + 1) % 60

        elif self.mode == "set_alarm":
            self.edit_alarm_minute = (self.edit_alarm_minute + 1) % 60

    def on_set(self):
        if not self.debounce():
            return

        if self.alarm_ringing:
            self.stop_alarm()
            return

        if self.mode == "set_time":
            t = list(self.get_time())
            t[3] = self.edit_hour
            t[4] = self.edit_minute
            t[5] = 0
            time.mktime(tuple(t))  # update interne klok
            self.mode = "display"

        elif self.mode == "set_alarm":
            self.alarm_hour = self.edit_alarm_hour
            self.alarm_minute = self.edit_alarm_minute
            self.mode = "display"

    # ===== ALARM =====
    def check_alarm(self):
        if not self.alarm_enabled:
            return

        t = self.get_time()
        if t[3] == self.alarm_hour and t[4] == self.alarm_minute:
            self.alarm_ringing = True

    def stop_alarm(self):
        self.buzzer.duty(0)
        self.alarm_ringing = False

    # ===== DRAW =====
    def draw_display(self):
        self.display.fill(0)

        t = self.get_time()
        time_str = f"{t[3]:02d}:{t[4]:02d}"
        self.display.text(time_str, 30, 20, 1)

        self.display.text(f"{t[5]:02d}s", 100, 25, 1)

        self.display.text(
            f"ALARM {self.alarm_hour:02d}:{self.alarm_minute:02d}",
            10, 40, 1
        )

        self.display.text("UP TIJD DOWN ALARM", 0, 55, 1)
        self.display.show()

    def draw_set_time(self):
        self.display.fill(0)
        self.display.text("SET TIJD", 30, 5, 1)
        self.display.text(f"{self.edit_hour:02d}:{self.edit_minute:02d}", 35, 25, 1)
        self.display.show()

    def draw_set_alarm(self):
        self.display.fill(0)
        self.display.text("SET ALARM", 25, 5, 1)
        self.display.text(f"{self.edit_alarm_hour:02d}:{self.edit_alarm_minute:02d}", 35, 25, 1)
        self.display.show()

    def draw_alarm(self):
        self.display.fill(0)
        self.display.text("ALARM!!!", 30, 20, 1)
        self.display.text("SET = STOP", 20, 40, 1)
        self.display.show()

    # ===== LOOP =====
    def run(self):
        frame = 0

        while True:
            self.check_alarm()

            if self.alarm_ringing:
                self.draw_alarm()
                self.buzzer.duty(512 if frame % 10 < 5 else 0)

            elif self.mode == "display":
                self.draw_display()

            elif self.mode == "set_time":
                self.draw_set_time()

            elif self.mode == "set_alarm":
                self.draw_set_alarm()

            frame += 1
            time.sleep(0.2)


# ===== MAIN =====
clock = AlarmClock()
clock.run()