# Retro Georgy Alarm Clock (ESP32 + MicroPython)

```text
██████╗ ███████╗████████╗██████╗  ██████╗      █████╗ ██╗      █████╗ ██████╗ ███╗   ███╗
██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██╔═══██╗    ██╔══██╗██║     ██╔══██╗██╔══██╗████╗ ████║
██████╔╝█████╗     ██║   ██████╔╝██║   ██║    ███████║██║     ███████║██████╔╝██╔████╔██║
██╔══██╗██╔══╝     ██║   ██╔══██╗██║   ██║    ██╔══██║██║     ██╔══██║██╔══██╗██║╚██╔╝██║
██║  ██║███████╗   ██║   ██║  ██║╚██████╔╝    ██║  ██║███████╗██║  ██║██║  ██║██║ ╚═╝ ██║
╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝

		  8-BIT OLED ANIMATIONS  +  MP3 ALARM MUSIC  +  WS2812 LED THEMES
```

An ESP32-S3 retro alarm clock project with:
- SH1106 OLED 128x64 display and pixel animations
- DFPlayer Mini MP3 alarm playback
- WS2812 LED strip  (8 leds) effects per alarm theme
- DS3231 RTC support (with optional EEPROM schedule storage)
- WiFi time sync (NTP), weather data, and web configuration UI
- Setup AP fallback (`AlarmKlok-Setup`) when WiFi is not configured/reachable

## What We Built

This project is a complete standalone alarm device, not only a demo sketch.

Main features:
- Clock display with big 8-bit style digits
- Weekly alarm scheduling
- One-tap "skip next alarm once"
- Snooze support
- Theme-based Retro (games) alarm playback (audio + display animation + LEDs)
- A tool to convert (small) gif images to bin files which can be used as a alarmclock animation.
- - OTA updates via browser
- Setup access point mode for first-time WiFi setup
- Safe boot fallback to backup app after repeated boot failures

## Hardware Requirements

- 1x ESP32-S3 DevKitC-1 -> I used a N16R8, other models not tested. Enough Ram is mandantory. 
- 1x SH1106 OLED display (128x64, I2C)
- 1x DS3231 RTC module (I2C)
- Optional: AT24C32 EEPROM on RTC board (for schedule persistence)
- 1x DFPlayer Mini MP3 module + speaker
- 1x WS2812/NeoPixel LED strip (configured for 8 LEDs)
- 3x push buttons
- Wires + common GND
- Recommended: 1k resistor on ESP32 TX -> DFPlayer RX line

## Pin Mapping (Current v6)

| Function | ESP32 Pin | Notes |
|---|---:|---|
| OLED SDA | GPIO8 | SH1106 I2C bus |
| OLED SCL | GPIO9 | SH1106 I2C bus |
| RTC SDA | GPIO5 | Dedicated RTC I2C bus |
| RTC SCL | GPIO6 | Dedicated RTC I2C bus |
| DFPlayer TX (ESP->DF RX) | GPIO17 | Use 1k series resistor |
| DFPlayer RX (ESP<-DF TX) | GPIO18 | Direct is fine |
| WS2812 Data | GPIO2 | GRB byte order |
| Button UP | GPIO12 | Short press: nightlight toggle |
| Button DOWN | GPIO13 | Short: OLED mode, Long: WiFi toggle |
| Button SET | GPIO14 | Short: skip next alarm once, Long: alarm edit |

## Wiring Overview

### OLED (SH1106)
- VCC -> 3.3V
- GND -> GND
- SDA -> GPIO8
- SCL -> GPIO9

### RTC (DS3231)
- VCC -> 3.3V
- GND -> GND
- SDA -> GPIO5
- SCL -> GPIO6

### DFPlayer Mini
- VCC -> 5V preferred (or stable 3.3V if your module supports it)
- GND -> GND (shared with ESP32)
- DF RX <- ESP GPIO17 (through 1k resistor)
- DF TX -> ESP GPIO18
- SPK_1/SPK_2 -> Speaker

### WS2812 LED Strip
- DIN <- GPIO2
- VCC -> external 5V (recommended)
- GND -> GND (must be shared with ESP32)

### Buttons
- One side of each button -> GPIO12 / GPIO13 / GPIO14
- Other side -> GND
- Internal pull-ups are enabled in firmware

