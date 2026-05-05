"""
WS2812B Neopixel LED driver for 8-LED strip
GPIO2 on ESP32-S3 DevKitC-1
"""
import machine
import time

try:
    import neopixel
except ImportError:
    neopixel = None

_HAS_BITSTREAM = hasattr(machine, "bitstream")
_WS2812_TIMING = (400, 850, 800, 450)

# Documented LED palette reference per alarm tone (1..9).
TONE_COLOR_SCHEMES = {
    "1": "Zelda: green->gold pulse (R 0..200, G 200..255, B 0)",
    "2": "Mario: red/yellow checker ((255,0,0) <-> (255,255,0))",
    "3": "Synthwave: neon pink->purple wave ((255,0,100) <-> (150,0,255))",
    "4": "Sonic: cyan/blue strobe ((0,200..250,255) <-> (0,100,200))",
    "5": "Metroid: orange->red by intensity (R 255, G 200..100, B 0)",
    "6": "Pokemon: yellow with red accents ((255,255,0) + (255,0,0))",
    "7": "Tetris: rainbow cycle (red->orange->yellow->green->blue->indigo->violet)",
    "8": "Moonstone: moon-blue and torch-gold pulse ((40,80,180) + (255,140,20))",
    "9": "Arcade: multicolor strobe (red->yellow->green->blue->magenta)",
}

