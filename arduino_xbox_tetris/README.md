# ESP32 Xbox Bluetooth Tetris (SH1106 OLED)

Dit project is bedoeld om direct te testen met een Xbox-controller via Bluetooth op een ESP32.

## Hardware

- ESP32 dev board
- OLED 128x64 SH1106 (I2C)
- Xbox-controller met Bluetooth

## Bedrading OLED

- VCC -> 3V3
- GND -> GND
- SDA -> GPIO21
- SCL -> GPIO22

## Arduino IDE setup

1. Installeer Arduino IDE 2.x.
2. Installeer ESP32 board package (Espressif Systems).
3. Kies board: ESP32 Dev Module (of jouw exacte variant).
4. Installeer libraries via Library Manager:
- Bluepad32
- U8g2
5. Open xbox_tetris_esp32.ino.
6. Selecteer juiste COM-poort.
7. Upload sketch.

## Controller koppelen

1. Zet de ESP32 aan met de sketch erop.
2. Zet Xbox-controller in pairing mode (knipperende Xbox-knop).
3. Binnen enkele seconden zou de controller verbinden.
4. Op het scherm verdwijnt de pairing-pagina en start Tetris.

## Knoppen

- D-pad links/rechts: bewegen
- D-pad omlaag: soft drop
- A: rotate
- B: hard drop
- X: pauze
- Y: restart

## Opmerking

De sketch roept BP32.forgetBluetoothKeys() aan tijdens startup, zodat opnieuw pairen simpel blijft tijdens testen.
Als je vaste pairing wilt behouden, verwijder die regel in de sketch.
