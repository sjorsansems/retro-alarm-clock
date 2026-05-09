"""
DFPlayer Mini driver voor MicroPython (ESP32-S3)
Communicatie via UART — 9600 baud, 8N1

Bedrading:
  ESP32-S3 TX (GPIO17)  -->  1kΩ weerstand  -->  DFPlayer RX
  ESP32-S3 RX (GPIO18)  <--                  <--  DFPlayer TX
  5V (of 3.3V)          -->  DFPlayer VCC
  GND                   -->  DFPlayer GND
  Speaker               <->  DFPlayer SPK_1 / SPK_2
  (optioneel)  DFPlayer BUSY --> GPIO (LOW = speelt af)
"""

from machine import UART, Pin
import time


class DFPlayer:
    # Bronnen
    SRC_USB   = 1
    SRC_TF    = 2  # SD-kaart

    def __init__(self, uart_id=1, tx_pin=17, rx_pin=18, busy_pin=None, volume=20):
        self._uart = UART(uart_id, baudrate=9600, tx=Pin(tx_pin), rx=Pin(rx_pin),
                          bits=8, parity=None, stop=1, timeout=100)
        self._busy = Pin(busy_pin, Pin.IN) if busy_pin is not None else None
        time.sleep_ms(1000)  # DFPlayer heeft ~1s opstarttijd nodig
        self._drain_uart()
        self.reset()
        self.select_source(self.SRC_TF)
        self.set_volume(0)    # start stil; beller stelt volume in voor afspelen

    # ---- interne helpers ----

    def _checksum(self, data):
        return -sum(data) & 0xFFFF

    def _send(self, cmd, param_hi=0, param_lo=0):
        cs = self._checksum([0xFF, 0x06, cmd, 0x00, param_hi, param_lo])
        pkt = bytes([
            0x7E, 0xFF, 0x06, cmd, 0x00,
            param_hi, param_lo,
            (cs >> 8) & 0xFF, cs & 0xFF,
            0xEF
        ])
        self._uart.write(pkt)
        time.sleep_ms(30)  # kleine rust tussen commando's

    def _drain_uart(self):
        try:
            while self._uart.any():
                self._uart.read()
                time.sleep_ms(5)
        except Exception:
            pass

    # ---- publieke API ----

    def set_volume(self, vol):
        """Zet volume (0–30)."""
        self._send(0x06, 0, max(0, min(30, int(vol))))

    def play_track(self, track):
        """Speel track N af van de SD-kaart (bestand volgorde, 1-based)."""
        self._send(0x03, 0, max(1, int(track)))

    def play_mp3(self, track):
        """Speel bestand uit de /MP3/ map op de SD-kaart (0001.mp3 … 9999.mp3)."""
        self._send(0x12, (track >> 8) & 0xFF, track & 0xFF)

    def select_source(self, source):
        """Selecteer afspeelbron, bijvoorbeeld TF/SD-kaart."""
        self._send(0x09, 0, int(source))
        time.sleep_ms(200)

    def play_folder(self, folder, track):
        """Speel track in map (01/ … 99/). Map = 1-byte, track = 1-byte."""
        self._send(0x0F, max(1, min(99, int(folder))), max(1, min(255, int(track))))

    def pause(self):
        self._send(0x0E)

    def resume(self):
        self._send(0x0D)

    def stop(self):
        self._send(0x16)

    def next_track(self):
        self._send(0x01)

    def prev_track(self):
        self._send(0x02)

    def loop_track(self, track):
        """Herhaal track N continu."""
        n = max(1, int(track))
        # 0x08 verwacht het tracknummer dat in single-loop moet draaien.
        self._send(0x08, (n >> 8) & 0xFF, n & 0xFF)

    def loop_all(self, enable=True):
        """Loop alle nummers."""
        self._send(0x11, 0, 1 if enable else 0)

    def set_eq(self, eq=0):
        """EQ: 0=Normal, 1=Pop, 2=Rock, 3=Jazz, 4=Classic, 5=Bass."""
        self._send(0x07, 0, eq)

    def sleep(self):
        """Zet DFPlayer in slaapstand (laag stroomverbruik)."""
        self._send(0x0A)

    def wake(self):
        """Wek DFPlayer op uit slaapstand."""
        self._send(0x0B)

    def reset(self):
        """Hardware-reset van de module."""
        self._send(0x0C)
        time.sleep_ms(1500)
        self._drain_uart()

    def is_busy(self):
        """Geeft True terug als de module momenteel afspeelt (via BUSY-pin)."""
        if self._busy is None:
            return False
        return self._busy.value() == 0  # BUSY is actief-laag

    def query_track_count(self):
        """Vraag het totaal aantal bestanden op de SD-kaart op. Geeft int terug of None bij timeout."""
        self._drain_uart()
        self._send(0x48)  # query TF total files
        deadline = time.ticks_add(time.ticks_ms(), 500)
        buf = b''
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._uart.any():
                buf += self._uart.read()
                if len(buf) >= 10:
                    # zoek pakket: 0x7E ... 0xEF
                    for i in range(len(buf) - 9):
                        if buf[i] == 0x7E and buf[i+9] == 0xEF:
                            return (buf[i+5] << 8) | buf[i+6]
            time.sleep_ms(10)
        return None
