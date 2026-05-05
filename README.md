# Retro Georgy Alarm Klok (ESP32 + MicroPython)

Deze projectmap bevat een ESP32 alarmklok met:
- OLED display animaties per spelthema
- DFPlayer audio tracks (1 t/m 9)
- WS2812 LED-strip effecten per spel
- WiFi/NTP + web UI

## Bevestigde werkende WS2812 instelling

Op basis van de laatste test werkt de strip met:
- Data pin: GPIO2
- Methode: machine.bitstream
- Byte-order: GRB

## LED kleurschema per spelthema

Onderstaande mapping is gecontroleerd tegen de actieve implementatie in neopixel_driver.py.

1. Zelda (lied 1)
- Palet: groen -> goud
- Gedrag: zachte pulse
- Kleurgebied: R 0..200, G 200..255, B 0

2. Mario (lied 2)
- Palet: rood + geel
- Gedrag: checker/jump patroon (om en om per LED)
- Kernkleuren: (255,0,0) en (255,255,0)

3. Synthwave (lied 3)
- Palet: neon roze -> paars
- Gedrag: golf die over de strip beweegt
- Kleurgebied: roze (255,0,100), paars (150,0,255)

4. Sonic (lied 4)
- Palet: cyaan + blauw
- Gedrag: snelle strobe
- Kernkleuren: (0,200..250,255) en (0,100,200)

5. Metroid (lied 5)
- Palet: oranje -> rood
- Gedrag: intensiteit maakt kleur heter
- Kleurgebied: R 255 vast, G 200..100, B 0

6. Pokemon (lied 6)
- Palet: geel met rode accenten
- Gedrag: knipperfase tussen accent-patroon en vol geel
- Kernkleuren: geel (255,255,0), rood (255,0,0)

7. Tetris (lied 7)
- Palet: regenboogcyclus
- Gedrag: kleur wisselt per stap
- Volgorde: rood -> oranje -> geel -> groen -> blauw -> indigo -> violet

8. Moonstone (lied 8)
- Palet: maanblauw met fakkel-gouden accenten
- Gedrag: koude pulse met bewegende fakkel-highlight
- Kernkleuren: maan (ongeveer 40,80,180) + fakkel (ongeveer 255,140,20)

9. Arcade (lied 9)
- Palet: multicolor strobe
- Gedrag: snelle arcade-kleurwissel
- Volgorde: rood -> geel -> groen -> blauw -> magenta

## Waar dit in de code staat

- LED-themes: neopixel_driver.py (theme_zelda t/m theme_arcade)
- Thema-keuze: neopixel_driver.py, get_theme_func
- Alarmtone labels: retro_georgy_alarm_klok_v2.py, get_alarm_tone_options
