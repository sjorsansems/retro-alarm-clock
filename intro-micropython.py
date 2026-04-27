from machine import Pin, I2C, SoftI2C
import framebuf
import time

# ====== Instellingen ======
WIDTH = 128
HEIGHT = 64
I2C_ID = 0
# ESP32 standaard I2C pinnen:
# SDA = GPIO21, SCL = GPIO22
# Je kunt op ESP32 vrijwel elke GPIO kiezen voor I2C.
USE_SOFT_I2C = False
SDA_PIN = 21
SCL_PIN = 22
I2C_FREQ = 100_000
OLED_ADDR = None      # None = probeer beide 0x3C en 0x3D
DISPLAY_TYPE = "SH1106"  # 1.3 inch OLED is meestal SH1106
SH1106_COL_OFFSET = 2      # Vaak 2; probeer 0 als beeld verschoven/ruis is
ANIM_WIDTH = 122
ANIM_HEIGHT = 60
# ==========================


def create_i2c():
    if USE_SOFT_I2C:
        # Met interne pull-ups (workaround zonder externe weerstanden)
        return SoftI2C(sda=Pin(SDA_PIN, pull=Pin.PULL_UP), 
                       scl=Pin(SCL_PIN, pull=Pin.PULL_UP), 
                       freq=I2C_FREQ)
    return I2C(I2C_ID, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)


class SSD1306_I2C(framebuf.FrameBuffer):
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
            0xAE,       # display off
            0x20, 0x00, # horizontal addressing mode
            0xB0,
            0xC8,
            0x00,
            0x10,
            0x40,
            0x81, 0xCF,
            0xA1,
            0xA6,
            0xA8, self.height - 1,
            0xA4,
            0xD3, 0x00,
            0xD5, 0x80,
            0xD9, 0xF1,
            0xDA, 0x12 if self.height == 64 else 0x02,
            0xDB, 0x40,
            0x8D, 0x14,
            0xAF,       # display on
        ):
            self._write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        self._write_cmd(0x21)
        self._write_cmd(0)
        self._write_cmd(self.width - 1)
        self._write_cmd(0x22)
        self._write_cmd(0)
        self._write_cmd(self.pages - 1)
        self._write_data(self.buffer)


class SH1106_I2C(framebuf.FrameBuffer):
    # Veel 1.3 inch OLED modules gebruiken SH1106 i.p.v. SSD1306.
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
            0xAE,
            0xD5, 0x80,
            0xA8, self.height - 1,
            0xD3, 0x00,
            0x40,
            0xAD, 0x8B,
            0xA1,
            0xC8,
            0xDA, 0x12,
            0x81, 0x7F,
            0xD9, 0x22,
            0xDB, 0x35,
            0xA4,
            0xA6,
            0xAF,
        ):
            self._write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        # SH1106 gebruikt page addressing; vaak met kolom-offset +2.
        for page in range(self.pages):
            self._write_cmd(0xB0 + page)
            col = SH1106_COL_OFFSET
            self._write_cmd(col & 0x0F)            # lagere kolom (offset)
            self._write_cmd(0x10 | (col >> 4))     # hogere kolom
            start = self.width * page
            end = start + self.width
            self._write_data(self.buffer[start:end])


def make_display(i2c, addr, display_type):
    display_type = display_type.upper()
    if display_type == "SH1106":
        return SH1106_I2C(WIDTH, HEIGHT, i2c, addr)
    return SSD1306_I2C(WIDTH, HEIGHT, i2c, addr)


def detect_address(i2c):
    if OLED_ADDR is not None:
        return OLED_ADDR
    
    # Kleine pauze voor stabiliteit
    time.sleep_ms(100)
    devices = i2c.scan()
    print(f"[I2C Scan] Gevonden apparaten: {devices}")
    
    if not devices:
        print("[DEBUG] Geen I2C apparaten gevonden!")
        print("[DEBUG] Controleer:")
        print("  - Is het OLED module aangesloten?")
        print(f"  - SDA op GPIO {SDA_PIN}, SCL op GPIO {SCL_PIN}?")
        print("  - Pull-up weerstanden (4.7kΩ) aanwezig?")
        print("  - Voeding correct (3.3V)?")
        raise RuntimeError("Geen I2C apparaten gevonden. Controleer bedrading.")
    
    # Probeer standaard adressen
    if 0x3C in devices:
        print("[OK] OLED gevonden op 0x3C")
        return 0x3C
    if 0x3D in devices:
        print("[OK] OLED gevonden op 0x3D")
        return 0x3D
    
    # Anders neem eerste adres
    print(f"[WARNING] Probeer eerste adres: 0x{devices[0]:02X}")
    return devices[0]