## Software Requirements

- MicroPython firmware on ESP32-S3
- Python 3.10+ on your PC
- `mpremote` for USB deployment (optional if you only use OTA)

Optional local tooling:
- FFmpeg (audio conversion)

## Project Structure (Important Files)

- `main.py` -> boot entrypoint with safe-mode fallback logic
- `retro_georgy_alarm_klok_v6.py` -> main application
- `retro_georgy_alarm_klok_v6_backup.py` -> backup runtime target
- `index_v6.html` -> web UI served by the device
- `config_manager.py` -> config defaults/load/save
- `config.example.json` -> safe config template for repo sharing
- `neopixel_driver.py`, `dfplayer.py`, `ds3231.py` -> hardware drivers

## Installation

### 1. Flash MicroPython
Flash an ESP32-S3 MicroPython firmware compatible with your board.

### Optional: Web Installer (WLED-style)

this repo includes an ESP Web Tools setup.
But you can also install Microphthon yourself en use the Powershell script included.

- `web-installer/install.html`
- `web-installer/manifest.json`

Usage:

1. Ensure `web-installer/manifest.json` points to a valid ESP32-S3 firmware `.bin`.
2. Publish your repo with GitHub Pages.
3. Open `https://<your-user>.github.io/<your-repo>/web-installer/install.html`.
4. Click **Install Alarm Clock Firmware** and select your board serial port.

Live installer URL for this project:

- https://sjorsansems.github.io/retro-alarm-clock/web-installer/install.html

Important:

- Web Serial only works on secure pages (`https://`) in compatible browsers (Chrome/Edge).
- This web installer flashes firmware only.

After flashing, run one command in PowerShell to deploy app files:

```powershell
powershell -ExecutionPolicy Bypass -Command "iwr https://raw.githubusercontent.com/sjorsansems/retro-alarm-clock/main/tools/deploy_web_installer.ps1 -OutFile deploy_alarmklok.ps1; ./deploy_alarmklok.ps1 -Port COM7"
```

Change `COM7` if your device uses another port.

### 2. Clone the Project

```bash
git clone <your-repo-url>
cd AlarmKlok
```

### 3. Prepare Configuration

Use `config.example.json` as your base and create local `config.json` (not tracked in git).

### 4. Deploy to Device

USB deployment example:

```bash
python -m mpremote connect COM7 + cp main.py :main.py + cp retro_georgy_alarm_klok_v6.py :retro_georgy_alarm_klok_v6.py + cp retro_georgy_alarm_klok_v6_backup.py :retro_georgy_alarm_klok_v6_backup.py + cp config_manager.py :config_manager.py + cp index_v6.html :index_v6.html + cp config.json :config.json + reset
```

### 5. First Boot / Setup AP

If WiFi is not configured or unavailable, the device starts AP mode:
- SSID: `AlarmKlok-Setup`
- IP: `192.168.4.1`

Connect to that network, open the page, and save your WiFi credentials.

## Web Interface

When connected to your home network, open the device IP in your browser.

You can configure:
- Current time and seconds
- Timezone and UI language
- Alarm schedule per weekday
- Alarm test playback
- Weather location and update behavior
- WiFi behavior and setup credentials
- OTA file uploads
- GitHub Pages update checks and installs

## Automatic Updates via GitHub Pages

This project supports update checks against a GitHub Pages manifest:

- Manifest location (default): `updates/stable/manifest.json`
- Example URL: `https://sjorsansems.github.io/retro-alarm-clock/updates/stable/manifest.json`

How it works:

1. Clock checks the manifest URL.
2. If `version` is newer than the running app version, update is marked as available.
3. On install, files in manifest `files[]` are downloaded and swapped in place.
4. Clock schedules an automatic reboot.

Manifest format:

```json
{
	"version": "6.1.0",
	"channel": "stable",
	"files": [
		{
			"path": "retro_georgy_alarm_klok_v6.py",
			"url": "https://sjorsansems.github.io/retro-alarm-clock/updates/stable/retro_georgy_alarm_klok_v6.py",
			"sha256": "optional-hex-sha256"
		}
	]
}
```

Use the web UI card **GitHub Auto-Update** to:

- Enable/disable automatic checks
- Set check interval (hours)
- Change manifest URL
- Run manual check/install