class NeopixelDriver:
    def __init__(self, pin=2, num_leds=8):
        """Initialize WS2812B strip on specified pin."""
        if isinstance(pin, (tuple, list)):
            self.pins = [machine.Pin(p, machine.Pin.OUT) for p in pin]
            self.pin_numbers = tuple(pin)
        else:
            self.pins = [machine.Pin(pin, machine.Pin.OUT)]
            self.pin_numbers = (pin,)
        self.num_leds = num_leds
        # Keep a logical GRB buffer so existing theme code remains unchanged.
        self.buf = bytearray(num_leds * 3)  # RGB * 8
        # timing=1 -> 800kHz (WS2812/WS2812B)
        self.np = [neopixel.NeoPixel(pin_obj, self.num_leds, bpp=3, timing=1) for pin_obj in self.pins] if neopixel else None
        self.brightness = 92  # Start at 36% to avoid power supply overload
        self._clear()
        self.show()
    
    def _write(self):
        """Write current buffer to strip using hardware-backed NeoPixel timing."""
        if self.np is not None:
            for strip in self.np:
                for i in range(self.num_leds):
                    o = i * 3
                    g = self.buf[o]
                    r = self.buf[o + 1]
                    b = self.buf[o + 2]
                    strip[i] = (r, g, b)
                strip.write()
            return

        if _HAS_BITSTREAM:
            for pin_obj in self.pins:
                machine.bitstream(pin_obj, 0, _WS2812_TIMING, self.buf)
            return

        # Fallback: bit-bang timing for firmwares without neopixel module.
        for pin_obj in self.pins:
            for byte in self.buf:
                for i in range(8):
                    pin_obj(1)
                    if byte & (0x80 >> i):
                        time.sleep_us(4)
                    else:
                        time.sleep_us(2)
                    pin_obj(0)
                    time.sleep_us(2)
        time.sleep_us(50)
    
    def _clear(self):
        """Clear all LEDs."""
        self.buf[:] = bytearray(self.num_leds * 3)
    
    def set_pixel(self, index, r, g, b):
        """Set pixel color (applies brightness)."""
        if 0 <= index < self.num_leds:
            # Apply brightness
            r = (r * self.brightness) // 255
            g = (g * self.brightness) // 255
            b = (b * self.brightness) // 255
            self.buf[index * 3] = g  # WS2812 uses GRB format
            self.buf[index * 3 + 1] = r
            self.buf[index * 3 + 2] = b
    
    def set_all(self, r, g, b):
        """Set all LEDs to same color."""
        for i in range(self.num_leds):
            self.set_pixel(i, r, g, b)
    
    def show(self):
        """Update LED strip."""
        self._write()
    
    def clear(self):
        """Turn off all LEDs."""
        self._clear()
        self.show()
    
    def set_brightness(self, level):
        """Set brightness 0-255."""
        self.brightness = max(0, min(255, level))
    
    def sunrise_effect(self, duration_ms=120000, callback=None):
        """
        Sunrise effect: gradual warm white fade up.
        Default 2 minutes, can be interrupted by callback returning True.
        """
        start = time.ticks_ms()
        steps = 100
        
        for step in range(steps + 1):
            if callback and callback():  # Allow early exit
                break
            
            elapsed = time.ticks_diff(time.ticks_ms(), start)
            progress = min(1.0, elapsed / duration_ms)
            current_step = int(progress * steps)
            
            if current_step > step:
                # Warm sunrise colors: deep red → orange → yellow → white
                if current_step < 25:
                    # Deep red → orange
                    ratio = current_step / 25
                    r = int(100 + 155 * ratio)
                    g = int(20 + 80 * ratio)
                    b = 0
                elif current_step < 50:
                    # Orange → yellow
                    ratio = (current_step - 25) / 25
                    r = 255
                    g = int(100 + 155 * ratio)
                    b = 0
                elif current_step < 75:
                    # Yellow → warm white
                    ratio = (current_step - 50) / 25
                    r = 255
                    g = 255
                    b = int(100 * ratio)
                else:
                    # Full warm white
                    r, g, b = 255, 255, 150
                
                self.set_all(r, g, b)
                self.show()
            
            time.sleep_ms(50)
    
    # ============ PER-LIEDJE THEMA'S ============
    
    def theme_zelda(self, frame, intensity):
        """Liedje 1: Zelda - Green to gold pulsing."""
        pulse = abs((frame % 30) - 15) / 15  # 0-1-0
        r = int(200 * pulse)
        g = int(200 + 55 * pulse)
        b = 0
        self.set_all(r, g, b)
        self.show()
    
    def theme_mario(self, frame, intensity):
        """Liedje 2: Mario - Red/yellow jumping pattern."""
        phase = frame % 24
        for i in range(self.num_leds):
            if (i + phase // 6) % 2 == 0:
                # Red
                self.set_pixel(i, 255, 0, 0)
            else:
                # Yellow
                self.set_pixel(i, 255, 255, 0)
        self.show()
    
    def theme_synthwave(self, frame, intensity):
        """Liedje 3: Synthwave - Neon pink/purple wave."""
        for i in range(self.num_leds):
            wave = (frame + i * 4) % 40
            if wave < 20:
                # Pink
                brightness = wave / 20
                self.set_pixel(i, int(255 * brightness), 0, int(100 * brightness))
            else:
                # Purple
                brightness = (40 - wave) / 20
                self.set_pixel(i, int(150 * brightness), 0, int(255 * brightness))
        self.show()
    
    def theme_sonic(self, frame, intensity):
        """Liedje 4: Sonic - Cyan/blue speed strobe."""
        if (frame // 4) % 2 == 0:
            self.set_all(0, 200 + intensity // 2, 255)
        else:
            self.set_all(0, 100, 200)
        self.show()
    
    def theme_metroid(self, frame, intensity):
        """Liedje 5: Metroid - Orange to red intensity escalation."""
        r = 255
        g = max(100, 200 - intensity)
        b = 0
        self.set_all(r, g, b)
        self.show()
    
    def theme_pokemon(self, frame, intensity):
        """Liedje 6: Pokemon - Yellow flashing with red accents."""
        if (frame // 6) % 2 == 0:
            # Yellow
            for i in range(self.num_leds):
                if i % 3 == 0:
                    self.set_pixel(i, 255, 0, 0)  # Red
                else:
                    self.set_pixel(i, 255, 255, 0)  # Yellow
        else:
            self.set_all(255, 255, 0)
        self.show()
    
    def theme_tetris(self, frame, intensity):
        """Liedje 7: Tetris - Rainbow cycling."""
        colors = [
            (255, 0, 0),    # Red
            (255, 165, 0),  # Orange
            (255, 255, 0),  # Yellow
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
            (75, 0, 130),   # Indigo
            (148, 0, 211),  # Violet
        ]
        color_idx = (frame // 8) % len(colors)
        r, g, b = colors[color_idx]
        self.set_all(r, g, b)
        self.show()
    
    def theme_moonstone(self, frame, intensity):
        """Liedje 8: Moonstone - cold moonlight with moving torch highlights."""
        pulse = abs((frame % 24) - 12) / 12.0
        moon_r = 20 + int(30 * pulse)
        moon_g = 50 + int(40 * pulse)
        moon_b = 120 + int(90 * pulse)

        for i in range(self.num_leds):
            # Moving torch shimmer over a moon-blue base.
            torch_pos = (frame // 2 + i * 3) % self.num_leds
            if torch_pos == i or torch_pos == (i + 1) % self.num_leds:
                torch_boost = 80 + intensity // 3
                self.set_pixel(
                    i,
                    min(255, moon_r + torch_boost),
                    min(255, moon_g + 40),
                    max(0, moon_b - 90),
                )
            else:
                self.set_pixel(i, moon_r, moon_g, moon_b)
        self.show()
    
    def theme_arcade(self, frame, intensity):
        """Liedje 9: Arcade - Multicolor strobing."""
        colors = [
            (255, 0, 0),    # Red
            (255, 255, 0),  # Yellow
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
            (255, 0, 255),  # Magenta
        ]
        color_idx = (frame // 4) % len(colors)
        r, g, b = colors[color_idx]
        self.set_all(r, g, b)
        self.show()
    
    def get_theme_func(self, tone):
        """Return theme function for given tone (1-9)."""
        themes = {
            '1': self.theme_zelda,
            '2': self.theme_mario,
            '3': self.theme_synthwave,
            '4': self.theme_sonic,
            '5': self.theme_metroid,
            '6': self.theme_pokemon,
            '7': self.theme_tetris,
            '8': self.theme_moonstone,
            '9': self.theme_arcade,
        }
        return themes.get(str(tone), self.theme_zelda)  # Default to Zelda