def splash(oled, addr):
    oled.fill(0)
    oled.rect(0, 0, WIDTH, HEIGHT, 1)
    oled.text("I2C 0x%02X" % addr, 28, 22)
    oled.text(DISPLAY_TYPE, 34, 36)
    oled.show()
    time.sleep(1.5)


# 5x7 bitmap-font voor groot pixel-logo.
BIG_FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "M": ("10001", "11011", "10101", "10001", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}


def draw_big_text(oled, text, x, y, scale=2, color=1):
    cursor_x = x
    for ch in text:
        glyph = BIG_FONT.get(ch, BIG_FONT[" "])
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "1":
                    oled.fill_rect(cursor_x + gx * scale, y + gy * scale, scale, scale, color)
        cursor_x += (5 * scale) + scale


def big_text_width(text, scale):
    if not text:
        return 0
    return len(text) * (5 * scale + scale) - scale


class OffsetCanvas:
    # Tekent in een gecentreerd viewport zonder alle scene-code te herschrijven.
    def __init__(self, base, ox, oy, width, height):
        self.base = base
        self.ox = ox
        self.oy = oy
        self.width = width
        self.height = height

    def pixel(self, x, y, c=1):
        self.base.pixel(self.ox + x, self.oy + y, c)

    def rect(self, x, y, w, h, c=1):
        self.base.rect(self.ox + x, self.oy + y, w, h, c)

    def fill_rect(self, x, y, w, h, c=1):
        self.base.fill_rect(self.ox + x, self.oy + y, w, h, c)

    def hline(self, x, y, w, c=1):
        self.base.hline(self.ox + x, self.oy + y, w, c)

    def vline(self, x, y, h, c=1):
        self.base.vline(self.ox + x, self.oy + y, h, c)

    def line(self, x1, y1, x2, y2, c=1):
        self.base.line(self.ox + x1, self.oy + y1, self.ox + x2, self.oy + y2, c)

    def text(self, text, x, y, c=1):
        self.base.text(text, self.ox + x, self.oy + y, c)