## User Guide (Buttons)

Normal clock screen:
- `UP` short press -> Nightlight ON/OFF
- `DOWN` short press -> Cycle OLED brightness modes
- `DOWN` long press -> WiFi ON/OFF
- `SET` short press -> Skip next scheduled alarm once
- `SET` long press -> Enter alarm edit mode

During alarm:
- `SET` -> Stop alarm
- `DOWN` -> Snooze (10 minutes)

Alarm edit mode:
- `UP` -> Hour +1
- `DOWN` -> Minute +1
- `SET` long press -> Save

## Safe Boot / Fallback Mode

`main.py` tracks startup failures.
- Primary app: `retro_georgy_alarm_klok_v6`
- Backup app: `retro_georgy_alarm_klok_v6_backup`

After repeated boot failures, it switches to backup mode automatically.

## Music and Animations

- DFPlayer supports multiple numbered tracks
- Theme mapping controls LED + animation style per alarm tone
- Additional animation binaries (`.bin`) can be uploaded via web UI

### DFPlayer MP3 File Order (Required)

`0001.mp3` is the intro track and is included in this repository.

For built-in alarm tones/animations, users should add their own files in this exact order:

1. `0001.mp3` -> Intro (already in repo)
2. `0002.mp3` -> Zelda
3. `0003.mp3` -> Mario
4. `0004.mp3` -> Synthwave
5. `0005.mp3` -> Sonic
6. `0006.mp3` -> Metroid
7. `0007.mp3` -> Pokemon
8. `0008.mp3` -> Tetris
9. `0009.mp3` -> Moonstone
10. `0010.mp3` -> Arcade
11. `0011.mp3` -> DOOM
12. `0012.mp3` -> Knight Rider
13. `0013.mp3` -> Fire
14. `0014.mp3` -> Heartbeat
15. `0015.mp3` -> Matrix
16. `0016.mp3` -> Pac-Man
17. `0017.mp3` -> Pong
18. `0018.mp3` -> Radar
19. `0019.mp3` -> Skull
20. `0020.mp3` -> Snake
21. `0021.mp3` -> Space
22. `0022.mp3` -> UFO
23. `0023.mp3` -> Donkey

Notes:

- Use zero-padded names (`0002.mp3`, not `2.mp3`).
- Place files in DFPlayer root.
- Keep numbering stable after first setup.

### Custom Uploads: Matching Music and Animations in Web UI

After uploading custom `.bin` animations in **Animaties beheren**:

1. Use the **Muziek** dropdown to choose the MP3 track mapping.
2. Use the **LED** dropdown to choose the LED theme mapping.
3. Click **Save** per animation.

This allows user-uploaded animations to use any preferred track and LED style.

### GIF to BIN Tool (How to Use)

You can convert small GIF animations to the `.bin` format used by the clock.

Requirements:

- Python 3.10+
- Pillow (`pip install pillow`)

Converter script:

- `tools/gif_to_frames.py`

Example command:

```bash
python tools/gif_to_frames.py --input animations/mario.gif --output animations/mario.bin --width 128 --height 64 --fps 12 --bin
```

Recommended settings:

- Keep source GIF short (2-8 seconds)
- Low frame rate (8-15 fps) to reduce file size
- High contrast source for better 1-bit conversion quality

Upload workflow:

1. Open the clock web UI.
2. Go to **Animaties beheren**.
3. Upload your generated `.bin` file.
4. Optionally map that animation to music/LED theme in the same UI.

Notes:

- Large `.bin` files may fail upload if free storage is low.
- Use `/api/storage-info` (shown in UI) to check available upload space.

See `MUSIC_GUIDE.md` for detailed music sourcing and preparation.

## Troubleshooting

No OLED output:
- Check I2C wiring and 3.3V power

No RTC detected:
- Verify DS3231 pins on dedicated bus (GPIO5/GPIO6)

No DFPlayer sound:
- Verify UART wiring, power, and shared GND
- Check speaker and SD content

No WiFi page:
- Check if AP mode is active (`AlarmKlok-Setup`)
- Otherwise verify station network connectivity

## License / Sharing Notes

- `config.json` is local-only and ignored by git
- Share `config.example.json` instead
- Do not commit personal WiFi credentials

---

```text
PRESS START TO WAKE UP.
```