def intro_animation(oled):
    # Pixel-art intro: RETRO zoomt in, daarna BAM en GEORGY verschijnt.
    zoom_scales = (6, 5, 4, 3, 2)
    tick = 0

    for scale in zoom_scales:
        for _ in range(2):
            oled.fill(0)
            draw_starfield(oled, tick)
            w = big_text_width("RETRO", scale)
            h = 7 * scale
            x = (WIDTH - w) // 2
            y = (HEIGHT - h) // 2
            draw_big_text(oled, "RETRO", x, y, scale)
            for i in range(0, WIDTH, 8):
                oled.pixel(i, (tick + i) % HEIGHT, 1)
            oled.show()
            time.sleep_ms(90)
            tick += 1

    for frame in range(12):
        oled.fill(0)
        draw_starfield(oled, tick + frame)
        draw_big_text(oled, "RETRO", (WIDTH - big_text_width("RETRO", 2)) // 2, 8, 2)
        scan_y = 8 + (frame % 14)
        oled.hline(10, scan_y, 108, 1)
        if frame % 3 == 0:
            oled.rect(8, 6, 112, 20, 1)
        oled.show()
        time.sleep_ms(75)

    for frame in range(18):
        oled.fill(0)
        draw_starfield(oled, 30 + frame)
        draw_big_text(oled, "RETRO", (WIDTH - big_text_width("RETRO", 2)) // 2, 8, 2)
        if frame < 5 and frame % 2 == 0:
            draw_big_text(oled, "BAM", (WIDTH - big_text_width("BAM", 2)) // 2, 28, 2)
            for ray in range(0, 32, 4):
                oled.line(64, 34, 64 - ray, 34 - ray // 2, 1)
                oled.line(64, 34, 64 + ray, 34 - ray // 2, 1)
                oled.line(64, 34, 64 - ray, 34 + ray // 2, 1)
                oled.line(64, 34, 64 + ray, 34 + ray // 2, 1)
        if frame >= 4:
            g_scale = 3 if frame < 9 else 2
            gx = (WIDTH - big_text_width("GEORGY", g_scale)) // 2
            gy = 30 if g_scale == 3 else 36
            draw_big_text(oled, "GEORGY", gx, gy, g_scale)
        oled.show()
        time.sleep_ms(85)

    for frame in range(16):
        oled.fill(0)
        draw_starfield(oled, 60 + frame)
        draw_big_text(oled, "RETRO", (WIDTH - big_text_width("RETRO", 2)) // 2, 8, 2)
        draw_big_text(oled, "GEORGY", (WIDTH - big_text_width("GEORGY", 2)) // 2, 36, 2)
        if frame % 4 < 2:
            oled.rect(4, 4, 120, 56, 1)
        oled.show()
        time.sleep_ms(85)


def draw_starfield(oled, tick):
    # Kleine bewegende sterren voor retro sfeer.
    for i in range(16):
        sx = (i * 23 + tick * (2 + (i % 3))) % oled.width
        sy = (i * 37 + tick * (1 + (i % 2))) % oled.height
        oled.pixel(sx, sy, 1)


def draw_apple_scene(oled, frame):
    x = 18
    y = 14
    oled.rect(x, y, 52, 32, 1)
    oled.fill_rect(x + 4, y + 4, 44, 18, 1)
    oled.fill_rect(x + 6, y + 6, 40, 14, 0)
    for i in range(5):
        oled.hline(x + 8, y + 8 + i * 2, 36 - (frame % 4), 1)
    oled.fill_rect(x + 6, y + 24, 40, 5, 1)
    oled.rect(x + 20, y + 32, 12, 6, 1)
    oled.text("A>", x + 9, y + 10)


def draw_dos_scene(oled, frame):
    x = 12
    y = 12
    oled.rect(x, y, 60, 36, 1)
    oled.fill_rect(x + 4, y + 4, 52, 22, 1)
    oled.fill_rect(x + 6, y + 6, 48, 18, 0)
    oled.text("C:\\>", x + 9, y + 10)
    if frame % 6 < 3:
        oled.fill_rect(x + 33, y + 16, 4, 1, 1)
    oled.rect(x + 4, y + 29, 52, 6, 1)
    for k in range(0, 52, 6):
        oled.vline(x + 5 + k, y + 30, 4, 1)


def draw_c64_scene(oled, frame):
    x = 14
    y = 11
    oled.rect(x, y, 58, 20, 1)
    oled.fill_rect(x + 3, y + 3, 52, 14, 1)
    oled.fill_rect(x + 5, y + 5, 48, 10, 0)
    oled.text("READY.", x + 8, y + 7)
    oled.fill_rect(x - 2, y + 24, 64, 16, 1)
    oled.fill_rect(x, y + 26, 60, 12, 0)
    for row in range(2):
        for col in range(10):
            key_x = x + 2 + col * 6
            key_y = y + 27 + row * 6
            oled.rect(key_x, key_y, 5, 4, 1)
    oled.hline(x + 6, y + 41, 48 - (frame % 5), 1)


def draw_gameboy_scene(oled, frame):
    x = 24
    y = 6
    oled.rect(x, y, 42, 52, 1)
    oled.fill_rect(x + 7, y + 7, 28, 18, 1)
    oled.fill_rect(x + 9, y + 9, 24, 14, 0)
    oled.text("8BIT", x + 11, y + 13)
    oled.fill_rect(x + 8, y + 31, 8, 2, 1)
    oled.fill_rect(x + 11, y + 28, 2, 8, 1)
    oled.fill_rect(x + 27, y + 31, 4, 4, 1)
    oled.fill_rect(x + 33, y + 36, 4, 4, 1)
    if frame % 8 < 4:
        oled.fill_rect(x + 9, y + 39, 4, 2, 1)
    else:
        oled.fill_rect(x + 15, y + 39, 4, 2, 1)


def draw_nintendo_scene(oled, frame):
    x = 12
    y = 20
    oled.rect(x, y, 72, 28, 1)
    oled.fill_rect(x + 2, y + 2, 68, 24, 1)
    oled.fill_rect(x + 4, y + 4, 64, 20, 0)
    oled.fill_rect(x + 10, y + 10, 10, 2, 1)
    oled.fill_rect(x + 14, y + 6, 2, 10, 1)
    oled.fill_rect(x + 46, y + 8, 6, 6, 1)
    oled.fill_rect(x + 56, y + 12, 6, 6, 1)
    oled.rect(x + 26, y + 9, 12, 8, 1)
    if frame % 6 < 3:
        oled.text("GO", x + 27, y + 10)


def draw_mario_scene(oled, frame):
    # Platformer scene met springende held en munt.
    ground_y = oled.height - 10
    oled.hline(0, ground_y, oled.width, 1)
    oled.hline(0, ground_y + 1, oled.width, 1)
    for bx in (22, 34, 46):
        oled.rect(bx, 28, 10, 8, 1)
    coin_y = 18 + (frame % 6 < 3)
    oled.rect(39, coin_y, 4, 6, 1)
    hero_x = 8 + (frame * 3) % 84
    jump = 0
    if 24 < hero_x < 54:
        jump = 8 - abs(39 - hero_x) // 2
    hero_y = ground_y - 10 - max(0, jump)
    oled.fill_rect(hero_x, hero_y, 6, 6, 1)
    oled.fill_rect(hero_x + 1, hero_y + 1, 4, 2, 0)


def draw_donkey_arcade_scene(oled, frame):
    # Arcade-style ladders, platformen en een rollend vat.
    for i, y in enumerate((18, 30, 42, 54)):
        slope = 1 if i % 2 == 0 else -1
        for x in range(0, oled.width, 4):
            yy = y + (x // 18) * slope
            oled.pixel(x, yy, 1)
            oled.pixel(x + 1, yy, 1)
    for lx in (26, 62, 92):
        oled.vline(lx, 21, 8, 1)
        oled.vline(lx, 33, 8, 1)
        oled.vline(lx, 45, 8, 1)
    monkey_x = 8
    monkey_y = 8
    oled.fill_rect(monkey_x, monkey_y, 10, 7, 1)
    barrel_x = (frame * 5) % (oled.width - 12)
    barrel_y = 18 + (barrel_x // 18)
    oled.rect(barrel_x, barrel_y, 6, 4, 1)
    hero_y = 46 - ((frame // 5) % 2) * 12
    oled.fill_rect(108, hero_y, 5, 7, 1)


def draw_pong_scene(oled, frame):
    mid = oled.width // 2
    oled.vline(mid, 0, oled.height, 1)
    left_y = 18 + (frame % 10)
    right_y = 28 - (frame % 10)
    oled.fill_rect(4, left_y, 3, 14, 1)
    oled.fill_rect(oled.width - 7, right_y, 3, 14, 1)
    bx = 20 + (frame * 5) % 88
    by = 10 + ((frame * 3) % 36)
    oled.fill_rect(bx, by, 3, 3, 1)
    oled.text("03", 44, 3)
    oled.text("07", 74, 3)


def draw_space_invaders_scene(oled, frame):
    shift = (frame // 2) % 14
    direction = 1 if (frame // 14) % 2 == 0 else -1
    base_x = 18 + shift * direction
    for row in range(3):
        for col in range(6):
            x = base_x + col * 14
            y = 10 + row * 10
            oled.rect(x, y, 8, 5, 1)
            if (frame + col + row) % 4 < 2:
                oled.pixel(x + 2, y + 6, 1)
                oled.pixel(x + 5, y + 6, 1)
    ship_x = 56 + (frame % 12 - 6)
    oled.fill_rect(ship_x, 56, 12, 4, 1)
    if frame % 5 == 0:
        oled.vline(ship_x + 6, 48, 7, 1)


def draw_moonstone_scene(oled, frame):
    # Dark fantasy, geinspireerd op Amiga-era sfeer.
    oled.fill_rect(0, oled.height - 24, oled.width, 24, 1)
    oled.fill_rect(0, oled.height - 24, oled.width, 24, 0)
    moon_x = 92
    moon_y = 12
    oled.fill_rect(moon_x, moon_y, 14, 14, 1)
    oled.fill_rect(moon_x + 3, moon_y + 2, 10, 10, 0)
    tower_x = 20
    oled.rect(tower_x, 14, 16, 34, 1)
    oled.vline(tower_x + 8, 6, 8, 1)
    knight_x = 54 + (frame % 12)
    oled.fill_rect(knight_x, 38, 5, 9, 1)
    oled.line(knight_x + 5, 40, knight_x + 10, 34, 1)
    oled.rect(78, 35, 9, 12, 1)
    if frame % 6 < 3:
        oled.vline(82, 28, 6, 1)


def draw_tetris_scene(oled, frame):
    bx = 34
    by = 8
    oled.rect(bx, by, 42, 50, 1)
    for y in range(12, 54, 8):
        oled.hline(bx + 2, y, 38, 1)
    for x in range(38, 72, 8):
        oled.vline(x, by + 2, 46, 1)
    stack = ((2, 5), (3, 5), (4, 5), (4, 4), (2, 4), (5, 5))
    for cx, cy in stack:
        oled.fill_rect(bx + 2 + cx * 8, by + 2 + cy * 8, 7, 7, 1)
    piece_y = 2 + (frame % 6)
    for dx, dy in ((0, 0), (1, 0), (1, 1), (2, 1)):
        oled.fill_rect(bx + 2 + dx * 8, by + 2 + piece_y * 4 + dy * 8, 7, 7, 1)


def draw_pac_scene(oled, frame):
    y = 30
    for x in range(10, 118, 12):
        oled.fill_rect(x, y + 4, 2, 2, 1)
    pac_x = 16 + (frame * 4) % 90
    oled.fill_rect(pac_x, y, 8, 8, 1)
    if frame % 4 < 2:
        oled.fill_rect(pac_x + 5, y + 2, 3, 4, 0)
    else:
        oled.fill_rect(pac_x + 3, y + 3, 5, 2, 0)
    ghost_x = pac_x + 22
    oled.fill_rect(ghost_x, y, 8, 8, 1)
    oled.pixel(ghost_x + 2, y + 2, 0)
    oled.pixel(ghost_x + 5, y + 2, 0)


def draw_asteroids_scene(oled, frame):
    ship_x = 18 + (frame * 2) % 90
    ship_y = 44 - ((frame // 3) % 6)
    oled.line(ship_x, ship_y + 4, ship_x + 10, ship_y, 1)
    oled.line(ship_x, ship_y + 4, ship_x + 10, ship_y + 8, 1)
    oled.line(ship_x + 10, ship_y, ship_x + 10, ship_y + 8, 1)
    for i in range(6):
        ax = (i * 21 + frame * (i + 2)) % oled.width
        ay = (i * 11 + frame * (i + 1)) % 36
        oled.rect(ax, ay, 6, 5, 1)
    if frame % 3 == 0:
        oled.hline(ship_x + 11, ship_y + 4, 8, 1)


def retro_animation(oled):
    scenes = (
        draw_apple_scene,
        draw_dos_scene,
        draw_c64_scene,
        draw_gameboy_scene,
        draw_nintendo_scene,
        draw_mario_scene,
        draw_donkey_arcade_scene,
        draw_pong_scene,
        draw_space_invaders_scene,
        draw_moonstone_scene,
        draw_tetris_scene,
        draw_pac_scene,
        draw_asteroids_scene,
    )

    scene_ox = (WIDTH - ANIM_WIDTH) // 2
    scene_oy = (HEIGHT - ANIM_HEIGHT) // 2
    canvas = OffsetCanvas(oled, scene_ox, scene_oy, ANIM_WIDTH, ANIM_HEIGHT)

    for draw_fn in scenes:
        for frame in range(18):
            oled.fill(0)
            draw_starfield(canvas, frame)
            draw_fn(canvas, frame)
            oled.show()
            time.sleep_ms(85)


def main():
    i2c = create_i2c()
    addr = detect_address(i2c)
    oled = make_display(i2c, addr, DISPLAY_TYPE)

    intro_animation(oled)

    while True:
        retro_animation(oled)


if __name__ == "__main__":
    main()
